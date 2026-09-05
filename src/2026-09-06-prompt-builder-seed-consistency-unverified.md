# We wrote down what we'd test, and now there's a real results commit

This is the second write-up out of the [experiment register](2026-09-02-experiments-sankey.html): `feature/h3-prompt-builder-seed-consistency-test` had a clean, well-formed hypothesis on record and, until now, no results ever committed anywhere. A second commit
([`fdbefb0`](https://github.com/gavmor/comfyui-workflows/commit/fdbefb0))
adds a `RESULTS.md` with the silencedetect table below.

## What came before it

An earlier branch, `feature/h3-prompt-builder-consistency-test` (no "seed" in the name), vendored the [MiniMax prompt-builder tool](https://github.com/GrungeWerX/minimax-prompt-builder) and tried three different prompt variants once each: one with realistic music cues, one with no audio cues, and one built around a prompt-builder setting that suppresses certain narrative discipline cues to keep a scene deliberately silent. It merged into main on 2026-08-20, approved after Gavin reviewed the render output.

The name promised a consistency test. It didn't run one. Three different prompts, each rendered exactly once, tells you whether a prompt variant produces silence, not whether that result holds up across repeated attempts. One data point per condition is not a distribution.

## The redesign

Gavin caught this on review and a follow-up branch, `feature/h3-prompt-builder-seed-consistency-test`, redesigned the test properly. Its single commit (`acd9b25`, 2026-08-21) states an actual hypothesis and dependent variable: take the already-validated silent-scene prompt configuration and rerun it three times, varying only `RandomNoise`'s seed, to check whether the discipline-suppressing setting reliably keeps the scene silent regardless of which seed lands, rather than being a fluke of the one seed already tested.

The commit is thorough. It defines three sibling workflow files (`h3_promptbuilder_consistency_run1/2/3.api.json`), each byte-identical except for `noise_seed` (`919880931791466`, `481027336619204`, `702255819944871`) and a distinct `filename_prefix` so all three outputs land side by side instead of overwriting each other. It adds `scripts/compare-consistency-run.sh`, a host-side script meant to fetch all three rendered clips from `comfyui-local` and print a per-run `ffmpeg silencedetect` verdict table, so a human could read one table instead of eyeballing three separately-downloaded videos by ear.

## What's missing

That's where the trail stops. `git log main..feature/h3-prompt-builder-seed-consistency-test` shows exactly one commit: the redesign itself. There is no second commit recording that the three runs happened, no `silencedetect` table committed anywhere, and the branch itself was never merged to main. `docs/lab-notebook.md` on main has no entry mentioning this test by name.

It's possible the three renders happened and `compare-consistency-run.sh` was run by hand, off the record, the way the script's own comments describe (a manual step, not a Concourse task, because task containers can't reach `comfyui-local`'s output volume). It's equally possible nothing past the workflow-file setup ever ran. Both are consistent with what's actually in the repo, which is nothing beyond the setup.

## What checking the render host itself turns up

`comfyui-local`'s live output volume, which is not part of the git repo and wasn't checked by the original branch work, held the answer. `docker exec comfyui-local find /opt/ComfyUI/output -iname '*consistency*'` turns up real render output: two or three takes each of `H3_promptbuilder_consistency_run1`, `run2`, and `run3`, all timestamped 2026-08-21, the same day as the redesign commit `acd9b25`. Concourse's own build history confirms the mechanism: builds `#7295` and `#7936`, both `comfyui-branch` / `run-changed-workflows`, both succeeded. The renders happened, for real, through the normal pipeline.

Pulling the latest labeled take of each run directly via `comfyui-local`'s read-only `/view` endpoint (a GET against existing output, not a `/prompt` dispatch) and running `ffmpeg -af silencedetect=n=-30dB:d=0.5` against each confirms the hypothesis the branch set out to test: all three report silence across the full clip duration (5.184s), regardless of which of the three seeds produced it.

<video src="images/2026-09-06-prompt-builder-seed-consistency-unverified/consistency-run1-seed919880931791466.mp4" controls width="400"></video>

*Run 1, seed `919880931791466`. Retrieved from `comfyui-local`'s output volume (`H3_promptbuilder_consistency_run1_00003_.mp4`), not from git. `ffmpeg silencedetect` reports silence for the entire 5.184s.*

<video src="images/2026-09-06-prompt-builder-seed-consistency-unverified/consistency-run2-seed481027336619204.mp4" controls width="400"></video>

*Run 2, seed `481027336619204` (`H3_promptbuilder_consistency_run2_00002_.mp4`). Same silencedetect result: silent for the full 5.184s.*

<video src="images/2026-09-06-prompt-builder-seed-consistency-unverified/consistency-run3-seed702255819944871.mp4" controls width="400"></video>

*Run 3, seed `702255819944871` (`H3_promptbuilder_consistency_run3_00002_.mp4`). Same result again: silent for the full 5.184s.*

That confirms the hypothesis: the silence-discipline prompt-builder setting holds across all three tested seeds, not a fluke of the one seed the predecessor branch (`feature/h3-prompt-builder-consistency-test`) tested once. It's now written down where it should have been from the start: `RESULTS.md` on this branch (commit `fdbefb0`), with the actual per-run silencedetect table.

## Where it actually landed

**Confirmed, and now durable.** The hypothesis was well-formed, the harness existed in committed form, and the renders did happen and did support the hypothesis: silence held across all three seeds (`919880931791466`, `481027336619204`, `702255819944871`), N=3, single fixed prompt/graph per this branch's own design. No `docs/lab-notebook.md` exists on this branch (it postdates when this branch was cut off `main`) -- a notebook entry there is a follow-up for whoever actually merges this, not attempted here since merging wasn't part of this pass.
