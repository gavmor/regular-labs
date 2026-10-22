"""Render the pi/Ollama bake-off figure as a dependency-free SVG.

Every number below is transcribed from the per-task lines emitted by
`harness/run_arm.py` in build #3 of `exp-pi-ollama-bakeoff/render-pi-ollama-bakeoff`
(Concourse target `lab`, 2026-10-22). No means are plotted that are not also
shown as their individual measurements.

Usage:  python3 plot_bakeoff.py <output.svg>
"""
import sys

TASKS = ["t1-bugfix", "t2-multifile", "t3-toolheavy"]

# arm -> label, role, [(passed, turns, tool_calls, tool_errors, wall_s), ...]
ARMS = [
    ("flint", "subject", [
        (True, 5, 6, 1, 20.6),
        (True, 7, 9, 1, 14.2),
        (True, 5, 4, 1, 12.6),
    ]),
    ("nemotron-lightning", "contender", [
        (True, 8, 9, 2, 83.2),
        (True, 6, 12, 0, 23.5),
        (True, 8, 7, 1, 29.8),
    ]),
    ("qwen3-coder-q5kxl", "contender", [
        (False, 4, 3, 0, 42.1),
        (False, 4, 3, 0, 3.6),
        (True, 5, 4, 0, 9.6),
    ]),
    ("qwen3-coder-q4kxl", "baseline", [
        (False, 3, 2, 0, 50.1),
        (False, 4, 3, 0, 3.2),
        (False, 3, 2, 0, 5.4),
    ]),
]

W, H = 860, 430
LEFT, TOP = 196, 76
CELL_W, CELL_H = 132, 56
ROW_GAP = 10
BAR_X = LEFT + 3 * CELL_W + 44
BAR_W = 180
MAX_CALLS = 12.0

PASS = "#1f7a4d"
FAIL = "#b23b3b"
INK = "#1a1a1a"
MUTE = "#6b6b6b"
GRID = "#d8d8d8"


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main(out):
    o = []
    o.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" font-family="Helvetica,Arial,sans-serif">'
    )
    o.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    o.append(
        f'<text x="20" y="28" font-size="15" font-weight="bold" fill="{INK}">'
        "Every task outcome in build #3: four arms x three tasks, one attempt each</text>"
    )
    o.append(
        f'<text x="20" y="48" font-size="11.5" fill="{MUTE}">'
        "Each cell is one oracle verdict. Bars at right are tool calls per task, "
        "the observable that separates the arms.</text>"
    )

    for i, t in enumerate(TASKS):
        x = LEFT + i * CELL_W + CELL_W / 2
        o.append(
            f'<text x="{x:.0f}" y="{TOP - 10}" font-size="12" text-anchor="middle" '
            f'fill="{INK}">{esc(t)}</text>'
        )
    o.append(
        f'<text x="{BAR_X}" y="{TOP - 10}" font-size="12" fill="{INK}">'
        "tool calls per task (mean of the three)</text>"
    )

    for r, (arm, role, rows) in enumerate(ARMS):
        y = TOP + r * (CELL_H + ROW_GAP)
        o.append(
            f'<text x="{LEFT - 14}" y="{y + 23}" font-size="12.5" text-anchor="end" '
            f'fill="{INK}">{esc(arm)}</text>'
        )
        o.append(
            f'<text x="{LEFT - 14}" y="{y + 40}" font-size="10.5" text-anchor="end" '
            f'fill="{MUTE}">{esc(role)}</text>'
        )

        for c, (passed, turns, calls, errs, wall) in enumerate(rows):
            x = LEFT + c * CELL_W
            col = PASS if passed else FAIL
            o.append(
                f'<rect x="{x + 3}" y="{y}" width="{CELL_W - 10}" height="{CELL_H}" '
                f'fill="{col}" fill-opacity="0.10" stroke="{col}" stroke-width="1.2" rx="4"/>'
            )
            o.append(
                f'<text x="{x + 13}" y="{y + 22}" font-size="12.5" font-weight="bold" '
                f'fill="{col}">{"PASS" if passed else "FAIL"}</text>'
            )
            o.append(
                f'<text x="{x + 13}" y="{y + 38}" font-size="10.5" fill="{MUTE}">'
                f"{calls} calls, {errs} err</text>"
            )
            o.append(
                f'<text x="{x + 13}" y="{y + 51}" font-size="10.5" fill="{MUTE}">'
                f"{turns} turns, {wall:.1f}s</text>"
            )

        mean = sum(row[2] for row in rows) / len(rows)
        bw = BAR_W * mean / MAX_CALLS
        o.append(
            f'<rect x="{BAR_X}" y="{y + 14}" width="{bw:.1f}" height="26" '
            f'fill="{INK}" fill-opacity="0.75" rx="2"/>'
        )
        o.append(
            f'<text x="{BAR_X + bw + 8:.0f}" y="{y + 32}" font-size="12" fill="{INK}">'
            f"{mean:.1f}</text>"
        )

    gy0 = TOP - 4
    gy1 = TOP + len(ARMS) * (CELL_H + ROW_GAP) - ROW_GAP + 4
    for v in (0, 4, 8, 12):
        gx = BAR_X + BAR_W * v / MAX_CALLS
        o.append(
            f'<line x1="{gx:.1f}" y1="{gy0}" x2="{gx:.1f}" y2="{gy1}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        o.append(
            f'<text x="{gx:.1f}" y="{gy1 + 14}" font-size="10" text-anchor="middle" '
            f'fill="{MUTE}">{v}</text>'
        )

    o.append(
        f'<text x="20" y="{H - 14}" font-size="10.5" fill="{MUTE}">'
        "N=3 tasks per arm, one attempt each. One task is 33 percentage points. "
        "Greedy decoding (temp 0, seed 42, num_ctx 16384) pinned identically across arms.</text>"
    )
    o.append("</svg>")
    with open(out, "w") as fh:
        fh.write("\n".join(o) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "bakeoff.svg")
