# The TTS experiment that never had a first commit

`feature/sopro-tts-experiment` is a real entry in the [experiment register](2026-09-02-experiments-sankey.html), and its honest status is that it never happened. The branch exists. It carries zero commits of its own.

## What's actually there

Its tip commit, `fab77c3`, is identical to a merge-pull-request commit that landed a completely unrelated PR (`fix/submit-error-surfacing`) into main. `git merge-base main feature/sopro-tts-experiment` resolves to that same commit: the branch's merge-base with main *is* its own tip. There is no divergence to show, because the branch never diverged: it was cut from main at some point and nothing was ever committed to it afterward.

There's no file anywhere in the repository, and no line in `docs/lab-notebook.md`, that mentions "sopro" at all. Whatever this branch was meant to test left no design doc, no workflow file, no README entry, nothing to reconstruct even a hypothesis from. The name is the entire artifact.

## Why this is worth writing down anyway

The [TTS voice-clone benchmark](2026-09-06-tts-voice-clone-benchmark-progress.html) covered above is the other TTS-tagged item in this lab's register, and it's a real, if partial, build-out: four models wired, validated, and benchmarked, ten still to go. This branch is its opposite case: a name reserved for TTS work that, as far as any commit history shows, was never started at all.

That distinction matters for the register as a whole. Not every branch that gets a name and a place in the experiment count actually produces evidence, even negative evidence. Some just mark an idea that got parked before the first commit. Recording that plainly, rather than quietly dropping the branch from the tally or guessing at what it might have been for, is the more honest option.

## Where it actually landed

**Never started.** No commits, no diff against main, no supporting documentation anywhere in the tree. This isn't a refuted hypothesis or a blocked experiment: there was never a hypothesis captured in the repository to refute or block. If TTS-related work under this name still matters, it starts from zero, not from anything recoverable here.
