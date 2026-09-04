# Getting one crew-group scene clean, and a collision along the way

Fifth deep dive out of the [experiment register](2026-09-02-experiments-sankey.html): `feature/h3-crewgroup-quality-pass`, branched directly from the [cut-versus-continuation comparison](2026-09-05-crewgroup-cut-vs-longmedia.html) at its results commit (`607b5eb`).

<video src="images/2026-09-05-crewgroup-quality-pass/crewgroup-quality-pass-final.mp4" controls width="640"></video>

*Job 30014's deliverable, `crewgroup_quality_pass.mp4` from `workflows/h3_crewgroup_quality_pass/output/` on the branch worktree: 372 of 372 frames, 15.533s, 864x480, h264+aac, matching the "372 of 372 frames exact, 15.5 seconds" claim below.*

## The hypothesis

The prior branch's deliverable was rejected on sight, described as "hideously smudgy and noisy." This branch isn't a second comparison arm; the continuation-based approach is dropped entirely since it never produced output. The only goal here is one clean cut-based scene, assembled from three independently-framed shots, at a quality bar that would actually get accepted.

## Build: root-causing the two known defects

The prior branch's two broken shots weren't random bad luck. Each got traced to a specific cause:

- The medium two-shot's identity duplication (two near-identical figures instead of the intended two distinct ones) traced to a weak text description for the second figure, too vague to compete against a much more visually distinctive figure once the frame was cropped to just the two of them. Fix: give the second figure its own strong, specific visual anchors.
- The low-angle shot's motion-blur and ghosting traced to the prompt requesting a continuous camera pan, on a graph tuned for fast, mostly-static single-sample turbo generation. Fix: drop the pan, keep the angle change but make it a fully static shot instead.

Checkpoint precision was checked and ruled out as a lever: every available reference-to-video-audio checkpoint on the render box is already quantized, and the only alternative is a more aggressive quantization, strictly worse. Not the cause.

These fixes landed at commit `c3c3393`, and a build (job 29976) went out with them. It got aborted mid-flight, not because of a defect in the fix but because of a second, independent issue: Gavin flagged, via outside research fed back into the session, a standing policy that prompts for this model should go through a structured token format rather than hand-typed prose. The shot that had already been dispatched to the render box was left to finish; the other two were pulled before submission.

## The collision

While this was in flight, a second agent instance was independently working the same branch and worktree, and committed the token-format rewrite (`bb9c094`) mid-render, aborting the in-progress build in the process. Checked directly against the render server's own job history rather than trusting either agent's self-report: the build that actually shipped (job 30014) ran with the plain-prose prompts from `c3c3393`, not the token-format rewrite, because the rewrite landed after that job's last shot had already been submitted. The token-format prompts only ever ran in a later build (30096), which was still in progress when this was checked.

Net result: the two agents' independently assembled final clips turned out to be byte-identical, both built from job 30014's output. There was no real disagreement about quality, only about which prompt format had produced it.

## Where it actually landed

Job 30014 shipped as the deliverable: 372 of 372 frames exact, 15.5 seconds, clean full decode, shot times of 90s/75s/69s for wide/closeup/angle. Dense frame sampling (every 15th frame, full clip, not just start-middle-end) showed no duplication in the medium shot and no ghosting in the angle shot. The plain-prose content fixes alone were sufficient; the token-format rewrite wasn't required to reach a clean result on this pass, though job 30096's token-format render also came out clean when checked afterward, so it isn't ruled out as a valid alternative either. It just wasn't the fix that mattered here.

This is recorded honestly as still pending sign-off. The register calls it "pending confirmation" for a reason: a clean build exists and its provenance has been verified against the render server directly, not just git timestamps, but Gavin hasn't reviewed and approved it yet.

## An open tooling gap, and a standing rule with one loose thread

The token-format detour surfaced a real infrastructure gap worth recording on its own: the tool this project uses to build correctly-structured prompts for this model is a browser app whose actual prompt-compiling logic runs entirely as client-side JavaScript. There's no command-line or API path into it, which is a real mismatch for a pipeline that's supposed to run headless. Porting that logic to a script, or adding a server-side endpoint that accepts the same JSON shape the app already saves, is flagged as a bounded follow-up, not attempted here.

The standing rule that came out of this, that prompts for this model should always go through the structured format rather than hand-typed prose, is recorded as applying beyond this one branch. But the branch's own notes flag a real tension worth keeping in view: this pass's actual evidence is that the plain-prose content fix alone was sufficient to reach a clean result, and the token-format rewrite doesn't demonstrate it fixed anything the content fix hadn't already fixed. The policy was relayed secondhand, from one agent's outside research rather than a direct instruction seen in this session, and the notes say so explicitly rather than treating it as settled on the strength of one relayed claim.

## Grounding

Solid on the mechanics, the root causes, and the collision. Solid but explicitly incomplete on the ending: `workflows/h3_crewgroup_quality_pass_NOTES.md` documents everything through job 30014/30096, and nothing past that. No sign-off commit exists to cite, because none has landed.
