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
