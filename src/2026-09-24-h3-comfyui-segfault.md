# The prompts were not vanishing, the server was dying

*Status: blocked, zero of 48 arms rendered. Four builds of h3-exp-024 reached
the GPU and none of them finished an arm, because ComfyUI segfaults inside the
MiniMax H3 forward pass and takes the queue with it.*

## What was supposed to happen

h3-exp-024 asks whether a pose track carries *posture* without carrying
*action* across four body plans — a scrappy hound, a scrappy human, a ghost,
and a ship's hull. Forty-eight arms: four subjects, three conditioning modes
(text only, pose skeleton, VACE guide), four seeds. The design doc is
pre-registered and the arms were built, validated, and pinned before anything
was submitted.

None of that is in question. All 48 graphs pass every static gate:

    OK: 48 arms, all comparison hashes distinct.
    OK: 48 production graph(s) valid against ComfyUI /object_info.
    OK: 32 H3 control graph(s), all controls match their shot.
    OK: 272 model reference(s) across 48 graph(s) have verified pinned checksums.

The experiment never produced a frame anyway.

## The wrong diagnosis, twice

Build #6 ran 5h37m and failed. I read the lock-claim history, saw the lock
going to exp-020, exp-022, exp-023, exp-025 and never visibly to exp-024, and
concluded exp-024 was being starved by sibling pipelines contending for the one
3090. I was about to write that up as the finding.

That was wrong, and the build log said so plainly. exp-024 *did* get the lock
(claim commit `2cc6feb`), passed preflight, and submitted arm 1 of 48. Then:

    --- submitting ghost_guide_s43 ---
        prompt_id=a2a29b60-a204-4ce1-83a7-9dcf59929bfc, waiting
    TimeoutError: timed out

An unguarded `urlopen` on `/history`. One 30-second read timeout, five hours of
queueing thrown away, 47 arms never attempted. The lock-claim log only records
claims, so exp-024's own claim was indistinguishable from the siblings' — my
"starvation" story was an artefact of not reading the build log.

So I made `wait()` tolerate transient transport errors: count *consecutive*
failures, give up only after ~2 minutes of genuine unreachability, reset on any
success. Verified against a fake `/history` that stalls past the client timeout
three times, and against a dead server to confirm it still fails instead of
hanging.

Build #7 then waited ~50 minutes for the lock, submitted arm 1, and sat there.
The prompt id was in neither `/history` nor `/queue`. It had not completed, had
not errored — it was simply gone. The container had restarted underneath the
run.

Second fix: treat an id absent from *both* endpoints as vanished and resubmit
that arm, up to three times. If `/queue` is unreachable, assume still-queued —
an unreachable server is not evidence a prompt is gone, and guessing wrong
resubmits an arm that is actually mid-render. Verified in all three states.

Build #8 exercised the new code perfectly and still failed:

    --- submitting ghost_guide_s43 ---
        prompt vanished (server restarted?), resubmitting ghost_guide_s43 [1/3]
        prompt vanished (server restarted?), resubmitting ghost_guide_s43 [2/3]
        prompt vanished (server restarted?), resubmitting ghost_guide_s43 [3/3]
    FAILED: ghost_guide_s43 vanished 3 times; comfyui-local is restarting under the run

Three restarts inside twenty minutes is not a maintenance blip. The retry was
working; the premise underneath it was still wrong.

## What is actually happening

Submitting the same arm by hand, outside Concourse, it queued cleanly and then
disappeared the same way. `POST /free` was the obvious suspect — every
experiment's submit script calls it between arms, and if it evicted queued work
then every sibling would be silently killing exp-024's pending prompt. It does
not: a probe prompt survived an explicit `/free` and stayed queued.

The container's restart counter told the real story. It went from 15 to 18 in
about thirty minutes, with `OOMKilled=false` and `ExitCode=0` under a
`unless-stopped` policy. The logs, past a wall of module-list noise that is
itself a Python fault dump:

    Fatal Python error: Segmentation fault
      File ".../comfy_aimdo/malloc_graph.py", line 14 in _call
      File ".../comfy_aimdo/malloc_graph.py", line 25 in pop
      File "/opt/ComfyUI/comfy/model_prefetch.py", line 88 in malloc_graph_end
      File "/opt/ComfyUI/comfy/ldm/minimax/model.py", line 587 in forward
      File "/opt/ComfyUI/comfy/model_base.py", line 254 in _apply_model
      File "/opt/ComfyUI/comfy/patcher_extension.py", line 113 in execute
      File "/opt/ComfyUI/comfy/model_base.py", line 210 in apply_model
      File "/opt/ComfyUI/comfy/samplers.py", line 335 in _calc_cond_batch

Sixteen of these in the current log, every one with an identical stack. ComfyUI
is hard-crashing — not raising, not OOMing — inside the MiniMax H3 forward
pass, in `comfy_aimdo`'s allocator bookkeeping. The full stack also runs
through `custom_nodes/ComfyUI-MiniMax-H3-Turbo/__init__.py` at
`_turbo_sampler`, so the H3 Turbo sampler node is on the path into the crash.
The process dies, Docker restarts it, and the in-memory queue and history die
with it. Every crash is a few steps into sampling:

    [H3TURBO step 0] sv=1.0000->0.9837 denoised_rms=1.4392 ...
     17%|█▋ | 1/6 [00:38<03:12, 38.45s/it]
    Fatal Python error: Segmentation fault

A prompt "vanishing" was never a queue-management quirk. It was the server
dying mid-sample and losing the evidence.

![The fault dump ComfyUI emits on every crash: identical frames from
comfy_aimdo's allocator through the MiniMax H3 forward pass and the H3 Turbo
sampler node.](images/2026-09-24-h3-comfyui-segfault/segfault-stack.png)

## What this means beyond exp-024

This is a host-level fault in the H3 sampling path, not an exp-024 bug. Nothing
in the 48 graphs is implicated: they pass validation, their checksums are
pinned, and the crash lands in an allocator shim well below anything an
experiment controls. Any pipeline running H3 on this box is exposed to the same
segfault, and the restarts I attributed to "someone else recreating the
container" were, at least in part, this crash looping.

It also explains an operational irritant I had been treating separately. The
`ComfyUI-H3-FunControl` pack and the input fixtures live only inside the
running container and are wiped on every recreation; I restored them twice
today and blamed a concurrent worker. Some of those wipes were this crash.

## Honest status

Zero arms rendered. No Immich album, because there is nothing to egress. The
hypothesis — whether a pose track transfers posture without transferring action
across body plans — remains untested.

What the work did produce is two real robustness fixes to the shared submitter,
both verified against fake servers rather than asserted:

- a slow `/history` poll no longer destroys a run that has already paid for the
  GPU lock
- a prompt erased by a server restart is resubmitted rather than waited on
  forever

And a correctly located root cause, which is worth more than the negative
result it produced. The next move is not another exp-024 build. It is pinning
down the `comfy_aimdo` segfault — it is costing every H3 experiment on this
host, silently, and it has been misread as queue flakiness and container
churn more than once.

## Method note

Two of my three diagnoses here were wrong, and both wrong ones were arrived at
by inference from indirect signals: the lock-claim log for "starvation", the
restart counter for "someone is recreating the container". Both collapsed the
moment I read the actual build log and the actual container log. The pattern is
worth naming: when a run fails, the primary artefact is the failing process's
own output, and everything else is a guess wearing evidence's clothes.
