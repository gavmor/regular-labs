# A fully-specified H3 LoRA test that never actually rendered

Item #12 on the [experiment register](2026-09-02-experiments-sankey.html):
`feature/h3-bf16-turbo-lora-quality-test`. This one has no build-by-build
story, because there was only ever one commit and no render. That's a
legitimate ending, not a gap in the research: the branch got as far as a
fully specified, ready-to-submit comparison, and then nothing happened.

## The hypothesis

Production's H3 render pipeline uses an int8-pruned Turbo LoRA
(`minimax_h3_turbo_v4_step600_ema.safetensors`) as a deliberate speed/VRAM
optimization. Two r/StableDiffusion threads speculated that a BF16-precision
LoRA, at more steps, might close a perceived quality gap between cloud H3
renders and this rig's quantized local setup. Kijai's personal HuggingFace
repo, `Kijai/MiniMax-H3_comfy`, hosts rank-resized BF16 Turbo LoRAs; its
`ref2v` rank-20 resize (`minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors`,
307MB) pairs with production's `ref2va` checkpoint, unlike the repo's other
four `fl2v`-prefixed files. The hypothesis: swapping only that LoRA file,
with everything else held identical, will measurably change wall-clock time,
peak VRAM/RAM, or full-clip video/audio quality, against production's
existing int8-pruned LoRA.

## What was actually set up

The single commit on this branch (`3019030`, 2026-08-23) does three things:
downloads the BF16 rank-20 file into `comfyui-local`'s LoRA directory
(confirmed byte-identical to HuggingFace's reported size, 306,731,560
bytes), adds a design doc
(`docs/experiments/h3-bf16-turbo-lora-quality-test.md`) stating the
hypothesis and dependent variables before any render, and adds two workflow
files: `h3_bf16_lora_test_baseline_int8.api.json` (byte-identical to
production's real prompt-builder workflow except a renamed output prefix)
and `h3_bf16_lora_test_bf16_rank20.api.json` (identical except one node's
`lora_name` pointed at the BF16 file). Everything else, prompt text,
reference images, seed, resolution, duration, step count, LoRA strength
(0.8, left untuned for the new file), and the low-VRAM attention wrapper
settings, is held constant across both files.

The design doc is explicit that Kijai's repo is actively churned (deletes
and re-uploads on the same day as ranks get retuned), which is why a
separate, later Concourse watch job (not part of this branch) was intended
to re-run the comparison automatically whenever the file set changes.

## What's missing, and why

The doc's own "Results" section, as committed, reads only: "(To be filled
in after the Concourse `comfyui-branch` / `run-changed-workflows` build for
this branch completes both arms.)" No later commit exists on this branch.
Nothing in the commit history or the doc explains why the build was never
triggered or never completed; the branch simply stops at the design-and-stage
step. There's no crash log, no blocker note, no abandoned-in-favor-of note,
the kind of honest dead ends this register usually documents when a branch
gets refuted or blocked. This one just never got run.

## Where it actually landed

No verdict, because no render happened. What exists is a complete,
ready-to-submit A/B test: two workflow files that differ in exactly one
field, a design doc stating what would count as a result, and a real model
file already staged on the render host. Anyone picking this back up doesn't
need to redo the setup, just push the branch and let its
`run-changed-workflows` pipeline actually run both arms.
