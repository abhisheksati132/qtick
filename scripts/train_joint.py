"""Jointly train the quantum-tuning agent (DQN) AND the dispatch agent (with predictor)."""
import argparse
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.simulator.workload import generate_workload
from src.simulator.scheduler import simulate, QUANTUM_CHOICES
from src.rl.dqn import DQNQuantumAgent
from src.rl.dispatch import RLDispatchAgent
from src.platform.predictor import BurstPredictor
from src.platform.services import ExperimentLog


class AgentPolicy:
    def __init__(self, agent):
        self.agent = agent

    def select_quantum(self, state):
        return QUANTUM_CHOICES[self.agent.act_index(state)]


def train(episodes=500, n_cores=2, delta=1.0, seed0=20000,
          processes=30, verbose_every=50, on_episode=None, agent_hook=None):
    """agent_hook(ep_idx_1based, q_agent, d_agent, predictor): called after
    each episode's updates, used e.g. to snapshot live learning."""
    q_agent = DQNQuantumAgent(hidden=128)
    predictor = BurstPredictor()
    d_agent = RLDispatchAgent(burst_predictor=predictor)
    q_policy = AgentPolicy(q_agent)
    hist = []

    for ep in range(episodes):
        cpu_frac = [0.2, 0.5, 0.8][ep % 3]
        procs = generate_workload(n_processes=processes, seed=seed0 + ep,
                                  cpu_bound_fraction=cpu_frac)
        res = simulate(procs, n_cores=n_cores, delta=delta, algorithm="RR",
                       quantum_policy=q_policy, dispatch_policy=d_agent,
                       collect_rl_trace=True)

        # DQN replay
        trace = res.rl_trace
        for i, step in enumerate(trace):
            nxt = trace[i + 1]["state"] if i + 1 < len(trace) else None
            a_idx = QUANTUM_CHOICES.index(min(QUANTUM_CHOICES,
                                              key=lambda c: abs(c - step["quantum"])))
            q_agent.update(step["state"], a_idx, step["reward"] * 2.0, nxt,
                           terminal=(nxt is None))
        q_agent.end_episode()

        # dispatch agent updated via feedback hooks
        d_agent.end_episode()

        m = res.metrics()
        score = m["avg_waiting"] + m["avg_turnaround"] + delta * m["context_switches"]
        hist.append(score)
        if on_episode:
            on_episode(ep + 1, len(q_agent.q) if hasattr(q_agent, "q") else 0,
                       hist[-1])
        if agent_hook:
            agent_hook(ep + 1, q_agent, d_agent, predictor)
        if verbose_every and (ep + 1) % verbose_every == 0:
            recent = hist[-verbose_every:]
            print(f"episode {ep+1:>4}/{episodes} | eps_q={q_agent.epsilon:.3f} "
                  f"eps_d={d_agent.epsilon:.3f} | composite={statistics.mean(recent):8.2f} "
                  f"| usage={d_agent.usage}")

    return q_agent, d_agent, predictor, hist


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=600)
    ap.add_argument("--cores", type=int, default=2)
    ap.add_argument("--delta", type=float, default=1.0)
    ap.add_argument("--out-q", default="results/dqn_quantum.npz")
    ap.add_argument("--out-d", default="results/qtable_dispatch.pkl")
    ap.add_argument("--out-pred", default="results/burst_predictor.npz")
    args = ap.parse_args()

    qa, da, pred, hist = train(episodes=args.episodes, n_cores=args.cores,
                               delta=args.delta)
    os.makedirs("results", exist_ok=True)
    qa.save(args.out_q)
    da.save(args.out_d)
    pred.save(args.out_pred)
    from src.platform.services import write_training_meta
    write_training_meta(args.episodes, cores=args.cores, delta=args.delta,
                        source="scripts/train_joint.py")
    with open("results/training_history_joint.json", "w") as f:
        json.dump({"composite": hist, "dispatch_usage": da.usage}, f, indent=2)
    print(f"saved quantum Q-table -> {args.out_q}")
    print(f"saved dispatch Q-table -> {args.out_d}")
    print(f"saved burst predictor  -> {args.out_pred}")


if __name__ == "__main__":
    main()