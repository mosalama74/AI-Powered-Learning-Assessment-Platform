"""Assessor worker: grades Python submissions with live sandbox execution and an evaluator-optimizer loop.

Analogy: the Assessor is a teacher with an editor. The teacher runs the student's code (the sandbox), writes feedback,
the editor (LLM judge) scores that feedback against a checklist, and the teacher rewrites until it passes or the
editor's patience runs out after 3 rewrites (token and latency control).

Curriculum mapping: Module 1 (Assignment 1 auto-grader), Module 4 (sandboxed REPL), Module 6 (evaluator-optimizer with
a strict cap of 3 refinements), Placement and Grading Policy (rubric: correctness 50, code quality 20, error handling
20, feedback clarity 10; passing score 70).
"""
from __future__ import annotations  # forward references

import ast  # inspect docstrings and error handling in learner code
from typing import Optional, TypedDict  # typing helpers

from langgraph.graph import END, START, StateGraph  # graph building blocks

from src.llm import get_llm  # Gemini or offline stand-in
from src.state import MAX_REFINEMENTS, GradeReport, Judgement, TestOutcome, UnableToVerify  # schemas/constants
from src.tools.code_repl import run_python_tests, split_tests  # sandbox


class AssessorState(TypedDict, total=False):
    """Private working notebook of the Assessor sub-graph."""

    learner_id: Optional[str]  # whose submission
    code: str  # learner code
    tests: str  # assert tests (one per line)
    outcome: dict  # TestOutcome dict
    failure: dict  # UnableToVerify dict
    facts: str  # evidence summary given to the LLM
    draft: str  # current feedback draft
    judgement: dict  # latest Judgement dict
    refinements: int  # optimizer rounds used so far
    history: list  # judge scores per round (audit trail)
    report: dict  # final GradeReport dict


def code_quality_signals(code: str) -> tuple[int, int, bool]:
    """Return (functions_with_docstrings, total_functions, has_error_handling) by parsing the code (rubric items 2 and 3)."""
    try:
        tree = ast.parse(code)  # parse only
    except SyntaxError:
        return 0, 0, False
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]  # all functions
    documented = sum(1 for f in funcs if ast.get_docstring(f))  # those with docstrings
    handles = any(isinstance(n, (ast.Try, ast.Raise)) for n in ast.walk(tree))  # try/except or raise present
    return documented, len(funcs), handles


def rubric_score(outcome: TestOutcome, code: str, judge_score: int) -> int:
    """Combine the Sprints rubric: correctness 50 + docstrings 20 + error handling 20 + feedback clarity 10."""
    correctness = 50 * (outcome.passed / outcome.total) if outcome.total else 0  # hidden-test share
    doc, total, handles = code_quality_signals(code)  # static signals
    quality = 20 * (doc / total) if total else 0  # docstring coverage
    robustness = 20 if handles else 0  # has try/except or raise
    clarity = judge_score  # 0..10 from the evaluator
    return int(round(correctness + quality + robustness + clarity))  # 0..100


# ----------------------------- graph nodes -----------------------------
def _run_tests(state: AssessorState) -> dict:
    """Node: execute the submission in the sandbox. Sandbox failure -> structured 'Unable to verify'."""
    res = run_python_tests(state["code"], state["tests"])  # live execution
    if isinstance(res, UnableToVerify):  # REPL exception
        return {"failure": res.model_dump()}
    return {"outcome": res.model_dump()}


def _after_tests(state: AssessorState) -> str:
    """Conditional edge: stop early if the sandbox failed."""
    return "finalize" if state.get("failure") else "draft"


def _draft(state: AssessorState) -> dict:
    """Node (generator): build the evidence summary and write the first feedback draft."""
    o = TestOutcome(**state["outcome"])  # rebuild the model
    doc, total, handles = code_quality_signals(state["code"])  # static signals
    issue = o.errors[0] if o.errors else "no failing tests"  # headline issue
    facts = (f"Tests passed: {o.passed}/{o.total}\nIssue: {issue}\n"
             f"Docstrings: {doc}/{total} functions; error handling present: {'yes' if handles else 'no'}")
    try:
        draft = get_llm().draft_feedback(facts)  # LLM first draft
    except Exception:  # LLM outage: fall back to the raw evidence so the learner still gets something
        draft = facts
    return {"facts": facts, "draft": draft, "refinements": 0, "history": []}


def _evaluate(state: AssessorState) -> dict:
    """Node (evaluator): LLM-as-a-judge scores the current draft."""
    try:
        j = get_llm().judge_feedback(state["facts"], state["draft"])  # structured verdict
    except Exception:  # judge unavailable: accept the draft rather than loop forever
        j = Judgement(score=5, approved=True, critique="judge unavailable")
    return {"judgement": j.model_dump(), "history": state.get("history", []) + [j.score]}


def _after_eval(state: AssessorState) -> str:
    """Conditional edge: finish if approved OR the refinement cap is reached; otherwise refine again."""
    if state["judgement"]["approved"]:  # good enough
        return "finalize"
    if state.get("refinements", 0) >= MAX_REFINEMENTS:  # HARD STOP: client requirement (max 3 iterations)
        return "finalize"
    return "refine"


def _refine(state: AssessorState) -> dict:
    """Node (optimizer): rewrite the draft using the judge's critique. Counts one refinement."""
    try:
        new = get_llm().refine_feedback(state["facts"], state["draft"], state["judgement"]["critique"])  # LLM rewrite
    except Exception:
        new = state["draft"]  # keep the old draft if the LLM fails
    return {"draft": new, "refinements": state.get("refinements", 0) + 1}  # increment the loop counter


def _finalize(state: AssessorState) -> dict:
    """Node: assemble the GradeReport (or the 'Unable to verify' report)."""
    if state.get("failure"):  # sandbox failed: no grade can be verified
        f = UnableToVerify(**state["failure"])
        return {"report": GradeReport(learner_id=state.get("learner_id"), score=0, feedback=f"Unable to verify. ({f.reason})",
                                      unable_to_verify=f).model_dump()}
    o = TestOutcome(**state["outcome"])  # test evidence
    j = state["judgement"]  # last judgement
    score = rubric_score(o, state["code"], j["score"])  # weighted rubric
    capped = (not j["approved"]) and state.get("refinements", 0) >= MAX_REFINEMENTS  # stopped by the cap?
    feedback = state["draft"] + f" Final score: {score}/100 (pass mark 70)."  # learner-facing text
    return {"report": GradeReport(learner_id=state.get("learner_id"), score=score, feedback=feedback, tests=o,
                                  refinements_used=state.get("refinements", 0), judge_score=j["score"],
                                  halted_by_cap=capped).model_dump()}


def build_assessor_graph():
    """Compile the Assessor sub-graph: run_tests -> draft -> evaluate <-> refine (max 3) -> finalize."""
    g = StateGraph(AssessorState)  # typed state
    for name, fn in [("run_tests", _run_tests), ("draft", _draft), ("evaluate", _evaluate), ("refine", _refine), ("finalize", _finalize)]:
        g.add_node(name, fn)  # register nodes
    g.add_edge(START, "run_tests")
    g.add_conditional_edges("run_tests", _after_tests, {"draft": "draft", "finalize": "finalize"})  # early exit on sandbox failure
    g.add_edge("draft", "evaluate")
    g.add_conditional_edges("evaluate", _after_eval, {"finalize": "finalize", "refine": "refine"})  # the evaluator-optimizer loop
    g.add_edge("refine", "evaluate")
    g.add_edge("finalize", END)
    return g.compile()


def run_assessor(code: str, tests: str, learner_id: Optional[str] = None) -> GradeReport:
    """Grade one submission and return a validated GradeReport (used by the orchestrator and the notebook)."""
    out = build_assessor_graph().invoke({"code": code, "tests": tests, "learner_id": learner_id})
    return GradeReport(**out["report"])
