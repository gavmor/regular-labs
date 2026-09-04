# Cut versus continuation: only one side of this comparison finished

Fourth deep dive out of the [experiment register](2026-09-02-experiments-sankey.html): `feature/h3-crewgroup-longmedia-vs-cut-comparison`. It picks up where the [30-second LongMedia render](2026-09-04-h3-30s-longmedia-native.html) left off, on a harder, more honest test subject.

## The hypothesis

That earlier LongMedia render succeeded technically, but a human review of the clip flagged a real weakness: the internal segment-continuation boundaries read as jarring hard cuts with no camera change to justify them. This branch asks whether an alternative architecture avoids that problem: render independent short takes with genuinely different camera framing, then assemble them with hard cuts via OTIO and ffmpeg concat. The prediction was that a real camera change at a cut reads as intentional editing, while LongMedia's same-angle internal seam never can.

Both arms ran against the same real production asset this time, an 11-person crew-portrait scene (not the synthetic test images earlier branches used), same seed (`919880931791466`), same MiniMax H3 checkpoint stack.

## Build: both arms submitted together, one came back

Both arms went out in the same `run-changed-workflows` build. The three independently-framed cut-based shots (wide static, medium two-shot, low static angle) all completed:

| shot | wall clock | result |
|---|---|---|
| wide, static | 102s | clean |
| medium two-shot | 70s | two near-duplicate figures where two distinct ones were intended |
| low angle | 71s | motion-blur and ghosting artifacts |

Assembled via `build_timeline.py`/`render_cut.py` (the same scripts validated in the sibling OTIO/ffmpeg mechanics spike) into a single clip: 372 of 372 frames exact, clean full decode, the same ~32ms audio decode-timestamp drift at the concat boundaries already disclosed on that sibling branch.

The LongMedia arm did not produce a video. It ran further than the previously-fixed bug (177 seconds in, past the setup stage, into the sampler's first segment) before hitting a new, distinct failure: `ValueError: only first/last keyframe anchors are supported`, raised in stock MiniMax model code and reached through a different monkeypatch chain than the one already fixed on the earlier branch. The earlier fix was confirmed still doing its job; this is a separate defect nobody had hit before, in the keyframe-anchor validation path. Per this branch's own scope, it wasn't root-caused or patched, just reported as a new blocker.

## Where it actually landed

This is not a clean head-to-head, and the write-up says so directly: only one arm produced output, so there's no seam-versus-cut visual comparison to actually make. What is real: on this exact photo, at the same seed and hardware conditions, the cut-based path finished end to end (render, then OTIO/ffmpeg assembly) while the continuation path failed before a single frame existed.

Within the cut-based arm itself, the underlying editing mechanism worked as hoped: going from a wide static shot to a visibly closer framing reads as an unambiguous cut, something a same-angle internal seam never could. But two of the three shots have independent, per-generation quality defects unrelated to the cut mechanism: the medium shot's two near-duplicate figures traced to a weak descriptor for the intended second figure, and the low-angle shot's ghosting traced to camera movement interacting badly with the fast turbo sampler. Those defects, not the cut-versus-continuation question, are what a follow-up branch (`feature/h3-crewgroup-quality-pass`) went on to fix.

Peak host RAM across the whole build (three cut renders plus one failed LongMedia attempt) hit 59.3GB, well above single-model-load peaks from earlier branches, plausibly because the build submits multiple workflows back to back with only one model-unload step at the end. Flagged, not investigated. Peak GPU VRAM across the same build was 23,707 MiB, well within the card's ceiling; the LongMedia arm's failure was a validation error in the sampler, not a resource exhaustion event.

One disclosed confound worth carrying forward: the cut-based arm's three shots reuse the same proven single-shot graph (Turbo LoRA plus two supporting attention modules) that the earlier LongMedia branch used as its own external quality reference, while the LongMedia arm here runs its own separate parameter set. So this comparison is really "LongMedia's native stack at 30 seconds" against "the proven single-shot stack at 5 seconds times three," not a clean ablation of one variable. The branch's own notes say this outright rather than presenting the asymmetry as a tidier result than it is.

## Follow-ups on record

Re-render the two defective cut-based shots and redo the comparison once LongMedia has an output to actually compare against; root-cause the new keyframe-anchor bug, which needs sign-off before touching shared render-node code again; and, if this comparison is worth generalizing, extend it to the other crew-group portraits it wasn't run against this time. None of that had happened as of this write-up.

## Grounding

Solid. Everything above comes directly from `workflows/h3_crewgroup_comparison_NOTES.md` on the branch (design doc at commit `4280965`, results recorded at `607b5eb`), including the exact prompt IDs, wall-clock times, and the traceback for the LongMedia failure. No verdict was invented past what the notes actually record: an asymmetric result, not a comparison.
