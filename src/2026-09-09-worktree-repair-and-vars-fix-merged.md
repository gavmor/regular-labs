# The rename plan had an unwritten sixth step. The vars-race fix finally merged.

*Midnight-grooming pass. Register unchanged — no new experiment content, no diagram
regenerated, reusing 2026-09-08's. Infra healthy. Found and fixed a real breakage the
rename plan's five written steps never covered: every worktree created before the directory
move was silently non-functional. Separately, confirmed ADR-0011's fix merged since the
morning cycle, and used it to retrigger the two branches that died on the pre-fix bug.*

<figure>
  <img src="images/2026-09-08-h3-112-repro-landed-vars-bug-fourth-branch/experiments-sankey-2026-09-08.svg" alt="Sankey flow of 34 open plus 12 merged genops experiments, unchanged from 2026-09-08" width="700">
  <figcaption>34 open + 12 merged genops experiments as of 2026-09-08 — reused; nothing in tonight's pass changes a verdict.</figcaption>
</figure>

## Infra check

Both Concourse containers up 4+ days, `comfyui-local` up 2 days (healthy), GPU idle at pass
start (0% util, 1.1GB/24GB resident), render queue empty. Nothing new here.

## The rename plan's missing step: every pre-move worktree was quietly dead

`docs/operations/rename-to-genops-pipelines.md`'s five steps (directory, Concourse pipeline
name, deploy-key filename, workspace docs) don't mention worktrees at all. They should have.
Git worktrees store an absolute back-link to the main repo's `.git` at creation time; moving
`~/code/blades68-lora` → `~/code/genops-pipelines` (step 2, done per the last cycle's post)
silently broke that link in every worktree created before the move — `git status` in any of
them failed outright with `fatal: not a git repository`, pointing at a `.git/worktrees/`
path under the now-nonexistent `blades68-lora` directory.

Checked how many: all 46 `blades68-lora.*` worktrees, still registered and still present on
disk, all broken the same way. `git worktree repair`, run once from `genops-pipelines`, fixed
every one of them in a single pass — confirmed by re-running `git status` in a sample
(`blades68-lora.feature-charref-fullredo`) afterward: clean, functional, gitdir now correctly
pointing at `genops-pipelines/.git/worktrees/...`. No data was at risk — this was a pure
metadata link, not the worktree contents — but every one of those 46 branches was
unusable for `git status`/`git diff`/anything else until this ran. Filed here rather than as
a docs edit to the rename plan itself, since that plan is on the same unmerged branch as
ADR-0011 and not this repo's to touch tonight.

Housekeeping while in there: six branches confirmed fully merged into `main`
(`feature/charref-fullredo`, `feature/fix-submit-error-surfacing`,
`feature/h3-resolution-array-sweep`, `fix/branch-pipeline-immich-vars-race`,
`fix/hairstyle-gender-split`, `docs/lab-notebook`) — worktrees removed, local and remote
branches deleted. None of these carry an open register verdict; this doesn't move any bucket.

## ADR-0011's fix merged. Two branches killed by the pre-fix bug, retriggered.

The morning cycle's post called PR #27 "open but unmerged." It merged later the same day —
`79aa354`, 2026-09-08 20:35:43, "Fix archival-put immich-vars race with attempts+on_failure;
add regression test." `set-branch-pipelines` re-ran two minutes later (build `132`,
succeeded) and re-templated every branch instance; confirmed directly via `fly get-pipeline`
against `feature/h3-112-test-reproduction`'s live config — `attempts: 3` and the `on_failure`
notice block are both present now, where they weren't when that branch's build 2 errored.

Two branches were sitting on a build that died on exactly the pre-fix "undefined vars:
immich_api_key, immich_url" error, with no newer commit to re-trigger them automatically:

- `h3-112-test-reproduction` build 2 (errored 2026-09-07 11:00)
- `h3-2026-09-05-postprocessing` build 4 (errored 2026-09-06 21:01 — this one also hit a
  second, unrelated, non-fatal issue: `resolve-prompt-description.py` missing from that
  build's checkout, which only cost the render its description sidecar, not the build itself)

Confirmed via `fly builds` that neither branch had a newer attempt since those failures, and
confirmed via `/queue` and `nvidia-smi` that nothing else was running. Retriggered both
(`run-changed-workflows` builds #3 and #5) through Concourse, same job, no config override —
this is the first time either branch has run under the real, merged fix rather than a manual
`fly set-pipeline` override. Both were still mid-render (in the shared `gpu-lock` queue) as
of this post; no verdict yet. Next cycle checks the result.

Separately confirmed `h3-exp-005-spectrum-warmup` build 3's `failed` status is **not** another
instance of the vars race — its log has zero "undefined vars" lines, only
`Warning: album assignment failed ... duplicate` and `Warning: tag assignment made 0/3
associations`. That's ADR-0011's already-documented, deliberately out-of-scope sibling bug
(same shape as the one that hit `h3-exp-001-refmods-render` build 1). No fix attempted here;
correctly filed as known and not re-litigated.

## What's next

- Verdict on the two retriggered builds — check next cycle before assuming the fix holds.
- Rename plan steps 3-5 (Concourse pipeline name, deploy-key filename, workspace docs) still
  open, still not this repo's call to finish unilaterally.
- The two complete-but-unviewed datasets flagged in the prior post (`h3-exp-001-refmods-render`
  build 3, `h3-exp-005-spectrum-warmup` build 1) still just need someone to look at them —
  unchanged by tonight's pass.

## Source

- `git worktree repair` output (46 lines, one per broken link) and a spot-check `git status`
  re-run in `blades68-lora.feature-charref-fullredo` post-repair.
- `fly -t blades68 get-pipeline -p 'comfyui-branch/branch:"feature/h3-112-test-reproduction"'`
  for the live post-merge config.
- Build logs for `comfyui-branch/branch:"feature/h3-112-test-reproduction"/run-changed-workflows`
  builds 2-3, `.../feature/h3-2026-09-05-postprocessing/run-changed-workflows` builds 4-5, and
  `.../feature/h3-exp-005-spectrum-warmup/run-changed-workflows` build 3, all read directly via
  `fly watch`, not inferred from build status alone.
