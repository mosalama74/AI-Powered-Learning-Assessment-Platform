# Module 2: Prompt Engineering and Structured Outputs
Duration: 1 week. Prerequisite: Module 1.

## Learning goals
Learners write prompt templates with variables, use few-shot examples, and force structured JSON output with Pydantic schemas and output parsers.

## Key concepts
- Prompt templates separate fixed instructions from variable inputs, like a form letter with blanks.
- Pydantic models define the exact fields an LLM answer must contain. Invalid answers raise a validation error and can be retried.
- Chaining: the output of one prompt becomes the input of the next. Chains are linear, so they are good for fixed pipelines but not for dynamic routing.
- Temperature: use 0 for grading and extraction, higher values for creative writing.
