# Module 4: Tools and ReAct Agents
Duration: 1.5 weeks. Prerequisite: Module 2.

## Learning goals
Learners build agents that decide which tool to call, using the Reason plus Act (ReAct) loop: think, call a tool, observe the result, repeat.

## Key concepts
- A tool is a Python function with a clear name, a docstring, and typed arguments. The docstring is what the LLM reads to decide when to use it.
- SQL tools must be read-only. Learners must validate that queries start with SELECT and use parameters to prevent SQL injection.
- Python REPL tools run code. Learners must sandbox them with timeouts, restricted imports, and a separate process, because running unknown code is dangerous.
- Graceful failure: when a tool raises an exception, the agent returns a structured Unable to verify message instead of guessing.
