# The half we could test, rendered, and then never reviewed

Fourth entry from the [experiment register](2026-09-02-experiments-sankey.html): `feature/h3-noturbo-50step-quality-test`. Filed under PARTIAL INFEASIBLE, which undersells how cleanly this one splits into "physically impossible here" and "rendered, but nobody wrote down what it showed."

## The hypothesis

A community theory floating around [r/StableDiffusion](https://www.reddit.com/r/StableDiffusion/) held that [MiniMax H3](https://huggingface.co/MiniMaxAI)'s cloud API looks better than local renders because the cloud side runs 50 steps at full BF16 precision with no turbo acceleration, versus local's usual 6 to 25 steps on a pruned, quantized UNet with a turbo LoRA bolted on. Explicitly called a possible "secret sauce," not confirmed by anyone. Production here runs the int8-pruned UNet at 6 steps with a turbo LoRA (strength 0.8) and a dedicated turbo sampler node.

The branch's single commit (`a595026`, 2026-08-23) does something the register's other entries mostly skip: it checks feasibility before touching any hardware at all.

## Part 1: the BF16 half, ruled out from a file listing

Before downloading anything, the commit's own notes check the official [`Comfy-Org/MiniMax-H3`](https://huggingface.co/Comfy-Org/MiniMax-H3) Hugging Face listing directly. Production's int8-pruned UNet is 21 GB. The pruned BF16 variant is 40.2 GB. The full unpruned BF16 is 66.3 GB. The rig is a single RTX 3090 with 24576 MiB (24 GB) total VRAM, already carrying about 2.4 GB of idle draw from other services.

Even the pruned BF16 file alone exceeds the card's entire capacity before the text encoder, VAE, latents, or activations load at all. The full unpruned version is roughly 2.75x the card's total capacity. No multi-gigabyte weights were downloaded to confirm this further: the file-size listing was enough. The notes also rule out swapping in a BF16 text encoder (the current one is a 32B-parameter model already quantized to nvfp4 specifically so it fits; BF16 would run around 64 GB on its own), and note the VAEs are moot since production already runs those unquantized.

Verdict on this half, in the branch's own words: "hard blocker, not tight... there is no headroom trick that closes a 16-40+ GB gap on weight residency alone." The BF16-precision side of the original Reddit hypothesis cannot be tested on this hardware at all.

## Part 2: the testable half, fully designed

What's left is the step-count and turbo-acceleration half: same int8-pruned UNet, but with the turbo LoRA and turbo sampler removed, 50 steps instead of 6, `res_multistep` plus a `simple` scheduler in place of the turbo sampler.

The notes are explicit that this is one inseparable bundle, not three independently toggleable changes: the turbo sampler node is hardcoded for the LoRA's fixed low-step schedule and cannot run at 50 steps, so dropping the LoRA means dropping the sampler too. That bundling is disclosed as a confound rather than glossed over, per the branch's own experiment-design checklist (see below).

The commit lays out a full hypothesis and four dependent variables before any render: continuous-playback video quality, face/armor fidelity to the reference images, audio presence and sync, and wall-clock time plus peak VRAM/RAM as the known cost side of the trade. It holds everything else constant (prompt, seed, reference images, resolution, checkpoints) and states up front that this is an N=1 spike, not a consistency claim. Two workflow files were built: a byte-identical copy of the production baseline, and the no-turbo/50-step variant with the turbo LoRA node deleted and the sampler chain rewired.

## What actually happened: a render exists, but the notes were never updated

The branch's `NOTES.md` ends with a `## Results` section that reads, verbatim:

```
_(filled in after the Concourse build completes -- wall-clock, peak VRAM,
peak host RAM, and playback quality comparison against baseline)_
```

That placeholder is still there, and there's no follow-up commit: the one commit on this branch (`a595026`) is the design work itself, not a result, and nothing in the worktree's git history closes the loop. But the NOTES.md itself says this was "dispatched via the `comfyui-branch` Concourse auto-trigger on this branch's push," and the render box backs that up: `comfyui-local:/opt/ComfyUI/output/video/` still has `H3_noturbo50_test_BASELINE_int8_turbo6step_00001_.mp4` and `H3_noturbo50_test_NOTURBO_res_multistep_50step_00001_.mp4`, both timestamped 2026-08-23, the same day as the commit, both 960x544 with an audio track, matching the workflow files' stated resolution and DV3 audio check. So the build did run. What never happened is someone pulling those files, watching them, and writing the comparison back into `NOTES.md`.

<video src="images/2026-09-05-h3-noturbo-50step-quality-test/baseline-int8-turbo6step.mp4" controls width="480"></video>

*Baseline arm, `H3_noturbo50_test_BASELINE_int8_turbo6step_00001_.mp4`: 960x544, 5.167s, h264+aac, the byte-for-byte production graph copy described above.*

<video src="images/2026-09-05-h3-noturbo-50step-quality-test/variant-noturbo-res_multistep-50step.mp4" controls width="480"></video>

*Variant arm, `H3_noturbo50_test_NOTURBO_res_multistep_50step_00001_.mp4`: 960x544, 5.167s, h264+aac, the no-turbo/50-step/`res_multistep` graph. This write-up did not re-derive the DV1/DV2 playback-quality and fidelity comparison the branch's own notes were supposed to record; watch both clips yourself to judge that, since no scored verdict exists anywhere for this pair.*

## Where it actually landed

Half of the original hypothesis is dead on arrival: BF16 precision cannot run on a 24 GB card, confirmed from a file-size listing alone, no ambiguity there. The other half was designed to the letter of this repo's own experiment-design standard (ADR 0004: state the hypothesis and DVs before rendering, disclose confounds, don't claim consistency from N=1), and it did render, on the same day as the design commit. What never happened is the write-up: no comparison against the four stated DVs was ever recorded, in `NOTES.md` or anywhere else in this repository. The honest read is not "half physically impossible, and we never got around to testing the other half" so much as "half physically impossible, and the other half rendered but was never reviewed or written up."
