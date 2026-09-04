# Slower, and not even the same shot

Sixth entry from the [experiment register](2026-09-02-experiments-sankey.html): `feature/h3-latent-upscale-speed-test`. Refuted on its own speed claim at N=3, and it turned up a second problem nobody was even testing for.

## The hypothesis

A Reddit post (thread ID `1vuim6f`, unlinked here because it couldn't be verified as still live) proposed a neural latent-space upscaler, [`Comfyui_Minimax_h3_latent_Upscaler`](https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler), for [MiniMax H3](https://huggingface.co/MiniMaxAI): render an initial pass at low resolution, upscale the latent directly instead of decoding to pixels and re-encoding through H3's own large VAE, then run a short refine pass at full resolution. The post claimed roughly 10 to 11 minutes down to 3 to 4 minutes on a standard, non-distilled H3 pipeline. Community replies already flagged a quality concern: the latent upscale reportedly loses detail compared to a plain VAE upscale.

The catch, stated up front in this branch's own commit (`c82011f`, 2026-08-21): production here is already a 6-step turbo-distilled pipeline, not the standard multi-step setup the Reddit numbers were measured against. The stated hypothesis was that the technique would not reproduce the claimed speedup on top of an already-distilled pipeline, because as commonly implemented it doesn't reduce the low-res pass's own step count. It runs the low-res pass at the full configured step budget, then adds a refine pass on top: strictly more compute than a single direct full-res pass at the same step budget.

## What was held constant, and what could not be

Same UNet, CLIP, VAE, turbo LoRA (strength 0.8, low-VRAM mode), turbo sampler, and chunked attention setup across both arms; same prompt, same reference images, same 5-second/24fps duration, same 6-step schedule at every stage.

Two things could not be held constant, and are disclosed rather than smoothed over. First, final output resolution differs slightly: the baseline renders at 960x544, while the test's low-res stage (chosen so the upscaler's default 2.0x scale lands near the baseline resolution) plus the upscaler's own 32-pixel alignment rounding produces 960x512, about 6% shorter. Second, and this turned out to matter more: reusing the same seed across the low-res and full-res passes does not produce "the same shot at different fidelity." The low-res stage's noise tensor has a different shape than the direct full-res pass's, so H3 generates a genuinely different composition at low-res than it does at full-res for the same nominal seed.

## The numbers, N=3 each

| Run | Condition | Seed | Wall-clock | Peak VRAM |
|---|---|---|---|---|
| 1 | baseline (direct, 6-step) | 919880931791466 | 82s | 23796 MiB |
| 2 | baseline | 919880931791466 | 84s | 24043 MiB |
| 3 | baseline | 111111 | 84s | (not captured) |
| 1 | test (low-res + upscale + 3-step refine) | 919880931791466 | 88s | (not captured) |
| 2 | test | 919880931791466 | 103s | 23444 MiB |
| 3 | test | 111111 | 139s (a concurrent job from another branch queued during this trial; contention noted, not attributed to the technique alone) | (not captured) |

Slower on every trial. Even the test arm's fastest run (88s) doesn't beat the baseline's slowest run (84s). Peak VRAM sits around 23.4 to 24 GB either way, no material difference, which matches the upscaler's own documentation that it saves time, not VRAM, and here it didn't even do that.

## Output

<video src="images/2026-09-05-h3-latent-upscale-speed-test/h3_latent_upscale_speed_test_run2.mp4" controls width="640"></video>

*Test-arm run 2 from the table above (seed 919880931791466, 103s wall-clock,
23444 MiB peak VRAM), pulled from the render container's output volume.
`ffprobe` confirms 960x512 at 24fps, 5.167s duration, matching this branch's
own held-constant setup exactly. No baseline-arm video survived in the
output volume alongside it, so this is the test arm on its own, not a
side-by-side; the framing/pose difference described below was checked
against the baseline separately at render time, not reproduced here.*

## The finding nobody was testing for

Frame comparisons at roughly 0.3 and 2.5 seconds into the clip, for the same nominal seed, showed the test pipeline's output was a materially different shot from baseline: different camera framing (a close profile shot versus a wide standing shot), different headgear, different pose. The reference-image identity was still recognizable in both, so the underlying conditioning chain wasn't broken, but "same seed means same shot, just faster or slower" does not hold across this two-stage split. Anyone considering this technique should treat the low-res stage as its own independent generation, not a preview of what the full-res pass would have produced.

## Where it actually landed

Refuted on the axis it was actually testing: not adopted for the production turbo pipeline, slower with no VRAM benefit, and less predictable in what it actually renders. The branch's own notes leave one door open rather than closing it out of spite: this might still be worth trying against the standard, non-distilled H3 path the Reddit post was actually benchmarked against, where the low-res pass could plausibly use fewer of its own steps instead of the full budget. That's a different experiment nobody has run yet, not a conclusion this one supports.
