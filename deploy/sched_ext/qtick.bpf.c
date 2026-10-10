/* QTick sched_ext skeleton — AI-tuned quantum on real Linux tasks.
 *
 * Target: Linux 6.12+ with CONFIG_SCHED_CLASS_EXT (sched_ext).
 * Build:  clang -O2 -g -target bpf -c qtick.bpf.c -o qtick.bpf.o
 * Load:   via a scx_loader / rust userspace (scx_rusty is a good template).
 *
 * Architecture:
 *   - Tasks are dispatched to a shared DSQ (per-node).
 *   - Every STATS_INTERVAL_MS the userspace loader aggregates ready-queue
 *     statistics, calls the QTick policy server (policy_server.py), and
 *     writes the returned quantum back into slice_ns.
 *   - Guardrails live in userspace; the kernel only ever sees a clamped,
 *     governor-checked quantum.
 *
 * This file is a build-ready SKELETON: the statistics plumbing marked TODO
 * is workload-specific and intentionally minimal for review clarity.
 */
#include <scx/common.bpf.h>

char _license[] SEC("license") = "GPL";

#define STATS_INTERVAL_MS 100

const volatile u64 initial_slice_ns = 8ULL * NSEC_PER_MSEC;
u64 qtick_slice_ns = 8ULL * NSEC_PER_MSEC;   /* written by userspace */

UEI_DEFINE(uei);

struct {
	__uint(type, SCX_DSQ_GLOBAL);   /* placeholder: replaced by DSQ defs */
	__uint(value, 0);
} shared_dsq;

s32 BPF_STRUCT_OPS(qtick_select_cpu, struct task_struct *p, s32 prev_cpu, u64 wake_flags)
{
	/* Cache-affinity-first placement: keep task on prev_cpu when idle. */
	bool is_idle = false;
	s32 cpu = scx_bpf_pick_idle_cpu(p->cpus_ptr, 0);
	if (cpu >= 0)
		return cpu;
	return prev_cpu;
}

void BPF_STRUCT_OPS(qtick_enqueue, struct task_struct *p, u64 enq_flags)
{
	/* Single shared DSQ — FIFO order preserves RR semantics. */
	scx_bpf_dispatch(p, SCX_DSQ_GLOBAL, qtick_slice_ns, enq_flags);
}

void BPF_STRUCT_OPS(qtick_running, struct task_struct *p)
{
	/* TODO: per-interval aggregation:
	 *   - ready-queue length (scx_bpf_dsq_nr_queued)
	 *   - EWMA of last slice consumed by p (p->se.exec_runtime delta)
	 *   - switch counter increment when p != last_task_on_cpu
	 * Publish via a per-CPU array map consumed by userspace each interval.
	 */
}

void BPF_STRUCT_OPS(qtick_stopping, struct task_struct *p, bool runnable)
{
	/* TODO: record whether slice expired (preempted) or task blocked
	 * (completed its need) -> feeds recent_preempt_fraction statistic. */
}

s32 BPF_STRUCT_OPS(qtick_init)
{
	return scx_bpf_create_dsq(SHARED_DSQ_ID, -1);
}

void BPF_STRUCT_OPS(qtick_exit, struct scx_exit_info *ei)
{
	UEI_RECORD(uei, ei);
}

SEC(".struct_ops.link")
struct sched_ext_ops qtick = {
	.select_cpu	= (void *)qtick_select_cpu,
	.enqueue	= (void *)qtick_enqueue,
	.running	= (void *)qtick_running,
	.stopping	= (void *)qtick_stopping,
	.init		= (void *)qtick_init,
	.exit		= (void *)qtick_exit,
	.timeout_ms	= 3000,
	.name		= "qtick",
};
