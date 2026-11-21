"""Render the Inkling 2 Mini VRAM/utilization timeline as an SVG.

Input : the harness's own 0.5 s nvidia-smi samples (gpu-samples.txt, staged in
        src/files/2026-11-21-inkling2-mini-3090-smoke/). Columns:
        unix_timestamp, memory_used_mib, utilization_pct
Output: src/images/2026-11-21-inkling2-mini-3090-smoke/vram-utilization.svg

Every plotted value comes from the samples file. Nothing is smoothed.
"""
import os
import re

ROOT = os.environ.get("REGULAR_LABS_ROOT") or "/home/user/code/regular-labs"
SLUG = "2026-11-21-inkling2-mini-3090-smoke"
SAMPLES = os.path.join(ROOT, "src", "files", SLUG, "gpu-samples.txt")
OUT = os.path.join(ROOT, "src", "images", SLUG, "vram-utilization.svg")

rows = []
with open(SAMPLES) as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        ts, mib, util = line.split()
        rows.append((float(ts), int(mib), int(util)))
if not rows:
    raise SystemExit(f"no samples parsed from {SAMPLES}")

t0 = rows[0][0]
samples = [(t - t0, mib, util) for t, mib, util in rows]
span = samples[-1][0]
peak_vram = max(s[1] for s in samples)
peak_util = max(s[2] for s in samples)
used_capacity_note = f"peak {peak_vram:,} MiB of 24,576 MiB"

W, H = 860, 520
LEFT, RIGHT = 74, 30
TOP_A, BOTTOM_A = 78, 268
TOP_B, BOTTOM_B = 306, 404


def x_of(t):
    return LEFT + (t / span) * (W - LEFT - RIGHT)


def y_of_vram(mib):
    return BOTTOM_A - (mib / CAP) * (BOTTOM_A - TOP_A)


def y_of_util(pct):
    return BOTTOM_B - (pct / 100.0) * (BOTTOM_B - TOP_B)


CAP = 25600  # y-axis top for the VRAM panel, chosen to leave headroom over the card

parts = []
parts.append(
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
    f'width="{W}" height="{H}" font-family="Helvetica,Arial,sans-serif">'
)
parts.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
parts.append(
    '<text x="20" y="28" font-size="15" font-weight="bold" fill="#1a1a1a">'
    "One RTX 3090 over 12.7 seconds: the weights land, and the card stays above "
    "75% utilization</text>"
)
parts.append(
    '<text x="20" y="48" font-size="11.5" fill="#6b6b6b">'
    "nvidia-smi at 0.5 s intervals during the single 320-token generation "
    f"(peak {peak_vram:,} MiB, peak utilization {peak_util}%). Dashed line is the "
    "card's 24,576 MiB capacity.</text>"
)

# --- panel A: VRAM used -----------------------------------------------------
parts.append(
    f'<text x="{LEFT}" y="{TOP_A - 16}" font-size="12" font-weight="bold" '
    'fill="#1a1a1a">VRAM used (MiB)</text>'
)
for tick in (0, 5000, 10000, 15000, 20000, 25000):
    y = y_of_vram(tick)
    parts.append(
        f'<line x1="{LEFT}" y1="{y:.1f}" x2="{W - RIGHT}" y2="{y:.1f}" '
        'stroke="#ececec" stroke-width="1"/>'
    )
    parts.append(
        f'<text x="{LEFT - 8}" y="{y + 4:.1f}" font-size="10.5" '
        f'text-anchor="end" fill="#6b6b6b">{tick:,}</text>'
    )
cap_y = y_of_vram(24576)
parts.append(
    f'<line x1="{LEFT}" y1="{cap_y:.1f}" x2="{W - RIGHT}" y2="{cap_y:.1f}" '
    'stroke="#b03a2e" stroke-width="1.2" stroke-dasharray="5 4"/>'
)
parts.append(
    f'<text x="{W - RIGHT}" y="{cap_y - 6:.1f}" font-size="10.5" '
    'text-anchor="end" fill="#b03a2e">card capacity 24,576 MiB</text>'
)

line = " ".join(f"{x_of(t):.1f},{y_of_vram(m):.1f}" for t, m, _ in samples)
parts.append(
    f'<polyline points="{line}" fill="none" stroke="#1f6f8b" '
    'stroke-width="2" stroke-linejoin="round"/>'
)
for t, m, _ in samples:
    parts.append(
        f'<circle cx="{x_of(t):.1f}" cy="{y_of_vram(m):.1f}" r="2.1" fill="#1f6f8b"/>'
    )

# --- panel B: utilization ---------------------------------------------------
parts.append(
    f'<text x="{LEFT}" y="{TOP_B - 12}" font-size="12" font-weight="bold" '
    'fill="#1a1a1a">GPU utilization (%)</text>'
)
for tick in (0, 25, 50, 75, 100):
    y = y_of_util(tick)
    parts.append(
        f'<line x1="{LEFT}" y1="{y:.1f}" x2="{W - RIGHT}" y2="{y:.1f}" '
        'stroke="#ececec" stroke-width="1"/>'
    )
    parts.append(
        f'<text x="{LEFT - 8}" y="{y + 4:.1f}" font-size="10.5" '
        f'text-anchor="end" fill="#6b6b6b">{tick}</text>'
    )
line = " ".join(f"{x_of(t):.1f},{y_of_util(u):.1f}" for t, _, u in samples)
parts.append(
    f'<polyline points="{line}" fill="none" stroke="#b45309" '
    'stroke-width="2" stroke-linejoin="round"/>'
)
for t, _, u in samples:
    parts.append(
        f'<circle cx="{x_of(t):.1f}" cy="{y_of_util(u):.1f}" r="2.1" fill="#b45309"/>'
    )

# --- shared x axis ----------------------------------------------------------
axis_y = BOTTOM_B + 16
parts.append(
    f'<line x1="{LEFT}" y1="{axis_y}" x2="{W - RIGHT}" y2="{axis_y}" '
    'stroke="#c9c9c9" stroke-width="1"/>'
)
tick = 0.0
while tick <= span + 0.01:
    x = x_of(tick)
    parts.append(
        f'<line x1="{x:.1f}" y1="{axis_y}" x2="{x:.1f}" y2="{axis_y + 4}" '
        'stroke="#c9c9c9" stroke-width="1"/>'
    )
    parts.append(
        f'<text x="{x:.1f}" y="{axis_y + 17}" font-size="10.5" '
        f'text-anchor="middle" fill="#6b6b6b">{tick:.0f}</text>'
    )
    tick += 2.0
loaded_at = next(t for t, m, _ in samples if m > 15000)
early_peak = max(u for t, _, u in samples if t < loaded_at + 3.0)
low = 0
for i, (_, _, u) in enumerate(samples):
    if u < 75:
        low = i
tail = samples[low + 1:]
tail_from = tail[0][0]
tail_lo = min(u for _, _, u in tail)
tail_hi = max(u for _, _, u in tail)
if tail_lo == tail_hi:
    hold = f"holds {tail_hi}%"
else:
    hold = f"stays between {tail_lo}% and {tail_hi}%"
parts.append(
    f'<text x="{(LEFT + W - RIGHT) / 2:.0f}" y="{axis_y + 34}" font-size="11" '
    'text-anchor="middle" fill="#6b6b6b">seconds from the first sample</text>'
)
parts.append(
    f'<text x="{(LEFT + W - RIGHT) / 2:.0f}" y="{axis_y + 50}" font-size="11" '
    'text-anchor="middle" fill="#6b6b6b">'
    f"Weights are resident by t={loaded_at:.1f} s; utilization spikes to "
    f"{early_peak}% for the load, then, from t={tail_from:.1f} s to the last "
    f"sample, {hold}.</text>"
)
parts.append(
    f'<text x="20" y="{H - 10}" font-size="10.5" fill="#8a8a8a">'
    "Source: results.json / gpu-samples.txt from build #7, "
    "pipeline inkling2-mini-smoke.</text>"
)
parts.append("</svg>")

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as fh:
    fh.write("\n".join(parts) + "\n")
print(f"wrote {OUT}")
print(f"samples={len(samples)} span={span:.2f}s peak_vram={peak_vram} peak_util={peak_util}")
