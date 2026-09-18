# TEMPLATE — Lab Report

Copy this to `src/YYYY-MM-DD-slug.md` and fill it in. Not for journal entries,
which live in `src/journal/` and follow no template — a journal entry may
narrate freely, in past tense, with dead ends and dates.

A report is the opposite. **It is written as though the methodology had been
correct from the start.** Every section below describes what the experiment
*is*, in present tense. Nothing in a report records the order in which you
figured things out, and nothing tallies your own retractions. Git holds that
history; a reader looking for it will run `git log -p`.

---

## Voice rules

**Present tense throughout.** "The floor is 63.94", not "I measured the floor
at 63.94 and then realised". The finding exists independently of the afternoon
that produced it.

**No self-narration about sequence.** Cut every instance of: *"I originally
read that as…"*, *"where I got it wrong"*, *"it took a later question before I
worked out…"*, *"the conclusion I first drew was too strong"*. Within ~36 hours
of publication there is nothing to correct — almost nobody read the earlier
text, so narrating its errors informs no one and costs the finding its
authority.

**No retraction tallies.** Do not motivate a choice by citing your own past
mistakes. "Single-render results in this line have a poor track record against
replication" does the same work as "…and two claims in this session had to be
retracted", without the confessional.

**Corrections are edited in place.** Never append an errata section. It
duplicates the git log and grows without bound while the finding stays the same
size.

**Three things that look like self-criticism but belong in a report:**

- **Superseded designs**, in Method — they explain why the final design is
  *necessary*. "The round trip is confounded and the contradiction arm is
  incoherent by construction" is design rationale, not apology.
- **Failed builds**, in Cost, with causes — real constraints for a reader on
  the same hardware.
- **Limitations** — what the result does not support. Non-negotiable.

The test for any sentence: *does this teach the reader about the subject, or
only about my previous mistakes?* Keep the first; delete the second.

---

## Structure

```markdown
# <Title: the finding, not the activity>

*Status: <complete | falsified | smoke-tested, N=1>. <One sentence: what was
measured against what, and the headline result.>*

## The question

Where it came from — a forum post, a decision that needs making, an upstream
claim. Quote the original wording if there is one. If answering a public
question, say so and credit any replies that already held part of the answer.

## Method

What varies, what is held, and why this design can answer the question when a
simpler one cannot. Name the arms. State N.

Include the **null**: what the measurement reads if the effect is absent,
measured in the same units and configuration as the claim — never borrowed from
another run. If the instrument has its own repeatability floor, state it and
say how it was validated.

State the decision rule *before* the results, including its indeterminate
branch.

## Results

Numbers first, in a table, with the null alongside them. Then the figure — a
chart or frame grid a reader can check the claim against. Plot every
measurement rather than only means.

## <What it means / Who was right>

Read the numbers out. If the work settles a disagreement, name who was right
about what; that is more honest and more persuasive than declaring a winner.

## What this does not settle

Scope limits, deliberate exclusions, and the obvious next experiment. An
honest limitations section is what lets a reader trust the rest.

## Cost

Three numbers, measured not estimated:

- **Render/compute time as a ratio to output** — "855s for 12.25s of video =
  ~70× real-time", then translate: "a twelve-second shot is a fifteen-minute
  wait".
- **Peak memory against capacity** — "20.0 GiB / 83% of a 24 GB card".
- **Calendar time from the original ask**, not active-work hours. Recover the
  ask from conversation history; git timestamps start after it. Report the
  active-build span too, but lead with calendar — that is the number people
  actually want and nobody publishes.

Failed and wasted builds belong here with their causes.

## Files

Workflows, data, scripts. If the graphs are API-format or name local
checkpoints, say so plainly rather than implying drag-and-drop.
```

---

## Before publishing

- [ ] Every claim in the prose matches the figure it sits next to — counts,
      labels, axis units. Count *arms* and *variants* separately and say which.
- [ ] `pnpm run build` clean; internal links and assets resolve; entry appears
      in `feed.xml`
- [ ] Listed under `## Reports` in `src/index.md` (journal entries go under
      `## Journal` and live in `src/journal/`)
- [ ] No present-tense violations, no sequence narration, no retraction tally
- [ ] Limitations section says what the result does *not* support
- [ ] Cost includes calendar time from the ask
