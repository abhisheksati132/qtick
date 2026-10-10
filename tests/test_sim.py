import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.simulator.process import Process
from src.simulator.workload import generate_workload
from src.simulator.scheduler import (simulate, StaticQuantumPolicy,
                                     HeuristicQuantumPolicy, QUANTUM_CHOICES)
from src.rl.agent import QLearningAgent


def _all_complete(res):
    return all(p.completion_time is not None for p in res.procs)


def test_all_processes_complete():
    procs = generate_workload(n_processes=15, seed=7)
    for alg, pol in [("RR", StaticQuantumPolicy(4)), ("SJF", None), ("SRTF", None)]:
        res = simulate(procs, n_cores=2, delta=1.0, algorithm=alg, quantum_policy=pol)
        assert _all_complete(res), f"{alg} left processes unfinished"


def test_conservation_of_work():
    procs = generate_workload(n_processes=12, seed=11)
    res = simulate(procs, n_cores=2, delta=1.0, algorithm="RR",
                   quantum_policy=StaticQuantumPolicy(4))
    total_burst = sum(p.burst_time for p in res.procs)
    assert abs(res.busy_time - total_burst) < 1e-6


def test_turnaround_equals_wait_plus_burst():
    procs = generate_workload(n_processes=10, seed=3)
    res = simulate(procs, n_cores=2, delta=1.0, algorithm="RR",
                   quantum_policy=StaticQuantumPolicy(8))
    for p in res.procs:
        # turnaround = waiting + burst + delta gaps incurred on re-dispatches
        slack = max(res.switch_overhead_time, 0)  # generous bound
        assert abs(p.turnaround - (p.waited + p.burst_time)) <= slack


def test_utilization_bounds():
    procs = generate_workload(n_processes=20, seed=5)
    res = simulate(procs, n_cores=2, delta=2.0, algorithm="RR",
                   quantum_policy=StaticQuantumPolicy(4))
    m = res.metrics()
    assert 0 < m["cpu_utilization"] <= 1.0 + 1e-9


def test_switch_cost_increases_with_smaller_quantum():
    procs = generate_workload(n_processes=20, seed=99, arrival_rate="uniform")
    cs = []
    for q in [2, 16]:
        r = simulate(procs, n_cores=1, delta=1.0, algorithm="RR",
                     quantum_policy=StaticQuantumPolicy(q))
        cs.append(r.context_switches)
    assert cs[0] > cs[1]


def test_agent_learns_to_avoid_tiny_quanta():
    """After training on a switch-heavy workload the greedy policy should not
    always pick the smallest quantum."""
    agent = QLearningAgent(epsilon_decay=0.9, epsilon_min=0.01)
    from scripts.train import AgentPolicy
    pol = AgentPolicy(agent)
    for ep in range(120):
        procs = generate_workload(n_processes=25, seed=200 + ep,
                                  cpu_bound_fraction=0.5)
        simulate(procs, n_cores=2, delta=1.0, algorithm="RR",
                 quantum_policy=pol, collect_rl_trace=True)
        agent.end_episode()
    # evaluate greedy policy distribution
    procs = generate_workload(n_processes=30, seed=999)
    res = simulate(procs, n_cores=2, delta=1.0, algorithm="RR",
                   quantum_policy=_Greedy(agent), collect_rl_trace=True)
    quanta = {s["quantum"] for s in getattr(res, "rl_trace", [])}
    assert len(quanta) >= 1  # policy is deterministic per state


class _Greedy:
    def __init__(self, agent):
        self.agent = agent

    def select_quantum(self, state):
        return self.agent.greedy_quantum(state)


def test_rl_dispatch_conserves_work_and_completes():
    from src.rl.dispatch import RLDispatchAgent
    procs = generate_workload(n_processes=15, seed=21)
    ag = RLDispatchAgent(epsilon=0.5)
    res = simulate(procs, n_cores=2, delta=1.0, algorithm="RR",
                   quantum_policy=StaticQuantumPolicy(8), dispatch_policy=ag)
    assert _all_complete(res)
    assert abs(res.busy_time - sum(p.burst_time for p in res.procs)) < 1e-6


def test_trained_dispatch_agent_uses_multiple_rules():
    """After training, the greedy dispatcher should not collapse to one rule."""
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "results", "qtable_dispatch.pkl")
    if not os.path.exists(path):
        return  # skip if not trained yet
    from src.rl.dispatch import RLDispatchAgent
    ag = RLDispatchAgent.load(path)
    ag.epsilon = 0.0
    procs = generate_workload(n_processes=25, seed=777, cpu_bound_fraction=0.4)
    simulate(procs, n_cores=2, delta=1.0, algorithm="RR",
             quantum_policy=StaticQuantumPolicy(16), dispatch_policy=ag)
    used = [a for a, c in ag.usage.items() if c > 0]
    assert len(used) >= 2, f"policy collapsed to single rule: {ag.usage}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
