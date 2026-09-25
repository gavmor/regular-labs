#!/usr/bin/env python3
"""h3-exp-026 metrics: DV1 seed variation, DV2 temporal motion, DV3 distance to reference.

Decodes each arm's mp4 to grayscale frames at temporal stride 8 via ffmpeg,
then computes mean absolute pixel distances in pure Python (no numpy dep
assumptions -- uses array + statistics).

DV1: mean pairwise |A-B| across all C(4,2)=6 seed pairs within an arm.
DV2: mean |frame_t - frame_t+1| within each clip, averaged over the arm.
DV3: mean |generated - reference| against the arm's own trimmed reference,
     frame-aligned over min(len) at the same stride.
"""
import array
import itertools
import json
import os
import subprocess
import sys

VID = os.path.expanduser(os.environ.get("EXP026_VIDS", ""))
REFS = "/home/user/code/genops-pipelines.h3-exp-026/workflows/refs"
W, H = 208, 120          # downscale for tractable pure-python math
STRIDE = 8
ARMS = ["noref", "ref22", "ref56", "ref90", "ref124"]
SEEDS = [43, 44, 45, 46]


def decode(path, stride=STRIDE):
    """Return list of grayscale frames (array of ints) at the given stride."""
    cmd = [
        "ffmpeg", "-v", "error", "-i", path,
        "-vf", f"select='not(mod(n\\,{stride}))',scale={W}:{H}",
        "-vsync", "0", "-pix_fmt", "gray", "-f", "rawvideo", "-",
    ]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    size = W * H
    return [array.array("B", raw[i:i + size]) for i in range(0, len(raw) - size + 1, size)]


def dist(fa, fb):
    n = min(len(fa), len(fb))
    if n == 0:
        return None
    tot = 0
    for a, b in zip(fa[:n], fb[:n]):
        d = 0
        for x, y in zip(a, b):
            d += x - y if x > y else y - x
        tot += d / len(a)
    return tot / n


def main():
    cache = {}
    for arm in ARMS:
        for s in SEEDS:
            p = os.path.join(VID, f"{arm}_s{s}.mp4")
            if os.path.exists(p):
                cache[(arm, s)] = decode(p)

    refcache = {}
    for n in (22, 56, 90, 124):
        p = os.path.join(REFS, f"char_ref_{n}.mp4")
        if os.path.exists(p):
            refcache[n] = decode(p)

    out = {}
    for arm in ARMS:
        clips = {s: cache[(arm, s)] for s in SEEDS if (arm, s) in cache}
        if len(clips) < 2:
            continue
        # DV1 seed variation
        pair = [dist(clips[a], clips[b]) for a, b in itertools.combinations(sorted(clips), 2)]
        dv1 = sum(pair) / len(pair)
        # DV2 within-clip temporal motion
        mot = []
        for s, fr in clips.items():
            if len(fr) > 1:
                mot.append(sum(dist([fr[i]], [fr[i + 1]]) for i in range(len(fr) - 1)) / (len(fr) - 1))
        dv2 = sum(mot) / len(mot) if mot else None
        # DV3 distance to that arm's reference
        dv3 = None
        if arm.startswith("ref"):
            n = int(arm[3:])
            if n in refcache:
                d = [dist(fr, refcache[n]) for fr in clips.values()]
                dv3 = sum(d) / len(d)
        out[arm] = {"n_seeds": len(clips), "dv1_seed_var": round(dv1, 3),
                    "dv2_temporal_motion": round(dv2, 3) if dv2 else None,
                    "dv3_dist_to_ref": round(dv3, 3) if dv3 else None}

    print(json.dumps(out, indent=2))
    with open(os.path.join(VID, "metrics.json"), "w") as fh:
        json.dump(out, fh, indent=2)


if __name__ == "__main__":
    if not VID:
        sys.exit("set EXP026_VIDS")
    main()
