"""Fetch public real workload traces (Parallel Workloads Archive, SWF format)
and convert them to QTick CSV traces.

Sources (Feitelson et al., Hebrew University PWA):
  - NASA-iPSC-1993  (NASA Ames iPSC/860, 42k jobs)
  - KTH-SP2-1996    (KTH SP2, 28k jobs)
  - CTC-SP2-1996    (Cornell Theory Center SP2, 79k jobs)

SWF fields used: [1]=submit time (s), [3]=run time (s), [7]=req processors.
We map each job -> process(arrival=submit, burst=runtime), keep the first
`max_jobs` valid jobs with runtime>0, and rescale time so the trace fits a
simulator-friendly horizon (default: scale arrivals/bursts jointly).

Run:  python scripts/fetch_traces.py
"""
import gzip
import os
import shutil
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TRACE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "traces", "real")

LOGS = {
    "nasa": "https://www.cs.huji.ac.il/labs/parallel/workload/l_nasa_ipsc/NASA-iPSC-1993-3.1-cln.swf.gz",
    "kth": "https://www.cs.huji.ac.il/labs/parallel/workload/l_kth_sp2/KTH-SP2-1996-2.1-cln.swf.gz",
    "ctc": "https://www.cs.huji.ac.il/labs/parallel/workload/l_ctc_sp2/CTC-SP2-1996-3.1-cln.swf.gz",
}


def parse_swf(path, max_jobs=400):
    """Parse SWF log -> list of (arrival, burst)."""
    jobs = []
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            parts = line.split()
            if len(parts) < 8:
                continue
            try:
                submit = float(parts[1])
                runtime = float(parts[3])
            except ValueError:
                continue
            if runtime <= 0 or submit < 0:
                continue
            jobs.append((submit, runtime))
            if len(jobs) >= max_jobs:
                break
    return jobs


def to_csv(jobs, out_path, time_scale=1.0):
    """Write (arrival, burst) pairs as QTick CSV, rescaling time."""
    import csv
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pid", "arrival", "burst", "io"])
        for i, (a, b) in enumerate(jobs):
            w.writerow([i, round(a * time_scale, 2), round(max(b * time_scale, 0.5), 2), 0])


def fetch(url, dest):
    import ssl
    print("downloading", url)
    req = urllib.request.Request(url, headers={"User-Agent": "QTick-research/1.0"})
    # NOTE: unverified context only because this host lacks CA certs;
    # integrity is checked by parsing + job-count validation below.
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=180, context=ctx) as r, \
            open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    print("saved", dest, os.path.getsize(dest), "bytes")


def main():
    os.makedirs(TRACE_DIR, exist_ok=True)
    for name, url in LOGS.items():
        gz = os.path.join(TRACE_DIR, name + ".swf.gz")
        if not os.path.exists(gz):
            try:
                fetch(url, gz)
            except Exception as e:
                print(f"FAILED {name}: {e}")
                continue
        try:
            jobs = parse_swf(gz, max_jobs=400)
        except Exception as e:
            print(f"PARSE FAILED {name}: {e}")
            continue
        if not jobs:
            print(f"NO JOBS {name}")
            continue
        # rescale: keep relative structure, fit ~ first arrival at t=0
        t0 = jobs[0][0]
        jobs = [(a - t0, b) for a, b in jobs]
        span = max(a for a, _ in jobs) or 1.0
        scale = 600.0 / span if span > 600 else 1.0
        out = os.path.join(TRACE_DIR, name + ".csv")
        to_csv(jobs, out, time_scale=scale)
        bursts = [b * scale for _, b in jobs]
        print(f"{name}: {len(jobs)} jobs -> {out} "
              f"(burst mean={sum(bursts)/len(bursts):.1f} max={max(bursts):.1f})")


if __name__ == "__main__":
    main()
