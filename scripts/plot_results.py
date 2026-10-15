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

real_path = os.path.join(ROOT, "results", "benchmark_real.json")
if os.path.exists(real_path):
    with open(real_path) as f:
        real_data = json.load(f)
    summary_rows = real_data.get("summary", [])
    # summary_rows format: [name, mean_wait, mean_p95, mean_switches, mean_energy, composite]
    # sort by composite score
    sorted_rows = sorted(summary_rows, key=lambda x: x[5])
    names = [r[0] for r in sorted_rows]
    
    metrics = [
        ([r[1] for r in sorted_rows], "Mean Waiting Time (ms)", "ms"),
        ([r[2] for r in sorted_rows], "P95 Tail Turnaround Time (ms)", "ms"),
        ([r[3] for r in sorted_rows], "Involuntary Context Switches", "count"),
        ([r[4] for r in sorted_rows], "Package Energy Consumption (Wh)", "Wh"),
    ]
    
    def _is_qtick(n):
        return "QTick" in n or "RLD" in n

    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
    for ax, (vals, title, unit) in zip(axes.flat, metrics):
        colors = ["#102C57" if "QTick" in n else ("#2E7D32" if _is_qtick(n) else "#718096") for n in names]
        bars = ax.bar(range(len(names)), vals, color=colors, width=0.65, edgecolor='black', linewidth=0.5)
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, rotation=35, ha="right", fontsize=8.5, fontweight='medium')
        ax.set_title(title, fontsize=11, fontweight='bold', pad=8)
        ax.set_ylabel(unit, fontsize=9)
        ax.grid(axis='y', linestyle='--', alpha=0.4)
        ax.spines[['top', 'right']].set_visible(False)
        
        # Add value labels above bars
        for bar in bars:
            height = bar.get_height()
            label_val = f"{height:.1f}" if height < 1000 else f"{int(height)}"
            ax.annotate(label_val,
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3), textcoords="offset points",
                        ha='center', va='bottom', fontsize=7.5)

    fig.suptitle("Empirical Cloud Trace Performance Benchmark (Alibaba, Google Borg, Azure VM)", fontsize=13, fontweight='bold', y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out = os.path.join(ROOT, "results", "benchmark.png")
    fig.savefig(out, dpi=180)
    print("saved real trace benchmark figure ->", out)
else:
    with open(os.path.join(ROOT, "results", "benchmark.json")) as f:
        rows = json.load(f)

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
                      color=["#102C57" if _is_ai(n) else "#7f7f7f" for n in order])
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
