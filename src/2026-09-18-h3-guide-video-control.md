# A guide video does not tell MiniMax H3 what to do

*Status: complete. Both of H3's video inputs tested at two seeds; three body
plans, the automaton at two seeds and the other two at one. A VACE-rendered guide containing a briefcase and a tripod
transfers neither the objects nor the action through either input. A pose
skeleton transfers the action — to a human, a machine, or a cloud of vapor
alike — and the prompt supplies the objects.*

## The question

The [pose transfer write-up](2026-09-15-h3-funcontrol-pose-transfer.html)
reported a limitation: H3 FunControl carries body position and nothing else.
Across three seeds the subject crouched and reached exactly as the control
skeleton did, and no briefcase or tripod ever appeared.

A reply disputed the framing:

> wan controlnets (fun, wace, onetoall, all the dancing scail etc) can produce
> qualified reference vid in like a minute or two. [...] It's very easy to make
> minimax do absolutely anything as intended by combining a storyboard grid
> first split onto control video for Vace then reused with minimax, decent
> prompt from LLM, a guide video rendered with Vace. prep steps take like two
> minutes, and you have the video to work with.

The claim is that the limitation belongs to the control signal, not to H3:
render an appearance-carrying guide with VACE first, feed that to H3 instead of
a stick figure, and the props come along. It is a specific, testable claim
against a published result, which makes it worth the GPU time.

## Method

One variable: the control video. Everything else is held — the prompt, 1312x736,
294 frames, strength 0.8, control window 0.0-0.6, the `int8_convrot` transformer
and the `nvfp4_awq` text encoder.

The guide is rendered with Wan2.1 VACE 1.3B as a video-to-video pass over the
original clip the pose skeleton was extracted from, so the briefcase and tripod
are present as pixels rather than as joint positions.

**The guide is verified before it is used.** A null result from a degraded guide
would prove nothing, so its frames are inspected first: a suited figure carries
a brown briefcase into frame, kneels, opens it, lifts out a tripod and extends
the legs. That is the appearance signal a skeleton discards.

![Four frames from the VACE guide: a figure carries a briefcase, kneels, opens it, and extracts a tripod](images/2026-09-18-h3-guide-video-control/guide-instrument.png)

H3 has **two** inputs that accept a video, and they are different mechanisms.
Both are tested:

- **`H3FunControlApply.control_video`** — structural. The clip is VAE-encoded,
  packed into control tokens, and injected at one transformer layer across a
  sigma window.
- **`MiniMaxH3ReferenceToVideo.ref_videos`** — semantic. The clip is
  VAE-encoded *and* subsampled to 2 fps with timestamps, then handed to the text
  encoder as a reference item. Qwen sees the video.

The second exists because the disputant's words are "qualified reference vid",
and H3's own reference-video input is `ref_videos`.

### Two instruments, two kinds of question

Whether an object is present and what posture a subject is in are discrete
readings, taken by eye from frame grids: six frames per clip at fixed indices,
identical across arms.

How much a subject moves is a continuous one, and comes from measurement — mean
absolute difference between frames one second apart, reported per clip and, for
the body-plan arms, per interval. Playback settles anything the two disagree
about.

### The null

H3 is deterministic here. The same graph at a fixed seed and control, rendered
in three separate builds on different days, produces byte-identical decoded
output (`ffmpeg -f md5` = `92203a0899aa1db59eb8726ff579b91a` each time). There
is no run-to-run noise to account for, so any difference between arms is
attributable to the control video.

The floor is therefore the **seed floor**: how much the output moves when only
the seed changes. It is measured fresh in each experiment rather than borrowed.

### The decision rule, registered before rendering

*Supported* — props or the kneel appear in both guided arms and neither skeleton
arm. *Refuted* — neither pathway transfers them. *Indeterminate* — an effect at
one seed only, or the guide's own subject replacing the prompt's, which is
leakage rather than transfer.

## Results

Same prompt, same seed, three control conditions:

![Three rows of six frames. The pose-skeleton row crouches and reaches toward the floor; both VACE-guide rows hold one upright posture](images/2026-09-18-h3-guide-video-control/three-conditions.png)

The skeleton row crouches to one knee and reaches toward the floor. Both guided
rows hold one upright posture throughout. Neither shows a briefcase or a tripod,
and neither reproduces the reach — through either input.

Mean absolute pixel difference, stride 8:

| | seed floor (skeleton) | seed floor (guided) | between control types | ratio |
|---|---|---|---|---|
| simple subject | 11.38 | 17.30 | 21.69–25.59 | 2.25x |
| complex subject | 10.82 | 17.09 | 21.84–29.00 | 2.68x |
| `ref_videos` | 11.38 | 7.16 | 25.39–25.54 | 3.57x |

The guide is not inert. In every case it moves the output further than changing
the seed does — two to three and a half times further. What it produces is a
subject *holding a posture* rather than performing an action.

Under `ref_videos` the seed floor is **7.16**, *lower* than the skeleton arms'
11.38 in the same build. A reference video makes the output more stable across
seeds, not less: it acts as a prior on what the shot looks like, not as an
instruction for what happens in it.

### The subject is not the reason

A sparse prompt might plausibly leave H3 with too little to hold onto. The
complex-subject row above uses a prompt specifying skin, hair, face, physique,
wardrobe and a named held object, drawn from a seeded palette grammar rather
than written to taste. It changes nothing: the guided arms hold the same
upright posture, and their measured motion stays low.

### What the prompt does carry

The complex subject's prompt names an object — *a mysterious reel of magnetic
tape clutched in one hand*. Under pose control, it appears:

![Three cropped frames: a woman kneels, sets down a film reel, and holds it up](images/2026-09-18-h3-guide-video-control/prop-and-pose.png)

She is doing the **skeleton's** action and holding the **prompt's** object. The
reel is carried while walking, set down during the crouch, and lifted again
afterwards.

Props come from the prompt, and this is the direct demonstration: an object
named in the text appears in frame while the body obeys a control video that
knows nothing about it.

### The subject does not have to be human

A pose skeleton describes human joints. Whether that is *why* it works is a
separate question, and every subject above is a person.

Three body plans, drawn from a seeded palette grammar, under the same skeleton:

![Three rows of six frames: a woman, an automaton, and a translucent vapor entity, each kneeling and working at floor level under the same pose skeleton](images/2026-09-18-h3-guide-video-control/body-plans.png)

The automaton walks in, kneels, works at floor level and stands, in the same
choreography as the woman. The vapor entity does the same while remaining
translucent mist throughout. Neither has human joints in the sense the skeleton
describes. Both follow it.

Each subject also stays what the prompt asked for. The machine is brass and
steel from first frame to last; the mist never solidifies. The control supplies
the choreography and takes nothing from the identity.

Temporal motion within each clip — mean absolute difference between frames one
second apart — confirms the pattern holds per body plan:

| subject | pose skeleton | VACE guide | ratio |
|---|---|---|---|
| woman | 8.83 | 3.91 | 2.26x |
| automaton | 6.93 | 4.30 | 1.61x |
| vapor entity | 4.26 | 1.20 | 3.55x |

Absolute values are not comparable across subjects — mist displaces fewer
pixels than a velvet dress whatever it does — but the within-subject ratio is.

These are clip averages, and a low average means the subject is not performing
the guide's action — not that it is frozen. The shape behind the average is not
stable across seeds: the automaton's guided arm rises from 1.32 to 2.96 across
one clip and holds flat at 1.01 to 1.28 at the next seed. Only the gap between
controls replicates.

### A pose is not an action

The automaton shows what the guide does transmit, because the two controls
split cleanly on it. Under the pose skeleton it walks on camera, kneels, works
at something on the ground, and walks off — the guide's whole action. Under the
guide itself it is kneeling in the first frame and still kneeling in the last.
It never kneels *down*.

Both hold at two seeds. What crosses is the kneel as a standing condition, with
none of the movement that produced it: the guide transfers a *pose*, and the
action does not survive the trip.

## Who was right

The dispute resolves cleanly, and not entirely in either direction.

He is right that a VACE guide is cheap to produce relative to an H3 render, and
right that the guide is a real signal — it changes the output decisively. He is
wrong that it makes H3 "do absolutely anything as intended". Through both of
H3's video inputs, a guide full of visible props produced neither the props nor
the action.

The published limitation survives, and the mechanism is now better described
than it was: **the control video contributes structure, the prompt contributes
content.** A pose skeleton is a good structural signal — good enough to move a
machine and a cloud of vapor through a human choreography. A photoreal guide is
a worse one, because its structure is buried in appearance the model does not
use.

One tempting explanation is ruled out by the second pathway. If FunControl
simply reads structure and ignores appearance, then `ref_videos` — which shows
the frames to the text encoder — ought to be where appearance gets through. It
is not. Both pathways fail the same way, so the limit is not peculiar to how
control tokens are injected.

## Cost

![Two bar charts: guide production measured at 42.5 minutes against a claimed 2 minutes; ref_videos 1.33x the per-clip cost of FunControl](images/2026-09-18-h3-guide-video-control/cost.png)

**The guide takes 42.5 minutes, not two.** 2547.9 s by ComfyUI's own execution
timestamps, excluding queue and model load, for 297 frames at 832x480, 20 steps,
VACE 1.3B fp16 on an RTX 3090. That is 21x the claimed figure. The gap is large
enough that it probably reflects a different configuration — a much lower step
count, a shorter clip, or the `rcm 1.3b` speed path also mentioned — rather than
a disagreement about the same work.

**Per clip, `ref_videos` costs 1.33x what FunControl costs** — 1447.7 s against
~1090 s. Consistent with the node's own tooltip: reference tokens ride through
every sampling step, where control tokens are injected at one layer inside a
window.

**Reference length is capped by memory, not by taste.** `adapt_canvas()` resizes
a reference *up* to a 768-short-edge canvas, so a 294-frame reference at
1312x736 adds ~87,700 tokens against the shot's own 82,000 and the sequence more
than doubles. That OOMs on a 24 GB card at 20.17 GiB allocated. A 90-frame
reference — 4 s, inside the node's stated 2-15 s range — adds ~18,100 and fits.

**Nine builds, roughly 7h15m of GPU under lock, plus ~50 minutes idle between
builds.** Three builds failed: a missing module in a task script; a guide
generated at the source clip's resolution rather than the shot's, rejected by
the node on a token-count mismatch; and the reference-length OOM above. On a
single card those failures are the schedule, not a footnote to it.

**Calendar: the reply landed 2026-09-18T04:42Z and the answer was published the
same day.** A day is what the measurement costs once the rig exists — GPU lock,
artifact egress, fixture validation, a pre-flight that refuses to deploy a graph
naming an encoder H3 cannot load. That rig took weeks and is the reason the
answer took a day.

## What this does not settle

- **Two of the recipe's components, not the recipe.** The storyboard grid split
  into a control video, the "128rbg spacing", the ExVideo/RifleX long-context
  path and an LLM-written prompt are all untested. This refutes *a VACE guide
  carries props into H3*, not his whole workflow.
- **Both inputs at once.** "Combining" is a fair reading of the comment and
  remains unrun. It is the obvious next experiment.
- **The guide depicts a different figure from the prompt's subject.** If the
  intended workflow is that the guide already resembles the target shot, that is
  a different procedure and would deserve its own test.
- **VACE 1.3B, upscaled from 832x480.** The 14B model and a natively
  full-resolution guide are both untested.
- **Three body plans, only one of them replicated.** The automaton ran at two
  seeds; the woman and the vapor entity at one. Three points, not a survey of
  what H3 will accept as a body.
- **The pose-without-action reading rests on one subject at two seeds.** The
  automaton is the only arm where a guided subject adopts a posture at all, so
  the distinction it draws is not yet known to generalise.

## Files

- [Pixel scores, simple subject](files/2026-09-18-h3-guide-video-control/h3-exp-010-pixel-scores.json)
- [Pixel scores, complex subject](files/2026-09-18-h3-guide-video-control/h3-exp-011-pixel-scores.json)
- [Pixel scores, ref_videos](files/2026-09-18-h3-guide-video-control/h3-exp-012-pixel-scores.json)
- [The scoring script](files/2026-09-18-h3-guide-video-control/score_prop_transfer.py)
- [Motion scores by body plan](files/2026-09-18-h3-guide-video-control/h3-exp-013-motion.json)
- [Per-interval motion profiles](files/2026-09-18-h3-guide-video-control/h3-exp-013-motion-profile.json)
- [The guide-render script](files/2026-09-18-h3-guide-video-control/render_vace_guide.py)

Workflows are API-format and name local checkpoints; they are a starting point,
not a drag-and-drop.
