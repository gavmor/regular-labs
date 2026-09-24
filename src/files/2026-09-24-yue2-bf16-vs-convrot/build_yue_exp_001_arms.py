#!/usr/bin/env python3
"""Emit the yue-exp-001 arm graphs (ComfyUI API format) into workflows/.

Arms are derived from docs/experiments/yue-exp-001-bf16-vs-convrot-audio-quality.md,
narrowed to what the published Comfy-Org/YuE2 repo actually ships (bf16 +
int8_convrot only -- there is no int4_convrot checkpoint, so design Arm 2 has
no fixture and is not emitted; see the experiment doc's execution record).

Topology is a flattened copy of ComfyUI 0.37.0's stock
"Text to Music (YuE2)" blueprint subgraph with ABC planning OFF (abc="",
matching the blueprint's default ComfySwitchNode=false path), so nothing here
is an invented graph -- only ckpt_name and seed vary across arms.
"""
import json
import os
import sys

STYLE = (
    "folk ballad, solo acoustic steel-string guitar, dry close-miked female "
    "vocal, no reverb, slow 3/4, warm and intimate"
)
LYRICS = (
    "[verse]\n"
    "The river took the summer and it left the stones\n"
    "I counted every window in the house of bones\n"
    "[chorus]\n"
    "Carry me home, carry me home\n"
    "The light on the water is all that I own\n"
)

MAX_DURATION = 30.0
STEPS = 32
SAMPLER = "dpm_2"
SCHEDULER = "sgm_uniform"
CFG = 1.0
TEMPERATURE = 1.0
TOP_P = 0.95
TOP_K = 100
REP_PENALTY = 1.2

# (arm_name, checkpoint, seed, role)
ARMS = [
    ("arm0_bf16_seed42", "yue2_3b_bf16.safetensors", 42, "ground-truth reference"),
    ("armnull_bf16_seed42_repeat", "yue2_3b_bf16.safetensors", 42, "null baseline: repeat of arm0 at identical seed"),
    ("arm1_int8convrot_seed42", "yue2_3b_int8_convrot.safetensors", 42, "claim under test"),
    ("armseedfloor_bf16_seed43", "yue2_3b_bf16.safetensors", 43, "seed floor: arm0 model, different seed"),
]


def graph(arm, ckpt, seed):
    return {
        "15": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": ckpt},
        },
        "25": {
            "class_type": "YuE2GenerateMusic",
            "inputs": {
                "clip": ["15", 1],
                "style": STYLE,
                "lyrics": LYRICS,
                "abc": "",
                "seed": seed,
                "mode": "full",
                "max_duration": MAX_DURATION,
                "temperature": TEMPERATURE,
                "top_p": TOP_P,
                "top_k": TOP_K,
                "repetition_penalty": REP_PENALTY,
            },
        },
        "18": {
            "class_type": "ConditioningZeroOut",
            "inputs": {"conditioning": ["25", 0]},
        },
        "5": {
            "class_type": "EmptyYuE2LatentAudio",
            "inputs": {"seconds": ["25", 1], "batch_size": 1},
        },
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["15", 0],
                "positive": ["25", 0],
                "negative": ["18", 0],
                "latent_image": ["5", 0],
                "seed": seed,
                "steps": STEPS,
                "cfg": CFG,
                "sampler_name": SAMPLER,
                "scheduler": SCHEDULER,
                "denoise": 1.0,
            },
        },
        "9": {
            "class_type": "VAEDecodeAudio",
            "inputs": {"samples": ["8", 0], "vae": ["15", 2]},
        },
        "10": {
            "class_type": "SaveAudio",
            "inputs": {"audio": ["9", 0], "filename_prefix": "yue_exp_001/" + arm},
        },
    }


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "workflows"
    os.makedirs(outdir, exist_ok=True)
    for arm, ckpt, seed, role in ARMS:
        path = os.path.join(outdir, "yue_exp_001_%s.api.json" % arm)
        with open(path, "w") as fh:
            json.dump(graph(arm, ckpt, seed), fh, indent=2)
            fh.write("\n")
        print("wrote %s  (ckpt=%s seed=%d role=%s)" % (path, ckpt, seed, role))


if __name__ == "__main__":
    main()
