#!/usr/bin/env python3
"""QTick policy server — the userspace half of the sched_ext deployment.

A tiny TCP/JSON service that loads the trained QTick agents and answers
scheduling decisions for the BPF side:

    request:  {"mean_remaining_burst": 42.1, "burst_heterogeneity": 0.8,
               "ready_len": 6, "switch_overhead_ratio": 0.11,
               "recent_preempt_fraction": 0.6}
    response: {"quantum_ms": 16, "source": "tabular", "guarded": false}

Run on the Linux target (the same host running the sched_ext scheduler):

    python3 policy_server.py --port 9911 --qtable ../../results/qtable.pkl

The BPF scheduler (see qtick.bpf.c) aggregates these stats per interval and
queries this server over loopback; the SafeQuantumPolicy guardrails run HERE,
in userspace, so unsafe quanta never reach the kernel.
"""
import argparse
import json
import os
import socketserver
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.rl.agent import QLearningAgent
from src.platform.services import SafeQuantumPolicy


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            line = self.rfile.readline()
            if not line:
                return
            req = json.loads(line)
            state = {
                "mean_remaining_burst": float(req.get("mean_remaining_burst", 0)),
                "burst_heterogeneity": float(req.get("burst_heterogeneity", 0)),
                "ready_len": int(req.get("ready_len", 0)),
                "switch_overhead_ratio": float(req.get("switch_overhead_ratio", 0)),
                "recent_preempt_fraction": float(req.get("recent_preempt_fraction", 0)),
            }
            q = self.server.policy.select_quantum(state)
            resp = {"quantum_ms": float(q), "source": self.server.source,
                    "guarded": True}
        except Exception as exc:                      # never crash the policy plane
            resp = {"quantum_ms": 8.0, "source": "fallback", "error": str(exc)}
        self.wfile.write((json.dumps(resp) + "\n").encode())


class PolicyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9911)
    ap.add_argument("--qtable", default="../../results/qtable.pkl")
    args = ap.parse_args()

    path = os.path.abspath(os.path.join(os.path.dirname(__file__), args.qtable))
    agent = QLearningAgent.load(path)
    agent.epsilon = 0.0
    safe = SafeQuantumPolicy(agent, q_min=2.0, q_max=64.0)

    srv = PolicyServer(("127.0.0.1", args.port), Handler)
    srv.policy = safe
    srv.source = "qtick-tabular-q"
    print(f"QTick policy server on 127.0.0.1:{args.port} "
          f"(qtable={path}, guardrails ON)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
