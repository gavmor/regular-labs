#!/usr/bin/env python3
"""Qwen Image 2.1 vertical panel aspect ratio manifest builder for exp-019a.

Generates manifest for the exp-019a smoke test across the 3 defect alters from
exp-019 plus 1 positive control:
  1. playbook05_paranormalist_male_scrappy (dwarfism defect in 1:1)
  2. playbook03_intellectual_male_decadent (camera zoom drift in 1:1)
  3. playbook01_hound_male_scrappy (shin crop defect in 1:1)
  4. playbook02_hull_male_decadent (positive control: clean pass in 1:1)

Across two vertical aspect ratio arms:
  - Arm 1: 3:4 aspect ratio (864x1152 canvas, 432x576 quadrants)
  - Arm 2: 2:3 aspect ratio (832x1248 canvas, 416x624 quadrants)

Usage:
    python3 build_qwen_charref_aspect_ratio_manifest.py --output /tmp/manifest_exp019a.json
"""
import argparse
import json
import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from build_charref_manifest import resolve_hair
from build_qwen_charref_manifest import get_all_entries, build_qwen_prompt, PHOTOGRAPHIC_STYLE

DEFAULT_SEED = 42

SMOKE_TEST_SLUGS = [
    "playbook05_paranormalist_male_scrappy",
    "playbook03_intellectual_male_decadent",
    "playbook01_hound_male_scrappy",
    "playbook02_hull_male_decadent",
]

ARMS = [
    {
        "arm": "arm1_3x4",
        "aspect_ratio": "3:4",
        "suffix": "_3x4",
        "width": 864,
        "height": 1152,
    },
    {
        "arm": "arm2_2x3",
        "aspect_ratio": "2:3",
        "suffix": "_2x3",
        "width": 832,
        "height": 1248,
    },
    {
        "arm": "arm3_lineup_1x4",
        "aspect_ratio": "1x4_2:3",
        "suffix": "_1x4",
        "width": 1792,
        "height": 672,
        "layout_directive": (
            "Character reference sheet, four vertical panels arranged side by side in a horizontal lineup from left to right: "
            "close-up portrait (far left), front view full body (middle left), "
            "rear view full body (middle right), side profile full body (far right)."
        ),
    },
]


def build_qwen_prompt_for_layout(entry, layout_directive=None):
    if not layout_directive:
        return build_qwen_prompt(entry)
    outfit = entry["outfit"].strip()
    hair = resolve_hair(outfit, entry["hair"]).strip()
    closeup = entry["closeup_detail"].strip()
    return (
        f"{layout_directive} Character: {outfit}, {hair}. "
        f"Portrait detail: {closeup}. {PHOTOGRAPHIC_STYLE}"
    )


def build_aspect_ratio_manifest(target_slugs=None, arms=None, seed=DEFAULT_SEED):
    if target_slugs is None:
        target_slugs = SMOKE_TEST_SLUGS
    if arms is None:
        arms = ARMS

    all_entries = get_all_entries()
    entries_by_slug = {}
    for entry in all_entries:
        target = entry.get("target_filename", "")
        slug = os.path.splitext(target)[0] if target else f"playbook_{entry['playbook_slug']}_{entry['gender']}_{entry['tone']}"
        entries_by_slug[slug] = entry

    manifest = []
    for base_slug in target_slugs:
        if base_slug not in entries_by_slug:
            raise KeyError(f"Base slug {base_slug} not found in palette entries")
        entry = entries_by_slug[base_slug]

        for arm_spec in arms:
            prompt = build_qwen_prompt_for_layout(entry, arm_spec.get("layout_directive"))
            slug = f"{base_slug}{arm_spec['suffix']}"
            manifest.append({
                "playbook_slug": entry["playbook_slug"],
                "playbook_label": entry["playbook_label"],
                "gender": entry["gender"],
                "tone": entry["tone"],
                "base_slug": base_slug,
                "slug": slug,
                "target_filename": f"{slug}.png",
                "arm": arm_spec["arm"],
                "aspect_ratio": arm_spec["aspect_ratio"],
                "width": arm_spec["width"],
                "height": arm_spec["height"],
                "seed": seed,
                "prompt": prompt,
            })

    return manifest


def main():
    parser = argparse.ArgumentParser(description="Build Qwen Image 2.1 aspect ratio manifest for exp-019a")
    parser.add_argument("--slug", help="Filter by single base slug")
    parser.add_argument("--arm", help="Filter by arm name (e.g. arm1_3x4, arm2_2x3, arm3_lineup_1x4, arm1, arm2, arm3, all)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"Seed (default: {DEFAULT_SEED})")
    parser.add_argument("--output", help="Path to write output JSON")

    args = parser.parse_args()

    slugs = [args.slug] if args.slug else SMOKE_TEST_SLUGS
    arms = ARMS
    if args.arm and args.arm != "all":
        arms = [a for a in ARMS if a["arm"] == args.arm or a["arm"].startswith(args.arm)]
        if not arms:
            raise ValueError(f"Unknown arm '{args.arm}'. Available: {[a['arm'] for a in ARMS]}")

    manifest = build_aspect_ratio_manifest(target_slugs=slugs, arms=arms, seed=args.seed)

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"Wrote {len(manifest)} manifest entries to {args.output}")
    else:
        print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
