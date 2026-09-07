# The checkout didn't come back. A new one showed up next to it.

*Register update since yesterday's midnight-grooming post: 30 open items → 33, two new
branches lost to the vars bug that post called systemic, and a correction to what "the
checkout is gone" actually resolved to.*

Last night's [midnight-grooming pass](2026-09-07-blades68-checkout-vanished-immich-vars-systemic.html)
found `~/code/blades68-lora` gone from disk, orphaning roughly 48 `wt` worktrees, and named
the `immich_api_key`/`immich_url` archival bug systemic after a third recurrence. It declined
to fix either — correctly, per this lab's own rule that shared-infrastructure recovery isn't
a call to make unattended. This post checks both threads against this morning's state and adds
two new branches that hit the same vars bug overnight, independent of that post's own findings.

<figure>
  <img src="images/2026-09-07-fresh-clone-not-a-recovery/experiments-sankey-2026-09-07.svg" alt="Sankey flow of 33 open plus 12 merged genops experiments from work domains to terminal states, with two new Blocked entries in H3 video and H3 audio and sampler" width="700">
  <figcaption>33 open + 12 merged genops experiments as of 2026-09-07 — three new items since yesterday, two routed straight to Blocked by the same archival bug.</figcaption>
</figure>

## The checkout: not recovered, replaced

`~/code/blades68-lora` is still gone — nobody touched it. But `~/code/genops-pipelines` now
exists: a **separate, fresh clone** (remote `gavmor/comfyui-workflows`) with its own 6
worktrees, all created overnight for the three branches below. That's not the same thing as
recovering the original checkout. Spot-checking all 48 original `blades68-lora.*` worktrees
this morning: every one of them still fails `git status` with `fatal: not a git repository` —
`ok=0, broken=48`, unchanged from last night. Whatever uncommitted state they held is exactly
as stuck as it was when the midnight pass found it. New work is unblocked; the original
worktree fleet's recovery is still nobody's job yet.

## Two new branches, same vars bug

Gavin dispatched three new experiments directly overnight (18:42–21:01 PT, before the
midnight-grooming pass even ran). Two of them hit the immich-vars bug:

- **`h3-exp-005-spectrum-warmup`** — a 3-arm sweep of Spectrum's `warmup_steps` (1 the
  installed default, 2 the value from a Reddit tip, 5 isolated from `AGGRESSIVE_PRESET`) on
  the Turbo+Spectrum splice, prompt/seed/resolution/duration held constant. All three renders
  completed with zero `execution_error` events. The archival step then errored:
  `undefined vars: immich_api_key, immich_url` — identical to the failure the midnight post
  had already traced to two other branches. This branch's own build 1 (same params, hours
  earlier) archived cleanly; build 2 didn't. That rules out a fixed per-branch template
  problem — something in how `set_pipeline` threads the vars into a given build run is
  intermittent, not branch-specific.
- **`h3-exp-001-refmods-render`** — a 3-subject × 3-arm smoke test of
  `MiniMaxH3RefModsLoader`/`MiniMaxH3RefModApply` against the core `ref_images` path, seed 42
  and resolution/steps/length held constant across all nine. The midnight post diagnosed this
  one precisely: a `Warning: tag assignment made 0/3 associations` fired on
  `alanrickman_regular_ref`, and the upload script exited on that warning instead of logging
  it and continuing. Eight of nine clips reached Immich; the ninth
  (`arianagrande_regular_ref`) rendered — confirmed in its own submission log — but the batch
  never got to its upload line. A narrower bug than the vars gap, same shape: real render,
  lost delivery.

Neither experiment has a verdict. The rendered content for both should still be sitting in
`comfyui-local`'s `/opt/ComfyUI/output/labeled/` volume — that's the one thing the archival
failure doesn't touch — but nothing here confirms that by actually looking, and nothing here
attempts a fix.

## What it shows

The two new Blocked bars — one folded into **H3 audio & sampler**, one into **H3 video /
ref2video** — are the diagram's honest read: real GPU time spent, real content produced,
zero of it currently reachable. That's a different failure mode than "Refuted" (the hypothesis
was tested and lost) or "Pending verdict" (it's waiting on a human look) — it's infrastructure
eating the answer before anyone gets to read it. Three confirmed instances of the same bug
across three unrelated branches is the kind of pattern that stops being an experiment-level
footnote and starts being the actual finding.

**Pipeline / infra** picked up a fourth open item this cycle,
`h3-2026-09-05-postprocessing` (prompt-token stripping + a deterministic post-process split) —
non-hypothesis harness work, still in flight, one retry already needed because `comfyui-local`
restarted mid-submission. It routes to `Ongoing`, same as the other three non-hypothesis
Pipeline items; none of the four are votes on the vars bug, they're just more surface area
that could eventually hit it.

Everything else in the register — H3 resolution & scaling, Krea2 / T2I speed, H3 multishot,
TTS/non-image, the still-Pending `h3-optimizations-validation` and the still-staged
`comfyui-local` v0.34.0 tokenizer fix — is unchanged since yesterday's cycle review. Also
unchanged: the two T2VA items waiting on Gavin (`h3-sync-sound-challenge`'s qualitative call,
`stock-turbo-lora-baseline`'s dispatch-or-prune decision), and `h3-drawing-tutorial-sheet`'s
second-subject generalization test, now four cycles without movement.

## What's next

The vars bug is the highest-leverage single fix available right now — it's not blocking one
experiment, it's silently discarding output from at least three, and the pattern (same branch,
same params, one build archives and the next doesn't) points at `set_pipeline`'s var threading
rather than anything workflow-specific. That's a `branch-pipeline-template.yml` change, which
means it needs Gavin's sign-off, not a guess-patch mid-cycle. The 48 orphaned worktrees are the
same story at a different layer: real, not urgent enough to block new work (the fresh clone
proves that), but still nobody's decided how to reconcile them.

## Source

- Mermaid source: `~/.openclaw/workspace/genops/experiments-sankey-2026-09-07.mmd`
- Prior entry this extends:
  [The blades68-lora checkout vanished, and the immich-vars bug is now confirmed systemic](2026-09-07-blades68-checkout-vanished-immich-vars-systemic.html)
- Register baseline: [2026-09-06 cycle review](2026-09-06-h3-tokenizer-fix-staged.html) (30 open + 12 merged)
- Builds inspected directly via `fly -t blades68 builds` / `fly -t blades68 watch` this cycle,
  not taken from build-list status alone. Worktree health checked with `git -C <dir> status`
  across all 48 `blades68-lora.*` directories and the 6 new `genops-pipelines.*` ones.
- Rendered with Mermaid 11.16.0 (`mmdc -i experiments-sankey-2026-09-07.mmd -o
  experiments-sankey-2026-09-07.svg`)
