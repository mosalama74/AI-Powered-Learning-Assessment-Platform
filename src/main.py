"""Command-line entry point for the Sprints orchestrator.

Usage (from the repository root):
    python -m src.main demo                 # scripted end-to-end demo (uses Gemini if GOOGLE_API_KEY is set)
    python -m src.main demo --offline       # same demo with the deterministic offline stand-in (no internet)
    python -m src.main demo --auto-approve  # skip the interactive human prompt (approves automatically; for recordings/CI)
    python -m src.main chat                 # interactive session; HITL prompts you as the human advisor

Curriculum mapping: Module 5 (compiled graph + thread_id memory) and Module 6 (interrupt/resume HITL).
"""
from __future__ import annotations  # forward references

import argparse  # command-line parsing
import os  # environment variable for offline mode
import sys  # exit codes
import uuid  # unique thread ids per session

from langgraph.types import Command  # used to resume after a human decision

from src.state import PlacementRecommendation  # schema (for pretty printing)

BANNER = "=" * 78  # visual separator

# A flawed learner submission: works for some inputs but has a bug and no error handling (shows the refine loop).
DEMO_CODE = '''def average(numbers):
    return sum(numbers) / (len(numbers) + 1)
'''
DEMO_TESTS = "assert average([2, 4, 6]) == 4\nassert average([10]) == 10\nassert average([1, 2, 3, 4]) == 2.5"


def _print_section(title: str) -> None:
    """Print a section header."""
    print(f"\n{BANNER}\n{title}\n{BANNER}")


def ask(app, text: str, thread_id: str, *, code: str | None = None, tests: str | None = None,
        human_prompt: bool = True, auto_decision: dict | None = None) -> dict:
    """Send one request through the graph; if it pauses for a human, collect the decision and resume.

    Returns the final graph state dict (contains final_response and audit_log).
    """
    cfg = {"configurable": {"thread_id": thread_id}}  # thread_id isolates this session's memory
    payload = {"user_input": text}  # initial state values
    if code:  # grading request
        payload.update({"submission_code": code, "test_code": tests or ""})
    out = app.invoke(payload, cfg)  # run until finish or interrupt
    if "__interrupt__" in out:  # the graph paused for the human advisor
        pkg = out["__interrupt__"][0].value["recommendation"]  # what the human must review
        _print_section("HUMAN-IN-THE-LOOP: placement approval required (graph is paused)")
        for k, v in pkg.items():
            print(f"  {k:24}: {v}")
        if auto_decision is not None:  # scripted decision (demo/CI)
            decision = auto_decision
            print(f"\n  [scripted human decision] {decision}")
        elif human_prompt:  # real human at the keyboard
            d = input("\n  Decision (approve / reject / needs_more_info): ").strip().lower() or "needs_more_info"
            decision = {"decision": d, "reviewer": input("  Your name: ").strip() or "human_advisor", "notes": input("  Notes: ").strip()}
        else:
            return out  # leave paused
        out = app.invoke(Command(resume=decision), cfg)  # resume exactly where we stopped
    return out


def run_demo(auto_approve: bool) -> None:
    """Scripted walkthrough used for the recorded demo: query, grading, HITL, graceful fallback."""
    from src.agents.orchestrator import build_orchestrator  # imported here so --offline is applied first
    from src.tools import db_queries  # to simulate a DB outage
    app = build_orchestrator()  # compile once, reuse for every request
    sid = uuid.uuid4().hex[:6]  # session id

    _print_section("1) Student curriculum question (Advisor: Agentic RAG over ChromaDB)")
    q = "What is the maximum number of refinement iterations allowed in the evaluator-optimizer loop?"
    print("Learner:", q)
    out = ask(app, q, f"{sid}-q")
    print("System :", out["final_response"])
    print("Audit  :", *out["audit_log"], sep="\n   - ")

    _print_section("2) Progress and target salary (Advisor: read-only SQLite)")
    q = "How is SPR-1004 doing and what is her target salary?"
    print("Learner:", q)
    out = ask(app, q, f"{sid}-p")
    print("System :", out["final_response"])

    _print_section("3) Code grading (Assessor: sandbox + evaluator-optimizer loop, max 3 refinements)")
    print("Submission:\n" + DEMO_CODE)
    out = ask(app, "Please grade this Python submission for SPR-1004.", f"{sid}-g", code=DEMO_CODE, tests=DEMO_TESTS)
    print("System :", out["final_response"])
    print("Audit  :", *out["audit_log"], sep="\n   - ")

    _print_section("4) Placement approval request for SPR-1001 (must pause for a human)")
    q = "Please approve placement for SPR-1001."
    print("Learner:", q)
    auto = {"decision": "approve", "reviewer": "Nour (Career Advisor)", "notes": "Strong portfolio; confirmed with employer."} if auto_approve else None
    out = ask(app, q, f"{sid}-h", auto_decision=auto)
    print("\nSystem :", out["final_response"])
    print("Audit  :", *out["audit_log"], sep="\n   - ")

    _print_section("5) Graceful fallback: SQLite is unavailable")
    original = db_queries.DB_PATH  # remember the real path
    import src.tools.db_queries as dbq
    orig_fetch = dbq.fetch_learner
    dbq.fetch_learner = lambda lid, db_path=None: orig_fetch(lid, db_path=db_queries.ROOT / "missing" / "nope.db")  # point at a broken DB
    import src.agents.advisor_agent as adv
    adv.fetch_learner = dbq.fetch_learner  # advisor imported the function by name, so patch there too
    out = ask(app, "What is the target salary of SPR-1002?", f"{sid}-f")
    print("System :", out["final_response"])
    dbq.fetch_learner = orig_fetch  # restore
    adv.fetch_learner = orig_fetch


def run_chat() -> None:
    """Interactive loop: type questions, paste code with the 'grade:' prefix is not supported; use demo for grading."""
    from src.agents.orchestrator import build_orchestrator
    app = build_orchestrator()
    tid = uuid.uuid4().hex[:8]  # one session
    print("Sprints Orchestrator. Type a question (or 'quit').")
    while True:
        text = input("\nYou> ").strip()
        if text.lower() in {"quit", "exit", ""}:
            break
        out = ask(app, text, tid)
        print("\nSprints>", out["final_response"])


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch."""
    ap = argparse.ArgumentParser(description="Sprints Multi-Agent AI Career & Assessment Orchestrator")
    ap.add_argument("command", choices=["demo", "chat"])
    ap.add_argument("--offline", action="store_true", help="use the deterministic offline stand-in instead of Gemini")
    ap.add_argument("--auto-approve", action="store_true", help="demo: approve the placement automatically")
    args = ap.parse_args(argv)
    if args.offline:
        os.environ["SPRINTS_OFFLINE"] = "1"  # must be set before the LLM/embedder are created
    from src.tools.db_queries import DB_PATH, build_database  # ensure the SQLite DB exists
    if not DB_PATH.exists():
        print(f"Built SQLite DB with {build_database()} learners.")
    from src.llm import is_offline
    print(f"Mode: {'OFFLINE (no Gemini calls)' if is_offline() else 'LIVE (Gemini ' + os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite') + ')'}")
    run_demo(args.auto_approve) if args.command == "demo" else run_chat()
    return 0


if __name__ == "__main__":
    sys.exit(main())
