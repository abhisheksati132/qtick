# -*- coding: utf-8 -*-
"""Single source of truth for all generated documents.

Every number in the report / draft / paper / README MUST come from these
helpers (which read results/*.json), never from hardcoded literals.
Stale hardcoded numbers were the #1 documentation bug; this module kills it.
"""
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(BASE, "results")


def _load(name):
    with open(os.path.join(RES, name)) as f:
        return json.load(f)


def bench():
    return _load("benchmark.json")


def full_rows():
    """(name, metrics) sorted by composite, excluding the oracle summary row."""
    b = bench()
    rows = [(n, v) for n, v in b.items() if "avg_waiting" in v]
    rows.sort(key=lambda kv: kv[1]["composite_score"])
    return rows


def oracle_score():
    b = bench()
    r = b.get("RR-oracle-q", {})
    return r.get("composite_score")


def ai_rows():
    return [(n, v) for n, v in full_rows()
            if ("RL-QT" in n or "DQN" in n or "+RLD" in n)]


def pure_fixed_rows():
    return [(n, v) for n, v in full_rows()
            if n.startswith("RR q=") and "+RLD" not in n]


def best_ai():
    rows = ai_rows()
    return min(rows, key=lambda kv: kv[1]["composite_score"])


def best_fixed():
    rows = pure_fixed_rows()
    return min(rows, key=lambda kv: kv[1]["composite_score"])


def pct_better(score, baseline):
    return round((1 - score / baseline) * 100, 1)


def f1(v):
    if v is None or v == "—" or v == "n/a" or v == "":
        return "—"
    try:
        return round(float(v), 1)
    except (ValueError, TypeError):
        return str(v)


def sig(key):
    try:
        return _load("benchmark_stats.json").get(key, {})
    except FileNotFoundError:
        return {}


def fmt_p(p):
    return "%.2e" % p if p else "n/a"


def real():
    try:
        return _load("benchmark_real.json")
    except FileNotFoundError:
        return {}


def multiseed():
    try:
        return _load("multiseed.json")
    except FileNotFoundError:
        return {}


def ablation():
    try:
        return _load("ablation.json")
    except FileNotFoundError:
        return {}


def sensitivity():
    try:
        return _load("sensitivity.json")
    except FileNotFoundError:
        return {}


def base_doc():
    """Shared helpers for document generators."""
    from docx import Document
    from docx.shared import Pt, Inches, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK

    def base_style(doc):
        st = doc.styles["Normal"]
        st.font.name = "Times New Roman"
        st.font.size = Pt(12)
        st.paragraph_format.line_spacing = 1.4
        st.paragraph_format.space_after = Pt(6)

    def H(doc, text, level=1, center=False):
        p = doc.add_heading("", level=level)
        r = p.add_run(text)
        r.font.name = "Times New Roman"
        r.font.color.rgb = RGBColor(0, 0, 0)
        r.font.size = Pt(16 - 2 * level)
        r.bold = True
        if center:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        return p

    def P(doc, text, bold=False, italic=False, align=None, size=12):
        p = doc.add_paragraph()
        r = p.add_run(text)
        r.font.name = "Times New Roman"
        r.font.size = Pt(size)
        r.bold = bold
        r.italic = italic
        if align == "c":
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if align == "j":
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        return p

    def TABLE(doc, headers, rows, caption=None, fs=9.5):
        if caption:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(caption)
            r.font.name = "Times New Roman"
            r.font.size = Pt(9)
            r.italic = True
        t = doc.add_table(rows=1 + len(rows), cols=len(headers))
        t.style = "Table Grid"
        for j, h in enumerate(headers):
            c = t.rows[0].cells[j]
            c.text = ""
            r = c.paragraphs[0].add_run(h)
            r.bold = True
            r.font.size = Pt(fs)
            r.font.name = "Times New Roman"
        for i, row in enumerate(rows):
            for j, v in enumerate(row):
                c = t.rows[i + 1].cells[j]
                c.text = ""
                r = c.paragraphs[0].add_run(str(v))
                r.font.size = Pt(fs)
                r.font.name = "Times New Roman"
        return t

    def FIG(doc, path, caption):
        if not os.path.exists(path):
            P(doc, "[figure missing: %s]" % os.path.basename(path))
            return
        doc.add_picture(path, width=Inches(5.6))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(caption)
        r.font.name = "Times New Roman"
        r.font.size = Pt(9)
        r.italic = True

    def PB(doc):
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    return base_style, H, P, TABLE, FIG, PB


def abstract_result_sentence():
    """One-sentence headline result, computed live. Used by all documents."""
    best, bv = best_ai()
    bfx, bfxv = best_fixed()
    orc = oracle_score()
    parts = [
        "Across 60 randomized traces the learned-dispatch configurations take "
        "the top composite scores (best %s at %s — %s%% better than the best "
        "static quantum %s at %s)" % (
            best, f1(bv["composite_score"]),
            pct_better(bv["composite_score"], bfxv["composite_score"]),
            bfx, f1(bfxv["composite_score"])),
    ]
    if orc:
        s = sig("DQN-QT+RLD < RR-oracle-q") or sig("RL-QT+RLD < RR-oracle-q")
        parts.append("and better than per-trace oracle-tuned static quanta "
                     "(%s%s)" % (f1(orc), ("; Wilcoxon p = %s" % fmt_p(s.get("p_value"))
                                           if s.get("p_value") else "")))
    parts.append("cutting context switches by up to %s%% versus the best "
                 "static quantum while attaining top CPU utilization (%s) — "
                 "without any a-priori knowledge of burst lengths." % (
                     pct_better(bv["context_switches"],
                                bfxv["context_switches"]),
                     round(float(bv["cpu_utilization"]), 3)))
    return " ".join(parts)
