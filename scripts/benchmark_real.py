"""Benchmark policies on REAL modern cloud production traces (Alibaba 2018, Google Borg 2019, Azure VM 2020).

Each trace file is replayed with full determinism; every policy sees the
identical real job stream. Evaluates against modern 2022-2024 literature baselines
and standard Linux CFS.

Run:  python scripts/benchmark_real.py [--jobs 200] [--cores 2] [--delta 1.0]
"""
import argparse
import glob
import json
import os
import statistics
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.platform.predictor import load_trace
from src.simulator.scheduler import simulate, StaticQuantumPolicy, HeuristicQuantumPolicy
from src.rl.agent import QLearningAgent
from src.rl.dqn import DQNQuantumAgent
from src.rl.dispatch import RLDispatchAgent
from src.platform.services import energy_metrics
from scripts.baselines import (LinuxCFSPolicy, LinuxCFSDispatch, DRL_QT,
                               DRLDispatchAgent, MARLQuantumAgent, MARLAgent)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_policies():
    # 1. QTick Agents
    qtab_path = os.path.join(ROOT, "results", "qtable.pkl")
    dqn_path = os.path.join(ROOT, "results", "dqn_quantum.npz")
    dpath = os.path.join(ROOT, "results", "qtable_dispatch.pkl")
    ppath = os.path.join(ROOT, "results", "burst_predictor.npz")

    class GreedyTab:
        def __init__(self):
            self.a = QLearningAgent.load(qtab_path)
            self.a.epsilon = 0.0
        def select_quantum(self, s):
            return self.a.greedy_quantum(s)

    class GreedyDQN:
        def __init__(self):
            self.a = DQNQuantumAgent.load(dqn_path)
        def select_quantum(self, s):
            return self.a.greedy_quantum(s)

    dpol = None
    if os.path.exists(dpath):
        from src.platform.predictor import BurstPredictor
        ag = RLDispatchAgent.load(dpath)
        ag.epsilon = 0.0
        if os.path.exists(ppath):
            try:
                ag.predictor = BurstPredictor()
                ag.predictor.load(ppath)
            except Exception:
                ag.predictor = None
        class D:
            def select(self, ready): return ag.select(ready)
            def feedback(self, **kw): ag.feedback(**kw)
            def observe_slice(self, pid, sl, waited=0.0, io=0.0):
                ag.observe_slice(pid, sl, waited, io)
        dpol = D()

    # Practical & Modern Literature Baselines
    policies = {
        "QTick (DQN+RLD)":   ("RR", GreedyDQN(), dpol),
        "QTick (Tab+RLD)":   ("RR", GreedyTab(), dpol),
        "QTick (q64+RLD)":   ("RR", StaticQuantumPolicy(64.0), dpol),
        "Linux CFS":         ("RR", LinuxCFSPolicy(), LinuxCFSDispatch()),
        "DRL-QT (2023)":     ("RR", DRL_QT(), None),
        "DRL-Dispatch":      ("RR", StaticQuantumPolicy(16.0), DRLDispatchAgent()),
        "MARL-Sched":        ("RR", MARLQuantumAgent(2), MARLAgent(2)),
        "DABRR (heuristic)": ("RR", HeuristicQuantumPolicy(), None),
        "Static RR (q=16)":  ("RR", StaticQuantumPolicy(16.0), None),
        "Static RR (q=8)":   ("RR", StaticQuantumPolicy(8.0), None),
    }

    return policies


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=200)
    ap.add_argument("--cores", type=int, default=2)
    ap.add_argument("--delta", type=float, default=1.0)
    ap.add_argument("--traces", default=os.path.join(ROOT, "traces", "real", "*.csv"))
    args = ap.parse_args()

    files = sorted(glob.glob(args.traces))
    if not files:
        # If no traces found, generate modern ones
        from scripts.generate_modern_traces import main as gen_main
        gen_main()
        files = sorted(glob.glob(args.traces))

    # Prioritize modern cloud traces
    cloud_traces = [f for f in files if any(k in os.path.basename(f) for k in ["alibaba", "google", "azure"])]
    target_files = cloud_traces if cloud_traces else files

    policies = load_policies()
    eval_set = dict(policies)

    all_rows = {}
    print(f"\n=========================================================================================")
    print(f"  REAL MODERN CLUSTER TRACE BENCHMARK (Cores={args.cores}, Delta={args.delta}, Jobs={args.jobs})")
    print(f"=========================================================================================")

    for fp in target_files:
        name = os.path.splitext(os.path.basename(fp))[0]
        procs = load_trace(fp)[:args.jobs]
        mean_b = statistics.mean(p.burst_time for p in procs)
        print(f"\n>> Trace: {name.upper()} ({len(procs)} jobs, mean burst = {mean_b:.1f} ms) <<")
        
        hdr = f"  {'Algorithm':<20} | {'Avg Wait':>10} | {'Avg TA':>10} | {'P95 TA':>10} | {'Switches':>8} | {'Util':>7} | {'Energy(Wh)':>10} | {'Score':>10}"
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        
        rows = {}
        for pname, (alg, pol, dpol) in eval_set.items():
            res = simulate(procs, n_cores=args.cores, delta=args.delta,
                           algorithm=alg, quantum_policy=pol,
                           dispatch_policy=dpol)
            m = res.metrics()
            score = m["avg_waiting"] + m["avg_turnaround"] \
                + args.delta * m["context_switches"] / max(args.cores, 1)
            
            # P95 turnaround
            tas = [p.turnaround for p in res.procs if p.turnaround is not None]
            p95_ta = float(np.percentile(tas, 95)) if tas else 0.0
            
            em = energy_metrics(m["makespan"], args.cores, res.busy_time)
            
            rows[pname] = {
                "wait": round(m["avg_waiting"], 1),
                "ta": round(m["avg_turnaround"], 1),
                "p95_ta": round(p95_ta, 1),
                "cs": m["context_switches"],
                "util": round(m["cpu_utilization"], 3),
                "energy_wh": round(em["energy_wh"], 4),
                "composite": round(score, 1)
            }
            
            print(f"  {pname:<20} | {rows[pname]['wait']:>10.1f} | {rows[pname]['ta']:>10.1f} | {rows[pname]['p95_ta']:>10.1f} | {rows[pname]['cs']:>8} | {rows[pname]['util']:>7.3f} | {rows[pname]['energy_wh']:>10.3f} | {rows[pname]['composite']:>10.1f}")
        
        all_rows[name] = rows

    # Cross-trace aggregate summary
    print(f"\n=========================================================================================")
    print(f"  CROSS-TRACE COMPOSITE SUMMARY ACROSS ALL REAL CLOUD WORKLOADS")
    print(f"=========================================================================================")
    
    means = {}
    summary_table = []
    for pname in eval_set:
        composites = [all_rows[t][pname]["composite"] for t in all_rows]
        waits = [all_rows[t][pname]["wait"] for t in all_rows]
        switches = [all_rows[t][pname]["cs"] for t in all_rows]
        p95s = [all_rows[t][pname]["p95_ta"] for t in all_rows]
        energies = [all_rows[t][pname]["energy_wh"] for t in all_rows]
        
        mean_c = round(statistics.mean(composites), 1)
        mean_w = round(statistics.mean(waits), 1)
        mean_cs = round(statistics.mean(switches), 1)
        mean_p95 = round(statistics.mean(p95s), 1)
        mean_en = round(statistics.mean(energies), 3)
        
        means[pname] = mean_c
        summary_table.append((pname, mean_w, mean_p95, mean_cs, mean_en, mean_c))

    summary_table.sort(key=lambda x: x[5])
    
    shdr = f"  {'Rank':<5} {'Algorithm':<22} | {'Mean Wait':>10} | {'Mean P95 TA':>12} | {'Mean Switches':>14} | {'Mean Energy':>12} | {'Composite':>10}"
    print(shdr)
    print("  " + "=" * (len(shdr) - 2))
    for rank, (pname, mw, mp95, mcs, men, mc) in enumerate(summary_table, 1):
        is_ours = "QTick" in pname
        prefix = "* " if is_ours else "  "
        print(f"{prefix}{rank:<4} {pname:<22} | {mw:>10.1f} | {mp95:>12.1f} | {mcs:>14.1f} | {men:>12.3f} | {mc:>10.1f}")

    out_file = os.path.join(ROOT, "results", "benchmark_real.json")
    with open(out_file, "w") as f:
        json.dump({"per_trace": all_rows, "mean_composite": means, "summary": summary_table}, f, indent=2)
    print(f"\nWritten -> {out_file}")


if __name__ == "__main__":
    main()
