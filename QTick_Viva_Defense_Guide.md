# QTick: Comprehensive Faculty Viva & Review Defense Guide

> **Project:** QTick — Reinforcement-Learning-Driven Dynamic Time Quantum Tuning and Decoupled Dispatching in Multiprocessing CPU Schedulers  
> **Authors:** Abhishek Sati, Tanishtha Swami  
> **Project Guide:** Prof. Ruby D (Senior Member, IEEE)  
> **Department:** School of Computer Science and Engineering (SCOPE), Vellore Institute of Technology (VIT), Vellore  
> **Submission Files:**  
> - Research Paper (Word): [`QTick_Final_Project_Report.docx`](file:///C:/Users/abhis/Downloads/project-base/osproject/QTick_Final_Project_Report.docx)  
> - Research Paper (PDF): [`QTick_Final_Project_Report.pdf`](file:///C:/Users/abhis/Downloads/project-base/osproject/QTick_Final_Project_Report.pdf) (17 Pages, IEEE Single-Column)  
> - Presentation Slides (PPTX): [`QTick_Defense_Presentation.pptx`](file:///C:/Users/abhis/Downloads/project-base/osproject/QTick_Defense_Presentation.pptx) (12 Slides, 16:9 Widescreen)  
> - Presentation Slides (PDF): [`QTick_Defense_Presentation.pdf`](file:///C:/Users/abhis/Downloads/project-base/osproject/QTick_Defense_Presentation.pdf)  

---

## 1. The 60-Second Elevator Pitch (What to Say at the Start)

> *"Good morning Ma'am and esteemed panel members. Our research project is **QTick**, an adaptive multi-agent reinforcement learning CPU scheduling framework for multi-core operating systems.*
>
> *For over four decades, CPU schedulers have faced the classical **Round Robin Time-Quantum Dilemma**: configure the time quantum too small, and you cause severe **preemption thrashing**, cache line evictions, and up to **350 μs of CPI microarchitectural delay** per switch; configure it too large, and short interactive tasks suffer severe **convoy delays** behind long batch jobs.*
>
> *Existing schedulers like Linux CFS and EEVDF rely on static sysctl latency knobs that cannot track bursty cloud workloads. Meanwhile, recent 2023–2025 academic heuristics either assume future burst knowledge (oracle prescience) or suffer from exponential action-space explosion.*
>
> *We solve this with **QTick**: we decouple per-dispatch quantum tuning (using a lightweight Deep Q-Network) from queue dispatch prioritization (using an online neural burst predictor). Evaluated on over **10,000 real production tasks** from Alibaba Cloud, Google Borg, and Microsoft Azure VM traces, QTick achieves a **57.3% lower composite score than Linux CFS**, slashes involuntary context switches by **98.3%** (from 3,050 down to 53), saves **10.5% package energy**, and executes with a sub-microsecond in-kernel dispatch latency of **0.42 μs** via eBPF and sched_ext. All improvements are statistically significant at **p < 0.001**."*

---

## 2. Key Numbers Cheat Sheet (Memorize These 5 Numbers)

| Metric | Baseline (Linux CFS / RR) | QTick (Ours) | Quantified Improvement |
| :--- | :--- | :--- | :--- |
| **Composite Latency Score** | `4,986.9` (CFS) | **`2,130.0`** | **57.3% Lower (Rank #1)** |
| **Involuntary Context Switches** | `3,050` switches | **`53` switches** | **98.3% Preemption Reduction** |
| **Package Energy Consumption** | `198.83 Wh` | **`177.99 Wh`** | **10.5% Energy Saved (Intel RAPL)** |
| **In-Kernel Decision Latency** | `1.0 μs` (Timer threshold) | **`0.42 μs`** | **Line-Rate eBPF / sched_ext verified** |
| **Statistical Significance** | Null Hypothesis ($H_0$) | **$p = 4.49 \times 10^{-9}$** | **Statistically Significant ($r = 0.734$, Large effect)** |

---

## 3. Anticipated Tough Faculty Questions & Bullet-Proof Answers

### Q1: *"How can you predict CPU burst time in an operating system without cheating or knowing the future?"*
**Your Answer:**  
> *"Ma'am, that was one of the biggest flaws we identified in prior 2023–2024 papers (like Hasan et al. in PLOS ONE 2024 and Qazi et al. 2023), which cheat by using oracle prescience.*  
> *In QTick, **we never peek into the future**. Instead, we employ an online Multi-Layer Perceptron (MLP) burst predictor that tracks only past historical execution bursts (a sliding window of the last 4 runs) combined with exponential moving averages, with a Mean Absolute Error of 4.12 ms.*  
> *This is conceptually identical to how modern hardware branch predictors and TCP round-trip-time estimators function in production operating systems. Our ablation study in Table V shows that even with imperfect burst estimation, QTick still outperforms static schedulers by over 13%."*

---

### Q2: *"Reinforcement learning and neural networks are too slow for the OS kernel. How do you meet line-rate scheduling budgets?"*
**Your Answer:**  
> *"That is precisely why we introduced our **Decoupled Architecture**.*  
> *Prior RL schedulers (like Zhang et al. at IEEE ICPP 2023) created a monolithic network where action space $|A| = N_{\text{procs}} \times |Q_{\text{ladder}}| = 300$, resulting in multi-millisecond inference latencies.*  
> *QTick decouples this into:*  
> *1. A tiny DQN network (6 inputs, 64 hidden, 64 hidden, 6 outputs) containing only **4,998 parameters (19.5 KB)** that computes in **0.18 μs** on AVX2 vector instructions.*  
> *2. A binary heap dispatch extraction that executes in $\mathcal{O}(\log N_q)$ (**0.12 μs**).*  
> *The total end-to-end kernel dispatch decision latency is **0.42 μs**, verified via lock-free BPF ring buffers on Linux 6.6+ with `sched_ext`.*  
> *Furthermore, the complete working memory footprint is **58.67 KB**, which fits entirely within the **64 KB L1 cache** of modern processors, incurring zero memory-bus stalls."*

---

### Q3: *"Why not just use the standard Linux CFS or the new EEVDF scheduler in Linux Kernel 6.6?"*
**Your Answer:**  
> *"Linux CFS and EEVDF rely on static sysctl configuration parameters—specifically `min_granularity_ns` (typically 0.75 ms) and `latency_ns` (6 ms).*  
> *Under bursty, multi-tenant cloud workloads (such as co-located microservices and big-data containers in Alibaba Cloud), queue variance shifts rapidly from 2 ms to over 2,000 ms.*  
> *Because CFS cannot dynamically widen its preemption granularity, it suffers from **preemption thrashing**: it produced **3,050 context switches** in our benchmark, causing severe cache line evictions and inflating CPI by 350 μs per preemption.*  
> *QTick dynamically widens time slices up to 64 ms for compute-bound tasks while preserving 2–4 ms slices for interactive tasks, cutting context switches by 98.3% and reducing latency by 57.3%."*

---

### Q4: *"What prevents the reinforcement learning agent from misbehaving, getting stuck, or causing process starvation?"*
**Your Answer:**  
> *"We do not allow the neural network unconstrained control over kernel scheduling. In Section III-F of our paper, we introduce a formal **Lyapunov Drift Safety Kernel** that enforces three strict invariants:*  
> *1. **Work-Conservation**: The CPU never idles when ready tasks exist.*  
> *2. **Anti-Starvation Aging Bound**: We set an aging threshold $\tau_{\text{starve}} = 50.0\,\text{ms}$. If any task's queue waiting age exceeds 50 ms, the safety kernel forcibly overrides the RL policy and grants immediate execution priority.*  
> *3. **Action Bounding**: Quantum choices are restricted to a safe physical ladder $\mathcal{A} \in \{2, 4, 8, 16, 32, 64\}\,\text{ms}$, preventing infinite loops or timer-interrupt starvation."*

---

### Q5: *"Are your results tested on real workloads or synthetic toy data?"*
**Your Answer:**  
> *"Ma'am, we used **100% real industrial cloud datasets**:*  
> *1. **Alibaba Cloud Trace (2018/2020)**: Real containerized cloud service logs featuring asymmetric, heavy-tailed burst distributions (mean burst 40.3 ms).*  
> *2. **Google Borg Cluster Trace (2019/2020)**: Production traces from Google's cell cluster manager with rapid arrival rates and short interactive bursts (mean burst 21.7 ms).*  
> *3. **Microsoft Azure VM Workload Trace (2020/2021)**: First-party virtual machine execution lifetimes (mean burst 38.5 ms).*  
> *We performed zero synthetic smoothing, zero artificial Poisson injection, and strictly excluded all obsolete 1990s traces like NASA logs. All tests were executed across **50 Monte Carlo trials** with randomized task offsets and arrival jitters."*

---

### Q6: *"How do you prove that both the RL quantum tuner and the dispatch prioritizer are necessary?"*
**Your Answer:**  
> *"We conducted a comprehensive **Factorial Ablation Study** across 30 evaluation runs, documented in Table V of our paper:*  
> *- **Full QTick (Config E)**: Mean wait time = **812.5 ms** (Reference).*  
> *- **Without RL-QT (Config D)**: Replacing dynamic quantum with static $q=16$ ms increases wait time to **880.6 ms (+8.4% penalty)**.*  
> *- **Without Predictor (Config C)**: Replacing the neural MLP with linear EWMA increases wait time to **914.7 ms (+12.6% penalty)**.*  
> *- **Without Dispatcher (Config B)**: Using FIFO queue ordering with RL-QT increases wait time to **901.7 ms (+11.0% penalty)**.*  
> *- **Baseline System (Config A)**: Static $q=16$ ms with FIFO increases wait time to **947.5 ms (+16.6% penalty)**.*  
> *This scientifically proves that neither dynamic quantum tuning alone nor intelligent dispatching alone can solve the dilemma; **both agents are synergistically required**."*

---

### Q7: *"How does reducing context switches reduce hardware energy consumption?"*
**Your Answer:**  
> *"In multi-core processors, an involuntary context switch is not merely a register save. When a core switches threads, the existing process's cache lines are evicted from the private L1 and L2 caches.*  
> *When that process resumes, it experiences high L1/L2 miss rates, requiring pipeline stalls and off-core memory requests over the high-power memory interconnect.*  
> *By cutting context switches from 3,050 down to 53, QTick preserves microarchitectural cache warmness. Using the standard Intel RAPL (Running Average Power Limit) energy model, this reduced overall package energy consumption by **10.5% (from 198.83 Wh down to 177.99 Wh)**, as shown in Table II and Section V-F."*

---

## 4. Slide-by-Slide Defense Walkthrough (Slide Deck Structure)

| Slide # | Slide Title | Key Point to Deliver | Figure / Table Reference |
| :---: | :--- | :--- | :--- |
| **1** | Title Slide | Introduce team, project title, guide (Prof. Ruby D), and IEEE scope. | Title Block |
| **2** | Executive Summary | Highlight the 4 stat cards: 57.3% latency drop, 98.3% switch drop, 10.5% energy saved, 0.42 μs eBPF speed. | 4 Metric Cards |
| **3** | Problem Statement | Explain the Round Robin trade-off (preemption thrashing vs convoy delay) and why CFS/EEVDF fail. | Theoretical Analysis |
| **4** | System Architecture | Walk through the 6-layer decoupled design, highlighting the two cooperating RL agents. | `arch_system.png` |
| **5** | Microarchitecture & L1 Cache | Explain the composite reward (preemption penalty $\delta=1.0$ ms) and show model fits in 64 KB L1 cache. | Equations (3)-(5) |
| **6** | Empirical Cloud Traces | Detail Alibaba Cloud, Google Borg, and Azure VM traces (10,000+ real tasks, no NASA traces). | Datasets Summary |
| **7** | Benchmark Visualizations | Point to the Royal Blue QTick bar dominating all 4 subplots in the benchmark figure. | `benchmark.png` |
| **8** | SOTA Literature Comparison | Show Table III: QTick outperforms Hasan (2024), Li (2024), Zhang (2023), and Linux CFS. | Table III |
| **9** | Component Ablation Study | Walk through Table V (Configs A to E) proving dual-agent synergy and neural predictor necessity. | Table V |
| **10** | Statistical Significance & Kernel | Present Wilcoxon tests ($p = 4.49 \times 10^{-9}, r = 0.734$) and in-kernel eBPF verification (0.42 μs). | Table VI |
| **11** | Viva Voce Defense Guide | Address the top 4 examiner questions preemptively (burst prediction, kernel latency, CFS, safety). | Viva Cheat Sheet |
| **12** | Conclusion & Future Scope | Summarize scientific contribution and propose ARM big.LITTLE and NUMA interconnect future scope. | Conclusion Block |

---

## 5. Repository File Index

- **Final IEEE Report (DOCX):** [`QTick_Final_Project_Report.docx`](file:///C:/Users/abhis/Downloads/project-base/osproject/QTick_Final_Project_Report.docx)  
- **Final IEEE Report (PDF):** [`QTick_Final_Project_Report.pdf`](file:///C:/Users/abhis/Downloads/project-base/osproject/QTick_Final_Project_Report.pdf) (17 pages, clean IEEE single-column layout)  
- **Defense Slide Deck (PPTX):** [`QTick_Defense_Presentation.pptx`](file:///C:/Users/abhis/Downloads/project-base/osproject/QTick_Defense_Presentation.pptx) (12 widescreen 16:9 slides)  
- **Defense Slide Deck (PDF):** [`QTick_Defense_Presentation.pdf`](file:///C:/Users/abhis/Downloads/project-base/osproject/QTick_Defense_Presentation.pdf)  
- **Report Generator Script:** [`scripts/make_final_report.py`](file:///C:/Users/abhis/Downloads/project-base/osproject/scripts/make_final_report.py)  
- **Presentation Generator Script:** [`scripts/make_defense_presentation.py`](file:///C:/Users/abhis/Downloads/project-base/osproject/scripts/make_defense_presentation.py)  
- **Architecture Diagram Generator:** [`scripts/make_clean_arch.py`](file:///C:/Users/abhis/Downloads/project-base/osproject/scripts/make_clean_arch.py) $\to$ [`results/arch_system.png`](file:///C:/Users/abhis/Downloads/project-base/osproject/results/arch_system.png)  
- **Benchmark Plotter:** [`scripts/plot_results.py`](file:///C:/Users/abhis/Downloads/project-base/osproject/scripts/plot_results.py) $\to$ [`results/benchmark.png`](file:///C:/Users/abhis/Downloads/project-base/osproject/results/benchmark.png)  
- **Unit & Integration Test Suite:** `python -m pytest` (27/27 tests PASS)
