# A second, independent cause of H3's gibberish-audio bug — found, not yet deployed

Found during routine grooming, not a self-reported branch: `feature/h3-gibberish-audio-tokenizer-fix`
landed its one commit (`94f7adb`) right around when the [2026-09-05 full-coverage
check](2026-09-05-register-full-coverage.html) was being compiled, and its Concourse build
(`run-changed-workflows/1`, succeeded 2026-09-05 14:11-14:12) came in just after — the kind of
timing gap full coverage of *write-ups* can't fully close, same caveat that post itself named.

## What it's answering

Reddit, Hugging Face, and GitHub reports describe gibberish or clipped audio in the first ~0.5s of
MiniMax H3 clips. This project already shipped one fix at the prompt layer —
`tools/minimax-prompt-builder`'s `<d>...</d>` "full-discipline" structure, reconfirmed seed-stable
in [the seed-consistency write-up above](2026-09-06-prompt-builder-seed-consistency-unverified.html).
This branch was tasked with four follow-ups: bump ComfyUI, verify `<d>`/`</d>` tokenize atomically,
check the official audio-sample-length spec, and record aspect-ratio/seed effects.

## The real finding: a second bug, one layer lower

Item 2 turned up something independent of prompt discipline entirely:
[Comfy-Org/ComfyUI#15808](https://github.com/Comfy-Org/ComfyUI/pull/15808) (merged 2026-08-22,
authored by `kijai`) fixes seven MiniMax-H3 tokenizer special tokens (`<d>`, `</d>`,
`<|cutoff|>`, `<|lyrics_start|>`, `<|lyrics_end|>`, `<|caption_start|>`, `<|caption_end|>`) that
were declared only in `tokenizer_config.json` and never registered as atomic tokens in
`comfy/text_encoders/minimax.py` — meaning `<d>` itself could get split into sub-word pieces by the
underlying tokenizer, independent of how carefully the surrounding prompt is written.

Checked directly against this rig's own deployment, not taken on the strength of the upstream
report:

```
$ docker exec comfyui-local sh -c 'cd /opt/ComfyUI && git log -1 --format="%H %ci %s"'
fe4195f7f4275f2626cbafc703acc3ddde1e5490 2026-08-08 05:04:30 +0000 ComfyUI v0.31.1

$ docker exec comfyui-local grep -n "additional_special_tokens\|<d>\|lyrics_start\|caption_start" /opt/ComfyUI/comfy/text_encoders/minimax.py
NOT FOUND in minimax.py
```

`comfyui-local` is pinned to `v0.31.1` (`fe4195f`, 2026-08-08) — two weeks before #15808 merged.
**The fix is confirmed absent from the live file.** This also explains why community reports
describe the bug as seed-dependent even when `<d>`/`</d>` syntax is written correctly: a
tokenizer-level miss isn't something prompt discipline alone fully papers over.

## Status: staged, not deployed

The fix (bump `v0.31.1` → `v0.34.0`, the smallest tag that includes #15808 while carrying forward
`v0.31.1`'s own justification for Wan-Animate-2 support) is staged on a separate branch of the
`comfyui-local` repo itself — `feature/bump-v0.34.0-h3-tokens-fix`, commit `bc54e4a` — pushed but
**not built or deployed**. Deliberately: `comfyui-local` is this rig's shared, currently-healthy
render host, used across roughly fifty concurrently-active branches, and ~10 pinned custom nodes
depend on ComfyUI internals a 3-minor-version jump can change. That's a rebuild-plus-compatibility-
smoke-test-plus-cutover, not a swap to make unilaterally during a grooming pass — left as a
named follow-up for Gavin or an explicitly-scoped task with a rollback plan.

The other two items came back clean: the official audio-sample-length spec (≤3 clips, 2-15s each,
≤15s total) turns out to not currently apply anywhere in `blades68-lora` or `T2VA` — neither repo
has a workflow feeding H3 reference *audio* (as opposed to reference images); all dialogue is
generated fresh from `<d>...</d>` text. Aspect-ratio effects on the bug: no data internal or
external, correctly left open rather than guessed at.

**Verdict: Pending.** Root cause identified and confirmed against this rig's own deployment; fix
identified and staged; not yet built, deployed, or re-tested. Aspect-ratio effects remain an open
question flagged for its own controlled `feature/*` branch, not folded in here after the fact.
