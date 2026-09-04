# The video warp wasn't the audio mask's fault

A branch on this register set out to measure a video-quality side effect of a technique that had already merged to `main`. It found the side effect. It also found that the technique wasn't the cause of it, and that nobody had actually checked before.

<video src="images/2026-09-04-h3-audio-latent-mask-video-quality/h3-av-quality-baseline.mp4" controls width="480"></video>
<video src="images/2026-09-04-h3-audio-latent-mask-video-quality/h3-av-quality-masked.mp4" controls width="480"></video>

*Build 1's real output, in order: unmodified [MiniMax H3](https://huggingface.co/MiniMaxAI) native audio+video (1056x608, 5.167s, 517,328 bytes) and the audio-latent-masked arm (1056x608, 5.167s, 505,569 bytes). Both hold on the reference still frame through roughly the first third of the clip before cross-fading, the artifact this write-up traces to something other than the audio mask.*

## The hypothesis

An earlier, already-merged branch reproduced a r/StableDiffusion technique for putting a custom soundtrack into an H3 render: split the joint audio+video latent H3 generates, discard the audio half, encode an external WAV in its place, protect it with a full noise mask for the whole 25-step trajectory, and rejoin it with the still-denoising video latent. That branch measured exactly one thing, whether the custom audio survived (verified by [Whisper](https://github.com/openai/whisper) transcription), and shipped. There was no video-quality check anywhere in its graph, its CI job, or its commits.

Gavin's review of the actual output caught what that missed: the audio was there, but the video "fades from a still frame to a speaking face" and reads warped. This branch's hypothesis was a plausible mechanism for that: protecting the audio latent for the entire trajectory conditions the video latent's cross-attention on an audio embedding that's fully clean from step 1, out of distribution with how joint audio/video diffusion normally denoises both together in lockstep, a plausible cause of a held-frame-then-jump artifact.

## What happened

**First, a build-status mismatch had to be untangled.** `fly builds` showed this branch's CI failing all 4 recorded builds, while Gavin was watching real rendered output on the dashboard. Both were true: the shared `run-changed-workflows` polling loop gives up and marks a build failed after 5 minutes, but this rig's H3 audio+video joint generation routinely takes about 6 minutes. Builds 3 and 4 both actually finished server-side and wrote real output; the CI had simply already given up watching. This is a pre-existing gap in shared infra, not something this branch caused, and wasn't fixed here.

**The redesign added the control the original branch never had.** Two sibling workflows, same first-frame reference image, same prompt, same seed, same 25 steps: one with the audio latent spliced and protected (the shipped technique, unchanged), one with H3's own native joint audio+video generation left completely alone. A new comparison script checks both an audio verdict (`silencedetect`) and, new, a video-continuity verdict: `freezedetect` segment counts for "holds a still frame" and a scene-change hard-cut count for "then jumps."

**Build 1: both arms hit the same artifact.** `freezedetect`/scene-cut counts came back close for both (`freeze_segments=3, hard_cuts=0` for the unmodified baseline vs. `freeze_segments=2, hard_cuts=0` for the masked arm), not the clear regression the acceptance criteria were written to catch. Pulling actual frames at t=0.2s/1.5s/3.0s/4.5s from both clips explained why the counts alone don't tell the story: both clips hold dead-static on the reference still frame through about 1.5s, then cross-fade through the same double-exposure ghosting, landing on a visibly different face and costume by 4.5s, the exact symptom Gavin described, present in the unmodified baseline that never touches the audio latent at all.

## Where it landed

Refuted, but not in the direction the hypothesis expected. The warp is not a cost the audio-latent-mask technique introduces; it's a pre-existing property of this first-frame-plus-prompt combination against this H3 image-to-video node, untested against other prompts or references. That doesn't clear the technique for use either. Gavin's original constraint was about the actual video quality being acceptable, not about which node graph is to blame, and this branch's real finding is that chasing a fix in the noise mask's timing (the cross-attention-mismatch idea above) would be solving the wrong problem. The video-quality issue needs to be root-caused against plain H3 image-to-video first, on its own, before this masking technique gets revisited at all. That root-causing work is not done and isn't claimed here.
