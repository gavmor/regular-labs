"""Build h3-exp-015: does a reference preserve motion in a subject already moving?

THE GAP THIS CLOSES

exp-014 found a reference video cuts seed-to-seed variation 81.8% while motion
ROSE (0.50 -> 2.32). But its no-reference baseline was nearly frozen at 0.50.
So exp-014 demonstrates a reference WAKING a still subject. Whether it
PRESERVES motion in a subject that is already acting is untested, and that is
the published report's leading limitation.

It matters because the two possibilities point opposite ways for production:

  PRESERVES  -> feed the reference on every shot, unconditionally.
  SUPPRESSES -> the reference and the pose control fight; you get consistency
                at the cost of the action, and the recipe needs a caveat.

THE DESIGN

A pose skeleton supplies the motion exp-014's baseline lacked. Its arms move:
h3-exp-013 measured skeleton-driven motion at 4.75-4.86 against guided arms at
1.08-2.43, so the skeleton reliably produces an acting subject.

  factor 1: pose skeleton, always present (this is what makes it move)
  factor 2: reference video, present or absent
  factor 3: seed, 43/44/45/46

Same prompt throughout. Same reference clip as exp-014 (a prior H3 render of
this prompt's own subject), so the two experiments are directly comparable --
only the skeleton is added.

Both arms carry FunControl. exp-014's arms carried none. That is the single
deliberate difference between the experiments.
"""
import copy
import hashlib
import json
import os
import subprocess

SRC = ("/home/user/code/genops-pipelines.h3-vace-props"
       "/workflows/h3-exp-010-arms/skeleton_s43.api.json")
OUT = "/home/user/code/genops-pipelines.h3-vace-props/workflows/h3-exp-015-arms"
SEEDS = [43, 44, 45, 46]
W, H, LEN = 832, 480, 124          # matches exp-014 exactly
REF = "char_ref_90.mp4"            # the same reference exp-014 used

assert (LEN - 5) % 17 == 0, "shot length must satisfy 17n+5"
os.makedirs(OUT, exist_ok=True)

base = json.load(open(SRC))
PROMPT = base["11"]["inputs"]["prompt"]
assert base["63"]["class_type"] == "H3FunControlApply", "node 63 must be FunControl"
# The control video must match the shot in length, width AND height --
# H3FunControlApply packs it into the same token stream and refuses a
# mismatch. The published skeleton is 1312x736x294 (82,041 tokens); this
# shot is 832x480x124 (14,430), so a rescaled copy is required. exp-014
# removed FunControl entirely, which is why it never hit this.
SKELETON = "pose_832x480_124.mp4"
assert base["60"]["inputs"]["file"] == "pose_briefcase_hq.mp4", "source skeleton moved"
def _probe(name, *keys):
    """Probe the installed input via a host-side copy.

    The ComfyUI container has no ffprobe, so the file is copied out and
    measured here. It must be measured AS INSTALLED -- probing the local
    build artifact would pass even if the copy into the container failed.
    """
    import subprocess as sp
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        local = os.path.join(td, name)
        sp.run(["docker", "cp", f"comfyui-local:/opt/ComfyUI/input/{name}", local],
               check=True, capture_output=True)
        out = sp.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                      "-count_frames", "-show_entries",
                      "stream=" + ",".join(keys), "-of", "default=nw=1:nk=1",
                      local], capture_output=True, text=True,
                     check=True).stdout.split()
    return [int(x) for x in out]


_w, _h, _n = _probe(SKELETON, "width", "height", "nb_read_frames")
assert (_w, _h, _n) == (W, H, LEN), (
    f"control is {_w}x{_h}x{_n}, shot is {W}x{H}x{LEN} -- FunControl will "
    f"reject this at sampling time, after the GPU lock is taken")
print(f"skeleton control video: {SKELETON} ({_w}x{_h}x{_n}, matches shot)")
print(f"reference video:        {REF}")

written = []
for arm in ("skel_noref", "skel_ref"):
    for seed in SEEDS:
        g = copy.deepcopy(base)
        g["9"]["inputs"]["noise_seed"] = seed
        g["11"]["inputs"]["width"] = W
        g["11"]["inputs"]["height"] = H
        g["11"]["inputs"]["length"] = LEN

        # node 60/61 = the skeleton's LoadVideo -> GetVideoComponents, feeding
        # FunControl at node 63. Both arms keep it; that is the motion source.
        g["60"]["inputs"]["file"] = SKELETON

        if arm == "skel_ref":
            # A SECOND loader chain for the reference, wired to ref_videos.
            # Reusing nodes 60/61 would hand the skeleton to both inputs.
            g["80"] = {"inputs": {"file": REF},
                       "class_type": "LoadVideo",
                       "_meta": {"title": "LoadVideo (reference)"}}
            g["81"] = {"inputs": {"video": ["80", 0]},
                       "class_type": "GetVideoComponents",
                       "_meta": {"title": "GetVideoComponents (reference)"}}
            g["11"]["inputs"]["ref_videos.ref_video_0"] = ["81", 0]

        name = f"{arm}_s{seed}"
        g["19"]["inputs"]["filename_prefix"] = f"H3/exp015/{name}"
        p = os.path.join(OUT, f"{name}.api.json")
        json.dump(g, open(p, "w"), indent=2)
        written.append((name, p, arm))

seen = {}
for name, p, arm in written:
    g = json.load(open(p))
    g.pop("19", None)
    h = hashlib.sha256(json.dumps(g, sort_keys=True).encode()).hexdigest()[:16]
    assert h not in seen, f"{name} is identical to {seen[h]}"
    seen[h] = name

    n11 = [x for x in g.values() if x.get("class_type") == "MiniMaxH3ReferenceToVideo"][0]
    has_ref = any(k.startswith("ref_videos") for k in n11["inputs"])
    has_fc = any(x.get("class_type") == "H3FunControlApply" for x in g.values())

    assert has_fc, f"{name}: the skeleton must be present in BOTH arms"
    assert has_ref == (arm == "skel_ref"), f"{name}: reference wiring wrong"
    assert n11["inputs"]["prompt"] == PROMPT, f"{name}: prompt drifted"

    if has_ref:
        # The reference must come from its own loader, never the skeleton's.
        src_node = n11["inputs"]["ref_videos.ref_video_0"][0]
        assert g[src_node]["class_type"] == "GetVideoComponents"
        feeder = g[src_node]["inputs"]["video"][0]
        assert g[feeder]["inputs"]["file"] == REF, (
            f"{name}: ref_videos is fed {g[feeder]['inputs']['file']}, not {REF}")
        assert g["60"]["inputs"]["file"] == SKELETON, (
            f"{name}: FunControl lost its skeleton")

    print(f"  {name:16} skeleton={has_fc!s:5} reference={has_ref!s:5} hash={h}")

print(f"\nOK: {len(written)} arms, hashes distinct, prompt identical,"
      f" skeleton in all, reference in half")
