# The half we could test, and then never did

Fourth entry from the [experiment register](2026-09-02-experiments-sankey.html): `feature/h3-noturbo-50step-quality-test`. Filed under PARTIAL INFEASIBLE, which undersells how cleanly this one splits into "physically impossible here" and "we just never got to it."

## The hypothesis

A community theory floating around r/StableDiffusion held that MiniMax H3's cloud API looks better than local renders because the cloud side runs 50 steps at full BF16 precision with no turbo acceleration, versus local's usual 6 to 25 steps on a pruned, quantized UNet with a turbo LoRA bolted on. Explicitly called a possible "secret sauce," not confirmed by anyone. Production here runs the int8-pruned UNet at 6 steps with a turbo LoRA (strength 0.8) and a dedicated turbo sampler node.

The branch's single commit (`a595026`, 2026-08-23) does something the register's other entries mostly skip: it checks feasibility before touching any hardware at all.

## Part 1: the BF16 half, ruled out from a file listing

Before downloading anything, the commit's own notes check the official `Comfy-Org/MiniMax-H3` Hugging Face listing directly. Production's int8-pruned UNet is 21 GB. The pruned BF16 variant is 40.2 GB. The full unpruned BF16 is 66.3 GB. The rig is a single RTX 3090 with 24576 MiB (24 GB) total VRAM, already carrying about 2.4 GB of idle draw from other services.

Even the pruned BF16 file alone exceeds the card's entire capacity before the text encoder, VAE, latents, or activations load at all. The full unpruned version is roughly 2.75x the card's total capacity. No multi-gigabyte weights were downloaded to confirm this further: the file-size listing was enough. The notes also rule out swapping in a BF16 text encoder (the current one is a 32B-parameter model already quantized to nvfp4 specifically so it fits; BF16 would run around 64 GB on its own), and note the VAEs are moot since production already runs those unquantized.

Verdict on this half, in the branch's own words: "hard blocker, not tight... there is no headroom trick that closes a 16-40+ GB gap on weight residency alone." The BF16-precision side of the original Reddit hypothesis cannot be tested on this hardware at all.

## Part 2: the testable half, fully designed

What's left is the step-count and turbo-acceleration half: same int8-pruned UNet, but with the turbo LoRA and turbo sampler removed, 50 steps instead of 6, `res_multistep` plus a `simple` scheduler in place of the turbo sampler.

The notes are explicit that this is one inseparable bundle, not three independently toggleable changes: the turbo sampler node is hardcoded for the LoRA's fixed low-step schedule and cannot run at 50 steps, so dropping the LoRA means dropping the sampler too. That bundling is disclosed as a confound rather than glossed over, per the branch's own experiment-design checklist (see below).

The commit lays out a full hypothesis and four dependent variables before any render: continuous-playback video quality, face/armor fidelity to the reference images, audio presence and sync, and wall-clock time plus peak VRAM/RAM as the known cost side of the trade. It holds everything else constant (prompt, seed, reference images, resolution, checkpoints) and states up front that this is an N=1 spike, not a consistency claim. Two workflow files were built: a byte-identical copy of the production baseline, and the no-turbo/50-step variant with the turbo LoRA node deleted and the sampler chain rewired.

## What actually happened: nothing

The branch's `NOTES.md` ends with a `## Results` section that reads, verbatim:

```
_(filled in after the Concourse build completes -- wall-clock, peak VRAM,
peak host RAM, and playback quality comparison against baseline)_
```

That placeholder is still there. There is no render in the history of this worktree, no follow-up commit, and no build recorded against either workflow file. The one commit on this branch is the design work itself, not a result.

## Where it actually landed

Half of the original hypothesis is dead on arrival: BF16 precision cannot run on a 24 GB card, confirmed from a file-size listing alone, no ambiguity there. The other half was designed to the letter of this repo's own experiment-design standard (ADR 0004: state the hypothesis and DVs before rendering, disclose confounds, don't claim consistency from N=1) and then simply never rendered. Nobody ran the 50-step build. The honest read is not "inconclusive" so much as "half physically impossible, and we never got around to testing the other half."
