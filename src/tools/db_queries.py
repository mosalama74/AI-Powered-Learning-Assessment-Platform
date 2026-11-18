"""SQLite tools for learner progress and target salary in EGP.

Analogy: the database is the registrar's filing cabinet. The tools below are a librarian who may only READ
folders (never write or shred them) and who hands back a structured "Unable to verify" slip if the cabinet is jammed.

Curriculum mapping: Module 4 (Tools and ReAct Agents) - read-only SQL tools, parameterised queries,
graceful failure; placement_and_grading_policy.md - readiness statuses and employer partners.
"""
from __future__ import annotations  # forward references

import csv  # read the starter CSV
import re  # validate SQL text
import sqlite3  # standard-library SQLite driver
from pathlib import Path  # file paths
from typing import Any, Optional  # typing helpers

from langchain_core.tools import tool  # decorator that turns a function into an LLM-callable tool

from src.state import UnableToVerify  # structured failure schema

ROOT = Path(__file__).resolve().parents[2]  # repository root
CSV_PATH = ROOT / "data" / "sprints_learner_db.csv"  # starter dataset from the client
DB_PATH = ROOT / "data" / "sprints_learner.db"  # SQLite database built from the CSV

_FORBIDDEN_SQL = re.compile(r"\b(insert|update|delete|drop|alter|create|attach|pragma|replace|vacuum)\b", re.I)  # write keywords


def build_database(csv_path: Path = CSV_PATH, db_path: Path = DB_PATH) -> int:
    """Load sprints_learner_db.csv into a SQLite table named `learners` (Sprint 1 data foundation).

    Returns the number of rows loaded. Safe to call repeatedly: the table is rebuilt each time.
    """
    with open(csv_path, newline="", encoding="utf-8") as fh:  # open the CSV
        rows = list(csv.DictReader(fh))  # parse every row into a dict
    conn = sqlite3.connect(db_path)  # open (or create) the database file
    try:
        conn.execute("DROP TABLE IF EXISTS learners")  # rebuild from scratch for reproducibility
        conn.execute(  # create the schema with proper types and a primary key
            """CREATE TABLE learners (
                learner_id TEXT PRIMARY KEY, name TEXT NOT NULL, bootcamp_track TEXT NOT NULL,
                completed_modules INTEGER NOT NULL, python_assignment_score INTEGER NOT NULL,
                target_salary_egp INTEGER NOT NULL, preferred_employers TEXT NOT NULL,
                readiness_status TEXT NOT NULL)"""
        )
        conn.executemany(  # bulk insert using named parameters (no string formatting -> no injection)
            "INSERT INTO learners VALUES (:learner_id,:name,:bootcamp_track,:completed_modules,"
            ":python_assignment_score,:target_salary_egp,:preferred_employers,:readiness_status)",
            rows,
        )
        conn.commit()  # persist
    finally:
        conn.close()  # always release the file handle
    return len(rows)  # report how many learners were loaded


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    """Open SQLite in read-only mode so even a bug cannot modify learner data."""
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2)  # URI mode=ro blocks writes


def fetch_learner(learner_id: str, db_path: Path = DB_PATH) -> dict[str, Any] | UnableToVerify:
    """Fetch one learner row by id (progress + target salary in EGP).

    Returns the row as a dict, or {"status": "not_found"} if the id does not exist, or an
    UnableToVerify object if SQLite raises any exception (client requirement).
    """
    try:
        conn = _connect_readonly(db_path)  # read-only connection
        try:
            conn.row_factory = sqlite3.Row  # rows behave like dicts
            cur = conn.execute("SELECT * FROM learners WHERE learner_id = ?", (learner_id.upper(),))  # parameterised query
            row = cur.fetchone()  # one row or None
        finally:
            conn.close()  # release the file
        if row is None:  # unknown learner
            return {"status": "not_found", "learner_id": learner_id}  # explicit, not an error
        data = dict(row)  # convert to plain dict
        data["preferred_employers"] = [e.strip() for e in data["preferred_employers"].split(",")]  # list of employers
        return data  # success
    except Exception as exc:  # any SQLite failure -> graceful fallback
        return UnableToVerify(tool="sqlite", reason=f"{type(exc).__name__}: {exc}")  # structured failure


def run_select(sql: str, params: tuple = (), db_path: Path = DB_PATH, max_rows: int = 50) -> dict[str, Any] | UnableToVerify:
    """Run a validated, read-only SELECT (used by the ReAct SQL tool).

    Rejects anything that is not a single SELECT statement. Caps rows to keep tokens low.
    """
    try:
        stripped = sql.strip().rstrip(";")  # remove trailing semicolon
        if not stripped.lower().startswith("select") or ";" in stripped or _FORBIDDEN_SQL.search(stripped):  # safety gate
            return UnableToVerify(tool="sqlite", reason="Only single read-only SELECT statements are allowed.")
        conn = _connect_readonly(db_path)  # read-only connection
        try:
            conn.row_factory = sqlite3.Row  # dict-like rows
            rows = [dict(r) for r in conn.execute(stripped, params).fetchmany(max_rows)]  # fetch capped rows
        finally:
            conn.close()  # release
        return {"status": "ok", "row_count": len(rows), "rows": rows}  # success payload
    except Exception as exc:  # syntax errors, missing DB, locked DB...
        return UnableToVerify(tool="sqlite", reason=f"{type(exc).__name__}: {exc}")  # structured failure


@tool
def get_learner_progress(learner_id: str) -> dict:
    """Look up a Sprints learner's progress, readiness status and target salary in EGP.

    Use for questions such as "How many modules has SPR-1001 completed?" or "What salary does SPR-1004 want?".
    Maps to the Sprints learner database (bootcamp tracks, completed modules out of 15, Python assignment
    score from Module 1, readiness_status per the Placement Policy). Returns "Unable to verify" if SQLite fails.

    Args:
        learner_id: Sprints learner id such as "SPR-1001".
    """
    res = fetch_learner(learner_id)  # query the DB
    return res.model_dump() if isinstance(res, UnableToVerify) else res  # tools return plain JSON-able dicts


@tool
def query_learners_sql(sql: str) -> dict:
    """Run a read-only SELECT against the `learners` table (columns: learner_id, name, bootcamp_track,
    completed_modules, python_assignment_score, target_salary_egp, preferred_employers, readiness_status).

    Use for cohort questions such as "average target_salary_egp for the Backend track" (Module 4: SQL tools).
    Only a single SELECT is accepted; other statements return "Unable to verify".

    Args:
        sql: A single SELECT statement.
    """
    res = run_select(sql)  # validated read-only execution
    return res.model_dump() if isinstance(res, UnableToVerify) else res  # JSON-able result


def build_sql_react_agent(llm: Any):
    """Create a simple ReAct agent that owns the two SQL tools (Sprint 1 requirement, Module 4).

    The ReAct loop (think -> call tool -> observe -> answer) is provided by LangGraph's prebuilt agent graph.
    Requires an online Gemini chat model; the orchestrator uses the direct tools in offline mode.
    """
    from langgraph.prebuilt import create_react_agent  # prebuilt ReAct graph

    return create_react_agent(  # returns a compiled LangGraph
        llm,  # Gemini chat model
        tools=[get_learner_progress, query_learners_sql],  # the custom SQL tools
        prompt="You are the Sprints data analyst. Use tools for facts. If a tool says 'Unable to verify', say so.",
    )
