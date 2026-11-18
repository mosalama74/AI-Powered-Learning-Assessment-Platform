# Project Charter: Sprints Multi-Agent AI Career & Assessment Orchestrator

**Sponsor:** Youssef El-Sherif, VP Engineering, Sprints | **Role:** Lead AI Systems Architect | **Duration:** 14 days

## Problem
Sprints is scaling employer-connected bootcamps. Human advisors and technical graders are the bottleneck for three repetitive jobs: answering curriculum questions, grading Python submissions, and preparing placement decisions. Placement is high-stakes, so full automation is not acceptable.

## Scope
**In:** LangGraph orchestrator with Advisor and Assessor workers; ChromaDB RAG over the curriculum; read-only SQLite tools (progress, target salary in EGP); sandboxed Python grading; evaluator-optimizer loop (max 3 refinements); human-in-the-loop approval for placements; structured JSON messages between agents; report, deck, notebook, demo.
**Out:** web UI, authentication, real employer integrations, writing back to the learner database, production deployment.

## Success criteria (from the brief and kickoff deck)
1. LangGraph is used for all orchestration and routing (no linear chains for dynamic routing).
2. Every function and tool has a docstring mapped to a Sprints curriculum module.
3. ChromaDB retrieval completes in under 1000 ms (measured, with a fallback if embedding is slow).
4. SQLite or REPL exceptions return a structured `Unable to verify`.
5. The evaluator-optimizer loop halts after at most 3 refinements.
6. No placement is approved without a human decision.
7. All deliverables in the expected submission tree.

## Risks and mitigations
| Risk | Mitigation |
|---|---|
| Running untrusted learner code | Separate process, import allow-list, timeout, CPU/memory limits, secrets stripped from environment |
| LLM latency or outage | Timeouts, retries, deterministic fallbacks, `Unable to verify` messages |
| Query embedding is slower than 1000 ms | 600 ms embedding timeout, then local keyword fallback; query cache |
| Judge never approves (token cost) | Hard cap of 3 refinements, enforced in the graph edge |
| Prompt or data mistakes affect careers | Human approval is mandatory; AI only recommends |
| Small sample data | Code is data-size agnostic; tests do not depend on row count |

## Assumptions
- **The discovery call recording (MP3) could not be transcribed in the build environment and is not reflected in this charter.** Requirements come from the written brief and kickoff deck. Any extra expectations from the call should be reviewed and added.
- The supplied CSV has 25 rows, not the 500 described in the kickoff deck; the starter repository link was not provided.
- Curriculum documents in `data/curriculum_docs/` were authored from the brief and deck as a stand-in for the real Sprints curriculum.
- Gemini (`GEMINI_MODEL=gemini-3.5-flash-lite`) is configured through `.env`; the system also runs with an offline stand-in for tests and demos.
