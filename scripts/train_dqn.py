"""Train the DQN quantum agent (continuous state) and compare with tabular."""
import argparse
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.simulator.workload import generate_workload
from src.simulator.scheduler import simulate
from src.rl.dqn import DQNQuantumAgent
from src.rl.agent import QLearningAgent
from src.platform.services import ExperimentLog

QUANTA = DQNQuantumAgent.ACTIONS


class DQNPolicy:
    def __init__(self, agent):
        self.agent = agent

    def select_quantum(self, state):
        return self.agent.select_quantum(state)


HELDOUT = list(range(95000, 95015))


def train_dqn(episodes=400, n_cores=2, delta=1.0, seed0=30000, hidden=128,
              eval_every=100):
    agent = DQNQuantumAgent(hidden=hidden)
    pol = DQNPolicy(agent)
    hist = []
    best, best_snap, best_ep = float("inf"), None, 0
    for ep in range(episodes):
        cpu_frac = [0.2, 0.5, 0.8][ep % 3]
        procs = generate_workload(n_processes=30, seed=seed0 + ep,
                                  cpu_bound_fraction=cpu_frac)
        res = simulate(procs, n_cores=n_cores, delta=delta, algorithm="RR",
                       quantum_policy=pol, collect_rl_trace=True)
        trace = res.rl_trace
        for i, step in enumerate(trace):
            nxt = trace[i + 1]["state"] if i + 1 < len(trace) else None
            a_idx = QUANTA.index(min(QUANTA, key=lambda c: abs(c - step["quantum"])))
            # scale rewards ×5 so the TD signal dominates network noise
            agent.update(step["state"], a_idx, step["reward"] * 2.0, nxt,
                         terminal=(nxt is None))
        agent.end_episode()
        m = res.metrics()
        score = m["avg_waiting"] + m["avg_turnaround"] + delta * m["context_switches"]
        hist.append(score)
        if (ep + 1) % 50 == 0:
            print(f"episode {ep+1:>4}/{episodes} | eps={agent.epsilon:.3f} | "
                  f"composite(last50)={statistics.mean(hist[-50:]):8.2f}")
        if eval_every and (ep + 1) % eval_every == 0:
            agent.epsilon, old_eps = 0.0, agent.epsilon
            held = evaluate(DQNPolicy(agent), HELDOUT)
            agent.epsilon = old_eps
            improved = held < best
            if improved:
                best, best_snap, best_ep = held, agent.snapshot_weights(), ep + 1
            print(f"  held-out@{ep+1}: {held:.1f} (best {best:.1f} @ep{best_ep})"
                  f"{' *' if improved else ''}")
    if best_snap is not None:
        agent.restore_weights(best_snap)
        print(f"restored best weights from episode {best_ep} (held-out {best:.1f})")
    return agent, hist


def evaluate(policy, seeds, n_cores=2, delta=1.0):
    rows = []
    for s in seeds:
        procs = generate_workload(n_processes=30, seed=s,
                                  cpu_bound_fraction=[0.2, 0.5, 0.8][s % 3])
        res = simulate(procs, n_cores=n_cores, delta=delta, algorithm="RR",
                       quantum_policy=policy)
        m = res.metrics()
        rows.append(m["avg_waiting"] + m["avg_turnaround"] + delta * m["context_switches"])
    return statistics.mean(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=400)
    ap.add_argument("--hidden", type=int, default=128)
    ap.add_argument("--eval-every", type=int, default=100)
    ap.add_argument("--skip-tabular", action="store_true")
    args = ap.parse_args()

    log = ExperimentLog()

    agent, hist = train_dqn(episodes=args.episodes, hidden=args.hidden,
                            eval_every=args.eval_every)
    agent.epsilon = 0.0
    agent.save("results/dqn_quantum.npz")
    dqn_score = evaluate(DQNPolicy(agent), range(90000, 90030))
    print(f"\nDQN held-out composite: {dqn_score:.2f}")

    results = {"dqn": dqn_score, "dqn_history": hist}
    if not args.skip_tabular and os.path.exists("results/qtable.pkl"):
        tab = QLearningAgent.load("results/qtable.pkl")

        class TabPolicy:
            def select_quantum(self, state):
                return tab.greedy_quantum(state)
        tab_score = evaluate(TabPolicy(), range(90000, 90030))
        results["tabular"] = tab_score
        print(f"Tabular held-out composite: {tab_score:.2f}")

    log.record("dqn-vs-tabular", {"episodes": args.episodes,
                                              "hidden": args.hidden},
               {k: round(v, 2) for k, v in results.items() if isinstance(v, float)},
               tags={"phase": "tier1"})
    with open("results/dqn_history.json", "w") as f:
        json.dump(results, f, indent=2)
    print("saved -> results/dqn_quantum.npz, results/dqn_history.json")


if __name__ == "__main__":
    main()
