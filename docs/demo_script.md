# Demo script (3-5 minutes) for a live, narrated recording

`docs/demo_walkthrough.mp4` is a silent, captioned replay recorded in **offline mode**. For the final submission, record your screen with your voice using Gemini:

```bash
cp .env.example .env     # add GOOGLE_API_KEY, keep GEMINI_MODEL=gemini-3.5-flash-lite
python -m src.main demo  # you will be asked to act as the human advisor in scene 4
```

| Time | Scene | Say (suggested) |
|---|---|---|
| 0:00-0:30 | Intro: show `README.md` architecture picture | "Sprints advisors and graders are the bottleneck. This LangGraph system has an orchestrator, an Advisor and an Assessor, and a human gate for placements." |
| 0:30-1:15 | Scene 1: curriculum question | "The orchestrator routes this to the Advisor. It searches ChromaDB, checks whether the context really answers the question, and answers. Retrieval is under 1000 ms, with a fallback." |
| 1:15-1:40 | Scene 2: progress and salary | "Facts and salary in EGP come from a read-only SQLite query, not model memory." |
| 1:40-2:30 | Scene 3: grading | "The Assessor runs the learner code in a sandbox, drafts feedback, an LLM judge scores it, and the loop is capped at three refinements. The score follows the Sprints rubric." |
| 2:30-3:30 | Scene 4: HITL | "Placement requests pause the graph. The human sees the AI recommendation and decides. Only then does the graph resume." Type `approve`, your name, a note. |
| 3:30-4:00 | Scene 5: failure | "If SQLite or the sandbox fails, we return a structured Unable to verify, never a guess." |
| 4:00-4:30 | Close: show `python -m pytest tests -q` (44 passed) | "Every acceptance criterion has an automated test." |
