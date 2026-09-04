# We wrote down what we'd test. We can't confirm we ever ran it.

This is the second write-up out of the [experiment register](2026-09-02-experiments-sankey.html), and it's the honest kind: `feature/h3-prompt-builder-seed-consistency-test` has a clean, well-formed hypothesis on record and no evidence it was ever executed.

## What came before it

An earlier branch, `feature/h3-prompt-builder-consistency-test` (no "seed" in the name), vendored a MiniMax prompt-builder tool and tried three different prompt variants once each: one with realistic music cues, one with no audio cues, and one built around a prompt-builder setting that suppresses certain narrative discipline cues to keep a scene deliberately silent. It merged into main on 2026-08-20, approved after Gavin reviewed the render output.

The name promised a consistency test. It didn't run one. Three different prompts, each rendered exactly once, tells you whether a prompt variant produces silence, not whether that result holds up across repeated attempts. One data point per condition is not a distribution.

## The redesign

Gavin caught this on review and a follow-up branch, `feature/h3-prompt-builder-seed-consistency-test`, redesigned the test properly. Its single commit (`acd9b25`, 2026-08-21) states an actual hypothesis and dependent variable: take the already-validated silent-scene prompt configuration and rerun it three times, varying only `RandomNoise`'s seed, to check whether the discipline-suppressing setting reliably keeps the scene silent regardless of which seed lands, rather than being a fluke of the one seed already tested.

The commit is thorough. It defines three sibling workflow files (`h3_promptbuilder_consistency_run1/2/3.api.json`), each byte-identical except for `noise_seed` (`919880931791466`, `481027336619204`, `702255819944871`) and a distinct `filename_prefix` so all three outputs land side by side instead of overwriting each other. It adds `scripts/compare-consistency-run.sh`, a host-side script meant to fetch all three rendered clips from `comfyui-local` and print a per-run `ffmpeg silencedetect` verdict table, so a human could read one table instead of eyeballing three separately-downloaded videos by ear.

## What's missing

That's where the trail stops. `git log main..feature/h3-prompt-builder-seed-consistency-test` shows exactly one commit: the redesign itself. There is no second commit recording that the three runs happened, no `silencedetect` table committed anywhere, and the branch itself was never merged to main. `docs/lab-notebook.md` on main has no entry mentioning this test by name.

It's possible the three renders happened and `compare-consistency-run.sh` was run by hand, off the record, the way the script's own comments describe (a manual step, not a Concourse task, because task containers can't reach `comfyui-local`'s output volume). It's equally possible nothing past the workflow-file setup ever ran. Both are consistent with what's actually in the repo, which is nothing beyond the setup.

## Where it actually landed

**Unverified, not refuted, not confirmed.** The hypothesis is well-formed and the harness to test it exists in committed form. What doesn't exist is any record that the harness was ever pointed at the GPU. Per this lab's register, that's a distinct outcome from "confirmed" or "refuted": an experiment that got designed correctly and then either never ran or ran and left no trace. Worth flagging plainly rather than assuming either way: if the silence-consistency question still matters for production use of that prompt-builder setting, this branch needs an actual re-run and a results commit before anyone can cite it.
