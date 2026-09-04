# Sparse attention for H3: built, staged, never run

Item #19 on the [experiment register](2026-09-02-experiments-sankey.html):
`feature/h3-optimizations-validation`. Like the pixel-art piece, this is a
"does the claimed thing actually work here" question rather than a formal
A/B with a result in hand. It got further than the pixel-art branch (real
infrastructure work, four staged workflow variants) but stops at the same
place: no render, no verdict.

## The hypothesis

A community report (referenced in this branch's Concourse dispatch log)
claimed that [H3-Optimizations](https://github.com/Zironic/H3-Optimizations)'s
default 30% video KV budget is quality-neutral for simple, single-subject
scenes but measurably hurts prompt adherence, elements popping in and out of
existence, in complex multi-element scenes, per one commenter's own
seed-controlled A/B testing. This branch tests only that library's sparse-attention
node, not its separate memory-optimization mode, across two
scene types: a simple dual-reference scene and a five-person crew-group
scene. [MiniMax H3](https://huggingface.co/MiniMaxAI) is the video model both
variants render against.

*Output: not retrievable.* No build log, Immich album, or output file under
this branch's name turned up in the `comfyui-local` container's output
volume (searched for `sparse`, `h3opt`, and `validation` keywords) or
anywhere in the branch worktree itself. This matches the article's own
account: the render that would have produced media never ran.

## What was actually built

The single commit (`8de5190`, 2026-08-26) does real infrastructure work, not
just a workflow edit. It adds `EXPERIMENT.md` stating the hypothesis and
four dependent variables (prompt adherence, video artifacting, audio
integrity, and peak VRAM) before any render, and installs the sparse
attention node into `comfyui-local` by building its native INT8 kernel from
source rather than trusting a prebuilt binary: the upstream package's
default CMake target list covers `sm_80/89/90a/120`, none of which matches
the RTX 3090 actually in this rig (`sm_86`), so the build script was
retargeted for that architecture and for the host's Ubuntu 22.04 glibc.

Four workflow files were added: baseline and sparse-attention variants for
both the simple scene and the crew-group scene
(`h3opt_validation_simple_baseline.api.json`,
`h3opt_validation_simple_sparse.api.json`,
`h3opt_validation_crewgroup_baseline.api.json`,
`h3opt_validation_crewgroup_sparse.api.json`), each pair verified
programmatically identical except for the attention-patch node itself.

## What's still open

No second commit exists on this branch. None of the four workflows have a
recorded render result: no build log, no Immich album, no artifact under
this branch's name in this lab's output archive. The document itself is
explicit that even a completed single-shot run here would only be a
scoped Phase-1 pass (N=1 per arm), not enough for a "stable"/"consistent"
claim, and separately notes that folding this into production would still
need the crew-group workflow ported into the real production job rather
than left as a branch-local copy. None of that follow-on work is reachable
until the first render actually happens.

## Where it actually landed

No verdict. What exists is a real, working sparse-attention build targeted
correctly at this rig's actual GPU architecture, and four workflows ready
to test the specific community claim under controlled conditions. Whether
the reported quality gap between simple and complex scenes shows up here
is exactly as unknown today as it was before this branch started; the
infrastructure to answer it is staged, the render that would answer it
never ran.
