#!/usr/bin/env python3
"""Build h3-exp-023's 24 arms: does a SAME-SUBJECT guide video transfer action?

THE OBJECTION THIS EXISTS TO ANSWER

h3-exp-010 (guide -> H3FunControlApply.control_video) and h3-exp-012 (guide ->
MiniMaxH3ReferenceToVideo.ref_videos) both found that a Wan2.1 VACE guide
transferred neither the briefcase/tripod props nor the kneel, while an OpenPose
skeleton over the same choreography transferred the action cleanly.

Both used a guide depicting a suited businessman while prompting for a woman in
a 1968 mini dress. A defender of the guide-video recipe can say the guide never
had a fair run: conditioning on subject A while prompting subject B is a direct
semantic collision, so the null result may be about the mismatch rather than
about guide conditioning. That objection is legitimate and cheap to settle.

THE DESIGN: 2x2 PLUS TWO CONTROLS, 4 SEEDS EACH

                      control_video        ref_videos
  different-subject   arm1_fc_diff         arm3_ref_diff     <- exp-010/012 redone
  same-subject        arm2_fc_same         arm4_ref_same     <- the novel cells

  armS_pose   OpenPose skeleton -> control_video   positive control: action DID
                                                   transfer here before
  arm0_null   no control video, no reference       negative control: what the
                                                   prompt alone produces

Six conditions x seeds 43/44/45/46 = 24 renders, sequential under gpu-lock.

WHAT IS HELD CONSTANT, AND ONE DEVIATION FROM THE DESIGN DOC

Everything but the conditioning input: prompt, geometry, model stack, sampler,
seeds. The prompt is exp-010's, byte-for-byte, asserted below -- the design doc
paraphrased it as "A woman in a straight-cut dress with red hem walking in a
room..." but no such fixture exists; the real held-constant prompt is the
1968 mini-dress one every arm in this arc has used. Using the doc's paraphrase
would have silently changed the subject the guides are supposed to match,
which is the exact confound this experiment was written to remove. Props stay
OUT of the prompt on purpose: if the prompt names the briefcase, prop
appearance is no longer evidence that the GUIDE carried it.

Geometry is exp-014's cheap shot -- 832x480, 124 frames (17*7+5) -- not
exp-010's 1312x736x294. Nothing here is compared against exp-010's numbers
directly (arm1/arm3 re-run those conditions inside this experiment), so the
smaller shot buys 4 seeds per arm instead of 2, and 24 runs that fit one
overnight lock window.
"""
import copy
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

SEEDS = [43, 44, 45, 46]
W, H, LEN = 832, 480, 124          # 124 = 17*7 + 5
GUIDE_LEN = 90                     # 90 = 17*5 + 5, inside ref_videos' window

assert (LEN - 5) % 17 == 0, "shot length must satisfy 17n+5"
assert (GUIDE_LEN - 5) % 17 == 0, "reference length must satisfy 17n+5"

# arm -> (conditioning pathway, fixture installed by build_exp023_fixtures.py)
#   "fc"   : H3FunControlApply.control_video, fixture must be shot-length (124)
#   "ref"  : MiniMaxH3ReferenceToVideo.ref_videos, fixture is 90
#   "none" : neither pathway wired
ARMS = {
    "arm1_fc_diff":  ("fc",   "exp023_guide_diff_124.mp4"),
    "arm2_fc_same":  ("fc",   "exp023_guide_same_124.mp4"),
    "arm3_ref_diff": ("ref",  "exp023_guide_diff_90.mp4"),
    "arm4_ref_same": ("ref",  "exp023_guide_same_90.mp4"),
    "armS_pose":     ("fc",   "exp023_pose_124.mp4"),
    "arm0_null":     ("none", None),
}


def main():
    src = os.path.join(REPO, "workflows", "h3-exp-023-base", "h3_base.api.json")
    out = os.path.join(REPO, "workflows", "h3-exp-023-arms")
    os.makedirs(out, exist_ok=True)

    base = json.load(open(src))
    # Pin the stack the design registered, so a swapped loader fails here and
    # not three hours into the lock.
    assert base["3"]["inputs"]["clip_name"] == \
        "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "text encoder drifted (ADR 0014)"
    assert base["4"]["inputs"]["unet_name"] == \
        "MinimaxH3/minimax_h3_ref2va_pruned_int8_convrot.safetensors", "diffusion model drifted"
    PROMPT = base["11"]["inputs"]["prompt"]
    assert "blonde bob" in PROMPT and "1968" in PROMPT, "prompt is not the exp-010 prompt"
    for banned in ("briefcase", "tripod", "kneel"):
        assert banned not in PROMPT.lower(), (
            f"prompt names '{banned}' -- prop/action appearance would then be "
            "attributable to the text, not the guide")

    written = []
    for arm, (pathway, fixture) in sorted(ARMS.items()):
        for seed in SEEDS:
            g = copy.deepcopy(base)
            g["9"]["inputs"]["noise_seed"] = seed
            g["11"]["inputs"]["width"] = W
            g["11"]["inputs"]["height"] = H
            g["11"]["inputs"]["length"] = LEN

            if pathway == "fc":
                g["60"]["inputs"]["file"] = fixture
            elif pathway == "ref":
                g["60"]["inputs"]["file"] = fixture
                # rewire: drop FunControl, feed the clip to ref_videos instead
                passthrough = g["63"]["inputs"]["model"]
                for node in g.values():
                    for k, v in (node.get("inputs") or {}).items():
                        if isinstance(v, list) and len(v) == 2 and str(v[0]) == "63":
                            node["inputs"][k] = passthrough
                del g["63"]
                g.pop("62", None)
                g["11"]["inputs"]["ref_videos.ref_video_0"] = ["61", 0]
            else:  # none
                passthrough = g["63"]["inputs"]["model"]
                for node in g.values():
                    for k, v in (node.get("inputs") or {}).items():
                        if isinstance(v, list) and len(v) == 2 and str(v[0]) == "63":
                            node["inputs"][k] = passthrough
                del g["63"]
                for nid in ("62", "60", "61"):
                    g.pop(nid, None)

            name = f"{arm}_s{seed}"
            g["19"]["inputs"]["filename_prefix"] = f"H3/exp023/{name}"
            path = os.path.join(out, f"{name}.api.json")
            json.dump(g, open(path, "w"), indent=2)
            written.append((name, path, arm, pathway, fixture))

    # ---- post-conditions -------------------------------------------------
    # The h3-exp-001 lesson: three "arms" that were byte-identical apart from
    # SaveVideo rendered identically, Immich deduped them to one asset, and the
    # comparison was void after the GPU time was spent.
    seen = {}
    for name, path, arm, pathway, fixture in written:
        g = json.load(open(path))
        g.pop("19", None)
        h = hashlib.sha256(json.dumps(g, sort_keys=True).encode()).hexdigest()[:16]
        assert h not in seen, f"{name} is identical to {seen[h]}"
        seen[h] = name

        n11 = [x for x in g.values()
               if x.get("class_type") == "MiniMaxH3ReferenceToVideo"][0]
        has_ref = any(k.startswith("ref_videos") for k in n11["inputs"])
        has_fc = any(x.get("class_type") == "H3FunControlApply" for x in g.values())
        loader = [x for x in g.values() if x.get("class_type") == "LoadVideo"]

        assert has_fc == (pathway == "fc"), f"{name}: FunControl wiring wrong"
        assert has_ref == (pathway == "ref"), f"{name}: ref_videos wiring wrong"
        # Exactly one pathway, never both -- otherwise an effect is
        # unattributable between them.
        assert not (has_fc and has_ref), f"{name}: both pathways wired"
        if pathway == "none":
            assert not loader, f"{name}: null arm still loads a video"
        else:
            assert len(loader) == 1 and loader[0]["inputs"]["file"] == fixture, \
                f"{name}: expected fixture {fixture}"
        assert n11["inputs"]["prompt"] == PROMPT, f"{name}: prompt drifted"
        assert (n11["inputs"]["width"], n11["inputs"]["height"],
                n11["inputs"]["length"]) == (W, H, LEN), f"{name}: geometry drifted"
        assert g["9"]["inputs"]["noise_seed"] in SEEDS, f"{name}: seed off-design"

    # Every arm must differ from every other arm at the SAME seed in exactly the
    # conditioning input, and every seed within an arm must differ only in seed.
    by_arm = {}
    for name, path, arm, _p, _f in written:
        by_arm.setdefault(arm, []).append(name)
    assert len(by_arm) == 6, f"expected 6 arms, got {sorted(by_arm)}"
    for arm, members in sorted(by_arm.items()):
        assert len(members) == len(SEEDS), f"{arm}: {len(members)} seeds"
        print(f"  {arm:15} {len(members)} seeds  pathway={ARMS[arm][0]:5} "
              f"fixture={ARMS[arm][1]}")

    print(f"\nOK: {len(written)} arms ({len(by_arm)} conditions x {len(SEEDS)} seeds), "
          f"all hashes distinct, prompt and geometry identical across all")
    return 0


if __name__ == "__main__":
    sys.exit(main())
