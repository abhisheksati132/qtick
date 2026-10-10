"""Multi-seed study: train tabular agents from K seeds, evaluate each on
M held-out seed sets, report mean ± std (confidence intervals).

Run:  python scripts/multiseed.py --seeds 3 --train-episodes 300 --eval-episodes 30
Saves: results/multiseed.json ; models -> results/qtable_seed{S}.pkl
"""
import argparse
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.train import train as train_tabular, AgentPolicy
from src.simulator.workload import generate_workload
from src.simulator.scheduler import simulate, StaticQuantumPolicy
from src.rl.agent import QLearningAgent

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def evaluate(agent, seed_base, n_episodes, n_cores=2, delta=1.0):
    # Evaluation must be fully greedy: leftover exploration noise (ε floor)
    # would contaminate the mean ± std comparison against static baselines.
    agent.epsilon = 0.0
    pol = AgentPolicy(agent)
    scores = []
    for ep in range(n_episodes):
        procs = generate_workload(n_processes=30, seed=seed_base + ep,
                                  cpu_bound_fraction=[0.2, 0.5, 0.8][ep % 3])
        res = simulate(procs, n_cores=n_cores, delta=delta, algorithm="RR",
                       quantum_policy=pol)
        m = res.metrics()
        scores.append(m["avg_waiting"] + m["avg_turnaround"]
                      + delta * m["context_switches"])
    return scores


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--train-episodes", type=int, default=300)
    ap.add_argument("--eval-episodes", type=int, default=30)
    args = ap.parse_args()

    seed_bases = [1000 + 7919 * k for k in range(args.seeds)]
    eval_bases = [90000, 91000, 92000]
    per_seed = {}
    for k, sb in enumerate(seed_bases):
        agent, _ = train_tabular(episodes=args.train_episodes, seed0=sb,
                                 verbose_every=0)
        agent.save(os.path.join(ROOT, "results", f"qtable_seed{k}.pkl"))
        ev = {}
        for eb in eval_bases:
            ev[str(eb)] = round(statistics.mean(
                evaluate(agent, eb, args.eval_episodes)), 2)
        ev["mean"] = round(statistics.mean(ev.values()), 2)
        ev["std"] = round(statistics.stdev(ev.values()), 2) if len(ev) > 2 else 0.0
        per_seed[f"seed{k}"] = ev
        print(f"seed{k} (train_base={sb}): " +
              " ".join(f"{k}={v}" for k, v in ev.items()))

    # static baseline on same eval sets for reference
    base = {}
    for eb in eval_bases:
        scores = []
        for ep in range(args.eval_episodes):
            procs = generate_workload(n_processes=30, seed=eb + ep,
                                      cpu_bound_fraction=[0.2, 0.5, 0.8][ep % 3])
            res = simulate(procs, algorithm="RR",
                           quantum_policy=StaticQuantumPolicy(16.0))
            m = res.metrics()
            scores.append(m["avg_waiting"] + m["avg_turnaround"]
                          + m["context_switches"])
        base[str(eb)] = round(statistics.mean(scores), 2)
    base["mean"] = round(statistics.mean(base.values()), 2)
    base["std"] = round(statistics.stdev(base.values()), 2)
    print("static q=16:", base)

    out = {"per_seed_agent": per_seed, "static_q16": base,
           "train_episodes": args.train_episodes,
           "eval_episodes": args.eval_episodes}
    with open(os.path.join(ROOT, "results", "multiseed.json"), "w") as f:
        json.dump(out, f, indent=2)
    print("written -> results/multiseed.json")


if __name__ == "__main__":
    main()
