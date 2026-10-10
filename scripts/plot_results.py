import json
import os
import sys

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    sys.exit("matplotlib is required: pip install matplotlib")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(ROOT, "results", "benchmark.json")) as f:
    rows = json.load(f)

# summary rows (e.g. RR-oracle-q) carry no per-metric values — exclude them
order = sorted([n for n in rows if "avg_waiting" in rows[n]],
               key=lambda n: rows[n]["composite_score"])
metrics = [
    ("avg_waiting", "Average waiting time"),
    ("avg_turnaround", "Average turnaround time"),
    ("context_switches", "Context switches"),
    ("cpu_utilization", "CPU utilization"),
]

def _is_ai(n):
    return ("RL-QT" in n or "DQN" in n or "+RLD" in n)

fig, axes = plt.subplots(2, 2, figsize=(12, 8))
for ax, (key, title) in zip(axes.flat, metrics):
    vals = [rows[n][key] for n in order]
    bars = ax.bar(range(len(order)), vals,
                  color=["#2E7D32" if _is_ai(n) else "#7f7f7f" for n in order])
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(order, rotation=30, ha="right", fontsize=8)
    ax.set_title(title)

fig.suptitle("RL-tuned quantum vs. baselines")
fig.tight_layout()
out = os.path.join(ROOT, "results", "benchmark.png")
fig.savefig(out, dpi=150)
print("saved ->", out)

# training curve
hist_path = os.path.join(ROOT, "results", "training_history.json")
if os.path.exists(hist_path):
    with open(hist_path) as f:
        hist = json.load(f)["avg_reward_per_step"]
    fig2, ax = plt.subplots(figsize=(8, 4))
    ax.plot(hist, linewidth=0.8)
    ax.set_xlabel("Episode")
    ax.set_ylabel("Avg reward / step")
    ax.set_title("Q-learning training convergence")
    fig2.tight_layout()
    out2 = os.path.join(ROOT, "results", "training_curve.png")
    fig2.savefig(out2, dpi=150)
    print("saved ->", out2)
