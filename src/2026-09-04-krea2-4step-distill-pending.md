# Three rendered arms, no verdict yet: the Krea2 4-step distill LoRA

Another item off the [experiment register](2026-09-02-experiments-sankey.html):
`feature/krea2-4step-chk14000-distill-test`. Unlike the LongMedia piece, this
one doesn't get a clean ending. The renders exist; the comparison that would
turn them into an answer doesn't, at least not on record yet.

## The hypothesis

Production crew-portrait renders on this rig run
[Krea2 Turbo](https://huggingface.co/krea/Krea-2-Turbo) at 8 steps. A
r/StableDiffusion-linked LoRA,
[`lvladikov/Krea2-Turbo-Distill-4step-LoRA`](https://huggingface.co/lvladikov/Krea2-Turbo-Distill-4step-LoRA),
claims a 44% reduction in prediction error against the 8-step teacher at
checkpoint `chk00014000`, measured by the author across 100 held-out prompts.
That's the author's own benchmark, not a guarantee for this project's actual
content (dense multi-figure period group portraits with halftone/grain
styling), so the branch treats it as something to test, not something to
trust.

The pinned file is `krea2_turbo_4step_rank_64_lora_chk00014000_comfyui.safetensors`,
fetched from HF repo commit `d5ebe6a71eba7b968cb54bbef8feba062c85ca08`, per
the author's own guidance to pin a numbered checkpoint rather than the
rolling `_latest` pointer. An earlier branch had already tried this LoRA
lineage at an older checkpoint (`chk00006000`) and never filled in a results
table; per instruction that branch was abandoned outright, not resumed, so
this is a fresh comparison against the current checkpoint, not a retry.

## Three arms, one caught confound

Build 1 (`aa4e099`, 2026-08-23) added the design doc and a two-arm pair:
8-step baseline vs. 4-step with the LoRA chained in at strength 1.0, holding
everything else constant (prompt text reused verbatim from a five-figure
crew-portrait manifest, seed 42, 1.5MP/3:2 resolution, cfg 1.0, euler/simple,
same base checkpoint and CLIP/VAE, the project's optional secondary LoRA off
as usual for this scene).

Build 2 (`72d7915`, 2026-08-25) was a two-day gap spent fixing a submission
bug, not a render: both workflow files had been saved with the full
`{"prompt": {...}, "client_id": ...}` POST envelope instead of the bare node
graph every other workflow file in the repo uses, so the branch pipeline's
own wrapping step double-wrapped them and `comfyui-local` rejected both as
invalid API-format JSON. Fixed by replacing each file's contents with just
its inner graph.

Build 3 (`a66171b`, 2026-08-26) caught something the first two arms hadn't
controlled for: they changed step count (8→4) *and* added the LoRA in the
same render, so any face/eye degradation seen in the 4-step arm couldn't be
attributed to either variable alone. A third arm re-renders the same scene
at 4 steps on the plain baseline checkpoint with no LoRA at all, isolating
step count from LoRA presence between the two 4-step renders.

## What's still open

All three arms are single-trial (N=1 per arm, explicitly not a repeatability
claim per this repo's own experiment-design standard). The repo's lab
notebook, written the same week, does record a finding: that the distill
LoRA, not the step cut, is the source of the observed face degradation. But
that entry also states plainly that "the actual synthesis write-up was never
produced" and that no album or file link survives in this session's visible
history, i.e. the notebook's "confirmed" is restating the register's own
categorization rather than pointing at a documented frame-by-frame compare.
No render artifacts from this branch turned up in this lab's own archive.

## Output: the renders, found late

The three renders were never lost, just never archived anywhere this lab's
own indexes look. They're still sitting in the `comfyui-local` container's
persistent output volume, under `krea2_4step_distill_test/`, filed under the
exact prefixes each arm's workflow writes
(`militants_baseline_8step`, `militants_test_4step_distill`,
`militants_isolate_4step_nolora`). All three are 1536x1024 (1.5MP, 3:2),
matching the design doc's stated resolution, and each shows the same
five-figure crew scene the design doc describes.

<img src="images/2026-09-04-krea2-4step-distill-pending/militants_baseline_8step.jpg" alt="8-step baseline, no LoRA: five figures, sharp well-defined faces and eyes" width="480">
<img src="images/2026-09-04-krea2-4step-distill-pending/militants_test_4step_distill_lora.jpg" alt="4-step with distill LoRA at strength 1.0: five figures, faces remain sharp, close to the 8-step baseline" width="480">
<img src="images/2026-09-04-krea2-4step-distill-pending/militants_isolate_4step_nolora.jpg" alt="4-step, no LoRA (isolate arm): five figures, faces and eyes visibly blurred and undefined compared to the other two arms" width="480">

*Left to right: 8-step baseline, 4-step with the distill LoRA, 4-step isolate
with no LoRA. Doing the frame-to-frame compare the design doc asked for: the
4-step+LoRA arm keeps faces and eyes close to the 8-step baseline's sharpness.
The 4-step isolate arm, step count cut with no LoRA to compensate, is the one
showing visible face and eye degradation, softened features and less-defined
eyes across all five figures.*

That's the opposite of what the lab notebook's unwritten "confirmed" claimed.
This is one reviewer's visual read of N=1 renders per arm, not the rigorous
frame-by-frame metric comparison the design doc actually asked for, so it
doesn't settle the question either. But as far as this write-up can trace it,
the visible evidence points at the step cut as the source of the degradation,
not the LoRA, which the LoRA appears to be compensating for rather than
causing.

## Where it actually landed

As of this write-up: three arms rendered, a real isolate-the-confound design,
and, as of this retrofit, a located but informal visual comparison that
contradicts the lab notebook's stated conclusion rather than backing it up.
Whether the distill LoRA degrades face and eye quality independent of the
step drop is still not answered by anything more rigorous than one reviewer's
side-by-side look at three images. What's still missing is exactly what the
design doc asked for: a full-resolution, frame-to-frame compare across the
three arms against portrait quality, wall-clock time, and peak VRAM, written
down rather than asserted, ideally at N=3 per arm rather than N=1.
