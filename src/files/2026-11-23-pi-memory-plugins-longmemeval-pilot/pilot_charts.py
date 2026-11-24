"""Render the LongMemEval pilot figures as SVG from samples.csv.

Input : samples.csv (one row per graded sample, exported from the Inspect logs by analyze.py), staged in
        src/files/2026-11-23-pi-memory-plugins-longmemeval-pilot/
Output: src/images/2026-11-23-pi-memory-plugins-longmemeval-pilot/answer-grid.svg   (every one of the 280 grades)
        src/images/2026-11-23-pi-memory-plugins-longmemeval-pilot/query-latency.svg (every sample's query time)

Every plotted value comes from samples.csv. Nothing is aggregated except the per-column accuracy labels.
"""
import csv
import math
import os
import random

ROOT = os.environ.get("REGULAR_LABS_ROOT") or "/home/user/code/regular-labs"
SLUG = "2026-11-23-pi-memory-plugins-longmemeval-pilot"
SAMPLES = os.path.join(ROOT, "src", "files", SLUG, "samples.csv")
OUT = os.path.join(ROOT, "src", "images", SLUG)

ARMS = ["none", "pi-memory", "pi-mem0", "pi-mem"]
READERS = ["original", "openuncensored", "unbound", "atomicchat", "qwen38"]
READER_LABEL = {"original": "Orig", "openuncensored": "OpenU", "unbound": "Unb", "atomicchat": "Atom", "qwen38": "Qwen"}
CATEGORIES = ["abstention", "single-session-user", "single-session-assistant", "single-session-preference",
              "multi-session", "knowledge-update", "temporal-reasoning"]
INK, MUTED, GRID = "#1a1a1a", "#6b6b6b", "#ececec"
YES, NO = "#2f6f4f", "#e6e6e6"

with open(SAMPLES) as fh:
    rows = list(csv.DictReader(fh))
if len(rows) != len(ARMS) * len(READERS) * 14:
    raise SystemExit(f"expected 280 samples, found {len(rows)}")
grade = {(r["reader"], r["memory"], r["question_id"]): int(r["correct"]) for r in rows}
questions = sorted({(r["category"], r["question_id"]) for r in rows}, key=lambda q: (CATEGORIES.index(q[0]), q[1]))


def text(x, y, s, size=11, fill=MUTED, anchor="start", weight="normal", rotate=None):
    t = f' transform="rotate({rotate} {x:.1f} {y:.1f})"' if rotate is not None else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" font-weight="{weight}"{t}>{s}</text>'


def grid_chart():
    cell, gap, arm_gap = 22, 3, 16
    left, top = 236, 128
    width = left + len(ARMS) * (len(READERS) * (cell + gap) + arm_gap) + 20
    height = top + len(questions) * (cell + gap) + 64
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" font-family="Helvetica,Arial,sans-serif">',
           f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
           text(20, 28, "All 280 grades: 14 LongMemEval-S questions, 4 memory arms, 5 local readers", 15, INK, weight="bold"),
           text(20, 48, "Filled = judged correct by the official LongMemEval prompt; grey = incorrect. Bottom row: accuracy per column (n = 14).", 11.5)]
    x0 = {}
    x = left
    for arm in ARMS:
        x0[arm] = x
        span = len(READERS) * (cell + gap) - gap
        out.append(text(x + span / 2, 76, arm, 13, INK, "middle", "bold"))
        for i, reader in enumerate(READERS):
            out.append(text(x + i * (cell + gap) + cell / 2 + 4, top - 8, READER_LABEL[reader], 10, MUTED, "start", rotate=-60))
        x += len(READERS) * (cell + gap) + arm_gap
    previous = None
    for j, (category, qid) in enumerate(questions):
        y = top + j * (cell + gap)
        if category != previous:
            out.append(text(20, y + cell - 6, category, 11, INK, weight="bold"))
            previous = category
        out.append(text(left - 10, y + cell - 7, qid, 10, MUTED, "end"))
        for arm in ARMS:
            for i, reader in enumerate(READERS):
                cx = x0[arm] + i * (cell + gap)
                fill = YES if grade[(reader, arm, qid)] else NO
                out.append(f'<rect x="{cx:.1f}" y="{y:.1f}" width="{cell}" height="{cell}" rx="3" fill="{fill}"/>')
    y = top + len(questions) * (cell + gap) + 18
    out.append(text(left - 10, y, "accuracy", 10.5, INK, "end", "bold"))
    for arm in ARMS:
        for i, reader in enumerate(READERS):
            acc = sum(grade[(reader, arm, q)] for _, q in questions) / len(questions)
            out.append(text(x0[arm] + i * (cell + gap) + cell / 2, y, f"{round(acc * 100)}", 10, INK, "middle"))
    out.append("</svg>")
    with open(os.path.join(OUT, "answer-grid.svg"), "w") as fh:
        fh.write("\n".join(out) + "\n")


def latency_chart():
    width, height = 860, 450
    left, right, top, bottom = 74, 30, 70, 360
    lo, hi = 1.0, 1000.0
    y_of = lambda s: bottom - (math.log10(max(s, lo)) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)) * (bottom - top)
    band = (width - left - right) / len(ARMS)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" font-family="Helvetica,Arial,sans-serif">',
           f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
           text(20, 28, "Query time per answer, every sample (log scale)", 15, INK, weight="bold"),
           text(20, 48, "Wall time of one Pi run, retrieval plus answer, on one RTX 3090. Filled = correct, hollow = incorrect; jitter within an arm is cosmetic.", 11.5)]
    for tick in (1, 2, 5, 10, 20, 50, 100, 200, 600):
        y = y_of(tick)
        out.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        out.append(text(left - 8, y + 4, f"{tick} s", 10.5, MUTED, "end"))
    rng = random.Random(7)
    for k, arm in enumerate(ARMS):
        cx = left + band * (k + 0.5)
        out.append(text(cx, bottom + 24, arm, 12.5, INK, "middle", "bold"))
        values = sorted(float(r["query_seconds"]) for r in rows if r["memory"] == arm)
        median = values[len(values) // 2] if len(values) % 2 else (values[len(values) // 2 - 1] + values[len(values) // 2]) / 2
        out.append(f'<line x1="{cx - band * 0.32:.1f}" y1="{y_of(median):.1f}" x2="{cx + band * 0.32:.1f}" y2="{y_of(median):.1f}" stroke="{INK}" stroke-width="2"/>')
        out.append(text(cx, bottom + 40, f"median {median:.1f} s", 11, MUTED, "middle"))
        for r in rows:
            if r["memory"] != arm:
                continue
            x = cx + rng.uniform(-band * 0.28, band * 0.28)
            y = y_of(float(r["query_seconds"]))
            style = f'fill="{YES}"' if r["correct"] == "1" else f'fill="none" stroke="{MUTED}" stroke-width="1"'
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" {style} opacity="0.85"/>')
    out.append(text(left, bottom + 70, "n = 70 per arm (14 questions × 5 readers). The horizontal bar is the arm's median. The point at 602 s hit the 600 s cap.", 10.5))
    out.append("</svg>")
    with open(os.path.join(OUT, "query-latency.svg"), "w") as fh:
        fh.write("\n".join(out) + "\n")


os.makedirs(OUT, exist_ok=True)
grid_chart()
latency_chart()
print(f"wrote {OUT}/answer-grid.svg and query-latency.svg from {len(rows)} samples")
