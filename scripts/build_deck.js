// Builds docs/final_presentation.pptx (10 slides) with pptxgenjs, themed + layouts per the pptx skill.
const pptxgen = require("pptxgenjs");
const { applyTheme } = require("/mnt/skills/public/pptx/scripts/apply_theme.js");

const THEME = {
  name: "Sprints Orchestrator", headFontFace: "Georgia", bodyFontFace: "Calibri",
  colors: { dk1: "1D2733", lt1: "FFFFFF", dk2: "0B2545", lt2: "EAF2F8", accent1: "13A89E", accent2: "F2A541", accent3: "0B2545",
            accent4: "C8553D", accent5: "5C6B7A", accent6: "8FD3CC", hlink: "13A89E", folHlink: "5C6B7A" },
};
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "Sprints Multi-Agent AI Career & Assessment Orchestrator";
pres.author = "Lead AI Systems Architect";
const C = pres.SchemeColor;

// ---- layouts (frames): dark title/closing, light content with title placeholder ----
pres.defineSlideMaster({ title: "TITLE_DARK", background: { color: "0B2545" },
  objects: [{ placeholder: { options: { name: "title", type: "title", x: 0.7, y: 1.5, w: 8.6, h: 1.4, fontFace: "Georgia", fontSize: 34, bold: true, color: "FFFFFF", valign: "top", align: "left", margin: 0 }, text: "" } }] });
pres.defineSlideMaster({ title: "CONTENT", background: { color: "FFFFFF" }, margin: [0.4, 0.5, 0.5, 0.5],
  objects: [{ placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.3, w: 9, h: 0.8, fontFace: "Georgia", fontSize: 21, bold: true, color: "0B2545", valign: "middle", align: "left", margin: 0 }, text: "" } },
            { text: { text: "Sprints | Multi-Agent Career & Assessment Orchestrator", options: { x: 0.5, y: 5.28, w: 7, h: 0.25, fontSize: 9, color: "5C6B7A", margin: 0 } } }],
  slideNumber: { x: 9.1, y: 5.28, w: 0.5, h: 0.25, fontSize: 9, color: "5C6B7A" } });

const card = (s, x, y, w, h, fill, name) => s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fill }, line: { color: fill }, rectRadius: 0.08, objectName: name });
const txt = (s, t, o) => s.addText(t, Object.assign({ isTextBox: true, margin: 0, fontFace: "Calibri", color: "1D2733" }, o));
const sec = (t) => pres.addSection({ title: t });

// 1. Title -----------------------------------------------------------
sec("Opening");
let s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Opening" });
s.addText("Sprints Multi-Agent AI Career & Assessment Orchestrator", { placeholder: "title" });
txt(s, "Faster answers and grading for learners, with humans in charge of every placement", { x: 0.7, y: 3.1, w: 8, h: 0.6, fontSize: 18, color: "8FD3CC", objectName: "subtitle" });
txt(s, "Final presentation for Sprints stakeholders | Advanced Agentic AI | Lead AI Systems Architect", { x: 0.7, y: 4.7, w: 8.6, h: 0.3, fontSize: 11, color: "CADCFC", objectName: "byline" });
s.addNotes("Open with the one-line promise: automate the repetitive work, keep humans on the high-stakes decision.");

// 2. Problem ----------------------------------------------------------
sec("Problem");
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Problem" });
s.addText("Advisors and graders are the bottleneck as cohorts grow", { placeholder: "title" });
const stats = [["3", "repetitive jobs eat expert time: curriculum questions, Python grading, placement prep"], ["25", "sample learners in the starter data; every row needs a status, a grade or a decision"], ["0", "placements may be decided without a human: the risk that rules out simple chatbots"]];
stats.forEach((st, i) => { const x = 0.5 + i * 3.05; card(s, x, 1.3, 2.85, 1.5, "EAF2F8", "stat" + i);
  txt(s, st[0], { x: x + 0.2, y: 1.38, w: 2.4, h: 0.7, fontSize: 40, bold: true, color: "13A89E", fontFace: "Georgia", objectName: "statnum" + i });
  txt(s, st[1], { x: x + 0.2, y: 2.05, w: 2.5, h: 0.7, fontSize: 11.5, objectName: "statlbl" + i }); });
s.addChart(pres.charts.BAR, [{ name: "Learners", labels: ["Ready for Placement", "In Progress", "Needs Review", "Dropped"], values: [11, 9, 4, 1] }], {
  x: 0.5, y: 2.95, w: 5.6, h: 2.25, barDir: "bar", chartColors: ["13A89E"], showTitle: true, title: "Starter data: learners by readiness status", titleFontSize: 11, titleColor: "0B2545",
  showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 10, catAxisLabelFontSize: 10, catAxisLabelColor: "1D2733", valAxisHidden: true, valGridLine: { style: "none" }, showLegend: false, catAxisLabelFontFace: "+mn-lt" });
txt(s, [{ text: "Every status needs a different action", options: { bold: true, breakLine: true, color: "0B2545" } },
        { text: "11 ready learners need placement approval, 4 need a human review, 9 need progress answers and grading. At thousands of learners this does not scale by hiring alone.", options: {} }],
    { x: 6.4, y: 3.1, w: 3.1, h: 2.0, fontSize: 12, objectName: "problem-text", valign: "top" });
s.addNotes("Data note: the supplied CSV has 25 rows; the kickoff deck mentions 500. The point stands at any size.");

// 3. Solution picture -------------------------------------------------
sec("Solution");
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Solution" });
s.addText("One orchestrator, two specialist agents, one human gate", { placeholder: "title" });
s.addImage({ path: "docs/assets/architecture.png", x: 0.5, y: 1.15, w: 6.6, h: 6.6 * 0.5, altText: "System architecture diagram" });
txt(s, [{ text: "Orchestrator ", options: { bold: true, color: "0B2545" } }, { text: "routes each request by intent", options: { breakLine: true } },
        { text: "Advisor ", options: { bold: true, color: "0B2545" } }, { text: "answers from the curriculum and the learner database", options: { breakLine: true } },
        { text: "Assessor ", options: { bold: true, color: "0B2545" } }, { text: "grades code safely and improves feedback", options: { breakLine: true } },
        { text: "Human advisor ", options: { bold: true, color: "C8553D" } }, { text: "approves or rejects every placement" }],
    { x: 7.3, y: 1.3, w: 2.3, h: 3.2, fontSize: 12, paraSpaceAfter: 8, valign: "top", objectName: "solution-legend" });
txt(s, "Built on LangGraph: branches, loops and pauses are part of the graph, not hidden in prompts.", { x: 0.5, y: 4.5, w: 6.6, h: 0.5, fontSize: 12, italic: true, color: "5C6B7A", objectName: "solution-note" });

// 4. Request flow -----------------------------------------------------
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Solution" });
s.addText("Every request takes the route that fits it", { placeholder: "title" });
const flows = [["Curriculum question", "Advisor: search ChromaDB, answer, self-check, retry up to 2 times", "13A89E"], ["Progress or salary (EGP)", "Advisor: read-only SQLite lookup, exact facts", "13A89E"],
               ["Python submission", "Assessor: sandbox run, draft, judge, refine up to 3 times", "0B2545"], ["Placement approval", "Prepare package, pause, human decides", "F2A541"]];
flows.forEach((f, i) => { const y = 1.3 + i * 0.95; card(s, 0.5, y, 2.7, 0.75, f[2], "route" + i);
  txt(s, f[0], { x: 0.65, y, w: 2.45, h: 0.75, fontSize: 13, bold: true, color: i === 3 ? "0B2545" : "FFFFFF", valign: "middle", objectName: "routeName" + i });
  s.addShape(pres.shapes.LINE, { x: 3.3, y: y + 0.375, w: 0.5, h: 0, line: { color: "5C6B7A", width: 1.5, endArrowType: "triangle" } });
  txt(s, f[1], { x: 3.95, y, w: 5.5, h: 0.75, fontSize: 13, valign: "middle", objectName: "routeDesc" + i }); });
txt(s, "All results come back to the orchestrator as validated JSON messages (sender, recipient, intent, status, payload).", { x: 0.5, y: 5.0, w: 9, h: 0.25, fontSize: 10.5, color: "5C6B7A", italic: true, objectName: "flow-note" });
s.addNotes("Router is Gemini structured output; code attached to a request always forces the grading route.");

// 5. Assessor ---------------------------------------------------------
sec("Capabilities");
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Capabilities" });
s.addText("Grading is safe, rubric-based and capped at 3 refinements", { placeholder: "title" });
s.addImage({ path: "docs/assets/eval_loop.png", x: 0.5, y: 1.2, w: 5.4, h: 5.4 * 0.33 * 1.0, altText: "Evaluator-optimizer loop" });
txt(s, [{ text: "Safe execution: ", options: { bold: true, color: "0B2545" } }, { text: "separate process, import allow-list, 5 s timeout, memory limits, no secrets", options: { breakLine: true } },
        { text: "Same rubric as Sprints: ", options: { bold: true, color: "0B2545" } }, { text: "50 correctness, 20 docstrings, 20 error handling, 10 feedback clarity", options: { breakLine: true } },
        { text: "Cost control: ", options: { bold: true, color: "0B2545" } }, { text: "the graph itself stops the loop after 3 refinements (4 judge calls at most)" }],
    { x: 0.5, y: 3.15, w: 5.4, h: 1.9, fontSize: 12, paraSpaceAfter: 7, valign: "top", objectName: "assessor-bullets" });
card(s, 6.3, 1.3, 3.2, 3.5, "EAF2F8", "demo-card");
txt(s, "Demo submission", { x: 6.5, y: 1.4, w: 2.8, h: 0.3, fontSize: 12, bold: true, color: "0B2545", objectName: "demo-title" });
txt(s, [{ text: "Buggy average()", options: { breakLine: true } }, { text: "0/3 tests, score 10/100", options: { bold: true, color: "C8553D", breakLine: true } }, { text: " ", options: { breakLine: true } },
        { text: "Correct, documented, validates input", options: { breakLine: true } }, { text: "3/3 tests, score 100/100", options: { bold: true, color: "13A89E" } }],
    { x: 6.5, y: 1.8, w: 2.8, h: 1.6, fontSize: 12, valign: "top", objectName: "demo-text" });
txt(s, "Stub judge that never approves: loop stops at exactly 3 refinements (tested).", { x: 6.5, y: 3.6, w: 2.8, h: 1.0, fontSize: 11, italic: true, color: "5C6B7A", valign: "top", objectName: "demo-cap" });

// 6. Advisor ----------------------------------------------------------
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Capabilities" });
s.addText("Advisor answers from your curriculum and your data, within 1 second", { placeholder: "title" });
const kp = [["600 / 80", "characters per chunk / overlap"], ["k = 4", "chunks retrieved per question"], ["< 1000 ms", "retrieval budget, with fallback"], ["max 2", "self-reflection query rewrites"]];
kp.forEach((k, i) => { const x = 0.5 + i * 2.3; card(s, x, 1.3, 2.15, 1.3, "0B2545", "kpi" + i);
  txt(s, k[0], { x: x + 0.1, y: 1.4, w: 1.95, h: 0.6, fontSize: 22, bold: true, color: "FFFFFF", fontFace: "Georgia", align: "center", objectName: "kpiNum" + i });
  txt(s, k[1], { x: x + 0.1, y: 2.0, w: 1.95, h: 0.5, fontSize: 10.5, color: "8FD3CC", align: "center", objectName: "kpiLbl" + i }); });
txt(s, [{ text: "How it stays fast: ", options: { bold: true, color: "0B2545" } }, { text: "query embedding gets 600 ms; if slower, a local keyword search answers instead, so the orchestrator never times out.", options: { breakLine: true } },
        { text: "How it stays honest: ", options: { bold: true, color: "0B2545" } }, { text: "the Advisor checks whether the retrieved text really answers the question, rewrites the search if not, and says so when it still cannot confirm.", options: { breakLine: true } },
        { text: "How it stays exact: ", options: { bold: true, color: "0B2545" } }, { text: "salary in EGP, scores and status come straight from a read-only SQLite connection, never from model memory." }],
    { x: 0.5, y: 2.95, w: 9, h: 2.2, fontSize: 13, paraSpaceAfter: 9, valign: "top", objectName: "advisor-bullets" });

// 7. HITL -------------------------------------------------------------
sec("Trust");
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Trust" });
s.addText("The AI recommends; a human advisor decides every placement", { placeholder: "title" });
const steps = [["1  Request", "\"Approve placement for SPR-1001\"", "EAF2F8", "0B2545"], ["2  AI package", "Ready for Placement, 12/15 modules, score 95, 30,000 EGP, Fawry or Swvl; AI suggests approve", "13A89E", "FFFFFF"],
               ["3  Graph pauses", "State saved; nothing is approved yet", "F2A541", "0B2545"], ["4  Human decides", "Approve, reject or ask for more info, with notes", "0B2545", "FFFFFF"]];
steps.forEach((st, i) => { const x = 0.5 + i * 2.3; card(s, x, 1.35, 2.15, 2.2, st[2], "hstep" + i);
  txt(s, st[0], { x: x + 0.12, y: 1.45, w: 1.9, h: 0.4, fontSize: 13, bold: true, color: st[3], objectName: "hsName" + i });
  txt(s, st[1], { x: x + 0.12, y: 1.9, w: 1.9, h: 1.55, fontSize: 11, color: st[3], valign: "top", objectName: "hsDesc" + i }); });
txt(s, [{ text: "A human can reject even when the AI recommends approval. ", options: { bold: true, color: "C8553D" } }, { text: "Unknown or unverifiable learners never reach the approval step. Every decision is logged with reviewer and notes.", options: {} }],
    { x: 0.5, y: 3.9, w: 9, h: 1.0, fontSize: 13, valign: "top", objectName: "hitl-note" });
s.addNotes("Implemented with LangGraph interrupt and Command(resume=...). Tested: approve, reject, not-ready learner, unknown learner.");

// 8. Evidence ---------------------------------------------------------
sec("Evidence");
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Evidence" });
s.addText("Every quality bar has an automated test (44 passing)", { placeholder: "title" });
const hdr = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: "0B2545" }, fontSize: 11 } });
const row = (a, b, c) => [{ text: a, options: { fontSize: 10.5 } }, { text: b, options: { fontSize: 10.5 } }, { text: c, options: { fontSize: 10.5, bold: true, color: "13A89E" } }];
s.addTable([[hdr("Quality bar"), hdr("How it is proven"), hdr("Result")],
  row("LangGraph orchestration", "Conditional routing tests across 4 intents", "Pass"),
  row("Retrieval under 1000 ms", "30 queries; slow-embedder fallback test", "Pass (offline: ~1-3 ms)"),
  row("'Unable to verify' on failure", "SQLite, REPL and ChromaDB failures injected", "Pass"),
  row("Max 3 refinements", "Judge that never approves", "Stops at 3"),
  row("Human approves placements", "Pause, approve, reject paths", "Pass"),
  row("Session isolation", "Two thread ids, no shared state", "Pass")],
  { x: 0.5, y: 1.3, w: 9, colW: [3, 4, 2], border: { type: "solid", pt: 0.5, color: "C9D3DC" }, fill: { color: "FFFFFF" }, margin: [0.05, 0.1, 0.05, 0.1], rowH: 0.42, objectName: "evidence-table" });
txt(s, "Evidence was produced in offline mode (deterministic LLM and embedder). Live Gemini latency and answer quality are re-measured with the included notebook.", { x: 0.5, y: 4.5, w: 9, h: 0.6, fontSize: 11.5, italic: true, color: "5C6B7A", objectName: "evidence-note" });

// 9. Business impact --------------------------------------------------
sec("Impact");
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Impact" });
s.addText("Business impact: pilot targets to measure, guarantees by design", { placeholder: "title" });
card(s, 0.5, 1.3, 4.4, 3.0, "EAF2F8", "guarantee-card"); card(s, 5.1, 1.3, 4.4, 3.0, "EAF2F8", "target-card");
txt(s, "Guaranteed by design (tested)", { x: 0.7, y: 1.4, w: 4.0, h: 0.4, fontSize: 14, bold: true, color: "13A89E", fontFace: "Georgia", objectName: "g-title" });
txt(s, [{ text: "100% of placements get a human decision", options: { bullet: true, breakLine: true } }, { text: "Learner code never runs in the main process", options: { bullet: true, breakLine: true } },
        { text: "No tool failure is hidden: structured Unable to verify", options: { bullet: true, breakLine: true } }, { text: "Grading cost is bounded: max 3 refinements", options: { bullet: true } }],
    { x: 0.7, y: 1.9, w: 4.0, h: 2.7, fontSize: 12.5, paraSpaceAfter: 8, valign: "top", objectName: "g-bullets" });
txt(s, "Targets to validate in a pilot", { x: 5.3, y: 1.4, w: 4.0, h: 0.4, fontSize: 14, bold: true, color: "F2A541", fontFace: "Georgia", objectName: "t-title" });
txt(s, [{ text: "Advisor hours saved on routine Q&A and progress checks", options: { bullet: true, breakLine: true } }, { text: "Grading turnaround from days to minutes", options: { bullet: true, breakLine: true } },
        { text: "Agreement between AI feedback and human graders", options: { bullet: true, breakLine: true } }, { text: "Share of placements ready for review on first pass", options: { bullet: true } }],
    { x: 5.3, y: 1.9, w: 4.0, h: 2.7, fontSize: 12.5, paraSpaceAfter: 8, valign: "top", objectName: "t-bullets" });
txt(s, "Targets are hypotheses; no savings are claimed before a pilot measures them.", { x: 0.5, y: 4.55, w: 9, h: 0.3, fontSize: 11.5, italic: true, color: "5C6B7A", objectName: "impact-note" });

// 10. Next steps ------------------------------------------------------
sec("Next steps");
s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Next steps" });
s.addText("Decisions and next steps", { placeholder: "title" });
txt(s, [{ text: "Approve a one-cohort pilot and agree the success metrics", options: { bullet: true, breakLine: true } },
        { text: "Share the real curriculum and the full 500-row learner data", options: { bullet: true, breakLine: true } },
        { text: "Confirm any expectations from the discovery call that this build has not reviewed", options: { bullet: true, breakLine: true } },
        { text: "Production hardening: persistent checkpointer, reviewer inbox, authentication, tracing", options: { bullet: true, breakLine: true } },
        { text: "Calibrate the LLM judge on 50 human-graded submissions before wider rollout", options: { bullet: true } }],
    { x: 0.7, y: 2.55, w: 8.6, h: 2.5, fontSize: 16, color: "FFFFFF", paraSpaceAfter: 9, valign: "top", objectName: "next-steps" });
s.addNotes("Be transparent: the discovery call audio could not be transcribed during the build; ask the stakeholder for any additional requirements.");

(async () => {
  await pres.writeFile({ fileName: "docs/final_presentation.pptx" });
  await applyTheme("docs/final_presentation.pptx", THEME);
  console.log("deck written");
})();
