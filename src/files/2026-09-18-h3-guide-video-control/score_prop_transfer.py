#!/usr/bin/env python3
"""Score h3-exp-010: do props appear, and does the subject survive?

Prop presence is a DISCRETE reading made by looking at frames, not a metric
computed from pixels. There is no "briefcase detector" here and pretending
otherwise would be dressing up a judgement call as a measurement. What this
script does is make that judgement auditable: it builds one frame grid per arm
at fixed frame indices, identical across arms, so the same moments are compared
and a reader can check the call against the image.

The pre-registered decision rule has three branches, and the third exists
because of a specific failure mode: a control signal strong enough to drag
props into frame may also drag in the source clip's SUBJECT, overwriting the
prompt's woman with the source's suited figure. That outcome is not "props
carried over" -- it is the guide video leaking through, and it is scored
INDETERMINATE rather than SUPPORTED.

So two readings per arm, both required:
    props_present   -- briefcase or tripod visible
    subject_intact  -- the prompt's blonde woman in the colour-blocked dress,
                       NOT the source clip's suited figure

Pixel distances are computed too, but only to establish the seed floor in THIS
configuration, so that any between-arm difference can be read against
within-arm variation rather than against an assumption.
"""
import argparse
import json
import os
import subprocess
import sys

# Fixed sampling points, identical for every arm. Chosen to span the source
# clip's action: approach, kneel, open, extract, stand.
GRID_FRAMES = [20, 70, 120, 170, 220, 270]


def frame_count(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=nb_read_frames", "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True,
    )
    return int(out.stdout.strip())


def build_grid(path, out_png, frames=GRID_FRAMES, tile_w=420):
    """One row of sampled frames, for a human (or vision model) to read."""
    sel = "+".join(f"eq(n\\,{n})" for n in frames)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", path,
         "-vf", f"select='{sel}',scale={tile_w}:-1,tile={len(frames)}x1",
         "-frames:v", "1", out_png],
        check=True,
    )
    return out_png


def mean_abs_diff(a, b, stride=8):
    """Mean absolute pixel difference between two clips, sampled every `stride`
    frames. Same estimator as h3-exp-009 so the numbers are comparable, but the
    floor is measured fresh here -- borrowing 63.94-66.63 from a different
    prompt and resolution would be assuming the answer."""
    import numpy as np

    def frames(path):
        n = min(frame_count(path), 294)
        idx = list(range(0, n, stride))
        sel = "+".join(f"eq(n\\,{i})" for i in idx)
        proc = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", path,
             "-vf", f"select='{sel}',scale=320:180", "-vsync", "0",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True, check=True,
        )
        arr = np.frombuffer(proc.stdout, dtype=np.uint8)
        return arr.reshape(-1, 180, 320, 3).astype(np.int16)

    fa, fb = frames(a), frames(b)
    n = min(len(fa), len(fb))
    return float(np.abs(fa[:n] - fb[:n]).mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--skip-pixels", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    clips = {}
    for f in sorted(os.listdir(args.assets_dir)):
        if not f.endswith(".mp4"):
            continue
        for arm in ("skeleton_s43", "skeleton_s44", "vace_s43", "vace_s44"):
            if arm in f:
                clips[arm] = os.path.join(args.assets_dir, f)

    missing = [a for a in ("skeleton_s43", "skeleton_s44", "vace_s43", "vace_s44")
               if a not in clips]
    if missing:
        raise SystemExit(f"FAILED: missing arms {missing} in {args.assets_dir}")

    report = {"arms": {}, "grids": {}, "pixels": {}}

    for arm, path in clips.items():
        n = frame_count(path)
        grid = build_grid(path, os.path.join(args.out_dir, f"{arm}.png"))
        report["arms"][arm] = {"path": path, "frames": n, "bytes": os.path.getsize(path)}
        report["grids"][arm] = grid
        print(f"  {arm:14} {n} frames -> {grid}")

    # A side-by-side of one seed, all arms, for the figure in the write-up.
    stack = os.path.join(args.out_dir, "arms-compare-s43.png")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-i", report["grids"]["skeleton_s43"],
         "-i", report["grids"]["vace_s43"],
         "-filter_complex", "[0:v][1:v]vstack=inputs=2", stack],
        check=True,
    )
    report["grids"]["compare_s43"] = stack
    print(f"  compare -> {stack}")

    if not args.skip_pixels:
        print("\n  pixel distances (stride 8):")
        # within-arm = same control, different seed. This IS the floor.
        for arm in ("skeleton", "vace"):
            d = mean_abs_diff(clips[f"{arm}_s43"], clips[f"{arm}_s44"])
            report["pixels"][f"{arm}_seed_floor"] = round(d, 2)
            print(f"    {arm} s43 vs s44 (floor): {d:.2f}")
        # between-arm = same seed, different control
        for seed in (43, 44):
            d = mean_abs_diff(clips[f"skeleton_s{seed}"], clips[f"vace_s{seed}"])
            report["pixels"][f"between_s{seed}"] = round(d, 2)
            print(f"    skeleton vs vace @ s{seed}:  {d:.2f}")

        floors = [v for k, v in report["pixels"].items() if k.endswith("seed_floor")]
        betweens = [v for k, v in report["pixels"].items() if k.startswith("between")]
        if floors and betweens:
            report["pixels"]["max_between_vs_min_floor"] = round(
                max(betweens) / min(floors), 3
            )
            print(f"\n    max between / min floor = "
                  f"{report['pixels']['max_between_vs_min_floor']}")
            print("    (>1 means the control type moves pixels more than the seed does)")

    report["readings_pending"] = {
        arm: {"props_present": None, "subject_intact": None} for arm in clips
    }
    report["decision_rule"] = (
        "SUPPORTED: props in BOTH vace arms and NEITHER skeleton arm, subject intact. "
        "REFUTED: no props in any arm. "
        "INDETERMINATE: props at one seed only, props in both arms, or props "
        "present but subject overwritten by the guide's figure."
    )

    json.dump(report, open(args.report, "w"), indent=2)
    print(f"\nwrote {args.report}")
    print("Prop and subject readings are made by inspecting the grids, not by this script.")


if __name__ == "__main__":
    sys.exit(main())
