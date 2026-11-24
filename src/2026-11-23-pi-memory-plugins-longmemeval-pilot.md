# Every Pi memory extension lifts local readers from 16% to 50–66% on a LongMemEval-S pilot, and the choice of reader barely moves the score

*Status: complete pilot, N=14 questions × 4 memory arms × 5 local readers = 280 graded answers. Against memory snapshots written by one fixed model, pi-mem answers 46 of 70 pooled questions, pi-memory 36, pi-mem0 35, and no memory at all 11. Every extension beats no memory with every reader; the order among the extensions is indeterminate at this size, and within any one memory arm the five readers differ by at most two questions.*

## The question

Pi, the terminal coding agent, has no long-term memory of its own; it gets one from extensions. Three are installable today, and each stores something different: plain markdown notes with optional local search, compressed observations in a vector table, or extracted facts in a local Mem0 store. The lab also has five local models that fit fully on one RTX 3090: Thinking Machines' Inkling 2 Mini, three uncensored Inkling derivatives, and Qwen3.8-27B. The lab's planning note frames the full comparison as "5 models × 4 memory systems × 2 benchmarks … 40 experimental cells (50 if you include a `none` baseline)".

This report is the first slice of that matrix: LongMemEval-S only, at pilot size. It asks two narrow questions:

1. Over a fixed body of remembered history, does the memory extension change how many questions a local reader answers correctly?
2. With the memory extension held fixed, does the choice of local reader change it?

The second benchmark in the planning note, DolphinBench, is outside this report; the limitations section says why.

## Method

**Benchmark.** [LongMemEval-S](https://github.com/xiaowu0162/LongMemEval), cleaned release ([Hugging Face revision `98d7416c`](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned), file SHA-256 `d6f21ea9…c3a442`). Each of its 500 questions arrives with its own haystack of past user–assistant chat sessions, 41 to 57 sessions for the questions used here, and a question date. The pilot takes two questions from each of seven strata: the six LongMemEval question types, plus abstention questions (IDs ending `_abs`, whose correct answer is that the history does not say) as a stratum of their own. Within a stratum, questions are ordered by the SHA-256 of their ID and the first two are taken, so the slice is fixed and reproducible: 14 questions.

**Memory arms.** Four, each a different Pi extension or none:

| Arm | Package | What it stores | Search |
|---|---|---|---|
| `none` | — | nothing | — |
| `pi-memory` | [`pi-memory` 0.4.2](https://github.com/jayzeng/pi-memory) | markdown files: long-term memory, daily logs, scratchpad | qmd 2.5.3 keyword or semantic search; `embeddinggemma-300M` on CPU |
| `pi-mem` | [`pi-mem` 0.1.0](https://github.com/georgebashi/pi-mem), prompt capture off (declared patch, below) | LLM-extracted observations and session summaries in LanceDB | full-text plus `nomic-embed-text` vectors |
| `pi-mem0` | [`@lincolness/pi-mem0` 0.2.0](https://github.com/lincolness92/pi-mem0) | facts extracted by Mem0 OSS 3.3.1 into SQLite | `nomic-embed-text` vectors |

The planning note's `mem0-local` is not a published package. `@lincolness/pi-mem0` is the Pi extension that runs Mem0 entirely locally; Mem0's official `@mem0/pi-agent-plugin` requires the hosted Mem0 platform. `pi-memory` requires Pi 0.81.1 or newer, so every run uses a workspace-local Pi 1.6.0. The shared embedding model, `nomic-embed-text`, is served by a CPU-only Ollama instance and never touches the GPU.

**Frozen snapshots, one fixed writer.** Memory is written once per (arm, question) and then frozen. A single writer model, Gemini 3.5 Flash-Lite, replays every session of the question's haystack in date order. Each session goes into a fresh Pi conversation, wrapped in a `<conversation date="…">` block, under one standing instruction: save every durable fact, preference, plan, date and anything the assistant recommended, using the extension's native memory tools. Evidence labels in the dataset (`has_answer`) are stripped before replay. The extensions' own background machinery stays on: pi-mem's observer and summarizer, and pi-mem0's session capture and Mem0 extraction, all routed to the same writer. After the last session the harness waits for that machinery to finish. It requires pi-mem0's outbox to empty with no failed items, pi-mem's LanceDB files to go 30 s without a write, and pi-memory's qmd index and embeddings to rebuild. Only then does it copy the store and record a SHA-256 content digest of the whole tree in a manifest.

**pi-mem's prompt capture is off.** As shipped, pi-mem's `before_agent_start` hook stores every user prompt verbatim as an observation. In this replay each prompt is a whole past session, so with capture on a pi-mem snapshot holds the raw haystack beside the writer's notes: one such snapshot holds 57 verbatim sessions and 57 deliberate notes. No other arm keeps the original text, and with it pi-mem answers 59 of 70 pooled questions. That measures transcript search, not the extension's memory representation. A [patch-package](https://github.com/ds300/patch-package) patch, [`pi-mem+0.1.0.patch`](files/2026-11-23-pi-memory-plugins-longmemeval-pilot/pi-mem+0.1.0.patch), adds a `capturePrompts` option that defaults to on, as upstream, and the arm runs with it off for both writing and reading. Every pi-mem snapshot then holds only the writer's explicit saves: 674 observations of type `manual` across the 14 snapshots, none of type `prompt`. Its observer and summarizer add nothing to a chat-only replay. pi-mem0's session capture stays on: Mem0 stores facts its own extraction model distills from each session, not the session text.

That gives 42 snapshots: 14 questions × 3 extensions. Each lives in its own isolated home directory at a fixed path, so the project and scope keys the extensions derive from the working directory stay stable.

Two simpler designs cannot answer question 2:

- **Each reader writes its own memories.** This costs five times the ingestion and mixes two skills, deciding what to save and finding it again, into one score.
- **Replaying history with no save instruction.** This leaves pi-mem nearly empty by construction: its native capture watches tool results, and a chat-only history produces none.

With the writer held fixed, the only things that vary in a reading cell are the extension's representation and the reader.

The writer reaches Gemini by two routes. The `pi-memory` and `pi-mem0` snapshots are written through OpenRouter, pinned to the Vertex upstream with fallbacks disabled (`{"order": ["google-vertex"], "allow_fallbacks": false}`); the pin is verified to reach the provider, since the same configuration with an unknown provider slug is refused with HTTP 404, `No endpoints found`, by both Pi and Inspect. The `pi-mem` snapshots are written through the Gemini API directly, on a paid project. The two routes serve the same model but can differ in safety and truncation defaults; their effect on what gets saved is not measured here.

**Readers.** Five local GGUFs, each served alone by `llama-server` with every layer on the GPU:

| Reader | Weights | Runtime |
|---|---|---|
| `original` | Inkling 2 Mini, Unsloth `UD-Q4_K_XL` | Unsloth llama.cpp `b12588-mix` |
| `openuncensored` | OpenUncensored Inkling 2 Mini, converted from its safetensors release and quantized to `Q4_K_M` | llama.cpp `b12633` |
| `unbound` | nokeepai Inkling-2-Mini-Unbound v2 `Q4_K_M` | llama.cpp `b12633` |
| `atomicchat` | AtomicChat Inkling-2-Mini-Uncensored `AD-Q4_K` | llama.cpp `b12633` |
| `qwen38` | Qwen3.8-27B, Unsloth `UD-Q4_K_XL` | llama.cpp `b12633` |

Every reader gets the same server settings: 32,768-token context, `q8_0` KV cache, flash attention, one slot, temperature 0, seed 42, reasoning effort `low` with a 4,096-token reasoning budget. The harness refuses to start a cell unless the server log reports all layers offloaded.

**Reading.** For each graded answer, the harness verifies the frozen snapshot against its manifest digest and copies it over the live path, so no read can change what the next read sees. It then runs one Pi conversation in print mode. The reader sees only the extension's memory tools, with Pi's built-in file and shell tools disabled, and gets one appended system instruction carrying the question date: look the history up in memory, then answer concisely or say it does not know. pi-mem0's capture is switched off for reads. A Pi run that exceeds 600 s is cut off and its empty answer scores as incorrect.

**Scoring.** LongMemEval's own grading prompts, imported from [`src/evaluation/evaluate_qa.py` at commit `9e0b455f`](https://github.com/xiaowu0162/LongMemEval/blob/9e0b455f4ef0e2ab8f2e582289761153549043fc/src/evaluation/evaluate_qa.py) and pinned by SHA-256. They are question-type specific: an off-by-one tolerance for counting days, credit for the updated answer on knowledge-update questions, a rubric for preference questions, and a separate abstention prompt. A verdict containing "yes" is correct, as upstream parses it. The judge is the same Gemini 3.5 Flash-Lite at temperature 0: through the OpenRouter Vertex pin for `none`, `pi-memory` and `pi-mem0`, and through the Gemini API directly for `pi-mem`. It grades reader answers only, never memory contents. An empty answer is scored incorrect without a judge call.

**Orchestration.** [Inspect AI](https://inspect.aisi.org.uk/) 0.3.292 `eval_set` owns retries, sample reuse and resume. Each memory arm is one Inspect task, and each reader is one eval set with its own log directory. Readers form the outer loop, so each model loads once per pass: one pass serves `none`, `pi-memory` and `pi-mem0`, a second serves `pi-mem`, both under the same server settings.

**N and the null.** 14 questions × 4 arms × 5 readers = 280 graded answers, one judge call each. The null is the `none` arm, measured with the same readers, server settings and prompt. With no memory, a reader can still pass the two abstention questions by saying it doesn't know, so the null's expected floor is 2 of 14 (14%).

**Repeatability floor.** Temperature 0 and a fixed seed do not make a Pi run repeat. One cell, the original reader on pi-memory, re-run on the same snapshots and graded through the Gemini API directly, gives different answer text on 12 of 14 questions and a different grade on 2, moving the cell from 6 to 8 of 14. A single reader cell is therefore good to about ±2 questions.

**Decision rule, fixed before reading the grades.** One arm *beats* another only if it answers at least 3 more of the 14 questions with **every** reader. Any smaller or inconsistent gap is *indeterminate*. The same rule applies to readers within an arm. With 14 questions, one answer moves a cell by 7 points.

## Results

Accuracy on the 14 questions; each reader cell is n = 14, each pooled cell n = 70:

| Memory | original | openuncensored | unbound | atomicchat | qwen38 | **Pooled** |
|---|---:|---:|---:|---:|---:|---:|
| `none` (null) | 14% | 7% | 21% | 21% | 14% | **11/70 (16%)** |
| `pi-memory` | 43% | 50% | 57% | 50% | 57% | **36/70 (51%)** |
| `pi-mem0` | 43% | 50% | 50% | 50% | 57% | **35/70 (50%)** |
| `pi-mem` | 64% | 64% | 64% | 64% | 71% | **46/70 (66%)** |

Accuracy by question stratum, pooled over readers (n = 10 per cell):

| Stratum | `none` | `pi-memory` | `pi-mem0` | `pi-mem` |
|---|---:|---:|---:|---:|
| abstention | 90% | 100% | 100% | 100% |
| single-session-user | 0% | 60% | 0% | 50% |
| single-session-assistant | 20% | 50% | 60% | 50% |
| single-session-preference | 0% | 90% | 100% | 100% |
| multi-session | 0% | 50% | 0% | 50% |
| knowledge-update | 0% | 0% | 40% | 60% |
| temporal-reasoning | 0% | 10% | 50% | 50% |

<figure>
  <img src="images/2026-11-23-pi-memory-plugins-longmemeval-pilot/answer-grid.svg" alt="A grid of 280 squares: 14 question rows grouped by stratum, by 20 columns in four blocks for the memory arms none, pi-memory, pi-mem0 and pi-mem, each block holding one column per reader. Filled squares mark correct answers. The none block is filled almost only in the two abstention rows. In the pi-mem block every row is either fully filled or empty except the knowledge-update question 07741c45, filled for Qwen3.8 only; the empty rows are 58bf7951, 1d4da289, gpt4_7fce9456 and gpt4_d31cdae3. Per-column accuracy along the bottom reads 14, 7, 21, 21, 14 for none; 43, 50, 57, 50, 57 for pi-memory; 43, 50, 50, 50, 57 for pi-mem0; 64, 64, 64, 64, 71 for pi-mem" width="820">
  <figcaption>Every grade in the pilot. Rows are questions, columns are readers within each memory arm. Rows hold steady across a block: whether a question is answered depends on the memory arm, not the reader.</figcaption>
</figure>

What each answer costs at read time, pooled over readers (n = 70 per arm):

| Memory | Median query time | Slowest answer | Reader input tokens per answer | Reader output tokens per answer | Answers that called a memory tool |
|---|---:|---:|---:|---:|---:|
| `none` | 3.6 s | 8.8 s | 275 | 166 | 0/70 |
| `pi-mem0` | 8.1 s | 600 s (cap) | 1,382 | 285 | 69/70 |
| `pi-mem` | 9.3 s | 22.5 s | 2,691 | 296 | 62/70 |
| `pi-memory` | 13.6 s | 35.7 s | 5,583 | 343 | 64/70 |

<figure>
  <img src="images/2026-11-23-pi-memory-plugins-longmemeval-pilot/query-latency.svg" alt="A strip plot on a log time axis from 1 to 1000 seconds with 70 points per memory arm. none clusters between 2.5 and 9 seconds with median 3.6 s; pi-memory between 7 and 36 seconds with median 13.6 s; pi-mem0 mostly between 4 and 18 seconds with median 8.1 s and one hollow point at 602 s; pi-mem between 4 and 23 seconds with median 9.3 s" width="860">
  <figcaption>Query time for every answer. The three extensions sit within a factor of two of each other at the median; the single 602 s point is the one answer cut off at the 600 s cap (AtomicChat, pi-mem0, a temporal-reasoning question).</figcaption>
</figure>

Snapshot ingestion, per extension, over the same 676 history sessions (14 snapshots each). The writer token columns count the writer's own conversation turns only:

| Memory | Mean time per snapshot | Explicit memory-tool calls | Sessions with no explicit save | Writer input tokens | Writer output tokens |
|---|---:|---:|---:|---:|---:|
| `pi-memory` | 143 s | 655 | 37 | 5.59 M | 106 K |
| `pi-mem0` | 135 s | 431 | 290 | 3.02 M | 60 K |
| `pi-mem` | 561 s | 742 | 5 | 5.00 M | 128 K |

The `sessions with no explicit save` column understates what pi-mem0 holds. Its session capture sends every conversation through Mem0's own fact extraction, whether or not the writer called the tool. The pi-mem snapshots are built at eight concurrent jobs through the Gemini API, the others at four through OpenRouter, so the time column does not compare like with like.

## Representation, not reader, sets the score

Under the decision rule:

- **Every extension beats no memory.** Each answers at least 4 more questions than `none` with every reader. The null sits at its expected floor: `none` passes 9 of 10 abstention answers and almost nothing else.
- **pi-mem against the other two extensions is indeterminate.** It answers 1 to 3 more questions than pi-memory and 2 to 3 more than pi-mem0, short of 3 with every reader, for a pooled 46 against 36 and 35.
- **pi-memory against pi-mem0 is indeterminate.** They are at most one question apart with every reader, and tied with four.
- **The readers are indeterminate** within every arm. The widest spread is two questions; under pi-mem it is one, 9 to 10 of 14.

The answer grid shows the same thing directly. A question that one reader gets right under an extension, most readers get right; a question one misses, most miss. Under pi-mem, 13 of the 14 questions are answered by all five readers or by none. Whatever the extension surfaced, or failed to surface, decides the row.

The pooled gap between pi-mem and pi-memory comes almost entirely from two questions that turn on dated facts: a knowledge update (`b6019101`) and a temporal question (`gpt4_4edbafa2`). Every reader answers both from pi-mem; at most one answers either from pi-memory. On the other twelve questions the two arms agree to within a reader. pi-mem0 answers the temporal question with every reader and the knowledge update with three, but answers no single-session-user or multi-session question, which the other two extensions each partly answer. The amount of retrieved text does not track accuracy: per answer, pi-mem hands the reader 2.7 K input tokens, between pi-mem0's 1.4 K and pi-memory's 5.6 K. With two questions per stratum, the pilot cannot say why dated facts survive better in one representation than another.

The uncensored Inkling derivatives read memory as well as the original. All three score at or above the original in every extension arm, by zero to two questions, inside the indeterminate band.

Qwen3.8 is the one reader whose tool use differs. It calls a memory tool in 33 of 42 extension-arm answers, against 40 or 41 for every Inkling build, yet answers the most extension-arm questions of any reader, 26 of 42 against 21 to 24. Its skipped lookups cost little on this slice.

pi-mem reads cheaply: its median answer takes 9.3 s and its slowest 22.5 s, the lowest worst case of the three extensions, and it sits between pi-mem0 and pi-memory on median time and on tokens in both directions. pi-mem0 is the cheapest extension to read from by median time and by tokens. Its one 600 s cutoff is the pilot's only timed-out answer.

## What this does not settle

- **The size of the gaps.** 14 questions is a pilot; each answer is 7 points per reader cell, and a re-run cell moves by about two questions. Pooling over readers does not multiply the evidence by five: readers share the same questions and the same snapshots, so the effective unit is the question. The ordering {pi-mem, pi-memory, pi-mem0} > none is supported; the order among the extensions is not. A 56-question follow-up (8 per stratum) of pi-mem against pi-memory, with the same readers, writer model and judge prompts and four answers served at once per reader, gives pi-mem 188 of 280 and pi-memory 141, more with every reader (36 to 39 of 56 against 27 to 31). Paired by reader and question, pi-mem alone is right 67 times and pi-memory alone 20 (exact McNemar p = 4 × 10⁻⁷); by question, 21 favor pi-mem and 8 pi-memory (sign test p = 0.024). On this pilot's 14 questions, pi-mem's grades with one answer and with four answers served at once agree on all 70.
- **Writing skill.** One writer produces every snapshot, by design. The pilot says nothing about which local model would write better memories, or about the extensions under each reader's own writes. That is the planning note's end-to-end design, at five times the ingestion.
- **Default behavior.** Every snapshot comes from an explicit "save durable facts" instruction, and pi-mem runs with prompt capture off. Installed and left alone, pi-mem stores every prompt verbatim and captures tool results from coding sessions. These results describe each extension given deliberate writes, not out of the box. How much of pi-mem's 59 of 70 with capture on is plain search over the transcript is the obvious control: a BM25 arm over the raw sessions, as in LongMemEval's own baselines.
- **Writer and judge route.** pi-mem is written and graded through the Gemini API directly, the other arms through OpenRouter's Vertex pin. The model is the same; any difference between the two upstreams falls on the pi-mem comparison.
- **The writer–judge link.** Memories are written by the same model that judges the answers. The judge grades reader answers, which paraphrase retrieved memories, so any preference it has for its own phrasing applies to every extension arm. Its size is not measured here.
- **Ingestion cost per extension.** The writer-token table omits pi-mem's observer and summarizer calls and pi-mem0's Mem0 extraction calls, which run inside the extensions. Spend is measured only as one OpenRouter total for the other arms; pi-mem's Gemini API spend is not broken out.
- **DolphinBench.** The planning note's second benchmark needs its own harness: five driver methods, a simulated app server reached over MCP, and action grading. One persona's history alone is 5,011 messages, each a fresh conversation. Nothing here predicts it.
- **Higher reasoning effort.** Every reader runs at effort `low` with a 4,096-token reasoning budget. One answer, AtomicChat with pi-mem0 on a temporal question, runs into the 600 s cap.

## Cost

- **Compute time, reading:** 899 s for the 70 pi-mem answers, 12.8 s per answer including judging and five model loads. The other three arms' 210 answers share a 4,947 s pass with a prompt-capture pi-mem arm, about 17.7 s per answer across its 280.
- **Compute time, writing:** the pi-memory and pi-mem0 snapshots share a 2,103 s pass at four concurrent jobs; the pi-mem snapshots come from a 56-snapshot pass of 3,966 s at eight. A snapshot of a 41- to 57-session history averages 135 s of writer time for pi-mem0, 143 s for pi-memory and 561 s for pi-mem, so a question's memory is ready in two to ten minutes.
- **Peak memory:** `llama-server`'s own allocation report (model, KV cache and compute buffers) ranges from 17,928 MiB for Qwen3.8 to 19,277 MiB for Unbound, 73–78% of the 24,576 MiB card, with every layer offloaded. CUDA context overhead comes on top. Embeddings and qmd run on CPU.
- **Money:** $7.15 of OpenRouter credit for every writer, extension-internal and judge call of the other arms, including the discarded builds below. pi-mem's Gemini API calls are billed to a Google Cloud project and not broken out here.
- **Calendar time:** **10 h 47 min** from the request for the memory matrix at 13:21 PST on 2026-11-23 to the last pi-mem grade at 00:08 PST on 2026-11-24, and 11 h 08 min from the first request to benchmark these models through Pi. Active spans: 35 min and 82 min for the snapshot and reader passes of the other arms, 66 min and 15 min for pi-mem's.

Failed and wasted work, with causes:

- **Google AI Studio free tier.** The lab's direct Google key caps Gemini 3.5 Flash-Lite at 15 requests per minute on the free tier, and ingestion exceeds that within five conversations (HTTP 429). OpenRouter serves the same model without that cap. Once the lab's $10 of OpenRouter credit is spent, billing on the Google project lifts the cap, and pi-mem's snapshots and grades take that route.
- **pi-mem with prompt capture on.** 14 snapshots and 70 graded answers that hold the replayed transcripts verbatim; they measure transcript search rather than pi-mem's notes (see Method) and are replaced.
- **Other judge candidates.** The lab's OpenAI key has no remaining credit, and its Anthropic key needs a workspace header it does not carry. That leaves Gemini as the reachable fixed judge.
- **Unpinned snapshots.** Seven snapshots built before the Vertex pin are discarded and rebuilt, about $1.
- **Transient network failures.** OpenRouter connections intermittently reset (`ECONNRESET`) or time out on connect. A harness-level retry of a failed session, after a partial write, replays that session twice into the same store; two snapshots built that way are among the discarded prompt-capture ones. The pi-mem snapshots leave retries to Pi's built-in provider retry (three attempts, 2 s base delay), which repeats only the failed request.
- **Old global Pi.** The machine-wide Pi 0.73.1 cannot load `pi-memory` (`Cannot read properties of undefined (reading 'Object')`), hence the workspace-local Pi 1.6.0.

## Files

Scripts, data and logs for this run, all in `files/2026-11-23-pi-memory-plugins-longmemeval-pilot/`. The top-level scripts build and read the `none`, `pi-memory` and `pi-mem0` arms; the `pi-mem/` copies build and read the `pi-mem` arm.

- [`arms.py`](files/2026-11-23-pi-memory-plugins-longmemeval-pilot/arms.py): the arms, per-phase extension configuration, the writer and its OpenRouter pin, the stratified question slice, and snapshot freeze/restore with content digests
- [`ingest.py`](files/2026-11-23-pi-memory-plugins-longmemeval-pilot/ingest.py): builds the snapshots through Pi's RPC mode, retries failed sessions, waits for each extension's background writes, freezes
- [`pi-mem/arms.py`](files/2026-11-23-pi-memory-plugins-longmemeval-pilot/pi-mem/arms.py), [`pi-mem/ingest.py`](files/2026-11-23-pi-memory-plugins-longmemeval-pilot/pi-mem/ingest.py), [`pi-mem/longmemeval.py`](files/2026-11-23-pi-memory-plugins-longmemeval-pilot/pi-mem/longmemeval.py), [`pi-mem/pilot.py`](files/2026-11-23-pi-memory-plugins-longmemeval-pilot/pi-mem/pilot.py): the same harness with the Gemini API writer and judge, `capturePrompts: false`, ingestion as an Inspect task with Pi's own retry, and `--parallel N` reader slots (the pilot uses 1)
- [`pi-mem+0.1.0.patch`](files/2026-11-23-pi-memory-plugins-longmemeval-pilot/pi-mem+0.1.0.patch): the patch-package patch adding pi-mem's `capturePrompts` option
- [`longmemeval.py`](files/2026-11-23-pi-memory-plugins-longmemeval-pilot/longmemeval.py): the Inspect task. A Pi-driven reader solver, and a scorer that imports LongMemEval's own grading prompts
- [`pilot.py`](files/2026-11-23-pi-memory-plugins-longmemeval-pilot/pilot.py): starts each reader's `llama-server`, checks full offload, runs `eval_set` over the four arms
- [`run.py`](files/2026-11-23-pi-memory-plugins-longmemeval-pilot/run.py): the reader table (`VARIANTS`) that `pilot.py` imports from the lab's earlier Pi benchmark
- [`analyze.py`](files/2026-11-23-pi-memory-plugins-longmemeval-pilot/analyze.py): builds every table above from the Inspect logs (`evals_df`, `samples_df`) and the snapshot manifests, and exports `samples.csv`
- [`pilot_charts.py`](files/2026-11-23-pi-memory-plugins-longmemeval-pilot/pilot_charts.py): renders both figures from `samples.csv`
- [`samples.csv`](files/2026-11-23-pi-memory-plugins-longmemeval-pilot/samples.csv): one row per graded answer, with correctness, query time, timeout flag, memory-tool calls and reader tokens
- [`pilot-summary.txt`](files/2026-11-23-pi-memory-plugins-longmemeval-pilot/pilot-summary.txt): `analyze.py`'s full output
- [`snapshot-manifests.jsonl`](files/2026-11-23-pi-memory-plugins-longmemeval-pilot/snapshot-manifests.jsonl): the 42 snapshot manifests: writer, sessions, memory calls, retries, writer usage, seconds, content digest
- [`inspect-logs.tar.gz`](files/2026-11-23-pi-memory-plugins-longmemeval-pilot/inspect-logs.tar.gz) (1.6 MB): every Inspect log behind the tables, viewable with `inspect view --log-dir lme-pilot` after extraction. Includes each answer's Pi transcript and the judge's verdict

The scripts are not drag-and-drop. They expect:

- the reader GGUFs at local paths named in `run.py`, two of them as Ollama blobs
- Pi 1.6.0 and the three extensions installed into the workspace (`.pi-runtime/`, `.plugins/`), with patch-package applying the pi-mem patch on install
- a CPU Ollama serving `nomic-embed-text` on port 11435
- `OPENROUTER_API_KEY` for the top-level scripts, `GEMINI_API_KEY` for the `pi-mem/` ones
- the LongMemEval-S file and `evaluate_qa.py` beside them, both hash-checked at import

The 142 MB of frozen snapshots are not published; `ingest.py` rebuilds them.
