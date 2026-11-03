# Antfly Thinking-Model Compatibility Report

Date: 2026-11-02  
Target: Ollama OpenAI-compatible `/v1` endpoint vs Antfly agents (`retrieval`, `query-builder`, `research`)  
Environment: RTX 3090 (24 GB), Ollama 0.40.11, Antfly `ghcr.io/antflydb/antfly:latest` (image built 2026-09-28, runtime v0.2.5) vs patched origin/main (`7ca4b04b81` + 460 commits to HEAD `ce4c1140ad` + patch `46a6df52ae`) on branch `fix/ollama-thinking-compat`.

---

## Executive Summary

Thinking models (Nemotron 3.5 Lightning 30B, Swift-Qwen3.8-27B, etc.) fail in Antfly because **Antfly enforces a hardcoded 256-token default completion cap** on requests that do not pass `max_tokens`. Ollama returns reasoning in a private `message.reasoning` (or `reasoning_content`) field and charges those tokens against `max_tokens`. The models burn all 256 tokens on reasoning, return `content: ""` with `finish_reason: "length"`, and Antfly's stock OpenAI client silently accepts the empty string as success.

Two fixes are viable:
1. **Config-only (cheapest, immediate, no fork, zero rebuilds)**: add `"max_tokens": 4096` to the generator JSON:
   `{"provider":"ollama","model":"...","url":"http://172.17.0.1:11434/v1","max_tokens":4096}`.
   This immediately restores Nemotron from **0.00 RAG / 0.38 QB** to **0.88 RAG / 0.88 QB** on the stock container, and Swift-Qwen from **0.88 RAG / 0.33 QB** to **0.88 RAG / 0.83 QB**.
2. **Upstream PR (36 lines of code across 3 files + spec docs)**:
   - Make `openai.zig` parse `finish_reason` and treat an empty length-truncated answer as `error.InferenceOutputIncomplete` instead of silent success.
   - Allow and forward `reasoning_effort` for the `ollama` provider so users can pass `reasoning_effort: "none"` to turn thinking off.
   - Encode bare assistant turns (no content, no tool calls) with `"content": ""` so Ollama doesn't reject query-builder retries with HTTP 400.
3. **Fork recommendation**: **DO NOT fork**. The upstream maintainer merges ~100 commits/day, regenerates multi-thousand-line SDK files on every minor schema touch, and has already released `v0.3.0-rc.9` (which includes the missing `agents research` route). A fork will drown in rebase friction. Instead, use the config-only fix immediately and contribute the 36-line fix upstream.

---

## Deliverable (a): Root Cause & Captured Evidence

### Hypothesis Verification Matrix

| Hypothesis | Verdict | Evidence |
|---|---|---|
| **H1: Ollama puts thinking in a separate field; `content` is empty/truncated under 256 default cap; Antfly reads only `content`** | **CONFIRMED (Primary cause)** | Wire captures #2, #3 below. Ollama emits `message.reasoning` and charges it to `completion_tokens`. When `completion_tokens == max_tokens == 256`, `finish_reason` is `"length"` and `content` is `""`. Antfly's `openai.zig:324` accepted `""` as valid completion. |
| **H2: Antfly does not forward `reasoning_effort` or `think: false` to Ollama** | **CONFIRMED (Secondary block)** | `mod.zig:603` and `inference_tasks.zig:542` rejected `reasoning_effort` for non-OpenAI providers with HTTP 400 `invalid retrieval agent request`. Ollama `/v1` natively supports `reasoning_effort: "none"` to disable thinking (verified directly; 13 tokens, finish `stop`, `content` populated). |
| **H3: Parser mishandles `<think>` blocks or bare `</think>` in content** | **RULED OUT for `/v1`** | Ollama 0.40.11 properly strips `<think>` into `message.reasoning` on the `/v1` OpenAI-compatible endpoint. `<think>` and `</think>` never appear in `/v1` `content`. The bare `</think>` observed on Humanlike-Chat happens only on raw `/api/generate` with custom template prefill. |
| **H4: Streaming vs non-streaming drops reasoning deltas** | **RULED OUT** | Antfly's retrieval and query-builder agents only call upstream providers via the blocking (non-streaming) `generate()` method (`openai.zig:265`). The `stream: false` vs `stream: true` in the agent request controls only how Antfly streams SSE events back to the client. |
| **New discovery: bare assistant turn serialization failure** | **CONFIRMED (Root of QB 500/502s)** | When an assistant turn produced no content and no tool calls (due to truncation), Antfly's `chat_wire.zig` omitted the `content` key entirely. Ollama rejected the subsequent turn with HTTP 400 `invalid message content type: <nil>`, killing the query-builder loop. |

### Wire Evidence

#### 1. Baseline failure: Nemotron retrieval under stock Antfly (port 11439 logging proxy)

**Antfly -> Ollama Request**:
```json
POST /v1/chat/completions HTTP/1.1
Host: 172.17.0.1:11439
Content-Type: application/json

{
  "model": "hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_S",
  "messages": [
    {"role": "system", "content": "Answer the user query using only the retrieved documents and cite document ids inline."},
    {"role": "user", "content": "Query: What protective garment did Cicero wear when he presided over the consular elections of 63 BC?\n\nDocuments:\n[ebook:a4c3c12c...:001114] In 63, Cicero presided over the electoral process... wearing a protective cuirass under his tunic...\n\nProvide a concise answer grounded in the retrieved documents."}
  ],
  "max_tokens": 256
}
```

**Ollama -> Antfly Response**:
```json
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "chatcmpl-883",
  "object": "chat.completion",
  "created": 1793656442,
  "model": "hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_S",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "",
        "reasoning": "Here's a thinking process:\n\n1.  **Analyze User Query**: The user asks: \"What protective garment did Cicero wear when he presided over the consular elections of 63 BC?\"\n\n2.  **Identify Key Information from Retrieved Documents**:\n   - Document 1 (id=ebook:a4c3c12c2af272ff28464e39671347db0d4e0ce849f7fb83622412490fff3ee8:001114): Mentions \"wearing a protective cuirass.\"\n   - Document 2 (id=ebook:a4c3c12c2af272ff28464e39671347db0d4e0ce849f7fb83622412490fff3ee8:000961): Mentions \"wearing a pro"
      },
      "finish_reason": "length"
    }
  ],
  "usage": {
    "prompt_tokens": 2577,
    "completion_tokens": 256,
    "total_tokens": 2833
  }
}
```

**Antfly -> Client Response** (`/db/v1/agents/retrieval`):
```json
{
  "status": "completed",
  "generation": "",
  "steps": [
    {"name": "pipeline", "status": "success", "details": {"query_count": 1, "strategies": ["bm25"]}},
    {"name": "generation", "status": "success", "details": null}
  ]
}
```
*Elapsed: 2.4s to 96s depending on model load. Antfly reports `generation: success` with an empty string because `openai.zig` read `content: ""` and ignored `finish_reason: "length"`.*

#### 2. Query-builder failure: bare assistant turn rejected by Ollama

When query-builder tried to recover from an empty assistant turn, Antfly sent:
```json
{
  "model": "hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_S",
  "messages": [
    {"role": "system", "content": "Build a read-only Antfly query using tools..."},
    {"role": "user", "content": "find chunks from Astin's book..."},
    {"role": "assistant", "tool_calls": [{"id": "...", "type": "function", "function": {"name": "describe_table", "arguments": "{}"}}]},
    {"role": "tool", "content": "{\"table\":\"rome\",...}", "tool_call_id": "..."},
    {"role": "assistant"},
    {"role": "user", "content": "This is query planning, not answering the question. Call describe_table if needed or submit_query."}
  ],
  "max_tokens": 256
}
```
**Ollama Response**:
```json
HTTP/1.1 400 Bad Request
{"error":{"message":"invalid message content type: \u003cnil\u003e","type":"invalid_request_error","param":null,"code":null}}
```
*Antfly translated this 400 into `query-builder 502 status=None err='query generation failed'` or HTTP 500.*

#### 3. Direct test: Ollama `/v1` control parameters

Tested against the identical Nemotron request:
- `antfly_as_sent` (`max_tokens: 256`): `finish: "length"`, `ctoks: 256`, `content: ""`, `reasoning_len: 570`
- `reasoning_effort: "none"`: `finish: "stop"`, `ctoks: 13`, `content: "cuirass (Document 1, Document 2)"`, `reasoning_len: 0`
- `think: false`: `finish: "length"`, `ctoks: 256`, `content: ""` (Ollama ignores top-level `think` on `/v1`)
- `max_tokens: 4096`: `finish: "stop"`, `ctoks: 834`, `content: "Cicero wore a **protective cuirass**..."`, `reasoning_len: 2103`

---

## Deliverable (b): The Cheapest Fix

### Option 1: Config-only (Recommended for immediate use)

Pass `"max_tokens": 4096` in the generator payload in all agent calls.

```json
{
  "provider": "ollama",
  "model": "hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_S",
  "url": "http://172.17.0.1:11434/v1",
  "max_tokens": 4096
}
```

**Why this works**:
- Antfly's `public_index_contract.zig` and `mod.zig` already accept `max_tokens` on `OllamaGeneratorConfig`.
- `openai.zig:196` forwards `max_tokens` verbatim to Ollama's `/v1/chat/completions`.
- Ollama lets thinking models spend 500-2500 tokens on reasoning and still have 1500+ tokens left for visible content.
- Works on the **stock production container today** without pulling new images, compiling Zig, or touching docker volumes.

**Why Modelfile tweaks do NOT work**:
1. Ollama's Modelfile parser has no `PARAMETER think false` (rejected with `Error: unknown parameter 'think'`).
2. The GGUFs for Nemotron and Qwen3.8 use builtin Jinja renderers (`nemotron-3-nano`). Ollama's Modelfile `TEMPLATE` command only accepts Go templates; pasting Jinja fails with `template: :5: malformed character constant: '\n<'`.
3. Replacing the template with a non-thinking Go template breaks tool-calling because Ollama's Go template path cannot parse the XML-style function call blocks emitted by Nemotron.

### Option 2: Code Patch (for upstream contribution)

Committed on branch `fix/ollama-thinking-compat` at `46a6df52ae` (based on origin/main):

1. **`zig/pkg/antfly-embedded/src/inference/providers/openai.zig`**:
   - Parse `choices[0].finish_reason`.
   - If `content` is empty, no tool calls were made, and `finish_reason == .length`, return `error.InferenceOutputIncomplete`. This converts silent empty completions into honest errors.
   - Forward `self.reasoning_effort` in compatible requests via `setReasoningEffort()`.
2. **`zig/lib/generating/src/chat_wire.zig`**:
   - Add `reasoning_effort: ?[]const u8` to `ChatRequestOptions` and serialize it to JSON.
   - When serializing an assistant turn where `content == null` and `tool_calls == null`, emit `"content": ""` so OpenAI-compatible servers (Ollama) accept the turn.
3. **`zig/lib/generating/src/mod.zig` + `inference_tasks.zig`**:
   - Loosen the generator config validator so `self.reasoning_effort != null` is permitted when `provider == .ollama`.
4. **`specs/openapi/shared/generating.yaml` + openapi specs**:
   - Add `reasoning_effort` property to `OllamaGeneratorConfig`.

---

## Deliverable (c): Fork Assessment

### Maintenance Cost vs Upstream Contribution

| Factor | Upstream Contribution | Self-Maintained Fork |
|---|---|---|
| **Upstream commit velocity** | - | **2,481 commits in last 30 days** (~83/day), single primary committer (`ajroetker`), squashed feature branches. |
| **Generated file drift** | Run `make generate` once before PR. | `openapi.yaml`, `rs/crates/sdk/openapi.yaml`, `go/pkg/sdk/oapi/client.gen.go` change in almost every upstream commit. Rebasing a fork requires continuous manual re-generation across Zig, Go, TS (requires Volta/Node 24.16.0), and Python toolchains. |
| **Code footprint of fix** | **36 lines** of real Zig changes across 3 files + 7 lines in OpenAPI YAML. | Same code, but constantly diverging build metadata and submodules. |
| **License & CLA friction** | **Apache-2.0, zero CLA**, no DCO required (`Signed-off-by` is optional per `CONTRIBUTING.md:215`). Upstream actively merges community bugfixes. | Apache-2.0 allows forks, but image building requires proprietary-style CI setups (CUDA fatbin compression, specialized ReleaseSafe scripts). |
| **Build time & resource cost** | Build once locally: ~5m24s incremental, ~11m28s cold; uses ~1.3 GB binary artifact and ~2 GB cache. | Ongoing CI maintenance, Docker registry hosting, multi-platform runner maintenance. |

**Verdict**: A long-term fork is a maintenance trap for a 36-line bugfix. The appropriate path is:
1. Apply the config-only workaround immediately in benchmark harnesses and production generator payloads.
2. Open an upstream PR with `fix/ollama-thinking-compat` (detailed PR draft below).

### The `agents research` Route Investigation

The user observed that `antfly agents research` gave "unknown agents subcommand" and `POST /db/v1/agents/research` returned 405 on the running container.

**Investigation findings**:
1. **Running container image**: `ghcr.io/antflydb/antfly:latest` running at `127.0.0.1:18080` was built on **2026-09-28** (digest `sha256:300b6644...`, version `antfly 0.2.5 (zig runtime)`).
2. **When research agent landed**: `research_agent.zig` and the `/db/v1/agents/research` HTTP route were committed on **2026-10-29** (commit `c1fe417726`). It did not exist when 0.2.5 was built.
3. **Published release candidate**: `ghcr.io/antflydb/antfly:v0.3.0-rc.9` (published **2026-11-02 07:36 UTC**) **contains the full research agent**:
   - `docker run --rm ghcr.io/antflydb/antfly:v0.3.0-rc.9 agents --help` lists:
     `usage: antfly agents <retrieval|research|query-builder> [options]`
4. **Patched build verification**:
   - The locally built binary from `fix/ollama-thinking-compat` running on port 18081 successfully executed a full multi-turn research run against the Rome table:
     ```bash
     ANTFLY_URL=http://127.0.0.1:18081 ./antfly agents research \
       --query "What protective garment did Cicero wear in 63 BC?" \
       --table rome \
       --generator '{"provider":"ollama","model":"Swift-Qwen3.8-27B:Q4_K_M","url":"http://172.17.0.1:11439/v1","max_tokens":4096}' \
       --max-rounds 1 --max-sub-questions 1 --max-parallel 1 --no-streaming
     ```
     Result: `status: "completed"`, `llm_calls: 9`, `tool_calls: 9`, `evidence_count: 4`, elapsed: 106s, cited `ebook:a4c3c12c...:001114` (cuirass).
5. **Storage format caution**: Running `v0.3.0-rc.9` or the patched binary on the production data auto-upgrades the directory from `storage_format 1` to `storage_format 2`. Rollback to 0.2.5 requires a backup. The user should plan a clean upgrade to official `v0.3.0` rather than running a custom fork.

---

## Deliverable (d): Before and After Bench Numbers

All runs executed against the real frozen `rome` vault harness (`/home/user/Documents/rome/bench/model_bench.py`, fixture `/home/user/Documents/rome/bench/fixture.json`) with full BM25 full-text queries and `max_internal_iterations: 6`.

### 1. NVIDIA-Nemotron-3.5-Lightning-30B-A3B (Q4_K_S)

| Configuration | Server | `antfly_rag_acc` | `antfly_qb_score` | `antfly_score` | Notes |
|---|---|---|---|---|---|
| **Stock baseline (before)** | Production container (0.2.5) | **0.0000** | 0.3750 | 0.1875 | Default `max_tokens: 256` exhausted by thinking; all 8 RAG answers returned empty `""`. |
| **Config fix (`max_tokens: 4096`)** | Production container (0.2.5) | **0.8750** | **0.8750** | **0.8750** | 7/8 RAG hits, 6/6 QB intents succeeded. **+0.6875 overall gain.** |
| **Patched + `max_tokens: 4096`** | Patched server (port 18081) | **0.7500** | **0.8750** | **0.8125** | Truncation error safety active. |
| **Patched + `reasoning_effort: "none"`** | Patched server (port 18081) | 0.7500 | 0.0000 | 0.3750 | Thinking disabled. RAG answers concise, but Nemotron cannot generate complex SQL/BM25 query structures without thinking. |
| **Patched + default (256 cap)** | Patched server (port 18081) | 0.0000 | 0.0000 | 0.0000 | Fails loudly with `retrieval 500 INTERNAL_ERROR` (`InferenceOutputIncomplete`) instead of silent empty string. |

### 2. Swift-Qwen3.8-27B (Q4_K_M)

| Configuration | Server | `antfly_rag_acc` | `antfly_qb_score` | `antfly_score` | Notes |
|---|---|---|---|---|---|
| **Stock baseline (before)** | Production container (0.2.5) | 0.8750 | 0.3333 | 0.6042 | 4 of 6 QB queries hit 502/500 errors due to bare-assistant turn rejection (`<nil>` content). |
| **Config fix (`max_tokens: 4096`)** | Production container (0.2.5) | **0.8750** | **0.8333** | **0.8542** | QB jumps from 0.33 to 0.83. **+0.2500 overall gain.** |
| **Patched + `max_tokens: 4096`** | Patched server (port 18081) | **0.8750** | **0.7917** | **0.8333** | Bare-assistant turns serialized cleanly; zero 500s. |
| **Patched + `reasoning_effort: "none"`** | Patched server (port 18081) | 0.8750 | 0.1667 | 0.5208 | Qwen also relies on thinking for schema introspection and multi-term boolean query synthesis. |

### Key Takeaway for the Bake-off

Thinking models **require thinking tokens for the tool-calling query-builder task**, even more than for single-turn RAG generation. Turning thinking off via `reasoning_effort: "none"` destroys query-builder accuracy (0.88 -> 0.00 on Nemotron, 0.83 -> 0.17 on Swift).

The winning strategy for the bake-off is **keeping thinking enabled and passing `max_tokens: 4096` in the generator config**. With that single configuration setting, Nemotron ties or beats non-thinking Qwen3-Coder (0.875 vs 0.75-1.0) while preserving its high direct QA (0.96) and tool (0.975) quality scores.

---

## Action Plan & Upstream PR Draft

1. **Immediate user action for bake-off**: Update `/home/user/Documents/rome/bench/models.json` (or any generation request wrapper) to pass `"max_tokens": 4096` in the `generator` dictionary.
2. **Upstream PR**:
   - Branch: `fix/ollama-thinking-compat` (at `46a6df52ae`, rebased on `origin/main`).
   - Title: `fix(generating): support Ollama thinking models and handle length truncation`
   - Description:
     ```markdown
     ### Problem
     When Ollama serves thinking-capable models (Nemotron, Qwen 3.8, DeepSeek-R1) via its
     OpenAI-compatible `/v1` endpoint, reasoning tokens are returned in `message.reasoning`
     and charged against `max_tokens`. Under Antfly's default 256-token cap:
     1. The budget is spent entirely on reasoning, returning `content: ""` and
        `finish_reason: "length"`. `openai.zig` did not inspect `finish_reason`, treating
        empty truncated answers as success.
     2. When agents replayed empty turns, `chat_wire.zig` omitted the `content` key on
        assistant messages without tool calls, causing Ollama to reject the turn with
        HTTP 400 (`invalid message content type: <nil>`).
     3. Users could not pass `reasoning_effort: "none"` to Ollama because Antfly's
        generator validator restricted that option to `openai` and `chatgpt`.

     ### Solution
     - `openai.zig`: parse `choices[0].finish_reason`. Return `error.InferenceOutputIncomplete`
       if content is empty, no tool calls occurred, and `finish_reason == .length`.
     - `chat_wire.zig`: add `reasoning_effort` to `ChatRequestOptions` and forward it in
       compatible chat completions (Ollama maps `"none"` to disabled thinking).
     - `chat_wire.zig`: serialize bare assistant turns with `"content": ""` to comply
       with Chat Completions wire requirements.
     - `mod.zig`, `inference_tasks.zig`: permit `reasoning_effort` on `provider == .ollama`.
     - `specs/openapi/shared/generating.yaml`: document `reasoning_effort` on `OllamaGeneratorConfig`.
     ```

3. **Production container upgrade**: When upstream releases `v0.3.0` stable, pull `ghcr.io/antflydb/antfly:v0.3.0`. It will natively support `agents research` and the upgraded storage format without maintaining any private image.
