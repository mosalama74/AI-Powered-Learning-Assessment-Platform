"""LLM access layer: Gemini in production, deterministic offline stand-in for tests.

Analogy: this file is the switchboard. Agents ask for "a route", "a judgement", "a refined draft";
the switchboard connects them to Gemini (live) or to a simple rule-based assistant (offline mode), so
the whole graph can be tested without internet or an API key.

Curriculum mapping: Module 2 (prompt templates + Pydantic output parsers), Module 6 (LLM-as-a-judge).
"""
from __future__ import annotations  # forward references

import os  # read environment variables
import re  # simple keyword/regex heuristics for offline mode
from typing import Optional  # optional types

from dotenv import load_dotenv  # load GOOGLE_API_KEY / GEMINI_MODEL from .env
from pydantic import BaseModel  # base class for schema typing

from src.state import Judgement, Reflection, RouteDecision  # structured output schemas

load_dotenv()  # read .env once at import time

LEARNER_ID_RE = re.compile(r"SPR-\d{4}", re.IGNORECASE)  # learner id pattern like SPR-1001


def is_offline() -> bool:
    """Return True when no API key is set or SPRINTS_OFFLINE=1 (Module 4: graceful degradation)."""
    return os.getenv("SPRINTS_OFFLINE") == "1" or not os.getenv("GOOGLE_API_KEY")  # offline if forced or key missing


class LLMClient:
    """One facade for every LLM call the system makes. Each method returns a validated Pydantic object or str."""

    def __init__(self) -> None:
        """Create the Gemini chat model lazily (only if we are online)."""
        self.offline = is_offline()  # remember the mode
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")  # model from .env
        self._chat = None  # chat model handle, created on first use
        if not self.offline:  # only import/create Gemini client when needed
            from langchain_google_genai import ChatGoogleGenerativeAI  # Gemini chat wrapper

            self._chat = ChatGoogleGenerativeAI(  # build the client
                model=self.model_name,  # e.g. gemini-3.5-flash-lite
                temperature=0,  # deterministic: best for routing and grading
                google_api_key=os.getenv("GOOGLE_API_KEY"),  # secret key from environment
                timeout=20,  # seconds; protects the orchestrator from hanging
                max_retries=2,  # retry transient errors
            )

    # ---------- generic helpers ----------
    def _structured(self, schema: type[BaseModel], system: str, user: str) -> BaseModel:
        """Ask Gemini for output that must match a Pydantic schema (strongly typed output parser)."""
        runnable = self._chat.with_structured_output(schema)  # bind schema so output is validated
        return runnable.invoke([("system", system), ("human", user)])  # call the model

    def _text(self, system: str, user: str) -> str:
        """Ask Gemini for plain text."""
        out = self._chat.invoke([("system", system), ("human", user)])  # call the model
        return out.content if isinstance(out.content, str) else str(out.content)  # normalise content to str

    # ---------- orchestrator ----------
    def route(self, user_input: str) -> RouteDecision:
        """Classify a learner request into one of the four intents (orchestrator supervisor step)."""
        if self.offline:  # rule-based stand-in
            text = user_input.lower()  # lower-case for matching
            m = LEARNER_ID_RE.search(user_input)  # find learner id
            lid = m.group(0).upper() if m else None  # normalise id
            if "```" in user_input or "def " in text and "grade" in text:  # code present -> grading
                intent = "grade_submission"
            elif any(k in text for k in ("approve placement", "placement approval", "place ", "placement for", "recommend placement")):
                intent = "placement_approval"
            elif lid or any(k in text for k in ("my progress", "salary", "target", "readiness", "status")):
                intent = "progress_query"
            else:
                intent = "curriculum_question"
            return RouteDecision(intent=intent, learner_id=lid, reasoning="offline keyword router")  # validated result
        system = (  # prompt template with strict instructions
            "You are the Sprints orchestrator. Classify the learner request into exactly one intent: "
            "curriculum_question (asks about course content), progress_query (asks about a learner's progress or salary), "
            "grade_submission (contains Python code to grade), placement_approval (asks to approve/recommend a job placement). "
            "Extract learner_id like SPR-1001 if present. Give a one-sentence reasoning."
        )
        return self._structured(RouteDecision, system, user_input)  # Gemini + Pydantic parser

    # ---------- advisor ----------
    def answer(self, question: str, context: str) -> str:
        """Write a grounded answer using only the retrieved curriculum context."""
        if self.offline:  # extractive stand-in: pick the most relevant sentences
            q_words = set(re.findall(r"[a-z]{4,}", question.lower()))  # significant words in the question
            sentences = re.split(r"(?<=[.!?])\s+|\n+|\s-\s", context)  # split context into sentences/bullets
            scored = sorted(  # rank sentences by word overlap
                (s for s in sentences if len(s.strip()) > 20 and q_words & set(re.findall(r"[a-z]{4,}", s.lower()))),  # only sentences sharing a keyword
                key=lambda s: -(100 * len(q_words & set(re.findall(r"[a-z]{4,}", s.lower()))) - len(s)),  # more overlap first, shorter wins ties
            )
            clean = lambda t: re.sub(r"\[[^\]]*\]|#+", "", t).strip(" -")  # drop "[title]" prefixes and markdown marks
            best = [clean(s) for s in scored[:2]]  # keep the top two
            return " ".join(best) if best else "I could not find this in the curriculum."  # fallback text
        system = (
            "You are the Sprints Advisor. Answer the learner using ONLY the curriculum context. "
            "Be concise (max 5 sentences). If the context is insufficient, say so."
        )
        return self._text(system, f"Question: {question}\n\nContext:\n{context}")  # grounded generation

    def reflect(self, question: str, context: str) -> Reflection:
        """Self-reflection: is the retrieved context enough? If not, propose a better query."""
        if self.offline:  # overlap heuristic
            q_words = set(re.findall(r"[a-z]{4,}", question.lower()))  # question keywords
            c_words = set(re.findall(r"[a-z]{4,}", context.lower()))  # context keywords
            overlap = len(q_words & c_words) / max(1, len(q_words))  # fraction of question words covered
            grounded = overlap >= 0.5  # threshold for "good enough"
            better = " ".join(sorted(q_words))[:120] if not grounded else None  # keyword-only rewrite
            return Reflection(grounded=grounded, critique=f"keyword coverage {overlap:.0%}", better_query=better)
        system = (
            "You are a strict reviewer. Decide if the context fully supports an answer to the question. "
            "If not, write a better search query (keywords) in better_query."
        )
        return self._structured(Reflection, system, f"Question: {question}\n\nContext:\n{context}")  # typed verdict

    # ---------- assessor (evaluator-optimizer) ----------
    def draft_feedback(self, facts: str) -> str:
        """Generator step: first-draft learner feedback from test evidence."""
        if self.offline:  # deliberately brief first draft so the loop has something to improve
            return facts.split("\n")[0]  # only the headline fact
        system = "You are a Sprints Python grader. Write short, kind feedback for a learner from the evidence."
        return self._text(system, facts)  # LLM draft

    def judge_feedback(self, facts: str, draft: str) -> Judgement:
        """Evaluator step (LLM-as-a-judge): score the draft against the Sprints rubric."""
        if self.offline:  # checklist judge: 4 rubric items worth 2.5 points each -> 0..10
            d = draft.lower()  # lower-case draft
            checks = {
                "states the test result": bool(re.search(r"\d+\s*(/|of|out of)\s*\d+", d)),  # e.g. 3/4
                "mentions a specific strength or error": any(w in d for w in ("passed", "failed", "error", "correct")),
                "gives a concrete next step": any(w in d for w in ("next step", "try", "fix", "improve")),
                "links to curriculum": "module" in d,  # references a module
            }
            score = int(round(sum(checks.values()) * 2.5))  # convert to 0..10
            missing = [k for k, ok in checks.items() if not ok]  # what is absent
            return Judgement(score=score, approved=score >= 8, critique="; ".join(missing) or "meets the bar")
        system = (
            "You are a strict LLM judge. Score the feedback 0-10 on: states test results, names specific strengths/errors, "
            "gives a concrete next step, links to a Sprints module. approved=true only if score>=8. critique = what to fix."
        )
        return self._structured(Judgement, system, f"Evidence:\n{facts}\n\nDraft:\n{draft}")  # typed verdict

    def refine_feedback(self, facts: str, draft: str, critique: str) -> str:
        """Optimizer step: rewrite the draft to address the judge's critique."""
        if self.offline:  # append the missing rubric items one by one
            additions = {
                "states the test result": "Tests: " + (m.group(1) if (m := re.search(r"Tests passed: (\d+/\d+)", facts)) else "n/a") + " passed.",
                "mentions a specific strength or error": "Strength/issue: " + (facts.split("\n")[1] if "\n" in facts else "see test output") + ".",
                "gives a concrete next step": "Next step: fix the failing case and re-run the tests.",
                "links to curriculum": "Review Module 1 (Python Foundations) and Module 4 (Tools) for exception handling.",
            }
            for key, text in additions.items():  # add every item the critique mentions
                if key in critique:
                    draft = draft + " " + text  # extend the draft
            return draft.strip()  # improved draft
        system = "Rewrite the grading feedback to fix every point in the critique. Keep it under 120 words."
        return self._text(system, f"Evidence:\n{facts}\n\nDraft:\n{draft}\n\nCritique:\n{critique}")  # LLM rewrite


_client: Optional[LLMClient] = None  # module-level singleton


def get_llm() -> LLMClient:
    """Return a shared LLMClient (so Gemini is configured once per process)."""
    global _client  # we assign the module-level variable
    if _client is None or _client.offline != is_offline():  # rebuild if the mode changed (tests toggle it)
        _client = LLMClient()  # create client
    return _client  # shared instance
