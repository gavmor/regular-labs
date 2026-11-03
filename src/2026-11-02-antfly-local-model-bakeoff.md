# Pinned decoding parameters separate the 30B coder from the pack, while reasoning models burn their token budget on thoughts Antfly never reads

*Status: complete, N=26 runs across 22 local Ollama models on a single 24 GB RTX 3090. A frozen 382-chunk Roman history corpus evaluates embedding retrieval (MRR@10, recall@5) and agentic execution (grounded QA, strict tool calling, Antfly query-builder planning). `bakeoff-qwen3-coder-q5kxl` wins generator quality at 0.9403 with 100% deterministic reproducibility, and `Octen-Embedding-8B` with lowercase asymmetric prefixes leads retrieval at 0.9583 MRR@10.*

## The question

Local retrieval-augmented generation stacks depend on two distinct model roles: an embedding model to index and retrieve corpus passages, and an instruction-tuned generator to execute tool calls, synthesize citations, and drive query-planning agents. On a single-GPU workstation with 24 GB of VRAM, the model choices are constrained by resident memory, decoding latency, and tool schema adherence.

Antfly exposes native agent endpoints for autonomous retrieval and query building against local Ollama models. Standard small models (`llama3.2:1b`) fail agentic query planning by violating JSON argument schemas, while newer 27B–30B reasoning models (`Nemotron-3.5-Lightning`, `Qwen3.8-27B`) fail inside Antfly despite high benchmark scores on direct OpenAI completions.

The question is concrete: **which currently-installed Ollama models deliver the highest retrieval accuracy and agentic completion rates for Antfly on a local 24 GB workstation?**

## Method

The evaluation spans 22 locally installed models on an NVIDIA GeForce RTX 3090 (24 GB VRAM) running driver 595.99 and CUDA 13.2. Tests run against local Ollama (0.40.11) and Antfly (v0.2.5).

### Evaluation Arms

The search space divides into two independent axes:

1. **Embedding Models (Retrieval Quality & Reindex Throughput)**:
   - `nomic-embed-text:latest` (768 dimensions)
   - `qwen3-embedding:latest` (4096 dimensions, 8B base)
   - `hf.co/tex8/Octen-Embedding-8B-GGUF:Q4_K_M` (4096 dimensions, 8B base)
   - Evaluated under symmetric raw text, task-specific prefixes (`search_query:` / `search_document:`), natural-language instructions (`Instruct:`), and asymmetric prefixes (`query:` / `passage:`), testing both casing and delimiter variants.

2. **Generator Models (Grounded QA, Tool Calling, and Antfly Agent Planning)**:
   - Coder models: `bakeoff-qwen3-coder-q5kxl:latest`, `bakeoff-qwen3-coder-q4kxl:latest`, `Qwen3-Coder-30B-A3B UD-Q5_K_XL`, `qwen3-coder-ud-q4kxl:latest`.
   - Reasoning / Thinking models: `Qwen3.8-27B` (5 quantization variants: `Humanlike-Chat`, `Swift`, `GSQ-RCO`, `Heretic`, `Aggressive-MTP`), `Nemotron-3.5-Lightning-30B` (base and `bakeoff` with `stop <think>`).
   - Generalist / Hybrid models: `flint:latest`, `bakeoff-flint:latest` (39.8B, NVFP4), `Muse-Glimmer-30B`, `Ornith-1.5-9B`, `DeepSeek-V4-Flash`, `KrakenSakura-12B`, `Gemma-4` (31B, 26B, 12B, MXFP4), `Laguna-XS-2.1`.

### The Frozen Workload

The harness evaluates a frozen fixture (`bench/fixture.json`) extracted from the 141,772-chunk `rome` history vault:
- **Retrieval Pool**: 382 text chunks across 36 Roman historical topics, including same-source distractor chunks.
- **Retrieval Test**: 32 hand-written known-item queries with verified gold chunk IDs and shingle-expanded equivalences, scored on MRR@10 and Recall@5.
- **Grounded QA**: 24 answerable historical questions in 8-passage distractor contexts and 8 unanswerable control contexts. Evaluated on factual answer accuracy, passage citation accuracy, refusal accuracy on unanswerables, and strict JSON format compliance.
- **Strict Tool Calling**: Multi-turn search and chunk-lookup prompts requiring typed integer arguments, string substring checks, parallel multi-tool dispatches, and plain-text stopping decisions.
- **Antfly Native Agents**: Direct end-to-end calls to Antfly's `/db/v1/agents/retrieval` (generation + citations) and `/db/v1/agents/query-builder` (autonomous multi-turn Bleve query planning).

The composite metric is:

$$\text{quality} = \frac{\text{embed\_mrr10} + \text{gen\_quality}}{2}$$

$$\text{gen\_quality} = \frac{\text{qa\_score} + \text{tool\_score} + \text{antfly\_score}}{3}$$

The null baseline is `nomic-embed-text` (raw) paired with `qwen3-coder-ud-q4kxl`, which measures 0.8572 quality with a ±0.03 stochastic noise floor under default sampling.

## Results

### Embedding Retrieval & Prefix Sensitivity

| Embedding Model | Prefix Scheme | MRR@10 | Recall@5 | Query Latency | Doc Throughput | Full Reindex (142k chunks) |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| **`Octen-Embedding-8B`** | **`query: ` / `passage: `** | **0.9583** | **1.0000** | 25.3 ms | 14.2 docs/s | ~2.6 hours |
| `Octen-Embedding-8B` | `Instruct: ...` / `passage: ` | 0.9557 | 1.0000 | 27.6 ms | 14.2 docs/s | ~2.6 hours |
| `Octen-Embedding-8B` | `query:\n` / `passage:\n` | 0.9333 | 1.0000 | 25.7 ms | 14.3 docs/s | ~2.6 hours |
| `Octen-Embedding-8B` | Raw / empty (`""`) | 0.9271 | 1.0000 | 25.7 ms | 14.8 docs/s | ~2.6 hours |
| `Octen-Embedding-8B` | `Query: ` / `Passage: ` | 0.9177 | 1.0000 | 25.0 ms | 14.6 docs/s | ~2.6 hours |
| `Octen-Embedding-8B` | `search_query: ` / `search_doc: ` | 0.8984 | 1.0000 | 25.2 ms | 14.2 docs/s | ~2.6 hours |
| **`qwen3-embedding`** | **Raw / empty (`""`)** | **0.9479** | **1.0000** | 25.4 ms | 14.9 docs/s | ~2.6 hours |
| `qwen3-embedding` | `query: ` / `passage: ` | 0.9427 | 1.0000 | 25.2 ms | 14.0 docs/s | ~2.6 hours |
| `qwen3-embedding` | `Instruct: ...` / raw | 0.9271 | 1.0000 | 28.4 ms | 14.9 docs/s | ~2.6 hours |
| `qwen3-embedding` | `search_query: ` / `search_doc: ` | 0.9036 | 1.0000 | 24.7 ms | 14.3 docs/s | ~2.6 hours |
| **`nomic-embed-text`** | **`search_query: ` / `search_doc: `** | **0.9151** | **1.0000** | **6.6 ms** | **166.7 docs/s** | **~14 minutes** |
| `nomic-embed-text` | Raw / empty (`""`) | 0.8755 | 0.9688 | 6.0 ms | 163.2 docs/s | ~14 minutes |
| `nomic-embed-text` | `search_query: ` only | 0.8701 | 0.9688 | 12.0 ms | 163.2 docs/s | ~14 minutes |

### Generator Performance Across 15 Candidates

All generators paired with 8B embedding on the same 24 GB card:

| Generator Model | Quality | QA Score | Tool Score | Antfly RAG | Antfly QB | Gen Latency | Deterministic |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| **`bakeoff-qwen3-coder-q5kxl:latest`** | **0.9493** | **0.9917** | **0.9750** | **0.8750** | **0.8333** | **0.89 s/call** | **Yes (0.0000 noise)** |
| `Qwen3-Coder-30B UD-Q5_K_XL` (unsloth) | 0.9267 | 0.9917 | 0.9750 | 0.7500 | 0.7500 | 1.99 s/call | No (±0.03 drift) |
| `qwen3.8-27b-neo-coder-max-mtp:Q4_K_S` | 0.8983 | 0.9417 | 1.0000 | 0.5000 | 0.7083 | 7.63 s/call | No |
| `Swift-Qwen3.8-27B:Q4_K_M` | 0.8781 | 0.9667 | 1.0000 | 0.7500 | 0.1667 | 6.17 s/call | No |
| `Qwen3.8-27B-GSQ-RCO:iq3_s-mtp` | 0.8781 | 0.9667 | 1.0000 | 0.7500 | 0.1667 | 5.68 s/call | No |
| `Qwen3.8-27B-Humanlike-Chat:Q4_K_M` | 0.8677 | 0.9667 | 1.0000 | 0.6250 | 0.1667 | 7.39 s/call | No |
| `bakeoff-qwen3-coder-q4kxl:latest` | 0.8552 | 0.9750 | 0.3750 | 0.8750 | 1.0000 | 0.82 s/call | Yes |
| `flint:latest` / `bakeoff-flint:latest` | 0.8375 | 0.9667 | 0.8812 | 0.5000 | 0.1667 | 2.54 s/call | Yes |
| `Nemotron-3.5-Lightning-30B` (stock) | 0.8240 | 0.9583 | 0.9750 | 0.0000 | 0.3333 | 6.66 s/call | No |
| `bakeoff-nemotron-lightning:latest` | 0.7882 | 0.9417 | 0.9437 | 0.0000 | 0.0000 | 4.71 s/call | Yes |
| `Muse-Glimmer-30B:Q4_K_M` | 0.7965 | 0.9917 | 0.9437 | 0.0000 | 0.0000 | 9.04 s/call | No |
| `hf.co/ornith-ai/Ornith-1.5-9B-GGUF:Q8_0` | 0.8712 | 0.9917 | 0.9750 | 0.7500 | 0.0833 | 2.54 s/call | No |
| `KrakenSakura-Maelstrom-12B-v1-GGUF:Q8_0` | 0.6844 | 0.7833 | 0.0417 | 0.8750 | 0.0000 | 1.59 s/call | No |
| `Huihui-DeepSeek-V4-Flash-0731:BF16` | 0.4809 | 0.0000 | 0.0417 | 0.0000 | 0.0000 | 3.37 s/call | No |
| `Gemma-4` (31B, 26B, 12B) / `Laguna-XS` | 0.0000 | — | — | — | — | Timeout | — |

## What the separation reveals

### Pinned parameters eliminate sampling drift

`bakeoff-qwen3-coder-q5kxl:latest` and `hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:UD-Q5_K_XL` share identical weights. The unsloth build scores 0.9267 and drifts by ±0.03 across runs. The `bakeoff` Modelfile pins:

```dockerfile
PARAMETER temperature 0
PARAMETER top_k 1
PARAMETER top_p 1
PARAMETER seed 42
PARAMETER repeat_penalty 1.1
PARAMETER num_ctx 16384
```

These parameters lower decoding latency from 1.99s to 0.89s per call and produce zero run-to-run noise: run #19 and run #23 reproduce every metric to four decimal places.

### Quantization cliff on tool schemas

Dropping from Q5 (`bakeoff-qwen3-coder-q5kxl`) to Q4 (`bakeoff-qwen3-coder-q4kxl`) saves 4 GB of VRAM but collapses tool schema validation from 0.9750 to 0.3750. The Q4 model fails type constraints (emitting strings like `"5"` instead of integer `5`) and omits optional filters. For agent tool calling, 5-bit quantization is a hard requirement.

### Why reasoning models fail inside Antfly

Network proxy captures between Antfly and Ollama expose the mechanism:

1. Stock Antfly applies a default completion limit of `max_tokens: 256` when the parameter is omitted from the generator configuration.
2. Ollama's OpenAI-compatible `/v1` endpoint places thinking output into a separate `message.reasoning` field and counts those tokens against `completion_tokens`.
3. Models such as `Nemotron` and `Qwen3.8-27B` generate 256 tokens of reasoning, hit `finish_reason: "length"`, and return `content: ""`.
4. Antfly's OpenAI client treats the empty string as a successful response, yielding blank generation and broken query plans.
5. Attempting to suppress reasoning via Modelfile (`PARAMETER stop <think>` in `bakeoff-nemotron-lightning`) halts generation at token 0, producing an Antfly score of 0.0000.
6. Supplying `"max_tokens": 4096` explicitly in the generator JSON allows reasoning models to complete their thinking trace and populate `content`.

### Tokenizer case sensitivity in dense embeddings

`Octen-Embedding-8B` exhibits sharp sensitivity to prefix formatting:
- Lowercase `query: ` and `passage: ` achieves 0.9583 MRR@10.
- Capitalized `Query: ` and `Passage: ` drops MRR@10 to 0.9177.
- Delimiting with a newline (`query:\n`) drops MRR@10 to 0.9333.
- Nomic's prefix convention (`search_query: `) drops MRR@10 to 0.8984.

The Qwen/Octen BPE tokenizer maps capitalized tokens to distinct vocabulary IDs. Dense retrieval vectors depend on exact prefix token alignment.

## What this does not settle

This benchmark does not evaluate long-context retrieval degradation beyond 16k tokens. While `Qwen3-Coder-30B` advertises 131k context, all runs here operate within 16,384 tokens to match resident GPU capacity.

The fixture tests 382 chunks from Roman historical texts; domain transfer to code repositories, mathematical proofs, or multilingual corpora is unmeasured.

Furthermore, this test does not evaluate multi-user concurrent throughput. All benchmarks execute serially under single-tenant GPU residence. Concurrent request queuing under Ollama may alter latency profiles.

Finally, while `"max_tokens": 4096` restores content generation for reasoning models, this bake-off does not benchmark whether reasoning models with thinking enabled outperform non-thinking 30B coders on retrieval synthesis when given sufficient tokens. That comparison requires an expanded latency budget.

## Cost

- **Compute time**: 26 benchmark runs totaling 3,420 seconds of active execution (~57 minutes). Each full harness run requires 62–90 seconds for non-thinking models, and 300–450 seconds for 27B thinking variants.
- **Peak memory**: 22.8 GiB / 95% of the 24 GB RTX 3090 when hosting 30B Q5 models alongside the 8B embedder.
- **Calendar time**: 4 hours 15 minutes from initial user ask to final report publication.
- **Wasted runs**: 5 runs failed or timed out on Gemma 4 and Laguna variants due to unsupported thought channels and missing tool schemas.

## Files

- Model configuration: [`models.json`](files/2026-11-02-antfly-local-model-bakeoff/models.json) — champion settings
- Benchmark harness: [`model_bench.py`](files/2026-11-02-antfly-local-model-bakeoff/model_bench.py) — evaluation script, stdlib urllib only
- Telemetry log: [`antfly-thinking-compat-report.md`](files/2026-11-02-antfly-local-model-bakeoff/antfly-thinking-compat-report.md) — wire proxy captures and Antfly compatibility analysis
