"""Generate report figures: sample Gantt chart + policy quantum-distribution chart."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.simulator.workload import generate_workload
from src.simulator.scheduler import simulate
from src.rl.agent import QLearningAgent

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "results")
os.makedirs(OUT, exist_ok=True)

# ---- 1. Gantt of the trained agent on one trace ----
agent = QLearningAgent.load(os.path.join(OUT, "qtable.pkl"))
class P:
    def select_quantum(self, state):
        return agent.greedy_quantum(state)
procs = generate_workload(n_processes=20, seed=42, cpu_bound_fraction=0.5)
res = simulate(procs, n_cores=2, delta=1.0, algorithm="RR",
               quantum_policy=P(), collect_rl_trace=True)

fig, ax = plt.subplots(figsize=(11, 2.8))
cmap = plt.cm.tab20
for core, s, e, pid in res.timeline:
    ax.broken_barh([(s, e - s)], (core * 1.0, 0.8),
                   facecolors=cmap((pid * 37) % 20), edgecolor='black', linewidth=.3)
ax.set_yticks([0.4, 1.4]); ax.set_yticklabels(["Core 0", "Core 1"])
ax.set_xlabel("Simulation time"); ax.set_title("Per-core execution timeline — RL-QT policy (sample trace)")
ax.spines[['top','right']].set_visible(False)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "gantt_sample.png"), dpi=160)

# ---- 2. Quantum-choice distribution of learned policy ----
qs, counts = zip(*sorted(agent.q.keys().__iter__().__length_hint__() * [None] or [], key=str)) if False else (None, None)
import collections
greedy = collections.Counter()
QUANTA = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0]
for s, vals in agent.q.items():
    greedy[QUANTA[vals.index(max(vals))]] += 1
fig, ax = plt.subplots(figsize=(7, 3.4))
ax.bar([str(int(q)) for q in QUANTA], [greedy[q] for q in QUANTA], color="#4f8cff")
ax.set_xlabel("Quantum chosen greedily"); ax.set_ylabel("# states where chosen")
ax.set_title(f"Learned policy distribution across {len(agent.q)} visited states")
ax.spines[['top','right']].set_visible(False)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "policy_dist.png"), dpi=160)

print("figures saved:", os.listdir(OUT))
