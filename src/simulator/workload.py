"""Synthetic workload generation with configurable CPU-bound / I/O-bound mixes."""
import random
from .process import Process


def generate_workload(
    n_processes=30,
    arrival_rate="poisson",       # "poisson" | "burst" | "uniform"
    mean_interarrival=2.0,
    cpu_bound_fraction=0.5,       # fraction of processes that are CPU-bound
    cpu_burst_range=(40, 200),
    io_burst_range=(2, 20),
    seed=None,
):
    if arrival_rate not in ("poisson", "burst", "uniform"):
        raise ValueError(
            f"unknown arrival_rate={arrival_rate!r}; "
            "expected 'poisson', 'burst' or 'uniform'")
    rng = random.Random(seed)
    procs = []
    t = 0.0
    n_cpu = int(round(n_processes * cpu_bound_fraction))
    kinds = [False] * (n_processes - n_cpu) + [True] * n_cpu
    rng.shuffle(kinds)

    for i, is_cpu in enumerate(kinds):
        if arrival_rate == "poisson":
            t += rng.expovariate(1.0 / mean_interarrival)
        elif arrival_rate == "burst":
            # arrivals come in clusters: mostly small gaps, occasional long gap
            t += rng.choice([rng.uniform(0, 1), rng.uniform(8, 15)])
        else:
            t += rng.uniform(0, 2 * mean_interarrival)

        lo, hi = cpu_burst_range if is_cpu else io_burst_range
        burst = max(1.0, rng.gammavariate(2.0, (lo + hi) / 4.0))
        burst = min(max(burst, lo * 0.5), hi * 1.5)
        procs.append(Process(pid=i, arrival_time=t, burst_time=burst, io_bound=not is_cpu))
    return procs
