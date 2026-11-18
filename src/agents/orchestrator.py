"""Orchestrator: the LangGraph supervisor that routes requests to workers and escalates placements to a human.

Analogy: the orchestrator is the front-desk coordinator of a hospital. It listens to the request, sends the person to the
right specialist (Advisor or Assessor), and for the high-stakes "may this learner be placed at an employer?" decision it
calls in a senior human who can approve or reject. The graph pauses (interrupt) and waits for the human; its notebook
(checkpointer) keeps everything safe while it waits.

Curriculum mapping: Module 5 (StateGraph, TypedDict state, conditional edges replacing linear chains, MemorySaver with
thread_id, structured AgentMessage contract), Module 6 (HITL with interrupt + Command(resume=...)).

Memory strategy (see docs/technical_report.pdf):
  * Short-term (per session): MemorySaver checkpointer keyed by thread_id = one isolated conversation per learner session.
  * Context window control: only the last MAX_HISTORY messages are shown to the router, so tokens do not grow forever.
  * Long-term facts: SQLite (learner records) and ChromaDB (curriculum) are queried on demand, not copied into the prompt.
"""
from __future__ import annotations  # forward references

from typing import Any, Optional  # typing helpers

from langchain_core.messages import AIMessage, HumanMessage  # chat message types for the history
from langgraph.checkpoint.memory import MemorySaver  # in-memory checkpointer (swap for SqliteSaver in production)
from langgraph.graph import END, START, StateGraph  # graph building blocks
from langgraph.types import interrupt  # pauses the graph for a human

from src.agents.advisor_agent import build_recommendation, run_advisor  # advisor worker
from src.agents.assessor_agent import run_assessor  # assessor worker
from src.llm import LEARNER_ID_RE, get_llm  # LLM facade
from src.state import AgentMessage, HumanDecision, OrchestratorState, PlacementRecommendation, RouteDecision, UnableToVerify  # schemas
from src.tools.db_queries import fetch_learner  # DB lookup for placement packages

MAX_HISTORY = 6  # number of recent messages the router may see (context-window control)


def _log(state: OrchestratorState, line: str) -> list[str]:
    """Return the audit log with one more line appended (audit trail for stakeholders)."""
    return state.get("audit_log", []) + [line]


# ----------------------------- nodes -----------------------------
def supervisor_node(state: OrchestratorState) -> dict:
    """Node: classify the request (dynamic routing). Code attached to the request always means grading."""
    text = state["user_input"]  # latest learner text
    history = state.get("messages", [])[-MAX_HISTORY:]  # trimmed memory window
    try:
        route = get_llm().route(text)  # Gemini structured routing
    except Exception as exc:  # LLM outage: route by simple rules so the system stays alive
        route = RouteDecision(intent="unknown", reasoning=f"router failed: {type(exc).__name__}")
    if state.get("submission_code"):  # deterministic override: attached code is a grading request
        route = RouteDecision(intent="grade_submission", learner_id=route.learner_id, reasoning="code attached to the request")
    m = LEARNER_ID_RE.search(text)  # also catch an id the router missed
    lid = state.get("learner_id") or route.learner_id or (m.group(0).upper() if m else None)  # best known id
    return {"route": route.model_dump(), "learner_id": lid, "messages": [HumanMessage(content=text)],
            "audit_log": _log(state, f"orchestrator: routed to '{route.intent}' ({route.reasoning}); history_window={len(history)}")}


def route_edge(state: OrchestratorState) -> str:
    """Conditional edge: choose the next worker from the route intent."""
    intent = state["route"]["intent"]
    if intent in ("curriculum_question", "progress_query"):
        return "advisor"
    if intent == "placement_approval":
        return "placement_prep"
    if intent == "grade_submission":
        return "assessor"
    return "finalize"  # unknown intent: ask for clarification


def advisor_node(state: OrchestratorState) -> dict:
    """Node: delegate to the Advisor and wrap its result in a structured AgentMessage."""
    intent = state["route"]["intent"]
    res = run_advisor(state["user_input"], intent, state.get("learner_id"))  # sub-graph call
    status = "error" if res.unable_to_verify else "ok"
    msg = AgentMessage(sender="advisor", recipient="orchestrator", intent=intent, status=status, payload=res.model_dump())
    return {"worker_message": msg.model_dump(), "audit_log": _log(state, f"advisor: status={status}, rag_attempts={res.rag_attempts}")}


def assessor_node(state: OrchestratorState) -> dict:
    """Node: delegate to the Assessor (sandbox + evaluator-optimizer) and wrap the result."""
    rep = run_assessor(state["submission_code"], state.get("test_code") or "", state.get("learner_id"))  # sub-graph call
    status = "error" if rep.unable_to_verify else "ok"
    msg = AgentMessage(sender="assessor", recipient="orchestrator", intent="grade_submission", status=status, payload=rep.model_dump())
    return {"worker_message": msg.model_dump(),
            "audit_log": _log(state, f"assessor: score={rep.score}, refinements={rep.refinements_used}, halted_by_cap={rep.halted_by_cap}")}


def placement_prep_node(state: OrchestratorState) -> dict:
    """Node: Advisor-side preparation of the recommendation package. Always escalates to a human on success."""
    lid = state.get("learner_id")
    row = fetch_learner(lid) if lid else UnableToVerify(tool="sqlite", reason="No learner id provided.")  # DB lookup
    if isinstance(row, UnableToVerify) or row.get("status") == "not_found":  # cannot build a package
        why = row if isinstance(row, UnableToVerify) else UnableToVerify(tool="sqlite", reason=f"Learner {lid} not found.")
        msg = AgentMessage(sender="advisor", recipient="orchestrator", intent="placement_approval", status="error",
                           payload={"unable_to_verify": why.model_dump(), "answer": f"Unable to verify. ({why.reason})"})
        return {"worker_message": msg.model_dump(), "audit_log": _log(state, "advisor: placement package failed -> Unable to verify")}
    rec = build_recommendation(row)  # policy-based recommendation
    msg = AgentMessage(sender="advisor", recipient="human_reviewer", intent="placement_approval", status="needs_human", payload=rec.model_dump())
    return {"worker_message": msg.model_dump(), "recommendation": rec.model_dump(),
            "audit_log": _log(state, f"advisor: placement package ready (AI recommends approval={rec.ai_recommends_approval}) -> human review")}


def after_prep_edge(state: OrchestratorState) -> str:
    """Conditional edge: only 'needs_human' messages go to the human reviewer."""
    return "human_review" if state["worker_message"]["status"] == "needs_human" else "finalize"


def human_review_node(state: OrchestratorState) -> dict:
    """Node (HITL): pause the graph and wait for a human advisor to approve or reject.

    interrupt() saves the state via the checkpointer and returns control to the caller. When the caller resumes with
    Command(resume={...}), this node restarts and interrupt() returns the human's answer. Do not put side effects
    before interrupt(): the node body runs again on resume.
    """
    answer = interrupt({"type": "placement_approval_request", "recommendation": state["recommendation"],
                        "instructions": "Reply with {decision: approve|reject|needs_more_info, reviewer, notes}."})  # pause here
    decision = HumanDecision(**answer)  # validate the human's reply
    msg = AgentMessage(sender="human_reviewer", recipient="orchestrator", intent="placement_approval", status="ok", payload=decision.model_dump())
    return {"human_decision": decision.model_dump(), "worker_message": msg.model_dump(),
            "audit_log": _log(state, f"human_reviewer: {decision.decision} by {decision.reviewer}")}


def finalize_node(state: OrchestratorState) -> dict:
    """Node: compose the learner/stakeholder-facing response from the last worker message."""
    intent = state["route"]["intent"]
    wm = state.get("worker_message")
    if intent == "unknown" or wm is None:  # nothing matched
        text = "I can answer Sprints curriculum questions, report learner progress, grade Python code, or prepare a placement for human approval. Could you rephrase?"
    elif wm["status"] == "error":  # structured graceful failure
        text = wm["payload"].get("answer") or "Unable to verify."
    elif intent in ("curriculum_question", "progress_query"):
        text = wm["payload"]["answer"]
    elif intent == "grade_submission":
        p = wm["payload"]
        text = p["feedback"]  # feedback already ends with the final score line
    else:  # placement approval after human decision
        rec, d = state["recommendation"], state["human_decision"]
        verb = {"approve": "APPROVED", "reject": "REJECTED", "needs_more_info": "SENT BACK for more information"}[d["decision"]]
        text = (f"Placement for {rec['name']} ({rec['learner_id']}) was {verb} by {d['reviewer']}. "
                f"AI recommendation was: {'approve' if rec['ai_recommends_approval'] else 'do not approve'}. Notes: {(d['notes'] or 'none').rstrip('.')}.")
    return {"final_response": text, "messages": [AIMessage(content=text)], "audit_log": _log(state, "orchestrator: final response ready")}


def build_orchestrator(checkpointer: Optional[Any] = None):
    """Compile the orchestrator graph (a checkpointer is required for HITL interrupts)."""
    g = StateGraph(OrchestratorState)  # typed global state
    g.add_node("supervisor", supervisor_node)  # router
    g.add_node("advisor", advisor_node)  # RAG + DB worker
    g.add_node("assessor", assessor_node)  # grading worker
    g.add_node("placement_prep", placement_prep_node)  # recommendation builder
    g.add_node("human_review", human_review_node)  # HITL
    g.add_node("finalize", finalize_node)  # response composer
    g.add_edge(START, "supervisor")
    g.add_conditional_edges("supervisor", route_edge, {"advisor": "advisor", "assessor": "assessor", "placement_prep": "placement_prep", "finalize": "finalize"})  # dynamic routing
    g.add_edge("advisor", "finalize")
    g.add_edge("assessor", "finalize")
    g.add_conditional_edges("placement_prep", after_prep_edge, {"human_review": "human_review", "finalize": "finalize"})  # HITL gate
    g.add_edge("human_review", "finalize")
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer or MemorySaver())  # MemorySaver gives per-thread memory
