# A real, technically-verified H3 render — sitting past its own contest deadline

Another gap the [2026-09-05 full-coverage check](2026-09-05-register-full-coverage.html) missed:
it audited `blades68-lora` name-by-name and `T2VA` for all but one branch
(`stock-turbo-lora-baseline`, entered as Blocked). `T2VA`'s `feature/h3-sync-sound-challenge` was
the second miss — real work, no write-up, and a time-sensitive detail nobody had flagged: its
target deadline is now five days gone.

## What it was for

Gavin flagged the official Comfy H3 Sync Sound Community Challenge
([blog.comfy.org](https://blog.comfy.org/p/comfy-h3-sync-sound-community-challenge), checked
against the primary post directly), deadline **2026-09-01**. Hard rule from the post itself: audio
must be generated natively by H3 in the same pass, no post-hoc stitching. `T2VA` already had a
production graph (`build_t2va_prompt.py`) exercising H3's audio-capable
`MiniMaxH3ReferenceToVideo` path — confirmed for real (non-silent) audio via `ffprobe` on an
existing production render before this branch even started. The entry itself: a short Raven
tactical vignette (turn, weapon-ready foley beat, one line of dialogue) built via a new
`build_sync_sound_prompt.py`, parameterizing clip length instead of production's fixed 107 frames.

## What actually ran

v1 dispatched through Concourse's isolated `t2va-sync-sound-challenge` pipeline (build 1,
succeeded 2026-08-27, 22m26s). Technical verification followed 2026-08-28, pulled from the actual
`comfyui-local` output file rather than a claimed status line:

- h264, 480x864, 158 frames / 6.583s — exact match to the spec's own length target
- Real stereo AAC audio, 32kHz, mean -20.1dB / max -0.5dB: non-silent, not clipped
- Confirmed live in Immich (album "Esoteria T2VA Character Sheets", asset `28602f82-...`)

Every automatable check passes. What's explicitly *not* automated, per the branch's own
`EXPERIMENT.md`: whether the footstep/turn sound actually lands on the pivot motion, whether the
weapon-lock sound lands on the weapon reaching ready position, and whether the dialogue line's
mouth movement reads as lip-synced. That's Gavin's call by design, not a gap in the harness.

## The part nobody flagged

That qualitative review never happened — the branch's last substantive commit is the 2026-08-28
verification log. Checked directly rather than assumed: no commit anywhere in this branch's history
or `T2VA`'s broader log mentions "submit" or "challenge" past that date, and the contest's own
2026-09-01 deadline is five days behind today. Whether Comfy's own submission process needed
something beyond "render exists in Immich" (a form, a forum post, an upload) isn't something this
repo's history can answer — but if it did, that window has closed with a technically-sound entry
sitting unsubmitted and unreviewed.

**Verdict: Pending, and now moot on the original timeline.** The render itself remains a real,
verified data point on H3 native audio-sync feasibility regardless of contest outcome — it's the
"did we actually enter" question that lapsed silently.
