"""Safety, drift, verification, energy, experiments — platform services."""

import json
import os
import time

# ---------------------------------------------------------------------------
# Sim-to-real SAFETY WRAPPER
# ---------------------------------------------------------------------------
class SafeQuantumPolicy:
    """Wraps any learned quantum policy with guardrails:

      1. Confidence gate   — if the policy's action margin is thin (tabular:
         |Q*−Q2| < margin), fall back to a robust heuristic quantum.
      2. Hard clamps       — quantum always within [q_min, q_max].
      3. Switch governor   — if recent switch-overhead ratio exceeds a limit,
         force the largest quantum until the ratio recovers.

    The wrapped policy can be the tabular agent, the DQN, anything with
    select_quantum(state) — for margin checks it may also expose
    q_values(state) (tabular agent does).
    """

    def __init__(self, policy, q_min=2.0, q_max=64.0, margin=0.15,
                 switch_ratio_limit=0.25, fallback_quantum=16.0):
        self.policy = policy
        self.q_min, self.q_max = q_min, q_max
        self.margin = margin
        self.switch_ratio_limit = switch_ratio_limit
        self.fallback_quantum = fallback_quantum
        self.stats = {"veto_margin": 0, "veto_governor": 0, "clamped": 0,
                      "passed": 0}

    def _margin_ok(self, state):
        qv = getattr(self.policy, "q_values", None)
        if qv is None:
            return True   # DQN path: margin check handled by ensemble/limit
        vals = sorted(qv(state), reverse=True)
        top, second = vals[0], vals[1] if len(vals) > 1 else vals[0]
        denom = max(abs(top), 1e-9)
        return (top - second) / max(denom, 1e-9) >= self.margin or second == 0.0

    def select_quantum(self, state):
        q = self.policy.select_quantum(state)
        if not self._margin_ok(state):
            self.stats["veto_margin"] += 1
            q = self.fallback_quantum
        ratio = state.get("switch_overhead_ratio", 0.0)
        if ratio > self.switch_ratio_limit:
            self.stats["veto_governor"] += 1
            q = max(q, self.fallback_quantum)
        qc = min(max(q, self.q_min), self.q_max)
        if qc != q:
            self.stats["clamped"] += 1
        else:
            self.stats["passed"] += 1
        return qc


# ---------------------------------------------------------------------------
# DRIFT DETECTION + CONTINUAL LEARNING TRIGGER
# ---------------------------------------------------------------------------
class DriftDetector:
    """Page-Hinkley test over the streaming composite score.

    Rising composite (worse scheduling) while workload stats shift => drift.
    """

    def __init__(self, delta=0.02, threshold=20.0, min_instances=40):
        self.delta, self.threshold = delta, threshold
        self.min_instances = min_instances
        self.reset()

    def reset(self):
        self.n = 0
        self.mean = 0.0
        self.ph_sum = 0.0
        self.ph_min = 0.0
        self.drift = False

    def update(self, value):
        self.n += 1
        self.mean += (value - self.mean) / self.n
        ph = value - self.mean - self.delta
        self.ph_sum += ph
        self.ph_min = min(self.ph_min, self.ph_sum)
        if self.n >= self.min_instances and (self.ph_sum - self.ph_min) > self.threshold:
            self.drift = True
        return self.drift


class ContinualScheduler:
    """Production loop skeleton: monitor -> detect drift -> retrain -> swap.

    `train_fn(episode)` must run one training episode and return the episode's
    composite score; `on_retrain` is called after each refresh round.
    """

    def __init__(self, train_fn, detector=None, retrain_episodes=30,
                 max_rounds=10, on_retrain=None):
        self.train_fn = train_fn
        self.detector = detector or DriftDetector()
        self.retrain_episodes = retrain_episodes
        self.max_rounds = max_rounds
        self.on_retrain = on_retrain
        self.log = []

    def run(self):
        for rnd in range(self.max_rounds):
            self.detector.reset()
            ran = 0
            for ep in range(self.retrain_episodes):
                score = self.train_fn(ep)
                ran = ep + 1
                if self.detector.update(score):
                    break
            self.log.append({"round": rnd, "episodes": ran,
                             "drift_detected": self.detector.drift})
            if self.on_retrain:
                self.on_retrain(rnd, self.detector.drift)
        return self.log


# ---------------------------------------------------------------------------
# TRAINING PROVENANCE
# ---------------------------------------------------------------------------
def write_training_meta(episodes, tabular_episodes=None, cores=None,
                        delta=None, source="cli"):
    """Record which training run produced the current model files.

    Called by EVERY training entry point (web worker included) so the
    dashboard's provenance line can never describe a different run than
    the files on disk. Returns the dict written.
    """
    import datetime as _dt
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    meta = {"finished_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "episodes": episodes, "tabular_episodes": tabular_episodes,
            "cores": cores, "delta": delta, "source": source}
    os.makedirs(os.path.join(root, "..", "results"), exist_ok=True)
    with open(os.path.join(root, "..", "results", "training_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    return meta


# ---------------------------------------------------------------------------
# ENERGY MODEL
# ---------------------------------------------------------------------------
def energy_metrics(makespan, n_cores, busy_time, p_idle=25.0, p_busy=95.0):
    """Linear power model per core: idle draw + busy increment.

    Returns watt-seconds and watt-hours.
    """
    idle_ws = p_idle * makespan * n_cores
    busy_ws = (p_busy - p_idle) * busy_time
    ws = idle_ws + busy_ws
    return {"energy_ws": round(ws, 1), "energy_wh": round(ws / 3600.0, 4),
            "p_idle": p_idle, "p_busy": p_busy}


# ---------------------------------------------------------------------------
# VERIFICATION LAYER — certify properties of a policy
# ---------------------------------------------------------------------------
def verify_result(res, *, switch_cap=None, starvation_ratio=None):
    """Check invariants on a single simulation result.

    Returns dict with pass/fail per property + measured values.
    """
    out = {"all_complete": all(p.completion_time is not None for p in res.procs)}
    m = res.metrics()
    out["metrics"] = m
    if switch_cap is not None:
        out["switch_cap_ok"] = res.context_switches <= switch_cap
        out["switch_cap"] = switch_cap
    if starvation_ratio is not None:
        # fraction of the makespan any single process may wait — a load-aware
        # starvation bound (absolute wait scales with system load)
        worst = max((p.waited / max(res.makespan, 1e-9) for p in res.procs),
                    default=0.0)
        out["worst_wait_fraction"] = round(worst, 3)
        out["starvation_ok"] = worst <= starvation_ratio
    out["pass"] = out["all_complete"] and out.get("switch_cap_ok", True) \
        and out.get("starvation_ok", True)
    return out


def certify_vs_baseline(policy, baseline_policy, workload_factory, seeds, tol=1.2):
    """Regression guard: policy must stay within `tol`× baseline composite."""
    from src.simulator.scheduler import simulate

    def composite(pol, seed):
        r = simulate(workload_factory(seed=seed), algorithm="RR",
                     quantum_policy=pol, n_cores=2, delta=1.0)
        m = r.metrics()
        return m["avg_waiting"] + m["avg_turnaround"] + m["context_switches"]

    rows = []
    for s in seeds:
        c_p, c_b = composite(policy, s), composite(baseline_policy, s)
        rows.append({"seed": s, "policy": round(c_p, 1),
                     "baseline": round(c_b, 1), "ok": c_p <= tol * c_b})
    return {"certified": all(r["ok"] for r in rows), "tol": tol, "runs": rows}


def certify(policy, workload_factory, seeds, *, quantum_policy_is_dispatch=False,
            **verify_kw):
    """Run a policy across `seeds` workloads and certify properties on each."""
    from src.simulator.scheduler import simulate
    reports = []
    for s in seeds:
        procs = workload_factory(seed=s)
        res = simulate(procs, quantum_policy=policy, algorithm="RR",
                       dispatch_policy=policy if quantum_policy_is_dispatch else None)
        reports.append(verify_result(res, **verify_kw))
    return {"certified": all(r["pass"] for r in reports), "runs": reports}


# ---------------------------------------------------------------------------
# EXPERIMENT TRACKING
# ---------------------------------------------------------------------------
class ExperimentLog:
    """Append-only JSONL experiment registry (MLflow-lite)."""

    def __init__(self, path="results/experiments.jsonl"):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def record(self, name, params, metrics, tags=None):
        entry = {"ts": time.time(), "name": name,
                 "params": params, "metrics": metrics, "tags": tags or {}}
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def all(self):
        if not os.path.exists(self.path):
            return []
        with open(self.path) as f:
            return [json.loads(l) for l in f if l.strip()]

    def leaderboard(self, metric="composite_score", top=10):
        rows = []
        for e in self.all():
            for k, v in e["metrics"].items():
                if isinstance(v, (int, float)):
                    rows.append((e["name"], k, v, e["ts"]))
        rows = [r for r in rows if r[1] == metric]
        rows.sort(key=lambda r: r[2])
        return rows[:top]
