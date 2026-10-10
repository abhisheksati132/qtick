class Process:
    __slots__ = (
        "pid", "arrival_time", "burst_time", "remaining_time",
        "io_bound", "start_time", "completion_time",
        "waited", "executed_slices", "last_ran_at",
    )

    def __init__(self, pid, arrival_time, burst_time, io_bound=False):
        self.pid = pid
        self.arrival_time = arrival_time
        self.burst_time = float(burst_time)
        self.remaining_time = float(burst_time)
        self.io_bound = io_bound
        self.start_time = None
        self.completion_time = None
        self.waited = 0.0          # time spent in ready queue
        self.executed_slices = 0   # number of dispatches (== preemptions+completions)
        self.last_ran_at = None

    @property
    def turnaround(self):
        if self.completion_time is None:
            return None
        return self.completion_time - self.arrival_time

    @property
    def waiting(self):
        return self.waited

    def __repr__(self):
        return (f"P{self.pid}(arr={self.arrival_time:.1f}, burst={self.burst_time:.1f}, "
                f"{'IO' if self.io_bound else 'CPU'})")
