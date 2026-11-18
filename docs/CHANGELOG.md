# Changelog of decisions

| Day | Decision | Why |
|---|---|---|
| 1-2 | Read deck and CSV; charter written; call audio unreviewed | Audio could not be transcribed offline; documented as an assumption |
| 3 | Pydantic schemas first (`state.py`) | Typed contracts keep agents from passing free text (Module 2) |
| 3 | `LLMClient` facade with an offline stand-in | Lets the whole graph be tested without a network or API key |
| 3 | Read-only SQLite connection (`mode=ro`) plus SELECT validation | Defence in depth; the agent can never change learner data |
| 4 | Own sandbox instead of LangChain `PythonREPL` | The utility runs in-process with full access; unsafe for learner code |
| 4 | Import **allow-list** instead of a block-list | Safer default: anything not needed for Module 1 is denied |
| 5 | One Chroma collection per embedder; cosine distance | Prevents mixing vector spaces when switching Gemini and offline |
| 5 | Embedding timeout (60% of budget) then lexical fallback | Guarantees the 1000 ms bar even if the network is slow |
| 5 | Chunks 600 chars with 80 overlap, k=4 | Within Module 3 guidance (500-800, 10-15%, k 3-5) |
| 6 | Advisor and Assessor are LangGraph sub-graphs | Each worker is independently testable; orchestrator stays small |
| 6 | Self-reflection capped at 2 rewrites | Bounds RAG latency and tokens |
| 7 | Refinement cap enforced in the conditional edge, not in the prompt | A prompt can be ignored; a graph edge cannot |
| 7 | Rubric score = 50 correctness + 20 docstrings + 20 error handling + 10 judge | Mirrors the Placement and Grading Policy |
| 8 | Placement always interrupts for a human, even when the AI recommends rejection | Humans keep final authority; AI recommendation is only advice |
| 8 | `MemorySaver` for checkpoints; history window of 6 messages | Meets session isolation; persistent saver listed as next step |
| 10 | 44 automated tests mapped to acceptance criteria | Evidence for the quality score |
| 10 | Offline embedder improved (stemming, 1024 dims) | Top-2 relevance rose from 3/7 to 7/7 on test questions |
| 11 | Fixed duplicate score text and a templating bug in the REPL runner | Found while running the demo and tests |
