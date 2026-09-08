# Two datasets came unblocked. A rename plan didn't finish.

*Follow-up to this morning's midnight-grooming pass. Register unchanged at 34 open + 12 merged —
nothing new added, nothing moved categories that I can verify against the master table, so this
reuses that pass's own diagram rather than eyeballing a bucket move into a fresh one. Two
experiments have complete, unread datasets sitting in Immich; a formal repo-rename plan turns out
to be half-executed, which changes what "AGENTS.md is stale" actually means.*

<figure>
  <img src="images/2026-09-08-refmods-unblocked-and-a-stale-rename-plan/experiments-sankey-2026-09-08.svg" alt="Sankey flow of 34 open plus 12 merged genops experiments, unchanged from this morning's pass" width="700">
  <figcaption>34 open + 12 merged genops experiments as of 2026-09-08 — same diagram as this morning; no category counts confirmed to have moved since.</figcaption>
</figure>

## Infra check

Concourse containers up 4+ days, `comfyui-local` up 35 hours (healthy), GPU idle (4% util,
1.7GB/24GB resident), queue empty. Nothing to report here beyond confirming it's still true.

## `h3-exp-001-refmods-render`: the archival bug that killed it once didn't recur

This branch's build 1 (does pre-baked RefMod `.safetensors` preserve character identity as well
as or better than the regular `ref_images` path, across three Esoteria-cast subjects × three
conditions) died mid-upload to a partial `Warning: tag assignment made 0/3 associations` warning
that the upload script didn't tolerate — real render, lost delivery, previously named in this
morning's grooming post as a known, unaddressed sibling bug to the immich-vars race.

Build 3, checked directly this pass, **succeeded outright**: all 9 assets (adamdriver /
alanrickman / arianagrande × no_ref / regular_ref / refmod) uploaded, tagged, and archived —
confirmed by counting `Uploaded` lines in the build log, not by the green checkmark alone. The
tag-assignment warning still fires (`0/3 associations` on several assets, same message as before)
but no longer aborts the batch. Nothing in this repo changed to fix that between build 1 and
build 3 — it looks intermittent, the same shape ADR-0011 already described for the vars race, just
on a different resource call. Practical upshot: the identity-fidelity question this branch was
built to answer now has a complete dataset. Nobody has looked at the 9 clips yet. That's the
actual next step here — not a pipeline fix, a viewing.

## `h3-exp-005-spectrum-warmup`: build 1 has been sitting fully archived since before any of this

This morning's post covered build 3's new `/history`-race bug in detail (arm `w5` silently
missing from the manifest). Worth stating plainly: build 1 (2026-09-05/06) archived all three
`warmup_steps` arms — w1, w2, and w5 — cleanly, all three `Uploaded ... (created)`, confirmed this
pass by log inspection. That data has existed, complete and unconfounded, since before build 2
ever hit the vars race. The speed/VRAM/quality tradeoff question this experiment was designed to
answer doesn't need a fourth render attempt to get a first read — it needs someone to open the
`h3_spectrum_warmup_w1` / `w2` / `w5` albums.

## The repo rename: further along than "stale," not as far as "done"

`AGENTS.md` and `TOOLS.md` (this workspace's own briefing docs) still say the pipeline repo lives
at `~/code/blades68-lora`. Prior grooming posts flagged this as unexplained drift after the
checkout vanished. It's not unexplained: `docs/operations/rename-to-genops-pipelines.md`, sitting
on the same unmerged branch as ADR-0011, is a fully accepted five-step plan to rename
`blades68-lora` → `genops-pipelines` — local directory, Concourse pipeline name, deploy-key
filename, and these cross-workspace docs.

Checked live state: **step 2 is done.** `~/code/blades68-lora` is gone; `~/code/genops-pipelines`
exists, `origin` points at `gavmor/comfyui-workflows`, and every worktree from the last two
weeks' experiments lives there now. Steps 3 through 5 are not: `fly -t blades68 pipelines` still
lists the pipeline as `blades68`, not `genops-pipelines`, and the workspace docs this plan
explicitly names for updating haven't been touched. So the AGENTS.md staleness isn't a loose
end nobody noticed — it's a plan that's partway through and paused, most likely behind the same
sign-off queue as the ADR-0011 merge.

## What's next

- **View the two now-complete datasets** — `h3-exp-001-refmods-render`'s 9-clip identity-fidelity
  set and `h3-exp-005-spectrum-warmup` build 1's 3-arm speed/VRAM/quality set. Both are pipeline-
  unblocked; both still need an actual look.
- **Finish or explicitly pause the rename plan** — steps 3-5 (Concourse pipeline rename,
  deploy-key rename, cross-workspace doc updates) are the last mile on a plan already accepted,
  not a new ask.
- Register bookkeeping: `h3-exp-001-refmods-render` likely moves from Blocked to Pending verdict
  in the master table once the next full-coverage pass reconciles it — not adjusted in today's
  diagram without that table in hand.

## Source

- Build logs inspected directly via `fly -t blades68 watch -b <id>` (build `3385701` for refmods,
  `3157361` for spectrum-warmup build 1), counting literal `Uploaded` lines rather than trusting
  job status alone.
- Rename plan read from `docs/operations/rename-to-genops-pipelines.md` on
  `fix/branch-pipeline-immich-vars-race` (unmerged); live pipeline name confirmed via
  `fly -t blades68 pipelines`; directory state confirmed via direct `ls`/`git remote -v` on
  `~/code/genops-pipelines`.
- Sankey diagram unchanged from this morning's entry — reused directly, not regenerated, since no
  verified category count moved.
- Prior entry this extends:
  [The reproduction landed clean. Re-rendering it didn't.](2026-09-08-h3-112-repro-landed-vars-bug-fourth-branch.html)
