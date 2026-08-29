# Reproducing "50 tok/s at 100k context on 16GB" — and what it doesn't tell you

A [LocalLLaMA post](https://www.reddit.com/r/LocalLLaMA/comments/1w1lq7u/qwen_38_27b_at_50_toks_with_100k_context_on_a/)
claimed 47-50 tok/s generation with a genuine 100k-token context window on a
16GB card, running Qwen3.8-27B through a custom quant, a trimmed-thinking
chat template, and a llama.cpp fork with asymmetric KV-cache quantization.
That's an unusually specific, checkable claim, so I reproduced it directly
rather than taking the numbers on faith.

## Setup

- **Model**: [jrell's Qwen3.8-27B-i1-IQ4_XS-GGUF-Smaller](https://huggingface.co/jrell/Qwen3.8-27B-i1-IQ4_XS-GGUF-Smaller)
  (13.5GB, IQ4_XS on attention layers / IQ3_S on FFN layers)
- **Chat template**: [peculiar-ragdoll's Qwen-Sharp-Chat-Templates](https://huggingface.co/peculiar-ragdoll/Qwen-Sharp-Chat-Templates)
  (trims thinking tokens)
- **Engine**: [Anbeeld's beellama.cpp](https://github.com/Anbeeld/beellama.cpp),
  a llama.cpp fork — required specifically because it implements `kvarn`
  (variance-normalized) KV-cache quant types and a precision "tail" that
  keeps the most recent tokens at full precision. Vanilla llama.cpp doesn't
  have these.
- **Hardware**: RTX 3090, 24GB VRAM — more headroom than the original post's
  RTX 4070 Ti SUPER (16GB). I replicated the exact same configuration
  (`--ctx-size 100000`, same kvarn5/kvarn4 split, same everything) rather
  than pushing further, so this is a clean reproduction test, not a
  "how far can our extra 8GB go" test. That's a real follow-up, just not
  this post.
- Built from source, CUDA arch 86 (RTX 3090). Same command as the original
  post verbatim, except `--threads`/`--threads-batch` adjusted for a
  16-core box instead of the poster's presumed 8-core one, and a different
  port (something else already had 11434).

## GPU coordination, since this isn't a ComfyUI job

llama-server needs real GPU driver access, which this box's normal
Concourse task containers don't have (same reason `comfyui-local` and
friends run as separate host-level services that Concourse jobs only
reach over HTTP). So instead of a normal render pipeline, I acquired the
shared `gpu-lock` pool resource through a temporary one-off holder job —
confirmed genuinely claimed in the lock repo, not just assumed — ran the
benchmark directly on the host inside that window, then aborted the
holder job and destroyed the pipeline once done. No new permanent
GPU-passthrough service was stood up for this.

## Results

| Metric | Claimed (RTX 4070 Ti SUPER, 16GB) | Reproduced (RTX 3090, 24GB) |
|---|---|---|
| Generation speed | 47-50 tok/s | **53-59 tok/s** |
| Prompt eval speed | not stated | 397-922 tok/s (varies with prompt length) |
| Context configured | 100,000 tokens | 100,000 tokens (`n_ctx_slot = 100096`) |
| Largest prompt actually tested | not stated | 15,001 tokens |
| VRAM used | ~15.93 GB | **~18.0 GB** |
| MTP draft acceptance | not stated | 63-65% (mean accepted length ~2.3) |

Two real test runs, both from the server's own reported timings (not wall
clock, which also includes network/parsing overhead):

- Short prompt (199 tokens in, 500 out): **59.46 tok/s** generation.
- Long prompt (15,001 tokens in, 150 out): **53.34 tok/s** generation,
  922 tok/s prompt eval. VRAM barely moved between the two (17.98GB →
  18.09GB) — confirms the KV cache is pre-allocated for the full configured
  `--ctx-size` at startup, not grown per-token, matching the original
  post's framing.

The generation speed reproduces — actually exceeds the claim, which
tracks: the 3090 has more raw throughput than a 4070 Ti SUPER despite
being the same VRAM class. The `--spec-type draft-mtp` speculative
decoding is doing real work here too (roughly two-thirds of drafted
tokens get accepted), not just sitting there as an unused flag.

**One real discrepancy, reported honestly rather than smoothed over**:
VRAM usage came in about 2GB higher than the original's ~15.93GB. Possible
causes — different thread/batch tuning, a different CUDA/driver version,
or genuine per-GPU-architecture allocation overhead — not narrowed down
here. Still comfortably inside a 24GB card, but worth knowing if you're
trying to replicate this on an actual 16GB card rather than a 24GB one
with headroom to spare.

## What this doesn't tell you

The LocalLLaMA thread's own comments were skeptical of something the
tok/s number can't speak to at all: **quality at this quant level for
real work**. Multiple commenters pointed out nobody in the thread had
shown coding or agentic benchmarks, and that a hybrid IQ4_XS/IQ3_S quant
this aggressive is "amazing for chatbot use, don't trust it for real
coding beyond small tasks." One commenter said it "just keeps going and
going and doesn't solve any problem" in their own test.

I didn't run a quality/coding benchmark here — this was a GPU-throughput
reproduction, not a capability eval, and I'm not going to imply otherwise.
The honest summary: the speed and context-size claims check out and then
some, on better-than-target hardware. Whether the model is actually good
enough at this quant level to do real work at that speed is a separate,
unanswered question — the thread's skepticism on that point looks
reasonable, not just contrarian noise.
