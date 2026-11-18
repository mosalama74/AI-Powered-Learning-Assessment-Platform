# Module 5: LangGraph Orchestration and State
Duration: 2 weeks. Prerequisite: Modules 3 and 4.

## Learning goals
Learners design multi-agent systems as graphs: nodes do work, edges decide what runs next, and a shared state travels through the graph.

## Key concepts
- StateGraph with a TypedDict state is the shared notebook that every node reads and writes.
- Orchestrator-worker pattern: a supervisor node classifies the request and routes it to a specialist worker such as the Advisor or the Assessor.
- Conditional edges implement dynamic routing. They replace deprecated linear chains.
- MemorySaver checkpointer stores a snapshot of the state after every step, keyed by thread_id, so each learner session has its own isolated memory.
- Structured agent-to-agent messages use a fixed JSON schema with sender, recipient, intent, and payload fields.
