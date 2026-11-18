"""Advisor worker: answers curriculum questions (Agentic RAG) and learner progress/salary questions (SQLite).

Analogy: the Advisor is a study-desk mentor. For course questions they look up the handbook, check "did that page really
answer it?", and if not they rephrase the search (self-reflection, at most twice). For "how is SPR-1001 doing?" they open
the learner's file instead of guessing.

Curriculum mapping: Module 3 (Agentic RAG with self-reflection, top-k retrieval), Module 4 (SQL tools, graceful
'Unable to verify'), Module 5 (worker sub-graph in an orchestrator-worker design), Placement Policy (readiness rules).
"""
from __future__ import annotations  # forward references

from typing import Any, Optional, TypedDict  # typing helpers

from langgraph.graph import END, START, StateGraph  # graph building blocks

from src.llm import get_llm  # Gemini or offline stand-in
from src.state import MAX_RAG_RETRIES, AdvisorResult, Citation, PlacementRecommendation, UnableToVerify  # schemas/constants
from src.tools.db_queries import fetch_learner  # read-only SQLite lookup
from src.tools.rag_retriever import safe_retrieve  # guarded ChromaDB retrieval


class AdvisorState(TypedDict, total=False):
    """Private working notebook of the Advisor sub-graph (Module 5)."""

    question: str  # learner question
    intent: str  # curriculum_question | progress_query | placement_approval
    learner_id: Optional[str]  # who it is about
    query: str  # current retrieval query (may be rewritten)
    attempts: int  # retrieval rounds used
    chunks: list  # Citation dicts from the last retrieval
    latency_ms: float  # last retrieval latency
    context: str  # concatenated chunk text
    answer: str  # draft answer
    grounded: bool  # reflection verdict
    snapshot: dict  # learner DB row
    failure: dict  # UnableToVerify dict if a tool failed
    result: dict  # final AdvisorResult dict


def build_recommendation(row: dict[str, Any]) -> PlacementRecommendation:
    """Turn a learner row into a recommendation package for the human advisor (Placement Policy rules).

    Rule from the policy: Ready for Placement means >= 12 modules AND Python score >= 80. The AI only *recommends*;
    a human always makes the final decision (Module 6 HITL).
    """
    ready = row["readiness_status"] == "Ready for Placement"  # status flag from the DB
    meets = row["completed_modules"] >= 12 and row["python_assignment_score"] >= 80  # policy thresholds
    recommends = ready and meets  # both must hold
    if recommends:  # positive case
        why = (f"{row['name']} completed {row['completed_modules']}/15 modules with a Python score of "
               f"{row['python_assignment_score']}, meeting the Ready for Placement thresholds (>=12 modules, >=80).")
    elif row["readiness_status"] == "Dropped":  # left the programme
        why = f"{row['name']} is marked Dropped and cannot be placed under the policy."
    else:  # not yet ready
        why = (f"{row['name']} is '{row['readiness_status']}' with {row['completed_modules']}/15 modules and a score of "
               f"{row['python_assignment_score']}; thresholds (>=12 modules, >=80) are not met.")
    return PlacementRecommendation(
        learner_id=row["learner_id"], name=row["name"], readiness_status=row["readiness_status"],
        python_score=row["python_assignment_score"], completed_modules=row["completed_modules"],
        target_salary_egp=row["target_salary_egp"], recommended_employers=row["preferred_employers"],
        ai_rationale=why, ai_recommends_approval=recommends,
    )


# ----------------------------- graph nodes -----------------------------
def _entry_router(state: AdvisorState) -> str:
    """Conditional entry: curriculum questions use RAG; progress/placement questions use the database."""
    return "retrieve" if state["intent"] == "curriculum_question" else "lookup_learner"  # pick the first node


def _lookup_learner(state: AdvisorState) -> dict:
    """Node: fetch the learner row from SQLite; on any exception return a structured 'Unable to verify'."""
    if not state.get("learner_id"):  # cannot look up without an id
        return {"failure": UnableToVerify(tool="sqlite", reason="No learner id provided (expected e.g. SPR-1001).").model_dump()}
    res = fetch_learner(state["learner_id"])  # guarded read-only query
    if isinstance(res, UnableToVerify):  # DB exception
        return {"failure": res.model_dump()}
    if res.get("status") == "not_found":  # unknown id is not an exception but cannot be verified either
        return {"failure": UnableToVerify(tool="sqlite", reason=f"Learner {state['learner_id']} not found.").model_dump()}
    return {"snapshot": res}  # success


def _format_progress(state: AdvisorState) -> dict:
    """Node: build the learner-facing progress answer (no LLM needed: facts come straight from the DB)."""
    if state.get("failure"):  # propagate failure
        f = UnableToVerify(**state["failure"])  # rebuild the model
        return {"result": AdvisorResult(answer=f"Unable to verify. ({f.reason})", unable_to_verify=f).model_dump()}
    r = state["snapshot"]  # learner row
    text = (f"{r['name']} ({r['learner_id']}, {r['bootcamp_track']}): {r['completed_modules']}/15 modules completed, "
            f"Python assignment score {r['python_assignment_score']}, status '{r['readiness_status']}'. "
            f"Target salary: {r['target_salary_egp']:,} EGP. Preferred employers: {', '.join(r['preferred_employers'])}.")
    return {"result": AdvisorResult(answer=text, learner_snapshot=r).model_dump()}


def _retrieve(state: AdvisorState) -> dict:
    """Node: ChromaDB retrieval (<1000 ms budget). Increments the attempt counter."""
    query = state.get("query") or state["question"]  # first round uses the raw question
    res = safe_retrieve(query)  # guarded retrieval
    if isinstance(res, UnableToVerify):  # ChromaDB exception
        return {"failure": res.model_dump(), "attempts": state.get("attempts", 0) + 1}
    return {  # success: store chunks, context text and latency
        "query": query, "attempts": state.get("attempts", 0) + 1,
        "chunks": [c.model_dump() for c in res.chunks], "latency_ms": res.latency_ms,
        "context": "\n\n".join(c.text or c.snippet for c in res.chunks),  # full chunk text as context
    }


def _generate(state: AdvisorState) -> dict:
    """Node: write a grounded answer from the retrieved context (skipped if retrieval failed)."""
    if state.get("failure"):  # nothing to ground on
        return {}
    try:
        return {"answer": get_llm().answer(state["question"], state["context"])}  # Gemini (or offline) generation
    except Exception as exc:  # LLM outage
        return {"failure": UnableToVerify(tool="llm", reason=f"{type(exc).__name__}: {exc}").model_dump()}


def _reflect(state: AdvisorState) -> dict:
    """Node: self-reflection. Decide if the context supports the answer; if not, rewrite the query."""
    if state.get("failure"):  # skip when something already broke
        return {}
    try:
        ref = get_llm().reflect(state["question"], state["context"])  # structured verdict
    except Exception as exc:
        return {"failure": UnableToVerify(tool="llm", reason=f"{type(exc).__name__}: {exc}").model_dump()}
    out: dict = {"grounded": ref.grounded}  # store verdict
    if not ref.grounded and ref.better_query:  # prepare next round
        out["query"] = ref.better_query
    return out


def _after_reflect(state: AdvisorState) -> str:
    """Conditional edge: loop back to retrieval or finish. Hard cap: MAX_RAG_RETRIES rewrites."""
    if state.get("failure") or state.get("grounded"):  # done (success or failure)
        return "finalize"
    return "retrieve" if state.get("attempts", 0) <= MAX_RAG_RETRIES else "finalize"  # first try + 2 retries max


def _finalize(state: AdvisorState) -> dict:
    """Node: package the curriculum answer (or the failure) as an AdvisorResult."""
    if state.get("failure"):
        f = UnableToVerify(**state["failure"])
        return {"result": AdvisorResult(answer=f"Unable to verify. ({f.reason})", unable_to_verify=f,
                                        rag_attempts=state.get("attempts", 0)).model_dump()}
    cites = [Citation(**c) for c in state.get("chunks", [])[:3]]  # keep top three citations
    answer = state.get("answer", "")
    if not state.get("grounded"):  # be honest when reflection never became confident
        answer += " (Note: I could not fully confirm this from the curriculum; please check with a Sprints advisor.)"
    return {"result": AdvisorResult(answer=answer, citations=cites, rag_attempts=state.get("attempts", 0),
                                    retrieval_latency_ms=state.get("latency_ms")).model_dump()}


def build_advisor_graph():
    """Compile the Advisor sub-graph: conditional entry, RAG loop with self-reflection, DB branch."""
    g = StateGraph(AdvisorState)  # typed state
    for name, fn in [("lookup_learner", _lookup_learner), ("format_progress", _format_progress), ("retrieve", _retrieve),
                     ("generate", _generate), ("reflect", _reflect), ("finalize", _finalize)]:
        g.add_node(name, fn)  # register nodes
    g.add_conditional_edges(START, _entry_router, {"retrieve": "retrieve", "lookup_learner": "lookup_learner"})  # dynamic entry
    g.add_edge("lookup_learner", "format_progress")  # DB branch
    g.add_edge("format_progress", END)
    g.add_edge("retrieve", "generate")  # RAG branch
    g.add_edge("generate", "reflect")
    g.add_conditional_edges("reflect", _after_reflect, {"retrieve": "retrieve", "finalize": "finalize"})  # self-reflection loop
    g.add_edge("finalize", END)
    return g.compile()


def run_advisor(question: str, intent: str, learner_id: Optional[str] = None) -> AdvisorResult:
    """Run the Advisor sub-graph once and return a validated AdvisorResult."""
    out = build_advisor_graph().invoke({"question": question, "intent": intent, "learner_id": learner_id, "attempts": 0})
    return AdvisorResult(**out["result"])  # validate the worker contract
