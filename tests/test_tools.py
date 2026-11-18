"""Tests for the three tools: SQLite, sandboxed REPL, ChromaDB retriever (acceptance criteria 3 and 4)."""
import statistics  # median / quantiles for latency checks
import subprocess  # patched to simulate sandbox failure
import time  # sleep to simulate a slow embedder
from pathlib import Path  # path helper

import pytest  # test framework

from src.state import RETRIEVAL_BUDGET_MS, TestOutcome, UnableToVerify
from src.tools import code_repl, db_queries
from src.tools.rag_retriever import CurriculumRetriever, HashingEmbedder, get_retriever, safe_retrieve

TESTS = "assert add(1,2)==3\nassert add(0,0)==0\nassert add(-1,1)==0"  # shared assert tests
GOOD = "def add(a,b):\n    return a+b\n"  # correct submission


# ---------------- SQLite ----------------
def test_db_loads_all_csv_rows():
    assert db_queries.build_database() == 25  # the starter CSV has 25 learners


def test_fetch_learner_returns_salary_in_egp():
    row = db_queries.fetch_learner("spr-1001")  # lower-case id is accepted
    assert row["target_salary_egp"] == 30000 and row["preferred_employers"] == ["Fawry", "Swvl"]


def test_unknown_learner_is_not_an_exception():
    assert db_queries.fetch_learner("SPR-9999")["status"] == "not_found"


def test_missing_database_returns_unable_to_verify():
    res = db_queries.fetch_learner("SPR-1001", db_path=Path("/nonexistent/db.sqlite"))
    assert isinstance(res, UnableToVerify) and res.message == "Unable to verify" and res.tool == "sqlite"


@pytest.mark.parametrize("bad", ["DROP TABLE learners", "SELECT 1; DELETE FROM learners", "UPDATE learners SET name='x'", "PRAGMA table_info(learners)"])
def test_sql_tool_rejects_non_select(bad):
    assert isinstance(db_queries.run_select(bad), UnableToVerify)


def test_sql_tool_runs_cohort_query():
    res = db_queries.run_select("SELECT COUNT(*) AS n FROM learners WHERE readiness_status = ?", ("Ready for Placement",))
    assert res["rows"][0]["n"] == 11


# ---------------- Python REPL ----------------
def test_repl_all_pass():
    assert code_repl.run_python_tests(GOOD, TESTS).passed == 3


def test_repl_reports_failures():
    out = code_repl.run_python_tests("def add(a,b):\n    return a-b\n", TESTS)
    assert isinstance(out, TestOutcome) and out.passed == 1 and out.errors


def test_repl_blocks_dangerous_imports():
    out = code_repl.run_python_tests("import os\nos.system('echo hi')", TESTS)
    assert out.passed == 0 and "not allowed" in out.errors[0]


def test_repl_blocks_dunder_escape():
    out = code_repl.run_python_tests("x = ().__class__.__bases__", TESTS)
    assert "not allowed" in out.errors[0]


def test_repl_times_out_infinite_loop():
    out = code_repl.run_python_tests("while True: pass", TESTS, timeout_s=2)
    assert out.timed_out


def test_repl_does_not_leak_api_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "secret-123")  # a secret in the parent environment
    out = code_repl.run_python_tests("import json\nprint('ok')", "assert True")  # runs fine; child env is stripped
    assert out.passed == 1 and "secret" not in out.stdout


def test_repl_infrastructure_failure_returns_unable_to_verify(monkeypatch):
    def boom(*a, **k):
        raise OSError("sandbox down")
    monkeypatch.setattr(subprocess, "run", boom)  # simulate the sandbox process failing to start
    res = code_repl.run_python_tests(GOOD, TESTS)
    assert isinstance(res, UnableToVerify) and res.tool == "python_repl"


# ---------------- ChromaDB retrieval ----------------
def test_retrieval_p95_latency_under_1000ms():
    r = get_retriever()
    queries = ["passing score python assignment", "refinement iterations cap", "chunk size overlap", "who approves placement",
               "read only sql tool", "MemorySaver thread_id", "employer partners", "ReAct loop", "top-k retrieval", "interrupt resume"] * 3
    times = [r.retrieve(q).latency_ms for q in queries]  # 30 queries
    assert statistics.quantiles(times, n=20)[-1] < RETRIEVAL_BUDGET_MS  # 95th percentile
    assert max(times) < RETRIEVAL_BUDGET_MS


@pytest.mark.parametrize("q,expected", [("What is the passing score for the Python assignment?", "module_01"),
                                         ("How many refinement iterations are allowed?", "module_06"),
                                         ("How does MemorySaver isolate learner sessions?", "module_05"),
                                         ("Why must SQL tools be read-only?", "module_04"),
                                         ("What chunk size should I use for RAG?", "module_03")])
def test_retrieval_relevance_top2(q, expected):
    sources = [c.source for c in get_retriever().retrieve(q).chunks[:2]]
    assert any(expected in s for s in sources)


def test_slow_embedder_triggers_fast_lexical_fallback(tmp_path):
    class Slow(HashingEmbedder):  # an embedder that is far too slow
        name = "slow_test"
        def embed_query(self, text):
            time.sleep(3)
            return super().embed_query(text)
    r = CurriculumRetriever(persist_dir=tmp_path, embedder=Slow())
    res = r.retrieve("how many refinement iterations are allowed")
    assert res.mode == "lexical_fallback" and res.within_budget and res.latency_ms < RETRIEVAL_BUDGET_MS


def test_chromadb_failure_returns_unable_to_verify(monkeypatch):
    r = get_retriever()
    monkeypatch.setattr(r.collection.__class__, "query", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("index corrupted")))
    res = safe_retrieve("anything unique 12345")
    assert isinstance(res, UnableToVerify) and res.tool == "chromadb"
