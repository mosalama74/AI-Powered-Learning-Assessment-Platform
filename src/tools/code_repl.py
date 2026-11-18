"""Sandboxed Python execution tool for grading learner submissions.

Analogy: grading unknown code is like testing a stranger's firework. We do it inside a concrete bunker:
a separate process (blast wall), a stopwatch (timeout), a short list of allowed imports (no matches),
and memory/CPU limits (small box). If the bunker itself fails, we report "Unable to verify" instead of guessing.

Why not LangChain's PythonREPL utility? It runs code inside our own process with full access to files, network
and secrets, which is unsafe for untrusted learner code. This tool keeps the same idea (a REPL as an agent tool)
but isolates it, as taught in Module 4 (Tools and ReAct Agents).

Curriculum mapping: Module 1 (assert-based unit tests, Assignment 1 auto-grader), Module 4 (sandboxed REPL tools,
graceful failure), Placement Policy (grading rubric: correctness 50 percent from hidden tests).
"""
from __future__ import annotations  # forward references

import ast  # parse code without running it, to enforce the import allow-list
import json  # exchange results with the sandbox process
import os  # environment and temp paths
import subprocess  # start the isolated process
import sys  # path of the current Python interpreter
import tempfile  # throw-away working directory
import textwrap  # clean multi-line strings
from typing import Iterable  # typing helper

from langchain_core.tools import tool  # make functions callable by agents

from src.state import TestOutcome, UnableToVerify  # structured result schemas

ALLOWED_IMPORTS = {  # only harmless standard-library modules taught in Module 1
    "math", "re", "json", "collections", "itertools", "functools", "typing", "string",
    "statistics", "datetime", "random", "decimal", "fractions", "heapq", "bisect",
}
BLOCKED_CALLS = {"eval", "exec", "compile", "open", "__import__", "input", "globals", "locals", "vars", "breakpoint", "exit", "quit"}
MARKER = "__SPRINTS_RESULT__"  # prefix of the JSON line the sandbox prints at the end
DEFAULT_TIMEOUT_S = 5  # wall-clock limit for one grading run

# The runner executes inside the child process. It loads the submission, then runs each assert test separately.
_RUNNER = textwrap.dedent('''
    import json, sys, io, contextlib
    payload = json.load(open(sys.argv[1]))                      # read code + tests written by the parent
    ns = {"__name__": "submission"}                              # fresh namespace for the submission
    buf = io.StringIO()                                          # capture print output of the learner
    errors, passed = [], 0                                       # counters
    with contextlib.redirect_stdout(buf):                        # silence stdout so only our JSON line is parsed
        try:
            exec(compile(payload["code"], "<submission>", "exec"), ns)   # define learner functions
            loaded = True
        except BaseException as e:                               # syntax or runtime error while loading
            loaded = False
            errors.append("load error: " + type(e).__name__ + ": " + str(e)[:150])
        if loaded:
            for t in payload["tests"]:                           # run each test independently
                try:
                    exec(compile(t, "<test>", "exec"), ns)       # an assert that raises means failure
                    passed += 1
                except BaseException as e:
                    errors.append(t[:80] + " -> " + type(e).__name__ + ": " + str(e)[:100])
    print("@@MARKER@@" + json.dumps({"passed": passed, "total": len(payload["tests"]), "stdout": buf.getvalue()[:500], "errors": errors[:5]}))
''').replace("@@MARKER@@", MARKER)


def split_tests(test_code: str) -> list[str]:
    """Split a block of test code into independent statements (one `assert ...` per non-empty line)."""
    return [ln.strip() for ln in test_code.splitlines() if ln.strip() and not ln.strip().startswith("#")]  # drop blanks/comments


def static_check(code: str) -> list[str]:
    """Return a list of policy violations found by parsing the code (empty list = allowed).

    Enforces the import allow-list and blocks dangerous builtins and dunder attribute access (Module 4 safety rules).
    """
    try:
        tree = ast.parse(code)  # parse only; nothing is executed here
    except SyntaxError as exc:  # learner syntax error is a normal grading outcome
        return [f"SyntaxError: {exc.msg} (line {exc.lineno})"]
    problems: list[str] = []  # collected violations
    for node in ast.walk(tree):  # visit every node
        if isinstance(node, ast.Import):  # import x
            for alias in node.names:
                if alias.name.split(".")[0] not in ALLOWED_IMPORTS:
                    problems.append(f"import of '{alias.name}' is not allowed")
        elif isinstance(node, ast.ImportFrom):  # from x import y
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS:
                problems.append(f"import from '{node.module}' is not allowed")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
            problems.append(f"call to '{node.func.id}' is not allowed")  # eval/exec/open...
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):  # block ().__class__ style escapes
            problems.append(f"dunder attribute '{node.attr}' is not allowed")
    return problems  # empty list means safe to run


def _limits() -> None:
    """Child-process hook: apply CPU, memory and file-size limits before the code starts (POSIX only)."""
    try:
        import resource  # Unix-only module
        resource.setrlimit(resource.RLIMIT_CPU, (3, 3))  # at most 3 CPU seconds
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)  # at most 512 MB address space
        resource.setrlimit(resource.RLIMIT_FSIZE, (1_000_000,) * 2)  # no file larger than 1 MB
    except Exception:  # on Windows this is skipped; the timeout still protects us
        pass


def run_python_tests(code: str, tests: Iterable[str] | str, timeout_s: int = DEFAULT_TIMEOUT_S) -> TestOutcome | UnableToVerify:
    """Execute a learner submission against assert tests inside the sandbox (Assignment 1 auto-grader).

    Returns TestOutcome for any learner-caused result (pass, fail, timeout, blocked import).
    Returns UnableToVerify only if the sandbox itself breaks (client requirement: graceful fallback).
    """
    test_list = split_tests(tests) if isinstance(tests, str) else list(tests)  # normalise tests to a list
    violations = static_check(code)  # policy check before running anything
    if violations:  # blocked code scores zero with a clear reason
        return TestOutcome(passed=0, total=len(test_list), errors=["Blocked by sandbox: " + "; ".join(violations[:3])])
    try:
        with tempfile.TemporaryDirectory() as tmp:  # private working directory, auto-deleted
            payload_path = os.path.join(tmp, "payload.json")  # where parent hands data to child
            runner_path = os.path.join(tmp, "runner.py")  # the runner script
            with open(payload_path, "w", encoding="utf-8") as fh:
                json.dump({"code": code, "tests": test_list}, fh)  # write inputs
            with open(runner_path, "w", encoding="utf-8") as fh:
                fh.write(_RUNNER)  # write the runner
            proc = subprocess.run(  # start the isolated process
                [sys.executable, "-I", runner_path, payload_path],  # -I = isolated mode (ignores env + user site)
                capture_output=True, text=True, timeout=timeout_s, cwd=tmp,  # stopwatch + private cwd
                env={"PATH": os.environ.get("PATH", "")},  # strip secrets such as GOOGLE_API_KEY
                preexec_fn=_limits if os.name == "posix" else None,  # resource limits on Linux/macOS
            )
        line = next((ln for ln in proc.stdout.splitlines() if ln.startswith(MARKER)), None)  # find result line
        if line is None:  # child died (e.g. CPU limit) without reporting
            return TestOutcome(passed=0, total=len(test_list), timed_out=proc.returncode != 0,
                               errors=["Sandbox process ended without a result (resource limit?)."])
        data = json.loads(line[len(MARKER):])  # parse child's JSON
        return TestOutcome(**data)  # validate into the schema
    except subprocess.TimeoutExpired:  # infinite loop or very slow code
        return TestOutcome(passed=0, total=len(test_list), timed_out=True, errors=[f"Timed out after {timeout_s}s."])
    except Exception as exc:  # the sandbox itself failed
        return UnableToVerify(tool="python_repl", reason=f"{type(exc).__name__}: {exc}")  # structured failure


@tool
def grade_python_submission(code: str, tests: str) -> dict:
    """Run a learner's Python submission against assert-style tests in a sandbox and return pass/fail evidence.

    Implements the Sprints Assignment 1 auto-grader (Module 1: assert tests; Module 4: sandboxed REPL tool).
    Correctness is 50 percent of the grading rubric in the Placement and Grading Policy.
    Returns "Unable to verify" if the sandbox itself fails.

    Args:
        code: The learner's Python source code (standard-library imports from the allow-list only).
        tests: One `assert ...` statement per line.
    """
    res = run_python_tests(code, tests)  # run in the sandbox
    return res.model_dump()  # both result types are Pydantic models


@tool
def execute_python(code: str) -> dict:
    """Run a short Python snippet in the sandbox and return its printed output (Module 4: Python REPL tool).

    Use for quick checks such as evaluating an expression a learner asks about. Same security limits as the grader.

    Args:
        code: Python source; allowed imports only.
    """
    res = run_python_tests(code, [])  # no tests: just execute and capture stdout
    return res.model_dump()  # JSON-able result
