"""Ablation study: which component matters?

Configs (same traces for all):
  A  static q=16 + FIFO            (no AI at all)
  B  RL-QT only                    (quantum agent, FIFO dispatch)
  C  dispatch only                 (static q=16 + RLD with EWMA fallback)
  D  dispatch + predictor          (static q=16 + RLD with neural predictor)
  E  full system                   (RL-QT + RLD with predictor)

Run:  python scripts/ablation.py --episodes 30
Saves: results/ablation.json
"""
import argparse
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.simulator.workload import generate_workload
from src.simulator.scheduler import simulate, StaticQuantumPolicy
from src.rl.agent import QLearningAgent
from src.rl.dispatch import RLDispatchAgent
from src.platform.predictor import BurstPredictor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "results")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=30)
    ap.add_argument("--cores", type=int, default=2)
    ap.add_argument("--delta", type=float, default=1.0)
    args = ap.parse_args()

    qtab = QLearningAgent.load(os.path.join(RES, "qtable.pkl"))
    qtab.epsilon = 0.0

    class QPol:
        def select_quantum(self, s):
            return qtab.greedy_quantum(s)

    def make_dispatch(with_predictor):
        ag = RLDispatchAgent.load(os.path.join(RES, "qtable_dispatch.pkl"))
        ag.epsilon = 0.0
        ag.predictor = BurstPredictor() if with_predictor else None
        if with_predictor:
            try:
                ag.predictor.load(os.path.join(RES, "burst_predictor.npz"))
            except Exception:
                pass
        class D:
            def select(self, r): return ag.select(r)
            def feedback(self, **k): ag.feedback(**k)
            def observe_slice(self, p, s, waited=0.0, io=0.0):
                ag.observe_slice(p, s, waited, io)
        return D()

    configs = {
        "A: static q16 + FIFO": ("RR", StaticQuantumPolicy(16.0), None),
        "B: RL-QT only": ("RR", QPol(), None),
        "C: dispatch only (EWMA)": ("RR", StaticQuantumPolicy(16.0),
                                    make_dispatch(False)),
        "D: dispatch + predictor": ("RR", StaticQuantumPolicy(16.0),
                                    make_dispatch(True)),
        "E: full (RL-QT + dispatch + predictor)": ("RR", QPol(),
                                                   make_dispatch(True)),
    }

    agg = {k: [] for k in configs}
    for ep in range(args.episodes):
        procs = generate_workload(n_processes=30, seed=60000 + ep,
                                  cpu_bound_fraction=[0.2, 0.5, 0.8][ep % 3])
        for name, (alg, pol, dpol) in configs.items():
            res = simulate(procs, n_cores=args.cores, delta=args.delta,
                           algorithm=alg, quantum_policy=pol,
                           dispatch_policy=dpol)
            m = res.metrics()
            agg[name].append(m["avg_waiting"] + m["avg_turnaround"]
                             + args.delta * m["context_switches"])

    rows = {}
    print(f"{'config':<42}{'mean':>10}{'std':>10}")
    for name, scores in agg.items():
        rows[name] = {"mean": round(statistics.mean(scores), 1),
                      "std": round(statistics.stdev(scores), 1) if len(scores) > 1 else 0.0,
                      "n": len(scores)}
        print(f"{name:<42}{rows[name]['mean']:>10}{rows[name]['std']:>10}")
    with open(os.path.join(RES, "ablation.json"), "w") as f:
        json.dump(rows, f, indent=2)
    print("written -> results/ablation.json")


if __name__ == "__main__":
    main()
