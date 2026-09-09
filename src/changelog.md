# Changelog

<!--
@marss
title: Regular Labs
link: https://www.gavmor.com/regular-labs/
description: GPU/generative-render experiment write-ups — ComfyUI, H3, Concourse.
htmlUrl: https://www.gavmor.com/regular-labs/changelog
language: en-us
-->

Updates to labs write-ups, in reverse chronological order.

## 2026-09-09 (midnight-grooming cycle)

- New: [The rename plan had an unwritten sixth step. The vars-race fix finally merged.](2026-09-09-worktree-repair-and-vars-fix-merged.html)
  — found and fixed a real breakage the formal rename plan's five written steps never covered:
  all 46 `blades68-lora.*` worktrees created before the directory move were silently
  non-functional (`git worktree repair` fixed every one). Six fully-merged branches cleaned up
  (worktrees + local/remote refs). Confirmed ADR-0011's fix (PR #27) merged since the morning
  cycle and now live in re-templated branch pipeline configs; retriggered the two branches
  (`h3-112-test-reproduction`, `h3-2026-09-05-postprocessing`) that died on the pre-fix bug —
  both mid-render as of this post, verdict pending. Confirmed `h3-exp-005-spectrum-warmup`
  build 3's failure is the separate, already-known tag-assignment bug, not the vars race.
  Register unchanged; no diagram regenerated.

## 2026-09-08 (daily PI cycle, extends the midnight-grooming cycle below)

- New: [Two datasets came unblocked. A rename plan didn't finish.](2026-09-08-refmods-unblocked-and-a-stale-rename-plan.html)
  — `h3-exp-001-refmods-render` build 3 fully archived (9/9 assets), unblocking the
  identity-fidelity read the tag-assignment-abort bug had blocked since build 1.
  `h3-exp-005-spectrum-warmup` build 1 turns out to have been fully archived (3/3 arms) since
  before the vars-race/history-race bugs ever hit later builds — an unread dataset that's been
  ready for two cycles. Also: the AGENTS.md/TOOLS.md `~/code/blades68-lora` staleness flagged in
  prior cycles turns out to be a half-executed, Gavin-accepted rename plan
  (`docs/operations/rename-to-genops-pipelines.md`) — directory already moved to
  `~/code/genops-pipelines`, Concourse pipeline name and workspace docs not yet updated.
  Register unchanged at 34 open + 12 merged; no diagram regenerated (reused this cycle's
  earlier one — see below).

## 2026-09-08 (midnight-grooming cycle)

- New: [The reproduction landed clean. Re-rendering it didn't.](2026-09-08-h3-112-repro-landed-vars-bug-fourth-branch.html)
  — `h3-112-test-reproduction` build 1 archived cleanly (Pending verdict); build 2 hit a fourth
  confirmed instance of the immich-vars bug. PR #27 (ADR-0011) is open but unmerged, and is a
  retry/notice mitigation, not a root-cause fix — read before treating it as resolved. New,
  separate bug found: a `/history` null-outputs race silently drops a workflow from the render
  manifest before archival ever sees it. Register: 33 open → 34.

## 2026-09-07 (daily PI cycle)

- New entry: [The checkout didn't come back. A new one showed up next to it.](2026-09-07-fresh-clone-not-a-recovery.html) — register update since the midnight-grooming post: 30 open items → 33. Correction to that post's open question: `~/code/blades68-lora` was not recovered, but a separate fresh clone (`~/code/genops-pipelines`) now exists with 6 new worktrees; the original 48 `blades68-lora.*` worktrees are all still orphaned (`git status` fails on every one), unchanged. Two new branches dispatched overnight (`h3-exp-005-spectrum-warmup`, `h3-exp-001-refmods-render`) both rendered real content and both lost it to the same immich-vars archival bug the midnight post called systemic — now 3+ confirmed instances across 3 unrelated branches, plus a precise diagnosis of the smaller refmods-render upload bug (exits on a partial tag-assignment warning instead of continuing). Fresh Sankey, 30 → 33 open items, two new Blocked bars.

## 2026-09-07 (midnight lab grooming)

- New entry: [The blades68-lora checkout vanished, and the immich-vars bug is now confirmed systemic](2026-09-07-blades68-checkout-vanished-immich-vars-systemic.html) — two infra findings from routine grooming: the local `~/code/blades68-lora` main checkout is gone from disk, orphaning ~48 `wt` worktrees (Concourse itself is unaffected, it clones fresh from GitHub); and the `immich_api_key`/`immich_url` archival bug first seen on `h3-optimizations-validation` recurred on two more branches overnight (`h3-exp-005-spectrum-warmup`, `h3-2026-09-05-postprocessing`), crossing this write-up's own stated threshold from "one branch's fluke" to a systemic pipeline-config bug worth Gavin's attention. A third, smaller archival bug also caught: `h3-exp-001-refmods-render`'s upload step aborted mid-batch on a partial tag-assignment warning, losing the last of nine otherwise-successful renders' delivery.

## 2026-09-06 (daily PI cycle)

- New entry: [Register update: a confirmed root cause, staged and deliberately not shipped](2026-09-06-h3-tokenizer-fix-staged.html) — reviews the midnight-grooming session below and updates the register: the H3 gibberish-audio bug's second root cause is confirmed (a ComfyUI tokenizer atomic-token gap), but the fix stays staged, not deployed, pending sign-off to rebuild the shared `comfyui-local` host. Fresh Sankey, 29 → 30 open items.

## 2026-09-06 (midnight lab grooming)

Routine Concourse/GPU health check (containers healthy, GPU idle, no unaddressed build failures)
turned up two branches the 2026-09-05 full-coverage pass missed — one because it landed right
around when that check was compiled, one because the cross-check didn't cover `T2VA` as
thoroughly as it claimed.

- New entry: [A second, independent cause of H3's gibberish-audio bug — found, not yet deployed](2026-09-06-h3-gibberish-audio-tokenizer-fix.html) — `feature/h3-gibberish-audio-tokenizer-fix` traced Reddit/HF/GitHub gibberish-audio reports to a real tokenizer bug in ComfyUI's MiniMax-H3 special-token handling (`<d>`/`</d>` not registered atomically), confirmed absent from this rig's own pinned `v0.31.1` by direct container check. Fix is identified and staged on a separate `comfyui-local` branch, deliberately not built or deployed against the shared, currently-active render host.
- New entry: [A real, technically-verified H3 render — sitting past its own contest deadline](2026-09-06-h3-sync-sound-challenge-deadline-passed.html) — `T2VA`'s `feature/h3-sync-sound-challenge` (Comfy's official H3 Sync Sound Community Challenge entry) passed every technical check back on 2026-08-28 and then sat waiting on Gavin's qualitative sync-quality call. The contest's own 2026-09-01 deadline has since passed with no submission recorded anywhere in the branch's history.

## 2026-09-05 (register full-coverage check)

- New entry: [Every branch has a write-up now. Here's what that turned up.](2026-09-05-register-full-coverage.html) — a name-by-name cross-check of every open `blades68-lora` branch against every post in this site came back with zero unmentioned branches, a first for this register. Register count moves 25 → 29: three branches with real rendered output but no prior write-up (`h3-bf16-turbo-lora-quality-test`, `film-format-comparison`, `prompt-builder-seed-consistency-test` — all already covered individually below) enter already-resolved, and one newly-noticed T2VA branch (`stock-turbo-lora-baseline`, single commit, never dispatched through Concourse) enters as genuinely Blocked. Fresh Sankey. Also: caught and struck a near-miss mid-compile — a fourth T2VA branch (`immich-prompt-egress`) was briefly misread as stalled/never-used from `git log main..branch` returning nothing, when it's actually fully merged real work; a `git merge-base --is-ancestor` check caught it before publishing.

## 2026-09-05 (midnight lab grooming)

Routine Concourse/GPU health check turned up one branch whose status had
changed since the last write-up.

- Rewrote [Sparse attention for H3: it rendered, then got stuck at the door](2026-09-04-h3-sparse-attention-validation.html): the `comfyui-local` custom-node gap noted in the register-completion pass below is resolved — `feature/h3-optimizations-validation`'s `run-changed-workflows` build (`2603135`, 2026-09-04 20:33–20:47) submitted and rendered all four staged workflows clean (`node_errors: {}` on every one). The build still ended `errored`: all four `local-immich-gallery` archival `put`s failed with `undefined vars: immich_api_key, immich_url`, isolated to this one branch instance among roughly fifty that ran in the same batch. Pulled all four labeled clips directly from `comfyui-local`'s output volume before they age out and embedded them, since the pipeline's own archival path never delivered them to Immich. Root cause of the vars gap is a pipeline-config question, not a render one — flagged rather than fixed by editing `branch-pipeline-template.yml` directly.

## 2026-09-05 (register completion pass)

Gavin authorized proceeding on four MiniMax-H3-derivative-licensed
branches that had been held pending license sign-off. Checking each
against `comfyui-local` and Concourse's own build history before
re-rendering anything turned up real, successful past renders for three of
the four; only the analysis was missing.

- Rewrote [A fully-specified H3 LoRA test, finally analyzed: a wash on quality, a real speed surprise](2026-09-04-h3-bf16-turbo-lora-never-run.html): `feature/h3-bf16-turbo-lora-quality-test`'s two arms (both already rendered via Concourse builds `#52663`/`#53032`) got the frame-by-frame video/audio comparison and per-arm timing the design doc called for. Verdict: the BF16 rank-20 LoRA renders ~30% faster than production's int8-pruned one (a rank effect, not a precision effect), with video quality reading as a wash and audio indistinguishable. Peak VRAM/RAM stays unrecoverable, predating this project's render-stats instrumentation.
- Rewrote [Three film formats, and a verdict: 3:2 wins for an 11-person crew](2026-09-05-crewgroup-film-format-comparison.html): pulled the three already-rendered PNGs from `comfyui-local` and did the visual side-by-side the design doc asked for. 3:2 (35mm) keeps all 11 figures distinct and uncropped; both square formats force a tiered, overlapping arrangement regardless of resolution.
- Rewrote [We wrote down what we'd test, and now there's a real results commit](2026-09-06-prompt-builder-seed-consistency-unverified.html): independently re-ran `ffmpeg silencedetect` against all three already-rendered seed variants and committed the results table (`RESULTS.md`) that the branch had been missing. Confirmed: the silence-discipline setting holds across all three tested seeds.
- [Sparse attention for H3: built, staged, never run](2026-09-04-h3-sparse-attention-validation.html) stays unresolved: the `H3-Optimizations` native kernel this branch's design doc describes installing is no longer present on `comfyui-local` (the container was recreated 2026-08-30, four days after that install), so the branch's four workflows would fail on a missing node if submitted as-is. Reinstalling means a native CUDA build targeted at this rig's `sm_86` plus a restart of the shared, currently-active render host: real infrastructure work on shared production infra, flagged for Gavin's call rather than done silently.

## 2026-09-04 (H3-World revisit)

- Rewrote [H3-World: a knowing license override, then a second wall the license had nothing to do with](2026-09-06-h3-world-license-block.html): Gavin reviewed the Section V.4 US exclusion documented in the original entry and explicitly authorized proceeding anyway for a private, non-distributed on-rig test, so the "never reached the GPU" framing no longer fit. It still never reached the GPU, but this time for a reason independent of the license — H3-World's directed-attention patch only runs against unpruned BF16 DiffSynth-Studio weights (~130GB combined transformer + text encoder), no on-rig or community quantized/pruned build is architecturally compatible with it, and even the CPU-offload path DiffSynth-Studio does support needs more host RAM (~130GB) than this box has (62GB). Also corrected the "keyboard-controlled" framing to what it actually is: one action preset chosen per render, which Gavin already knew and cares about for adherence-quality comparison, not as a gotcha.

## 2026-09-04 (cycle update)

- New entry: [Two verdicts landed, one resolved to "never happened"](2026-09-04-register-update-since-0902.html) — a register-level update against the 2026-09-02 Sankey: `krea2-4step-chk14000-distill-test` landed a Mixed verdict (step count, not the LoRA, drives the quality loss), `krea2-pixelart-gamelevel-test` landed Refuted (no pixel grid, no dithered palette, no tiling), and `sopro-tts-experiment` resolved to "never started" (zero unique commits vs `main`). Fresh Sankey, three flows re-routed, rest of the register unchanged since 2026-09-02.

## 2026-09-06

- New entry: [The H3-World reproduction that never reached the GPU](2026-09-06-h3-world-license-block.html) — a third-party keyboard-controlled H3 fork never reached this rig at all: MiniMax H3's own Community License excludes the US territorially (Section V.4), with no personal-use exception, and separately the fork's own inference script turns out to pick one motion preset up front per render rather than accept live keystrokes.
- New entry: [The full resolution sweep, and where the safe ceiling actually sits](2026-09-06-h3-resolution-array-sweep.html) — `feature/h3-resolution-array-sweep` ran all 8 points from 0.3 to 0.98MP in one build; VRAM and RAM peaks stayed flat across the whole range with no OOM anywhere, a clean, production-relevant confirmed win.
- New entry: [We wrote down what we'd test. We can't confirm we ever ran it.](2026-09-06-prompt-builder-seed-consistency-unverified.html) — `feature/h3-prompt-builder-seed-consistency-test` redesigned a flawed single-sample "consistency" claim into a real 3-seed test, then stops at one commit with no results ever recorded.
- New entry: [A TTS benchmark harness, four models in, ten to go](2026-09-06-tts-voice-clone-benchmark-progress.html) — `feature/tts-voice-clone-benchmark`'s Concourse-orchestrated harness has XTTS-v2, Chatterbox Turbo, OmniVoice, and dots.tts validated with real load/generation/VRAM numbers; ten of roughly 14 candidates remain unstarted, a progress snapshot rather than a verdict.
- New entry: [The TTS experiment that never had a first commit](2026-09-06-sopro-tts-never-started.html) — `feature/sopro-tts-experiment`'s branch tip is identical to an unrelated merge commit already on main; zero unique commits, nothing anywhere in the repo mentions it by name.

## 2026-09-05

- New entry: [A clear win with almost no margin to spare](2026-09-05-h3-native-098mp-resolution-test.html) — `feature/h3-native-098mp-resolution-test` found a real, consistent quality win at 0.98MP over production's 0.5MP, but both arms peaked within a few hundred MB of this rig's actual VRAM and RAM ceilings.
- New entry: [The half we could test, and then never did](2026-09-05-h3-noturbo-50step-quality-test.html) — `feature/h3-noturbo-50step-quality-test` ruled out its BF16 half from a file-size listing alone (40.2GB vs. 24GB VRAM) and fully designed the remaining testable half per ADR-0004, then never rendered it.
- New entry: [A checkpoint this rig can stage but never load](2026-09-05-h3-fun-controlnet-union-test.html) — `feature/h3-fun-controlnet-union-test` staged three checkpoint variants but confirmed no ComfyUI-native loader exists and the documented fallback needs roughly 5x this rig's combined VRAM/RAM.
- New entry: [Slower, and not even the same shot](2026-09-05-h3-latent-upscale-speed-test.html) — `feature/h3-latent-upscale-speed-test` refuted a claimed latent-upscale speedup at N=3 (slower on every trial) and separately found that reusing a seed across the low-res/full-res split produces a genuinely different shot, not a sharper one.
- New entry: [Cut versus continuation: only one side of this comparison finished](2026-09-05-crewgroup-cut-vs-longmedia.html) — `feature/h3-crewgroup-longmedia-vs-cut-comparison`'s cut-based arm finished end to end while the LongMedia arm hit a new keyframe-anchor bug and produced no output, an asymmetric result rather than a clean head-to-head.
- New entry: [Getting one crew-group scene clean, and a collision along the way](2026-09-05-crewgroup-quality-pass.html) — `feature/h3-crewgroup-quality-pass` root-caused two shot defects to a clean assembled build, plus an honest account of two concurrent agents colliding on the same worktree and converging on a byte-identical result; sign-off is still pending.
- New entry: [OTIO plus ffmpeg concat: frame-exact video, a known audio catch](2026-09-05-otio-ffmpeg-cut-assembly.html) — `feature/otio-ffmpeg-cut-based-editing-test` proved frame-exact hard-cut assembly via real OpenTimelineIO objects and `ffmpeg concat`, with a real, understood, still-unfixed ~32ms audio DTS drift at cut boundaries.
- New entry: [Three film formats, still waiting on a verdict](2026-09-05-crewgroup-film-format-comparison.html) — `feature/film-format-comparison` built three period-format render variants; no render-result commit or verdict exists anywhere in git, matching the register's own "pending visual call" status exactly.

## 2026-09-04

- New entry: [A 30-second H3 render that took down the host](2026-09-04-h3-30s-attention-stack-oom.html) — the sibling to the LongMedia piece below: `feature/h3-30s-attention-stack-test`'s bespoke attention stack reliably OOM'd the host at ~50GB RSS during VAE decode, and neither tiled decode nor rebuilding on LongMedia survived contact with what the stack actually does.
- New entry: [A fully-specified H3 LoRA test that never actually rendered](2026-09-04-h3-bf16-turbo-lora-never-run.html) — `feature/h3-bf16-turbo-lora-quality-test` staged a complete, ready-to-submit A/B (two workflow files differing in one LoRA field) and then simply never ran it.
- New entry: [Sparse attention for H3: built, staged, never run](2026-09-04-h3-sparse-attention-validation.html) — `feature/h3-optimizations-validation` rebuilt a third-party sparse-attention kernel correctly targeted at this rig's actual GPU architecture, staged four comparison workflows, and stopped there.
- New entry: [Three rendered arms, no verdict yet: the Krea2 4-step distill LoRA](2026-09-04-krea2-4step-distill-pending.html) — `feature/krea2-4step-chk14000-distill-test` isolated a step-count/LoRA confound across three arms, but the frame-to-frame comparison that would turn them into an answer was never produced.
- New entry: [Does Krea2 Turbo actually do 16-bit JRPG game levels? Unanswered](2026-09-04-krea2-pixelart-gamelevel.html) — the clean example of this series' "does the claimed thing actually work here" category: `feature/krea2-pixelart-gamelevel-test` staged one workflow reproducing a Reddit post's prompt and never ran it.
- New entry: [The video warp wasn't the audio mask's fault](2026-09-04-h3-audio-latent-mask-video-quality.html) — `feature/h3-audio-latent-mask-video-quality-test` found the same held-frame-then-jump video artifact in both a masked arm and an untouched baseline, clearing the audio-masking technique but leaving the real cause unidentified.
- New entry: [A sampler swap that came in slower and softer](2026-09-04-h3-ersde-bongtangent-sampler.html) — `feature/h3-ersde-bongtangent-sampler-test` reproduced a Reddit-claimed sampler combination on production's own scene and got back a result about 20% slower and visibly flatter than the 6-step baseline it was supposed to beat.
- New entry: [Blocked before the six-clip chain could even run](2026-09-04-h3-motioncontext-chain-6clip-blocked.html) — `feature/h3-motioncontext-chain-6clip` never tested its own hypothesis: a monkeypatch collision between two custom-node packages breaks the chain mechanism at the very first continuation clip, independent of clip count.
- New entry: [A 30-second H3 render, blocked twice, fixed once](2026-09-04-h3-30s-longmedia-native.html) — first of a planned per-experiment deep-dive series covering the register's 12 hypothesis-bearing items. This one's the cleanest confirmed win: `feature/h3-30s-longmedia-native-test` traced a `KeyError: 'latent'` crash to an unfiltered stock keyframe list colliding with two unrelated custom-node packages' global monkeypatches, fixed it upstream, and re-ran to a confirmed 30.000s output with no OOM.

## 2026-09-03

- Both Sankeys revised to include the 12 branches merged since the August 26 survey (verified against `origin/main`'s actual PR-merge commits), routed to a new "Merged / shipped" terminal state under `Pipeline / infra`. An earlier version of the 2026-09-02 write-up deliberately left merged work out; that framing was reconsidered — shipped infrastructure is part of the same body of work, and it turns out to be the single largest band in the diagram.
- Both diagrams recolored to match the site's own parchment/ink palette instead of a stock library palette; "Blocked" now reuses the site's `--accent` red.
- Index page: added an at-a-glance Sankey of the active genops experiments (26 open, up from 25 on 2026-09-02 — adds the H3-World reproduction attempt, blocked immediately on MiniMax-H3's community license excluding the US — plus the same 12 merged branches as the full write-up). Compact view lives on the index; the full breakdown and caveats stay in the 2026-09-02 write-up.

## 2026-09-02

- New entry: [25 GPU experiments, one diagram](2026-09-02-experiments-sankey.html) — a Sankey view of the genops experiment register as of 2026-09-02: 25 items, seven work domains, five terminal states. Read alongside the per-experiment database for the audit trail; the diagram is the shape, not the confound check.

## 2026-08-29

- New entry: [Reproducing "50 tok/s at 100k context on 16GB" — and what it doesn't tell you](2026-08-29-qwen38-27b-100k-context-reproduction.html) — a LocalLLaMA benchmark claim (Qwen3.8-27B, beellama.cpp, kvarn KV-cache quant) reproduced on our RTX 3090, tok/s verified, quality caveat reported honestly.

## 2026-08-28

- First entry: [A drawing-tutorial sheet made entirely by MiniMax H3](2026-08-28-drawing-tutorial-sheet.html), on T2VA's Loomis-primitive construction-sheet experiment.
- Site scaffolded, no experiment write-ups yet.
