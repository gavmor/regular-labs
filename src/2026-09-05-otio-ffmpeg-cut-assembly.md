# OTIO plus ffmpeg concat: frame-exact video, a known audio catch

Sixth deep dive out of the [experiment register](2026-09-02-experiments-sankey.html): `feature/otio-ffmpeg-cut-based-editing-test`, the tooling spike that both the [cut-versus-continuation comparison](2026-09-05-crewgroup-cut-vs-longmedia.html) and the [quality pass](2026-09-05-crewgroup-quality-pass.html) went on to build directly on top of.

## The hypothesis

This one is narrower than the render experiments around it: not a comparative generative test, a mechanics validation. Cut-based editing had been proposed as an alternative to single long continuous takes, on the reasoning that a continuation-based render is architecturally fragile (the sibling LongMedia branch had already hit a real host-RAM risk from that class of approach). The claim under test: can a small Python script drive real OpenTimelineIO (OTIO) objects and a real `ffmpeg concat` invocation to produce a frame-accurate hard-cut assembly, with no manual timestamp math and no re-encoding?

## What was built

Two scripts under `workflows/otio_cut_test/`. `build_timeline.py` opens each input clip with PyAV, reads the real stream frame count and frame rate (not the container's float duration field), and builds an OTIO `Timeline` to `Stack` to `Track` to one whole-clip `Clip` per shot. `render_cut.py` reads that file back, walks the clips in track order, writes an ffmpeg concat-demuxer manifest, and shells out to `ffmpeg -f concat -safe 0 -c copy`.

No new GPU render was needed for this pass. Three already-rendered clips from sibling branches were reused as three independent "shots": a 5-second control clip, a 5-second diagnostic clip, and the 30-second continuation render, all h264/864x480/24fps/AAC by coincidence of sharing the same pipeline, not by any codec-compatibility check the scripts themselves enforce.

## Results

Video: exact. `ffprobe -count_frames` on the assembled output reports 964 frames, precisely 124 + 120 + 720, matching the OTIO timeline's own computed total to the frame. Full decode (`ffmpeg -f null -`) came back clean, no corruption.

Container-level duration: off by about 32 milliseconds, 40.199s reported against an expected 40.166667s. Traced to the audio stream specifically, video timestamps stayed clean. ffmpeg logged `Non-monotonic DTS in output stream 0:1` at each of the two concat boundaries. That's less than one frame at 24fps (1/24 is about 0.0417s), so it passed the task's own success bar, but it's a real, disclosed artifact, not swept under the rug.

Two version-specific surprises showed up only from actually running the code rather than trusting a description of the approach: `opentimelineio` 0.18.1's `Timeline` wants a list of tracks, not a pre-built `Stack` object, and the working call to enumerate clips on a track is `Track.find_clips()`, not `each_clip()`. Neither is exotic, but neither would show up without hands on the actual library.

## The audio catch, and the fix nobody applied yet

A follow-up research pass (fed the two open questions back into external research, results recorded on the branch at commit `310beef`) came back with a concrete mechanism for the DTS drift: AAC encoders inject roughly 1024 samples of encoder-delay silence before the first true sample, and ffmpeg's concat demuxer retains that padding per input clip, so it accumulates at every cut. That matches the roughly 32ms measured here across two boundaries almost exactly.

The recommended fix is to have each shot's render pipeline emit uncompressed PCM audio and encode to AAC exactly once, in the final assembly pass, rather than once per shot. That would eliminate the per-clip priming delay entirely. It's a change to the render pipeline's save step, not to `build_timeline.py` or `render_cut.py`, and it was explicitly left as a follow-up rather than implemented in this branch. Two cheaper alternatives were also named and explicitly not pursued: forcing every clip's duration to a strict multiple of the AAC frame duration, or trimming padding directly in the concat manifest.

That same follow-up pass also sketched how to detect an awkward same-angle cut programmatically, since OTIO clips can carry arbitrary metadata: tag each clip with the camera angle it was rendered at, then flag any cut between two clips carrying the same tag. Not implemented here, on the honest grounds that none of this spike's three reused test clips had a real per-shot camera intent worth tagging; a fabricated tag would validate the code path without validating the judgment call.

Environment notes worth keeping for anyone repeating this: neither OpenTimelineIO nor PyAV was preinstalled, and the system Python is externally managed, so both went into a project-local virtual environment instead of a user-wide pip install. The PyPI package name for PyAV is the lowercase `av`, not `PyAV`, which 404s if typed literally. ffmpeg and ffprobe were already present system-wide and needed no install.

## Where it actually landed

Succeeded on its own terms: the core three-layer shape (render independently, OTIO holds the metadata, ffmpeg assembles) worked exactly as intended, and every surprise encountered was implementation-detail friction, not an architecture-level problem. This work then got folded directly into the crew-group comparison branch, which reused these same two scripts unmodified. The audio drift is real, understood, and still unfixed.

## Grounding

Solid. `workflows/otio_cut_test_NOTES.md` documents the exact frame counts, the exact ffmpeg warning text, the exact library versions, and the exact recommended fix, none of it inferred.
