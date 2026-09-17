#!/usr/bin/env python3
"""Compare rendered arms in PIXEL space against a measured seed noise floor.

The point
---------
h3-exp-008 showed int4_convrot's conditioning sits 17x further from unquantised
bf16 than int8's. That is a fact about tensors. A user never sees a tensor --
they see video, produced by a stochastic sampler that consumes the
conditioning. So the question this answers is whether the tensor difference
survives sampling.

Why the floor has to be measured HERE
-------------------------------------
An earlier experiment on this rig measured a seed noise floor of 62.13 mean
absolute pixel difference. That was a different prompt at a different
resolution, and borrowing it would be a borrowed threshold masquerading as a
measurement. Instead, each encoder is rendered at two seeds, which gives four
independent estimates of the floor for THIS prompt and config.

The comparison that matters is therefore:

  within-encoder  (same encoder, seed 42 vs 43)  -> the floor
  between-encoder (matched seed, quant vs bf16)  -> the effect

If the effect is smaller than the floor, the quant choice matters less than
which seed you happened to roll, and "no visible difference" is the right
answer regardless of what the tensors say.

Frames are compared pairwise and aligned by index. Clips are the same length,
seed, resolution and step count by construction, so index alignment is exact --
no attempt is made to handle drift, and a length mismatch is a hard error
rather than something to paper over.
"""

import argparse
import itertools
import json
import os
import sys

import cv2
import numpy as np


def load_frames(path, stride=1):
    cap = cv2.VideoCapture(path)
    frames = []
    i = 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if i % stride == 0:
            frames.append(f.astype(np.float32))
        i += 1
    cap.release()
    if not frames:
        raise RuntimeError(f"no frames decoded from {path}")
    return frames


def mean_abs_diff(a, b):
    if len(a) != len(b):
        raise RuntimeError(f"frame count mismatch: {len(a)} vs {len(b)}")
    return float(np.mean([np.mean(np.abs(x - y)) for x, y in zip(a, b)]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="dir of <encoder>_s<seed>.mp4")
    ap.add_argument("--reference", default="bf16")
    ap.add_argument("--stride", type=int, default=4, help="sample every Nth frame")
    ap.add_argument("--out", default="pixel_visibility.json")
    args = ap.parse_args()

    clips = {}
    for fn in sorted(os.listdir(args.dir)):
        if not fn.endswith(".mp4"):
            continue
        stem = fn.split(".")[0]
        # tolerate the renderer's _00001_ suffix
        parts = stem.replace("_00001_", "").replace("_00002_", "").rsplit("_s", 1)
        if len(parts) != 2:
            continue
        enc, seed = parts[0], parts[1].split("_")[0]
        clips[(enc, seed)] = os.path.join(args.dir, fn)

    if not clips:
        print(f"no clips found in {args.dir}", file=sys.stderr)
        return 1

    print(f"loaded {len(clips)} clips (stride {args.stride})")
    frames = {k: load_frames(v, args.stride) for k, v in clips.items()}
    for k, v in sorted(frames.items()):
        print(f"  {k[0]}_s{k[1]}: {len(v)} sampled frames")

    encoders = sorted({k[0] for k in clips})
    seeds = sorted({k[1] for k in clips})

    # 1. the floor: same encoder, different seed
    within = {}
    for enc in encoders:
        pairs = [
            (a, b)
            for a, b in itertools.combinations(seeds, 2)
            if (enc, a) in frames and (enc, b) in frames
        ]
        for a, b in pairs:
            within[f"{enc}: s{a} vs s{b}"] = mean_abs_diff(frames[(enc, a)], frames[(enc, b)])

    # 2. the effect: different encoder, same seed, vs the reference
    between = {}
    for enc in encoders:
        if enc == args.reference:
            continue
        for s in seeds:
            if (enc, s) in frames and (args.reference, s) in frames:
                between[f"{enc} vs {args.reference} @ s{s}"] = mean_abs_diff(
                    frames[(args.reference, s)], frames[(enc, s)]
                )

    floor_min, floor_max = min(within.values()), max(within.values())

    print("\n=== within-encoder (SEED NOISE FLOOR for this prompt/config) ===")
    for k, v in sorted(within.items(), key=lambda kv: kv[1]):
        print(f"  {k:34} {v:8.2f}")
    print(f"  floor range: {floor_min:.2f} - {floor_max:.2f}")

    print(f"\n=== between-encoder vs {args.reference}, matched seed ===")
    for k, v in sorted(between.items(), key=lambda kv: kv[1]):
        rel = v / floor_min if floor_min else float("nan")
        print(f"  {k:34} {v:8.2f}   {rel:5.2f}x the smallest floor")

    # 3. the pre-registered decision rule, applied mechanically
    eff_max = max(between.values())
    if eff_max < floor_min:
        verdict = (
            "INVISIBLE. Every between-encoder difference is smaller than the "
            "smallest same-encoder seed-to-seed difference. Which quant you use "
            "matters less than which seed you rolled."
        )
    elif eff_max > floor_max:
        worst = max(between, key=lambda k: between[k])
        verdict = (
            f"VISIBLE for at least one arm: '{worst}' at {between[worst]:.2f} "
            f"exceeds the largest seed floor ({floor_max:.2f}). The conditioning "
            f"difference survives sampling."
        )
    else:
        verdict = (
            f"INDETERMINATE at this N. The largest effect ({eff_max:.2f}) falls "
            f"inside the floor's own range ({floor_min:.2f}-{floor_max:.2f}), so "
            f"it cannot be separated from seed variation with two seeds. "
            f"Reporting this rather than rounding to the tidier conclusion."
        )

    print(f"\n=== VERDICT ===\n{verdict}")

    with open(args.out, "w") as f:
        json.dump(
            {
                "reference": args.reference,
                "stride": args.stride,
                "within_encoder_seed_floor": within,
                "floor_min": floor_min,
                "floor_max": floor_max,
                "between_encoder_matched_seed": between,
                "verdict": verdict,
            },
            f,
            indent=2,
        )
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
