"""Build docs/technical_report.pdf and docs/project_charter.pdf with ReportLab."""
from reportlab.lib import colors  # colours
from reportlab.lib.enums import TA_LEFT  # alignment
from reportlab.lib.pagesizes import A4  # page size
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # styles
from reportlab.lib.units import cm  # units
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # flowables

NAVY, TEAL, LIGHT, GREY = colors.HexColor("#0B2545"), colors.HexColor("#13A89E"), colors.HexColor("#EAF2F8"), colors.HexColor("#5C6B7A")
ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=16, textColor=NAVY, spaceBefore=14, spaceAfter=6)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=12, textColor=TEAL, spaceBefore=8, spaceAfter=3)
B = ParagraphStyle("B", parent=ss["BodyText"], fontName="Helvetica", fontSize=9.6, leading=13.4, textColor=colors.HexColor("#1D2733"), alignment=TA_LEFT, spaceAfter=5)
BUL = ParagraphStyle("BUL", parent=B, leftIndent=14, bulletIndent=3, spaceAfter=2)
SM = ParagraphStyle("SM", parent=B, fontSize=8.4, leading=11, spaceAfter=0)
SMB = ParagraphStyle("SMB", parent=SM, fontName="Helvetica-Bold", textColor=colors.white)
CODE = ParagraphStyle("CODE", parent=B, fontName="Courier", fontSize=8.2, leading=10.5, backColor=LIGHT, borderPadding=5, spaceAfter=8)


def P(t, s=B): return Paragraph(t, s)
def bullets(items): return [Paragraph(i, BUL, bulletText="\u2022") for i in items]


def table(rows, widths, header=True):
    """Build a styled table; cells are wrapped Paragraphs."""
    data = [[Paragraph(str(c), SMB if (header and r == 0) else SM) for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=[w * cm for w in widths], repeatRows=1 if header else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9D3DC")),
          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), NAVY)] + [("BACKGROUND", (0, i), (-1, i), LIGHT) for i in range(2, len(rows), 2)]
    t.setStyle(TableStyle(st)); return t


def footer(canvas, doc):
    """Page footer with number."""
    canvas.saveState(); canvas.setFont("Helvetica", 8); canvas.setFillColor(GREY)
    canvas.drawString(2 * cm, 1.1 * cm, "Sprints Multi-Agent AI Career & Assessment Orchestrator | Technical Report")
    canvas.drawRightString(A4[0] - 2 * cm, 1.1 * cm, f"Page {doc.page}"); canvas.restoreState()


def build_report(path="docs/technical_report.pdf"):
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            title="Sprints Orchestrator Technical Report", author="Lead AI Systems Architect")
    s = []
    s += [Spacer(1, 3 * cm), P("Technical Report", ParagraphStyle("T", parent=H1, fontSize=30, textColor=NAVY)),
          P("Sprints Multi-Agent AI Career &amp; Assessment Orchestrator", ParagraphStyle("T2", parent=H1, fontSize=17, textColor=TEAL)),
          Spacer(1, 0.4 * cm), P("Agentic architecture, memory strategy and RAG configuration", ParagraphStyle("T3", parent=B, fontSize=12)),
          Spacer(1, 1 * cm), P("Prepared for: Youssef El-Sherif, VP Engineering, Sprints<br/>Prepared by: Lead AI Systems Architect, Core Platforms team<br/>Stack: LangGraph, ChromaDB, SQLite, Pydantic, Gemini (gemini-3.5-flash-lite)", B),
          Spacer(1, 1.2 * cm), Image("docs/assets/architecture.png", width=17 * cm, height=17 * cm * 0.5), PageBreak()]

    s += [P("1. Executive summary", H1),
          P("Sprints human advisors and graders are the bottleneck of its employer-connected bootcamps. We built a stateful multi-agent system that takes over the three repetitive jobs (curriculum Q&amp;A, Python grading, placement preparation) while keeping humans in charge of the one high-stakes decision: placement approval."),
          P("A LangGraph <b>orchestrator</b> classifies each request and routes it to an <b>Advisor</b> (agentic RAG over ChromaDB, read-only SQLite for progress and target salary in EGP) or an <b>Assessor</b> (sandboxed code execution plus an evaluator-optimizer loop capped at three refinements). Placement requests pause the graph with LangGraph <font name='Courier'>interrupt</font> until a human advisor approves, rejects, or asks for more information."),
          P("<b>Result:</b> every acceptance criterion has an automated test (44 tests pass) and the end-to-end demo exercises query, grading and HITL escalation. Evidence in this report comes from offline mode (deterministic LLM and embedder stand-ins), because Gemini could not be called from the build environment; section 11 explains what must be re-measured live.")]

    s += [P("2. Requirements traceability", H1),
          table([["Requirement", "Implementation", "Evidence"],
                 ["LangGraph for all orchestration", "Orchestrator StateGraph with conditional edges; Advisor and Assessor are sub-graphs", "<font name='Courier'>orchestrator.py</font>, routing tests"],
                 ["Docstrings mapped to curriculum", "Every module/class/function/tool names its Sprints module", "Code review; tool docstrings are the LLM-facing descriptions"],
                 ["ChromaDB under 1000 ms", "Persistent index, query cache, 600 ms embedding timeout, local keyword fallback", "p95 and max latency tests; slow-embedder fallback test"],
                 ["Graceful 'Unable to verify'", "SQLite, REPL, ChromaDB and LLM failures become a structured <font name='Courier'>UnableToVerify</font> object", "5 failure-injection tests"],
                 ["Max 3 refinement iterations", "Cap enforced in the conditional edge (graph level, not prompt level)", "Stub judge never approves: exactly 3 refinements, 4 judgements"],
                 ["HITL for placements", "<font name='Courier'>interrupt()</font> + <font name='Courier'>Command(resume=...)</font>; AI only recommends", "Approve, reject, unknown-learner tests"],
                 ["Structured agent messages", "<font name='Courier'>AgentMessage</font> envelope: trace_id, sender, recipient, intent, status, payload", "Pydantic validation on every hop"],
                 ["Session memory isolation", "<font name='Courier'>MemorySaver</font> keyed by thread_id", "Thread isolation and accumulation tests"]],
                [4.2, 7.3, 5.5])]

    s += [P("3. Agentic architecture", H1),
          P("The design is an <b>orchestrator-worker</b> pattern. Think of a hospital front desk: the coordinator listens, sends the person to the right specialist, and calls a senior doctor for serious decisions. The coordinator never does the specialist work itself."),
          Image("docs/assets/architecture.png", width=16.5 * cm, height=16.5 * cm * 0.5), Spacer(1, 4),
          table([["Node", "Role", "Notes"],
                 ["supervisor", "Classifies intent (curriculum, progress, grading, placement) and extracts the learner id", "Gemini structured output (Pydantic <font name='Courier'>RouteDecision</font>); attached code forces the grading route; LLM outage degrades to 'unknown' instead of crashing"],
                 ["advisor", "Curriculum answers (RAG) and learner progress (SQLite)", "Sub-graph with self-reflection loop"],
                 ["assessor", "Runs code in sandbox, drafts and refines feedback, computes rubric score", "Sub-graph with evaluator-optimizer loop"],
                 ["placement_prep", "Builds a recommendation package from the DB and policy thresholds", "Always escalates when a package exists"],
                 ["human_review", "Pauses for a human decision", "interrupt() / resume"],
                 ["finalize", "Writes the learner-facing answer and audit log", "Single exit point"]], [3, 6, 8]),
          P("<b>Why LangGraph and not chains?</b> A chain is a fixed conveyor belt. Our workflow needs branches (which worker?), loops (reflect, refine) and a pause (human). Conditional edges, cycles and checkpointing are native in LangGraph, so none of the routing is hard-coded in prompts.", B)]

    s += [P("4. State and structured communication", H1),
          P("The global state is a <font name='Courier'>TypedDict</font> (<font name='Courier'>OrchestratorState</font>): conversation messages (append-only reducer), user input, learner id, route, last worker message, recommendation, human decision, final response and an audit log. It works like a shared notebook that every node can read and write."),
          P("Workers never return free text to the orchestrator. They return an <font name='Courier'>AgentMessage</font> whose payload is a validated Pydantic model (<font name='Courier'>AdvisorResult</font>, <font name='Courier'>GradeReport</font>, <font name='Courier'>PlacementRecommendation</font>, <font name='Courier'>HumanDecision</font>). Benefits: contracts are explicit, invalid output fails fast, and every hop is auditable via trace_id and timestamps.")]

    s += [P("5. Memory strategy", H1),
          table([["Layer", "Mechanism", "Why this choice"],
                 ["Short-term (session)", "LangGraph <font name='Courier'>MemorySaver</font> checkpointer; one thread_id per learner session; snapshot after every node", "Required for HITL (the graph must survive a pause) and gives isolation between learners for free"],
                 ["Context-window control", "Router sees only the last 6 messages (<font name='Courier'>MAX_HISTORY</font>)", "Prevents token growth over long sessions; routing needs recent context only"],
                 ["Long-term structured facts", "SQLite learner table queried on demand through read-only tools", "Facts such as salary and scores must be exact; never copied into prompts where they could go stale"],
                 ["Long-term knowledge", "ChromaDB curriculum index retrieved on demand", "Curriculum is large and changes; retrieval keeps prompts small and answers citable"],
                 ["Audit memory", "<font name='Courier'>audit_log</font> and AgentMessage trace_ids stored in state", "Stakeholders can see why a decision was routed and who approved it"]],
                [3.4, 6.4, 7.2]),
          P("<b>Trade-off:</b> MemorySaver keeps checkpoints in process memory, so a server restart loses paused approvals. Production should swap in a persistent checkpointer (for example the SQLite or Postgres savers); the graph code does not change.")]

    s += [P("6. RAG configuration", H1),
          table([["Parameter", "Value", "Reason"],
                 ["Source", "7 curriculum Markdown files (Modules 1-6, placement and grading policy)", "Authored stand-in for the real curriculum"],
                 ["Chunking", "RecursiveCharacterTextSplitter, 600 chars, 80 overlap (~13%), splits on headings first", "Module 3 guidance: 500-800 chars, 10-15% overlap; headings keep ideas intact"],
                 ["Chunk text", "Prefixed with the document title", "Each chunk knows its origin; improves retrieval and citations"],
                 ["Index", "ChromaDB PersistentClient, cosine space (HNSW), one collection per embedder", "Avoids mixing vector spaces; survives restarts"],
                 ["Embeddings", "Live: Gemini embedding model (gemini-embedding-001). Offline: 1024-dim hashing embedder with light stemming", "Offline mode keeps tests deterministic and network-free"],
                 ["Top-k", "4", "Module 3 guidance (3-5)"],
                 ["Latency guard", "Embedding runs in a worker thread with a 600 ms timeout; on timeout a local keyword search answers; repeated queries use a cache; result records <font name='Courier'>latency_ms</font>, <font name='Courier'>within_budget</font>, <font name='Courier'>mode</font>", "Guarantees the orchestrator never waits more than the 1000 ms budget for retrieval"],
                 ["Agentic RAG", "Retrieve, generate, reflect (is the context enough?), rewrite query, retry; max 2 rewrites", "Bounded self-correction; honest 'could not fully confirm' note if still ungrounded"]],
                [3.1, 7.2, 6.7]),
          P("Retrieval relevance on 7 test questions: top-2 hit rate rose from 3/7 to 7/7 after adding stemming, larger dimension and unsigned buckets to the offline embedder (see changelog). Live Gemini embeddings should be benchmarked with the notebook (section 5).")]

    s += [P("7. Assessor: sandbox and evaluator-optimizer loop", H1),
          P("<b>Sandbox.</b> Learner code is untrusted. It runs in a separate Python process in isolated mode with: an AST check (import <b>allow-list</b>, no eval/exec/open, no dunder attribute access), a 5 s wall-clock timeout, CPU (3 s), memory (512 MB) and file-size limits, a private temp directory, and an environment stripped of secrets such as the API key. We deliberately did not use LangChain's in-process PythonREPL utility because it has full access to the host."),
          Image("docs/assets/eval_loop.png", width=15.5 * cm, height=15.5 * cm * 0.33),
          P("<b>Loop.</b> Draft feedback, then an LLM judge scores it 0-10 against a checklist (states test result, names a specific strength or error, gives a next step, links to a curriculum module). If not approved and fewer than 3 refinements have run, the optimizer rewrites the draft using the critique. The cap is enforced in the graph's conditional edge, so a prompt cannot override it. Worst case is 3 refinements and 4 judge calls."),
          P("<b>Score.</b> Mirrors the grading policy: 50 correctness (share of assert tests passed) + 20 docstring coverage + 20 error handling (try/except or raise) + 10 feedback clarity (judge score). Pass mark 70.")]

    s += [P("8. Human-in-the-loop placement approval", H1),
          P("Placement is high-stakes, so the AI never decides. The recommendation package (readiness status, modules, Python score, target salary in EGP, preferred employers, rationale, AI suggestion) is sent through <font name='Courier'>interrupt()</font>. The graph state is checkpointed and control returns to the caller. A human replies with approve, reject, or needs_more_info plus notes, and the graph resumes with <font name='Courier'>Command(resume=...)</font>. Rules: placement requests always pause when a package exists; a human may reject even when the AI recommends approval; an unknown learner never reaches a human because there is nothing verifiable to review.")]

    s += [P("9. Safety and failure handling", H1),
          table([["Failure", "Behaviour"],
                 ["SQLite missing, locked or invalid query", "<font name='Courier'>{status: unable_to_verify, message: 'Unable to verify', tool: sqlite, reason}</font>; connections are read-only; only single SELECT statements are accepted"],
                 ["Sandbox cannot start or crashes", "<font name='Courier'>Unable to verify</font> with tool=python_repl; learner-caused failures (bug, timeout, blocked import) are normal grading results"],
                 ["ChromaDB error", "<font name='Courier'>Unable to verify</font> with tool=chromadb"],
                 ["LLM outage", "Router degrades to 'unknown'; grader falls back to raw test evidence; advisor reports Unable to verify"],
                 ["Prompt-injected SQL", "Rejected by validator; parameterised queries elsewhere"]], [5, 12])]

    s += [P("10. Testing and results", H1),
          P("44 automated tests (pytest, offline, about 4 s): 24 tool tests and 20 agent/orchestrator tests. Highlights:"),
          *bullets(["Retrieval: p95 and max latency far below 1000 ms across 30 queries (offline embedder, about 1-3 ms); a deliberately slow embedder triggers the keyword fallback and still meets the budget.",
                    "Loop: a judge that never approves is stopped after exactly 3 refinements (judge called 4 times); an approving judge ends with 0 refinements.",
                    "HITL: placement pauses; approve and reject both resume correctly; not-ready learner gets a negative AI recommendation; unknown learner returns Unable to verify.",
                    "Memory: two thread_ids never share state; messages accumulate within one thread.",
                    "Security: dangerous imports, dunder escapes and infinite loops are blocked; the API key is not visible inside the sandbox."]),
          table([["Learner submission (demo)", "Tests", "Score"], ["Buggy <font name='Courier'>average()</font> (divides by n+1)", "0/3", "10/100"], ["Correct, documented, validates input", "3/3", "100/100"]], [9, 3, 3]),
          Spacer(1, 4)]

    s += [P("11. Limitations, assumptions and what to verify live", H1),
          *bullets(["<b>Discovery call not reviewed.</b> The MP3 could not be transcribed in the build environment. Any expectations only stated in the call are not reflected; review and add them.",
                    "<b>Live Gemini not exercised.</b> The code targets the configured model through langchain-google-genai, but all measured results here use the offline stand-ins. Run the demo, tests and notebook with a real key to record live latency, answer quality and judge behaviour; real embedding latency is network dependent (hence the timeout and fallback).",
                    "<b>Data differences.</b> The CSV has 25 rows (the deck says 500) and the starter repository link was not provided. Curriculum documents are authored stand-ins.",
                    "<b>Offline judge and answers are rule-based</b> and much weaker than Gemini; they exist for deterministic testing, not for production quality.",
                    "MemorySaver is not persistent; the HITL queue needs a persistent checkpointer and a reviewer UI in production.",
                    "Business impact figures in the deck are design targets to measure in a pilot, not measured results."])]

    s += [P("12. Next steps", H1),
          *bullets(["Pilot with one cohort and measure advisor hours saved, grading turnaround and judge-vs-human agreement.",
                    "Replace MemorySaver with a persistent checkpointer; add a reviewer inbox for pending approvals.",
                    "Expand curriculum ingestion to the real documents; add reranking and a retrieval-quality benchmark set.",
                    "Add authentication, per-learner access control and structured logging/tracing (for example LangSmith).",
                    "Calibrate the LLM judge against human graders on 50 submissions before trusting automated feedback."]),
          P("<b>How to run:</b>", B), P("pip install -r requirements.txt<br/>cp .env.example .env  (set GOOGLE_API_KEY)<br/>python -m src.main demo<br/>python -m pytest tests -q", CODE)]
    doc.build(s, onFirstPage=lambda c, d: None, onLaterPages=footer)


def build_charter(path="docs/project_charter.pdf"):
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.3 * cm, bottomMargin=1.2 * cm, title="Project Charter")
    c9 = ParagraphStyle("c9", parent=B, fontSize=8.5, leading=11, spaceAfter=3)
    cb = ParagraphStyle("cb", parent=c9, leftIndent=10, bulletIndent=2, spaceAfter=1)
    cH = ParagraphStyle("cH", parent=H2, fontSize=10.5, spaceBefore=5, spaceAfter=2)
    bl = lambda items: [Paragraph(i, cb, bulletText="\u2022") for i in items]
    s = [P("Project Charter: Sprints Multi-Agent AI Career &amp; Assessment Orchestrator", ParagraphStyle("ct", parent=H1, fontSize=14, spaceBefore=0)),
         P("Sponsor: Youssef El-Sherif, VP Engineering, Sprints | Role: Lead AI Systems Architect | Duration: 14 days", c9),
         P("Problem", cH), P("Human advisors and graders are the bottleneck as employer-connected bootcamps scale. Curriculum questions, Python grading and placement preparation are repetitive, but placement is high-stakes and must keep human oversight.", c9),
         P("Scope", cH), *bl(["<b>In:</b> LangGraph orchestrator + Advisor + Assessor; ChromaDB RAG; read-only SQLite tools (progress, target salary in EGP); sandboxed Python grading; evaluator-optimizer (max 3); HITL placement approval; structured agent messages; report, deck, notebook, demo.",
                              "<b>Out:</b> web UI, authentication, real employer integrations, writing to learner data, production deployment."]),
         P("Success criteria", cH), *bl(["LangGraph for all orchestration and dynamic routing", "Docstrings mapped to curriculum on all code and tools", "ChromaDB retrieval under 1000 ms", "Structured 'Unable to verify' on SQLite or REPL exceptions",
                                         "Evaluator-optimizer halts after at most 3 refinements", "No placement approved without a human decision", "All deliverables in the expected submission tree"]),
         P("Risks and mitigations", cH),
         table([["Risk", "Mitigation"], ["Untrusted learner code", "Separate process, import allow-list, timeout, CPU/memory limits, secrets stripped"], ["LLM latency or outage", "Timeouts, retries, deterministic fallbacks, Unable to verify"],
                ["Embedding slower than 1000 ms", "600 ms embedding timeout then local keyword fallback, query cache"], ["Judge never approves", "Hard cap of 3 refinements in the graph edge"],
                ["Wrong placement decision", "Mandatory human approval; AI only recommends"], ["Small sample data (25 rows)", "Code and tests independent of data size"]], [5.5, 12.3]),
         P("Assumptions", cH),
         *bl(["<b>The discovery call MP3 could not be transcribed in the build environment and is not reflected here.</b> Requirements come from the written brief and kickoff deck; review the call and add anything missing.",
              "The CSV has 25 rows (deck says 500); the starter repo link was not provided.", "Curriculum documents are authored stand-ins for the real Sprints curriculum.",
              "Gemini model is set by <font name='Courier'>GEMINI_MODEL=gemini-3.5-flash-lite</font> in .env; an offline stand-in is used for tests and demos."]),
         P("Milestones", cH), P("Days 1-2 discovery and charter | 3-5 foundation and thin slice | 6-9 build | 10-11 quality | 12-13 report and deck | 14 demo and submission.", c9)]
    doc.build(s)


if __name__ == "__main__":
    build_report(); build_charter(); print("PDFs built")
