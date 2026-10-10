"""Train the Q-learning quantum-tuning agent across synthetic workload episodes."""
import argparse
import json
import statistics
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.simulator.workload import generate_workload
from src.simulator.scheduler import simulate
from src.rl.agent import QLearningAgent, QUANTUM_CHOICES


class AgentPolicy:
    """Thin adapter: simulator asks for a quantum; the agent answers."""

    def __init__(self, agent):
        self.agent = agent

    def select_quantum(self, state):
        return QUANTUM_CHOICES[self.agent.act_index(state)]


def train(episodes=400, n_cores=2, delta=1.0, seed0=1000,
          processes=30, verbose_every=25, on_episode=None, agent_hook=None):
    """agent_hook(ep_idx_1based, agent): called after each episode's update,
    used e.g. to snapshot the live Q-table for visualization."""
    agent = QLearningAgent()
    policy = AgentPolicy(agent)
    rewards_hist = []

    for ep in range(episodes):
        # rotate workload mixes so the agent sees heterogeneous conditions
        cpu_frac = [0.2, 0.5, 0.8][ep % 3]
        procs = generate_workload(n_processes=processes, seed=seed0 + ep,
                                  cpu_bound_fraction=cpu_frac)
        res = simulate(procs, n_cores=n_cores, delta=delta, algorithm="RR",
                       quantum_policy=policy, collect_rl_trace=True)

        total_reward = 0.0
        trace = res.rl_trace
        for i, step in enumerate(trace):
            total_reward += step["reward"]
            a_idx = QUANTUM_CHOICES.index(min(QUANTUM_CHOICES,
                                              key=lambda c: abs(c - step["quantum"])))
            nxt = trace[i + 1]["state"] if i + 1 < len(trace) else None
            agent.update(step["state"], a_idx, step["reward"], nxt)
        agent.end_episode()

        m = res.metrics()
        rewards_hist.append(total_reward / max(len(trace), 1))
        if on_episode:
            on_episode(ep + 1, len(agent.q), rewards_hist[-1])
        if agent_hook:
            agent_hook(ep + 1, agent)
        if verbose_every and (ep + 1) % verbose_every == 0:
            recent = rewards_hist[-verbose_every:]
            print(f"episode {ep+1:>4}/{episodes} | eps={agent.epsilon:.3f} | "
                  f"reward/step={statistics.mean(recent):8.3f} | "
                  f"wait={m['avg_waiting']:7.2f} ta={m['avg_turnaround']:7.2f} "
                  f"cs={m['context_switches']:4d}")

    return agent, rewards_hist


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=400)
    ap.add_argument("--cores", type=int, default=2)
    ap.add_argument("--delta", type=float, default=1.0)
    ap.add_argument("--out", default="results/qtable.pkl")
    args = ap.parse_args()

    agent, hist = train(episodes=args.episodes, n_cores=args.cores, delta=args.delta)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    agent.save(args.out)
    from src.platform.services import write_training_meta
    write_training_meta(args.episodes, tabular_episodes=args.episodes,
                        cores=args.cores, delta=args.delta,
                        source="scripts/train.py")
    with open("results/training_history.json", "w") as f:
        json.dump({"avg_reward_per_step": hist}, f, indent=2)
    print(f"saved Q-table ({len(agent.q)} discretized states) -> {args.out}")


if __name__ == "__main__":
    main()
