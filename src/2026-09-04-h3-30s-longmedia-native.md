# A 30-second H3 render, blocked twice, fixed once

This is the first deep dive out of the [experiment register](2026-09-02-experiments-sankey.html). One full write-up per hypothesis-bearing item, starting with the cleanest confirmed win in it: `feature/h3-30s-longmedia-native-test`.

<video src="images/2026-09-04-h3-30s-longmedia-native/h3-30s-longmedia-native.mp4" controls width="640"></video>

*The confirmed Build 4 render: 30.000s, 864×480, h264+aac, 1.28MB. Full continuous-playback quality (seams, coherence across segment boundaries, audio degradation) is a separate visual-review question this write-up doesn't answer; watch it yourself to judge that.*

## The hypothesis

Two branches on the register tried the same goal from different angles: get a single [MiniMax H3](https://huggingface.co/MiniMaxAI) render past its usual short-clip ceiling to a coherent 30-second single-shot output. The sibling branch (`feature/h3-30s-attention-stack-test`) tried it by stacking a custom attention module (SolAttn) and Spectrum on top of the production 8-step Turbo LoRA, and refuted itself with a ~50GB host-RAM OOM, root-caused to the segmented sampler silently discarding the external attention stack rather than merging with it.

This branch's hypothesis was narrower and used only shipped components: does [`ComfyUI-MiniMax-H3-LongMedia`](https://github.com/vizart-vj/ComfyUI-MiniMax-H3-LongMedia)'s **native** segmented-continuation mode (no custom attention stack, no experimental sampler) produce the full 30 seconds without hitting the same class of failure?

## Build 1: blocked, not disproven

The first submission (`h3_longmedia_native_test_30s.api.json`, prompt `246248c6`) built LongMedia's full 4-pass plan correctly: `segment_lengths=(226, 226, 226, 226)`, matching the expected 30s-in-8s-segments math, and encoded conditioning for all four segments. Then it crashed 95 seconds in, inside the sampler, with `KeyError: 'latent'`.

The traceback (read straight off ComfyUI's own `/history` endpoint, not inferred) showed the actual cause had nothing to do with LongMedia's own code:

```
guider.inner_sample → comfy/samplers.py:process_conds → encode_model_conds
  → patched extra_conds (ComfyUI-H3-Multishot/h3_avbank_probe.py)
  → patched extra_conds (ComfyUI-ALLinONE-MinimaxH3/nodes.py)
  → stock comfy/model_base.py:2160 → KeyError: 'latent'
```

Two pre-existing custom-node packages on the box (unrelated to LongMedia) both monkeypatch `comfy.model_base.MiniMaxH3.extra_conds` globally, for every H3 model load, not conditionally on which nodes are present in a given graph. LongMedia's continuation keyframes past the first segment carry no `"latent"` key by design (they're placeholders), and stock's unfiltered `[kf["latent"] for kf in keyframes]` list comprehension has no defense against that, unlike the `refs` branch two lines below it, which already filters.

A second, cheaper build (same graph, 5 seconds, single pass, no continuation) rendered cleanly. That isolated the bug to the multi-segment continuation path specifically, not a blanket incompatibility, and confirmed the crash wasn't a fluke of the 30s graph itself.

<video src="images/2026-09-04-h3-30s-longmedia-native/h3-5s-diagnostic.mp4" controls width="480"></video>

*The 5s single-pass diagnostic that isolated the bug to the continuation path: 5.000s, 238KB.*

**Verdict at this point: blocked, not resolved either way.** The RAM/VRAM sampling built into the task brief (10s-interval `nvidia-smi`/`free -m` throughout) showed peaks nearly identical to the successful 5s diagnostic: both are just H3 checkpoint loading. The crash happened before any segment reached the sampling stage that produced the sibling branch's OOM, so this branch had, honestly, no evidence either way yet on whether LongMedia's segmentation avoids that failure mode. Fixing the actual bug meant patching a shared custom-node package used by other production workflows: flagged as a blocker per the task's own guardrail against unilateral infra escalation, not attempted without sign-off.

## The fix, once authorized

With explicit authorization to go past the original blocker, the root cause traced cleanly: [`ComfyUI-H3-Multishot`](https://github.com/jlucasmcrell/ComfyUI-H3-Multishot), [`ComfyUI-ALLinONE-MinimaxH3`](https://github.com/LeonQ8/ComfyUI-ALLinONE-MinimaxH3), and LongMedia's own `hybrid_payload_patch.py` all patch the same method for the same legitimate reason (stock's refs+keyframes collision). LongMedia's copy already detects the other two via a shared marker and stands down correctly. The bug was that all three call their captured `_orig()` unconditionally before their own merge logic runs: whichever wrapper loads outermost (confirmed via load order to be `ComfyUI-H3-Multishot`) delegates straight into unfiltered stock code first.

The fix was a single-file, minimal change: filter `kwargs["minimax_keyframes"]` down to latent-carrying entries before delegating to `_orig`, in that one outermost wrapper, the same filter stock already applies to `refs`, applied one layer higher. Applied live to `comfyui-local`'s running container, and pushed upstream to a fork ([`gavmor/ComfyUI-H3-Multishot@354d86a`](https://github.com/gavmor/ComfyUI-H3-Multishot), forked from `jlucasmcrell/ComfyUI-H3-Multishot`) rather than left as an uncommitted local patch.

One honest loose end, recorded rather than quietly fixed: the `comfyui-local` image's Dockerfile still clones upstream, not the fork. The running container has the patch applied directly, which survives a `docker restart` but not an image rebuild. That's a shared-image build-config change bigger than this one experiment's scope, so it's flagged rather than silently rolled in.

## Build 4: the confirmed re-run

Same graph, byte-identical seed/prompt/resolution/sampler settings, only a cosmetic `_meta.title` touch to make the branch-diff trigger pick the file up again. Result: `execution_success`, confirmed from ComfyUI's own history (not the driver script's status line, which, per a [known gotcha](2026-09-02-experiments-sankey.html) on this lab, lost its terminal mid-run and exited misleadingly; Concourse's own build status is what's reported here).

| stage | peak host RAM | peak GPU VRAM |
|---|---|---|
| Sampling (4-pass segmented, ~80 samples) | 41.2 GB | 23.76 GB |
| Decode/encode tail | 29.2 GB, falling to ~20.3 GB | 9.5 GB, falling to ~3.2 GB |
| Post-render idle | ~20–24.8 GB | ~2.4–2.5 GB |

The sampling-stage peak matches ordinary H3 checkpoint-loading peaks from the earlier crashed builds almost exactly. It's not segment-count-driven growth. More importantly, the decode/encode tail (the exact stage where the sibling attention-stack branch's host RAM spiked to ~50GB and OOM'd) instead showed RAM *falling* once the UNET/CLIP were freed. Output was a valid 30.000-second h264+aac file at 864×480, confirmed via `ffprobe`, 1.28MB (proportionally consistent with the 5s diagnostic's 238KB).

## Where it actually landed

**Confirmed:** the render reaches `execution_success` with valid 30-second output, and LongMedia's segmented decode does not reproduce the sibling branch's OOM class on this rig, at least for this one run (N=1, same caveat as the rest of the register). Full continuous-playback quality review (seams, coherence across segment boundaries, audio degradation) is deferred to visual review and wasn't assessed as part of this branch's own verdict.

The distinction that made this one land where the sibling branch didn't: same goal, same underlying model, but this branch used only shipped LongMedia machinery instead of a bespoke attention stack, and the actual blocker turned out to be an unrelated pre-existing bug two other packages both happened to share, not anything wrong with the segmentation approach itself.
