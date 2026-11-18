"""Tests for the agents and orchestrator (acceptance criteria 1, 2, 4 and 5 plus HITL)."""
import pytest  # test framework
from langgraph.types import Command  # resume a paused graph

from src.agents import advisor_agent, assessor_agent, orchestrator
from src.agents.orchestrator import build_orchestrator
from src.state import MAX_REFINEMENTS, Judgement, UnableToVerify
from src.tools import code_repl

BAD = "def average(n):\n    return sum(n) / (len(n) + 1)\n"  # buggy learner code
TESTS = "assert average([2,4,6]) == 4\nassert average([10]) == 10"


class StubicLLM:
    """Test double that counts calls and lets us script the judge's behaviour."""

    def __init__(self, always_reject: bool):
        self.always_reject, self.judge_calls, self.refine_calls = always_reject, 0, 0  # counters

    def draft_feedback(self, facts): return "draft"
    def judge_feedback(self, facts, draft):
        self.judge_calls += 1  # count judge invocations
        return Judgement(score=3 if self.always_reject else 9, approved=not self.always_reject, critique="needs work")
    def refine_feedback(self, facts, draft, critique):
        self.refine_calls += 1  # count optimizer invocations
        return draft + "+"


# ---------------- Evaluator-optimizer loop (criterion 5) ----------------
def test_loop_halts_after_exactly_three_refinements(monkeypatch):
    stub = StubicLLM(always_reject=True)  # a judge that is never satisfied
    monkeypatch.setattr(assessor_agent, "get_llm", lambda: stub)
    rep = assessor_agent.run_assessor(BAD, TESTS)
    assert rep.refinements_used == MAX_REFINEMENTS == 3  # strict cap
    assert stub.refine_calls == 3 and stub.judge_calls == 4  # 1 initial judging + 3 after refinements
    assert rep.halted_by_cap is True


def test_loop_stops_immediately_when_approved(monkeypatch):
    stub = StubicLLM(always_reject=False)
    monkeypatch.setattr(assessor_agent, "get_llm", lambda: stub)
    rep = assessor_agent.run_assessor(BAD, TESTS)
    assert rep.refinements_used == 0 and stub.refine_calls == 0 and not rep.halted_by_cap


def test_offline_loop_improves_judge_score():
    rep = assessor_agent.run_assessor(BAD, TESTS)  # real offline judge
    assert rep.refinements_used >= 1 and rep.judge_score >= 8 and rep.refinements_used <= 3


def test_rubric_rewards_docstrings_and_error_handling():
    good = 'def average(n):\n    """Mean."""\n    if not n:\n        raise ValueError("empty")\n    return sum(n)/len(n)\n'
    rep = assessor_agent.run_assessor(good, "assert average([2,4,6]) == 4\nassert average([10]) == 10")
    assert rep.score >= 90 and rep.tests.passed == 2


# ---------------- Graceful fallback (criterion 4) ----------------
def test_assessor_unable_to_verify_when_sandbox_fails(monkeypatch):
    monkeypatch.setattr(assessor_agent, "run_python_tests", lambda *a, **k: UnableToVerify(tool="python_repl", reason="down"))
    rep = assessor_agent.run_assessor(BAD, TESTS)
    assert rep.unable_to_verify and rep.unable_to_verify.message == "Unable to verify" and rep.score == 0


def test_advisor_unable_to_verify_when_db_fails(monkeypatch):
    monkeypatch.setattr(advisor_agent, "fetch_learner", lambda lid: UnableToVerify(tool="sqlite", reason="locked"))
    res = advisor_agent.run_advisor("status of SPR-1001", "progress_query", "SPR-1001")
    assert res.unable_to_verify and res.answer.startswith("Unable to verify")


def test_advisor_unable_to_verify_for_unknown_learner():
    res = advisor_agent.run_advisor("status of SPR-9999", "progress_query", "SPR-9999")
    assert res.unable_to_verify is not None


def test_rag_self_reflection_is_bounded():
    res = advisor_agent.run_advisor("zzzz qqqq wwww xxxx unrelated gibberish", "curriculum_question")
    assert res.rag_attempts <= 3  # first try + at most 2 rewrites


# ---------------- Orchestrator routing, HITL and memory ----------------
@pytest.fixture()
def app():
    return build_orchestrator()


@pytest.mark.parametrize("text,intent", [("What chunk size should I use for RAG?", "curriculum_question"),
                                          ("What is the target salary of SPR-1002?", "progress_query"),
                                          ("Please approve placement for SPR-1001", "placement_approval")])
def test_dynamic_routing(app, text, intent):
    out = app.invoke({"user_input": text}, {"configurable": {"thread_id": f"r-{intent}"}})
    assert out.get("route", {}).get("intent") == intent or "__interrupt__" in out


def test_code_attachment_routes_to_assessor(app):
    out = app.invoke({"user_input": "hello", "submission_code": BAD, "test_code": TESTS}, {"configurable": {"thread_id": "g1"}})
    assert out["route"]["intent"] == "grade_submission" and "100" in out["final_response"]


def test_placement_always_pauses_for_human_and_resumes(app):
    cfg = {"configurable": {"thread_id": "h1"}}
    out = app.invoke({"user_input": "Please approve placement for SPR-1001"}, cfg)
    assert "__interrupt__" in out  # paused, nothing approved yet
    assert "final_response" not in out or not out.get("final_response")
    out = app.invoke(Command(resume={"decision": "approve", "reviewer": "Nour", "notes": "ok"}), cfg)
    assert "APPROVED by Nour" in out["final_response"]


def test_human_can_reject_even_when_ai_recommends_approval(app):
    cfg = {"configurable": {"thread_id": "h2"}}
    app.invoke({"user_input": "Please approve placement for SPR-1001"}, cfg)
    out = app.invoke(Command(resume={"decision": "reject", "reviewer": "Nour", "notes": "needs interview"}), cfg)
    assert "REJECTED" in out["final_response"] and "AI recommendation was: approve" in out["final_response"]


def test_not_ready_learner_gets_negative_ai_recommendation(app):
    cfg = {"configurable": {"thread_id": "h3"}}
    out = app.invoke({"user_input": "Please approve placement for SPR-1004"}, cfg)
    assert out["__interrupt__"][0].value["recommendation"]["ai_recommends_approval"] is False


def test_placement_for_unknown_learner_does_not_reach_human(app):
    out = app.invoke({"user_input": "Please approve placement for SPR-9999"}, {"configurable": {"thread_id": "h4"}})
    assert "__interrupt__" not in out and out["final_response"].startswith("Unable to verify")


def test_threads_are_isolated(app):
    app.invoke({"user_input": "What is the passing score?"}, {"configurable": {"thread_id": "A"}})
    app.invoke({"user_input": "What is the target salary of SPR-1002?"}, {"configurable": {"thread_id": "B"}})
    a = app.get_state({"configurable": {"thread_id": "A"}}).values
    b = app.get_state({"configurable": {"thread_id": "B"}}).values
    assert len(a["messages"]) == 2 and len(b["messages"]) == 2 and a["learner_id"] is None and b["learner_id"] == "SPR-1002"


def test_memory_accumulates_within_a_thread(app):
    cfg = {"configurable": {"thread_id": "M"}}
    app.invoke({"user_input": "What is the passing score?"}, cfg)
    app.invoke({"user_input": "How many refinement iterations are allowed?"}, cfg)
    assert len(app.get_state(cfg).values["messages"]) == 4  # two human + two AI messages


def test_unknown_intent_asks_for_clarification(app, monkeypatch):
    from src.state import RouteDecision
    class R:
        def route(self, t): return RouteDecision(intent="unknown", reasoning="test")
    monkeypatch.setattr(orchestrator, "get_llm", lambda: R())
    out = app.invoke({"user_input": "asdf"}, {"configurable": {"thread_id": "U"}})
    assert "rephrase" in out["final_response"]


def test_llm_outage_does_not_crash_router(app, monkeypatch):
    class Broken:
        def route(self, t): raise RuntimeError("503")
    monkeypatch.setattr(orchestrator, "get_llm", lambda: Broken())
    out = app.invoke({"user_input": "hi"}, {"configurable": {"thread_id": "X"}})
    assert out["route"]["intent"] == "unknown"
