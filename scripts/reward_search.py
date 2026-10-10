"""Reward-shape search on the FAST tabular agent (exact per-state updates).

Candidate (completion, switch, blocking, queue) weightings x 400 episodes,
evaluated on fixed synthetic seeds AND the ctc real trace head.
Picks the shaping with the best worst-case rank.

Run:  python scripts/reward_search.py
Saves: results/reward_search.json
"""
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.simulator.scheduler as S
import scripts.train as T
from src.rl.agent import QLearningAgent
from src.simulator.workload import generate_workload
from src.simulator.scheduler import simulate
from src.platform.predictor import load_trace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES = [
    (3.0, 1.0, 0.03, 0.0),    # status quo ante (known good ~852)
    (3.0, 1.0, 0.03, 0.001),  # + whisper of queue-delay
    (3.0, 1.0, 0.06, 0.001),  # + stronger blocking
    (2.0, 1.0, 0.03, 0.002),  # middle ground
]


def evaluate(agent, seeds):
    from src.simulator.scheduler import QUANTUM_CHOICES

    class P:
        def select_quantum(self, s):
            return QUANTUM_CHOICES[agent.act_index(s)]
    out = []
    for s in seeds:
        procs = generate_workload(n_processes=30, seed=s,
                                  cpu_bound_fraction=[0.2, 0.5, 0.8][s % 3])
        res = simulate(procs, algorithm="RR", quantum_policy=P())
        m = res.metrics()
        out.append(m["avg_waiting"] + m["avg_turnaround"] + m["context_switches"])
    return round(statistics.mean(out), 1)


def evaluate_ctc(agent):
    from src.simulator.scheduler import QUANTUM_CHOICES

    class P:
        def select_quantum(self, s):
            return QUANTUM_CHOICES[agent.act_index(s)]
    procs = load_trace(os.path.join(ROOT, "traces", "real", "ctc.csv"))[:200]
    res = simulate(procs, n_cores=2, delta=1.0, algorithm="RR", quantum_policy=P())
    m = res.metrics()
    return (round(m["avg_waiting"] + m["avg_turnaround"] + m["context_switches"], 1),
            res.context_switches)


def main():
    seeds = list(range(90000, 90020))
    results = {}
    orig_sim, orig_t = S.simulate, T.simulate
    try:
        for w in CANDIDATES:
            def patched(*a, **k):
                k.setdefault("reward_weights", w)
                return orig_sim(*a, **k)
            S.simulate = patched
            T.simulate = patched
            agent, _ = T.train(episodes=400, verbose_every=0)
            syn = evaluate(agent, seeds)
            ctc, cs = evaluate_ctc(agent)
            # action diversity check (degeneracy detector)
            import random
            from collections import Counter
            rng = random.Random(0)
            from src.simulator.scheduler import QUANTUM_CHOICES
            def _rand_state():
                return {
                    "mean_remaining_burst": rng.uniform(1, 300),
                    "burst_heterogeneity": rng.uniform(0, 2),
                    "ready_len": rng.choice([0, 1, 3, 6, 12]),
                    "switch_overhead_ratio": rng.uniform(0, 0.3),
                    "recent_preempt_fraction": rng.uniform(0, 1)}
            c = Counter(QUANTUM_CHOICES[agent.act_index(_rand_state())]
                        for _ in range(300))
            n_actions = len(c)
            results[str(w)] = {"synthetic": syn, "ctc": ctc, "ctc_switches": cs,
                               "n_actions_used": n_actions}
            print(f"w={w} -> synthetic {syn} | ctc {ctc} (cs={cs}) | actions used {n_actions}/{len(QUANTUM_CHOICES)}",
                  flush=True)
    finally:
        S.simulate = orig_sim
        T.simulate = orig_t
    with open(os.path.join(ROOT, "results", "reward_search.json"), "w") as f:
        json.dump(results, f, indent=2)
    print("written -> results/reward_search.json")


if __name__ == "__main__":
    main()
