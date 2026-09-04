# A sampler swap that came in slower and softer

A r/StableDiffusion comment claimed that swapping [MiniMax H3](https://huggingface.co/MiniMaxAI)'s production sampler for a manual [`er_sde` + `bong_tangent`](https://github.com/ClownsharkBatwing/RES4LYF) combination at 8 steps beats the official approach, "not even close." This branch (`feature/h3-ersde-bongtangent-sampler-test`) tested that claim on this rig's own production scene, and it didn't hold up.

<video src="images/2026-09-04-h3-ersde-bongtangent-sampler/h3-baseline-6step-rerun.mp4" controls width="480"></video>
<video src="images/2026-09-04-h3-ersde-bongtangent-sampler/h3-ersde-bongtangent-test.mp4" controls width="480"></video>

*In order: the unmodified 6-step production baseline (960x544, 5.167s, 320,495 bytes) and the er_sde+bong_tangent 8-step test arm (960x544, 5.167s, 295,603 bytes). Both files' embedded ComfyUI prompt metadata confirms the settings this write-up describes: `scheduler: simple, steps: 6` for the baseline, `sampler_name: er_sde` paired with `scheduler: bong_tangent, steps: 8` for the test arm, both against the same production Turbo LoRA.*

## The hypothesis

Production's real workflow uses a purpose-built [`MiniMaxH3TurboSampler`](https://github.com/Larryvrh/ComfyUI-MiniMax-H3-Turbo) node paired with the turbo LoRA at strength 0.8 and a `BasicScheduler` at `scheduler=simple, steps=6`. Before writing any workflow, the branch checked whether that node exposes swappable internals: it doesn't, `/object_info` shows it takes zero inputs, it's an opaque object emitting a fixed sampler. But production's graph already wires that sampler's output into a generic `SamplerCustomAdvanced` node alongside a separate scheduler node, so reproducing the Reddit recipe turned out to be a two-node swap on the existing graph: the turbo sampler node swapped for `KSamplerSelect` set to `er_sde`, and the scheduler swapped from `simple` to `bong_tangent` with steps raised 6 to 8. Everything else (LoRA, loaders, reference images, resolution, prompt, seed) stayed untouched. The hypothesis: this combination, at the same LoRA strength production already uses, produces equal-or-better full-clip quality than the 6-step baseline.

One confound was disclosed up front rather than hidden: steps change too (6 to 8), because the Reddit recipe is specifically "8 step... er_sde + bong_tangent," not a sampler swap alone. A positive result couldn't have distinguished which part helped; that isolation arm wasn't run in this pass.

## What happened

Both arms rendered clean, no crash, no OOM, via the sanctioned Concourse path.

**Test arm (er_sde + bong_tangent, 8 steps):** "Prompt executed in 135.79 seconds" per comfyui-local's own log, sampling loop itself around 80s, first step 20.6s cold-start then roughly 10.1 to 10.2s per iteration steady state.

**Baseline arm (unmodified production, 6 steps), rendered fresh in the same session** for a clean same-host comparison: "Prompt executed in 112.95 seconds," sampling loop around 69s, first step 19.3s then decreasing per-step cost as the schedule's sigma deltas shrink.

That's roughly 20% slower overall (135.79s vs. 112.95s), proportional to the step-count increase (+33%), which reads as ordinary per-step overhead rather than `er_sde` itself being slower per step, since both arms land in the same ~10s-per-step ballpark once past the shared cold-start.

**Visual read, reviewed frame by frame across the full clip:** the 6-step production baseline came back grounded, with distinct metallic highlights, visible weathering, a warm rim light, and background detail staying legible throughout. The 8-step test arm came back visibly flatter and softer across every frame: material response reads more like a smooth CG sculpt than weathered surface, background detail is muddier and lower-contrast, and the color temperature shifts cooler. This isn't the "overcooked" failure mode the Reddit source warned about; it's the other one it named ("grainy with blur"), consistent with strength 0.8 not being the right spot for this sampler pairing specifically, though the LoRA-strength sweep needed to confirm that wasn't run, since the first result didn't look promising enough to justify it.

**Peak VRAM and host RAM: honestly not captured.** Neither this branch's job nor production's `run-changed-workflows` runs any memory-polling loop during a render, confirmed by reading the job script directly. A post-hoc `nvidia-smi` snapshot taken minutes after both renders finished reflects whatever the shared box was doing by then, not either render's actual peak, so it isn't reported as a number. The only honest finding on this axis: neither arm hit a memory ceiling, but neither arm's real peak is known.

## Where it landed

Refuted. The claimed "far better, not even close" result reads the opposite way on this rig's own scene: flatter, softer, and about 20% slower than the 6-step baseline it was supposed to beat. No LoRA-strength sweep or steps-only isolation arm was run, since the first-pass result didn't clear the bar the task set for justifying either follow-up. No merge to `main` is proposed; this stands as a documented negative finding for the next person tempted by the same recipe on a MiniMax H3 setup.
