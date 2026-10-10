"""QTick web dashboard — Flask backend.

Endpoints:
  GET  /                -> dashboard UI
  POST /api/simulate    -> run one simulation, return metrics + Gantt timeline
  POST /api/train       -> train RL agent in background thread
  GET  /api/train/status-> training progress
  POST /api/benchmark   -> compare all algorithms on random traces
"""
import json
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, request, send_from_directory

from src.simulator.workload import generate_workload
from src.simulator.scheduler import (simulate, StaticQuantumPolicy,
                                     HeuristicQuantumPolicy)
from src.rl.agent import QLearningAgent

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QTABLE = os.path.join(ROOT, "results", "qtable.pkl")
DTABLE = os.path.join(ROOT, "results", "qtable_dispatch.pkl")
DQN_WEIGHTS = os.path.join(ROOT, "results", "dqn_quantum.npz")
PREDICTOR_PATH = os.path.join(ROOT, "results", "burst_predictor.npz")

app = Flask(__name__, static_folder="static")


@app.after_request
def _no_cache_api(resp):
    # NOTHING on this local demo server may be cached: stale HTML/JS/JSON
    # made real fixes look like "nothing happened". Cache-Control on every
    # response (page, static assets, API) guarantees what you see is current.
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp

_train_state = {"running": False, "progress": 0, "total": 0,
                "history": [], "error": None}


def _backup_models():
    """Snapshot current production models before a training run overwrites
    them. Keeps the last 3 backups; training is destructive by design, so
    a bad/accidental run must always be undoable."""
    import datetime as _dt
    import shutil
    files = [QTABLE, DTABLE, DQN_WEIGHTS, PREDICTOR_PATH]
    if not any(os.path.exists(f) for f in files):
        return
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(ROOT, "results", "backups", stamp)
    os.makedirs(dest, exist_ok=True)
    for f in files:
        if os.path.exists(f):
            shutil.copy(f, os.path.join(dest, os.path.basename(f)))
    # rotate: keep newest 3
    bdir = os.path.join(ROOT, "results", "backups")
    olds = sorted(os.listdir(bdir))
    for o in olds[:-3]:
        shutil.rmtree(os.path.join(bdir, o), ignore_errors=True)


class _Greedy:
    def __init__(self, agent):
        self.agent = agent

    def select_quantum(self, state):
        return self.agent.greedy_quantum(state)


def _policy_for(name, quantum):
    if name == "static":
        return StaticQuantumPolicy(float(quantum))
    if name == "heuristic":
        return HeuristicQuantumPolicy()
    if name == "rl":
        if not os.path.exists(QTABLE):
            raise FileNotFoundError("tabular Q-table not found — train first")
        agent = QLearningAgent.load(QTABLE)
        return _Greedy(agent)
    if name == "dqn":
        if not os.path.exists(DQN_WEIGHTS):
            raise FileNotFoundError("DQN weights not found — train first")
        from src.rl.dqn import DQNQuantumAgent
        return _Greedy(DQNQuantumAgent.load(DQN_WEIGHTS))
    return None


def _dispatch_for(name):
    if name != "rl":
        return None
    if not os.path.exists(DTABLE):
        return None
    from src.rl.dispatch import RLDispatchAgent
    from src.platform.predictor import BurstPredictor
    ag = RLDispatchAgent.load(DTABLE)
    ag.epsilon = 0.0
    # train/serve consistency: use the trained predictor, not EWMA fallback
    if os.path.exists(PREDICTOR_PATH):
        try:
            ag.predictor = BurstPredictor()
            ag.predictor.load(PREDICTOR_PATH)
        except Exception:
            ag.predictor = None
    return ag


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/simulate", methods=["POST"])
def api_simulate():
    d = request.get_json(force=True)
    try:
        return _run_simulation(d)
    except (FileNotFoundError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # never leak HTML stack traces to the UI
        return jsonify({"error": "simulation failed: %s" % exc}), 500


def _run_simulation(d):
    procs = generate_workload(
        n_processes=int(d.get("n_processes", 20)),
        seed=int(d.get("seed", 42)),
        cpu_bound_fraction=float(d.get("cpu_bound_fraction", 0.5)),
        arrival_rate=d.get("arrival_rate", "poisson"),
        mean_interarrival=float(d.get("mean_interarrival", 2.0)),
    )
    alg = d.get("algorithm", "RR")
    pol = _policy_for(d.get("policy"), d.get("quantum", 4)) \
        if d.get("policy") not in (None, "none") else None
    dpol = _dispatch_for(d.get("ai_dispatch", "off"))
    res = simulate(procs, n_cores=int(d.get("cores", 2)),
                   delta=float(d.get("delta", 1.0)),
                   algorithm=alg, quantum_policy=pol, dispatch_policy=dpol)
    m = res.metrics()
    if dpol is not None:
        m["dispatch_usage"] = dpol.usage
    return jsonify({
        "metrics": {k: (round(v, 3) if isinstance(v, (int, float)) else v)
                    for k, v in m.items()},
        "timeline": [
            {"core": c, "start": round(s, 2), "end": round(e, 2), "pid": pid}
            for c, s, e, pid in res.timeline
        ],
        "processes": [
            {"pid": p.pid, "arrival": round(p.arrival_time, 2),
             "burst": round(p.burst_time, 2),
             "io_bound": p.io_bound,
             "waiting": round(p.waited, 2),
             "turnaround": round(p.turnaround, 2) if p.turnaround else None}
            for p in sorted(res.procs, key=lambda x: x.pid)
        ],
    })


@app.route("/api/train", methods=["POST"])
def api_train():
    if _train_state["running"]:
        return jsonify({"status": "already_running"}), 409
    d = request.get_json(force=True) or {}
    episodes = int(d.get("episodes", 300))
    cores = int(d.get("cores", 2))
    delta = float(d.get("delta", 1.0))

    _train_state.update(running=True, progress=0, total=episodes,
                        history=[], error=None, brain_snaps=[],
                        brain_actions=[],  # live tabular snapshots (phase 1)
                        deep_snaps=[])     # live DQN/dispatch/predictor (phase 2)

    def worker():
        try:
            os.makedirs(os.path.dirname(QTABLE), exist_ok=True)
            _backup_models()
            # Phase 1/2: tabular RL-QT agent (the Simulator's default brain).
            # Without this, retraining visibly changed nothing.
            from scripts.train import train as train_tabular
            tab_episodes = max(100, episodes // 3)
            snap_every = max(1, tab_episodes // 6)

            def on_tab_ep(i, nq, r):
                _train_state.update(
                    progress=int(i / tab_episodes * 0.2 * episodes))

            def agent_hook(ep_idx, agent):
                if ep_idx % snap_every == 0 or ep_idx == tab_episodes:
                    _train_state["brain_snaps"].append(
                        _snapshot_brain(agent, ep_idx))
                    _train_state["brain_actions"] = list(agent.actions)

            tab_agent, _ = train_tabular(
                episodes=tab_episodes, n_cores=cores, delta=delta,
                verbose_every=0, on_episode=on_tab_ep,
                agent_hook=agent_hook)
            tab_agent.save(QTABLE)
            # Phase 2/2: DQN + dispatch + predictor (joint training).
            from scripts.train_joint import train as train_joint
            deep_every = max(1, episodes // 12)

            def on_joint_ep(i, nq, r):
                _train_state.update(
                    progress=int(0.2 * episodes + i / episodes * 0.8 * episodes))

            def on_joint_agents(ep_idx, q_agent, d_agent, predictor):
                if ep_idx % deep_every != 0 and ep_idx != episodes:
                    return
                probe = {}
                for s in _DEEP_PROBE:
                    try:
                        q = q_agent.greedy_quantum(dict(s))
                    except Exception:
                        q = None
                    probe[str(q)] = probe.get(str(q), 0) + 1
                _train_state["deep_snaps"].append({
                    "ep": ep_idx,
                    "dqn_loss": (round(q_agent.loss_ma, 4)
                                 if q_agent.loss_ma is not None else None),
                    "dqn_probe": probe,
                    "dispatch_usage": dict(d_agent.usage),
                    "pred_mae": (round(predictor.recent_mae(), 3)
                                 if predictor is not None else None),
                    "pred_samples": len(predictor.X) if predictor else 0,
                })

            qa, da, pred, hist = train_joint(
                episodes=episodes, n_cores=cores, delta=delta,
                verbose_every=0, on_episode=on_joint_ep,
                agent_hook=on_joint_agents)
            qa.save(DQN_WEIGHTS)
            da.save(DTABLE)
            pred.save(PREDICTOR_PATH)
            from src.platform.services import write_training_meta
            write_training_meta(episodes, tabular_episodes=tab_episodes,
                                cores=cores, delta=delta, source="dashboard")
            _train_state["history"] = hist
            _train_state["progress"] = episodes
        except Exception as exc:               # surface to UI
            _train_state["error"] = str(exc)
        finally:
            _train_state["running"] = False

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/api/train/status")
def api_train_status():
    return jsonify(_train_state)


@app.route("/api/benchmark", methods=["POST"])
def api_benchmark():
    from scripts.benchmark import run_suite
    d = request.get_json(force=True) or {}
    rows = run_suite(n_episodes=int(d.get("episodes", 30)),
                     n_cores=int(d.get("cores", 2)),
                     delta=float(d.get("delta", 1.0)),
                     qtable=QTABLE,
                     qtable_dispatch=DTABLE,
                     processes=int(d.get("n_processes", 30)),
                     cpu_fracs=d.get("cpu_fracs"),
                     arrival_rates=d.get("arrival_rates"))
    with open(os.path.join(ROOT, "results", "benchmark.json"), "w") as f:
        json.dump(rows, f, indent=2)
    return jsonify(rows)


BRAIN_FEATURES = [
    {"name": "Mean remaining burst", "labels": ["<5", "5–20", "20–60", "≥60"]},
    {"name": "Burst heterogeneity", "labels": ["low", "mid", "high"]},
    {"name": "Ready queue length", "labels": ["0–1", "2–4", "5–9", "10+"]},
    {"name": "Switch overhead ratio", "labels": ["<5%", "5–20%", "≥20%"]},
    {"name": "Recent preemption rate", "labels": ["low", "med", "high"]},
]


def _snapshot_brain(agent, ep, top_n=12):
    """Serialize the most decisive states of a live tabular agent."""
    scored = []
    for s_tuple, vals in agent.q.items():
        best = max(range(len(vals)), key=lambda i: vals[i])
        margin = vals[best] - sorted(vals)[-2] if len(vals) > 1 else 0.0
        scored.append((margin, s_tuple, vals, best))
    scored.sort(key=lambda t: t[0], reverse=True)
    states = [{"s": list(st), "q": [round(v, 3) for v in vals]}
              for _, st, vals, _ in scored[:top_n]]
    greedy = {}
    for _, _, vals, b in scored:
        greedy[agent.actions[b]] = greedy.get(agent.actions[b], 0) + 1
    return {"ep": ep, "n_states": len(agent.q),
            "actions": list(agent.actions), "features": BRAIN_FEATURES,
            "states": states,
            "greedy_counts": {str(k): v for k, v in greedy.items()}}


# Fixed probe situations for watching the DQN learn: same 12 inputs every
# snapshot, so shifting answers prove the network is really changing.
_DEEP_PROBE = [
    {"mean_remaining_burst": 8.0, "burst_heterogeneity": 0.2,
     "ready_len": 2, "switch_overhead_ratio": 0.02,
     "recent_preempt_fraction": 0.3},
    {"mean_remaining_burst": 25.0, "burst_heterogeneity": 0.5,
     "ready_len": 4, "switch_overhead_ratio": 0.08,
     "recent_preempt_fraction": 0.5},
    {"mean_remaining_burst": 80.0, "burst_heterogeneity": 1.2,
     "ready_len": 8, "switch_overhead_ratio": 0.15,
     "recent_preempt_fraction": 0.7},
    {"mean_remaining_burst": 150.0, "burst_heterogeneity": 0.4,
     "ready_len": 12, "switch_overhead_ratio": 0.05,
     "recent_preempt_fraction": 0.4},
    {"mean_remaining_burst": 45.0, "burst_heterogeneity": 1.8,
     "ready_len": 6, "switch_overhead_ratio": 0.25,
     "recent_preempt_fraction": 0.8},
    {"mean_remaining_burst": 12.0, "burst_heterogeneity": 0.9,
     "ready_len": 3, "switch_overhead_ratio": 0.12,
     "recent_preempt_fraction": 0.6},
    {"mean_remaining_burst": 200.0, "burst_heterogeneity": 0.3,
     "ready_len": 15, "switch_overhead_ratio": 0.03,
     "recent_preempt_fraction": 0.2},
    {"mean_remaining_burst": 60.0, "burst_heterogeneity": 0.7,
     "ready_len": 5, "switch_overhead_ratio": 0.18,
     "recent_preempt_fraction": 0.55},
    {"mean_remaining_burst": 5.0, "burst_heterogeneity": 0.1,
     "ready_len": 1, "switch_overhead_ratio": 0.01,
     "recent_preempt_fraction": 0.1},
    {"mean_remaining_burst": 110.0, "burst_heterogeneity": 1.5,
     "ready_len": 9, "switch_overhead_ratio": 0.22,
     "recent_preempt_fraction": 0.75},
    {"mean_remaining_burst": 35.0, "burst_heterogeneity": 0.6,
     "ready_len": 7, "switch_overhead_ratio": 0.1,
     "recent_preempt_fraction": 0.45},
    {"mean_remaining_burst": 95.0, "burst_heterogeneity": 1.0,
     "ready_len": 11, "switch_overhead_ratio": 0.14,
     "recent_preempt_fraction": 0.65},
]


@app.route("/api/brain_live")
def api_brain_live():
    """Snapshots captured during the latest training run: tabular Q-table
    (phase 1) plus DQN/dispatch/predictor telemetry (phase 2)."""
    return jsonify({"snaps": _train_state.get("brain_snaps", []),
                    "deep": _train_state.get("deep_snaps", []),
                    "running": _train_state.get("running", False),
                    "progress": _train_state.get("progress", 0),
                    "total": _train_state.get("total", 0)})


@app.route("/api/qtable")
def api_qtable():
    """Expose the learned Q-table for the Agent Brain inspector."""
    if not os.path.exists(QTABLE):
        return jsonify({"error": "no trained agent found — train first"}), 404
    agent = QLearningAgent.load(QTABLE)
    states = []
    greedy_counts = {a: 0 for a in agent.actions}
    for s_tuple, vals in agent.q.items():
        best = max(range(len(vals)), key=lambda i: vals[i])
        greedy_counts[agent.actions[best]] += 1
        states.append({"s": list(s_tuple), "q": [round(v, 3) for v in vals]})
    states.sort(key=lambda x: max(x["q"]), reverse=True)
    meta_path = os.path.join(ROOT, "results", "training_meta.json")
    meta = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path) as f:
                meta = json.load(f)
        except Exception:
            meta = {}
    return jsonify({
        "actions": agent.actions,
        "features": BRAIN_FEATURES,
        "n_states": len(states),
        "states": states,
        "greedy_counts": {str(k): v for k, v in greedy_counts.items()},
        "epsilon": agent.epsilon,
        "trained_at": meta.get("finished_at"),
        "trained_episodes": meta.get("episodes"),
        "trained_source": meta.get("source"),
    })


@app.route("/api/experiments")
def api_experiments():
    from src.platform.services import ExperimentLog
    log = ExperimentLog(os.path.join(ROOT, "results", "experiments.jsonl"))
    return jsonify({"experiments": log.all()[-50:],
                    "leaderboard": log.leaderboard("composite_score", top=10)})


@app.route("/api/cluster", methods=["POST"])
def api_cluster():
    from src.platform.cluster import simulate_cluster, generate_cluster_jobs, QClusterAgent
    d = request.get_json(force=True) or {}
    jobs = generate_cluster_jobs(n=int(d.get("jobs", 100)),
                                 seed=int(d.get("seed", 0)),
                                 n_nodes=int(d.get("nodes", 4)))
    out = simulate_cluster(jobs, n_nodes=int(d.get("nodes", 4)),
                           agent=QClusterAgent(int(d.get("nodes", 4)),
                                               epsilon=float(d.get("epsilon", 0.2))))
    return jsonify(out)


@app.route("/api/energy", methods=["POST"])
def api_energy():
    from src.platform.services import energy_metrics
    d = request.get_json(force=True) or {}
    cores = int(d.get("n_cores", 2))
    if "makespan" in d and "busy_time" in d:
        makespan, busy = float(d["makespan"]), float(d["busy_time"])
    else:
        # self-contained: run a workload, then account its energy honestly
        procs = generate_workload(
            n_processes=int(d.get("n_processes", 25)),
            seed=int(d.get("seed", 7)),
            cpu_bound_fraction=float(d.get("cpu_bound_fraction", 0.5)),
            arrival_rate=d.get("arrival_rate", "poisson"))
        try:
            pol = _policy_for(d.get("policy", "rl"), d.get("quantum", 8.0))
        except (FileNotFoundError, ValueError):
            pol = None
        res = simulate(procs, n_cores=cores, delta=float(d.get("delta", 1.0)),
                       algorithm="RR", quantum_policy=pol)
        m = res.metrics()
        makespan, busy = m["makespan"], res.busy_time
    return jsonify(energy_metrics(
        makespan=makespan, n_cores=cores, busy_time=busy,
        p_idle=float(d.get("p_idle", 25.0)),
        p_busy=float(d.get("p_busy", 95.0)),
    ))


@app.route("/api/verify", methods=["POST"])
def api_verify():
    from src.simulator.scheduler import simulate, StaticQuantumPolicy
    from src.platform.services import certify_vs_baseline
    d = request.get_json(force=True) or {}
    seeds = d.get("seeds", [11, 12, 13])
    policy = QLearningAgent.load(QTABLE)
    policy.epsilon = 0.0
    from src.simulator.workload import generate_workload
    class Greedy:
        def select_quantum(self, state):
            return policy.greedy_quantum(state)
    reg = certify_vs_baseline(
        Greedy(),
        StaticQuantumPolicy(16.0),
        lambda seed: generate_workload(n_processes=25, seed=seed,
                                       cpu_bound_fraction=0.5),
        seeds=seeds,
        tol=float(d.get("tol", 1.2)))
    return jsonify(reg)


# persistent drift monitor: remembers the score stream across calls,
# so the dashboard demo actually demonstrates drift
from src.platform.services import DriftDetector as _DriftDetector

_drift_monitor = _DriftDetector()


@app.route("/api/drift_demo", methods=["POST"])
def api_drift_demo():
    """REAL drift demonstration: run actual simulations whose workload shifts
    halfway (balanced -> CPU-heavy) and feed the true composite scores into
    the persistent drift monitor. No synthetic numbers anywhere."""
    d = request.get_json(force=True) or {}
    try:
        pol = _policy_for(d.get("policy", "rl"), d.get("quantum", 8.0))
    except (FileNotFoundError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    # demo-tuned sensitivity (same Page-Hinkley algorithm, shorter memory so
    # it can fire within a 14-sample demo; production default needs 40+)
    from src.platform.services import DriftDetector as _DD
    monitor = _DD(threshold=20.0, min_instances=8)
    n = int(d.get("rounds", 14))
    composites = []
    for i in range(n):
        frac = 0.3 if i < n // 2 else 0.85   # the workload shift
        procs = generate_workload(n_processes=20, seed=70000 + i,
                                  cpu_bound_fraction=frac)
        res = simulate(procs, n_cores=2, delta=1.0, algorithm="RR",
                       quantum_policy=pol)
        m = res.metrics()
        s = m["avg_waiting"] + m["avg_turnaround"] + m["context_switches"]
        composites.append(round(s, 1))
        monitor.update(s)
    half = n // 2
    return jsonify({
        "drift": monitor.drift,
        "n": monitor.n,
        "composites": composites,
        "first_half_avg": round(sum(composites[:half]) / half, 1),
        "second_half_avg": round(sum(composites[half:]) / (n - half), 1),
    })


@app.route("/api/drift", methods=["POST"])
def api_drift():
    d = request.get_json(force=True) or {}
    if d.get("reset"):
        _drift_monitor.reset()
        return jsonify({"drift": False, "n": 0, "reset": True})
    if "history" in d:
        for v in d["history"]:
            _drift_monitor.update(float(v))
    else:
        _drift_monitor.update(float(d.get("composite", 0)))
    return jsonify({"drift": _drift_monitor.drift, "n": _drift_monitor.n})


if __name__ == "__main__":
    print("QTick dashboard -> http://127.0.0.1:5000")
    app.run(debug=False, port=5000)
