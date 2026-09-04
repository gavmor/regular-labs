# A checkpoint this rig can stage but never load

Fifth entry from the [experiment register](2026-09-02-experiments-sankey.html): `feature/h3-fun-controlnet-union-test`. One commit (`bc16f46`, 2026-08-24), zero renders, and a clean answer to a narrower question than the branch name suggests: not "is this technique good," but "can this rig run it at all."

## The question

MiniMax H3's native reference/motion conditioning treats a reference video as loose guidance and tends to drift from it: community reports describe swapping a subject in and getting back something close to the original reference video, not a faithful edit. A separately released checkpoint conditions H3 on Canny, depth, HED, MLSD, or pose control video plus inpainting, and the hypothesis was that it would hold tighter, more literal adherence to a control video than H3's native conditioning does. None of that got tested. This is a feasibility check that stopped before the first render.

## Ecosystem check: no path in, confirmed by inspection

Three things were checked directly rather than assumed from the source Reddit post:

- The ComfyUI pull request adding native support for this checkpoint was open and unmerged as of the check date, last updated the same day.
- This rig's own H3 wrapper node package has zero controlnet-mode support and zero references to "controlnet" anywhere in its source, confirmed by grepping both the installed copy and the upstream repository's current HEAD.
- A well-known community packager has staged two pruned companion checkpoints (a 4.22 GB BF16 version and a 2.30 GB int8 version) using the same quantization naming convention this pipeline's own working H3 VAE already uses, which is a real signal about which one would eventually be the drop-in fit. But no loader or wrapper node code has shipped for either yet.

Nothing ComfyUI-native or ComfyUI-adjacent can load this checkpoint today.

## The documented fallback also does not fit

The model's own card points at a separate inference toolkit and states, in its own words, that the transformer alone needs about 62 GB and the accompanying text encoder needs about another 62 GB, so the combination does not fully fit even an 80 GB GPU without offload tricks.

Measured against what's actually available here: 24 GB of VRAM on a single RTX 3090, and a host with 62 GB of total system RAM (about 11 GB free at the time of the check). That's roughly a 5x VRAM gap against the documented requirement, with no system RAM headroom to absorb an offloaded half of a combined footprint around 124 GB. The existing H3 stack on this rig only fits at all because its transformer, VAE, and text encoder are already quantized and pruned; the checkpoint's own maintainers assume a full BF16 stack and don't document a consumer-GPU path.

## What was actually done

No render, no Concourse task. What did happen: confirming no duplicate work existed on this topic already, confirming the GPU was idle before touching anything, verifying that the model storage volume was a separate mount with enough free space (so the download itself wasn't put at risk by an unrelated, nearly-full root filesystem), and downloading all three known checkpoint variants into the model directory: the canonical 6.81 GB release and the two pruned companions (4.22 GB and 2.30 GB). That's model-file placement only, no GPU work.

No Concourse render task was written for a raw-script fallback attempt. The branch's own reasoning: building pipeline infrastructure for a path that's already confirmed infeasible is wasted effort, not a hedge worth keeping.

## Where it actually landed

Deferred, and honestly so: not "might work with tuning," but a roughly 5x VRAM shortfall against the checkpoint's own documented requirements, with no ComfyUI-native loader existing yet regardless. The checkpoints are staged and ready. The branch names two concrete conditions that would make this worth revisiting: the pending ComfyUI pull request merging, or someone shipping actual loader code for the pruned int8 checkpoint that composes with this rig's existing quantized H3 stack. Until one of those happens, this is a hard no, not a maybe.
