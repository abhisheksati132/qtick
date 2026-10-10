# QTick on-device validation runbook (Linux 6.12+, x86_64)

Goal: replace simulator numbers with measured numbers — run the trained
QTick policy as a real `sched_ext` scheduler and compare against the
default CFS/SCX scheduler on scheduler-sensitive benchmarks.

> Status: BPF skeleton (`qtick.bpf.c`) + working userspace policy server
> (`policy_server.py`) ship in this folder. Kernel-side statistics plumbing
> (TODO markers) must be completed on the target machine. Everything below
> is the exact procedure to follow once that is done.

## 0. Prerequisites (target machine)

- Linux kernel ≥ 6.12 with `CONFIG_SCHED_CLASS_EXT=y`
  (`grep SCHED_CLASS_EXT /boot/config-$(uname -r)`)
- `clang`, `llvm`, `bpftool`, kernel headers, `libbpf`
- Python 3.10+ with `numpy` (policy server has no other dependencies)
- Benchmarks: `hackbench`, `sysbench`, `schbench` (build from source)

## 1. Start the policy plane (userspace, portable)

```bash
cd deploy/sched_ext
python3 policy_server.py --port 9911 --qtable ../../results/dqn_quantum.npz
# sanity check from another shell:
echo '{"ready_len": 5, "mean_remaining_burst": 40}' | nc 127.0.0.1 9911
# -> {"quantum_ms": 16.0, "source": "qtick-...", "guarded": true}
```

Guardrails (`SafeQuantumPolicy`: margin veto, [2, 64] ms clamps, switch
governor) run here, so the kernel can never receive an unsafe quantum —
worst case it falls back to a robust 16 ms slice.

## 2. Build and load the BPF scheduler

```bash
clang -O2 -g -target bpf -c qtick.bpf.c -o qtick.bpf.o
# adapt an scx_rusty-style loader to:
#   1. load qtick.bpf.o and attach struct_ops
#   2. every 100 ms: read the stats map (ready-queue length, EWMA slice
#      use, switch counter, preemption fraction)
#   3. POST stats JSON to 127.0.0.1:9911
#   4. write the returned quantum_ms into the qtick_slice_ns map
```

## 3. A/B measurement protocol

For each workload below, run 5 trials under (a) default scheduler and
(b) `qtick`, alternating (A/B/A/B…) to cancel thermal drift. Record
mean ± std of the primary metric.

| Workload | Command (example) | Primary metric |
|---|---|---|
| Scheduler stress | `hackbench -l 1000 -g 10` | completion time (s, lower better) |
| CPU throughput | `sysbench cpu --threads=8 --time=30 run` | events/s (higher better) |
| Wakeup latency | `schbench -m 2 -t 8 -r 30` | p99 wakeup latency (lower better) |
| Mixed (face-detection style) | OpenCV DNN loop, 500 frames | FPS (higher better) |

## 4. Success criteria (pre-registered)

- No regression vs default scheduler on any workload (paired t-test, p < 0.05).
- ≥10% improvement on at least one scheduler-sensitive workload (hackbench/schbench).
- Zero safety-veto storms: `guarded:true` fallbacks < 5% of decisions
  (check policy-server logs).

## 5. Reporting

Append a row per workload to `results/ondevice.csv` with columns:
`date,kernel,scheduler,workload,trials,mean,std,unit`. These numbers —
not simulator numbers — are what a journal's "real-system evaluation"
section and a patent's "industrial applicability" argument are built on.

## 6. Safety notes

- `sched_ext` has a watchdog (`timeout_ms`): a stuck scheduler detaches
  automatically and the kernel falls back — you cannot wedge the machine
  with a bad slice value, only slow it.
- Keep an SSH session open; test first with `hackbench` (short runs)
  before long `sysbench` soaks.
- The policy server is loopback-only by default; do not expose port 9911.
