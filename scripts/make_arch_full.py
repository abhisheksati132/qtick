# -*- coding: utf-8 -*-
"""Regenerate results/arch_system.png — the full QTick system architecture
figure (portrait, panel style). Replaces the older render whose Dashboard
box still referenced the removed Platform tab."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GREEN_BG, GREEN_EC, GREEN_TX = "#EDF3EA", "#8AA583", "#4E6E50"
BLUE_BG, BLUE_EC, BLUE_TX = "#E9F0F9", "#7AA0CC", "#3A5A8C"
BEIGE_BG, BEIGE_EC = "#F7F1E3", "#C9A96A"
PURP_BG, PURP_EC = "#EFEBF6", "#9B8BC4"
RED_BG, RED_EC = "#F9EAEA", "#C48484"
INK, MUT = "#1B2A41", "#5C6672"


def panel(ax, x, y, w, h, title, fc, ec, dashed=False, tcol=None):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.09",
        fc=fc, ec=ec, lw=1.2,
        linestyle=(0, (4, 3)) if dashed else "-"))
    ax.text(x + 0.15, y + h - 0.1, title, ha="left", va="top", fontsize=8,
            fontweight="bold", color=tcol or MUT)


def box(ax, x, y, w, h, title, lines=(), tsize=8):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.06",
        fc="white", ec="#B9B4A6", lw=1.0))
    ax.text(x + w / 2, y + h - 0.1, title, ha="center", va="top",
            fontsize=tsize, fontweight="bold", color=INK)
    yy = y + h - 0.32
    for ln in lines:
        ax.text(x + w / 2, yy, ln, ha="center", va="top", fontsize=6.5,
                color=MUT)
        yy -= 0.17


def bullets(ax, x, y, items, fs=6.8):
    for i, t in enumerate(items):
        ax.text(x, y - i * 0.24, "· " + t, ha="left", va="top", fontsize=fs,
                color=MUT)


def arrow(ax, x1, y1, x2, y2, label=None, dashed=False, color="#55534E"):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=1.2,
                                linestyle=(0, (4, 3)) if dashed else "-"))
    if label:
        ax.text((x1 + x2) / 2 + 0.06, (y1 + y2) / 2 + 0.08, label, ha="left",
                fontsize=6.5, color=color)


def main():
    fig, ax = plt.subplots(figsize=(8.5, 11.8))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 14.4)
    ax.axis("off")
    ax.add_patch(FancyBboxPatch((0.08, 0.08), 9.84, 14.1,
                                boxstyle="round,pad=0.02,rounding_size=0.12",
                                fc="none", ec="#999999", lw=1.2))
    ax.text(5, 13.85, "QTick — System Architecture", ha="center", va="top",
            fontsize=13, fontweight="bold", color=INK)

    # ---- workload layer ----
    panel(ax, 0.3, 11.75, 9.4, 1.35, "Workload layer", GREEN_BG, GREEN_EC,
          tcol=GREEN_TX)
    box(ax, 0.45, 11.88, 2.95, 0.95, "Synthetic traces",
        ["Gamma bursts, CPU/IO mixes", "20 / 50 / 80% CPU"])
    box(ax, 3.52, 11.88, 2.95, 0.95, "Cloud production traces",
        ["Alibaba · Google Borg · Azure VM", "10,000+ Real Microservices"])
    box(ax, 6.6, 11.88, 2.95, 0.95, "Arrival patterns",
        ["Poisson / bursty / uniform"])
    arrow(ax, 5, 11.75, 5, 11.2, label="processes (arrival time, burst length)")

    # ---- simulator core ----
    ax.add_patch(FancyBboxPatch((0.3, 10.3), 9.4, 0.75,
                                boxstyle="round,pad=0.02,rounding_size=0.09",
                                fc=BLUE_BG, ec=BLUE_EC, lw=1.2))
    ax.text(0.45, 10.9, "Simulator core", ha="left", va="top", fontsize=8.5,
            fontweight="bold", color=BLUE_TX)
    ax.text(5.4, 10.78, "Discrete-event, N cores", ha="center", va="top",
            fontsize=7.5, fontweight="bold", color=INK)
    ax.text(5.4, 10.52, "Ready queue · arrival engine · per-core dispatch · "
                        "overhead δ charged per switch · exact waiting-time "
                        "accounting · timeline log",
            ha="center", va="top", fontsize=6, color=MUT)
    arrow(ax, 1.6, 10.3, 1.6, 9.95, label="state snapshot")
    arrow(ax, 4.95, 10.3, 4.95, 9.95, label="decision request")
    arrow(ax, 8.4, 10.3, 8.4, 9.5, label="slice outcome")

    # ---- encoders ----
    panel(ax, 0.3, 7.75, 2.65, 2.0, "", BEIGE_BG, BEIGE_EC)
    ax.text(0.45, 9.57, "System state encoder", ha="left", va="top",
            fontsize=8, fontweight="bold", color="#8A6D3B")
    bullets(ax, 0.45, 9.2, ["Mean work", "Burst spread", "Queue length",
                            "Switch ratio", "Preemptions", "Last slice"])
    panel(ax, 0.3, 5.55, 2.65, 2.0, "", BEIGE_BG, BEIGE_EC)
    ax.text(0.45, 7.37, "Burst history encoder", ha="left", va="top",
            fontsize=8, fontweight="bold", color="#8A6D3B")
    bullets(ax, 0.45, 7.0, ["EWMA memory", "MLP predictor", "I/O flags"])

    # fusion point
    ax.add_patch(Circle((3.18, 8.85), 0.17, fc="white", ec=MUT, lw=1.3))
    ax.text(3.18, 8.85, "+", ha="center", va="center", fontsize=13,
            fontweight="bold", color=MUT)
    arrow(ax, 2.95, 8.85, 3.0, 8.85)
    arrow(ax, 3.36, 8.85, 3.6, 8.85)

    # ---- decision layer ----
    panel(ax, 3.85, 5.55, 2.85, 4.2, "Decision layer", PURP_BG, PURP_EC,
          tcol="#6A5A9B")
    box(ax, 4.0, 8.8, 2.55, 0.85, "Quantum agent",
        ["DQN / tabular", "quantum q: 1 to 64"])
    box(ax, 4.0, 7.8, 2.55, 0.85, "Dispatch agent",
        ["4 rules:", "FIFO · SEF · LWF · IO-1"])
    box(ax, 4.0, 6.8, 2.55, 0.85, "Safety wrapper",
        ["Veto · clamp · govern", "Guards final (q, process) choice"])
    ax.text(5.27, 6.55, "guarded (q, process)", ha="center", fontsize=6.5,
            color=MUT)
    arrow(ax, 5.27, 6.5, 5.27, 6.15)

    # ---- reward shaper ----
    panel(ax, 7.05, 7.75, 2.65, 2.0, "", RED_BG, RED_EC)
    ax.text(8.37, 9.57, "Reward shaper", ha="center", va="top",
            fontsize=8, fontweight="bold", color="#A05A5A")
    for i, t in enumerate(["+3 on process finish", "−1 per context switch",
                           "−0.03 × quantum overshoot"]):
        ax.text(8.37, 9.15 - i * 0.24, t, ha="center", va="top", fontsize=6.8,
                color=MUT)
    arrow(ax, 7.7, 7.75, 7.7, 5.6, label="to execution")

    # ---- execution bar ----
    ax.add_patch(FancyBboxPatch((3.85, 4.85), 2.85, 0.6,
                                boxstyle="round,pad=0.02,rounding_size=0.09",
                                fc=BLUE_BG, ec=BLUE_EC, lw=1.2))
    ax.text(5.27, 5.32, "Execution on cores", ha="center", va="top",
            fontsize=8, fontweight="bold", color=INK)
    ax.text(5.27, 5.08, "transition stored for replay", ha="center", va="top",
            fontsize=6.5, color=MUT)
    arrow(ax, 5.27, 4.85, 5.27, 4.6, label="metrics")
    # learning-flow curve: execution -> replay buffer
    ax.annotate("", xy=(1.1, 2.35), xytext=(3.8, 4.9),
                arrowprops=dict(arrowstyle="-|>", color="#8A6D3B", lw=1.2,
                                linestyle=(0, (4, 3)),
                                connectionstyle="arc3,rad=0.25"))

    # ---- scoreboard ----
    panel(ax, 0.3, 2.9, 9.4, 1.5, "Scoreboard", GREEN_BG, GREEN_EC,
          tcol=GREEN_TX)
    ax.text(5, 4.05, "Waiting · turnaround · switches · CPU use · energy · "
                     "makespan", ha="center", fontsize=6.5, color=MUT)
    box(ax, 0.45, 3.05, 2.95, 0.8, "Verification",
        ["Caps / bounds / regression", "checks · experiment log"], tsize=7.5)
    box(ax, 3.52, 3.05, 2.95, 0.8, "Dashboard",
        ["Race · watch · brain · guide views"], tsize=7.5)
    box(ax, 6.6, 3.05, 2.95, 0.8, "sched_ext policy server",
        ["Linux deployment path"], tsize=7.5)

    # ---- training loop ----
    panel(ax, 0.3, 0.45, 9.4, 2.15, "Training loop", "#FAF6EA", BEIGE_EC,
          dashed=True, tcol="#8A6D3B")
    ax.text(5, 2.3, "Dashed path: execution → replay → learners",
            ha="center", fontsize=6.5, color=MUT)
    box(ax, 0.45, 1.45, 2.9, 0.7, "Replay buffer",
        ["Capacity 20,000 transitions"], tsize=7.5)
    box(ax, 3.55, 1.45, 2.9, 0.7, "Random mini-batches",
        ["Batch size 32"], tsize=7.5)
    box(ax, 6.65, 1.45, 2.9, 0.7, "Learners",
        ["DQN online/target nets", "+ tabular Q + dispatch updates"], tsize=7)
    ax.add_patch(FancyBboxPatch((0.45, 0.6), 9.1, 0.68,
                                boxstyle="round,pad=0.02,rounding_size=0.06",
                                fc="white", ec="#B9B4A6", lw=1.0))
    ax.text(5, 1.12, "Exploration: ε decays 1.0 → 0.08 over training",
            ha="center", va="top", fontsize=6.8, color=MUT)
    ax.text(5, 0.9, "Episodes rotate workload mixes so no policy overfits "
                    "a single trace",
            ha="center", va="top", fontsize=6.8, color=MUT)
    arrow(ax, 3.35, 1.8, 3.5, 1.8, dashed=True, color="#8A6D3B")
    arrow(ax, 6.45, 1.8, 6.6, 1.8, dashed=True, color="#8A6D3B")

    # legend
    arrow(ax, 0.5, 0.25, 0.9, 0.25)
    ax.text(1.0, 0.25, "data flow", ha="left", va="center", fontsize=7,
            color=MUT)
    arrow(ax, 2.4, 0.25, 2.8, 0.25, dashed=True)
    ax.text(2.9, 0.25, "learning flow", ha="left", va="center", fontsize=7,
            color=MUT)
    ax.text(4.6, 0.25, "⊕ fusion point — queue state + program history merge",
            ha="left", va="center", fontsize=7, color=MUT)
    ax.text(0.5, 0.08, "FIFO = first-come · SEF = shortest-predicted · "
                       "LWF = longest-waiting · IO-1 = I/O-first",
            ha="left", va="center", fontsize=6.5, color=MUT)

    fig.tight_layout()
    fig.savefig(os.path.join(BASE, "results", "arch_system.png"), dpi=170)
    plt.close(fig)
    print("arch_system.png regenerated")


if __name__ == "__main__":
    main()
