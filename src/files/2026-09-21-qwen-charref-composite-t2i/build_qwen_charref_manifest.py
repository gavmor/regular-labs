#!/usr/bin/env python3
"""Qwen Image 2.1 T2I 44-alter charref manifest builder for exp-019.

Generates manifest for the 44 core alters (11 playbooks x 2 genders x 2 tones)
using Dunmanifestin palette entries from build_charref_manifest.py and
charref_entries_remaining41.py.

Prompt format:
  Layout: 4-panel composite (closeup portrait, front full body, rear full body, side full body)
  Subject: {outfit}, {resolved_hair}. Portrait detail: {closeup_detail}.
  Style: 1968 photographic studio portraiture (clean, no litho/halftone tokens,
         no 'Dunmanifestin' generator leak).

Usage:
    python3 build_qwen_charref_manifest.py
    python3 build_qwen_charref_manifest.py --limit 2
    python3 build_qwen_charref_manifest.py --slug playbook01_hound_male_decadent
    python3 build_qwen_charref_manifest.py --output /tmp/manifest_qwen.json
"""
import argparse
import json
import os
import sys

# Ensure projects/blades68/scripts is on path
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from build_charref_manifest import PILOT_ENTRIES, resolve_hair
from charref_entries_remaining41 import REMAINING_ENTRIES

DEFAULT_SEED = 42

LAYOUT_DIRECTIVE = (
    "Character reference sheet, four panels arranged in a single composite image: "
    "close-up portrait (top left), front view full body (top right), "
    "rear view full body (bottom left), side profile full body (bottom right)."
)

PHOTOGRAPHIC_STYLE = (
    "1968 photographic studio portraiture, crisp natural directional lighting, "
    "fine fabric and material texture, sharp focus, neutral studio backdrop."
)


def build_qwen_prompt(entry):
    outfit = entry["outfit"].strip()
    hair = resolve_hair(outfit, entry["hair"]).strip()
    closeup = entry["closeup_detail"].strip()
    return (
        f"{LAYOUT_DIRECTIVE} Character: {outfit}, {hair}. "
        f"Portrait detail: {closeup}. {PHOTOGRAPHIC_STYLE}"
    )


def get_all_entries(include_contender=False):
    all_raw = PILOT_ENTRIES + REMAINING_ENTRIES
    if not include_contender:
        return [e for e in all_raw if e.get("playbook_slug") != "contender"]
    return all_raw


def build_manifest(entries, seed=DEFAULT_SEED):
    manifest = []
    for entry in entries:
        target = entry.get("target_filename", "")
        slug = os.path.splitext(target)[0] if target else f"playbook_{entry['playbook_slug']}_{entry['gender']}_{entry['tone']}"
        prompt = build_qwen_prompt(entry)
        manifest.append({
            "playbook_slug": entry["playbook_slug"],
            "playbook_label": entry["playbook_label"],
            "gender": entry["gender"],
            "tone": entry["tone"],
            "slug": slug,
            "target_filename": f"{slug}.png",
            "seed": seed,
            "prompt": prompt,
        })
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Build Qwen Image 2.1 charref manifest")
    parser.add_argument("--slug", help="Filter by specific slug")
    parser.add_argument("--limit", type=int, help="Limit number of entries")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"Seed for generation (default: {DEFAULT_SEED})")
    parser.add_argument("--include-contender", action="store_true", help="Include Contender playbook (48 total)")
    parser.add_argument("--output", help="Path to write output JSON")

    args = parser.parse_args()

    entries = get_all_entries(include_contender=args.include_contender)

    if args.slug:
        entries = [e for e in entries if os.path.splitext(e.get("target_filename", ""))[0] == args.slug or e.get("playbook_slug") == args.slug]
        if not entries:
            print(f"Error: no entries matching slug '{args.slug}'", file=sys.stderr)
            sys.exit(1)

    if args.limit:
        entries = entries[:args.limit]

    manifest = build_manifest(entries, seed=args.seed)

    if args.output:
        out_path = args.output
    else:
        repo_root = os.path.abspath(os.path.join(script_dir, "..", "..", ".."))
        gen_dir = os.path.join(repo_root, "gen_charref")
        os.makedirs(gen_dir, exist_ok=True)
        out_path = os.path.join(gen_dir, "manifest_qwen.json")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Wrote {out_path} with {len(manifest)} entries")


if __name__ == "__main__":
    main()
