"""End-to-end platform demo: traces → DQN → safety → verification →
energy → cluster → drift/continual → experiment log.

Run:  python scripts/run_platform_demo.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.simulator.scheduler import simulate
from src.simulator.workload import generate_workload
from src.platform.predictor import load_trace
from src.rl.dqn import DQNQuantumAgent
from src.rl.agent import QLearningAgent
from src.platform.services import (SafeQuantumPolicy, DriftDetector,
                                   ContinualScheduler, energy_metrics,
                                   verify_result, certify,
                                   certify_vs_baseline, ExperimentLog)

QUANTA = DQNQuantumAgent.ACTIONS
log = ExperimentLog()


def banner(t):
    print(f"\n{'='*64}\n  {t}\n{'='*64}")


class AnyPolicy:
    """Uniform wrapper: tabular or DQN behind one interface."""
    def __init__(self, inner):
        self.inner = inner
    def select_quantum(self, state):
        return self.inner.select_quantum(state)


# ---------------------------------------------------------------- 1. traces
banner("1. REAL-TRACE INGESTION")
if os.path.exists("traces/sample_trace.csv"):
    procs = load_trace("traces/sample_trace.csv")
    print(f"loaded {len(procs)} processes from traces/sample_trace.csv "
          f"(drop GWA-T-12 / Google-style CSVs in the same folder)")
else:
    procs = generate_workload(n_processes=30, seed=1)
    print("no trace file found — using synthetic workload")

# ---------------------------------------------------------------- 2. agents
banner("2. AGENTS: tabular + DQN (continuous state)")
tab = QLearningAgent.load("results/qtable.pkl") if os.path.exists("results/qtable.pkl") \
    else QLearningAgent()
tab.epsilon = 0.0
dqn = DQNQuantumAgent()
dqn_path = "results/dqn_quantum.npz"
if os.path.exists(dqn_path):
    dqn = DQNQuantumAgent.load(dqn_path)
    print("DQN weights loaded from", dqn_path)
else:
    print("DQN not trained yet — run scripts/train_dqn.py (demo uses untrained DQN)")

# ------------------------------------------------------------- 3. safety
banner("3. SAFETY WRAPPER (sim-to-real guardrails)")
safe = SafeQuantumPolicy(tab, q_min=2.0, q_max=64.0, margin=0.15,
                         switch_ratio_limit=0.25, fallback_quantum=16.0)
procs = generate_workload(n_processes=25, seed=123)
res = simulate(procs, n_cores=2, delta=1.0, algorithm="RR", quantum_policy=safe)
print("guarded run:", res.metrics()["context_switches"], "switches |",
      "guard stats:", safe.stats)

# --------------------------------------------------------- 4. verification
banner("4. VERIFICATION LAYER (certify properties)")
report = certify(AnyPolicy(safe), lambda seed: generate_workload(
    n_processes=25, seed=seed, cpu_bound_fraction=0.5),
    seeds=[11, 12, 13], switch_cap=250, starvation_ratio=0.85)
print(f"certified across 3 seeds: {report['certified']}")
for r in report["runs"]:
    print(f"  seed run -> pass={r['pass']} CS={r['metrics']['context_switches']} "
          f"wait/makespan={r.get('worst_wait_fraction')}")

from src.simulator.scheduler import StaticQuantumPolicy
reg = certify_vs_baseline(AnyPolicy(safe), StaticQuantumPolicy(16),
                          lambda seed: generate_workload(
                              n_processes=25, seed=seed, cpu_bound_fraction=0.5),
                          seeds=[11, 12, 13], tol=1.2)
print(f"regression guard vs static q=16 (tol 1.2x): {reg['certified']}")
for r in reg["runs"]:
    print(f"  seed {r['seed']}: policy={r['policy']} baseline={r['baseline']} ok={r['ok']}")

# --------------------------------------------------------------- 5. energy
banner("5. ENERGY MODEL")
m = res.metrics()
em = energy_metrics(m["makespan"], n_cores=2, busy_time=res.busy_time)
print(f"energy: {em['energy_ws']} W·s ({em['energy_wh']} Wh) "
      f"[p_idle={em['p_idle']}W p_busy={em['p_busy']}W per core]")
log.record("energy-guarded", {"cores": 2}, em, tags={"phase": "tier3"})

# ------------------------------------------------------- 6. continual loop
banner("6. DRIFT DETECTION + CONTINUAL LEARNING")
episode_counter = {"n": 0}

def train_fn(ep):
    episode_counter["n"] += 1
    p = generate_workload(n_processes=25, seed=40000 + episode_counter["n"],
                          cpu_bound_fraction=0.5)
    r = simulate(p, n_cores=2, delta=1.0, algorithm="RR", quantum_policy=safe)
    mm = r.metrics()
    return mm["avg_waiting"] + mm["avg_turnaround"] + mm["context_switches"]

cont = ContinualScheduler(train_fn, retrain_episodes=40, max_rounds=3,
                          on_retrain=lambda rnd, drift:
                              print(f"  round {rnd}: drift={drift}"))
loop_log = cont.run()
print("continual loop:", loop_log)

# ------------------------------------------------------------- 7. cluster
banner("7. MULTI-NODE CLUSTER SCHEDULER (mini-DeepRM)")
from src.platform.cluster import simulate_cluster, generate_cluster_jobs, QClusterAgent
jobs = generate_cluster_jobs(n=100, seed=3)
out = simulate_cluster(jobs, n_nodes=4, agent=QClusterAgent(4, epsilon=0.2))
print("cluster:", out)
log.record("cluster-q", {"nodes": 4, "jobs": 100},
           {"avg_wait": out["avg_wait"], "util": out["cpu_utilization"]},
           tags={"phase": "tier2"})

# ------------------------------------------------------- 8. leaderboard
banner("8. EXPERIMENT REGISTRY / LEADERBOARD")
log.record("demo-guarded-run", {"cores": 2, "delta": 1.0},
           {"composite_score": round(m["avg_waiting"] + m["avg_turnaround"]
                                     + m["context_switches"], 2)},
           tags={"phase": "demo"})
for row in log.leaderboard("composite_score", top=5):
    print("  ", row)

print("\nplatform demo complete — everything above ran on real code.")
