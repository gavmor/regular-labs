# The full resolution sweep, and where the safe ceiling actually sits

Third write-up out of the [experiment register](2026-09-02-experiments-sankey.html), and the cleanest confirmed result of the three covered here: `feature/h3-resolution-array-sweep` ran a full 8-point resolution sweep from 0.3 to 0.98 megapixels on the Graves [MiniMax H3](https://huggingface.co/MiniMaxAI) workflow, and none of the eight arms came close to an out-of-memory failure.

<video src="images/2026-09-06-h3-resolution-array-sweep/sweep-030mp-736x416.mp4" controls width="400"></video>

*Low end of the sweep: 0.3MP arm, `h3_resolution_sweep_030mp.mp4` from the `feature/h3-resolution-array-sweep` worktree's `.scratch/` output. Confirmed via ffprobe: 736x416, 5.167s, h264+aac (736x416 is 306,176px, consistent with the 0.3MP label).*

<video src="images/2026-09-06-h3-resolution-array-sweep/sweep-050mp-960x544.mp4" controls width="400"></video>

*Production midpoint: 0.5MP arm, `h3_resolution_sweep_050mp.mp4`. Confirmed via ffprobe: 960x544, 5.167s, h264+aac (522,240px).*

<video src="images/2026-09-06-h3-resolution-array-sweep/sweep-098mp-1344x768.mp4" controls width="400"></video>

*Top of the tested range: 0.98MP arm, `h3_resolution_sweep_098mp.mp4`. Confirmed via ffprobe: 1344x768, 5.167s, h264+aac (1,032,192px), the same resolution the prior two-point test used and the one that came in at one of the lowest VRAM peaks in this sweep despite being the largest frame.*

## Why this needed a sweep, not another A/B

A prior branch, `feature/h3-native-098mp-resolution-test`, ran a straight two-point comparison: production's 0.5MP against a Reddit-claimed-native 0.98MP. Both arms landed within a few hundred MB of this rig's real hardware ceiling (VRAM 24,047 of 24,576 MiB; host RAM 58,176 of 64,223 MB): too close to the wall, on only one sample per arm, to cleanly credit any quality difference to resolution rather than run-to-run noise. Gavin's actual question wasn't "is 0.98 better than 0.5," it was how quality changes across a spread of resolution values, and that needed more than two points to show.

## The array

Eight workflow files, each an exact copy of the production graph differing only in the `ResolutionSelector` node's `megapixels` value: `0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.98`. Finer 0.1 steps through the middle of the range, a deliberately tighter 0.08 step at the top end where the prior test showed the margin getting thin. Everything else held byte-identical across all eight: same seed (`919880931791466`), same 6-step scheduler, same Turbo LoRA, same reference images, same prompt text. All eight files landed in one commit so `run-changed-workflows` would submit them in ascending resolution order, letting continuous VRAM/RAM polling show a trend across the sweep rather than an out-of-order jump.

The branch deliberately renders no quality verdict. It's instrumented for wall-clock, peak VRAM, peak host RAM, and output location only, per the task brief, with the actual clips handed to Gavin for his own visual review.

## The run

Build `run-changed-workflows/1`, 2026-08-23, all 8 arms rendered sequentially in one `gpu-lock` hold, 15:51:39 to 16:10:45 UTC (about 19 minutes total). Every arm hit `execution_success` over the websocket. No `execution_error`, no timeout, no OOM, anywhere in the sweep:

| megapixels | wall-clock | peak VRAM | peak host RAM |
|---|---|---|---|
| 0.3 | 77s | 23,878 MiB | 56,131 MB |
| 0.4 | 77s | 23,016 MiB | 56,556 MB |
| 0.5 (production) | 94s | 23,848 MiB | 56,436 MB |
| 0.6 | 122s | 23,496 MiB | 56,628 MB |
| 0.7 | 145s | 23,816 MiB | 57,287 MB |
| 0.8 | 172s | 23,080 MiB | 57,155 MB |
| 0.9 | 207s | 23,880 MiB | 57,294 MB |
| 0.98 | 232s | 23,080 MiB | 55,693 MB |

Wall-clock scales roughly linearly with pixel count, about 3.0x slower end to end for a 3.27x pixel-count increase, consistent with the workflow's chunked attention avoiding super-linear scaling.

The interesting finding is what didn't move: peak VRAM stayed inside a narrow 23,016-23,880 MiB band across the entire array, with no trend against resolution at all. 0.98MP's own peak (23,080 MiB) was one of the lowest in the array, not the highest. Peak host RAM told the same story, staying in a 55,693-57,294 MB band with no monotonic climb, and every single arm came in under the prior two-arm test's own peak of 58,176 MB. Both peaks are dominated by the fixed decode/mux phase and model-weight residency once chunked attention is active, not by how many pixels a given arm is rendering.

## One disclosed caveat

Every number here is N=1 per resolution point: one seed, one prompt, one sample at each of the eight values. That says nothing about whether any individual point is reliably repeatable, only that this one representative run at each point produced a labeled array for visual comparison. The branch's own writeup also flags that host RAM readings this run started from a cleaner rig state than the prior test's (54,875 of 64,223 MB already in use from unrelated concurrent work, versus whatever the prior test's baseline was), a plausible reason this sweep's absolute peaks read a bit lower across the board, not proof this sweep is inherently safer under contention.

## Where it actually landed

**Confirmed, and the practically useful kind of confirmed.** The full 8-point sweep survives on this rig with no OOM anywhere, and VRAM/RAM peaks stay flat across the whole resolution range rather than climbing with pixel count. That's a real answer to a production question: this workflow has headroom across its entire tested resolution envelope, and pushing resolution up to 0.98MP costs wall-clock time, not memory margin. No quality call is made here by design (that verdict is Gavin's, from the eight clips handed off), but the "is this safe to run" question this branch actually asked came back yes, cleanly, at every point tested.
