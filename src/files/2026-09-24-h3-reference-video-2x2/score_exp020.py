#!/usr/bin/env python3
"""Score h3-exp-020: is the H3 reference pathway subject-bound, engine-bound,
both, or just a generic variance clamp?

The 2x2 is subject identity (same/different) x reference render engine (H3/Wan),
plus an unconditioned null arm. Every number is measured HERE, in this
configuration: the null arm supplies the floor rather than a figure borrowed
from exp-012 or exp-014 at different settings. Prior numbers are context in the
write-up, never the baseline in the arithmetic.

Three measures per arm, matching h3-exp-023's scorer so the two are comparable:

    seed_variation  mean pairwise pixel distance across the arm's four seeds.
                    How much the output moves when only the seed changes.
    motion          mean absolute frame-to-frame difference. Guards the failure
                    where consistency is bought by freezing the subject.
    dist_to_ref     distance from each arm to the reference clip it was given.
                    Low distance + dead motion = the reference is being
                    replayed, which is leakage, not identity transfer.

Garment/identity retention (DV3) is a DISCRETE READING made by looking at
frames, not a pixel metric. There is no dress detector here and dressing a
judgement call up as a measurement would be worse than admitting it. What this
script does is make the reading auditable: one frame grid per arm at FIXED
frame indices, identical across arms, so the same moments are compared.
"""
import argparse
import json
import os
import subprocess
from itertools import combinations

# Fixed sampling points, identical for every arm. 90-frame shots.
GRID_FRAMES = [4, 21, 38, 55, 72, 88]

CONDITIONS = ["A_same_h3", "B_diff_h3", "C_same_wan", "D_diff_wan", "null_noref"]
SEEDS = [43, 44, 45, 46]

# The reference fixture each arm was conditioned on. The null arm has none by
# construction -- that is what makes it the floor.
REF_OF = {
    "A_same_h3": "char_ref_90.mp4",
    "B_diff_h3": "h3_diff_subject_90.mp4",
    "C_same_wan": "wan_same_subject_90.mp4",
    "D_diff_wan": "vace_guide_90.mp4",
}


def frame_count(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=nb_read_frames", "-of", "default=nw=1:nk=1",
         path],
        capture_output=True, text=True, check=True)
    return int(out.stdout.strip())


def frames(path, stride=8, limit=90):
    """Decode a clip to a small RGB array, sampled every `stride` frames.

    stride=8 for the pairwise measures, per the design doc's DV1.
    """
    import numpy as np
    n = min(frame_count(path), limit)
    idx = list(range(0, n, stride))
    sel = "+".join(f"eq(n\\,{i})" for i in idx)
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path,
         "-vf", f"select='{sel}',scale=320:180", "-vsync", "0",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True)
    arr = np.frombuffer(proc.stdout, dtype=np.uint8)
    return arr.reshape(-1, 180, 320, 3).astype("int16")


def mean_abs_diff(a, b):
    import numpy as np
    fa, fb = frames(a), frames(b)
    n = min(len(fa), len(fb))
    return float(np.abs(fa[:n] - fb[:n]).mean())


def motion_of(path):
    """Mean absolute frame-to-frame difference within one clip."""
    import numpy as np
    f = frames(path, stride=2)
    if len(f) < 2:
        return 0.0
    return float(np.abs(f[1:] - f[:-1]).mean())


def motion_series(path, stride=2, limit=90):
    """Per-step motion through the clip, as a series rather than one mean.

    Two clips can share an average motion while moving at completely different
    moments. The series is what tells you whether an arm is moving IN TIME WITH
    its reference or merely moving as much as it.
    """
    import numpy as np
    f = frames(path, stride=stride, limit=limit)
    if len(f) < 2:
        return np.zeros(1)
    return np.abs(f[1:] - f[:-1]).mean(axis=(1, 2, 3))


def motion_corr(a, b):
    """Pearson r between two clips' motion series over their common length.

    This is the measurement behind any claim that a reference transferred its
    CHOREOGRAPHY. A still frame grid cannot support that claim -- it shows
    poses at sampled instants and says nothing about what happened between
    them -- so the claim is made here, in numbers, or not at all.
    """
    import numpy as np
    sa, sb = motion_series(a), motion_series(b)
    n = min(len(sa), len(sb))
    if n < 3:
        return None
    sa, sb = sa[:n], sb[:n]
    if sa.std() < 1e-6 or sb.std() < 1e-6:
        # A frozen clip has no temporal shape to correlate against.
        return None
    return float(np.corrcoef(sa, sb)[0, 1])


def build_grid(path, out_png, tile_w=400):
    sel = "+".join(f"eq(n\\,{n})" for n in GRID_FRAMES)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", path,
         "-vf", f"select='{sel}',scale={tile_w}:-1,tile={len(GRID_FRAMES)}x1",
         "-frames:v", "1", out_png],
        check=True)
    return out_png


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets-dir", required=True)
    ap.add_argument("--fixtures-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    # Map arm -> rendered file. Only the render, never the reference echo that
    # sits beside it in the asset dir: matching on the "_00001_" suffix keeps
    # char_ref_90.mp4 and friends out of the measurement.
    clips = {}
    for f in sorted(os.listdir(args.assets_dir)):
        if not f.endswith(".mp4") or "_00001_" not in f:
            continue
        for cond in CONDITIONS:
            for s in SEEDS:
                arm = f"{cond}_s{s}"
                if f.startswith(arm + "_"):
                    clips[arm] = os.path.join(args.assets_dir, f)

    expected = [f"{c}_s{s}" for c in CONDITIONS for s in SEEDS]
    missing = [a for a in expected if a not in clips]
    if missing:
        raise SystemExit(f"FAILED: missing {len(missing)} arms: {missing}")
    print(f"found all {len(expected)} arms")

    report = {"arms": {}, "conditions": {}, "grids": {}}

    for arm in expected:
        p = clips[arm]
        report["arms"][arm] = {
            "file": os.path.basename(p),
            "frames": frame_count(p),
            "bytes": os.path.getsize(p),
        }

    # One grid per condition at seed 43, so the identity reading is auditable.
    for cond in CONDITIONS:
        g = build_grid(clips[f"{cond}_s43"], os.path.join(args.out_dir, f"{cond}.png"))
        report["grids"][cond] = g
        print(f"  grid {cond:12} -> {g}")

    print("\n  per-condition measures:")
    for cond in CONDITIONS:
        paths = [clips[f"{cond}_s{s}"] for s in SEEDS]
        pair = [mean_abs_diff(a, b) for a, b in combinations(paths, 2)]
        mot = [motion_of(p) for p in paths]
        entry = {
            "seed_variation": round(sum(pair) / len(pair), 2),
            "seed_pairwise": [round(x, 2) for x in sorted(pair)],
            "motion": round(sum(mot) / len(mot), 2),
            "motion_per_seed": [round(x, 2) for x in mot],
        }
        fixture = REF_OF.get(cond)
        if fixture:
            fp = os.path.join(args.fixtures_dir, fixture)
            if os.path.exists(fp):
                d = [mean_abs_diff(p, fp) for p in paths]
                entry["dist_to_ref"] = round(sum(d) / len(d), 2)
                entry["ref_motion"] = round(motion_of(fp), 2)
                entry["ref_file"] = fixture
                # Does the arm move IN TIME with its reference? Mean motion
                # alone cannot answer that; correlated motion series can.
                corrs = [motion_corr(p, fp) for p in paths]
                corrs = [c for c in corrs if c is not None]
                entry["motion_corr_to_ref"] = (
                    round(sum(corrs) / len(corrs), 3) if corrs else None)
            else:
                raise SystemExit(f"FAILED: fixture {fp} missing; dist_to_ref "
                                 f"would be silently dropped for {cond}")
        report["conditions"][cond] = entry
        print(f"    {cond:12} seedvar={entry['seed_variation']:6.2f} "
              f"motion={entry['motion']:5.2f} "
              f"dist_to_ref={entry.get('dist_to_ref', 'n/a')} "
              f"motion_corr={entry.get('motion_corr_to_ref', 'n/a')}")

    # Read every arm against the null measured HERE, not against exp-012/014.
    null = report["conditions"]["null_noref"]
    report["null"] = {"seed_variation": null["seed_variation"],
                      "motion": null["motion"]}
    verdicts = {}
    for cond in CONDITIONS:
        if cond == "null_noref":
            continue
        c = report["conditions"][cond]
        dmot = (c["motion"] - null["motion"]) / null["motion"] * 100 if null["motion"] else 0.0
        dvar = (c["seed_variation"] - null["seed_variation"]) / null["seed_variation"] * 100 \
            if null["seed_variation"] else 0.0
        verdicts[cond] = {"motion_vs_null_pct": round(dmot, 1),
                          "seedvar_vs_null_pct": round(dvar, 1)}
    report["vs_null"] = verdicts

    print("\n  against the null arm, measured here:")
    for cond, v in verdicts.items():
        print(f"    {cond:12} motion {v['motion_vs_null_pct']:+7.1f}%  "
              f"seed variation {v['seedvar_vs_null_pct']:+7.1f}%")

    # The two contrasts the 2x2 exists to separate. Each holds one factor fixed.
    report["factor_effects"] = {}
    for label, a, b in (
        ("subject_effect_under_h3", "A_same_h3", "B_diff_h3"),
        ("subject_effect_under_wan", "C_same_wan", "D_diff_wan"),
        ("engine_effect_same_subject", "A_same_h3", "C_same_wan"),
        ("engine_effect_diff_subject", "B_diff_h3", "D_diff_wan"),
    ):
        ca, cb = report["conditions"][a], report["conditions"][b]
        report["factor_effects"][label] = {
            "arms": [a, b],
            "seedvar": [ca["seed_variation"], cb["seed_variation"]],
            "seedvar_delta": round(cb["seed_variation"] - ca["seed_variation"], 2),
            "motion": [ca["motion"], cb["motion"]],
            "motion_delta": round(cb["motion"] - ca["motion"], 2),
        }

    print("\n  factor effects (one factor held fixed in each row):")
    for label, v in report["factor_effects"].items():
        print(f"    {label:28} seedvar {v['seedvar'][0]:6.2f} -> {v['seedvar'][1]:6.2f} "
              f"({v['seedvar_delta']:+.2f})   motion {v['motion'][0]:5.2f} -> "
              f"{v['motion'][1]:5.2f} ({v['motion_delta']:+.2f})")

    with open(args.report, "w") as fh:
        json.dump(report, fh, indent=2)
    print(f"\nwrote {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
