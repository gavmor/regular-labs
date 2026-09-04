# A clear win with almost no margin to spare

Seventh entry from the [experiment register](2026-09-02-experiments-sankey.html): `feature/h3-native-098mp-resolution-test`. A quality win that holds up under a real look, paired with a hardware-margin problem that applies to production today, not just to the higher-resolution variant being tested.

## The hypothesis

A well-upvoted r/StableDiffusion comment claimed MiniMax H3 was trained at 0.98 megapixels specifically, and that running at that resolution is both faster and lower-VRAM than going above 1.0 MP. Production's real render workflow runs at 0.5 MP, chosen for VRAM headroom on this rig's single shared RTX 3090 (24 GB), but never actually tested against this specific claim.

The branch's two commits (`96c2daf` then `27b3b2b`, both 2026-08-23) raised `ResolutionSelector.megapixels` from 0.5 to 0.98 on a fixed-seed production workflow, holding everything else identical: same aspect ratio, same 32-pixel rounding, same seed, same 6-step turbo setup, same reference images. Both arms went into the same Concourse build under one continuous GPU lock hold, the closest available approximation of a controlled A/B on shared hardware.

## An honest correction before the render even ran

The spike's own original brief asserted a "documented VRAM ceiling" of roughly 23,250 to 23,500 MiB to extrapolate against. That number does not actually exist anywhere in the repository as written. The branch searched every architecture decision record, every open branch's commit history, and the live VRAM ledger, and found instead: an unmerged ADR documenting a 22,528 MiB effective budget (24,576 MiB physical total, minus a roughly 2 GB reservation for other resident services), and a separate steady-state footprint figure that isn't a sampling-time peak for this specific workflow at all.

Rather than invent a number or quietly route around the gap, the branch flagged it and treated the 0.5 MP arm's own live measurement as the real baseline it needed and didn't have going in.

## The results

| | baseline (0.5 MP) | variant (0.98 MP) |
|---|---|---|
| wall-clock | 1m58s | 3m54s |
| output resolution | 960x544 (522,240 px) | 1344x768 (1,032,192 px) |
| pixel ratio vs. baseline | 1.0x | 1.976x |
| wall-clock ratio vs. baseline | 1.0x | 1.983x |

Wall-clock scaled almost exactly linearly with pixel count, not worse, consistent with the chunked attention and attention-patching already active in this workflow avoiding a quadratic memory blowup as resolution rises.

**Quality (DV1): a clear, consistent win.** Frames sampled across the full clip at five timestamps all favored the 0.98 MP arm: sharper skin, metal, and fabric texture, more legible background detail, and one prompt-specific detail (a shower of sparks from a severed cable) that rendered as a vivid, distinct particle effect at 0.98 MP versus a faint smear at 0.5 MP. No increase in temporal artifacting was observed at the higher resolution.

**VRAM (DV2): both arms landed within a few hundred megabytes of the card's physical ceiling, not just the higher-resolution one.** The baseline (current production setting) peaked at 24,047 MiB out of 24,576 MiB total, leaving about 529 MiB unaccounted for. The variant peaked at 23,631 MiB, but early in its own render window while the baseline's model weights were still resident (unload only happens once at the end of a lock hold, not between two workflows processed sequentially inside it), so the comparison between the two peaks is genuinely inconclusive at 5-second polling granularity. What isn't inconclusive: both numbers sit well above the documented 22,528 MiB effective budget, meaning that budget already understates what this exact workflow uses today, even at its current production resolution.

**Host RAM (DV3): the same thin margin.** Peak usage reached 58,176 MB out of 64,223 MB total (627 MB free) during the variant's decode phase, and 57,881 MB during the baseline's, consistent with a separate branch's earlier finding that the decode and mux step, not the sampler loop, is the RAM-heavy phase for this model family.

## Where it actually landed

The quality claim holds up: 0.98 MP is a real, visible improvement over 0.5 MP, at linear rather than punishing cost. But this was not a free win to bank. Both arms, including the resolution already running in production, peaked within a few hundred megabytes of this rig's actual ceiling on VRAM and RAM alike. At a margin that thin, this single run's own notes recommend against changing the production default on this evidence alone: an unlucky render, a concurrently active background service, or leftover state from a prior job could tip either resolution into an out-of-memory failure that this particular run happened not to hit. The repo's own lab notebook records the direct follow-up: a later resolution sweep across eight points was built specifically because this experiment's two arms sat too close to the rig's real ceiling to cleanly attribute the quality difference to resolution rather than render-to-render noise.
