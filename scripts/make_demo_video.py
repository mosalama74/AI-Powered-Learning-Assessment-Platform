"""Render a silent, captioned MP4 walkthrough of the scripted demo (terminal replay).

Input : demo output captured with `python -m src.main demo --offline --auto-approve > /tmp/demo_run.txt`
Output: docs/demo_walkthrough.mp4 (about 3.5 minutes). Re-record with your Gemini key and a voice-over for the final submission.
"""
import subprocess, textwrap, tempfile, os, sys  # std lib
from PIL import Image, ImageDraw, ImageFont  # drawing

W, H = 1280, 720
FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 18)
BOLD = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 18)
SANS_B = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
SANS = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 19)
NAVY, TEAL, AMBER, TERM, WHITE, GREY, RED = (11, 37, 69), (19, 168, 158), (242, 165, 65), (13, 27, 42), (255, 255, 255), (150, 165, 180), (232, 110, 85)
CAPTIONS = [
    "Student question: the Orchestrator classifies it and routes to the Advisor. ChromaDB retrieval, a self-check, then a grounded answer.",
    "Progress and target salary (EGP) come from a read-only SQLite lookup, never from model memory.",
    "Grading: the Assessor runs the code in a sandbox, drafts feedback, an LLM judge scores it, and the refine loop is capped at 3 rounds.",
    "Placement: the graph PAUSES (LangGraph interrupt). A human advisor decides, and only then does the graph resume.",
    "Failure injected: SQLite is unavailable, so the system returns a structured 'Unable to verify' instead of guessing.",
]
raw = open(sys.argv[1] if len(sys.argv) > 1 else "/tmp/demo_run.txt").read().splitlines()
BAN = "=" * 78
scenes, cur, i = [], None, 0
while i < len(raw):  # split output into scenes at banner-title-banner triples
    if raw[i] == BAN and i + 2 < len(raw) and raw[i + 2] == BAN and raw[i + 1][:2] in ("1)", "2)", "3)", "4)", "5)"):
        cur = {"title": raw[i + 1], "lines": []}; scenes.append(cur); i += 3; continue
    if cur is not None and not (raw[i] == BAN):
        cur["lines"].append(raw[i])
    elif cur is not None and raw[i] == BAN and i + 2 < len(raw) and raw[i + 1].startswith("HUMAN"):  # HITL banner stays inside scene 4
        cur["lines"].append(raw[i + 1]); i += 3; continue
    i += 1
for sc in scenes:  # wrap long lines to the terminal width
    out = []
    for ln in sc["lines"]:
        out += textwrap.wrap(ln, 98, subsequent_indent="    ") or [""]
    sc["lines"] = out
total_lines = sum(len(s["lines"]) for s in scenes)
per_line = max(0.55, (200 - 8 - 8 - 4 * len(scenes)) / total_lines)  # aim for about 200 s


def color(line):
    s = line.strip()
    if s.startswith("System"): return (120, 230, 170), BOLD
    if s.startswith("Learner"): return AMBER, BOLD
    if s.startswith("HUMAN") or "[scripted human" in s: return AMBER, BOLD
    if "Unable to verify" in s: return RED, BOLD
    if s.startswith("- "): return GREY, FONT
    return (215, 225, 235), FONT


def frame(title, lines, caption, progress, header="Sprints Orchestrator demo (offline mode)"):
    im = Image.new("RGB", (W, H), NAVY); d = ImageDraw.Draw(im)
    d.text((30, 18), title, font=SANS_B, fill=WHITE)
    d.rounded_rectangle((24, 70, W - 24, 590), radius=10, fill=TERM)
    y = 84
    for ln in lines[-19:]:
        c, f = color(ln); d.text((42, y), ln, font=f, fill=c); y += 26
    d.rounded_rectangle((24, 604, W - 24, 690), radius=10, fill=(20, 60, 95))
    for k, row in enumerate(textwrap.wrap(caption, 120)[:2]): d.text((42, 616 + k * 28), row, font=SANS, fill=WHITE)
    d.text((W - 40, 668), header, font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14), fill=TEAL, anchor="ra")
    d.rectangle((0, H - 8, int(W * progress), H), fill=TEAL)
    return im


tmp = tempfile.mkdtemp(); items = []  # (png path, seconds)
def add(im, secs):
    p = os.path.join(tmp, f"f{len(items):04d}.png"); im.save(p); items.append((p, secs))

card = Image.new("RGB", (W, H), NAVY); d = ImageDraw.Draw(card)
d.text((80, 170), "Sprints Multi-Agent AI Career & Assessment Orchestrator", font=SANS_B, fill=WHITE)
for k, t in enumerate(["Demo walkthrough: five scenes", "1  Student question (Advisor, agentic RAG on ChromaDB)", "2  Progress and target salary in EGP (SQLite)", "3  Code grading (sandbox + evaluator-optimizer, max 3 refinements)",
                       "4  Placement approval (human-in-the-loop pause)", "5  Graceful failure ('Unable to verify')", "", "Recorded in OFFLINE mode with deterministic stand-ins. Re-record with a Gemini key for submission."]):
    d.text((80, 240 + k * 36), t, font=SANS, fill=TEAL if k == 0 else (AMBER if k == 7 else WHITE))
add(card, 8)
done = 0
for si, sc in enumerate(scenes):
    shown = []
    for ln in sc["lines"]:
        shown.append(ln); done += 1
        add(frame(sc["title"], shown, CAPTIONS[si], done / total_lines), per_line)
    items[-1] = (items[-1][0], 4)  # hold the finished scene for 4 s
end = Image.new("RGB", (W, H), NAVY); d = ImageDraw.Draw(end)
d.text((80, 220), "Summary", font=SANS_B, fill=TEAL)
for k, t in enumerate(["LangGraph orchestrator routes by intent to Advisor and Assessor", "Retrieval under 1000 ms (timeout + fallback), structured 'Unable to verify' on tool failure",
                       "Evaluator-optimizer halts after at most 3 refinements", "Humans approve every placement; the AI only recommends", "44 automated tests cover each acceptance criterion"]):
    d.text((80, 290 + k * 40), "- " + t, font=SANS, fill=WHITE)
add(end, 8)
lst = os.path.join(tmp, "list.txt")
with open(lst, "w") as fh:
    for p, secs in items: fh.write(f"file '{p}'\nduration {secs:.3f}\n")
    fh.write(f"file '{items[-1][0]}'\n")
out = "docs/demo_walkthrough.mp4"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-vf", "fps=10,format=yuv420p", "-c:v", "libx264", "-crf", "24", out], check=True)
print("scenes:", [(s["title"][:12], len(s["lines"])) for s in scenes], "| seconds ~", round(sum(s for _, s in items)), "->", out)
