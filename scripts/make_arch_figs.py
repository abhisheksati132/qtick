# -*- coding: utf-8 -*-
"""70% implementation draft: title, abstract, design (block architecture
in the style of the reference photo), lit survey, experimental results.
Generates QTick_Implementation_Draft.docx + architecture figures."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG = os.path.join(BASE, "results")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle
import matplotlib.lines as mlines


def panel(ax, x, y, w, h, title=None, fc="#EDEBE4", ec="#B9B4A6"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06",
                                fc=fc, ec=ec, lw=1.2))
    if title:
        ax.text(x + w / 2, y + h - 0.14, title, ha="center", va="top",
                fontsize=9, fontweight="bold")


def block(ax, x, y, w, h, text, fc="white", ec="#8A877E", fs=8.5, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.04",
                                fc=fc, ec=ec, lw=1.0))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, fontweight="bold" if bold else "normal", wrap=True)


def arrow(ax, x1, y1, x2, y2, label=None):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color="#55534E", lw=1.2))
    if label:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.08, label, ha="center",
                fontsize=7.5, color="#55534E")


def fig1_system():
    fig, ax = plt.subplots(figsize=(11, 6.2))
    ax.set_xlim(0, 11); ax.set_ylim(0, 6.4); ax.axis("off")

    # ---- left: workload layer ----
    panel(ax, 0.15, 1.5, 1.95, 3.6, "Workload Layer")
    block(ax, 0.3, 4.35, 1.65, 0.55, "Synthetic traces")
    block(ax, 0.3, 3.65, 1.65, 0.55, "Real CSV traces")
    block(ax, 0.3, 2.95, 1.65, 0.55, "Arrival patterns")
    block(ax, 0.3, 2.05, 1.65, 0.55, "Ready Queue +\nProcess History", fc="#FFF7EC")

    # ---- middle top: state encoder ----
    panel(ax, 2.6, 3.35, 3.0, 1.75, "System State Encoder")
    block(ax, 2.75, 4.15, 0.85, 0.6, "Queue\nstats")
    block(ax, 3.68, 4.15, 0.85, 0.6, "Burst\nspread")
    block(ax, 4.61, 4.15, 0.85, 0.6, "Switch\nratio")
    block(ax, 2.75, 3.5, 1.32, 0.5, "Preemption rate")
    block(ax, 4.14, 3.5, 1.32, 0.5, "Last slice used")

    # ---- middle bottom: history encoder ----
    panel(ax, 2.6, 1.5, 3.0, 1.75, "Burst History Encoder")
    block(ax, 2.75, 2.3, 0.85, 0.6, "EWMA")
    block(ax, 3.68, 2.3, 0.85, 0.6, "MLP\npredictor")
    block(ax, 4.61, 2.3, 0.85, 0.6, "I/O\nflags")
    block(ax, 2.75, 1.65, 2.71, 0.5, "Per-program slice history")

    # ---- fusion ----
    ax.add_patch(Circle((5.95, 2.42), 0.22, fc="white", ec="#55534E", lw=1.4))
    ax.text(5.95, 2.42, "+", ha="center", va="center", fontsize=16, fontweight="bold")

    # ---- decision layer ----
    panel(ax, 6.5, 1.5, 2.1, 3.6, "Decision Layer", fc="#F7EBE4", ec="#C96442")
    block(ax, 6.65, 4.0, 1.8, 0.85, "Quantum Agent\nDQN / tabular Q", fc="white", bold=True)
    block(ax, 6.65, 2.95, 1.8, 0.85, "Dispatch Agent\n4-rule Q-learner", fc="white", bold=True)
    block(ax, 6.65, 1.95, 1.8, 0.75, "Safety wrapper\nveto + clamp + governor", fc="#EAF2EB", ec="#3E7B4F")

    # ---- outputs ----
    block(ax, 9.0, 4.0, 1.75, 0.85, "Scheduled\ntimeline", fc="white", bold=True)
    block(ax, 9.0, 2.95, 1.75, 0.85, "Metrics\nwait · switches · energy", fc="white", bold=True)

    arrow(ax, 2.1, 3.4, 2.58, 4.0)
    arrow(ax, 2.1, 2.6, 2.58, 2.4)
    arrow(ax, 5.6, 4.2, 6.45, 4.4)
    arrow(ax, 5.6, 2.4, 5.7, 2.42)
    arrow(ax, 6.17, 2.42, 6.45, 2.42)
    arrow(ax, 8.6, 4.4, 8.97, 4.4)
    arrow(ax, 8.6, 3.3, 8.97, 3.3)

    ax.text(5.5, 0.9, "Reward shaper: +3 finish in-slice  ·  −1 per switch  ·  −0.03 × head-of-line overshoot",
            ha="center", fontsize=9, style="italic",
            bbox=dict(fc="#FFF7EC", ec="#B9B4A6", boxstyle="round,pad=0.3"))
    ax.text(5.5, 0.35, "Training loop (dashed): scheduled outcomes → replay memory → agent updates → better policy",
            ha="center", fontsize=9, style="italic",
            bbox=dict(fc="#F7EBE4", ec="#C96442", boxstyle="round,pad=0.3"))
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "arch_system.png"), dpi=170)
    plt.close(fig)


def fig2_training():
    fig, ax = plt.subplots(figsize=(11, 4.6))
    ax.set_xlim(0, 11); ax.set_ylim(0, 4.8); ax.axis("off")

    panel(ax, 0.15, 1.0, 2.0, 2.9, "Environment")
    block(ax, 0.3, 2.9, 1.7, 0.6, "Simulator step")
    block(ax, 0.3, 2.1, 1.7, 0.6, "Reward signal")
    block(ax, 0.3, 1.3, 1.7, 0.6, "Next state")

    panel(ax, 2.6, 1.0, 2.6, 2.9, "Experience Replay")
    block(ax, 2.75, 2.9, 2.3, 0.6, "Replay buffer (20k transitions)")
    block(ax, 2.75, 2.1, 2.3, 0.6, "Random mini-batches (32)")
    block(ax, 2.75, 1.3, 2.3, 0.6, "Rotating mixes: 20 / 50 / 80% CPU")

    panel(ax, 5.65, 1.0, 2.5, 2.9, "Learners", fc="#F7EBE4", ec="#C96442")
    block(ax, 5.8, 2.9, 2.2, 0.6, "DQN online net (6-64-64-7)")
    block(ax, 5.8, 2.1, 2.2, 0.6, "Target net (sync /300 steps)")
    block(ax, 5.8, 1.3, 2.2, 0.6, "Tabular + dispatch Q-tables")

    panel(ax, 8.6, 1.0, 2.2, 2.9, "Deployment")
    block(ax, 8.75, 2.9, 1.9, 0.6, "Greedy policy (ε = 0)")
    block(ax, 8.75, 2.1, 1.9, 0.6, "Verification suite")
    block(ax, 8.75, 1.3, 1.9, 0.6, "Dashboard / sched_ext")

    arrow(ax, 2.15, 2.5, 2.58, 2.5)
    arrow(ax, 5.2, 2.5, 5.63, 2.5)
    arrow(ax, 8.15, 2.5, 8.58, 2.5)
    # feedback loop
    ax.annotate("", xy=(1.1, 1.0), xytext=(7.0, 1.0),
                arrowprops=dict(arrowstyle="-|>", color="#C96442", lw=1.4,
                                linestyle="dashed",
                                connectionstyle="arc3,rad=0.35"))
    ax.text(4.0, 0.35, "evaluation → better weights → redeploy", ha="center",
            fontsize=9, color="#C96442", fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "arch_training.png"), dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    fig1_system()
    fig2_training()
    print("architecture figures saved")
