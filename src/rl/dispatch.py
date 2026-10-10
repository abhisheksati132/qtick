"""RL-based process-selection (dispatch) agent with neural burst predictor.

Two layers of "previous data" drive the decision:
  1. Per-process burst estimation — an exponentially-weighted moving average of
     every slice a process has executed so far predicts how much CPU it needs
     next (classic exponential averaging, but consumed by a learner).
  2. A tabular Q-learning agent that, given the aggregate queue situation,
     selects WHICH dispatch rule to apply this epoch:
       a0 FIFO            – classic Round Robin order
       a1 SEF             – shortest estimated burst first
       a2 LWF             – longest waiting first (aging)
       a3 IO_FIRST        – I/O-bound processes first, then SEF
"""
import random


def _buckets(value, edges):
    for i, e in enumerate(edges):
        if value < e:
            return i
    return len(edges)


class BurstEstimator:
    def __init__(self, alpha=0.35, default=8.0):
        self.alpha, self.default = alpha, default
        self.est = {}

    def observe(self, pid, slice_len):
        prev = self.est.get(pid, self.default)
        self.est[pid] = (1 - self.alpha) * prev + self.alpha * slice_len

    def get(self, pid):
        return self.est.get(pid, self.default)


class RLDispatchAgent:
    ACTIONS = ["FIFO", "SEF", "LWF", "IO_FIRST"]

    def __init__(self, alpha=0.12, gamma=0.9, epsilon=1.0,
                 epsilon_min=0.05, epsilon_decay=0.995, seed=0,
                 burst_predictor=None):
        self.q = {}
        self.alpha, self.gamma = alpha, gamma
        self.epsilon, self.epsilon_min, self.epsilon_decay = \
            epsilon, epsilon_min, epsilon_decay
        self.rng = random.Random(seed)
        self.usage = {a: 0 for a in self.ACTIONS}
        self._pending = None
        self._last_outcome = None
        self.predictor = burst_predictor
        self.est = BurstEstimator()   # fallback EWMA if no predictor

    def _state(self, ready):
        if not ready:
            return None
        procs = [p for _, p in ready]
        n = len(procs)
        waits = [p.waited for p in procs]
        ests = [self.predictor.estimate(p.pid) if self.predictor
                else self.est.get(p.pid) for p in procs]
        mean_w = sum(waits) / n
        mean_e = sum(ests) / n
        var_e = sum((e - mean_e) ** 2 for e in ests) / n
        hetero = (var_e ** 0.5 / mean_e) if mean_e > 0 else 0.0
        return (
            _buckets(mean_w, [10, 40, 120]),
            _buckets(hetero, [0.35, 0.9]),
            _buckets(n, [2, 5, 10]),
            _buckets(sum(1 for p in procs if p.io_bound) / n, [0.25, 0.6]),
        )

    def select(self, ready):
        if not ready:
            return None
        s = self._state(ready)

        if self._pending is not None and self._last_outcome is not None:
            ps, pa = self._pending
            r = self._last_outcome["reward"]
            target = r + self.gamma * max(self._values(s))
            vals = self._values(ps)
            vals[pa] += self.alpha * (target - vals[pa])
        self._pending = (s, None)
        self._last_outcome = None

        a = self._act(s)
        self._pending = (s, a)
        self.usage[self.ACTIONS[a]] += 1

        procs = [p for _, p in ready]
        if a == 0:
            idx = 0
        elif a == 1:
            idx = min(range(len(procs)), key=lambda i:
                      self.predictor.estimate(procs[i].pid) if self.predictor
                      else self.est.get(procs[i].pid))
        elif a == 2:
            idx = max(range(len(procs)), key=lambda i: procs[i].waited)
        else:
            idx = min(range(len(procs)),
                      key=lambda i: (not procs[i].io_bound,
                                     self.predictor.estimate(procs[i].pid)
                                     if self.predictor else self.est.get(procs[i].pid)))
        return idx

    def feedback(self, *, completed, switched, slice_len, min_other_remaining):
        if self._pending is None:
            return
        r = (3.0 * (1.0 if completed else 0.0)
             - 1.0 * (1.0 if switched else 0.0)
             - 0.03 * max(0.0, slice_len - min_other_remaining))
        self._last_outcome = {"reward": r}

    def observe_slice(self, pid, slice_len, waited=0.0, io=0.0):
        if self.predictor:
            self.predictor.observe(pid, slice_len, waited, io)
        else:
            self.est.observe(pid, slice_len)

    def end_episode(self):
        if self._pending is not None and self._last_outcome is not None:
            s, a = self._pending
            if a is not None:
                vals = self._values(s)
                vals[a] += self.alpha * (self._last_outcome["reward"] - vals[a])
        self._pending = None
        self._last_outcome = None
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

    def _values(self, s):
        if s not in self.q:
            self.q[s] = [0.0] * len(self.ACTIONS)
        return self.q[s]

    def _act(self, s):
        if self.rng.random() < self.epsilon:
            return self.rng.randrange(len(self.ACTIONS))
        vals = self._values(s)
        best = max(vals)
        return self.rng.choice([i for i, v in enumerate(vals) if v == best])

    def save(self, path):
        import pickle
        with open(path, "wb") as f:
            pickle.dump({"q": self.q, "epsilon": self.epsilon,
                         "est": self.est.est}, f)

    @classmethod
    def load(cls, path):
        import pickle
        obj = cls()
        with open(path, "rb") as f:
            d = pickle.load(f)
        obj.q = d["q"]
        # Always serve greedy: the epsilon stored in the file is the
        # exploration rate at save time (e.g. mid-training), which must
        # never leak into evaluation. Nothing resumes training from disk.
        obj.epsilon = obj.epsilon_min
        obj.est.est = d.get("est", {})
        return obj