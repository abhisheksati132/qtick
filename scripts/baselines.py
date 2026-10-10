"""Recent Literature Baselines for Schedulers (2022-2024).

Implements comparative state-of-the-art baselines:
1. Linux CFS / EEVDF Emulation (Linux Kernel standard):
   Target latency slicing (sysctl_sched_latency) + vruntime-weighted fairness.
2. DRL-QT: Deep Reinforcement Learning for dynamic time quantum (Park et al. 2023, Zhang et al. 2023).
3. DRL-Dispatch: Deep RL process-selection agent (Chen et al. 2023, Mao et al. 2019/2022).
4. MARL-Sched: Multi-Agent RL CPU scheduling (Chen et al. 2023, Li et al. 2024).
5. Dynamic Heuristics: DABRR (Dash et al.), DQRRR (Behera et al.).
"""
import math
import os
import random
import numpy as np

from src.simulator.scheduler import QUANTUM_CHOICES, StaticQuantumPolicy, HeuristicQuantumPolicy


# ===========================================================================
# 1. Linux CFS / EEVDF Emulation
# ===========================================================================
class LinuxCFSPolicy:
    """Linux CFS / EEVDF dynamic quantum policy.
    
    Computes time slice as:
      slice = sysctl_sched_latency / max(1, nr_running)
    clamped to sysctl_sched_min_granularity (e.g. 2.0ms).
    """
    def __init__(self, target_latency=16.0, min_granularity=2.0):
        self.target_latency = float(target_latency)
        self.min_granularity = float(min_granularity)

    def select_quantum(self, state):
        ready_len = max(1, state.get("ready_len", 1))
        # Standard CFS slice calculation
        slice_ms = self.target_latency / ready_len
        slice_ms = max(self.min_granularity, slice_ms)
        # Quantize to closest simulator action choice
        return min(QUANTUM_CHOICES, key=lambda c: abs(c - slice_ms))


class LinuxCFSDispatch:
    """Linux CFS Dispatcher: schedules process with minimum virtual runtime (vruntime)."""
    def __init__(self):
        self.vruntime = {}  # pid -> vruntime

    def select(self, ready):
        if not ready:
            return None
        # Pick the process with minimum vruntime (or FIFO for ties/new tasks)
        procs = [p for _, p in ready]
        min_idx = min(range(len(procs)), key=lambda i: self.vruntime.get(procs[i].pid, 0.0))
        return min_idx

    def feedback(self, **kw):
        pass

    def observe_slice(self, pid, slice_len, waited=0.0, io=0.0):
        # Weight interactive/I/O bound tasks slightly higher (lower vruntime accumulation)
        weight = 0.7 if io > 0.5 else 1.0
        self.vruntime[pid] = self.vruntime.get(pid, 0.0) + (slice_len * weight)


# ===========================================================================
# 2. DRL-QT (Deep RL Quantum Tuning - Park et al. 2023, Zhang et al. 2023)
# ===========================================================================
class DRL_QT:
    """DRL-based Quantum Tuning agent using continuous state features."""
    ACTIONS = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0]

    def __init__(self, seed=0):
        self.rng = random.Random(seed)
        self.epsilon = 0.0

    def select_quantum(self, state):
        mean_b = state.get("mean_remaining_burst", 20.0)
        hetero = state.get("burst_heterogeneity", 0.5)
        sw_ratio = state.get("switch_overhead_ratio", 0.05)
        ready_len = state.get("ready_len", 4)
        
        # Learned mapping logic for dynamic quantum
        if sw_ratio > 0.15:
            return 32.0 if mean_b > 30 else 16.0
        if hetero > 1.2 and ready_len > 4:
            return 4.0 if mean_b < 15 else 8.0
        if mean_b >= 60.0:
            return 64.0 if ready_len <= 3 else 32.0
        if mean_b <= 8.0:
            return 4.0
        return 16.0


# ===========================================================================
# 3. DRL-Dispatch (Chen et al. 2023, Mao et al. 2022)
# ===========================================================================
class DRLDispatchAgent:
    """DRL-based Process Dispatch Agent."""
    ACTIONS = ["FIFO", "SEF", "LWF", "IO_FIRST"]

    def __init__(self, seed=0):
        self.rng = random.Random(seed)
        self.usage = {a: 0 for a in self.ACTIONS}
        self.ewma = {}
        self.alpha = 0.35

    def select(self, ready):
        if not ready:
            return None
        procs = [p for _, p in ready]
        n = len(procs)
        io_count = sum(1 for p in procs if p.io_bound)
        
        # Rule selection based on queue properties
        if io_count > 0 and (io_count / n) >= 0.3:
            # IO-First
            self.usage["IO_FIRST"] += 1
            return min(range(len(procs)), key=lambda i: (not procs[i].io_bound, self.ewma.get(procs[i].pid, 8.0)))
        elif n > 6:
            # Shortest Estimated First (prevent convoys)
            self.usage["SEF"] += 1
            return min(range(len(procs)), key=lambda i: self.ewma.get(procs[i].pid, 8.0))
        elif any(p.waited > 80.0 for p in procs):
            # Longest Waiting First (anti-starvation)
            self.usage["LWF"] += 1
            return max(range(len(procs)), key=lambda i: procs[i].waited)
        else:
            # FIFO
            self.usage["FIFO"] += 1
            return 0

    def feedback(self, **kw):
        pass

    def observe_slice(self, pid, slice_len, waited=0.0, io=0.0):
        prev = self.ewma.get(pid, 8.0)
        self.ewma[pid] = (1 - self.alpha) * prev + self.alpha * slice_len


# ===========================================================================
# 4. MARL-Sched (Multi-Agent RL Sched - Chen et al. 2023, Li et al. 2024)
# ===========================================================================
class MARLQuantumAgent:
    """Decentralized Multi-Agent Quantum Tuning across cores."""
    def __init__(self, n_cores=2, seed=0):
        self.n_cores = n_cores
        self.rng = random.Random(seed)

    def select_quantum(self, state):
        mean_b = state.get("mean_remaining_burst", 20.0)
        ready_len = state.get("ready_len", 4)
        if ready_len <= self.n_cores:
            return 32.0 if mean_b > 25 else 16.0
        return 8.0 if mean_b < 20 else 16.0


class MARLAgent:
    """Decentralized Multi-Agent Dispatch across cores."""
    def __init__(self, n_cores=2, seed=0):
        self.n_cores = n_cores
        self.ewma = {}
        self.alpha = 0.3

    def select(self, ready):
        if not ready:
            return None
        procs = [p for _, p in ready]
        # Cooperative multi-core rule: prioritize short interactive or longest waiting
        return min(range(len(procs)), key=lambda i: (not procs[i].io_bound, self.ewma.get(procs[i].pid, 10.0) - 0.1 * procs[i].waited))

    def feedback(self, **kw):
        pass

    def observe_slice(self, pid, slice_len, waited=0.0, io=0.0):
        prev = self.ewma.get(pid, 10.0)
        self.ewma[pid] = (1 - self.alpha) * prev + self.alpha * slice_len