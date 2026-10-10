"""Benchmark the RL-tuned scheduler against static RR, heuristic RR, SJF and SRTF."""
import argparse
import json
import statistics
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.simulator.workload import generate_workload
from src.simulator.scheduler import (simulate, StaticQuantumPolicy,
                                      HeuristicQuantumPolicy, QUANTUM_CHOICES)
from src.rl.agent import QLearningAgent
from src.rl.dqn import DQNQuantumAgent
from src.rl.dispatch import RLDispatchAgent
from src.platform.predictor import BurstPredictor
from scripts.baselines import (DRL_QT, DRLDispatchAgent, MARLAgent,
                               MARLQuantumAgent)


def load_agent_policy(path):
    from src.rl.agent import QLearningAgent

    class P:
        def __init__(self, agent, greedy=True):
            self.agent = agent
            self.greedy = greedy

        def select_quantum(self, state):
            return self.agent.greedy_quantum(state)

    return P(QLearningAgent.load(path))


def load_dqn_policy(path):
    from src.rl.dqn import DQNQuantumAgent

    class P:
        def __init__(self, agent):
            self.agent = agent
            self.epsilon = 0.0

        def select_quantum(self, state):
            return self.agent.greedy_quantum(state)

    return P(DQNQuantumAgent.load(path))


ORACLE_LADDER = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0]


def run_suite(n_episodes=50, n_cores=2, delta=1.0, qtable="results/qtable.pkl",
              qtable_dispatch="results/qtable_dispatch.pkl",
              dqn_weights="results/dqn_quantum.npz", processes=30,
              p_idle=25.0, p_busy=95.0, cpu_fracs=None, arrival_rates=None,
              collect=None):
    """collect (optional dict): filled with per-episode composite scores and
    regime labels for significance/regime analysis. Webapp ignores it."""
    cpu_fracs = cpu_fracs or [0.2, 0.5, 0.8]
    arrival_rates = arrival_rates or ["poisson", "burst", "uniform"]
    from src.platform.services import energy_metrics
    rl_policy = load_agent_policy(qtable)
    dqn_policy = load_dqn_policy(dqn_weights) if os.path.exists(dqn_weights) else None

    dpath = qtable_dispatch
    d_agent = None
    if os.path.exists(dpath):
        from src.rl.dispatch import RLDispatchAgent
        from src.platform.predictor import BurstPredictor
        d_agent = RLDispatchAgent.load(dpath)
        d_agent.epsilon = 0.0   # greedy at evaluation
        # train/serve consistency: dispatch was trained on predictor
        # estimates, so evaluation must use the predictor too (not EWMA).
        ppath = os.path.join(os.path.dirname(dpath) if os.path.dirname(dpath)
                             else ".", "burst_predictor.npz")
        if os.path.exists(ppath):
            try:
                d_agent.predictor = BurstPredictor()
                d_agent.predictor.load(ppath)
            except Exception:
                d_agent.predictor = None

    class DispatchOn:
        def __init__(self, a): self.a = a
        def select(self, ready): return self.a.select(ready)
        def feedback(self, **kw): self.a.feedback(**kw)
        def observe_slice(self, pid, sl, waited=0.0, io=0.0):
            self.a.observe_slice(pid, sl, waited, io)

    from scripts.baselines import (LinuxCFSPolicy, LinuxCFSDispatch, DRL_QT,
                                   DRLDispatchAgent, MARLQuantumAgent, MARLAgent)

    configs = {
        "DQN-QT+RLD (Ours)": ("RR", dqn_policy,
                              DispatchOn(d_agent) if d_agent else None),
        "RL-QT+RLD (Ours)":  ("RR", rl_policy,
                              DispatchOn(d_agent) if d_agent else None),
        "RR q64+RLD":        ("RR", StaticQuantumPolicy(64.0),
                              DispatchOn(d_agent) if d_agent else None),
        "DQN-QT":            ("RR", dqn_policy, None),
        "RL-QT (tabular)":   ("RR", rl_policy, None),
        "Linux CFS":         ("RR", LinuxCFSPolicy(), LinuxCFSDispatch()),
        "DRL-QT (2023)":     ("RR", DRL_QT(), None),
        "DRL-Dispatch (2023)": ("RR", StaticQuantumPolicy(16.0), DRLDispatchAgent()),
        "MARL-Sched (2023)": ("RR", MARLQuantumAgent(2), MARLAgent(2)),
        "DABRR-heuristic":   ("RR", HeuristicQuantumPolicy(), None),
        "RR q=16":           ("RR", StaticQuantumPolicy(16.0), None),
        "RR q=8":            ("RR", StaticQuantumPolicy(8.0), None),
        "RR q=4":            ("RR", StaticQuantumPolicy(4.0), None),
        "RR q=2":            ("RR", StaticQuantumPolicy(2.0), None),
    }
    # prune configs with missing model files
    configs = {k: v for k, v in configs.items() if v[1] is not None}

    # aggregate over many random workload traces
    agg = {name: [] for name in configs}
    if collect is not None:
        collect["scores"] = {name: [] for name in list(configs) + ["RR-oracle-q"]}
        collect["regimes"] = []
    for ep in range(n_episodes):
        cpu_frac = cpu_fracs[ep % len(cpu_fracs)]
        arr = arrival_rates[ep % len(arrival_rates)]
        procs = generate_workload(n_processes=processes, seed=50000 + ep,
                                  cpu_bound_fraction=cpu_frac,
                                  arrival_rate=arr)
        if collect is not None:
            collect["regimes"].append({"cpu_frac": cpu_frac, "arrival": arr})
        for name, (alg, pol, dpol) in configs.items():
            res = simulate(procs, n_cores=n_cores, delta=delta,
                           algorithm=alg, quantum_policy=pol,
                           dispatch_policy=dpol)
            m = res.metrics()
            m["score"] = (m["avg_waiting"] + m["avg_turnaround"]
                          + delta * m["context_switches"] / max(n_cores, 1))
            em = energy_metrics(m["makespan"], n_cores, res.busy_time,
                                p_idle=p_idle, p_busy=p_busy)
            m["energy_wh"] = em["energy_wh"]
            agg[name].append(m)
            if collect is not None:
                collect["scores"][name].append(m["score"])
        # oracle-tuned static quantum: best q on THIS trace (unfair advantage).
        # Only computed when collect is requested (CLI), not for the webapp.
        if collect is not None:
            best = float("inf")
            for q in ORACLE_LADDER:
                r = simulate(procs, n_cores=n_cores, delta=delta, algorithm="RR",
                             quantum_policy=StaticQuantumPolicy(q))
                mm = r.metrics()
                s = (mm["avg_waiting"] + mm["avg_turnaround"]
                     + delta * r.context_switches / max(n_cores, 1))
                best = min(best, s)
            collect["scores"]["RR-oracle-q"].append(best)
            
            # Oracle SJF and SRTF (requires future knowledge)
            r_sjf = simulate(procs, n_cores=n_cores, delta=delta, algorithm="SJF")
            m_sjf = r_sjf.metrics()
            collect.setdefault("oracle_sjf", []).append(m_sjf["avg_waiting"] + m_sjf["avg_turnaround"])
            
            r_srtf = simulate(procs, n_cores=n_cores, delta=delta, algorithm="SRTF")
            m_srtf = r_srtf.metrics()
            collect.setdefault("oracle_srtf", []).append(m_srtf["avg_waiting"] + m_srtf["avg_turnaround"] + delta * r_srtf.context_switches / max(n_cores, 1))

    rows = {}
    for name, runs in agg.items():
        rows[name] = {
            k: round(statistics.mean(r[k] for r in runs), 3)
            for k in runs[0]
        }
        rows[name]["composite_score"] = round(statistics.mean(r["score"] for r in runs), 3)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=50)
    ap.add_argument("--cores", type=int, default=2)
    ap.add_argument("--delta", type=float, default=1.0)
    ap.add_argument("--qtable", default="results/qtable.pkl")
    ap.add_argument("--dqn", default="results/dqn_quantum.npz")
    args = ap.parse_args()

    collect = {}
    rows = run_suite(n_episodes=args.episodes, n_cores=args.cores,
                     delta=args.delta, qtable=args.qtable,
                     dqn_weights=args.dqn, collect=collect)

    # oracle row (mean of per-trace best static quanta)
    if "RR-oracle-q" in collect.get("scores", {}):
        import statistics as _st
        rows["RR-oracle-q"] = {
            "composite_score": round(_st.mean(collect["scores"]["RR-oracle-q"]), 3),
            "note": "mean of per-trace oracle best-q; unfair advantage baseline",
        }

    # significance: paired Wilcoxon signed-rank + effect size (rank-biserial)
    try:
        from scipy.stats import wilcoxon
        import numpy as np
        stats = {}
        ai_names = [n for n in collect["scores"]
                    if ("RL-QT" in n or "DQN" in n) and n in rows]
        for other in ["RR q=16", "RR-oracle-q", "DABRR-heuristic"]:
            if other not in collect["scores"]:
                continue
            for ai in ai_names:
                x = np.array(collect["scores"][ai])
                y = np.array(collect["scores"][other])
                r = wilcoxon(x, y, alternative="less")
                n = len(x)
                z = (r.statistic - n * (n + 1) / 4) / ((n * (n + 1) * (2 * n + 1) / 24) ** 0.5)
                rb = abs(z) / (n ** 0.5)   # rank-biserial r
                stats[f"{ai} < {other}"] = {
                    "p_value": float(r.pvalue),
                    "significant_0.01": bool(r.pvalue < 0.01),
                    "effect_r": round(float(rb), 3),
                    "median_diff": round(float(np.median(y - x)), 2),
                }
        with open("results/benchmark_stats.json", "w") as f:
            json.dump(stats, f, indent=2)
        print("\n-- significance (paired Wilcoxon, H1: AI composite < other) --")
        for k, v in stats.items():
            print(f"  {k}: p={v['p_value']:.2e} "
                  f"({'SIG' if v['significant_0.01'] else 'n.s.'}, r={v['effect_r']})")
    except ImportError:
        print("\n(scipy missing — skipping significance tests)")

    # per-regime breakdown
    try:
        regimes = {}
        for i, reg in enumerate(collect["regimes"]):
            key = f"cpu={reg['cpu_frac']}/{reg['arrival']}"
            regimes.setdefault(key, {n: [] for n in collect["scores"]})
            for n in collect["scores"]:
                regimes[key][n].append(collect["scores"][n][i])
        regrows = {k: {n: round(sum(v) / len(v), 1) for n, v in d.items()}
                   for k, d in regimes.items()}
        with open("results/benchmark_regimes.json", "w") as f:
            json.dump(regrows, f, indent=2)
        print("\n-- per-regime mean composite --")
        for k in sorted(regrows):
            best = min(regrows[k], key=lambda n: regrows[k][n])
            print(f"  {k}: best={best} ({regrows[k][best]})")
    except Exception as e:
        print("\n(regime breakdown failed:", e, ")")

    cols = ["avg_waiting", "avg_turnaround", "avg_response",
            "context_switches", "switch_overhead_time", "cpu_utilization",
            "makespan", "energy_wh", "composite_score"]

    hdr = f"{'algorithm':<18}" + "".join(f"{c:>20}" for c in cols)
    print(hdr)
    print("-" * len(hdr))
    table_rows = {n: r for n, r in rows.items() if "avg_waiting" in r}
    for name in sorted(table_rows, key=lambda n: table_rows[n]["composite_score"]):
        print(f"{name:<18}" + "".join(f"{table_rows[name][c]:>20.3f}" for c in cols))
    if "RR-oracle-q" in rows or "oracle_sjf" in collect:
        print("\n" + "=" * 70)
        print("  THEORETICAL ORACLE BOUNDS (Requires 100% Unknowable Future Prescience)")
        print("=" * 70)
        if "oracle_sjf" in collect:
            print(f"  SJF (Oracle)*   : composite = {statistics.mean(collect['oracle_sjf']):.2f} (Assumes exact burst time known in advance)")
        if "oracle_srtf" in collect:
            print(f"  SRTF (Oracle)*  : composite = {statistics.mean(collect['oracle_srtf']):.2f} (Assumes exact remaining time known in advance)")
        if "RR-oracle-q" in rows:
            print(f"  RR-oracle-q*    : composite = {rows['RR-oracle-q']['composite_score']:.2f} (Per-trace optimal static quantum grid search)")
        print("  * Included solely as theoretical ceiling references; not deployable in practice.")

    with open("results/benchmark.json", "w") as f:
        json.dump(rows, f, indent=2)
    print("\nwritten -> results/benchmark.json")


if __name__ == "__main__":
    main()
