"""Curriculum ingestion + ChromaDB retrieval with a hard 1000 ms latency budget.

Analogy: ingestion is a librarian who cuts every handbook into index cards (chunks), writes each card's "meaning
fingerprint" (embedding) and files it in a drawer (ChromaDB). Retrieval is asking the librarian a question and getting the
3-5 closest cards back. If the fingerprint machine is slow (network), the librarian switches to quick keyword matching
so the orchestrator never times out.

Curriculum mapping: Module 3 (RAG and Vector Databases): chunking 500-800 chars with 10-15 percent overlap, top-k of
3 to 5, ChromaDB, retrieval under 1000 ms. Module 4: tools with docstrings and graceful failure.
"""
from __future__ import annotations  # forward references

import hashlib  # stable hashing for the offline embedder
import math  # vector normalisation
import os  # environment variables
import re  # tokenisation
import time  # latency measurement
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout  # enforce an embedding timeout
from functools import lru_cache  # cache repeated query embeddings
from pathlib import Path  # file paths
from typing import Optional  # typing helper

import chromadb  # vector database
from langchain_core.tools import tool  # expose retrieval to agents
from langchain_text_splitters import RecursiveCharacterTextSplitter  # chunking utility

from src.state import RETRIEVAL_BUDGET_MS, Citation, RetrievalResult, UnableToVerify  # shared schemas/constants

ROOT = Path(__file__).resolve().parents[2]  # repository root
DOCS_DIR = ROOT / "data" / "curriculum_docs"  # curriculum markdown files
CHROMA_DIR = ROOT / "data" / "chroma_db"  # persistent vector store location
CHUNK_SIZE = 600  # characters per chunk (Module 3 guideline: 500-800)
CHUNK_OVERLAP = 80  # about 13 percent overlap (Module 3 guideline: 10-15 percent)
DEFAULT_K = 4  # top-k (Module 3 guideline: 3-5)
STOPWORDS = {"the", "and", "for", "are", "with", "that", "this", "from", "you", "your", "what", "how", "does", "is", "of", "to", "in", "a", "an", "on", "it", "or", "as", "at", "by", "be"}


class HashingEmbedder:
    """Offline embedder: turns words and word pairs into a fixed-length vector with the hashing trick.

    Not as smart as Gemini embeddings, but deterministic, instant and needs no internet (used for tests and CI).
    """

    name = "hash1024"  # identifies the embedding space (collections are not mixed across embedders)
    dim = 1024  # vector length (larger = fewer hash collisions)

    @staticmethod
    def _stem(word: str) -> str:
        """Very light stemming so 'iterations' matches 'iteration' and 'approves' matches 'approval'-style variants."""
        for suffix in ("ations", "ation", "ments", "ment", "ings", "ing", "ies", "es", "ed", "s", "al"):  # common endings
            if word.endswith(suffix) and len(word) - len(suffix) >= 4:  # keep a meaningful stem
                return word[: -len(suffix)]
        return word

    def _vec(self, text: str) -> list[float]:
        """Embed one text."""
        tokens = [self._stem(t) for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]  # keep meaningful words, lightly stemmed
        feats = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]  # unigrams + bigrams
        v = [0.0] * self.dim  # empty vector
        for f in feats:  # hash each feature into a bucket with a +/- sign
            h = int(hashlib.md5(f.encode()).hexdigest(), 16)  # stable across runs (Python hash() is not)
            v[h % self.dim] += 1.0  # count into a bucket (unsigned: better for tiny corpora)
        norm = math.sqrt(sum(x * x for x in v)) or 1.0  # L2 norm
        return [x / norm for x in v]  # unit-length vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed many texts."""
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        """Embed one query."""
        return self._vec(text)


class GeminiEmbedder:
    """Online embedder using Google's Gemini embedding model through LangChain."""

    dim = 3072  # gemini-embedding-001 default size

    def __init__(self) -> None:
        """Create the Gemini embeddings client."""
        from langchain_google_genai import GoogleGenerativeAIEmbeddings  # imported lazily: only needed online

        model = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")  # model name from .env
        self.name = f"gemini_{model}"  # embedding-space id
        self._emb = GoogleGenerativeAIEmbeddings(model=f"models/{model}", google_api_key=os.getenv("GOOGLE_API_KEY"))  # client

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed many texts (called once, at ingestion time)."""
        return self._emb.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        """Embed one query (called at question time; protected by a timeout in the retriever)."""
        return self._emb.embed_query(text)


def make_embedder():
    """Pick the embedder: Gemini if a key is present and SPRINTS_OFFLINE != 1, else the offline hashing embedder."""
    if os.getenv("SPRINTS_OFFLINE") == "1" or not os.getenv("GOOGLE_API_KEY"):  # same rule as the chat model
        return HashingEmbedder()
    return GeminiEmbedder()


def _tokens(text: str) -> set[str]:
    """Lower-case keyword set used by the lexical fallback."""
    return {t for t in re.findall(r"[a-z0-9]{3,}", text.lower()) if t not in STOPWORDS}


class CurriculumRetriever:
    """Owns the ChromaDB collection and exposes ingest() and retrieve()."""

    def __init__(self, docs_dir: Path = DOCS_DIR, persist_dir: Path = CHROMA_DIR, embedder=None) -> None:
        """Open (or create) the persistent store and ingest the curriculum if the collection is empty."""
        self.docs_dir = docs_dir  # where curriculum files live
        self.embedder = embedder or make_embedder()  # chosen embedding model
        self.client = chromadb.PersistentClient(path=str(persist_dir))  # on-disk Chroma
        self.collection_name = f"sprints_curriculum_{self.embedder.name}"[:60].replace("-", "_").replace(".", "_")  # one collection per embedder
        self.collection = self.client.get_or_create_collection(self.collection_name, metadata={"hnsw:space": "cosine"})  # cosine distance
        self._chunk_cache: list[tuple[str, str]] = []  # (source, text) kept in RAM for the lexical fallback
        self._pool = ThreadPoolExecutor(max_workers=2)  # runs embedding calls so we can time them out
        self._cache: dict[str, list[float]] = {}  # query -> embedding cache
        if self.collection.count() == 0:  # first run: build the index
            self.ingest()
        else:  # later runs: reload chunk texts for the fallback
            got = self.collection.get(include=["documents", "metadatas"])
            self._chunk_cache = [(m["source"], d) for d, m in zip(got["documents"], got["metadatas"])]

    def ingest(self) -> int:
        """Load every markdown file, split into chunks, embed, and store in ChromaDB (Sprint 1 ingestion pipeline).

        Returns the number of chunks stored. Safe to re-run: the collection is rebuilt.
        """
        self.client.delete_collection(self.collection_name)  # start clean so re-ingest never duplicates
        self.collection = self.client.get_or_create_collection(self.collection_name, metadata={"hnsw:space": "cosine"})  # recreate
        splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP,
                                                  separators=["\n## ", "\n# ", "\n\n", "\n", ". ", " "])  # split on headings first
        ids, docs, metas = [], [], []  # parallel lists for Chroma
        for path in sorted(self.docs_dir.glob("*.md")):  # every curriculum file
            title = path.stem.replace("_", " ")  # e.g. "module 03 rag and vector databases"
            for i, chunk in enumerate(splitter.split_text(path.read_text(encoding="utf-8"))):  # chunk the file
                ids.append(f"{path.stem}-{i}")  # unique chunk id
                docs.append(f"[{title}] {chunk}")  # prefix with title so each chunk knows where it came from
                metas.append({"source": path.name, "chunk_index": i})  # metadata for citations
        embeddings = self.embedder.embed_documents(docs)  # embed all chunks once
        self.collection.add(ids=ids, documents=docs, metadatas=metas, embeddings=embeddings)  # store them
        self._chunk_cache = [(m["source"], d) for d, m in zip(docs, metas)]  # refresh fallback cache
        return len(ids)  # chunk count

    def _embed_query(self, query: str, timeout_s: float) -> Optional[list[float]]:
        """Embed a query with a timeout; returns None if the embedder is too slow (triggers the lexical fallback)."""
        if query in self._cache:  # repeated questions are free
            return self._cache[query]
        fut = self._pool.submit(self.embedder.embed_query, query)  # run in a worker thread
        try:
            vec = fut.result(timeout=timeout_s)  # wait at most timeout_s
        except (FuturesTimeout, Exception):  # too slow or failed
            return None
        self._cache[query] = vec  # remember
        return vec

    def _lexical_search(self, query: str, k: int) -> list[Citation]:
        """Fast local keyword search used only when vector embedding exceeds its time slice."""
        q = _tokens(query)  # query keywords
        scored = sorted(((len(q & _tokens(text)) / max(1, len(q)), src, text) for src, text in self._chunk_cache), reverse=True)  # overlap score
        return [Citation(source=src, snippet=text[:300], text=text, distance=round(1 - s, 4)) for s, src, text in scored[:k]]

    def retrieve(self, query: str, k: int = DEFAULT_K, budget_ms: float = RETRIEVAL_BUDGET_MS) -> RetrievalResult:
        """Return the top-k curriculum chunks for a query and prove the latency (client bar: within 1000 ms).

        Strategy: give embedding 60 percent of the budget; if it is slower, fall back to lexical search so the
        orchestrator never times out. The `mode` field records which path ran.
        """
        t0 = time.perf_counter()  # start the stopwatch
        vec = self._embed_query(query, timeout_s=budget_ms * 0.6 / 1000)  # embedding with timeout
        if vec is not None:  # normal path: vector search
            res = self.collection.query(query_embeddings=[vec], n_results=k, include=["documents", "metadatas", "distances"])
            chunks = [Citation(source=m["source"], snippet=d[:300], text=d, distance=round(dist, 4))
                      for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])]
            mode = "vector"
        else:  # slow/failed embedding: fallback path
            chunks, mode = self._lexical_search(query, k), "lexical_fallback"
        latency = (time.perf_counter() - t0) * 1000  # elapsed ms
        return RetrievalResult(query=query, chunks=chunks, latency_ms=round(latency, 2), within_budget=latency <= budget_ms, mode=mode)


_retriever: Optional[CurriculumRetriever] = None  # process-wide singleton (index is built once)


def get_retriever() -> CurriculumRetriever:
    """Return the shared retriever, creating it on first use."""
    global _retriever
    if _retriever is None or _retriever.embedder.name != make_embedder().name:  # rebuild if the embedding mode changed
        _retriever = CurriculumRetriever()
    return _retriever


def safe_retrieve(query: str, k: int = DEFAULT_K) -> RetrievalResult | UnableToVerify:
    """Retrieve with graceful failure: any ChromaDB error becomes a structured 'Unable to verify'."""
    try:
        return get_retriever().retrieve(query, k)  # normal path
    except Exception as exc:  # corrupted index, disk error...
        return UnableToVerify(tool="chromadb", reason=f"{type(exc).__name__}: {exc}")


@tool
def search_curriculum(query: str, k: int = 4) -> dict:
    """Search the Sprints Advanced Agentic AI curriculum (Modules 1-6 and the Placement and Grading Policy).

    Use this for any question about course content, assignments, passing scores, tools, LangGraph, RAG, HITL
    or placement rules. Returns the top-k chunks with source file, distance and measured latency in milliseconds
    (Module 3: ChromaDB retrieval under 1000 ms). Returns "Unable to verify" if ChromaDB fails.

    Args:
        query: Natural-language question or keywords.
        k: Number of chunks to return (3-5 recommended).
    """
    res = safe_retrieve(query, k)  # guarded retrieval
    return res.model_dump()  # JSON-able
