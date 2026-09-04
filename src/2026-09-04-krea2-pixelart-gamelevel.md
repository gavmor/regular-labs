# Does Krea2 Turbo actually do 16-bit JRPG game levels? Unanswered

This one belongs to a different category than most of the
[experiment register](2026-09-02-experiments-sankey.html): not a formal
hypothesis test with dependent variables, but a straight "does this claimed
trick actually work on this rig" reproduction attempt, the kind this site
will keep coming back to. Item #18: `feature/krea2-pixelart-gamelevel-test`.
The honest answer, as of this write-up, is that nobody ever looked.

## What was being reproduced

A r/StableDiffusion post (thread ID `1vtdr3l`) claimed Krea 2 Turbo produces
high-quality 16-bit pixel-art JRPG game-level scenes out of the box, no LoRA
needed, purely from prompt structure: dense stairs/bridges/stacked-building
architecture, a named art style, and explicit camera framing. The claim
under test is narrow and specific: that a hand- or LLM-crafted, already-
detailed prompt works close to verbatim, not whether this pipeline's own
prompt-refinement stage could also arrive at the same result on its own.

## What was actually built

The single commit on this branch (`6a48b21`, 2026-08-20) adds one workflow
file, `workflows/krea2_pixelart_gamelevel_test.api.json`: the original
poster's first verbatim prompt (a victorian steampunk winter riverside
city) swapped into the user-prompt node, no LoRA attached (already this
pipeline's default), and internal prompt-refinement explicitly turned off
so the posted prompt reaches CLIP unmodified rather than getting rewritten
by this project's own refiner first.

That's the entire branch. No second commit, no render submission, no
output file, no note about a build being queued or blocked. The workflow
that would test the claim exists and is committed; it was never actually
run through this rig's Concourse pipeline.

## What's not yet answered

Everything the original hypothesis is actually about: whether Krea2 Turbo,
on this hardware and this pipeline's exact node graph, reproduces
anything close to the Reddit post's claimed 16-bit JRPG game-level look
from that prompt alone. No image exists in this lab's output archive under
this branch's name, and nothing in the repo's own lab notebook mentions
this experiment past the initial commit. There's no comparison to fail or
pass here, because there's no output to look at.

## Where it actually landed

No verdict, and unlike some of the register's "no verdict" entries, this
one isn't even a partial result with an open question left over, it's a
single staged workflow file and nothing else. If this is worth revisiting,
the next step is exactly the one that never happened: push the branch,
let the render run, and actually look at what comes back against the
original post's screenshots.
