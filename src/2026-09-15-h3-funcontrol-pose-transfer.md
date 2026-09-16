# Pose transfer works: the woman in the dress follows the briefcase poses

*Status: smoke-tested, positive, N=1. Nine Concourse builds, zero stranded GPU
locks. The [August feasibility check](2026-09-05-h3-fun-controlnet-union-test.html)
on this exact technique stopped before its first render — "can this rig run it
at all," answered no, blocked on a 124 GB checkpoint. That blocker cleared on
2026-09-15 when a loader shipped for Kijai's pruned variant. This is the same
experiment, unblocked and answered.*

<figure>
  <img src="images/2026-09-15-h3-funcontrol-pose-transfer/pose-transfer-compare.png" alt="Three rows of six frames: a pose skeleton control video, a render following it in which a woman in a 1960s mini dress kneels and handles a briefcase, and a no-control render in which she stands still" width="800">
  <figcaption>Top: the pose skeleton fed in. Middle: the render with pose control — she kneels, crouches, rises, exits. Bottom: identical prompt, no control — she stands still. The prompt describes only who and where; it never mentions kneeling, a briefcase, or a tripod.</figcaption>
</figure>

## Abstract

MiniMax-H3 accepts a pose-skeleton control video through a third-party
ControlNet node ([wyzborrero/ComfyUI-H3-FunControl](https://github.com/wyzborrero/ComfyUI-H3-FunControl),
published the morning of 2026-09-15) that loads Kijai's curve-form pruned
checkpoint instead of Alibaba's full-width release. The question: can it impose
a *specific* motion on a subject it has never seen — pose transfer — on a
single RTX 3090?

It can. With a prompt describing only *who and where*, and a control video
supplying *what happens*, H3 rendered a woman in a 1960s mini dress kneeling,
opening a briefcase, and assembling a tripod — an action sequence the prompt
never mentions. The matched no-control arm, same prompt and seed, produced a
woman standing still.

Two earlier experimental designs could not have established this, for opposite
reasons. The design error is the more transferable result, so both are recorded
below.

## Hypothesis

A pose skeleton extracted from arbitrary footage, fed to `H3FunControlApply`,
will impose that skeleton's action on a generation whose text prompt does not
describe the action.

**Dependent variable:** presence and timing of the action beats — kneel, ground
manipulation, rise, exit — in the rendered subject, judged against the control
skeleton.

**Falsifier:** the pose arm stands still like the no-control arm, or performs
action uncorrelated with the skeleton's timing.

Written before the arms rendered, per the repo's
[experiment design standard](https://github.com/gavmor/comfyui-workflows/blob/main/docs/adr/0004-experiment-design-standard-for-feature-branches.md).

## Methods

### Verifying the checkpoint before trusting the README

The loader accepts only the curve-form variant. Rather than trust the
documentation, the safetensors headers were read directly on the box:

| checkpoint | `adaln_proj.linear` | metadata | loader |
| :-- | :-- | :-- | :-- |
| `..._pruned_bf16` | `[96768, 8]` | `adaln_basis` | accepted |
| `..._union` (full width) | `[96768, 2688]` | — | explicitly refused |

Both had been downloaded back in August, so nothing needed fetching. The node
itself is 560 lines with zero third-party imports — only `torch` and `comfy.*`,
reusing `comfy.ldm.minimax.model.DiTBlock`. That is *why* it is small: with
curve-form weights, a control block simply is Comfy's own DiT block. It was
pinned by commit into `comfyui-local` with a `PINNED_COMMIT` file so the
container's state stays auditable.

### Building a control video from footage we own

No pose preprocessor is installed in this ComfyUI (only Canny), so the skeleton
is produced offline with MediaPipe `PoseLandmarker`, drawing an OpenPose-style
**coloured** skeleton at exactly the generation's dimensions and frame count —
the node hard-fails when control token count diverges from the video segment.

Rather than download a human-activity dataset (Kinetics, AVA, NTU RGB+D were
all considered), the source clip was *rendered by H3 itself*: a man in a
late-1960s suit walking in with a briefcase, kneeling, assembling a tripod, and
leaving. Perfect provenance, exact scale control, no licensing question, and it
sidesteps the defect that killed an earlier experiment in this line — reference
artifacts whose source material was unknowable.

### The measurement that redirected the whole experiment

Two properties of the control signal turned out to matter more than any node
parameter: how often the detector finds the figure, and how much of the frame
that figure occupies. The node's README names subject size — not strength — as
the binding constraint on control authority.

| control video | skeleton bbox | lit px | detection |
| :-- | --: | --: | --: |
| 0.40 MP, uncropped | 7.2 % | 6,050 | 100 % |
| 0.98 MP, uncropped | **7.1 %** | 12,360 | 100 % |
| 0.98 MP, autocropped | **10.6 %** | 18,833 | 100 % |

**Raising resolution alone does nothing for subject size.** Doubling the pixel
budget left the bounding box unchanged at ~7 %. That is the finding that
matters operationally: "render at a higher resolution" is not a fix for a weak
control, because the figure scales with the frame.

Cropping the source to the figure before extraction is the fix. The first
implementation stretched a tall crop into 16:9 and detection **collapsed to
52 %** — distorted limb proportions defeat the detector. Letterboxing restored
100 %. Aspect fidelity beats filling the frame.

### Three designs, only one of which can answer the question

| design | prompt | control | can it answer the hypothesis? |
| :-- | :-- | :-- | :-- |
| agreement | briefcase action | skeleton of *H3's own render of that prompt* | **No** — confounded |
| contradiction | briefcase action | turn-in-place skeleton | **No** — measures dominance |
| decomposed | *who and where only* | briefcase skeleton | **Yes** |

**Why agreement fails.** The skeleton came from H3's own render of the same
prompt and seed, so agreement between output and control was guaranteed whether
or not the ControlNet contributed anything. That build looked like a success and
proved nothing.

**Why contradiction fails.** Two mutually exclusive instructions admit no
coherent video. The design answers "which signal dominates?" — genuinely useful,
and the answer was *the prompt wins* — but the footage is uninterpretable as a
quality result. Ranking tools against each other on it is a category error. It
was ranked on it mid-session, wrongly; see Corrections.

**Why decomposed works.** The prompt was audited to contain no action or prop
vocabulary — including removing "locked off on a tripod" from the camera
boilerplate, since *tripod* is precisely the prop the pose introduces. Any
action in the output is therefore attributable to the control.

## Results

Both arms: 1312×736 (0.966 MP), 294 frames (12.25 s at 24 fps), same seed,
strength 0.8, control window 0.0–0.6. Prompt in both: a young woman with a
blonde bob in a red/white/blue colour-blocked A-line mini dress, studio,
locked-off camera. **No action described.**

| arm | control | outcome |
| :-- | :-- | :-- |
| `woman_pose` | briefcase skeleton | kneels, crouches, shifts weight, rises, exits — tracking the skeleton timepoint by timepoint |
| `woman_noctl` | none | stands, essentially one pose across all six sampled timepoints |

Identity and wardrobe held in both arms, so the pose drove the body without
disturbing appearance.

### The failure mode worth knowing about

In the contradiction design at 0.98 MP, something stranger than "control
ignored" happened: the prompt still governed the human, **but the skeleton
rendered as a physical armature standing in the frame** — a dark angular
structure with the skeleton's proportions, present from the first frame. The
conditioning had gained enough authority to enter the image without gaining
enough to steer the subject, so it was absorbed as a foreign object. That is
the signature of an under-weighted control, distinct from one doing nothing.

### Cost

| configuration | render | peak VRAM |
| :-- | --: | --: |
| no control, 0.98 MP | 919 s | — |
| pose control, 0.98 MP | 1154 s | ~20 GiB |
| native `ref_videos` v2v, 0.98 MP | 1334 s | 20.9 GiB |

The ControlNet materialises a control tensor the size of the video sequence
alongside the image tensor, roughly doubling peak activation memory. It fits in
24 GiB with about 3.6 GiB of headroom — but only on a clean card, which cost
one build to learn.

## Conclusion

Pose transfer works on this stack. The node loads, applies, costs real compute,
and imposes a specific unprompted action on a novel subject while preserving
prompt-specified identity.

The operative division of labour: **the prompt says who and where; the pose says
what happens.** Fighting them is a diagnostic, not a workflow — a lesson that
cost four builds to learn properly.

This also makes ControlNet and H3's native `ref_videos` complementary rather
than competing. `ref_videos` transfers appearance and idiom; pose control
transfers motion. They are answers to different questions, and the mid-session
claim that one is "clearly better" does not survive the decomposed design.

### Limitations

- **N=1.** One seed, one prompt, one skeleton. This experiment line has
  repeatedly produced single-render results that replication overturned.
- **The source is H3's own output.** This shows H3 reproducing motion it can
  already generate. Driving from genuinely external footage is the harder test,
  and is not done.
- **No quantitative pose-adherence metric.** The verdict is visual. Two pixel
  metrics were attempted and both failed — one used each clip's own opening
  frames as a baseline (so a structure present from frame zero registered as no
  change), the other used a brightness threshold defeated by a darker render.
  Consistent with earlier findings in this line that pixel distance measures
  magnitude, not kind.

### Next

1. Seed replicates at 43/44 — the cheapest check that the effect is real.
2. Pose extracted from genuinely external footage.
3. A control-window sweep at fixed resolution.
4. Pose control combined with a worn-cohort reference artifact — motion and
   wardrobe arriving through independent channels.

## Corrections

Claims made earlier in this same session and overturned by later evidence,
recorded rather than quietly edited away:

- **"The ControlNet tracks the skeleton beat for beat."** Confounded; the
  skeleton came from H3's own render of that prompt and seed. Retracted.
- **"Video-to-video is clearly better than ControlNet."** Asserted on
  contradiction footage where neither approach could produce sensible output.
  Unsupported.
- **An out-of-memory failure blamed on resolution.** It was not a resolution
  ceiling — the same arm had rendered alone at the same size. The preceding arm
  left 12 GiB of models resident and the VRAM flush only ran at job end. Fixed
  by flushing between arms; confirmed by the next build.
- **A process violation.** A VRAM probe was submitted directly to ComfyUI from
  a shell, without the GPU lock, rationalised as "just a probe, not an
  experiment." Interrupted and disclosed. The standing rule is that all
  generative work runs through Concourse; the fix was then verified by a
  pipeline build rather than by hand.

## Artifacts

Nine `render-and-review` builds, eight green, one partial failure (the OOM
above). Every render held the cross-pipeline GPU lock and egressed through a
pipeline `put:` — **zero stranded locks across all nine**, on infrastructure
that was stranding them seven times in fourteen hours two days earlier.

Six Immich albums, from the source clip through to the final pose-transfer
pair. Machine-readable design and provenance live alongside the fixtures in
[`EXPERIMENT.yml`](https://github.com/gavmor/comfyui-workflows/blob/feature/h3-funcontrol-pose-20260915/EXPERIMENT.yml)
on `feature/h3-funcontrol-pose-20260915`.
