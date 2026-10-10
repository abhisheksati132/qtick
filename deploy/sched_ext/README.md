# QTick sched_ext deployment kit

Run the trained QTick policy against **real Linux processes** using
`sched_ext` (Linux 6.12+, `CONFIG_SCHED_CLASS_EXT`).

```
┌──────────────────────────── Linux host ────────────────────────────┐
│  qtick.bpf.o  (sched_ext scheduler)                                │
│    • dispatches tasks to a shared DSQ with slice = quantum         │
│    • every 100 ms aggregates queue statistics                      │
│              │ stats (JSON over loopback)                ▲         │
│              ▼                                          │ quantum  │
│  policy_server.py  ── SafeQuantumPolicy guardrails ─────┘          │
│    loads results/qtable.pkl (tabular) or DQN weights               │
└─────────────────────────────────────────────────────────────────────┘
```

## Files

| File | Role |
|---|---|
| `qtick.bpf.c` | sched_ext scheduler (build-ready skeleton; stat plumbing marked TODO) |
| `policy_server.py` | userspace TCP/JSON service answering `{"quantum_ms": N}` — runs the trained agent + guardrails |
| `loader.md` | notes for wiring the loader loop |

## Build & run (Linux 6.12+)

```bash
# 1. policy server (userspace, portable)
python3 policy_server.py --port 9911 --qtable ../../results/qtable.pkl

# quick sanity check from another shell:
echo '{"ready_len": 5, "mean_remaining_burst": 40}' | nc 127.0.0.1 9911
# -> {"quantum_ms": 16.0, "source": "qtick-tabular-q", "guarded": true}

# 2. BPF side
clang -O2 -g -target bpf -c qtick.bpf.c -o qtick.bpf.o   # needs vmlinux.h + scx/common.bpf.h
# then adapt an scx_rusty-style Rust/Python loader to:
#   - load qtick.bpf.o
#   - read the stats map each 100 ms
#   - POST stats to 127.0.0.1:9911 and write returned quantum into qtick_slice_ns
```

## Why guardrails live in userspace

`SafeQuantumPolicy` (margin veto, hard clamps, switch governor) runs inside the
policy server, so a misbehaving model can never push an unsafe quantum to the
kernel — worst case it falls back to a robust 16 ms slice. This is the
sim-to-real safety story from the report (Chapter "safety wrapper") applied to
production.
