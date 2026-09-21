#!/usr/bin/env python3
"""Generate dataviz charts comparing Qwen Image 2.1 composite T2I vs H3 turnaround pipeline.

Produces:
1. performance-cost-comparison.png: Latency per sheet and Peak VRAM.
2. view-reliability-comparison.png: Accuracy across view angles (Qwen vs MediaPipe pose/face in exp-018).
3. exit-review-tradeoff.png: Pass rate across the three pre-registered exit review conditions.
"""

import os
import matplotlib.pyplot as plt
import numpy as np

OUTPUT_DIR = "/home/user/code/regular-labs/src/images/2026-09-21-qwen-charref-composite-t2i"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Styling configuration
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Helvetica", "Arial"],
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "axes.labelsize": 11,
    "axes.labelweight": "bold",
    "xtick.labelsize": 10.5,
    "ytick.labelsize": 10,
    "figure.titlesize": 14.5,
    "figure.titleweight": "bold",
})

COLOR_QWEN = "#2a6ebb"       # Steel blue
COLOR_H3_POSE = "#c1443c"    # Muted crimson
COLOR_H3_FACE = "#7a5aa8"    # Muted purple
COLOR_THRESHOLD = "#9c2318"  # Accent dark red
COLOR_BG = "#ffffff"
COLOR_GRID = "#ebebeb"


def generate_performance_cost_chart():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 5.0), facecolor=COLOR_BG)
    fig.subplots_adjust(wspace=0.34, top=0.84, bottom=0.16)

    # --- Panel 1: Latency per Reference Sheet ---
    labels = ["Qwen Image 2.1\n(Single T2I pass)", "H3 Turnaround\n(T2VA + extraction)"]
    times = [46.7, 105.0]
    colors = [COLOR_QWEN, COLOR_H3_POSE]

    bars1 = ax1.bar(labels, times, color=colors, width=0.48, edgecolor="#222222", linewidth=1.1, zorder=3)
    ax1.set_ylabel("Seconds per Character Sheet", fontweight="bold")
    ax1.set_title("Render & Assembly Latency", pad=12)
    ax1.set_ylim(0, 135)
    ax1.grid(axis="y", linestyle="--", alpha=0.7, color=COLOR_GRID, zorder=0)
    ax1.set_facecolor(COLOR_BG)

    for bar, time in zip(bars1, times):
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width() / 2.0, height + 3.2,
                 f"{time:.1f}s", ha="center", va="bottom", fontsize=11, fontweight="bold")

    ax1.annotate("-55% Latency\n(2.25× faster)",
                 xy=(0.26, 48), xycoords="data",
                 xytext=(0.53, 76), textcoords="data",
                 arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=-0.18", color="#1c4d85", lw=1.6),
                 fontsize=10.5, fontweight="bold", color="#1c4d85",
                 bbox=dict(boxstyle="round,pad=0.35", fc="#eef4fa", ec="#b3cee8", lw=1))

    # --- Panel 2: Peak VRAM Footprint ---
    vram = [14.0, 22.4]
    bars2 = ax2.bar(labels, vram, color=colors, width=0.48, edgecolor="#222222", linewidth=1.1, zorder=3)
    ax2.set_ylabel("Peak VRAM (GiB) on RTX 3090", fontweight="bold")
    ax2.set_title("GPU Memory Consumption", pad=12)
    ax2.set_ylim(0, 29)
    ax2.grid(axis="y", linestyle="--", alpha=0.7, color=COLOR_GRID, zorder=0)
    ax2.set_facecolor(COLOR_BG)

    # 24GB hardware limit line
    ax2.axhline(24.0, color="#555555", linestyle=":", linewidth=1.6, zorder=4)
    ax2.text(0.5, 24.3, "24.0 GiB VRAM Hardware Limit", ha="center", va="bottom",
             fontsize=9.5, fontweight="bold", color="#555555")

    for bar, val in zip(bars2, vram):
        height = bar.get_height()
        pct = (val / 24.0) * 100.0
        if val > 20:
            ax2.text(bar.get_x() + bar.get_width() / 2.0, height - 2.8,
                     f"{val:.1f} GiB\n({pct:.0f}%)", ha="center", va="center",
                     fontsize=10.5, fontweight="bold", color="#ffffff")
        else:
            ax2.text(bar.get_x() + bar.get_width() / 2.0, height + 0.8,
                     f"{val:.1f} GiB\n({pct:.0f}%)", ha="center", va="bottom",
                     fontsize=10.5, fontweight="bold", color="#1c4d85")

    ax2.annotate("+8.4 GiB\nHeadroom",
                 xy=(0.12, 14.8), xycoords="data",
                 xytext=(0.48, 17.2), textcoords="data",
                 arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=-0.15", color="#1c4d85", lw=1.6),
                 fontsize=10.5, fontweight="bold", color="#1c4d85",
                 bbox=dict(boxstyle="round,pad=0.35", fc="#eef4fa", ec="#b3cee8", lw=1))

    for ax in (ax1, ax2):
        for spine in ["top", "right"]:
            ax.spines[spine].set_visible(False)
        ax.spines["left"].set_color("#777777")
        ax.spines["bottom"].set_color("#777777")

    plt.suptitle("Compute Efficiency: Single-Pass Qwen 2.1 T2I vs Multi-Clip H3 Turnaround", y=0.98)
    out_path = os.path.join(OUTPUT_DIR, "performance-cost-comparison.png")
    plt.savefig(out_path, dpi=300, bbox_inches="tight", facecolor=COLOR_BG)
    plt.close()
    print(f"Saved: {out_path}")


def generate_view_reliability_chart():
    fig, ax = plt.subplots(figsize=(11.5, 5.5), facecolor=COLOR_BG)
    fig.subplots_adjust(top=0.86, bottom=0.18)

    views = ["Front", "Side", "Rear", "Close-up", "Overall"]
    x = np.arange(len(views))
    width = 0.24

    qwen_acc = [100.0, 100.0, 100.0, 100.0, 100.0]
    pose_acc = [100.0, 85.5, 51.6, 0.0, 56.5]
    face_acc = [16.4, 0.0, 50.0, 87.0, 40.3]

    rects1 = ax.bar(x - width, qwen_acc, width, label="Qwen 2.1 (Direct T2I Quadrant Layout)",
                    color=COLOR_QWEN, edgecolor="#222222", linewidth=1.0, zorder=3)
    rects2 = ax.bar(x, pose_acc, width, label="H3 + MediaPipe Pose Geometry (exp-018)",
                    color=COLOR_H3_POSE, edgecolor="#222222", linewidth=1.0, zorder=3)
    rects3 = ax.bar(x + width, face_acc, width, label="H3 + MediaPipe Face Area (exp-018)",
                    color=COLOR_H3_FACE, edgecolor="#222222", linewidth=1.0, zorder=3)

    # 90% pre-registered accuracy pass threshold line
    ax.axhline(90.0, color=COLOR_THRESHOLD, linestyle="--", linewidth=1.5, zorder=4)
    ax.text(0.02, 0.92, "- - - Pre-registered accuracy pass threshold (≥90%)", transform=ax.transAxes,
            color=COLOR_THRESHOLD, fontsize=9.5, fontweight="bold", ha="left", va="top")

    ax.set_ylabel("View Classification / Placement Accuracy (%)", fontweight="bold")
    ax.set_title("View Angle Reliability: Direct Canvas Placement vs Post-Hoc Geometry Extraction", pad=14)
    ax.set_xticks(x)
    ax.set_xticklabels(views, fontweight="bold", fontsize=11)
    ax.set_ylim(0, 126)
    ax.set_xlim(-0.5, len(views) - 0.5)
    ax.grid(axis="y", linestyle="--", alpha=0.7, color=COLOR_GRID, zorder=0)
    ax.set_facecolor(COLOR_BG)

    # Qwen labels: white text inside top of bar
    for r in rects1:
        ax.text(r.get_x() + r.get_width() / 2.0, 95.0,
                "100%", ha="center", va="center", fontsize=8.5, fontweight="bold", color="#ffffff")

    # H3 Pose labels
    for i, r in enumerate(rects2):
        h = r.get_height()
        if h >= 95:
            ax.text(r.get_x() + r.get_width() / 2.0, 95.0,
                    f"{h:.0f}%", ha="center", va="center", fontsize=8.5, fontweight="bold", color="#ffffff")
        elif h >= 80:
            ax.text(r.get_x() + r.get_width() / 2.0, h - 5.5,
                    f"{h:.0f}%", ha="center", va="center", fontsize=8.5, fontweight="bold", color="#ffffff")
        elif h > 5:
            ax.text(r.get_x() + r.get_width() / 2.0, h + 2.2,
                    f"{h:.0f}%", ha="center", va="bottom", fontsize=8.5, fontweight="bold", color="#7a2019")
        else:
            ax.text(r.get_x() + r.get_width() / 2.0, 2.5,
                    "0%", ha="center", va="bottom", fontsize=8.5, fontweight="bold", color="#777777")

    # H3 Face labels
    for r in rects3:
        h = r.get_height()
        if h >= 80:
            ax.text(r.get_x() + r.get_width() / 2.0, h - 5.5,
                    f"{h:.0f}%", ha="center", va="center", fontsize=8.5, fontweight="bold", color="#ffffff")
        elif h > 5:
            ax.text(r.get_x() + r.get_width() / 2.0, h + 2.2,
                    f"{h:.0f}%", ha="center", va="bottom", fontsize=8.5, fontweight="bold", color="#4b2e6d")
        else:
            ax.text(r.get_x() + r.get_width() / 2.0, 2.5,
                    "0%", ha="center", va="bottom", fontsize=8.5, fontweight="bold", color="#777777")

    # Specific callouts for failure points in H3
    ax.annotate("52% Rear Ceiling:\nFront & rear poses\ngeometrically identical",
                xy=(2.0, 53), xycoords="data",
                xytext=(1.68, 70), textcoords="data",
                arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=-0.14", color="#a33229", lw=1.3),
                fontsize=8.5, fontweight="bold", color="#7a2019",
                bbox=dict(boxstyle="round,pad=0.3", fc="#fdf2f1", ec="#e5b8b5", lw=0.9))

    ax.annotate("0% Close-up:\nCrop invariant\nto landmarks",
                xy=(3.0, 2), xycoords="data",
                xytext=(2.72, 26), textcoords="data",
                arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=-0.14", color="#a33229", lw=1.3),
                fontsize=8.5, fontweight="bold", color="#7a2019",
                bbox=dict(boxstyle="round,pad=0.3", fc="#fdf2f1", ec="#e5b8b5", lw=0.9))

    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#777777")
    ax.spines["bottom"].set_color("#777777")

    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3, frameon=True,
              facecolor="#f9f9f9", edgecolor="#cccccc", fontsize=9.5)

    out_path = os.path.join(OUTPUT_DIR, "view-reliability-comparison.png")
    plt.savefig(out_path, dpi=300, bbox_inches="tight", facecolor=COLOR_BG)
    plt.close()
    print(f"Saved: {out_path}")


def generate_exit_review_tradeoff_chart():
    fig, ax = plt.subplots(figsize=(11.0, 4.8), facecolor=COLOR_BG)
    fig.subplots_adjust(top=0.86, bottom=0.18)

    criteria = [
        "1. View Placement\nCompliance",
        "2. Costume & Identity\nCoherence",
        "3. Framing & Scale\nConsistency",
        "Overall Batch\nExit Verdict"
    ]
    x = np.arange(len(criteria))
    width = 0.32

    qwen_rates = [100.0, 100.0, 93.2, 0.0]
    h3_rates = [56.5, 100.0, 100.0, 0.0]

    rects1 = ax.bar(x - width / 2, qwen_rates, width, label="Qwen Image 2.1 (T2I)",
                    color=COLOR_QWEN, edgecolor="#222222", linewidth=1.0, zorder=3)
    rects2 = ax.bar(x + width / 2, h3_rates, width, label="H3 Turnaround Pipeline",
                    color=COLOR_H3_POSE, edgecolor="#222222", linewidth=1.0, zorder=3)

    ax.set_ylabel("Pass Rate Across 44 Alters (%)", fontweight="bold")
    ax.set_title("Pre-Registered Exit Review Criteria: Where Each Pipeline Breaks Down", pad=14)
    ax.set_xticks(x)
    ax.set_xticklabels(criteria, fontweight="bold", fontsize=10.5)
    ax.set_ylim(0, 126)
    ax.grid(axis="y", linestyle="--", alpha=0.7, color=COLOR_GRID, zorder=0)
    ax.set_facecolor(COLOR_BG)

    # Bar labels
    for i, (rect, val) in enumerate(zip(rects1, qwen_rates)):
        if val > 0:
            if i == 1:
                ax.text(rect.get_x() + rect.get_width() / 2.0, rect.get_height() - 5.0,
                        "100%", ha="center", va="center", fontsize=9.5, fontweight="bold", color="#ffffff")
            else:
                ax.text(rect.get_x() + rect.get_width() / 2.0, rect.get_height() + 2.5,
                        f"{val:.1f}%", ha="center", va="bottom", fontsize=9.5, fontweight="bold", color="#1c4d85")
        else:
            ax.text(rect.get_x() + rect.get_width() / 2.0, 3.5,
                    "FAIL\n(0%)", ha="center", va="bottom", fontsize=9.5, fontweight="bold", color="#9c2318")

    for i, (rect, val) in enumerate(zip(rects2, h3_rates)):
        if val > 0:
            if i == 1:
                ax.text(rect.get_x() + rect.get_width() / 2.0, rect.get_height() - 5.0,
                        "100%", ha="center", va="center", fontsize=9.5, fontweight="bold", color="#ffffff")
            else:
                ax.text(rect.get_x() + rect.get_width() / 2.0, rect.get_height() + 2.5,
                        f"{val:.1f}%", ha="center", va="bottom", fontsize=9.5, fontweight="bold", color="#7a2019")
        else:
            ax.text(rect.get_x() + rect.get_width() / 2.0, 3.5,
                    "FAIL\n(0%)", ha="center", va="bottom", fontsize=9.5, fontweight="bold", color="#9c2318")

    ax.annotate("3 Defects in Qwen:\nDwarfism, zoom drift,\nand shin cropping",
                xy=(2.0 - width / 2, 94.0), xycoords="data",
                xytext=(1.45, 62), textcoords="data",
                arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=-0.15", color="#1c4d85", lw=1.3),
                fontsize=8.5, fontweight="bold", color="#1c4d85",
                bbox=dict(boxstyle="round,pad=0.3", fc="#eef4fa", ec="#b3cee8", lw=0.9))

    ax.annotate("H3 Breakdown:\nCut ambiguity & 52%\nrear accuracy ceiling",
                xy=(0.0 + width / 2, 57.0), xycoords="data",
                xytext=(0.20, 30), textcoords="data",
                arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=-0.15", color="#a33229", lw=1.3),
                fontsize=8.5, fontweight="bold", color="#7a2019",
                bbox=dict(boxstyle="round,pad=0.3", fc="#fdf2f1", ec="#e5b8b5", lw=0.9))

    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#777777")
    ax.spines["bottom"].set_color("#777777")

    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2, frameon=True,
              facecolor="#f9f9f9", edgecolor="#cccccc", fontsize=9.5)

    out_path = os.path.join(OUTPUT_DIR, "exit-review-tradeoff.png")
    plt.savefig(out_path, dpi=300, bbox_inches="tight", facecolor=COLOR_BG)
    plt.close()
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    generate_performance_cost_chart()
    generate_view_reliability_chart()
    generate_exit_review_tradeoff_chart()
