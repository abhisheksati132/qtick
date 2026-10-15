# -*- coding: utf-8 -*-
"""Generate a clean, graphical, modern System Architecture Diagram for QTick.
Key principle: Focus on visual architecture diagram flow, NOT walls of bullet text.
Output: results/arch_system.png
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, Circle, Polygon, Wedge
import matplotlib.patheffects as pe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "results")
os.makedirs(OUT, exist_ok=True)

# 16:9 widescreen layout, 300 DPI
fig, ax = plt.subplots(figsize=(15, 8.5), dpi=300)
ax.set_xlim(0, 16)
ax.set_ylim(0, 9)
ax.axis("off")

# Soft clean background
ax.add_patch(Rectangle((0, 0), 16, 9, fc="#F8FAFC", ec="none"))

# Colors
C_DARK = "#0F172A"       # Dark Navy
C_BLUE = "#1E40AF"       # Royal Blue
C_BLUE_BG = "#EFF6FF"
C_BLUE_BD = "#93C5FD"

C_GREEN = "#059669"      # Emerald
C_GREEN_BG = "#F0FDF4"
C_GREEN_BD = "#86EFAC"

C_PURPLE = "#7C3AED"     # Purple
C_PURPLE_BG = "#FAF5FF"
C_PURPLE_BD = "#D8B4FE"

C_AMBER = "#D97706"      # Amber
C_AMBER_BG = "#FFFBEB"
C_AMBER_BD = "#FCD34D"

C_RED = "#DC2626"        # Red
C_RED_BG = "#FEF2F2"
C_RED_BD = "#FCA5A5"

C_SLATE = "#334155"      # Slate
C_SLATE_BG = "#F1F5F9"
C_SLATE_BD = "#CBD5E1"

WHITE = "#FFFFFF"

# -----------------------------------------------------------------------------
# Drawing Helpers
# -----------------------------------------------------------------------------
def box(x, y, w, h, title="", subtitle="", fc=WHITE, ec="#CBD5E1", lw=1.5, rx=0.15):
    p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0.04,rounding_size={rx}",
                       fc=fc, ec=ec, lw=lw, zorder=2)
    ax.add_patch(p)
    if title:
        ax.text(x + w / 2, y + h / 2 + (0.12 if subtitle else 0), title,
                ha="center", va="center", fontsize=9.5, fontweight="bold",
                color=C_DARK, zorder=3)
    if subtitle:
        ax.text(x + w / 2, y + h / 2 - 0.16, subtitle,
                ha="center", va="center", fontsize=7.8, color="#64748B", zorder=3)
    return p

def container(x, y, w, h, title, fc, ec, tcol):
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08,rounding_size=0.18",
                       fc=fc, ec=ec, lw=1.8, zorder=1)
    ax.add_patch(p)
    ax.text(x + 0.25, y + h - 0.22, title.upper(), ha="left", va="top",
            fontsize=9.0, fontweight="bold", color=tcol, zorder=3)
    return p

def arrow(x1, y1, x2, y2, label="", color="#475569", lw=1.8, rad=0.0, lpos=0.5, dy=0.12):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=lw,
                                connectionstyle=f"arc3,rad={rad}", shrinkA=3, shrinkB=3),
                zorder=4)
    if label:
        mx = x1 + (x2 - x1) * lpos
        my = y1 + (y2 - y1) * lpos
        ax.text(mx, my + dy, label, ha="center", va="center", fontsize=7.8,
                fontweight="bold", color=color,
                bbox=dict(boxstyle="round,pad=0.18", fc=WHITE, ec=color, lw=0.7),
                zorder=5)

# =============================================================================
# HEADER
# =============================================================================
ax.text(8.0, 8.55, "QTick: Decoupled Multi-Agent Reinforcement Learning Scheduling Architecture",
        ha="center", va="center", fontsize=13.5, fontweight="bold", color=C_DARK)
ax.text(8.0, 8.25, "Closed-Loop Dynamic Time Quantum Adaptation and Task Prioritization with Sub-Microsecond eBPF Kernel Control",
        ha="center", va="center", fontsize=8.5, color="#64748B")

# =============================================================================
# 1. CLOUD WORKLOAD & READY QUEUE (Left Column)
# =============================================================================
container(0.5, 4.4, 3.2, 3.5, "1. Production Cloud Workloads", C_GREEN_BG, C_GREEN_BD, C_GREEN)

# 3 Cloud Trace Badges
box(0.7, 6.7, 2.8, 0.75, "Alibaba Cloud Trace", "10k+ Tasks • Asymmetric Microservices", fc=WHITE, ec=C_GREEN_BD)
box(0.7, 5.8, 2.8, 0.75, "Google Borg Trace", "Heavy-Tailed Bursts • Interactive Tasks", fc=WHITE, ec=C_GREEN_BD)
box(0.7, 4.9, 2.8, 0.75, "Azure VM Workload", "VM Execution Traces • High Variance", fc=WHITE, ec=C_GREEN_BD)

# Ready Queue Container (Bottom Left)
container(0.5, 0.8, 3.2, 3.2, "Active Ready Queue (FIFO / Prioritized)", C_SLATE_BG, C_SLATE_BD, C_SLATE)

# Visual Queue Buffer slots
queue_y = 2.4
ax.text(2.1, 3.3, "Ready Task Queue Buffer", ha="center", va="center", fontsize=8.5, fontweight="bold", color=C_DARK)
q_colors = ["#93C5FD", "#A7F3D0", "#FDE68A", "#FCA5A5", "#DDD6FE"]
q_pids = ["P₁", "P₂", "P₃", "P₄", "..."]
for i in range(5):
    qx = 0.8 + i * 0.52
    ax.add_patch(FancyBboxPatch((qx, queue_y), 0.46, 0.55, boxstyle="round,pad=0.02,rounding_size=0.05",
                                fc=q_colors[i], ec=C_DARK, lw=1.0, zorder=3))
    ax.text(qx + 0.23, queue_y + 0.27, q_pids[i], ha="center", va="center",
            fontsize=8.5, fontweight="bold", color=C_DARK, zorder=4)

ax.text(2.1, 1.8, "Tracked Process History\n(Burst History, Slices, I/O States)",
        ha="center", va="center", fontsize=7.8, color="#475569",
        bbox=dict(boxstyle="round,pad=0.3", fc=WHITE, ec="#CBD5E1", lw=0.8))

# Arrow: Workloads -> Ready Queue
arrow(2.1, 4.4, 2.1, 3.65, "Task Ingestion (Aᵢ, Bᵢ)", color=C_GREEN, lw=2.0)

# =============================================================================
# 2. FEATURE ENCODERS & PREDICTOR (Middle-Left)
# =============================================================================
container(4.1, 4.4, 3.3, 3.5, "2. State Encoders & Predictor", C_BLUE_BG, C_BLUE_BD, C_BLUE)

box(4.3, 6.35, 2.9, 1.1, "System State Vector Extractor",
    "Observable Queue Metrics\n⟨W̄ₜ, σ_B, N_q, δ/W̄ₜ, ρ_preempt, q_{t-1}⟩", fc=WHITE, ec=C_BLUE_BD)

box(4.3, 4.75, 2.9, 1.3, "Online Neural Burst Predictor",
    "3-Layer MLP (History → Estimate)\nHuber Loss • MAE = 4.12 ms\n(Zero Future Oracle Prescience)", fc=WHITE, ec=C_BLUE_BD)

# Arrows: Queue -> Encoders
arrow(3.7, 3.1, 4.3, 6.9, "Queue State", color=C_BLUE, lw=1.8, rad=0.1)
arrow(3.7, 2.2, 4.3, 5.4, "Process History", color=C_BLUE, lw=1.8, rad=-0.05)

# =============================================================================
# 3. DECOUPLED DUAL-AGENT RL CORE (Middle-Right)
# =============================================================================
container(7.8, 4.4, 4.3, 3.5, "3. Decoupled Dual-Agent RL Core", C_PURPLE_BG, C_PURPLE_BD, C_PURPLE)

box(8.0, 6.35, 3.9, 1.1, "Agent 1: DQN Quantum Tuner",
    "6 → 64 → 64 → 6 Dense Network\nAction: qₜ ∈ {2, 4, 8, 16, 32, 64} ms\nTarget Sync every 100 steps", fc=WHITE, ec=C_PURPLE_BD)

box(8.0, 4.75, 3.9, 1.3, "Agent 2: Tabular Dispatcher (RLD)",
    "Lightweight Q-Table (< 45 KB Memory)\nDynamic Policy Selection:\n[SEF | FIFO | LWF | I/O-First]", fc=WHITE, ec=C_PURPLE_BD)

# Arrows: Encoders -> Dual RL Agents
arrow(7.2, 6.9, 8.0, 6.9, "State Vector sₜ", color=C_BLUE, lw=2.0)
arrow(7.2, 5.4, 8.0, 5.4, "Burst Estimate B̂ᵢ", color=C_PURPLE, lw=2.0)

# =============================================================================
# 4. LYAPUNOV DRIFT SAFETY GOVERNOR (Right Column - Top)
# =============================================================================
container(12.5, 4.4, 3.0, 3.5, "4. Safety Governor", C_AMBER_BG, C_AMBER_BD, C_AMBER)

box(12.7, 6.45, 2.6, 1.0, "Starvation Guard", "Anti-Aging Rule\nAge(pᵢ) ≤ τ_starve", fc=WHITE, ec=C_AMBER_BD)
box(12.7, 5.3, 2.6, 0.95, "Quantum Clamping", "Clamps qₜ ∈ [2, 64] ms\nSwitch Rate Throttling", fc=WHITE, ec=C_AMBER_BD)
box(12.7, 4.6, 2.6, 0.55, "Work-Conservation Guard", "Zero Idle CPU when Tasks Ready", fc=WHITE, ec=C_AMBER_BD)

# Arrows: Dual Agents -> Safety Governor
arrow(11.9, 6.9, 12.7, 6.9, "Quantum qₜ", color=C_PURPLE, lw=2.0)
arrow(11.9, 5.4, 12.7, 5.4, "PID Pick", color=C_PURPLE, lw=2.0)

# =============================================================================
# 5. MULTI-CORE ENGINE & eBPF KERNEL PATH (Bottom Middle)
# =============================================================================
container(4.1, 0.8, 8.0, 3.2, "5. Hardware Engine & Linux eBPF / sched_ext Subsystem", C_SLATE_BG, C_SLATE_BD, C_SLATE)

# eBPF Kernel Path block
box(4.3, 1.9, 3.6, 1.7, "eBPF Kernel Scheduling Layer",
    "sched_ext Dispatch Hook (qtick.bpf.c)\nLock-Free Ring Buffer (0.42 μs)\nDirect Kernel Dispatch Control", fc=WHITE, ec=C_SLATE_BD)

# Physical Multi-Core Execution Block
box(8.2, 1.9, 3.7, 1.7, "Physical Multi-Core SMP Engine",
    "Core 0, Core 1 ... Core N-1\nExplicit Switch Penalty δ = 1.0 ms\n(L1/L2/L3 Cache Refill & CPI Penalty)\nIntel RAPL Package Energy Tracking", fc=WHITE, ec=C_SLATE_BD)

# Arrow from Safety Governor to eBPF Engine
arrow(14.0, 4.4, 9.8, 3.6, "Certified Safe Action (qₜ, PID)", color=C_AMBER, lw=2.2, rad=0.15)
arrow(7.9, 2.75, 8.2, 2.75, "Dispatch Task", color=C_SLATE, lw=1.8)

# =============================================================================
# 6. REWARD FEEDBACK & EXPERIENCE REPLAY (Bottom Right)
# =============================================================================
container(12.5, 0.8, 3.0, 3.2, "6. Reward & Replay", C_RED_BG, C_RED_BD, C_RED)

box(12.7, 2.2, 2.6, 1.4, "Microarchitectural Reward",
    "R(t) = R_comp + R_switch\n        + R_wait + R_convoy\n\n• +3.0: Slice Completion\n• -1.8·δ: Preemption Switch", fc=WHITE, ec=C_RED_BD)

box(12.7, 1.05, 2.6, 0.95, "Experience Replay", "20k Transitions • Batch 32\nQ-Learning Updates (γ = 0.6)", fc=WHITE, ec=C_RED_BD)

# Arrows: Execution -> Reward -> Replay -> RL Core
arrow(11.9, 2.7, 12.7, 2.7, "Preemptions, Wait", color=C_RED, lw=2.0)
arrow(14.0, 2.2, 14.0, 2.0, "", color=C_RED, lw=1.8)

# Feedback Arrow from Replay to Dual RL Core (Closing the Loop)
arrow(12.5, 1.5, 9.9, 4.4, "Temporal Difference Update ΔQ", color=C_RED, lw=2.2, rad=0.15, lpos=0.45)

fig.tight_layout()
out_fig = os.path.join(OUT, "arch_system.png")
fig.savefig(out_fig, dpi=300, bbox_inches="tight")
print(f"Clean graphical architecture diagram saved successfully -> {out_fig}")
