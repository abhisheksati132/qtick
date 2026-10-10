"""Discrete-event multiprocessing CPU simulator.

Supports Round Robin with a pluggable quantum-selection policy (static value,
heuristic, or RL agent), plus SJF and SRTF baselines. Every inter-process
switch on a core charges an explicit context-switch overhead (delta).
"""
import copy
from collections import deque

QUANTUM_CHOICES = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0]


class SimResult:
    def __init__(self):
        self.procs = []
        self.context_switches = 0
        self.switch_overhead_time = 0.0
        self.makespan = 0.0
        self.busy_time = 0.0          # time cores spent executing user work
        self.n_cores = 1
        self.rl_trace = []
        self.timeline = []            # (core, start, end, pid) execution intervals

    @property
    def cpu_utilization(self):
        denom = self.makespan * self.n_cores
        return self.busy_time / denom if denom > 0 else 0.0

    def metrics(self):
        done = [p for p in self.procs if p.completion_time is not None]
        n = max(len(done), 1)
        return {
            "avg_waiting": sum(p.waited for p in done) / n,
            "avg_turnaround": sum(p.turnaround for p in done) / n,
            "avg_response": sum(
                (p.start_time - p.arrival_time)
                for p in done if p.start_time is not None
            ) / n,
            "context_switches": self.context_switches,
            "switch_overhead_time": self.switch_overhead_time,
            "cpu_utilization": self.cpu_utilization,
            "makespan": self.makespan,
        }


def simulate(procs, n_cores=2, delta=1.0, algorithm="RR", quantum_policy=None,
             reward_weights=(3.0, 1.0, 0.03, 0.0), collect_rl_trace=False,
             max_steps=500000, dispatch_policy=None):
    """Run the simulation.

    quantum_policy  : object with select_quantum(state) -> float (RR only)
    dispatch_policy : object with select(ready) -> index (AI process selection)
    algorithm       : "RR" | "SJF" | "SRTF"
    delta           : context-switch overhead charged on every inter-process switch
    reward_weights  : (completion_w, switch_w, blocking_w[, queue_w])

    Queue-delay term (4th weight): penalizes queued×slice per decision. Use with
    care — a weight ≥0.005 collapses learning to tiny quanta (switch storm),
    while ≤0.001 leaves heavy-tail regimes untouched; see results/reward_search.json.
    Default 0.0 (blocking term alone carries the anti-convoy signal).
    """
    W_DONE, W_SWITCH, W_BLOCK = reward_weights[:3]
    W_QUEUE = reward_weights[3] if len(reward_weights) > 3 else 0.0
    if not procs:
        return SimResult()
    ps = [copy.copy(p) for p in procs]
    ps.sort(key=lambda x: x.arrival_time)

    res = SimResult()
    res.n_cores = n_cores
    res.procs = ps

    ready = []           # list of (seq, proc), kept sorted by seq -> FIFO order
    seq = 0
    ai = 0
    total = len(ps)

    free_at = [ps[0].arrival_time] * n_cores
    last_pid = [None] * n_cores
    recent_switch_time = [0.0] * n_cores
    recent_exec_time = [0.0] * n_cores
    preempt_history = deque(maxlen=10)

    cur_t = ps[0].arrival_time if ps else 0.0
    requeues = []        # (ready_time, seq, proc)
    rl_trace = []
    steps = 0

    def admit(upto):
        nonlocal ai, seq
        while ai < total and ps[ai].arrival_time <= upto:
            p = ps[ai]
            p.waited += upto - p.arrival_time
            ready.append((seq, p))
            seq += 1
            ai += 1

    def pick_index():
        if not ready:
            return None
        if dispatch_policy is not None and algorithm == "RR":
            return dispatch_policy.select(ready)
        if algorithm == "SJF":
            return min(range(len(ready)), key=lambda i: ready[i][1].burst_time)
        if algorithm == "SRTF":
            return min(range(len(ready)), key=lambda i: ready[i][1].remaining_time)
        return 0

    def build_state():
        if ready:
            bursts = [rp[1].remaining_time for rp in ready]
            mean_b = sum(bursts) / len(bursts)
            var_b = sum((b - mean_b) ** 2 for b in bursts) / len(bursts)
            hetero = (var_b ** 0.5 / mean_b) if mean_b > 0 else 0.0
        else:
            mean_b, hetero = 0.0, 0.0
        sw_denom = sum(recent_exec_time) + sum(recent_switch_time)
        sw_ratio = sum(recent_switch_time) / sw_denom if sw_denom > 0 else 0.0
        preempt_frac = sum(preempt_history) / len(preempt_history) if preempt_history else 0.0
        return {
            "mean_remaining_burst": mean_b,
            "burst_heterogeneity": hetero,
            "ready_len": len(ready),
            "switch_overhead_ratio": sw_ratio,
            "recent_preempt_fraction": preempt_frac,
        }

    while ai < total or ready or requeues:
        steps += 1
        if steps > max_steps:
            raise RuntimeError("simulation failed to terminate")

        admit(cur_t)

        # release preempted processes whose slice ended at/before cur_t
        due = [r for r in requeues if r[0] <= cur_t]
        if due:
            for _, s, p in sorted(due, key=lambda r: r[1]):
                ready.append((s, p))
                seq = max(seq, s + 1)
            requeues = [r for r in requeues if r[0] > cur_t]
            ready.sort(key=lambda x: x[0])

        # dispatch on every free core.
        # NOTE: the free-core check MUST come first: pick_index() may invoke
        # a learning dispatch policy with side effects (TD updates, usage
        # counters) that must only fire for decisions actually taken.
        for c in range(n_cores):
            if free_at[c] > cur_t:
                continue
            idx = pick_index()
            if idx is None:
                continue
            _, p = ready.pop(idx)
            start_exec = max(free_at[c], cur_t)

            switched = last_pid[c] is not None
            switch_cost = delta if switched else 0.0
            exec_start = start_exec + switch_cost

            state = build_state()
            if algorithm == "RR":
                q = quantum_policy.select_quantum(state) if quantum_policy else 4.0
                slice_len = min(q, p.remaining_time)
            else:                       # SJF / SRTF: run until done or better arrival
                if algorithm == "SRTF" and ai < total:
                    next_arr = ps[ai].arrival_time
                    slice_len = min(p.remaining_time, max(next_arr - exec_start, 1e-9))
                    slice_len = p.remaining_time if next_arr >= exec_start + p.remaining_time \
                        else slice_len
                else:
                    slice_len = p.remaining_time

            p.executed_slices += 1
            if p.start_time is None:
                p.start_time = exec_start

            will_finish = slice_len >= p.remaining_time - 1e-9
            p.remaining_time -= slice_len
            end = exec_start + slice_len

            # core bookkeeping
            free_at[c] = end
            if switched:
                res.context_switches += 1
                res.switch_overhead_time += switch_cost
                recent_switch_time[c] = 0.9 * recent_switch_time[c] + switch_cost
                recent_exec_time[c] *= 0.9
            recent_exec_time[c] = 0.9 * recent_exec_time[c] + slice_len
            res.busy_time += slice_len
            res.timeline.append((c, exec_start, end, p.pid))

            if will_finish:
                p.remaining_time = 0.0
                p.completion_time = end
                last_pid[c] = None
                preempt_history.append(0.0)
            else:
                preempt_history.append(1.0)
                requeues.append((end, seq, p))
                seq += 1
                last_pid[c] = p.pid

            if dispatch_policy is not None:
                waiting_rems = [rp[1].remaining_time for rp in ready]
                min_rem = min(waiting_rems) if waiting_rems else slice_len
                dispatch_policy.feedback(completed=will_finish, switched=switched,
                                         slice_len=slice_len,
                                         min_other_remaining=min_rem)
                # waited/io must be passed through: the burst predictor's
                # waited and io_bound features are otherwise always zero.
                dispatch_policy.observe_slice(p.pid, slice_len, p.waited,
                                              float(p.io_bound))

            if collect_rl_trace and algorithm == "RR":
                # Reward shaping:
                #  + complete a process inside one slice (efficient service)
                #  - pay for each context switch (discourage tiny quanta)
                #  - pay for head-of-line blocking: running longer than the
                #    shortest remaining burst waiting in queue
                #  - pay queue-delay: every queued process waits through this
                #    slice (matters when all queued jobs are large, i.e. no
                #    blocking signal exists — the heavy-tail regime)
                waiting_rems = [rp[1].remaining_time for rp in ready]
                min_rem = min(waiting_rems) if waiting_rems else float("inf")
                blocking = max(0.0, slice_len - min_rem) if min_rem != float("inf") else 0.0
                reward = (W_DONE * (1.0 if will_finish else 0.0)
                          - W_SWITCH * (1.0 if switched else 0.0)
                          - W_BLOCK * blocking
                          - W_QUEUE * len(ready) * slice_len)
                rl_trace.append({"state": state, "quantum": q, "reward": reward,
                                 "completed": will_finish})

        # advance global clock to the next event
        candidates = [f for f in free_at if f > cur_t]
        if ai < total:
            candidates.append(ps[ai].arrival_time)
        if requeues:
            candidates.append(min(r[0] for r in requeues))
        if not candidates:
            break  # nothing left to wait for
        nxt = max(cur_t + 1e-12, min(candidates))
        dt = nxt - cur_t
        if dt > 0:
            for _, rp in ready:
                rp.waited += dt
        cur_t = nxt

    res.makespan = max([cur_t] + list(free_at))
    res.rl_trace = rl_trace
    return res


class StaticQuantumPolicy:
    def __init__(self, q):
        self.q = float(q)

    def select_quantum(self, state):
        return self.q


class HeuristicQuantumPolicy:
    """DABRR-style heuristic: quantum = mean remaining burst of the ready queue."""

    def select_quantum(self, state):
        m = state["mean_remaining_burst"]
        return max(1.0, min(m, QUANTUM_CHOICES[-1]))


def quantize_q(q):
    return min(QUANTUM_CHOICES, key=lambda c: abs(c - q))
