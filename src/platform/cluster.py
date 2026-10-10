"""Multi-node cluster scheduler — mini-DeepRM with tabular Q-learning.

Jobs with (cpu, mem, duration) demands arrive at a cluster of homogeneous
nodes. A Q-learning agent assigns each job to a node (or defers it), learning
to balance load and avoid fragmentation. Time-stepped simulation.
"""
import random
from collections import deque

ACTIONS_DEFER = -1


class Node:
    def __init__(self, cpu, mem):
        self.cpu_cap, self.mem_cap = cpu, mem
        self.cpu_used = 0.0
        self.mem_used = 0.0

    @property
    def cpu_free(self): return self.cpu_cap - self.cpu_used
    @property
    def mem_free(self): return self.mem_cap - self.mem_used

    def fits(self, job):
        return job["cpu"] <= self.cpu_free and job["mem"] <= self.mem_free

    def place(self, job):
        self.cpu_used += job["cpu"]; self.mem_used += job["mem"]

    def release(self, job):
        self.cpu_used -= job["cpu"]; self.mem_used -= job["mem"]


class QClusterAgent:
    """State: (cluster load level, queue length, job size class) -> node index / defer."""

    def __init__(self, n_nodes, alpha=0.1, gamma=0.9, epsilon=0.3,
                 epsilon_min=0.03, seed=0):
        self.n = n_nodes
        self.alpha, self.gamma = alpha, gamma
        self.epsilon, self.eps_min, self.eps_decay = epsilon, epsilon_min, 0.99
        self.rng = random.Random(seed)
        self.q = {}
        self.usage = {f"node{i}": 0 for i in range(n_nodes)}
        self.usage["defer"] = 0
        self._last = None

    def _bucket(self, v, edges):
        for i, e in enumerate(edges):
            if v < e:
                return i
        return len(edges)

    def state(self, cluster_load, queue_len, job_cpu_frac):
        return (self._bucket(cluster_load, [0.3, 0.6, 0.85]),
                self._bucket(queue_len, [1, 4, 8]),
                self._bucket(job_cpu_frac, [0.15, 0.4, 0.7]))

    def _vals(self, s):
        return self.q.setdefault(s, [0.0] * (self.n + 1))

    @staticmethod
    def _slot(a, n):
        # defer (-1) lives in the last slot; explicit mapping instead of
        # relying on Python negative indexing (fragile and unreadable).
        return n if a == ACTIONS_DEFER else a

    def act(self, s, feasible):
        """feasible: list of node indices that fit; defer always allowed."""
        candidates = list(feasible) + [ACTIONS_DEFER]
        if self.rng.random() < self.epsilon:
            return self.rng.choice(candidates)
        vals = self._vals(s)
        best = max(vals[self._slot(i, self.n)] for i in candidates)
        choices = [i for i in candidates
                   if vals[self._slot(i, self.n)] == best]
        return self.rng.choice(choices)

    def learn(self, s, a, r, ns):
        slot = self._slot(a, self.n)
        target = r + self.gamma * max(self._vals(ns))
        vals = self._vals(s)
        vals[slot] += self.alpha * (target - vals[slot])

    def end_episode(self):
        self.epsilon = max(self.eps_min, self.epsilon * self.eps_decay)


def simulate_cluster(jobs, n_nodes=4, cpu_per_node=16, mem_per_node=32,
                     agent=None, seed=0):
    """jobs: list of dicts {arrival, cpu, mem, duration}. Returns metrics."""
    agent = agent or QClusterAgent(n_nodes, seed=seed)
    jobs = sorted(jobs, key=lambda j: j["arrival"])
    for jb in jobs:
        if jb["cpu"] > cpu_per_node or jb["mem"] > mem_per_node:
            raise ValueError(f"job {jb} exceeds empty-node capacity "
                             f"({cpu_per_node} cpu, {mem_per_node} mem)")
    nodes = [Node(cpu_per_node, mem_per_node) for _ in range(n_nodes)]
    queue = deque()
    running = []          # (finish_time, node_idx, job)
    t = 0.0
    i = 0
    total = len(jobs)
    done = 0
    wait_sum = 0.0
    busy_node_time = 0.0
    guard = 0

    def cluster_load():
        cap = n_nodes * cpu_per_node
        return sum(nd.cpu_used for nd in nodes) / max(cap, 1)

    while done < total:
        guard += 1
        if guard > 400000:
            raise RuntimeError("cluster simulation stalled")
        # admit arrivals
        while i < total and jobs[i]["arrival"] <= t:
            queue.append(jobs[i]); i += 1
        # finish finished
        still = []
        for ft, ni, jb in running:
            if ft <= t:
                nodes[ni].release(jb); done += 1
                # node-time actually consumed = duration × cpu fraction
                busy_node_time += jb["duration"] * jb["cpu"] / cpu_per_node
            else:
                still.append((ft, ni, jb))
        running = still

        # dispatch loop
        progressed = True
        while progressed and queue:
            progressed = False
            job = queue[0]
            s = agent.state(cluster_load(), len(queue), job["cpu"] / cpu_per_node)
            feasible = [k for k, nd in enumerate(nodes) if nd.fits(job)]
            a = agent.act(s, feasible)
            if a == ACTIONS_DEFER:
                if not running and i >= total:
                    # Nothing running and nothing arriving: idling would
                    # deadlock (no future event exists), so force placement.
                    a = feasible[0]
                else:
                    # Deferral is a real decision and must receive a learning
                    # signal too (previously it got none): waiting costs a
                    # tick, so the agent learns to defer only when patience
                    # pays off.
                    agent.learn(s, a, -0.05 * (1 + len(queue)), s)
                    agent.usage["defer"] += 1
                    break   # wait for capacity; time will advance
            # reward: negative load imbalance created + queue relief
            load_before = max(nd.cpu_used / cpu_per_node for nd in nodes)
            queue.popleft()
            nodes[a].place(job)
            load_after = max(nd.cpu_used / cpu_per_node for nd in nodes)
            r = 1.0 - (load_after - load_before) - 0.1 * len(queue)
            ns = agent.state(cluster_load(), len(queue), job["cpu"] / cpu_per_node)
            agent.learn(s, a, r, ns)
            agent.usage[f"node{a}"] += 1
            job = dict(job); job["start"] = t
            wait_sum += t - job["arrival"]
            running.append((t + job["duration"], a, job))
            progressed = True

        # advance time
        cands = [jobs[i]["arrival"]] if i < total else []
        cands += [ft for ft, _, _ in running]
        if not cands:
            break
        t = max(t + 1e-9, min(cands))

    makespan = t
    util = busy_node_time / (makespan * n_nodes) if makespan > 0 else 0
    return {"makespan": round(makespan, 2),
            "avg_wait": round(wait_sum / max(total, 1), 3),
            "completed": done, "total": total,
            "cpu_utilization": round(util, 3),
            "placement_usage": agent.usage}


def generate_cluster_jobs(n=120, seed=0, n_nodes=4):
    rng = random.Random(seed)
    jobs = []
    t = 0.0
    for _ in range(n):
        t += rng.expovariate(1.0 / 2.0)
        jobs.append({"arrival": t,
                     "cpu": rng.choice([1, 2, 4, 8]),
                     "mem": rng.choice([2, 4, 8, 16]),
                     "duration": max(1.0, rng.gammavariate(2, 6))})
    return jobs
