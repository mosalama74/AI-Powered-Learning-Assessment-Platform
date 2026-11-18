# Module 6: Evaluator-Optimizer Loops and Human-in-the-Loop
Duration: 1.5 weeks. Prerequisite: Module 5.

## Learning goals
Learners improve answer quality with an LLM-as-a-judge loop and add human approval for high-stakes decisions.

## Key concepts
- Evaluator-optimizer: one LLM drafts, a second LLM judges against a rubric, and the drafter refines. It is like an editor sending a draft back to a writer.
- Always cap iterations. Sprints production limit is a maximum of 3 refinement iterations to control token cost and latency.
- Human-in-the-loop: LangGraph interrupt pauses the graph and saves state. A human reviews and resumes the graph with a Command carrying the decision.
- Placement approvals are high-stakes. A human career advisor must approve every final placement recommendation; the AI never approves alone.
