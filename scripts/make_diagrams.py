"""Generate architecture diagrams (PNG) used by the technical report and the final deck."""
import matplotlib
matplotlib.use("Agg")  # headless backend
import matplotlib.pyplot as plt  # drawing
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch  # shapes

NAVY, TEAL, AMBER, GREY, LIGHT, RED = "#0B2545", "#13A89E", "#F2A541", "#5C6B7A", "#EAF2F8", "#C8553D"  # palette


def box(ax, x, y, w, h, text, fc, tc="white", fs=10, bold=True):
    """Draw a rounded box with centred text."""
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12", fc=fc, ec="none"))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", color=tc, fontsize=fs, fontweight="bold" if bold else "normal", linespacing=1.3)


def arrow(ax, p1, p2, color=GREY, style="-|>", ls="-", rad=0.0, label=None, lx=0, ly=0):
    """Draw an arrow between two points."""
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=14, color=color, lw=1.6, linestyle=ls, connectionstyle=f"arc3,rad={rad}"))
    if label:
        ax.text((p1[0] + p2[0]) / 2 + lx, (p1[1] + p2[1]) / 2 + ly, label, fontsize=8, color=color, ha="center")


# ---------------- Diagram 1: system architecture ----------------
fig, ax = plt.subplots(figsize=(12, 6.6)); ax.set_xlim(0, 12); ax.set_ylim(0, 6.6); ax.axis("off")
box(ax, 0.2, 2.9, 1.6, 0.9, "Learner /\nSprints staff", GREY)
box(ax, 2.5, 2.7, 2.2, 1.3, "ORCHESTRATOR\n(LangGraph supervisor)\nroutes by intent", NAVY, fs=10)
box(ax, 6.0, 4.6, 2.6, 1.3, "ADVISOR\nAgentic RAG +\nself-reflection (max 2 rewrites)", TEAL, fs=9.5)
box(ax, 6.0, 2.7, 2.6, 1.3, "ASSESSOR\nSandbox grading +\nevaluator-optimizer (max 3)", TEAL, fs=9.5)
box(ax, 6.0, 0.7, 2.6, 1.3, "PLACEMENT PREP\nbuilds recommendation\n(policy rules)", TEAL, fs=9.5)
box(ax, 9.6, 0.7, 2.2, 1.3, "HUMAN ADVISOR\n(HITL interrupt)\napprove / reject", AMBER, tc=NAVY)
box(ax, 9.6, 4.8, 2.2, 0.9, "ChromaDB\ncurriculum (RAG)", LIGHT, tc=NAVY, fs=9)
box(ax, 9.6, 3.55, 2.2, 0.9, "SQLite (read-only)\nprogress + salary EGP", LIGHT, tc=NAVY, fs=9)
box(ax, 9.6, 2.3, 2.2, 0.9, "Sandboxed Python\nREPL (subprocess)", LIGHT, tc=NAVY, fs=9)
arrow(ax, (1.8, 3.35), (2.5, 3.35)); arrow(ax, (4.7, 3.6), (6.0, 5.2), label="question / progress", lx=-0.25, ly=0.25)
arrow(ax, (4.7, 3.35), (6.0, 3.35), label="code to grade", ly=0.15); arrow(ax, (4.7, 3.0), (6.0, 1.5), label="placement", lx=-0.1, ly=-0.35)
arrow(ax, (8.6, 1.35), (9.6, 1.35), color=AMBER, label="pause", ly=0.12)
arrow(ax, (8.6, 5.25), (9.6, 5.25)); arrow(ax, (8.6, 4.7), (9.6, 4.05)); arrow(ax, (8.6, 3.35), (9.6, 2.75)); arrow(ax, (8.6, 1.6), (9.6, 3.55), ls="--", color=GREY)
ax.text(6.0, 0.3, "MemorySaver checkpointer (thread_id per session) stores state after every step; HITL resumes with Command(resume=...)", fontsize=9, color=NAVY)
ax.text(0.2, 6.3, "Sprints Multi-Agent Orchestrator: architecture", fontsize=14, fontweight="bold", color=NAVY)
ax.text(0.2, 5.95, "All worker results travel as validated AgentMessage JSON envelopes. Any tool exception becomes a structured 'Unable to verify'.", fontsize=9, color=GREY)
fig.savefig("docs/assets/architecture.png", dpi=170, bbox_inches="tight", facecolor="white"); plt.close(fig)

# ---------------- Diagram 2: evaluator-optimizer loop ----------------
fig, ax = plt.subplots(figsize=(11, 3.6)); ax.set_xlim(0, 11); ax.set_ylim(0, 3.6); ax.axis("off")
box(ax, 0.1, 1.2, 1.7, 1.1, "Run tests\nin sandbox", NAVY); box(ax, 2.4, 1.2, 1.7, 1.1, "Draft\nfeedback", TEAL)
box(ax, 4.7, 1.2, 1.7, 1.1, "LLM judge\nscores 0-10", TEAL); box(ax, 7.0, 2.3, 1.7, 0.9, "Refine\n(count + 1)", AMBER, tc=NAVY)
box(ax, 9.1, 1.2, 1.8, 1.1, "Finalize\nrubric score", NAVY)
arrow(ax, (1.8, 1.75), (2.4, 1.75)); arrow(ax, (4.1, 1.75), (4.7, 1.75)); arrow(ax, (6.0, 2.3), (7.0, 2.85), rad=-0.35, label="not approved\nand count < 3", lx=-0.5, ly=0.55)
arrow(ax, (7.5, 2.3), (6.4, 1.95), rad=-0.3, label="rewrite", lx=0.55, ly=-0.1); arrow(ax, (6.4, 1.5), (9.1, 1.5), color=RED, label="approved OR count = 3 (hard stop)", ly=-0.4)
ax.text(0.1, 3.3, "Evaluator-optimizer loop (Assessor)", fontsize=13, fontweight="bold", color=NAVY)
fig.savefig("docs/assets/eval_loop.png", dpi=170, bbox_inches="tight", facecolor="white"); plt.close(fig)
print("diagrams written")
