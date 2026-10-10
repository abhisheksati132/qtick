"""Dependency-free DQN (numpy MLP + experience replay + target network).

Drop-in upgrade for the tabular quantum agent: same select_quantum() interface,
but learns over a CONTINUOUS state vector — no bucketing — so it can exploit
real burst distributions.
"""
import random
import numpy as np


class MLP:
    def __init__(self, sizes, seed=0, lr=1e-3):
        rng = np.random.default_rng(seed)
        self.W = [rng.normal(0, np.sqrt(2.0 / sizes[i]), size=(sizes[i], sizes[i+1]))
                  for i in range(len(sizes) - 1)]
        self.b = [np.zeros(sizes[i+1]) for i in range(len(sizes) - 1)]
        self.lr = lr

    def forward(self, x):
        self.cache = [x]
        a = x
        for i in range(len(self.W) - 1):
            z = a @ self.W[i] + self.b[i]
            a = np.maximum(0, z)
            self.cache.append(a)
        return a @ self.W[-1] + self.b[-1]

    def backward(self, grad_out):
        grads_W = [None] * len(self.W)
        grads_b = [None] * len(self.b)
        delta = grad_out
        for i in range(len(self.W) - 1, -1, -1):
            grads_W[i] = self.cache[i].T @ delta
            grads_b[i] = delta.sum(axis=0)
            if i > 0:
                delta = (delta @ self.W[i].T) * (self.cache[i] > 0)
        for i in range(len(self.W)):
            self.W[i] -= self.lr * grads_W[i]
            self.b[i] -= self.lr * grads_b[i]

    def copy_from(self, other):
        self.W = [w.copy() for w in other.W]
        self.b = [b.copy() for b in other.b]


class ReplayBuffer:
    def __init__(self, cap=20000):
        self.cap = cap
        self.buf = []

    def add(self, tr):
        self.buf.append(tr)
        if len(self.buf) > self.cap:
            self.buf.pop(0)

    def sample(self, n, rng):
        idxs = rng.sample(range(len(self.buf)), min(n, len(self.buf)))
        return [self.buf[i] for i in idxs]

    def __len__(self):
        return len(self.buf)


class DQNQuantumAgent:
    """Continuous-state DQN over the quantum ladder.

    state vector (6 dims, log-scaled so heavy-tailed production regimes do
    not saturate the encoding):
      [log1p(mean_remaining)/log1p(2000), min(hetero,4)/4,
       log1p(ready_len)/log1p(200), min(switch_ratio,1),
       recent_preempt_frac, last_quantum/64]
    """

    ACTIONS = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0]

    def __init__(self, gamma=0.6, epsilon=1.0, epsilon_min=0.08,
                 epsilon_decay=0.99, batch=32, sync_every=300, seed=0,
                 hidden=64):
        sizes = [6, hidden, hidden, len(self.ACTIONS)]
        self.hidden = hidden
        self.online = MLP(sizes, seed=seed, lr=5e-4)
        self.target = MLP(sizes, seed=seed + 1)
        self.target.copy_from(self.online)
        self.replay = ReplayBuffer()
        self.gamma, self.batch, self.sync_every = gamma, batch, sync_every
        self.epsilon, self.epsilon_min, self.epsilon_decay = epsilon, epsilon_min, epsilon_decay
        self.rng = random.Random(seed)
        self.steps = 0
        self.loss_ma = None   # moving-average TD-error magnitude (loss curve)
        self._last = None   # (state_vec, action_idx)

    # ---- state encoding -------------------------------------------------
    @staticmethod
    def encode(state, last_quantum=4.0):
        import math
        return np.array([
            math.log1p(max(state.get("mean_remaining_burst", 0.0), 0.0)) / math.log1p(2000.0),
            min(state.get("burst_heterogeneity", 0.0), 4.0) / 4.0,
            math.log1p(max(state.get("ready_len", 0), 0)) / math.log1p(200.0),
            min(state.get("switch_overhead_ratio", 0.0), 1.0),
            min(max(state.get("recent_preempt_fraction", 0.0), 0.0), 1.0),
            min(last_quantum, 64.0) / 64.0,
        ], dtype=np.float64)

    # ---- simulator interface --------------------------------------------
    def select_quantum(self, state):
        s = self.encode(state, self._last_q)
        if self.rng.random() < self.epsilon:
            a = self.rng.randrange(len(self.ACTIONS))
        else:
            a = int(np.argmax(self.online.forward(s[None, :])[0]))
        self._last = (s, a)
        self._last_q = self.ACTIONS[a]
        return self.ACTIONS[a]

    _last_q = 4.0

    def observe_reward(self, reward, next_state=None, terminal=False):
        if self._last is None:
            return
        s, a = self._last
        ns = self.encode(next_state, self._last_q) if next_state is not None \
        else np.zeros(6)
        self.replay.add((s, a, reward, ns, 0.0 if terminal else 1.0))
        self._last = None
        self._train_step()
        self.steps += 1
        if self.steps % self.sync_every == 0:
            self.target.copy_from(self.online)

    def update(self, state, action_idx, reward, next_state=None, terminal=False):
        """Explicit replay transition (offline trace replay — safe when many
        select_quantum calls happened between rewards). Accepts raw state
        dicts (encoded) or pre-encoded vectors."""
        s = state if isinstance(state, np.ndarray) else self.encode(state)
        ns = next_state if isinstance(next_state, np.ndarray) \
            else (self.encode(next_state) if next_state is not None else np.zeros(6))
        self.replay.add((s, action_idx, reward, ns, 0.0 if terminal else 1.0))
        self._train_step()
        self.steps += 1
        if self.steps % self.sync_every == 0:
            self.target.copy_from(self.online)

    def end_episode(self):
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

    # ---- learning ---------------------------------------------------------
    def _train_step(self):
        if len(self.replay) < self.batch:
            return
        batch = self.replay.sample(self.batch, self.rng)
        S = np.stack([b[0] for b in batch])
        A = np.array([b[1] for b in batch])
        R = np.array([b[2] for b in batch], dtype=np.float64)
        NS = np.stack([b[3] for b in batch])
        M = np.array([b[4] for b in batch], dtype=np.float64)
        q_next = self.target.forward(NS).max(axis=1)
        targets = self.online.forward(S)
        targets[np.arange(len(batch)), A] = R + self.gamma * M * q_next
        pred = self.online.forward(S)
        td_err = float(np.abs(pred - targets).mean())
        # moving average of TD error magnitude = the visible "loss curve"
        self.loss_ma = td_err if self.loss_ma is None \
            else 0.95 * self.loss_ma + 0.05 * td_err
        grad = np.clip(pred - targets, -2.0, 2.0) / len(batch)
        self.online.backward(grad)

    # ---- persistence --------------------------------------------------------
    def save(self, path):
        np.savez(path, **{f"W{i}": w for i, w in enumerate(self.online.W)},
                 **{f"b{i}": b for i, b in enumerate(self.online.b)},
                 epsilon=self.epsilon,
                 hidden=np.array([self.hidden]))

    @classmethod
    def load(cls, path):
        d = np.load(path)
        hidden = int(d["hidden"][0]) if "hidden" in d else 64
        obj = cls(hidden=hidden)
        # Evaluation callers override epsilon explicitly; default to greedy
        # floor here so a bare load() never explores unexpectedly.
        n = len(obj.online.W)
        obj.online.W = [d[f"W{i}"] for i in range(n)]
        obj.online.b = [d[f"b{i}"] for i in range(n)]
        obj.target.copy_from(obj.online)
        obj.epsilon = obj.epsilon_min
        return obj

    def snapshot_weights(self):
        return ([w.copy() for w in self.online.W],
                [b.copy() for b in self.online.b])

    def restore_weights(self, snap):
        self.online.W = [w.copy() for w in snap[0]]
        self.online.b = [b.copy() for b in snap[1]]
        self.target.copy_from(self.online)

    def greedy_quantum(self, state):
        s = self.encode(state, self._last_q)
        return self.ACTIONS[int(np.argmax(self.online.forward(s[None, :])[0]))]

    def act_index(self, state):
        s = self.encode(state, self._last_q)
        return int(np.argmax(self.online.forward(s[None, :])[0]))
