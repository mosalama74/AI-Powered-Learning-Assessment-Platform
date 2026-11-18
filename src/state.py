"""Shared state and structured message schemas for the Sprints orchestrator.

Analogy: the global state is a shared notebook that travels with the learner's request.
Every node (orchestrator, advisor, assessor, human reviewer) reads from it and writes to it.
The Pydantic models are "forms" with fixed boxes, so agents can never hand each other free-form text.

Curriculum mapping:
  * Module 2 (Prompt Engineering and Structured Outputs) -> Pydantic schemas below.
  * Module 5 (LangGraph Orchestration and State)          -> OrchestratorState TypedDict + AgentMessage envelope.
  * Module 6 (Evaluator-Optimizer and HITL)               -> MAX_REFINEMENTS, GradeReport, PlacementRecommendation.
"""
from __future__ import annotations  # allow forward references in type hints

import uuid  # used to create unique trace ids for agent messages
from datetime import datetime, timezone  # timestamps for audit trail
from typing import Annotated, Any, Literal, Optional, TypedDict  # typing helpers for the state

from pydantic import BaseModel, Field  # Pydantic gives us validated, typed schemas
from langgraph.graph.message import add_messages  # reducer: appends messages instead of overwriting

# Hard cap on evaluator-optimizer refinements (client quality bar: strictly <= 3 iterations).
MAX_REFINEMENTS = 3
# Hard cap on Advisor self-reflection query rewrites (keeps RAG latency predictable).
MAX_RAG_RETRIES = 2
# Retrieval latency budget in milliseconds (client quality bar: ChromaDB must answer within 1000 ms).
RETRIEVAL_BUDGET_MS = 1000

# The four things a learner can ask the system to do.
Intent = Literal["curriculum_question", "progress_query", "grade_submission", "placement_approval", "unknown"]


class RouteDecision(BaseModel):
    """Orchestrator output (Module 5): which worker should handle the request."""

    intent: Intent = Field(description="Category of the learner request.")  # the chosen route
    learner_id: Optional[str] = Field(default=None, description="Learner id such as SPR-1001 if mentioned.")  # who it is about
    reasoning: str = Field(description="One-sentence justification for the route.")  # explainability for audits


class UnableToVerify(BaseModel):
    """Structured graceful-failure message returned when SQLite or the Python REPL fails (client quality bar)."""

    status: Literal["unable_to_verify"] = "unable_to_verify"  # fixed marker so callers can detect failure
    message: str = "Unable to verify"  # the exact phrase the client asked for
    tool: str = Field(description="Which tool failed: sqlite | python_repl | chromadb | llm.")  # where it broke
    reason: str = Field(description="Short, safe description of the exception.")  # why it broke


class Citation(BaseModel):
    """One retrieved curriculum chunk that supports an answer (Module 3)."""

    source: str  # file name of the curriculum document
    snippet: str  # short excerpt of the chunk text (for display)
    text: str = ""  # full chunk text (fed to the LLM as context)
    distance: float  # vector distance (lower = closer)


class RetrievalResult(BaseModel):
    """What the RAG retriever returns, including latency evidence for the 1000 ms bar."""

    query: str  # query actually used
    chunks: list[Citation]  # top-k chunks
    latency_ms: float  # wall-clock retrieval time
    within_budget: bool  # True if latency_ms <= RETRIEVAL_BUDGET_MS
    mode: str = "vector"  # "vector" normally, "lexical_fallback" if embedding was too slow


class Reflection(BaseModel):
    """Advisor self-reflection verdict (Agentic RAG, Module 3 + 5)."""

    grounded: bool = Field(description="Does the retrieved context contain the answer?")  # sufficient evidence?
    critique: str  # what is missing, if anything
    better_query: Optional[str] = None  # rewritten query for the next retrieval attempt


class AdvisorResult(BaseModel):
    """Advisor worker output."""

    answer: str  # final text for the learner
    citations: list[Citation] = []  # supporting chunks
    learner_snapshot: Optional[dict[str, Any]] = None  # DB row (progress, salary EGP) when relevant
    rag_attempts: int = 0  # how many retrieval rounds were used
    retrieval_latency_ms: Optional[float] = None  # last retrieval latency
    unable_to_verify: Optional[UnableToVerify] = None  # set if a tool failed


class TestOutcome(BaseModel):
    """Result of running a submission in the sandboxed REPL (Module 4)."""

    __test__ = False  # tell pytest this is not a test class despite its name

    passed: int  # number of passing assert tests
    total: int  # number of tests run
    stdout: str = ""  # captured print output (truncated)
    errors: list[str] = []  # short failure messages
    timed_out: bool = False  # True if the sandbox killed the run


class Judgement(BaseModel):
    """Evaluator LLM verdict on a feedback draft (Module 6, LLM-as-a-judge)."""

    score: int = Field(ge=0, le=10, description="Overall quality of the feedback, 0-10.")  # numeric quality
    approved: bool  # True when the draft meets the bar
    critique: str  # what to fix next round


class GradeReport(BaseModel):
    """Assessor worker output: final grade plus audited loop metadata."""

    learner_id: Optional[str] = None  # whose submission
    score: int = Field(ge=0, le=100)  # numeric grade
    feedback: str  # learner-facing feedback text
    tests: Optional[TestOutcome] = None  # raw execution evidence
    refinements_used: int = 0  # how many optimizer rounds ran (<= MAX_REFINEMENTS)
    judge_score: Optional[int] = None  # final evaluator score
    halted_by_cap: bool = False  # True if loop stopped because the cap was hit
    unable_to_verify: Optional[UnableToVerify] = None  # set if the REPL failed


class PlacementRecommendation(BaseModel):
    """Package sent to a human advisor for final approval (Module 6 HITL)."""

    learner_id: str  # learner under review
    name: str  # learner name
    readiness_status: str  # status from the DB
    python_score: int  # assignment score
    completed_modules: int  # modules done
    target_salary_egp: int  # target salary in EGP
    recommended_employers: list[str]  # employers from preferences
    ai_rationale: str  # why the AI suggests (or does not suggest) placement
    ai_recommends_approval: bool  # AI's suggestion; never final


class HumanDecision(BaseModel):
    """What the human reviewer sends back when resuming the graph."""

    decision: Literal["approve", "reject", "needs_more_info"]  # the human verdict
    reviewer: str = "human_advisor"  # who decided
    notes: str = ""  # free-text notes


class AgentMessage(BaseModel):
    """Structured envelope for Orchestrator <-> Worker communication (JSON-schema contract, Module 5)."""

    trace_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])  # correlates a request across agents
    sender: Literal["orchestrator", "advisor", "assessor", "human_reviewer"]  # who sent it
    recipient: Literal["orchestrator", "advisor", "assessor", "human_reviewer", "learner"]  # who receives it
    intent: Intent  # what the message is about
    status: Literal["ok", "needs_human", "error"] = "ok"  # outcome signal for routing
    payload: dict[str, Any] = {}  # validated worker result (model_dump)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())  # audit timestamp


class OrchestratorState(TypedDict, total=False):
    """Global LangGraph state (Module 5). total=False because nodes fill fields progressively."""

    messages: Annotated[list, add_messages]  # conversation history (append-only reducer)
    user_input: str  # latest learner request text
    learner_id: Optional[str]  # resolved learner id
    submission_code: Optional[str]  # Python code to grade, if any
    test_code: Optional[str]  # assert-based tests for the assignment
    route: dict  # RouteDecision.model_dump()
    worker_message: dict  # AgentMessage.model_dump() from the last worker
    recommendation: dict  # PlacementRecommendation.model_dump()
    human_decision: dict  # HumanDecision.model_dump()
    final_response: str  # text shown to the learner
    audit_log: list[str]  # human-readable trail of what happened
