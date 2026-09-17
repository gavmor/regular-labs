#!/usr/bin/env python3
"""Measure how far each quantised H3 text encoder's CONDITIONING drifts from bf16.

Why this exists
---------------
r/StableDiffusion post 1whr5j7 produced four flatly contradictory claims about
H3 text-encoder quants ("int8 convrot, the nvfp4 or int4s aren't worth it" vs
"no visible difference"), none of them measured. Both camps claim to have
compared. Neither published a number.

Conditioning distance settles the factual half of that argument, because it is
deterministic: same prompt + same encoder = same tensor, every time. No seed,
no sampler, no taste. What it does NOT settle is whether the difference is
VISIBLE -- that needs pixels, and pixels need a noise floor (see phase 2).

Method
------
For each encoder, encode an identical prompt set and capture the raw
CONDITIONING via RES4LYF's ConditioningToBase64, which pickles the tensor and
base64s it -- lossless, verified by reading its source. Then, against the bf16
(unquantised) reference:

  cosine distance  = 1 - cos(flat(q), flat(ref))   -- direction change
  relative L2      = ||q - ref|| / ||ref||          -- magnitude change

Both are reported because they answer different questions. A quant can
preserve direction while scaling magnitude (which the model may partly absorb)
or leave magnitude alone while rotating the vector (which it will not).

House rules: stdlib only, no network, no third-party deps. Torch is imported
only because the pickled payload contains torch tensors, and it is already in
the ComfyUI image where this runs.
"""

import argparse
import base64
import json
import pickle
import sys
import urllib.request

# Six prompts, chosen to stress different parts of the encoder rather than to
# be pretty. Quantisation error is not uniform across the input distribution:
# rare tokens and long-range structure are where low-bit weights are expected
# to hurt most, so the set deliberately spans short/long, concrete/abstract,
# and includes one non-English line and one with unusual proper nouns.
PROMPTS = [
    # 1. short and concrete -- the easy case
    "A red apple on a wooden table.",
    # 2. long, many independently checkable attributes -- the same instrument
    #    used in h3-exp-007, reused so the two experiments are comparable
    "Live-action photorealistic cinematic film footage. FULL BODY SHOT, the "
    "entire figure visible head to feet. Camera locked off and static at "
    "standing eye level. A woman with short platinum-blonde hair stands in the "
    "centre of frame. She wears a bright yellow sleeveless A-line mini dress "
    "with a single wide horizontal black stripe across the waist, and white "
    "knee-high boots. She holds a closed red umbrella in her left hand, "
    "pointing down at the floor. Her right arm is raised, hand above her "
    "shoulder, waving slowly. Behind her on the left stands a tall green "
    "potted plant. The wall behind is plain pale blue. Soft even studio "
    "lighting. Shot on 35mm film, 1968.",
    # 3. abstract / non-visual -- no concrete referent to anchor on
    "The bittersweet feeling of nostalgia for a place you have never been.",
    # 4. rare proper nouns and technical vocabulary -- low-frequency tokens
    "A Zeiss Planar lens resting beside a Nagra IV-S reel-to-reel recorder, "
    "photographed on Kodak Ektachrome.",
    # 5. non-English -- the ClipProj author's own benchmark found language is
    #    where small/projected encoders diverge most, so it is worth probing
    "Une femme en manteau rouge marche lentement sous la pluie a Paris.",
    # 6. negation and spatial relations -- structure rather than nouns
    "An empty room with no furniture, a single window on the left wall, and "
    "light falling across the floor from right to left.",
]


def encode_and_capture(url, clip_name, prompt, timeout=900, width=832, height=480, length=124):
    """Run a minimal graph: CLIPLoader -> MiniMaxH3ReferenceToVideo -> ToBase64.

    Deliberately NOT a render -- no sampler, no decode, no video file. This
    loads the encoder, encodes one prompt, and returns the conditioning tensor,
    which is why the whole sweep costs minutes rather than hours and needs no
    seed.

    There is no standalone H3 text-encode node: the prompt enters the graph
    through MiniMaxH3ReferenceToVideo, which is also what builds the empty
    latent, so it demands both VAEs even though nothing here decodes anything.
    Verified against /object_info rather than assumed -- an earlier draft of
    this script invented a "MiniMaxH3TextEncode" node that does not exist.

    width/height/length are held constant across arms. They shape the LATENT
    output we discard; the CONDITIONING we measure is a function of the prompt
    and the encoder, which is the comparison we want.
    """
    graph = {
        "1": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"},
        },
        "2": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"},
        },
        "3": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": clip_name, "type": "minimax", "device": "default"},
        },
        "4": {
            "class_type": "MiniMaxH3ReferenceToVideo",
            "inputs": {
                "clip": ["3", 0],
                "vae": ["1", 0],
                "audio_vae": ["2", 0],
                "prompt": prompt,
                "width": width,
                "height": height,
                "length": length,
                "ref_image_size": "match",
            },
        },
        "5": {
            "class_type": "ConditioningToBase64",
            "inputs": {"conditioning": ["4", 0]},
        },
    }
    body = json.dumps({"prompt": graph}).encode()
    req = urllib.request.Request(
        f"{url}/prompt", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        pid = json.load(r)["prompt_id"]

    # poll history
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3)
        with urllib.request.urlopen(f"{url}/history/{pid}", timeout=30) as r:
            hist = json.load(r)
        if pid not in hist:
            continue
        entry = hist[pid]
        status = entry.get("status", {})
        if status.get("status_str") == "error":
            raise RuntimeError(f"execution failed: {json.dumps(status)[:800]}")
        if not status.get("completed"):
            continue
        for node_out in entry.get("outputs", {}).values():
            for key in ("string", "text"):
                vals = node_out.get(key)
                if vals:
                    return vals[0] if isinstance(vals, list) else vals
        raise RuntimeError(f"no string output found: {json.dumps(entry.get('outputs'))[:400]}")
    raise TimeoutError(f"prompt {pid} did not finish in {timeout}s")


def to_flat(b64):
    """Decode the pickled CONDITIONING into one flat float list.

    CONDITIONING is [[tensor, dict], ...]. Only the tensor is compared; the
    dict carries pooled/metadata that varies structurally between models.
    """
    import torch  # noqa: F401 -- required to unpickle torch tensors

    obj = pickle.loads(base64.b64decode(b64))
    parts = []
    for item in obj:
        t = item[0]
        parts.append(t.detach().to("cpu").float().flatten())
    return torch.cat(parts)


def compare(ref, other):
    import torch

    if ref.numel() != other.numel():
        return {
            "comparable": False,
            "reason": f"shape mismatch: ref {ref.numel()} vs {other.numel()}",
        }
    cos = torch.nn.functional.cosine_similarity(ref.unsqueeze(0), other.unsqueeze(0)).item()
    rel_l2 = (torch.linalg.vector_norm(other - ref) / torch.linalg.vector_norm(ref)).item()
    return {
        "comparable": True,
        "cosine_similarity": cos,
        "cosine_distance": 1.0 - cos,
        "relative_l2": rel_l2,
        "ref_norm": torch.linalg.vector_norm(ref).item(),
        "other_norm": torch.linalg.vector_norm(other).item(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8188")
    ap.add_argument("--reference", required=True, help="bf16 encoder filename")
    ap.add_argument("--candidates", nargs="+", required=True)
    ap.add_argument("--out", default="conditioning_fidelity.json")
    ap.add_argument(
        "--self-check",
        action="store_true",
        help="encode the reference TWICE and compare it to itself; must be "
        "exactly 0 distance, otherwise the instrument is not deterministic "
        "and no other number here means anything",
    )
    args = ap.parse_args()

    results = {"reference": args.reference, "prompts": len(PROMPTS), "per_prompt": []}

    for i, prompt in enumerate(PROMPTS):
        print(f"--- prompt {i + 1}/{len(PROMPTS)}: {prompt[:60]}...", flush=True)
        print(f"    encoding with REFERENCE {args.reference}", flush=True)
        ref_flat = to_flat(encode_and_capture(args.url, args.reference, prompt))
        row = {"index": i, "prompt": prompt, "ref_elements": int(ref_flat.numel()), "arms": {}}

        if args.self_check:
            again = to_flat(encode_and_capture(args.url, args.reference, prompt))
            row["self_check"] = compare(ref_flat, again)
            d = row["self_check"].get("cosine_distance")
            print(f"    SELF-CHECK cosine_distance={d:.3e} (must be ~0)", flush=True)

        for cand in args.candidates:
            print(f"    encoding with {cand}", flush=True)
            try:
                flat = to_flat(encode_and_capture(args.url, cand, prompt))
                row["arms"][cand] = compare(ref_flat, flat)
                m = row["arms"][cand]
                if m.get("comparable"):
                    print(
                        f"      cos_dist={m['cosine_distance']:.6f}  rel_l2={m['relative_l2']:.6f}",
                        flush=True,
                    )
            except Exception as e:  # noqa: BLE001 -- record, don't abort the sweep
                row["arms"][cand] = {"comparable": False, "reason": str(e)[:300]}
                print(f"      FAILED: {str(e)[:200]}", flush=True)

        results["per_prompt"].append(row)

    # aggregate
    agg = {}
    for cand in args.candidates:
        vals = [
            r["arms"][cand]
            for r in results["per_prompt"]
            if r["arms"].get(cand, {}).get("comparable")
        ]
        if vals:
            agg[cand] = {
                "n": len(vals),
                "mean_cosine_distance": sum(v["cosine_distance"] for v in vals) / len(vals),
                "max_cosine_distance": max(v["cosine_distance"] for v in vals),
                "mean_relative_l2": sum(v["relative_l2"] for v in vals) / len(vals),
                "max_relative_l2": max(v["relative_l2"] for v in vals),
            }
        else:
            agg[cand] = {"n": 0, "note": "no comparable measurements"}
    results["aggregate"] = agg

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)

    # The self-check is NOT a pass/fail assertion -- it is the instrument's own
    # NOISE FLOOR, and it is not zero. Encoding the same prompt twice with the
    # SAME encoder gave cosine distances around 1e-5 to 6e-4 on this rig
    # (non-deterministic GPU kernels: reduction order varies between runs).
    #
    # That makes it the direct analogue of the seed noise floor used for pixel
    # comparisons. A quant whose distance from the reference sits at or below
    # this floor is indistinguishable from the SAME encoder run twice, and no
    # claim about its quality can rest on that number.
    floors = [
        r["self_check"]["cosine_distance"]
        for r in results["per_prompt"]
        if r.get("self_check", {}).get("comparable")
    ]
    if floors:
        floor = max(abs(f) for f in floors)
        results["noise_floor"] = {
            "max_abs_self_cosine_distance": floor,
            "per_prompt": floors,
            "meaning": "same encoder, same prompt, encoded twice. Any candidate "
            "at or below this is indistinguishable from run-to-run noise.",
        }
    else:
        floor = None

    print("\n=== aggregate, vs reference ===")
    if floor is not None:
        print(f"instrument noise floor (same encoder twice): {floor:.3e}")
    print(f"{'encoder':52} {'mean cos dist':>14} {'mean rel L2':>12} {'x floor':>9}")
    for cand, m in sorted(agg.items(), key=lambda kv: kv[1].get("mean_cosine_distance", 9e9)):
        if m.get("n"):
            ratio = (m["mean_cosine_distance"] / floor) if floor else float("nan")
            verdict = "  <-- AT NOISE FLOOR" if floor and ratio <= 1.0 else ""
            print(
                f"{cand:52} {m['mean_cosine_distance']:>14.6f} "
                f"{m['mean_relative_l2']:>12.6f} {ratio:>9.1f}{verdict}"
            )
        else:
            print(f"{cand:52} {'--':>14} {'--':>12} {'--':>9}  {m.get('note', '')}")

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
