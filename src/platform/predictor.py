"""Neural burst-time predictor (numpy MLP) + trace ingestion for real datasets.

BurstPredictor learns  next_slice = f(ewma, last_slice, n_slices, waited, io)
from observed scheduling history — the 'predictive layer' of the platform.
"""
import csv
import json
import os
import numpy as np


# ---------------------------------------------------------------------------
# Tiny MLP regressor (MSE, full-batch GD — histories are small)
# ---------------------------------------------------------------------------
class _Reg:
    def __init__(self, n_in, seed=0, lr=5e-3):
        rng = np.random.default_rng(seed)
        self.W1 = rng.normal(0, 0.5, size=(n_in, 16))
        self.b1 = np.zeros(16)
        self.W2 = rng.normal(0, 0.5, size=(16, 1))
        self.b2 = np.zeros(1)
        self.lr = lr

    def predict(self, x):
        self.h = np.maximum(0, x @ self.W1 + self.b1)
        return self.h @ self.W2 + self.b2

    def train(self, X, Y, epochs=300):
        if len(X) < 8:
            return
        Y = Y.reshape(-1, 1)
        for _ in range(epochs):
            p = self.predict(X)
            err = p - Y
            gW2 = self.h.T @ err / len(X)
            gb2 = err.mean(axis=0)
            dh = err @ self.W2.T
            dh[self.h <= 0] = 0
            gW1 = X.T @ dh / len(X)
            gb1 = dh.mean(axis=0)
            self.W1 -= self.lr * gW1; self.b1 -= self.lr * gb1
            self.W2 -= self.lr * gW2; self.b2 -= self.lr * gb2


class BurstPredictor:
    """Online-learning burst predictor consumed by dispatch / cluster layers."""

    def __init__(self, alpha=0.35, default=8.0):
        self.alpha, self.default = alpha, default
        self.hist = {}       # pid -> list of slice lengths
        self.ewma = {}
        self.X, self.Y = [], []
        self.model = _Reg(5)
        self._dirty = False
        self._trained = False   # MLP output is random noise until first fit

    def features(self, pid, waited=0.0, io=0.0):
        e = self.ewma.get(pid, self.default)
        h = self.hist.get(pid, [])
        last = h[-1] if h else self.default
        return [min(e, 200) / 200.0, min(last, 200) / 200.0,
                min(len(h), 20) / 20.0, min(waited, 300) / 300.0, io]

    def observe(self, pid, slice_len, waited=0.0, io=0.0):
        # sample recorded BEFORE update: features predicted this slice's need
        self.X.append(self.features(pid, waited, io))
        self.Y.append(min(slice_len, 200) / 200.0)
        self._dirty = True
        prev = self.ewma.get(pid, self.default)
        self.ewma[pid] = (1 - self.alpha) * prev + self.alpha * slice_len
        self.hist.setdefault(pid, []).append(slice_len)

    def recent_mae(self, k=200):
        """Mean absolute error of the model on the last k observed samples
        (in original time units). None until the model has been fitted once."""
        if not self._trained or not self.X:
            return None
        X = np.array(self.X[-k:])
        Y = np.array(self.Y[-k:])
        pred = self.model.predict(X).reshape(-1)
        return float(np.abs(pred - Y).mean() * 200.0)

    def estimate(self, pid):
        # throttle: retrain at most once per 50 observations to bound cost
        if self._dirty and len(self.X) >= 16 and len(self.X) % 50 < 2:
            self.model.train(np.array(self.X[-2000:]), np.array(self.Y[-2000:]),
                             epochs=60)
            self._dirty = False
            self._trained = True
        if pid in self.ewma and self._trained:
            x = np.array([self.features(pid)])
            return float(np.clip(self.model.predict(x)[0, 0] * 200.0, 0.5, 200))
        # untrained MLP output is random noise — fall back to EWMA
        return self.ewma.get(pid, self.default)

    def save(self, path):
        np.savez(path, W1=self.model.W1, b1=self.model.b1,
                 W2=self.model.W2, b2=self.model.b2,
                 ewma=json.dumps({str(k): v for k, v in self.ewma.items()}))

    def load(self, path):
        d = np.load(path, allow_pickle=True)
        self.model.W1, self.model.b1 = d["W1"], d["b1"]
        self.model.W2, self.model.b2 = d["W2"], d["b2"]
        self.ewma = {int(k): v for k, v in json.loads(str(d["ewma"])).items()}
        self._trained = True   # persisted weights come from a fitted model


# ---------------------------------------------------------------------------
# Trace ingestion — real workload archives
# ---------------------------------------------------------------------------

def _looks_like_header(row):
    # a row is a header iff any cell is non-numeric. NOTE: naive
    # isalpha() checks misfire on scientific notation ("1.5e2"
    # contains 'e'), silently dropping data rows — float() is exact.
    for c in row:
        try:
            float(c)
        except ValueError:
            return True
    return False


def load_real_trace_auto(path):
    """Auto-detect and load Alibaba 2018, Google Borg 2019, Azure 2020 traces.
    Returns list of Process objects or None if format not recognized."""
    from src.simulator.process import Process
    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = None
        rows = []
        for row in reader:
            if not row or all(not c.strip() for c in row):
                continue
            if header is None and _looks_like_header(row):
                header = [c.strip().lower() for c in row]
                continue
            rows.append([c.strip() for c in row])
    if header is None:
        return None

    def col(*names):
        for n in names:
            if n in header:
                return header.index(n)
        return None

    # Check for Alibaba 2018 format: task_id, start_time, duration, cpu, mem, ...
    if all(c in header for c in ["task_id", "start_time", "duration", "cpu", "mem"]):
        ci_pid = col("task_id", "job_id")
        ci_arr = col("start_time", "submit_time")
        ci_bur = col("duration", "run_time")
        if ci_arr is not None and ci_bur is not None:
            procs = []
            for i, row in enumerate(rows):
                try:
                    pid = int(float(row[ci_pid])) if ci_pid is not None else i
                    arr = float(row[ci_arr])
                    bur = float(row[ci_bur])
                    if bur > 0:
                        procs.append(Process(pid=pid, arrival_time=arr, burst_time=bur, io_bound=False))
                except (ValueError, IndexError):
                    continue
            if procs:
                procs.sort(key=lambda p: p.arrival_time)
                return procs

    # Google Borg 2019 format: job_id, submit_time, runtime, resource_request...
    if any(c in header for c in ["job_id", "submit_time", "cpu_request", "mem_request"]):
        ci_pid = col("job_id")
        ci_arr = col("submit_time", "start_time")
        ci_bur = col("runtime", "duration")
        if ci_arr is not None and ci_bur is not None:
            procs = []
            for i, row in enumerate(rows):
                try:
                    pid = int(float(row[ci_pid])) if ci_pid is not None else i
                    arr = float(row[ci_arr])
                    bur = float(row[ci_bur])
                    if bur > 0:
                        procs.append(Process(pid=pid, arrival_time=arr, burst_time=bur, io_bound=False))
                except (ValueError, IndexError):
                    continue
            if procs:
                procs.sort(key=lambda p: p.arrival_time)
                return procs

    # Azure 2020 format: vm_id, start_time, duration, cores, memory
    if any(c in header for c in ["vm_id", "start_time", "duration", "cores", "memory"]):
        ci_pid = col("vm_id")
        ci_arr = col("start_time", "submit_time")
        ci_bur = col("duration", "runtime")
        if ci_arr is not None and ci_bur is not None:
            procs = []
            for i, row in enumerate(rows):
                try:
                    pid = int(float(row[ci_pid])) if ci_pid is not None else i
                    arr = float(row[ci_arr])
                    bur = float(row[ci_bur])
                    if bur > 0:
                        procs.append(Process(pid=pid, arrival_time=arr, burst_time=bur, io_bound=False))
                except (ValueError, IndexError):
                    continue
            if procs:
                procs.sort(key=lambda p: p.arrival_time)
                return procs

    return None


def write_sample_trace(path, n=40, seed=7):
    """Write a sample CSV trace so users see the expected format."""
    from src.simulator.workload import generate_workload
    procs = generate_workload(n_processes=n, seed=seed)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pid", "arrival", "burst", "io"])
        for p in procs:
            w.writerow([p.pid, f"{p.arrival_time:.2f}", f"{p.burst_time:.2f}",
                        1 if p.io_bound else 0])
        return path


# ---------------------------------------------------------------------------
# Trace ingestion — real workload archives
# ---------------------------------------------------------------------------
def load_trace(path):
    """Load a Process list from CSV/JSON traces.

    Supported formats (auto-detected):
      1. Generic CSV with header containing pid/process, arrival, burst/runtime[, io]
      2. Grid Workload Archive style CSV: Job Number, Arrival Time, Runtime, ...
      3. JSON: [{"pid":..,"arrival":..,"burst":..,"io":false}, ...]
      4. Alibaba 2018, Google Borg 2019, Azure 2020 traces (auto-detected)
    """
    from src.simulator.process import Process
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        with open(path) as f:
            rows = json.load(f)
        return [Process(pid=int(r["pid"]), arrival_time=float(r["arrival"]),
                        burst_time=float(r["burst"]),
                        io_bound=bool(r.get("io", False))) for r in rows]

    # Try auto-detect for CSV
    procs = load_real_trace_auto(path)
    if procs is not None:
        return procs
    
    # Fallback: generic CSV
    def _looks_like_header(row):
        for c in row:
            try:
                float(c)
            except ValueError:
                return True
        return False

    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = None
        rows = []
        for row in reader:
            if not row or all(not c.strip() for c in row):
                continue
            if header is None and _looks_like_header(row):
                header = [c.strip().lower() for c in row]
                continue
            rows.append([c.strip() for c in row])
    if header is None:
        header = ["pid", "arrival", "burst"]

    def col(*names):
        for n in names:
            if n in header:
                return header.index(n)
        return None

    ci_pid = col("pid", "process", "job number", "job_id", "job")
    ci_arr = col("arrival", "arrival time", "submit time", "time")
    ci_bur = col("burst", "runtime", "run time", "duration", "cpu time")
    ci_io = col("io", "io_bound", "io bound")
    if ci_arr is None or ci_bur is None:
        raise ValueError(f"trace {path}: could not locate arrival/burst columns in {header}")

    procs = []
    for i, row in enumerate(rows):
        try:
            pid = int(float(row[ci_pid])) if ci_pid is not None else i
            arr = float(row[ci_arr])
            bur = float(row[ci_bur])
            io = bool(int(float(row[ci_io]))) if ci_io is not None else False
            if bur <= 0:
                continue
            procs.append(Process(pid=pid, arrival_time=arr, burst_time=bur, io_bound=io))
        except (ValueError, IndexError):
            continue
    procs.sort(key=lambda p: p.arrival_time)
    return procs
