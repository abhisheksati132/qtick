"""Consolidated analysis: energy Pareto frontier + per-regime winners +
significance digest, all from logged result files.

Run:  python scripts/analyze.py
Saves: results/analysis.json, results/pareto.png
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "results")


def load(name):
    with open(os.path.join(RES, name)) as f:
        return json.load(f)


def main():
    bench = load("benchmark.json")
    practical = [n for n in bench
                 if n != "RR-oracle-q" and "avg_waiting" in bench[n]]
    pts = [(n, bench[n]["avg_waiting"], bench[n]["energy_wh"]) for n in practical]

    # Pareto-optimal: no other point is better-or-equal on both axes
    pareto = []
    for n, w, e in pts:
        if not any((w2 <= w and e2 <= e) and (w2 < w or e2 < e)
                   for _, w2, e2 in pts):
            pareto.append(n)
    pareto.sort(key=lambda n: bench[n]["avg_waiting"])

    regimes = load("benchmark_regimes.json")
    reg_win = {}
    for k in sorted(regimes):
        cand = {n: v for n, v in regimes[k].items() if n in practical}
        reg_win[k] = min(cand, key=lambda n: cand[n])

    stats = load("benchmark_stats.json") if os.path.exists(
        os.path.join(RES, "benchmark_stats.json")) else {}
    sig = {k: v for k, v in stats.items()
           if v.get("significant_0.01") and "oracle" not in k}

    sens = load("sensitivity.json") if os.path.exists(
        os.path.join(RES, "sensitivity.json")) else {}

    out = {
        "pareto_frontier_wait_vs_energy": pareto,
        "regime_winners": reg_win,
        "significant_wins_vs_q16": [k for k in sig if "RR q=16" in k],
        "oracle_comparison": {k: v for k, v in stats.items() if "oracle" in k},
        "reward_sensitivity": sens,
    }
    with open(os.path.join(RES, "analysis.json"), "w") as f:
        json.dump(out, f, indent=2)

    # Pareto plot
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 5))
    for n, w, e in pts:
        ax.scatter(w, e, s=90 if n in pareto else 45,
                   label=n, zorder=3 if n in pareto else 2)
        ax.annotate(n, (w, e), fontsize=7, xytext=(4, 4),
                    textcoords="offset points")
    pw = sorted([bench[n]["avg_waiting"] for n in pareto])
    pe = sorted([bench[n]["energy_wh"] for n in pareto], reverse=True)
    ax.plot(pw, pe, "--", color="gray", lw=1, label="Pareto frontier")
    ax.set_xlabel("Average waiting time (lower better)")
    ax.set_ylabel("Energy (Wh, lower better)")
    ax.set_title("Waiting–energy Pareto frontier (60-trace benchmark)")
    ax.legend(fontsize=7, loc="upper right")
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "pareto.png"), dpi=150)

    print("pareto frontier:", pareto)
    print("regime winners:", reg_win)
    print("significant AI<q16 wins:", out["significant_wins_vs_q16"])
    print("written -> results/analysis.json, results/pareto.png")


if __name__ == "__main__":
    main()
