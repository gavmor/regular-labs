# INT8 quantization moves YuE2's output about as much as changing the seed

*Status: smoke-tested, N=1. One 30-second prompt through YuE2 3B at BF16 and at
INT8 ConvRot, against a same-model seed-change control: the quantization
changes the log-spectral distance by 13.45 dB where merely moving from seed 42
to seed 43 changes it by 12.29 dB — a ratio of 1.09×, which is not a
distinguishable quality effect at this sample size.*

## The question

Comfy-Org publishes YuE2 3B in two checkpoints: `yue2_3b_bf16` at 7.8 GB and
`yue2_3b_int8_convrot` at 4.0 GB. The ComfyUI blueprint that ships with the
model — `Text to Music (YuE2).json` — defaults to the INT8 ConvRot build, with
no note on what the smaller file costs in audio quality.

On a single 24 GB card that default matters. 3.8 GB of headroom is the
difference between a music model that coexists with a video model and one that
does not. The question is whether the cheaper checkpoint sounds worse.

The trap is that "sounds worse" has a floor nobody quotes. YuE2 is an
autoregressive sampler: change the seed and you get different music from the
same prompt. Any comparison of two checkpoints that does not measure that
ordinary seed-to-seed variation first will report a large number and call it
quantization damage.

## Method

Four arms, one prompt, one 30-second duration, one 3B model, on one RTX 3090
under GPU lock.

| Arm | Checkpoint | Seed | Role |
|---|---|---|---|
| arm0 | `yue2_3b_bf16` | 42 | ground-truth reference |
| arm1 | `yue2_3b_int8_convrot` | 42 | claim under test |
| null | `yue2_3b_bf16` | 42 | reproducibility floor — repeat of arm0 |
| seed floor | `yue2_3b_bf16` | 43 | ordinary seed variation |

Every arm holds style prompt, lyrics, duration, sampler (`dpm_2` /
`sgm_uniform`, 32 steps, cfg 1.0), and `max_duration` identical. Only the
checkpoint and the seed vary, and never both at once.

**The two controls are the design.** Comparing arm0 to arm1 alone produces a
distance with nothing to compare it against. The seed-floor arm supplies the
scale: it changes the seed while holding the model, so it measures what this
metric reads when the output differs for a reason that is *not* quantization.
The reproducibility arm re-runs arm0 unchanged, establishing what the metric
reads when nothing differs at all.

**The measure** is mean L1 distance between per-frame log-magnitude STFT
spectra, in dB, on 48 kHz mono decodes of both clips — plus waveform
correlation and RMS difference. Log-spectral L1 is the right instrument here
because two autoregressive samples of the same prompt are never
sample-aligned: waveform correlation between any two different generations is
approximately zero by construction, which the results confirm and which is why
correlation alone cannot answer this.

**The decision rule, fixed before rendering.** Let *R* = (arm0↔arm1 distance) /
(arm0↔seed-floor distance).

- *R* ≥ 2.0 — quantization damage is real and larger than seed variation.
- *R* ≤ 1.25 — the quantization difference is not distinguishable from
  ordinary seed-to-seed variation at this N.
- between — indeterminate; needs more seeds and more prompts.

## Results

| Pair | Identical | Waveform corr | Log-spec L1 (dB) | ΔRMS (dB) |
|---|---|---|---|---|
| arm0 ↔ null (same model, same seed) | **yes** | 1.0000 | **0.000** | 0.00 |
| arm0 ↔ seed floor (same model, seed 42 vs 43) | no | −0.0009 | **12.287** | 0.25 |
| arm0 ↔ arm1 (**BF16 vs INT8 ConvRot**) | no | 0.0884 | **13.445** | 0.05 |
| arm1 ↔ seed floor | no | 0.0005 | 12.960 | 0.20 |

**R = 13.445 / 12.287 = 1.09×.** That falls in the ≤ 1.25 branch: the
quantization difference is not distinguishable from ordinary seed-to-seed
variation.

All four arms render 30.00 s at an RMS within 0.25 dB of each other
(−18.96, −18.92, −18.96, −18.71 dBFS). The quantization does not shift level,
and it does not truncate or pad duration.

![Four spectrograms in a 2x2 grid, each 30 seconds of audio to 16 kHz. Top left, BF16 seed 42. Top right, the BF16 seed 42 repeat, visually indistinguishable from it. Bottom left, INT8 ConvRot seed 42: the same kind of harmonic stack and onset pattern but a different arrangement. Bottom right, BF16 seed 43, likewise different in the same way. All four show dense harmonic structure with clear note onsets and a sustained band below 16 kHz.](images/2026-09-24-yue2-bf16-vs-convrot/spectrograms.png)

The figure is the check on the numbers. All four panels carry real musical
structure — harmonic stacks, distinct onsets, a populated band below 16 kHz —
so no arm collapsed to noise or silence. The INT8 panel does not look degraded
next to the BF16 panel; it looks like a *different take*, in the same way the
seed-43 panel looks like a different take.

## What this does and does not say

The INT8 ConvRot checkpoint is not measurably worse than BF16 on this prompt.
It is different, by an amount that this instrument cannot separate from the
difference you get by nudging the seed. For a workflow that already accepts
whatever the seed gives it, the 3.8 GB is available at no detectable cost.

That is a much weaker claim than "the quantization is lossless", and the
distinction matters. A 1.09× ratio does not prove the two checkpoints are
equivalent — it proves this experiment cannot tell them apart.

## What this does not settle

- **N=1 on one prompt.** One style prompt, one lyric, one duration, one seed
  pair. A quantization artefact that appears only on dense mixes, only on
  vocals, or only past 60 seconds would not show up here.
- **The seed floor rests on a single seed pair.** Seed 42 vs 43 is one draw
  from the distribution of seed-to-seed distances, not an estimate of its
  spread. A proper floor needs several seeds per model, and the ratio would
  then be a comparison of distributions rather than of two numbers.
- **The reproducibility floor is confounded by ComfyUI's execution cache.**
  arm0 and the null arm are byte-identical graphs apart from the save node's
  filename prefix, submitted back-to-back to the same server. A bit-identical
  result is what a working cache produces *and* what a deterministic sampler
  produces, and this design cannot separate them. The arm therefore confirms
  the harness is not injecting noise between submission and file; it does not
  establish that YuE2 is deterministic. A genuine determinism check needs the
  repeat in a separate process, or the cache defeated.
- **No listening test.** Log-spectral L1 is not perceptual. Two clips at equal
  spectral distance can differ greatly in how good they sound, and artefacts
  that a human hears immediately — a warbling vocal, a smeared transient — are
  not what this metric is sensitive to.
- **Nothing about speed or memory.** Both checkpoints were rendered under the
  same lock but peak VRAM was not instrumented per arm, so the headroom claim
  rests on file size, not on measured allocation.

## Cost

- **Render:** all four 30-second arms in 62 seconds of wall clock under the
  lock — 13 s, 13 s, 13 s and 15 s respectively. That is roughly **0.45× real
  time**: a 30-second track takes about 13 seconds to generate. The full build,
  including image pull, git, packaging, metrics and Immich egress, is 1h41m,
  almost all of it spent queueing.
- **Memory:** the BF16 checkpoint is 7.8 GB on disk against the INT8 ConvRot's
  4.0 GB, on a 24 GB card. Per-arm peak allocation is not instrumented.
- **Queue:** 1h34m of the 1h41m build was spent waiting at the GPU-lock
  acquire, behind six other experiments on this lab's single 3090. Serialized,
  not blocked.
- **Calendar:** the design document predates this run; execution took about
  4h45m from the first orienting command to the verified Immich album.
- **Failed builds:** four, before the one that produced these numbers.
  Build #1 errored instantly — the Concourse worker was at its 250-container
  ceiling, cluster-wide, and every pipeline on the box was erroring. Build #2
  died after 12m at the lock acquire on a transient git failure against the
  lock repository. Build #3 passed its fixture check and then met a ComfyUI
  that had been restarted by another job's VRAM flush while it waited in the
  acquire queue. Build #4 reached the render and was rejected four times with
  `missing_node_type: Node 'YuE2GenerateMusic' not found`.

  That last one is the instructive failure. The `comfyui-local` image is pinned
  to ComfyUI v0.31.1; YuE2 support landed in `b058ec65` and was first tagged in
  **v0.36.0**. The running container had drifted to v0.37.0 at runtime, so the
  graphs validated clean against the live `/object_info` — and a restart
  mid-experiment reverted it to the pinned version and took the nodes with it.
  **Validating a graph against a live server validates runtime state, not the
  image.** The same lesson applies one level up: build #3's fixture check ran
  *outside* the GPU lock, which means it certified a shared resource's past
  state across a 12-minute queue. Both checks now run inside the lock, and the
  render polls for the checkpoints by name rather than for an HTTP 200.

## Files

Graphs are ComfyUI API format and name local checkpoints; they will not
drag-and-drop into a stock install, and they require ComfyUI ≥ v0.36.0 for the
YuE2 nodes.

- [arm0 — BF16, seed 42](files/2026-09-24-yue2-bf16-vs-convrot/yue_exp_001_arm0_bf16_seed42.api.json)
- [arm1 — INT8 ConvRot, seed 42](files/2026-09-24-yue2-bf16-vs-convrot/yue_exp_001_arm1_int8convrot_seed42.api.json)
- [null — BF16, seed 42 repeat](files/2026-09-24-yue2-bf16-vs-convrot/yue_exp_001_armnull_bf16_seed42_repeat.api.json)
- [seed floor — BF16, seed 43](files/2026-09-24-yue2-bf16-vs-convrot/yue_exp_001_armseedfloor_bf16_seed43.api.json)
- [Arm builder](files/2026-09-24-yue2-bf16-vs-convrot/build_yue_exp_001_arms.py)
- [Metrics script](files/2026-09-24-yue2-bf16-vs-convrot/yue_exp_001_metrics.py)

Pipeline, pre-registration and decision rules live in `genops-pipelines` under
`concourse/yue-exp-001-pipeline.yml` and
`docs/experiments/yue-exp-001-bf16-vs-convrot-audio-quality.md`. Rendered audio
is in the Immich album *yue-exp-001 YuE2 BF16 vs ConvRot*.
