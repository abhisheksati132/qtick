"""Tabular Q-learning agent for RR quantum tuning.

State features are discretized into buckets; actions are the discrete
quantum choices. Off-policy updates follow Watkins & Dayan [Watkins & Dayan, 1992].
"""
import random

QUANTUM_CHOICES = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0]


def _buckets(value, edges):
    for i, e in enumerate(edges):
        if value < e:
            return i
    return len(edges)


class Discretizer:
    """Maps the continuous simulator state dict to a tabular state index."""

    def __init__(self):
        self.burst_edges = [5.0, 20.0, 60.0]              # mean remaining burst
        self.hetero_edges = [0.35, 0.9]                   # std/mean of bursts
        self.len_edges = [2, 5, 10]                       # ready-queue length
        self.switch_edges = [0.05, 0.2]                   # overhead time ratio
        self.preempt_edges = [0.4, 0.8]                   # recent preemption rate

    def index(self, s):
        f = (
            _buckets(s["mean_remaining_burst"], self.burst_edges),
            _buckets(s["burst_heterogeneity"], self.hetero_edges),
            _buckets(s["ready_len"], self.len_edges),
            _buckets(s["switch_overhead_ratio"], self.switch_edges),
            _buckets(s["recent_preempt_fraction"], self.preempt_edges),
        )
        return f


class QLearningAgent:
    def __init__(self,
                 actions=None,
                 alpha=0.1,
                 gamma=0.9,
                 epsilon=1.0,
                 epsilon_min=0.03,
                 epsilon_decay=0.99,
                 seed=0):
        self.actions = list(actions or QUANTUM_CHOICES)
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.disc = Discretizer()
        self.rng = random.Random(seed)
        self.q = {}                # (state_tuple) -> [value per action]
        self.last = None           # pending (s, a) awaiting reward/next-state

    # ---- policy interface used by the simulator -------------------------
    def select_quantum(self, state):
        s = self.disc.index(state)
        a = self._act(s)
        self.last = (s, a)
        return self.actions[a]

    def observe(self, transition):
        """Feed one (reward, next_state) pair; completes the TD update."""
        if self.last is None:
            return
        s, a = self.last
        reward, next_state = transition["reward"], transition["next_state"]
        ns = self.disc.index(next_state)
        target = reward + self.gamma * max(self._values(ns))
        vals = self._values(s)
        vals[a] += self.alpha * (target - vals[a])
        self.last = None

    def update(self, state, action_idx, reward, next_state=None):
        """Explicit TD update given raw state dicts (used by offline replay)."""
        s = self.disc.index(state)
        target = reward
        if next_state is not None:
            ns = self.disc.index(next_state)
            target += self.gamma * max(self._values(ns))
        vals = self._values(s)
        vals[action_idx] += self.alpha * (target - vals[action_idx])

    def act_index(self, state):
        """Epsilon-greedy action index for a raw state dict (no update side effects)."""
        return self._act(self.disc.index(state))

    def end_episode(self):
        # Any decision left without a reward (abandoned select_quantum call)
        # carries no learning signal — drop it rather than updating toward
        # an arbitrary zero target, which would corrupt the Q-estimate.
        self.last = None
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

    def q_values(self, state):
        """Copy of action values for a raw state (used by safety margin checks)."""
        return list(self._values(self.disc.index(state)))

    # ---- internals -------------------------------------------------------
    def _values(self, s):
        if s not in self.q:
            self.q[s] = [0.0] * len(self.actions)
        return self.q[s]

    def _act(self, s):
        if self.rng.random() < self.epsilon:
            return self.rng.randrange(len(self.actions))
        vals = self._values(s)
        best = max(vals)
        return self.rng.choice([i for i, v in enumerate(vals) if v == best])

    def greedy_quantum(self, state):
        s = self.disc.index(state)
        vals = self._values(s)
        return self.actions[vals.index(max(vals))]

    # ---- persistence -----------------------------------------------------
    def save(self, path):
        import pickle
        with open(path, "wb") as f:
            pickle.dump({"q": {k: v for k, v in self.q.items()},
                         "epsilon": self.epsilon,
                         "actions": self.actions}, f)

    @classmethod
    def load(cls, path):
        import pickle
        obj = cls()
        with open(path, "rb") as f:
            data = pickle.load(f)
        obj.q = data["q"]
        # Always serve greedy: ignore the exploration rate stored at save
        # time. Nothing resumes training from disk.
        obj.epsilon = obj.epsilon_min
        saved_actions = data.get("actions")
        if saved_actions is not None and len(saved_actions) != len(obj.actions):
            raise ValueError("Q-table was trained with a different action set")
        return obj
