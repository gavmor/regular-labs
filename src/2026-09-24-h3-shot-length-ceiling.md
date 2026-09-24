# H3's shot length has a hard ceiling on a 24 GB card

*Status: negative result. Six arms at 832x480x294 produce no renders. MiniMax
H3 segfaults inside its allocator before the first sampling step, deterministic
across ten attempts, and the frame count is the only variable that separates it
from a working render.*

## The question

Experiment 022 decouples four components of a recipe posted to Reddit — a
storyboard keyframe grid, 128 RGB neutral delimiter spacing, the Wan
ExVideo/RifleX long-context path, and LLM prompt isolation — into six arms
across two seeds, so each component's contribution can be read on its own
rather than as one bundled claim.

The design specifies a 294-frame shot at 832x480. 294 satisfies H3's `17n + 5`
frame constraint (n = 17), so it is a legal shot length for the architecture.

It is not a legal shot length for the hardware.

## What happens

Every attempt to render an arm kills the ComfyUI process. The fault is a
segmentation fault, not a Python exception, so nothing is caught and nothing is
logged as an error — the container simply exits and restarts, taking its queue
and its history with it.

The stack is identical on all ten occurrences:

```
Fatal Python error: Segmentation fault

Stack (most recent call first):
  File "comfy_aimdo/malloc_graph.py", line 14 in _call
  File "comfy_aimdo/malloc_graph.py", line 25 in pop
  File "/opt/ComfyUI/comfy/model_prefetch.py", line 88 in malloc_graph_end
  File "/opt/ComfyUI/comfy/ldm/minimax/model.py", line 587 in forward
  ...
  File "/opt/ComfyUI/comfy/samplers.py", line 620 in sampling_function
```

The crash is in the allocator's prefetch bookkeeping, reached from MiniMax H3's
own `forward`. It is not an out-of-memory error. PyTorch raises a clean
`torch.OutOfMemoryError` when an allocation cannot be served; this path never
gets that far, because `comfy_aimdo` walks a malloc graph that the failed
allocation has already invalidated.

Ten segfaults, one stack, no successful frames.

## Why the frame count is the variable

The hypothesis that this is a VRAM ceiling rather than a graph defect rests on
three independent observations.

**H3 already runs at the wall.** The resolution array sweep of 2026-09-06
measured peak VRAM across eight resolutions from 0.3 to 0.98 megapixels, every
arm a 124-frame shot:

| megapixels | peak VRAM | headroom on a 24,576 MiB card |
| --- | --- | --- |
| 0.3 | 23,878 MiB | 698 MiB |
| 0.4 | 23,016 MiB | 1,560 MiB |
| 0.5 | 23,848 MiB | 728 MiB |
| 0.6 | 23,496 MiB | 1,080 MiB |
| 0.7 | 23,816 MiB | 760 MiB |
| 0.8 | 23,080 MiB | 1,496 MiB |
| 0.9 | 23,880 MiB | 696 MiB |
| 0.98 | 23,080 MiB | 1,496 MiB |

Peak VRAM stays inside a 23,016–23,880 MiB band with no trend against
resolution at all — the peak is dominated by model-weight residency and the
decode/mux phase once chunked attention is active, not by pixel count. A
124-frame shot has under 1.6 GiB of headroom at its most generous.

**A working render differs only in length.** Experiment 020 renders the same
node graph — `MiniMaxH3ReferenceToVideo`, `MiniMaxH3TurboLoRA`,
`MiniMaxH3TurboSampler` — at 832x480x124 and succeeds, on this card, on the
same day. The resolution is identical to 022's. The frame count is not.

**The observed allocation matches.** During the crashing render the card
reports 23,858 MiB in use, at the top of the measured band, and the process
dies rather than returning. A shot 2.4x longer than the one with 700 MiB of
headroom does not fit, and the allocator's failure mode under that condition is
a segfault rather than a diagnostic.

Resolution is not the lever here, and neither is the graph: 294 frames is
simply past the point where H3's activations still fit alongside its weights.

This is a different failure from the 30-second render of 2026-09-04, which
exhausted *host* RAM and brought the kernel OOM-killer down on unrelated
processes. Nothing of the sort happens here: the kernel logs no OOM-kill for
this window, and the host holds 43 GiB available throughout. The exhaustion is
on the card, and the casualty is the ComfyUI process alone.

## What this costs the experiment

Nothing in experiment 022's design is tested by this run. The four decoupled
components — stepped keyframe guidance, 128 RGB spacing, the retimed ExVideo
guide, prompt isolation — each require a rendered arm to compare, and no arm
renders. The pipeline's supporting stages all work: preflight passes, both Wan
2.1 guides render, and all six fixtures build and install. The experiment stops
at the H3 sampler.

This is a hardware-capability finding, not a result about the recipe. The
recipe's claims remain untested.

## The pipeline stages that do work

The run exercises everything up to the sampler, and those stages are sound:

- **Preflight** validates all twelve arm graphs against the live ComfyUI,
  confirms the arms are genuinely distinct, and checks model checksums against
  pinned values.
- **Fixture construction** builds four CPU fixtures with ffmpeg — a continuous
  pose baseline, a stepped storyboard, a 128 RGB delimited storyboard, and the
  gray delimiter plate — at exactly 294 frames each.
- **Guide rendering** produces two Wan 2.1 guides on the GPU: a 241-frame
  ExVideo/RifleX long-context render, retimed from 12 fps to 24 fps, and a
  297-frame stepped VACE guide.

![Eight video frames in two rows of four. Both rows show the same shot: a man
in a dark suit kneels on a grey studio floor, opens a briefcase, and assembles
a camera on a tripod. The top row is the 241-frame ExVideo/RifleX guide at 12
fps; the bottom row is the 297-frame stepped VACE guide at 24 fps. The first
frame of each row is a dim green-grey smear before the subject resolves. By the
fourth frame the top row still holds the man beside the tripod while the bottom
row has left only the tripod standing in an empty
room.](images/2026-09-24-h3-shot-length-ceiling/guides.png)

Both guides are real output from this run, sampled at four points across each
clip. They are the input H3 never consumes.

All six fixtures install into ComfyUI and survive for reuse, so a rerun at a
viable shot length skips 80 minutes of guide rendering.

## Method

Six arms, two seeds (43, 44), twelve renders, 832x480x294, 6 steps
euler/simple, on one RTX 3090 (24,576 MiB) serialized behind a `gpu-lock`
mutex in Concourse.

Arm 0 is the continuous-pose baseline. Arms 1 through 4 each change exactly one
component against that baseline: stepped storyboard guidance, 128 RGB
delimiter spacing, the retimed Wan ExVideo guide, and LLM prompt isolation. Arm
5 combines all four, so the bundled recipe can be read against the sum of its
parts.

Arm graphs are generated programmatically rather than edited by hand, which is
what lets `check_arms_distinct` assert that arms differ *only* in the tested
parameter. Model checksums are pinned in graph metadata.

The source clips are committed to the repository. ComfyUI's `input/` directory
lives inside the container image, so anything staged there is lost on redeploy;
reading sources from git makes fixture construction independent of container
lifetime.

## Reproducing

```
fly -t lab set-pipeline -p h3-exp-022-recipe \
  -c concourse/h3-exp-022-pipeline.yml
fly -t lab trigger-job -j h3-exp-022-recipe/render-and-review -w
```

Branch `feature/h3-exp-022-untested-recipe-components` in
`gavmor/comfyui-workflows`.

Builds on target `lab`, pipeline `h3-exp-022-recipe`, job `render-and-review`:

| build | outcome | what it establishes |
| --- | --- | --- |
| [31](https://tower-1.tail4e3622.ts.net:8443/teams/main/pipelines/h3-exp-022-recipe/jobs/render-and-review/builds/31) | failed | both Wan guides render; all six fixtures install |
| [32](https://tower-1.tail4e3622.ts.net:8443/teams/main/pipelines/h3-exp-022-recipe/jobs/render-and-review/builds/32) | aborted | guides reused; first arm submitted; ComfyUI dies |
| [33](https://tower-1.tail4e3622.ts.net:8443/teams/main/pipelines/h3-exp-022-recipe/jobs/render-and-review/builds/33) | aborted | five resubmissions of one arm, five segfaults |

No build produces an arm render, so no assets are egressed and no album is
created.

## What comes next

The shot length is the thing to change, and it is a design decision rather than
a fix: 209 frames is the next `17n + 5` step down, and 124 is the length known
to render on this card. Both are shorter than the 294 the design specifies, and
shortening the shot changes what the ExVideo arm is testing — the whole point
of that component is long-context behaviour, so a 124-frame version of it tests
something narrower than the claim.

The arm builder now takes `--length` and `--arms`, so regenerating at a
different shot length is one flag. The fixtures are still named and built for
294 frames and would need the same treatment.
