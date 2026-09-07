# The blades68-lora checkout vanished, and the immich-vars bug is now confirmed systemic

Routine midnight grooming pass. Two separate findings, neither a render-quality question — both
are lab-infrastructure integrity problems, the kind this cron exists to catch before they compound.

## `~/code/blades68-lora`, the main checkout, is gone from disk

`git fetch` against it failed outright. `ls -la /home/user/code/blades68-lora` returns "No such
file or directory" — not a broken symlink, not a permissions issue, the directory itself is
absent. That's the repo every `wt` worktree on this box was created from: roughly 48 of them
(`blades68-lora.feature-h3-*`, `blades68-lora.fix-*`, etc.), each holding a `.git` file that
points back at `/home/user/code/blades68-lora/.git/worktrees/<name>`. With the parent gone,
every one of those pointers is dead — `git status` inside `blades68-lora.sopro-tts-experiment`,
picked as a spot check, fails with `fatal: not a git repository`. Same result expected across
the rest; the failure mode is structural, not branch-specific.

What this does *not* affect: Concourse's `blades68` pipeline and all `comfyui-branch` instances
clone straight from `github.com/gavmor/blades68-lora` on each build, so render dispatch is
unaffected — confirmed by three builds completing overnight (below) while this was already
broken. Disk isn't the cause either (`/`: 87% used, 124G free, no space pressure).

What it does block: any new local git work on this repo — content edits, pipeline changes,
new worktrees for the next experiment — until the checkout is recovered. The working-directory
*files* inside each orphaned worktree are still on disk and untouched; nothing has been deleted
by this pass, and nothing here attempts a fix. Recovering ~48 worktrees' git linkage against a
missing parent isn't a call to make unattended — it needs Gavin to decide whether to re-clone
fresh and reconcile each worktree's uncommitted state by hand, or something else. Flagged, not
touched.

## The `immich_api_key`/`immich_url` bug just crossed from "one branch's fluke" to systemic

The [2026-09-04 sparse-attention write-up](2026-09-04-h3-sparse-attention-validation.html) first
caught this: a `comfyui-branch` build's `local-immich-gallery` archival `put` step failing with
`undefined vars: immich_api_key, immich_url`, isolated — at the time — to one branch instance
among roughly fifty that ran clean in the same `set-branch-pipelines` batch. The standing call
was to treat it as that branch's own fluke unless it recurred elsewhere.

It recurred. Twice, overnight:

- `feature/h3-exp-005-spectrum-warmup`, build 2 (2026-09-06 19:06–19:56): same three-line
  `undefined vars: immich_api_key, immich_url` error, build `errored`.
- `feature/h3-2026-09-05-postprocessing`, build 4 (2026-09-06 20:35–21:01): identical failure,
  same two vars, same terminal state.

Both are real, unconfounded experiments that rendered clean and then lost their output at the
same last step. `h3-exp-005-spectrum-warmup` is a same-params repeat (rep 2/2, commit `0af1e6e`)
of an already-succeeded run — its own build 1 archived fine hours earlier, build 2 didn't, no
config change between them. That rules out a branch-specific template problem and points at
something intermittent in how `set_pipeline` threads `immich_api_key`/`immich_url` into a given
build's vars, not a fixed per-branch state. Three confirmed instances now (`h3-optimizations-
validation`, `h3-exp-005-spectrum-warmup`, `h3-2026-09-05-postprocessing`) is enough to call this
a real intermittent bug in the shared `branch-pipeline-template.yml`/`set-branch-pipelines` path,
not three unlucky branches. Per the original write-up's own standing instruction, that upgrades
it: worth Gavin's attention as a pipeline-config fix, not something to guess-patch inline.

Rendered output for both new instances should still be sitting in `comfyui-local`'s persistent
`/opt/ComfyUI/output/labeled/` volume, same as the sparse-attention case — it survives even
though the archival step doesn't. Don't assume Immich has a copy of either.

### A second, smaller loss in the same neighborhood

`feature/h3-exp-001-refmods-render` (build 1, 2026-09-06 19:03–19:50, `failed`) — a real 3-subject
× 3-arm RefMods-loader identity test (`ed01b6a`), holding prompt, seed, resolution, length, and
step count constant across all nine arms — rendered all nine clips and started uploading them to
Immich individually. Partway through (`alanrickman_regular_ref`), one tag-assignment call came
back `Warning: tag assignment made 0/3 associations; some assets may be missing tags` — and the
task exited immediately after printing it, before uploading the remaining arms
(`arianagrande_regular_ref` confirmed rendered, per its own submission log entry, but never
reaches an upload line). Reads like the upload script isn't tolerating that partial-tag-failure
exit code and is aborting the whole batch under it, rather than logging the warning and
continuing — a narrower, different bug from the vars issue above, but the same shape: a real
render succeeding and then losing part of its own delivery at the archival step.

## What's healthy

Both Concourse containers (`concourse-concourse-1`, `concourse-concourse-db-1`) up 2 days,
`comfyui-local` up and healthy, GPU idle (0% util, 2.1GB/24GB VRAM resident). `fix/h3-
optimizations-validation-resolve-prompt-description` (the branch meant to backfill the missing
`resolve-prompt-description.py` sidecar script seen in the postprocessing logs above) ran clean
twice — but both runs hit "no changed workflows to render," so it hasn't actually been exercised
against the case it's named for yet. T2VA's three active branches
(`h3-drawing-tutorial-sheet`, `h3-sync-sound-challenge`, `stock-turbo-lora-baseline`) are
unchanged since the last full sweep, worktrees intact.

## Source

Concourse builds inspected directly via `fly -t blades68 builds` / `fly -t blades68 watch`, not
taken from build-list status alone. Branch head commits confirmed via GitHub API against
`gavmor/blades68-lora`.
