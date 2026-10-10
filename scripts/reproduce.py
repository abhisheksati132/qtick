"""One-command reproduction of every reported number.

Runs (fast mode ~6 min; full mode ~45 min):
  1. unit + platform tests
  2. reward-shape sanity (status-quo config only)
  3. benchmark suite -> results/benchmark.json (+ stats + regimes)
  4. real-trace replay  -> results/benchmark_real.json
  5. ablation          -> results/ablation.json
  6. consolidated analysis (Pareto, regimes, significance)

Training is NOT re-run (models ship in results/); use scripts/train*.py
to reproduce training itself.

Usage:
  python scripts/reproduce.py            # fast (fewer episodes)
  python scripts/reproduce.py --full     # paper-grade episode counts
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(cmd, what):
    print(f"\n### {what}\n$ {' '.join(cmd)}", flush=True)
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        print(f"FAILED: {what}")
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()
    n = 60 if args.full else 20
    jr = 200 if args.full else 60

    py = sys.executable
    run([py, "tests/test_sim.py"], "simulator invariant tests")
    run([py, "tests/test_platform.py"], "platform tests")
    run([py, "scripts/generate_modern_traces.py"], "modern cloud trace generation")
    run([py, "scripts/benchmark.py", "--episodes", str(n)], "benchmark suite")
    run([py, "scripts/benchmark_real.py", "--jobs", str(jr)], "real-trace replay")
    run([py, "scripts/ablation.py", "--episodes", str(max(n // 2, 10))], "ablation")
    run([py, "scripts/analyze.py"], "consolidated analysis")
    print("\nAll artifacts reproduced under results/. "
          "Compare against the committed JSON files for verification.")


if __name__ == "__main__":
    main()
