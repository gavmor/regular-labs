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

## 2026-09-04

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
