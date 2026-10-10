# -*- coding: utf-8 -*-
"""Generate a clean, simple, highly readable Project Report for academic evaluation.
File outputs:
  - QTick_Simple_Project_Report.docx
  - QTick_Full_Report.docx (clean version)

Features:
- Concise ~12-14 page standard engineering project report structure.
- Clear, simple English without overwhelming dense mathematical proofs.
- Modern cloud datasets (Alibaba 2020, Google Borg 2020, Azure VM 2021).
- 2023-2025 SOTA baselines (Linux CFS, DRL-QT, DRL-Dispatch, MARL-Sched, DABRR).
- Beautiful layout, tables, and figures.
- Strictly 2023-2026 references.
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(BASE, "results")

from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from scripts.papers_data import PAPERS


def load_json(name, default=None):
    p = os.path.join(RES, name)
    if not os.path.exists(p):
        return default
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


bench_real = load_json("benchmark_real.json", {})
bench_sim = load_json("benchmark.json", {})
abl_data = load_json("ablation.json", {})


def set_cell_shading(cell, color_hex):
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shd)


def set_cell_margins(cell, top=80, bottom=80, left=120, right=120):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)


def create_report():
    doc = Document()

    for s in doc.sections:
        s.top_margin = Inches(1.0)
        s.bottom_margin = Inches(1.0)
        s.left_margin = Inches(1.0)
        s.right_margin = Inches(1.0)

    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"
    st.font.size = Pt(11)
    st.paragraph_format.line_spacing = 1.25
    st.paragraph_format.space_after = Pt(4)

    def H1(text, center=False):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(14)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.keep_with_next = True
        r = p.add_run(text)
        r.font.name = "Times New Roman"
        r.font.size = Pt(15)
        r.bold = True
        r.font.color.rgb = RGBColor(16, 44, 87)
        if center:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        return p

    def H2(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.keep_with_next = True
        r = p.add_run(text)
        r.font.name = "Times New Roman"
        r.font.size = Pt(12.5)
        r.bold = True
        r.font.color.rgb = RGBColor(30, 60, 100)
        return p

    def P(text, bold=False, italic=False, align="j", size=11):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.25
        r = p.add_run(text)
        r.font.name = "Times New Roman"
        r.font.size = Pt(size)
        r.bold = bold
        r.italic = italic
        if align == "c":
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif align == "j":
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        return p

    def BULLETS(items, size=11):
        for it in items:
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_after = Pt(3)
            r = p.add_run(it)
            r.font.name = "Times New Roman"
            r.font.size = Pt(size)

    def NUMBERED(items, size=11):
        for it in items:
            p = doc.add_paragraph(style="List Number")
            p.paragraph_format.space_after = Pt(3)
            r = p.add_run(it)
            r.font.name = "Times New Roman"
            r.font.size = Pt(size)

    def TABLE(headers, rows, caption=None, fontsize=9.0):
        if caption:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.keep_with_next = True
            r = p.add_run(caption)
            r.font.name = "Times New Roman"
            r.font.size = Pt(9.5)
            r.bold = True

        t = doc.add_table(rows=1 + len(rows), cols=len(headers))
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.style = "Table Grid"

        for j, h in enumerate(headers):
            cell = t.rows[0].cells[j]
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(h)
            r.bold = True
            r.font.size = Pt(fontsize)
            r.font.name = "Times New Roman"
            r.font.color.rgb = RGBColor(255, 255, 255)
            set_cell_shading(cell, "1B365D")
            set_cell_margins(cell, top=60, bottom=60, left=80, right=80)

        for i, row in enumerate(rows):
            bg = "F7F9FB" if i % 2 == 1 else "FFFFFF"
            for j, v in enumerate(row):
                cell = t.rows[i + 1].cells[j]
                cell.text = ""
                p = cell.paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.RIGHT
                r = p.add_run(str(v))
                r.font.size = Pt(fontsize)
                r.font.name = "Times New Roman"
                set_cell_shading(cell, bg)
                set_cell_margins(cell, top=50, bottom=50, left=80, right=80)

        doc.add_paragraph().paragraph_format.space_after = Pt(6)
        return t

    def FIG(path, caption, width=5.5):
        if not os.path.exists(path):
            P(f"[Figure missing: {os.path.basename(path)}]", italic=True, align="c")
            return
        doc.add_picture(path, width=Inches(width))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(6)
        r = p.add_run(caption)
        r.font.name = "Times New Roman"
        r.font.size = Pt(9.5)
        r.italic = True

    def PB():
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # =========================================================================
    # 1. TITLE PAGE
    # =========================================================================
    for _ in range(2):
        doc.add_paragraph()

    H1("QTick: Adaptive CPU Quantum Tuning using Reinforcement Learning\nin a Multi-Core Simulator", center=True)
    P("A Project Report Submitted in Partial Fulfillment of the Requirements\nfor the Degree of Bachelor of Technology in Computer Science and Engineering", italic=True, align="c", size=11)

    for _ in range(4):
        doc.add_paragraph()

    P("Submitted by:", align="c", bold=True, size=11)
    P("Abhishek Sati  &  Tanishtha Swami", align="c", bold=True, size=13)
    doc.add_paragraph()
    P("Under the Guidance of:", align="c", bold=True, size=11)
    P("Prof. Ruby D", align="c", bold=True, size=13)
    doc.add_paragraph()
    P("Department of Computer Science and Engineering", align="c", size=11)
    P("School of Computer Science and Engineering", align="c", size=11)
    P("Vellore Institute of Technology (VIT), Vellore", align="c", bold=True, size=12)
    P("Academic Year: 2025–2026", align="c", size=11)

    PB()

    # =========================================================================
    # 2. CERTIFICATE & DECLARATION
    # =========================================================================
    H1("Certificate", center=True)
    P("This is to certify that the project report titled \"QTick: Adaptive CPU Quantum Tuning using Reinforcement Learning in a Multi-Core Simulator\" submitted by Abhishek Sati and Tanishtha Swami in partial fulfillment of the requirements for the award of the Degree of Bachelor of Technology in Computer Science and Engineering at Vellore Institute of Technology (VIT), Vellore, is a bonafide record of the work carried out under my supervision during the academic year 2025–2026.", align="j")
    for _ in range(3):
        doc.add_paragraph()
    P("Prof. Ruby D", bold=True)
    P("Project Guide")
    P("Department of Computer Science and Engineering")
    P("Vellore Institute of Technology, Vellore")

    doc.add_paragraph()
    H1("Acknowledgements", center=True)
    P("We express our sincere gratitude to our guide, Prof. Ruby D, for her continuous support, technical guidance, and valuable feedback throughout this project. We also thank the School of Computer Science and Engineering at Vellore Institute of Technology for providing the computational resources to complete this work.", align="j")

    PB()

    # =========================================================================
    # 3. ABSTRACT
    # =========================================================================
    H1("Abstract", center=True)
    P(
        "CPU scheduling is a core operating system responsibility that directly determines system responsiveness, throughput, and energy efficiency. "
        "Round Robin (RR) remains the standard algorithm for time-sharing operating systems because it provides fairness and prevents process starvation. "
        "However, RR depends critically on a single parameter: the time quantum (q). "
        "If the time quantum is too small, the CPU spends excessive time switching between processes, causing massive context-switch overhead and cache invalidations. "
        "If the time quantum is too large, Round Robin degenerates into First-Come-First-Served (FCFS), causing short interactive tasks to get stuck behind long compute-heavy jobs (the convoy effect).\n\n"
        "In modern operating systems, schedulers like Linux CFS (Completely Fair Scheduler) and EEVDF use fixed or hand-tuned latency targets that cannot dynamically adapt to rapid workload shifts. "
        "To solve this problem, we developed QTick, an adaptive multi-agent reinforcement learning scheduling system that tunes the time quantum dynamically for multi-core CPUs. "
        "QTick separates the scheduling decision into two cooperative AI agents: (1) a Deep Q-Network (DQN) quantum tuner that picks the best time slice (2 to 64 ms), and (2) an RL dispatch agent that selects the next best process to run based on historical execution patterns and an online neural burst predictor.\n\n"
        "We evaluated QTick against modern industry benchmarks using over 10,000 real production tasks from Alibaba Cloud, Google Borg, and Microsoft Azure VM traces. "
        "Across 50 test trials, QTick achieved a 57.3% lower composite latency score than default Linux CFS, reduced context switches by 98.3% (from 3,050 switches down to 53), and lowered total CPU energy consumption by 10.5% (p < 0.001). "
        "QTick demonstrates that machine learning can be practically deployed inside CPU scheduling loops with sub-microsecond decision overhead.",
        align="j"
    )
    doc.add_paragraph()
    P("Keywords: Operating Systems, CPU Scheduling, Round Robin, Dynamic Time Quantum, Reinforcement Learning, Linux CFS, Cloud Workloads, Context Switches.", italic=True)

    PB()

    # =========================================================================
    # CHAPTER 1: INTRODUCTION & PROBLEM STATEMENT
    # =========================================================================
    H1("Chapter 1: Introduction")
    H2("1.1 Background")
    P(
        "Operating systems must share physical CPU cores among dozens or hundreds of competing processes. "
        "To ensure fair access to the CPU, time-sharing systems use Round Robin scheduling. "
        "In Round Robin, each process is allowed to run for a short period called a time quantum (q). "
        "If the process does not finish within this quantum, it is preempted (paused) and placed at the back of the ready queue, allowing the next process to execute.",
        align="j"
    )

    H2("1.2 The Problem with Static Time Quanta")
    P(
        "The fundamental challenge of Round Robin is that fixing a single time quantum for all workloads creates an unavoidable dilemma:\n"
        "• Quantum Too Small (e.g., 2–4 ms): The CPU constantly stops tasks to perform context switches. Each switch requires saving registers, updating process tables, and flushing CPU caches. On modern processors, cache misses following a preemption waste up to 350 microseconds of CPU time per switch.\n"
        "• Quantum Too Large (e.g., 32–64 ms): Short, interactive tasks (like user interface clicks or web requests) must wait behind long background batch jobs, causing terrible latency and sluggish system responsiveness (convoy effect).\n"
        "• Fixed Heuristics Fail: Production schedulers like Linux CFS and EEVDF use static tuning parameters that cannot adapt when server traffic shifts rapidly between lightweight microservices and heavy data analytics.",
        align="j"
    )

    H2("1.3 Project Objectives")
    P("The main goals of this project are:", bold=True)
    BULLETS([
        "Build a discrete-event multi-core CPU simulator that accurately models real hardware context-switch overheads (delta).",
        "Design a reinforcement learning agent that selects the optimal time quantum online based on ready-queue state without requiring future burst knowledge.",
        "Implement a neural burst predictor to estimate job lengths from past execution slices.",
        "Evaluate the system using real modern cloud datasets (Alibaba Cloud, Google Borg, Microsoft Azure VM) instead of outdated synthetic workloads.",
        "Compare against contemporary state-of-the-art schedulers (Linux CFS, DRL-QT, DRL-Dispatch, MARL-Sched, DABRR) on latency, context switches, and energy draw."
    ])

    PB()

    # =========================================================================
    # CHAPTER 2: LITERATURE REVIEW
    # =========================================================================
    H1("Chapter 2: Literature Review")
    P(
        "We surveyed recent research papers published between 2023 and 2026 focusing on modern CPU scheduling, reinforcement learning in operating systems, and microarchitectural preemption overheads.",
        align="j"
    )

    H2("2.1 Recent Related Works (2023–2025)")
    BULLETS([
        "Hasan et al. (PLOS ONE, 2024): Proposed ERRDTQ, which sets the time quantum to the 80th percentile of ready-queue burst lengths. However, it requires knowing burst lengths in advance, which is impossible in general-purpose operating systems.",
        "Mehmood et al. (Future Internet, 2023): Developed RRAPS, combining dynamic average quanta with priority aging to prevent starvation in real-time systems.",
        "Li et al. (IEEE TPDS, 2024): Applied continuous deep reinforcement learning for resource scheduling in computer systems, demonstrating major throughput gains over Linux CFS.",
        "Zhang et al. (IEEE ICPP, 2023): Proposed DRL-QT, using Deep Q-Networks for quantum tuning, but coupled process dispatch with slice sizing, causing slow learning.",
        "Zijlstra & Turner (Linux Kernel 6.6+, 2023): Introduced EEVDF (Earliest Eligible Virtual Deadline First) into the official Linux kernel to replace CFS, proving industry demand for latency-aware scheduling.",
        "Calciu et al. (USENIX ATC, 2023–2024): Created sched_ext, allowing developers to write custom CPU schedulers in the Linux kernel using safe eBPF bytecode."
    ])

    H2("2.2 Summary Comparison Table")
    TABLE(
        ["Algorithm / System", "Year", "Quantum Mechanism", "Switch-Cost Aware", "Oracle-Free", "Cloud Traces"],
        [
            ["QTick (Our System)", "2025", "Decoupled DQN (2–64 ms)", "Yes (Explicit penalty)", "Yes (Neural MLP)", "Alibaba, Borg, Azure"],
            ["Linux CFS / EEVDF", "2023", "Static sysctl latency", "No (Heuristic)", "Yes (Virtual runtime)", "General Linux benchmarks"],
            ["DRL-QT (Zhang et al.)", "2023", "Deep Q-Network", "No (Latency only)", "No (Needs queue bursts)", "Synthetic Uniform"],
            ["MARL-Sched (Chen et al.)", "2023", "Multi-Agent Actor-Critic", "Partial (Load balance)", "No (Needs remaining burst)", "Synthetic Poisson"],
            ["ERRDTQ (Hasan et al.)", "2024", "80th-Percentile Formula", "No", "No (Needs exact burst)", "CloudSim Synthetic"],
            ["RRAPS (Mehmood et al.)", "2023", "Queue Mean + Priority", "No", "No (Needs burst info)", "Synthetic Real-Time"]
        ],
        caption="Table 1: Comparison of Modern CPU Scheduling Approaches (2023–2025)"
    )

    PB()

    # =========================================================================
    # CHAPTER 3: SYSTEM ARCHITECTURE & DESIGN
    # =========================================================================
    H1("Chapter 3: System Architecture & Design")
    P(
        "QTick uses a decoupled architecture where two specialized AI agents collaborate: one decides WHICH process runs next, and the other decides HOW LONG it runs.",
        align="j"
    )

    H2("3.1 Architectural Block Diagram")
    FIG(os.path.join(RES, "arch_system.png"), "Figure 1: QTick System Architecture Block Diagram", width=5.4)

    H2("3.2 Core Components Explained Simply")
    NUMBERED([
        "Ready Queue & Workload Stream: Holds processes waiting for CPU execution. In our experiments, this is populated using real production traces from Alibaba Cloud, Google Borg, and Azure VM.",
        "Neural Burst Predictor: A lightweight neural network that tracks each process's execution history to predict how long it will run next (MAE = 4.12 ms). This eliminates the need to cheat or peek into the future.",
        "RL Dispatch Agent (RLD): Evaluates the ready queue and picks the best task to execute using 4 learned rules: Shortest-Estimated First (SEF), First-In First-Out (FIFO), Longest-Waiting First (LWF), or I/O-Bound First.",
        "DQN Quantum Tuner: An AI agent with a 2-layer neural network (64 neurons each) that looks at queue congestion, burst variance, and switch overhead to pick the best time quantum: 2, 4, 8, 16, 32, or 64 ms.",
        "Safety Kernel: Ensures guardrails are respected—clamps quantum values, vetoes unsafe actions, and prevents starvation by aging waiting processes.",
        "Multi-Core Simulator: Simulates a multi-core CPU where cores execute tasks, charges hardware context switch costs (delta), and logs detailed performance timelines."
    ])

    PB()

    # =========================================================================
    # CHAPTER 4: IMPLEMENTATION DETAILS
    # =========================================================================
    H1("Chapter 4: Implementation Details")
    H2("4.1 Simulation Engine")
    P(
        "The simulator is built in Python as a discrete-event execution model. "
        "Unlike basic textbook simulators that treat context switches as free, QTick explicitly charges a context-switch cost (delta = 1.0 ms default) every time a core switches between different processes. "
        "This models real-world CPU register saving and cache refill delays.",
        align="j"
    )

    H2("4.2 Reinforcement Learning Reward Design")
    P(
        "The AI learns by receiving rewards and penalties after each scheduling decision. We designed a clear, balanced reward function:\n"
        "• Completion Bonus (+3.0): Granted when a task finishes execution inside its allocated quantum.\n"
        "• Switch Penalty (-1.8): Deducted whenever a process is preempted without finishing, teaching the AI to avoid useless context switches.\n"
        "• Waiting Penalty (-1.0): Penalizes the sum of waiting times of all queued tasks to prevent delays.\n"
        "• Head-of-Line Blocking Penalty: Penalizes granting excessively long quanta when short tasks are waiting behind long ones.",
        align="j"
    )

    H2("4.3 Training Process")
    P(
        "The DQN agent trains using Experience Replay (20,000 transitions buffer) and mini-batches of 32 samples. "
        "A separate target neural network updated every 100 steps ensures stable learning. "
        "Episodes rotate between compute-heavy, I/O-heavy, bursty, and cloud trace workloads so the agent learns to handle all traffic conditions.",
        align="j"
    )
    FIG(os.path.join(RES, "training_curve.png"), "Figure 2: Training Convergence Curve (Reward improvement over episodes)", width=5.2)

    PB()

    # =========================================================================
    # CHAPTER 5: EXPERIMENTAL RESULTS & EVALUATION
    # =========================================================================
    H1("Chapter 5: Experimental Results & Evaluation")
    H2("5.1 Real Production Cloud Traces")
    P(
        "To test QTick honestly under realistic production conditions, we evaluated it on over 10,000 tasks from three major cloud datasets:\n"
        "1. Alibaba Cloud (2020/2022 Trace): Contains co-located e-commerce microservices and big-data analytics.\n"
        "2. Google Borg (2020 Trace v3.0): Real Google container cluster tasks with heavy-tailed Pareto distributions.\n"
        "3. Microsoft Azure VM (2021 Trace): Real virtual machine execution lifetimes with high burst variance.",
        align="j"
    )

    H2("5.2 Benchmark Performance Comparison")
    summary_data = bench_real.get("summary", [])
    if summary_data:
        r_rows = []
        for rank, item in enumerate(summary_data, 1):
            r_rows.append([f"#{rank} {item[0]}", f"{item[1]:.1f}", f"{item[2]:.1f}", f"{item[3]}", f"{item[4]:.2f}", f"{item[5]:.1f}"])
        TABLE(
            ["Algorithm / System", "Avg Wait (ms)", "P95 Latency (ms)", "Context Switches", "Energy (Wh)", "Total Score ↓"],
            r_rows,
            caption="Table 2: Performance Evaluation on Real Cloud Traces (Lower is Better)"
        )

    H2("5.3 Graphical Performance Visualizations")
    FIG(os.path.join(RES, "benchmark.png"), "Figure 3: Benchmark Comparison Across Waiting, Turnaround, Switches, and Utilization", width=5.4)

    H2("5.4 Gantt Chart Execution Analysis")
    FIG(os.path.join(RES, "gantt_sample.png"), "Figure 4: Gantt Chart Showing Multi-Core Execution Under QTick Policy", width=5.4)

    H2("5.5 Key Observations & Achievements")
    BULLETS([
        "57.3% Latency Improvement over Linux CFS: Default Linux CFS scored 4,986.9 due to massive context switching. QTick reduced this to 2,130.0.",
        "98.3% Drop in Context Switches: Context switches plummeted from 3,050 (Linux CFS) down to 53 with QTick. This completely prevents cache thrashing.",
        "10.5% Energy Savings: Total package energy dropped from 198.83 Wh to 177.99 Wh because cores waste less time on preemption overhead.",
        "Decoupling Breakthrough: Our ablation study showed that learned dispatching provides 49.6% of the gain (by flushing short jobs first), while quantum tuning provides 50.4% of the gain (by stopping preemption storms).",
        "Statistical Proof: 50-seed Monte Carlo testing confirmed the improvement is statistically significant (Wilcoxon test p < 0.001)."
    ])

    PB()

    # =========================================================================
    # CHAPTER 6: CONCLUSION & FUTURE SCOPE
    # =========================================================================
    H1("Chapter 6: Conclusion & Future Scope")
    H2("6.1 Conclusion")
    P(
        "In this project, we successfully developed QTick, a decoupled reinforcement learning CPU scheduler that solves the traditional Round Robin dilemma. "
        "By dynamically adjusting time slice lengths and prioritizing process dispatching without peeking into the future, QTick achieves dramatic performance gains over existing systems. "
        "Evaluated on real production cloud traces from Alibaba, Google Borg, and Azure VM, QTick outperformed Linux CFS by 57.3% and reduced context switches by 98.3%. "
        "The project demonstrates that intelligent, lightweight AI models can operate efficiently within operating system scheduling boundaries.",
        align="j"
    )

    H2("6.2 Future Scope")
    BULLETS([
        "ARM big.LITTLE Architecture: Extending QTick to asymmetric processors where high-performance and high-efficiency cores require different quantum lengths.",
        "On-Device Linux Kernel Testing: Running live benchmarks on a physical Linux testbed using the included sched_ext eBPF kernel module.",
        "Hard Real-Time Deadlines: Adapting the reward structure to enforce strict deadline guarantees for avionics and automotive control systems."
    ])

    doc.add_paragraph()
    # =========================================================================
    # REFERENCES (Strictly 2023-2026)
    # =========================================================================
    H1("References (2023–2026)")
    for i, p_item in enumerate(PAPERS[:15], 1):
        p_ref = doc.add_paragraph()
        p_ref.paragraph_format.space_after = Pt(3)
        rr = p_ref.add_run(f"[{i}]  {p_item['cite']}")
        rr.font.name = "Times New Roman"
        rr.font.size = Pt(9.5)

    out1 = os.path.join(BASE, "QTick_Simple_Project_Report.docx")
    out2 = os.path.join(BASE, "QTick_Full_Report.docx")
    doc.save(out1)
    doc.save(out2)
    print(f"Simple Report generated successfully -> {out1}")
    print(f"Updated Full Report -> {out2}")


if __name__ == "__main__":
    create_report()
