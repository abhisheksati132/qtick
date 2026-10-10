"""Test the theoretically-principled reward: queue-delay + switch cost only,
high discount (telescoping sum ~= true waiting + switching objective).

Configs: (gamma, reward_weights) x 300 tabular episodes -> eval 20 seeds.
Saves: results/reward_v2.json
"""
import json
import os
import statistics
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.simulator.scheduler as S
import scripts.train as T
from src.simulator.workload import generate_workload
from src.simulator.scheduler import simulate, QUANTUM_CHOICES
from src.rl.agent import QLearningAgent

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIGS = [
    ("gamma0.99_q0.02", 0.99, (0.0, 1.0, 0.0, 0.02)),
    ("gamma0.99_q0.02_block003", 0.99, (0.0, 1.0, 0.03, 0.02)),
    ("gamma0.90_q0.02", 0.90, (0.0, 1.0, 0.0, 0.02)),
]

orig_sim, orig_Tsim = S.simulate, T.simulate
orig_agent_cls = T.QLearningAgent


def evaluate(agent):
    class P:
        def select_quantum(self, s):
            return QUANTUM_CHOICES[agent.act_index(s)]
    out = []
    for s in range(90000, 90020):
        procs = generate_workload(n_processes=30, seed=s,
                                  cpu_bound_fraction=[0.2, 0.5, 0.8][s % 3])
        res = simulate(procs, algorithm="RR", quantum_policy=P())
        m = res.metrics()
        out.append(m["avg_waiting"] + m["avg_turnaround"] + m["context_switches"])
    return round(statistics.mean(out), 1)


def _rand_state(rng):
    return {
        "mean_remaining_burst": rng.uniform(1, 300),
        "burst_heterogeneity": rng.uniform(0, 2),
        "ready_len": rng.choice([0, 1, 3, 6, 12]),
        "switch_overhead_ratio": rng.uniform(0, 0.3),
        "recent_preempt_fraction": rng.uniform(0, 1)}


def diversity(agent):
    import random
    rng = random.Random(0)
    c = Counter()
    for _ in range(300):
        c[QUANTUM_CHOICES[agent.act_index(_rand_state(rng))]] += 1
    return len(c), dict(c)


results = {}
try:
    for name, gamma, w in CONFIGS:
        def patched(*a, **k):
            k.setdefault("reward_weights", w)
            return orig_sim(*a, **k)

        S.simulate = patched
        T.simulate = patched

        class GA(orig_agent_cls):
            def __init__(self, *a, **k):
                super().__init__(*a, gamma=gamma, **k)

        T.QLearningAgent = GA
        agent, _ = T.train(episodes=300, verbose_every=0)
        n_act, dist = diversity(agent)
        score = evaluate(agent)
        results[name] = {"eval": score, "n_actions": n_act, "dist": dist}
        print(f"{name}: eval={score} actions={n_act}/{len(QUANTUM_CHOICES)} {dist}",
              flush=True)
finally:
    S.simulate = orig_sim
    T.simulate = orig_Tsim
    T.QLearningAgent = orig_agent_cls

with open(os.path.join(ROOT, "results", "reward_v2.json"), "w") as f:
    json.dump(results, f, indent=2)
print("written -> results/reward_v2.json")
