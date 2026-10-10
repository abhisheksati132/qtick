"""Reward-weight sensitivity: is the result a lucky hyperparameter?

Trains short tabular runs under 6 (switch_w, blocking_w) combos around the
defaults (1.0, 0.03) and evaluates each on one fixed 12-trace suite.
Stable ranking across the grid => robust idea, not a lucky setting.

Run:  python scripts/sensitivity.py
Saves: results/sensitivity.json
"""
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.train import train as train_tabular, AgentPolicy
from src.simulator.workload import generate_workload
from src.simulator.scheduler import simulate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRID = [(1.0, 0.03), (1.0, 0.01), (1.0, 0.06), (1.0, 0.15),
        (0.5, 0.03), (2.0, 0.03)]


def evaluate(agent, seeds):
    pol = AgentPolicy(agent)
    out = []
    for s in seeds:
        procs = generate_workload(n_processes=30, seed=s,
                                  cpu_bound_fraction=[0.2, 0.5, 0.8][s % 3])
        res = simulate(procs, algorithm="RR", quantum_policy=pol)
        m = res.metrics()
        out.append(m["avg_waiting"] + m["avg_turnaround"] + m["context_switches"])
    return round(statistics.mean(out), 1)


def main():
    seeds = list(range(61000, 61012))
    rows = {}
    for sw, bw in GRID:
        import src.simulator.scheduler as S
        # patch default reward weights for this training run
        orig = S.simulate

        def patched(*a, _o=orig, **k):
            k.setdefault("reward_weights", (3.0, sw, bw))
            return _o(*a, **k)

        S.simulate = patched
        # train_tabular imports simulate directly; patch there too
        import scripts.train as T
        T.simulate = patched
        agent, _ = train_tabular(episodes=100, verbose_every=0)
        S.simulate = orig
        T.simulate = orig
        score = evaluate(agent, seeds)
        rows[f"switch_w={sw}, blocking_w={bw}"] = score
        print(f"switch_w={sw:<4} blocking_w={bw:<5} -> eval composite {score}",
              flush=True)
    base = rows["switch_w=1.0, blocking_w=0.03"]
    print("\ndefault:", base, "| max deviation:",
          round(max(abs(v - base) / base for v in rows.values()) * 100, 1), "%")
    with open(os.path.join(ROOT, "results", "sensitivity.json"), "w") as f:
        json.dump(rows, f, indent=2)
    print("written -> results/sensitivity.json")


if __name__ == "__main__":
    main()
