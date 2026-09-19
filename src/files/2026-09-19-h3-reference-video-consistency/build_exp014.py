"""Build h3-exp-014: is a reference video a character-consistency lever?

THE OBSERVATION THAT PROMPTED THIS

In h3-exp-012 the seed-to-seed distance under ref_videos was 7.16, against
11.38 for the same prompt under a pose skeleton. A reference video made the
output roughly half as sensitive to the seed. Character consistency across
shots is a real production problem, so a lever on it is worth testing directly.

THE TRAP, AND THE DISCRIMINATOR

Those exp-012 arms were static and generic. A reference can reduce seed
variation two ways:

  STABILISING -- identity is pinned across seeds while the subject still acts.
                 Useful.
  FLATTENING  -- every seed collapses toward the same inert portrait. The
                 numbers look identical and the capability is worthless.

Seed variation alone cannot tell these apart, which is why exp-012's 7.16 is
suggestive rather than conclusive. Two measures together can:

  seed variation   how much output changes when only the seed changes
  temporal motion  how much the subject moves within a clip

  reference reduces seed variation AND preserves motion -> STABILISING
  reference reduces both                                -> FLATTENING

That pairing is the whole design, registered before rendering.

THE REFERENCE IS A PRIOR RENDER

Not the briefcase guide. The production use case is "render a character once,
then keep her across later shots", so the reference is an earlier H3 render of
this very prompt's subject -- exp-010's seed-43 clip, trimmed to 90 frames and
scaled to the shot. That is the workflow someone would actually run.

CHEAPER ARMS, MORE SEEDS

832x480 at 124 frames rather than 1312x736 at 294. This is a new question, not
a comparison against exp-010/011/012, so nothing needs to match their
resolution -- and the smaller shot buys FOUR seeds per arm instead of two.
Seed variation is then estimated from six pairs per arm rather than one, which
is a far better floor than anything else in this arc.
"""
import copy
import hashlib
import json
import os
import subprocess

SRC = (
    "/home/user/code/genops-pipelines.h3-vace-props"
    "/workflows/h3-exp-010-arms/skeleton_s43.api.json"
)
OUT = "/home/user/code/genops-pipelines.h3-vace-props/workflows/h3-exp-014-arms"
SEEDS = [43, 44, 45, 46]
W, H, LEN = 832, 480, 124          # 124 = 17*7+5
REF_FRAMES = 90                    # 17*5+5, inside ref_videos' 2-15s window

assert (LEN - 5) % 17 == 0, "shot length must satisfy 17n+5"
assert (REF_FRAMES - 5) % 17 == 0, "reference length must satisfy 17n+5"

os.makedirs(OUT, exist_ok=True)

# --- build the reference from a prior render of the same character ---------
subprocess.run(
    ["ffmpeg", "-y", "-v", "error", "-i", "/tmp/exp010/skeleton_s43_00002_.mp4",
     "-vf", f"select='lt(n,{REF_FRAMES})',scale={W}:{H}:flags=lanczos",
     # -an: trimming video without touching the audio stream leaves a clip
     # whose container runs to the ORIGINAL audio length, so playback freezes
     # on the last video frame while sound continues. The node reads the
     # decoded frame tensor and never consults container duration, so this
     # does not reach the render -- but it makes the artifact unviewable.
     "-vsync", "0", "-an",
     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "12",
     "/tmp/char_ref_90.mp4"],
    check=True,
)
n = int(subprocess.run(
    ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
     "-show_entries", "stream=nb_read_frames", "-of", "default=nw=1:nk=1",
     "/tmp/char_ref_90.mp4"], capture_output=True, text=True, check=True).stdout.strip())
assert n == REF_FRAMES, f"reference is {n} frames, expected {REF_FRAMES}"

# Frame count alone passes a clip whose container outruns its video stream.
vdur = float(subprocess.run(
    ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
     "stream=duration", "-of", "default=nw=1:nk=1", "/tmp/char_ref_90.mp4"],
    capture_output=True, text=True, check=True).stdout.strip())
cdur = float(subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
     "-of", "default=nw=1:nk=1", "/tmp/char_ref_90.mp4"],
    capture_output=True, text=True, check=True).stdout.strip())
assert abs(vdur - cdur) < 0.05, (
    f"container runs {cdur:.2f}s against {vdur:.2f}s of video -- playback "
    f"will freeze on the last frame")
subprocess.run(["docker", "cp", "/tmp/char_ref_90.mp4",
                "comfyui-local:/opt/ComfyUI/input/char_ref_90.mp4"], check=True)
print(f"reference: {n} frames at {W}x{H}, installed as char_ref_90.mp4")

base = json.load(open(SRC))
assert base["3"]["inputs"]["clip_name"] == "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
PROMPT = base["11"]["inputs"]["prompt"]

written = []
for arm in ("noref", "ref"):
    for seed in SEEDS:
        g = copy.deepcopy(base)
        g["9"]["inputs"]["noise_seed"] = seed
        g["11"]["inputs"]["width"] = W
        g["11"]["inputs"]["height"] = H
        g["11"]["inputs"]["length"] = LEN

        # Both arms drop FunControl entirely: the question is about the
        # reference input, and leaving a control video attached would make any
        # effect unattributable between the two.
        control_src = g["63"]["inputs"]["model"]
        for node in g.values():
            for k, v in (node.get("inputs") or {}).items():
                if isinstance(v, list) and len(v) == 2 and str(v[0]) == "63":
                    node["inputs"][k] = control_src
        del g["63"]
        g.pop("62", None)

        if arm == "ref":
            g["60"]["inputs"]["file"] = "char_ref_90.mp4"
            g["11"]["inputs"]["ref_videos.ref_video_0"] = ["61", 0]
        else:
            # no reference at all -- strip the video loader chain
            for nid in ("60", "61"):
                g.pop(nid, None)

        name = f"{arm}_s{seed}"
        g["19"]["inputs"]["filename_prefix"] = f"H3/exp014/{name}"
        p = os.path.join(OUT, f"{name}.api.json")
        json.dump(g, open(p, "w"), indent=2)
        written.append((name, p, arm))

seen = {}
for name, p, arm in written:
    g = json.load(open(p))
    g.pop("19", None)
    h = hashlib.sha256(json.dumps(g, sort_keys=True).encode()).hexdigest()[:16]
    assert h not in seen, f"{name} identical to {seen[h]}"
    seen[h] = name

    n11 = [x for x in g.values() if x.get("class_type") == "MiniMaxH3ReferenceToVideo"][0]
    has_ref = any(k.startswith("ref_videos") for k in n11["inputs"])
    has_fc = any(x.get("class_type") == "H3FunControlApply" for x in g.values())
    assert not has_fc, f"{name}: FunControl must be absent from both arms"
    assert has_ref == (arm == "ref"), f"{name}: reference wiring does not match arm"
    assert n11["inputs"]["prompt"] == PROMPT, f"{name}: prompt drifted"
    print(f"  {name:12} ref={has_ref!s:5} funcontrol={has_fc!s:5} {W}x{H}x{LEN} hash={h}")

print(f"\nOK: {len(written)} arms, hashes distinct, prompt identical across all")
