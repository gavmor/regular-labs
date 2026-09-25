#!/usr/bin/env python3
"""h3-exp-021: conditioning fidelity across BOTH weight format AND loader node.

Why this is a separate script from measure_conditioning_fidelity.py
-------------------------------------------------------------------
h3-exp-008 measured four H3 text-encoder quants and deliberately EXCLUDED GGUF
Q4_K_M, recording the reason as an explicit scope limit:

    "GGUF Q4_K_M requires a third-party loader node (molbal/ComfyUI-GGUF).
     Adding an untested loader would confound the quantisation question with a
     loader-implementation question."

That is the right call and it is also the thing exp-021 has to undo. You cannot
answer "is GGUF Q4_K_M worse?" with a script that can only drive one loader,
because every GGUF number it produced would carry an unknown loader offset
baked in. So the loader becomes a declared factor: each arm names BOTH a weight
file and the node that loads it, and the design includes an arm whose weights
are unquantised but whose loader is the third-party one (the loader control).

    delta_loader = distance(gguf_bf16_via_GGUFLoader, safetensors_bf16_via_CLIPLoader)

If delta_loader sits at the instrument noise floor, the loader is transparent
and any GGUF drift is quantisation. If it clears the floor, the loader has its
own offset and every GGUF-vs-safetensors number must be read against the GGUF
control, not against the safetensors reference.

Everything else -- the six prompts, ConditioningToBase64 capture, cosine /
relative-L2 metrics, the repeat-encode noise floor -- is IDENTICAL to
measure_conditioning_fidelity.py on purpose, so exp-021's numbers can be put on
the same axis as exp-008's.

House rules: stdlib only. Torch is imported solely to unpickle the captured
tensors.
"""

import argparse
import base64
import csv
import json
import pickle
import sys
import time
import urllib.request

# Byte-identical to measure_conditioning_fidelity.py's PROMPTS. Do not "improve"
# these: exp-008's published numbers were produced with this exact set, and
# changing a single character makes the two experiments incomparable.
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

# The two loader nodes under comparison. CLIPLoaderGGUF is molbal/ComfyUI-GGUF's
# legacy node; it takes the same (clip_name, type) inputs as the stock loader,
# which is what makes a clean A/B possible at all -- verified against
# /object_info, not assumed.
LOADERS = {
    "CLIPLoader": {"class_type": "CLIPLoader", "extra": {"device": "default"}},
    "CLIPLoaderGGUF": {"class_type": "CLIPLoaderGGUF", "extra": {}},
}


def build_graph(clip_name, loader, prompt, width, height, length):
    """CLIPLoader|CLIPLoaderGGUF -> MiniMaxH3ReferenceToVideo -> ConditioningToBase64.

    Not a render: no sampler, no decode, no video. Loads the encoder, encodes
    one prompt, returns the conditioning. MiniMaxH3ReferenceToVideo is the only
    way a prompt enters an H3 graph (there is no standalone H3 text-encode
    node), and it builds the empty latent, which is why both VAEs are required
    even though nothing here decodes anything.
    """
    spec = LOADERS[loader]
    loader_inputs = {"clip_name": clip_name, "type": "minimax"}
    loader_inputs.update(spec["extra"])
    return {
        "1": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"},
        },
        "2": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"},
        },
        "3": {"class_type": spec["class_type"], "inputs": loader_inputs},
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


def encode_and_capture(
    url, clip_name, loader, prompt, timeout=1800, width=832, height=480, length=124
):
    """Submit the graph and return (base64_conditioning, wall_seconds).

    Wall time is returned because DV 5 of the design asks for load/encode
    overhead per arm, and a 51 GB GGUF dequantising on the fly is exactly the
    kind of thing that is cheap in tensor distance and expensive in seconds.
    """
    graph = build_graph(clip_name, loader, prompt, width, height, length)
    body = json.dumps({"prompt": graph}).encode()
    req = urllib.request.Request(
        f"{url}/prompt", data=body, headers={"Content-Type": "application/json"}
    )
    started = time.time()
    with urllib.request.urlopen(req, timeout=120) as r:
        pid = json.load(r)["prompt_id"]

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3)
        with urllib.request.urlopen(f"{url}/history/{pid}", timeout=60) as r:
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
                    payload = vals[0] if isinstance(vals, list) else vals
                    return payload, time.time() - started
        raise RuntimeError(f"no string output found: {json.dumps(entry.get('outputs'))[:400]}")
    raise TimeoutError(f"prompt {pid} did not finish in {timeout}s")


def to_flat(b64):
    """Decode the pickled CONDITIONING into one flat float tensor."""
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


def parse_arm(spec):
    """'name=file.gguf@CLIPLoaderGGUF' -> (name, file, loader)."""
    name, _, rest = spec.partition("=")
    if not rest:
        raise ValueError(f"arm spec must be name=file@loader, got {spec!r}")
    filename, _, loader = rest.partition("@")
    loader = loader or "CLIPLoader"
    if loader not in LOADERS:
        raise ValueError(f"unknown loader {loader!r}; known: {sorted(LOADERS)}")
    return name, filename, loader


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8188")
    ap.add_argument(
        "--reference",
        required=True,
        help="reference arm, name=file@loader (the unquantised ground truth)",
    )
    ap.add_argument(
        "--arms",
        nargs="+",
        required=True,
        help="candidate arms, each name=file@loader",
    )
    ap.add_argument("--out", default="conditioning_fidelity_gguf.json")
    ap.add_argument(
        "--self-check",
        action="store_true",
        help="encode the reference twice per prompt to measure the instrument's "
        "own noise floor; without it no other number here is interpretable",
    )
    args = ap.parse_args()

    ref_name, ref_file, ref_loader = parse_arm(args.reference)
    arms = [parse_arm(a) for a in args.arms]

    print(f"reference : {ref_name}  {ref_file}  via {ref_loader}")
    for n, f, ldr in arms:
        print(f"arm       : {n}  {f}  via {ldr}")

    results = {
        "reference": {"name": ref_name, "file": ref_file, "loader": ref_loader},
        "arms": [{"name": n, "file": f, "loader": ldr} for n, f, ldr in arms],
        "prompts": len(PROMPTS),
        "per_prompt": [],
    }

    for i, prompt in enumerate(PROMPTS):
        print(f"\n--- prompt {i + 1}/{len(PROMPTS)}: {prompt[:60]}...", flush=True)
        print(f"    encoding REFERENCE {ref_name}", flush=True)
        ref_b64, ref_secs = encode_and_capture(args.url, ref_file, ref_loader, prompt)
        ref_flat = to_flat(ref_b64)
        row = {
            "index": i,
            "prompt": prompt,
            "ref_elements": int(ref_flat.numel()),
            "ref_seconds": ref_secs,
            "arms": {},
        }

        if args.self_check:
            again_b64, _ = encode_and_capture(args.url, ref_file, ref_loader, prompt)
            row["self_check"] = compare(ref_flat, to_flat(again_b64))
            d = row["self_check"].get("cosine_distance")
            print(f"    SELF-CHECK cosine_distance={d:.3e}", flush=True)

        for name, filename, loader in arms:
            print(f"    encoding {name} ({filename} via {loader})", flush=True)
            try:
                b64, secs = encode_and_capture(args.url, filename, loader, prompt)
                m = compare(ref_flat, to_flat(b64))
                m["seconds"] = secs
                m["file"] = filename
                m["loader"] = loader
                row["arms"][name] = m
                if m.get("comparable"):
                    print(
                        f"      cos_dist={m['cosine_distance']:.6f}  "
                        f"rel_l2={m['relative_l2']:.6f}  {secs:.1f}s",
                        flush=True,
                    )
            except Exception as e:  # noqa: BLE001 -- record, never abort the sweep
                row["arms"][name] = {
                    "comparable": False,
                    "reason": str(e)[:500],
                    "file": filename,
                    "loader": loader,
                }
                print(f"      FAILED: {str(e)[:300]}", flush=True)

        results["per_prompt"].append(row)

    agg = {}
    for name, filename, loader in arms:
        vals = [
            r["arms"][name]
            for r in results["per_prompt"]
            if r["arms"].get(name, {}).get("comparable")
        ]
        if vals:
            agg[name] = {
                "n": len(vals),
                "file": filename,
                "loader": loader,
                "mean_cosine_distance": sum(v["cosine_distance"] for v in vals) / len(vals),
                "max_cosine_distance": max(v["cosine_distance"] for v in vals),
                "mean_relative_l2": sum(v["relative_l2"] for v in vals) / len(vals),
                "max_relative_l2": max(v["relative_l2"] for v in vals),
                "mean_seconds": sum(v["seconds"] for v in vals) / len(vals),
            }
        else:
            reasons = [
                r["arms"].get(name, {}).get("reason", "")
                for r in results["per_prompt"]
            ]
            agg[name] = {
                "n": 0,
                "file": filename,
                "loader": loader,
                "note": "no comparable measurements",
                "first_reason": next((x for x in reasons if x), ""),
            }
    results["aggregate"] = agg

    # The self-check is the instrument's NOISE FLOOR, not a pass/fail assertion.
    # Encoding the same prompt twice with the SAME encoder is not bit-exact on
    # this rig (GPU reduction order varies run to run). exp-008 measured that
    # floor at ~6.4e-4 cosine. Any arm at or below the floor is indistinguishable
    # from the same encoder run twice, and no claim can rest on its number.
    floors = [
        r["self_check"]
        for r in results["per_prompt"]
        if r.get("self_check", {}).get("comparable")
    ]
    floor = floor_l2 = None
    if floors:
        floor = max(abs(f["cosine_distance"]) for f in floors)
        floor_l2 = max(f["relative_l2"] for f in floors)
        results["noise_floor"] = {
            "max_abs_self_cosine_distance": floor,
            "max_self_relative_l2": floor_l2,
            "per_prompt_cosine": [f["cosine_distance"] for f in floors],
            "per_prompt_relative_l2": [f["relative_l2"] for f in floors],
            "meaning": "same encoder, same prompt, encoded twice. Any arm at or "
            "below this is indistinguishable from run-to-run noise.",
        }

    print("\n=== aggregate, vs reference ===")
    if floor is not None:
        print(
            f"instrument noise floor (same encoder twice): "
            f"{floor:.3e} cosine, {floor_l2:.6f} relative L2"
        )
    print(f"{'arm':28} {'loader':16} {'mean cos dist':>14} {'mean rel L2':>12} {'x floor':>9}")
    for name, m in sorted(agg.items(), key=lambda kv: kv[1].get("mean_cosine_distance", 9e9)):
        if m.get("n"):
            ratio = (m["mean_cosine_distance"] / floor) if floor else float("nan")
            verdict = "  <-- AT NOISE FLOOR" if floor and ratio <= 1.0 else ""
            print(
                f"{name:28} {m['loader']:16} {m['mean_cosine_distance']:>14.6f} "
                f"{m['mean_relative_l2']:>12.6f} {ratio:>9.1f}{verdict}"
            )
        else:
            print(f"{name:28} {m['loader']:16} {'--':>14} {'--':>12} {'--':>9}  {m.get('note')}")

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)

    csv_path = args.out.rsplit(".", 1)[0] + ".csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "prompt_index",
                "arm",
                "file",
                "loader",
                "cosine_distance",
                "relative_l2",
                "seconds",
                "self_check_cosine_distance",
            ],
        )
        w.writeheader()
        for p in results["per_prompt"]:
            sc = (p.get("self_check") or {}).get("cosine_distance")
            for name, m in p["arms"].items():
                if m.get("comparable"):
                    w.writerow(
                        {
                            "prompt_index": p["index"],
                            "arm": name,
                            "file": m["file"],
                            "loader": m["loader"],
                            "cosine_distance": m["cosine_distance"],
                            "relative_l2": m["relative_l2"],
                            "seconds": m["seconds"],
                            "self_check_cosine_distance": sc,
                        }
                    )
    print(f"\nwrote {args.out}")
    print(f"wrote {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
