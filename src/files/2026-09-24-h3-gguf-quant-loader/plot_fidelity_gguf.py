#!/usr/bin/env python3
"""Plot h3-exp-021: conditioning distance by weight format AND loader node.

Different from plot_conditioning_fidelity.py in one way that matters: the arms
here differ along TWO factors, so the chart has to keep them visually separate
or it silently re-creates the confound the experiment exists to remove. Stock-
loader arms and GGUF-loader arms get different marker shapes, and the GGUF
loader control (unquantised weights, third-party loader) is annotated, because
that single point is what licenses any statement about the other GGUF arms.

Same honesty rules as exp-008's plotter: every measurement plotted, y axis
starts at zero, and the noise floor is drawn when one was measured.

stdlib + matplotlib only. No network.
"""

import argparse
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

MARKER = {"CLIPLoader": "o", "CLIPLoaderGGUF": "^"}
COLOURS = ["#7ddc7d", "#ffc87d", "#ff7d7d", "#7dc8ff", "#d79dff", "#9dffea"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.input) as f:
        d = json.load(f)

    series = {}
    for p in d.get("per_prompt", []):
        for name, m in p["arms"].items():
            if m.get("comparable"):
                series.setdefault(name, []).append(m["relative_l2"])

    agg = d.get("aggregate") or {}
    order = [a for a in agg if a in series]
    arms = order + [a for a in series if a not in order]
    if not arms:
        # An empty chart is worse than no chart: it looks like a measured zero.
        print("no comparable measurements to plot", file=sys.stderr)
        for name, m in agg.items():
            print(f"  {name}: {m.get('note')} {m.get('first_reason', '')[:200]}", file=sys.stderr)
        return 1

    floor_l2 = (d.get("noise_floor") or {}).get("max_self_relative_l2")
    n_prompts = len(d.get("per_prompt", []))

    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(11.5, 6.4))

    if floor_l2:
        ax.axhline(floor_l2, color="#ccc88c", lw=1.2, ls="--", zorder=1)
        ax.annotate(
            f"instrument noise floor {floor_l2:.6f}",
            (len(arms) - 0.42, floor_l2),
            va="bottom",
            ha="right",
            fontsize=8.5,
            color="#ccc88c",
        )

    labels = []
    for i, a in enumerate(arms):
        vals = sorted(series[a])
        loader = agg.get(a, {}).get("loader", "CLIPLoader")
        xs = [i + (j - (len(vals) - 1) / 2) * 0.055 for j in range(len(vals))]
        ax.scatter(
            xs,
            vals,
            s=52,
            marker=MARKER.get(loader, "o"),
            color=COLOURS[i % len(COLOURS)],
            zorder=3,
        )
        mean = sum(vals) / len(vals)
        ax.plot(
            [i - 0.28, i + 0.28], [mean, mean], lw=3, color=COLOURS[i % len(COLOURS)], zorder=4
        )
        ax.annotate(
            f"mean {mean:.4f}",
            (i + 0.31, mean),
            va="center",
            fontsize=9.5,
            color=COLOURS[i % len(COLOURS)],
        )
        short = "GGUF loader" if loader == "CLIPLoaderGGUF" else "stock loader"
        labels.append(f"{a}\n{short}")

    ax.set_xticks(range(len(arms)))
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("relative L2 vs unquantised bf16 (stock loader)", fontsize=11)
    ax.set_ylim(0, None)
    ax.set_title(
        "h3-exp-021: H3 text-encoder conditioning distance by format AND loader\n"
        f"{n_prompts} prompts per arm, every measurement plotted; "
        "triangles are the third-party GGUF loader",
        fontsize=12,
        pad=14,
    )
    ax.grid(axis="y", alpha=0.18)
    ax.set_axisbelow(True)

    fig.text(
        0.5,
        0.015,
        "The GGUF arm with unquantised weights is the LOADER CONTROL: its distance from the "
        "reference\nis the loader's own offset. Only distance ABOVE that point can be "
        "attributed to Q4_K_M quantisation.",
        ha="center",
        fontsize=9,
        color="#ccc88c",
    )

    fig.tight_layout(rect=(0, 0.075, 1, 1))
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    fig.savefig(args.out, dpi=130)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
