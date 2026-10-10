"""Fine-tune agents on REAL traces (continual-learning story).

Mixes synthetic episodes with sliding windows sampled from the real
PWA traces, so the agents adapt to heavy-tailed bursts and bursty
arrivals they never saw in synthetic training.

Run:  python scripts/finetune_real.py --episodes 200
Saves: results/dqn_quantum.npz, results/qtable_dispatch.pkl (backed up first)
"""
import argparse
import glob
import os
import shutil
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.simulator.workload import generate_workload
from src.simulator.scheduler import simulate, QUANTUM_CHOICES
from src.platform.predictor import load_trace, BurstPredictor
from src.rl.dqn import DQNQuantumAgent
from src.rl.dispatch import RLDispatchAgent

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "results")


class DQNPolicy:
    def __init__(self, agent):
        self.agent = agent
    def select_quantum(self, state):
        return DQNQuantumAgent.ACTIONS[self.agent.act_index(state)]


def real_windows(trace_dir, window=80, stride=40, max_windows=12):
    wins = []
    # Prioritize modern cloud traces
    csv_files = [fp for fp in sorted(glob.glob(os.path.join(trace_dir, "*.csv")))
                 if any(k in os.path.basename(fp) for k in ["alibaba", "google", "azure"])]
    if not csv_files:
        csv_files = sorted(glob.glob(os.path.join(trace_dir, "*.csv")))
        
    for fp in csv_files:
        procs = load_trace(fp)
        for s in range(0, max(1, len(procs) - window), stride):
            chunk = procs[s:s + window]
            t0 = chunk[0].arrival_time
            for p in chunk:
                p.arrival_time -= t0
                p.remaining_time = p.burst_time
                p.waited = 0.0
                p.start_time = None
                p.completion_time = None
                p.executed_slices = 0
            wins.append(chunk)
            if len(wins) >= max_windows:
                break
    return wins


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=200)
    ap.add_argument("--cores", type=int, default=2)
    ap.add_argument("--delta", type=float, default=1.0)
    ap.add_argument("--blocking-w", type=float, default=0.03,
                    help="head-of-line blocking penalty weight "
                         "(raise on heavy-tailed traces, e.g. 0.15)")
    args = ap.parse_args()

    # backup current models
    for f in ["dqn_quantum.npz", "qtable_dispatch.pkl", "burst_predictor.npz"]:
        src = os.path.join(RES, f)
        if os.path.exists(src):
            shutil.copy(src, src + ".pre_real.bak")
            print("backed up", f)

    dqn = DQNQuantumAgent.load(os.path.join(RES, "dqn_quantum.npz"))
    dqn.epsilon = 0.35
    disp = RLDispatchAgent.load(os.path.join(RES, "qtable_dispatch.pkl"))
    disp.predictor = BurstPredictor()
    try:
        disp.predictor.load(os.path.join(RES, "burst_predictor.npz"))
    except Exception:
        pass
    disp.epsilon = 0.35
    pol = DQNPolicy(dqn)

    wins = real_windows(os.path.join(ROOT, "traces", "real"))
    print(f"{len(wins)} real windows loaded")
    hist = []
    for ep in range(args.episodes):
        if ep % 2 == 0 or not wins:
            procs = generate_workload(n_processes=30, seed=60000 + ep,
                                      cpu_bound_fraction=[0.2, 0.5, 0.8][ep % 3])
        else:
            import copy
            procs = copy.deepcopy(wins[ep % len(wins)])
        res = simulate(procs, n_cores=args.cores, delta=args.delta,
                       algorithm="RR", quantum_policy=pol,
                       dispatch_policy=disp, collect_rl_trace=True,
                       reward_weights=(3.0, 1.0, args.blocking_w))
        trace = res.rl_trace
        for i, step in enumerate(trace):
            nxt = trace[i + 1]["state"] if i + 1 < len(trace) else None
            a_idx = QUANTUM_CHOICES.index(min(QUANTUM_CHOICES,
                                              key=lambda c: abs(c - step["quantum"])))
            dqn.update(step["state"], a_idx, step["reward"] * 5.0, nxt,
                       terminal=(nxt is None))
        dqn.end_episode()
        disp.end_episode()
        m = res.metrics()
        hist.append(m["avg_waiting"] + m["avg_turnaround"]
                    + args.delta * m["context_switches"])
        if (ep + 1) % 25 == 0:
            print(f"episode {ep+1:>4}/{args.episodes} | eps={dqn.epsilon:.3f} | "
                  f"composite(last25)={statistics.mean(hist[-25:]):8.2f}")

    dqn.save(os.path.join(RES, "dqn_quantum.npz"))
    disp.save(os.path.join(RES, "qtable_dispatch.pkl"))
    disp.predictor.save(os.path.join(RES, "burst_predictor.npz"))
    from src.platform.services import write_training_meta
    write_training_meta(args.episodes, cores=args.cores, delta=args.delta,
                        source="scripts/finetune_real.py")
    print("fine-tuned models saved (old ones kept as *.pre_real.bak)")


if __name__ == "__main__":
    main()
