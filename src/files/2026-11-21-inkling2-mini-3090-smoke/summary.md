# Inkling 2 Mini smoke — RESULT

verdict: **pass**
reason: all checks passed

| measurement | value |
| :-- | :-- |
| model | `Inkling-2-Mini-UD-Q4_K_XL.gguf` (16.42 GiB) |
| runtime | llama.cpp `b12588-mix-c0c3de8` linux-x64-cuda12-portable |
| GPU | NVIDIA GeForce RTX 3090 (24576 MiB, driver 595.99.02) |
| load time | 6.5 s |
| new tokens | 320 |
| tok/s (runtime) | 51.18 |
| tok/s (wall incl. overhead) | 47.55 |
| prompt eval | 44 tokens in 0.49 s |
| peak VRAM | 18952 MiB (+17283 MiB over idle) |
| peak GPU util | 88% |
| Ollama arm | error |

## Prompt

> In two sentences, explain why a graphics card's memory bandwidth matters more than its raw FLOPs when generating tokens from a large language model.

## Generated text

channel: `content`

```
During autoregressive decoding, each new token mostly requires streaming the model weights and KV cache from GPU memory rather than doing dense arithmetic, so arithmetic intensity is low and compute units sit idle. Consequently, tokens/sec is capped by memory bandwidth and capacity, while raw FLOPs mainly help compute-bound phases like prefill and training, not single-
```

## Reasoning channel (if any)

```
The user asks: "In two sentences, explain why a graphics card's memory bandwidth matters more than its raw FLOPs when generating tokens from a large language model."

Need answer in two sentences. Need explain: token generation is memory-bound autoregressive decoding; each token requires reading model weights/KV cache from memory, arithmetic intensity low, so FLOPs underutilized. Raw FLOPs matter for training/prefill compute-heavy phases, but decode is limited by bandwidth to fetch weights/KV. Need concise two sentences. Ensure exactly two sentences. Could mention batch size caveat? They ask why matters more. Keep two sentences.

Need final only. No extra. Ensure two sentences exactly. Sentence 1: During autoregressive decoding, each new token mostly requires streaming the model weights and KV cache from GPU memory rather than doing dense arithmetic, so arithmetic intensity is low and compute units sit idle. Sentence 2: Consequently, tokens/sec is capped by memory bandwidth (and capacity), while raw FLOPs mainly help compute-bound phases like prefill/training, not single-token generation. That's two sentences. Good.
```
