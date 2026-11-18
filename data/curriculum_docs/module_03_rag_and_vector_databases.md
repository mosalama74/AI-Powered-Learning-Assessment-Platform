# Module 3: Retrieval-Augmented Generation (RAG) and Vector Databases
Duration: 1.5 weeks. Prerequisite: Module 2.

## Learning goals
Learners ingest documents, split them into chunks, embed the chunks, store them in ChromaDB, and retrieve the most relevant chunks to ground LLM answers.

## Key concepts
- Chunking: split documents into pieces of about 500 to 800 characters with 10 to 15 percent overlap so ideas are not cut in half.
- Embeddings turn text into numbers so that similar meanings sit close together. It works like a library catalogue organised by meaning instead of alphabet.
- ChromaDB stores vectors on disk and returns the nearest chunks for a query. Retrieval should finish in under 1000 milliseconds in production.
- Top-k retrieval: k of 3 to 5 is a good default. Too large adds noise and cost.
- Agentic RAG adds self-reflection: the agent checks whether the retrieved context really answers the question and rewrites the query if not.
