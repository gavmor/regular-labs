#!/usr/bin/env python3
"""Figure for the Strata 3090 throughput smoke test — stdlib only, emits SVG.

Panel 1: the engine's own running generation rate over the measured answer,
         against the README's claimed 100-140 tok/s 3090 band.
Panel 2: what the calibrator's micro-benchmark predicted at each setting it
         swept, against the sustained rate the real 30,341-token request
         actually delivered at the setting the calibrator chose.

Every number below is read off the Concourse build #8 log (build 2532550,
`fly -t lab watch -b 2532550`) and the egressed results.json. Nothing is
modelled, smoothed or interpolated.
"""

import os

OUT_DIR = "/home/user/code/regular-labs/src/images/2026-10-04-strata-throughput-3090"
OUT = os.path.join(OUT_DIR, "throughput.svg")

# --- engine streaming progress lines, build #8 ----------------------------
# "[strata] <phase>: N of max 2048 tokens, R tok/s, S s"
PROGRESS = [
    (1, 107.9), (2, 105.2), (3, 101.1), (4, 104.6), (5, 105.2), (6, 104.6),
    (7, 106.3), (8, 107.1), (9, 106.8), (10, 107.4), (11, 106.9), (12, 107.2),
    (13, 109.2), (14, 109.4), (15, 109.6), (16, 110.3), (17, 111.0),
]
REASONING_ENDS_S = 3.4          # last "thinking:" line is at 3 s, 300 tokens
FINAL_TOK_S = 111.28            # harness: 1916 completion tokens / 17.209 s
FINAL_T = 17.209

# --- calibrator sweep, build #8 ------------------------------------------
SWEEP = [
    ("PCIe 0.00", 127.6), ("PCIe 0.20", 125.9), ("PCIe 0.35", 118.6),
    ("PCIe 0.36", 114.5), ("PCIe 0.55", 110.8), ("PCIe 0.75", 110.3),
    ("draft 0.30", 115.9), ("draft 0.50", 119.4), ("draft 0.70", 120.0),
    ("7 workers", 130.1), ("5 workers", 128.9), ("4 workers", 126.0),
]
CAL_PICK = 130.1                # "[ok] tuned for this PC ... (130.1 tok/s)"

BAND_LO, BAND_HI = 100.0, 140.0
Y_LO, Y_HI = 95.0, 143.0

W, H = 1180, 500
PLOT_TOP, PLOT_BOT = 64, 396
P1_L, P1_R = 68, 566
P2_L, P2_R = 672, 1158

C_RUN = "#2a6ebb"
C_RUN_DK = "#17406e"
C_CAL = "#c1443c"
C_BAND = "#dce8f5"
C_THRESH = "#9c2318"
C_GRID = "#e8e8e8"
C_AXIS = "#444444"


def yv(v):
    return PLOT_BOT - (v - Y_LO) / (Y_HI - Y_LO) * (PLOT_BOT - PLOT_TOP)


def x1(t):
    return P1_L + t / 18.6 * (P1_R - P1_L)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def plate(x, y, w, h):
    """White backing so a label stays legible where it crosses the plot."""
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'fill="#ffffff" opacity="0.88"/>')


def text(x, y, s, size=11.0, fill="#222222", anchor="start", weight="normal",
         rotate=None):
    tr = f' transform="rotate({rotate} {x} {y})"' if rotate is not None else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="DejaVu Sans, Helvetica, Arial, sans-serif" '
            f'font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
            f'font-weight="{weight}"{tr}>{esc(s)}</text>')


def panel_frame(left, right, title):
    out = [f'<rect x="{left}" y="{yv(BAND_HI):.1f}" width="{right - left}" '
           f'height="{yv(BAND_LO) - yv(BAND_HI):.1f}" fill="{C_BAND}"/>']
    for v in range(95, 146, 5):
        if v < Y_LO or v > Y_HI:
            continue
        y = yv(v)
        out.append(f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" '
                   f'stroke="{C_GRID}" stroke-width="1"/>')
        out.append(text(left - 8, y + 4, str(v), size=10, fill="#666666",
                        anchor="end"))
    out.append(f'<line x1="{left}" y1="{PLOT_TOP}" x2="{left}" y2="{PLOT_BOT}" '
               f'stroke="{C_AXIS}" stroke-width="1.2"/>')
    out.append(f'<line x1="{left}" y1="{PLOT_BOT}" x2="{right}" y2="{PLOT_BOT}" '
               f'stroke="{C_AXIS}" stroke-width="1.2"/>')
    out.append(f'<line x1="{left}" y1="{yv(BAND_LO):.1f}" x2="{right}" '
               f'y2="{yv(BAND_LO):.1f}" stroke="{C_THRESH}" stroke-width="1.4" '
               f'stroke-dasharray="6 4"/>')
    out.append(text((left + right) / 2, 38, title, size=13, weight="bold",
                    anchor="middle"))
    return out


def build():
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}">',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>']

    # ------------------------------------------------ panel 1
    s += panel_frame(P1_L, P1_R,
                     "One 30,341-token request, sustained in band at its floor")
    # reasoning shading
    s.append(f'<rect x="{P1_L}" y="{PLOT_TOP}" width="{x1(REASONING_ENDS_S) - P1_L:.1f}" '
             f'height="{PLOT_BOT - PLOT_TOP}" fill="#000000" opacity="0.045"/>')
    s.append(text(x1(1.7), PLOT_BOT - 10, "reasoning", size=9.5, fill="#777777",
                  anchor="middle"))
    s.append(text(x1(10.5), PLOT_BOT - 10, "answer", size=9.5, fill="#777777",
                  anchor="middle"))

    pts = " ".join(f"{x1(t):.1f},{yv(r):.1f}" for t, r in PROGRESS)
    s.append(f'<polyline points="{pts}" fill="none" stroke="{C_RUN}" '
             f'stroke-width="2.2"/>')
    for t, r in PROGRESS:
        s.append(f'<circle cx="{x1(t):.1f}" cy="{yv(r):.1f}" r="3.1" '
                 f'fill="{C_RUN}"/>')
    fx, fy = x1(FINAL_T), yv(FINAL_TOK_S)
    s.append(f'<polygon points="{fx:.1f},{fy - 7:.1f} {fx + 7:.1f},{fy:.1f} '
             f'{fx:.1f},{fy + 7:.1f} {fx - 7:.1f},{fy:.1f}" fill="{C_RUN_DK}"/>')
    s.append(f'<line x1="{x1(14.2):.1f}" y1="{yv(118.5):.1f}" x2="{fx - 7:.1f}" '
             f'y2="{fy - 3:.1f}" stroke="{C_RUN_DK}" stroke-width="1.2"/>')
    s.append(text(x1(14.0), yv(119.4), "111.28", size=11.5, weight="bold",
                  fill=C_RUN_DK, anchor="end"))

    for t in range(0, 19, 3):
        s.append(f'<line x1="{x1(t):.1f}" y1="{PLOT_BOT}" x2="{x1(t):.1f}" '
                 f'y2="{PLOT_BOT + 5}" stroke="{C_AXIS}" stroke-width="1"/>')
        s.append(text(x1(t), PLOT_BOT + 19, str(t), size=10, fill="#555555",
                      anchor="middle"))
    s.append(text((P1_L + P1_R) / 2, PLOT_BOT + 40, "seconds into the response",
                  size=11, weight="bold", anchor="middle"))
    s.append(text(22, (PLOT_TOP + PLOT_BOT) / 2, "generation rate (tok/s)",
                  size=11, weight="bold", anchor="middle",
                  rotate=-90))
    s.append(text(P1_R - 4, yv(BAND_HI) + 15,
                  "README's claimed 3090 band, 100-140 tok/s", size=9.5,
                  fill="#45617d", anchor="end"))
    s.append(plate(P1_L + 4, yv(BAND_LO) - 19, 232, 15))
    s.append(text(P1_L + 8, yv(BAND_LO) - 8,
                  "100 tok/s - pass threshold and band floor", size=9.5,
                  fill=C_THRESH))

    # ------------------------------------------------ panel 2
    s += panel_frame(P2_L, P2_R,
                     "Calibration predicts 130.1; serving delivers 111.28")
    n = len(SWEEP)
    slot = (P2_R - P2_L) / n
    bw = slot * 0.6
    for i, (label, v) in enumerate(SWEEP):
        bx = P2_L + i * slot + (slot - bw) / 2
        by = yv(v)
        s.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" '
                 f'height="{PLOT_BOT - by:.1f}" fill="{C_CAL}" opacity="0.88"/>')
        s.append(text(bx + bw / 2 + 3, PLOT_BOT + 12, label, size=9.5,
                      fill="#555555", anchor="end",
                      rotate=-45))
    s.append(f'<line x1="{P2_L}" y1="{yv(CAL_PICK):.1f}" x2="{P2_R}" '
             f'y2="{yv(CAL_PICK):.1f}" stroke="{C_CAL}" stroke-width="1.5" '
             f'stroke-dasharray="3 3"/>')
    s.append(text(P2_R - 4, yv(CAL_PICK) - 6, "calibrator's pick: 130.1",
                  size=10, weight="bold", fill=C_CAL, anchor="end"))
    s.append(f'<line x1="{P2_L}" y1="{yv(FINAL_TOK_S):.1f}" x2="{P2_R}" '
             f'y2="{yv(FINAL_TOK_S):.1f}" stroke="{C_RUN_DK}" stroke-width="2.4"/>')
    s.append(plate(P2_L + 4, yv(FINAL_TOK_S) + 4, 258, 16))
    s.append(text(P2_L + 8, yv(FINAL_TOK_S) + 16,
                  "111.28 - sustained 30K-context serving rate", size=10,
                  weight="bold", fill=C_RUN_DK))
    ax = P2_R - 46
    s.append(f'<line x1="{ax:.1f}" y1="{yv(CAL_PICK):.1f}" x2="{ax:.1f}" '
             f'y2="{yv(FINAL_TOK_S):.1f}" stroke="#333333" stroke-width="1.4"/>')
    for yy in (yv(CAL_PICK), yv(FINAL_TOK_S)):
        s.append(f'<line x1="{ax - 4:.1f}" y1="{yy:.1f}" x2="{ax + 4:.1f}" '
                 f'y2="{yy:.1f}" stroke="#333333" stroke-width="1.4"/>')
    s.append(text(ax - 8, (yv(CAL_PICK) + yv(FINAL_TOK_S)) / 2 + 4,
                  "17% overstated", size=10.5, weight="bold", fill="#333333",
                  anchor="end"))
    s.append(text((P2_L + P2_R) / 2, PLOT_BOT + 72,
                  "setting swept by the calibrator's micro-benchmark",
                  size=11, weight="bold", anchor="middle"))
    s.append(text(626, (PLOT_TOP + PLOT_BOT) / 2, "tok/s", size=11,
                  weight="bold", anchor="middle", rotate=-90))

    s.append(text(W / 2, H - 10,
                  "Strata 0.1.39, Qwen3.8-Flash-Next GSQ-RCO Q2_0, RTX 3090, "
                  "32768-token context - Concourse build 2532550 (strata-smoke/smoke/8)",
                  size=9.5, fill="#888888", anchor="middle"))
    s.append("</svg>")
    return "\n".join(s)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(build())
    print(f"wrote {OUT} ({os.path.getsize(OUT)} bytes)")


if __name__ == "__main__":
    main()
