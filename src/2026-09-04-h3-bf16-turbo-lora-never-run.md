# A fully-specified H3 LoRA test, finally analyzed: a wash on quality, a real speed surprise

Item #12 on the [experiment register](2026-09-02-experiments-sankey.html):
`feature/h3-bf16-turbo-lora-quality-test`. This one had no build-by-build
story in its own commit history, because there was only ever one commit and
its design doc's "Results" section was never filled in. That looked, from
the branch alone, like a legitimate stop at the design-and-stage step. It
wasn't quite that: real render output for both arms turned out to exist on
the shared render host, dated minutes after that single commit, matching
this branch's two workflow files exactly. Nobody came back to look at it or
write it up until now. A second commit
([`ed80c15`](https://github.com/gavmor/comfyui-workflows/commit/ed80c15))
fills in the design doc's Results section with the actual analysis below.

<video src="images/2026-09-04-h3-bf16-turbo-lora-never-run/h3-bf16lora-baseline-int8.mp4" controls width="480"></video>
<video src="images/2026-09-04-h3-bf16-turbo-lora-never-run/h3-bf16lora-rank20-bf16.mp4" controls width="480"></video>

*In order: the baseline arm (int8-pruned Turbo LoRA, 960x544, 5.167s, 1,048,111 bytes) and the BF16 rank-20 arm (960x544, 5.167s, 880,365 bytes), pulled from `comfyui-local`'s output directory. Each file's embedded ComfyUI prompt metadata was checked directly: the baseline's `lora_name` reads `minimax_h3_turbo_v4_step600_ema.safetensors`, the other reads `MiniMax-H3/minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors`, exactly the two LoRA files this branch's design doc specifies. No frame-by-frame quality comparison has been done on these; that's still not done, see below.*

## The hypothesis

Production's H3 render pipeline uses an int8-pruned Turbo LoRA
([`minimax_h3_turbo_v4_step600_ema.safetensors`](https://huggingface.co/larryvrh/MiniMax-H3-Turbo-Lora/blob/main/minimax_h3_turbo_v4_step600_ema.safetensors))
as a deliberate speed/VRAM optimization. Two r/StableDiffusion threads speculated that a BF16-precision
LoRA, at more steps, might close a perceived quality gap between cloud H3
renders and this rig's quantized local setup. Kijai's personal HuggingFace
repo, [`Kijai/MiniMax-H3_comfy`](https://huggingface.co/Kijai/MiniMax-H3_comfy), hosts rank-resized BF16 Turbo LoRAs; its
`ref2v` rank-20 resize ([`minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors`](https://huggingface.co/Kijai/MiniMax-H3_comfy/blob/main/loras/minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors),
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

## What was actually found on the render host

Both workflow files' exact `filename_prefix` values
(`H3_bf16lora_test_baseline_int8` and `H3_bf16lora_test_bf16_rank20`) showed
up in `comfyui-local`'s output directory, each with two numbered renders,
timestamped 2026-08-23 15:16-15:33 UTC, minutes after the branch's single
commit at 15:12 UTC. Pulling each file's own embedded ComfyUI prompt
metadata (the `prompt` tag baked into the container by ComfyUI itself, not
inferred from the filename) confirmed the `lora_name` on each matches this
branch's two workflow files exactly, not a coincidence of similar naming
from some other branch. Checking Concourse's own build history confirmed
the mechanism: builds
[`#52663`](https://github.com/gavmor/comfyui-workflows) and `#53032`, both
`comfyui-branch` / `run-changed-workflows` runs on 2026-08-23, both
succeeded, both submitted both workflow files. Real render, real pipeline,
no OOM, just never looked at.

## The analysis, run for real

**Wall-clock time**, read per-arm from the Concourse build logs (not total
build time, which includes container setup): baseline int8 took ~2m00s
across both builds; the BF16 rank-20 arm took ~1m24s in both. The BF16
arm was **~30% faster**, the opposite of the naive "higher precision is
slower" assumption. That's a rank effect, not a precision effect: Kijai's
rank-20 resize is a much smaller LoRA than production's existing
int8-pruned one, and fewer compute ops apparently wins out over bf16 vs.
int8 arithmetic.

**Peak VRAM / RAM**: not recoverable. These builds predate this project's
`render-stats-shared-task` instrumentation, and the render host doesn't
retain historical `nvidia-smi` samples. A genuinely open question for any
future rerun.

**Full-clip video quality**, checked via dense frame sampling across the
entire clip (not just first/last frame, specifically to catch the kind of
mid-clip coherence collapse this project has hit before): neither arm
degraded progressively. Static quality differences existed but read
inconsistently across two independent review passes: one favored the
baseline's sharpness and exposure, another favored the BF16 arm's black
levels and motion handling on a hand gesture mid-clip. Read together: a
close call, not a decisive gap either direction.

**Audio quality**, via `ffmpeg astats` over the full clip: baseline RMS
-22.31dB / peak -6.08dB vs. BF16 rank-20 RMS -22.52dB / peak -6.58dB.
Within noise; no audible or measurable difference.

## Where it actually landed

The two r/StableDiffusion threads that motivated this branch speculated a
BF16 LoRA would look better than production's int8-pruned one. It doesn't,
clearly, but it also isn't clearly worse: video quality is a wash and audio
is indistinguishable. The real, unpredicted finding is the ~30% wall-clock
speedup from the rank-20 resize itself, worth a second look on its own
terms (this run left LoRA strength at production's 0.8, tuned for the
*other* LoRA, not this one). **N=1/single-seed; not a production change
recommendation.** Peak VRAM/RAM stays an open question for whoever reruns
this with the newer instrumentation.
