# Sparse attention for H3: it rendered, then got stuck at the door

Item #19 on the [experiment register](2026-09-02-experiments-sankey.html):
`feature/h3-optimizations-validation`. As of 2026-09-04 this was "built,
staged, never run" — the custom sparse-attention node hadn't survived a
`comfyui-local` container recreation, and that gap was flagged for Gavin
rather than silently reinstalled. As of the night of 2026-09-04/05 that's no
longer true: all four staged workflows ran to completion. What's now stuck
is one step later than expected: the branch's own Concourse pipeline
instance can't archive the results to Immich.

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

## What actually happened this time

All four workflows submitted clean (`node_errors: {}` for every one), which
by itself resolves the earlier open question: the sparse-attention custom
node is present and loading in `comfyui-local` again, whatever changed
between then and now. Each rendered a real 5.17s H.264+AAC clip and passed
through labeling successfully:

<video src="images/2026-09-04-h3-sparse-attention-validation/simple-baseline.mp4" controls width="480"></video>
<video src="images/2026-09-04-h3-sparse-attention-validation/simple-sparse.mp4" controls width="480"></video>

*Simple scene, baseline (left) vs. sparse attention (right). 1344x768, both
5.17s.*

<video src="images/2026-09-04-h3-sparse-attention-validation/crewgroup-baseline.mp4" controls width="480"></video>
<video src="images/2026-09-04-h3-sparse-attention-validation/crewgroup-sparse.mp4" controls width="480"></video>

*Crew-group scene, baseline (left) vs. sparse attention (right). 864x480,
both 5.17s.*

All four were pulled directly from `comfyui-local`'s persistent output
volume (`/opt/ComfyUI/output/labeled/`), not from the pipeline's own
archival path, because that path is exactly what failed. The `run-changed-workflows`
build (`2603135`, errored, 14m49s) got through submission, render, and
labeling for all four workflows, then hit `put: local-immich-gallery`:

```
undefined vars: immich_api_key, immich_url
undefined vars: immich_api_key, immich_url
undefined vars: immich_api_key, immich_url
undefined vars: immich_api_key, immich_url
4 errors occurred
```

One failure per workflow's album-upload `put`, all the same cause. This is
isolated to this one branch instance: roughly fifty other `comfyui-branch`
pipelines ran in the same batch that night and none hit this. The base
`blades68` pipeline's `set-branch-pipelines` job (build 118) had already
succeeded just minutes earlier, re-injecting `immich_url`/`immich_api_key`
into every branch instance's `set_pipeline` call the way it's supposed to
per the fix already merged into `main`. Why this one branch's instance
still ended up with unresolved vars at `put` time, when its own pipeline
config should have had them baked in at `set_pipeline` time, isn't
something this write-up resolves — that's a pipeline-infrastructure
question, not a render-quality one, and per the same policy that held the
custom-node gap open for Gavin rather than patching it silently, it's
flagged here rather than fixed by editing `branch-pipeline-template.yml`
directly.

One more loose end, unrelated to the vars bug: the rendered filenames
(`H3_promptbuilder_music_na_*`, `H3_qualitypass_crewgroup_shot01_wide_*`)
don't match this experiment's own naming (`h3opt_validation_*`) — the
album routing picked up the right names from the workflow JSON's own
basename, but the `SaveVideo`/filename-prefix node inside each workflow
file still carries whatever name it was copied from. Cosmetic, doesn't
affect the render itself, but worth fixing before this becomes the crew-group
production workflow.

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

No second commit exists on this branch, and no formal frame-to-frame
comparison has been written up yet: this write-up only confirms the render
completed and embeds the raw output for future analysis, it doesn't itself
adjudicate the community's quality claim. Doing that would mean actually
comparing the baseline/sparse pairs frame-by-frame for the popping-artifact
the report describes, which hasn't happened. Separately, the pipeline vars
bug above blocks this from being reproducible on this branch through the
normal archival path until someone with pipeline-config access looks at it;
until then, re-running this build will keep producing real video that
never reaches Immich.

## Where it actually landed

**Rendered, unverified, and stuck at archival.** The infrastructure
question from 2026-09-04 (does the sparse-attention node still build and
load on this rig) is answered: yes. The quality question the branch was
built to test is still open — the video exists now, embedded above, but
hasn't been analyzed frame-by-frame against the community's claim. And a
new, narrower problem replaced the old one: this branch's own Concourse
pipeline instance can't complete a normal archival run, which is a
different kind of blocker than "never ran."
