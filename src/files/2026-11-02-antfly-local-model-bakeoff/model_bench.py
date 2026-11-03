#!/usr/bin/env python3
"""Benchmark one (embedding model, generator model) pair from bench/models.json.

Workload is frozen in bench/fixture.json (382 rome chunks, 32 hand-written
known-item questions with answer keys). Every model call is local Ollama or
local Antfly; generation uses temperature 0 and a fixed seed.

Sections
  embed    known-item retrieval over the fixture pool (MRR@10, recall@5)
  qa       grounded QA over 5 passages via /v1/chat/completions (answer + citation)
  tools    OpenAI-style tool calling with Antfly-like tools (args/types/values)
  antfly   Antfly retrieval agent (generation) + query-builder (tool planner)

Prints `METRIC name=value` lines; primary is `quality`.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BENCH = Path(__file__).resolve().parent
OLLAMA = os.environ.get("BENCH_OLLAMA_URL", "http://127.0.0.1:11434")
ANTFLY = os.environ.get("BENCH_ANTFLY_URL", "http://127.0.0.1:18080")
# Antfly runs in Docker and reaches the host Ollama via the bridge gateway.
ANTFLY_OLLAMA = os.environ.get("BENCH_ANTFLY_OLLAMA_URL", "http://172.17.0.1:11434/v1")
SEED = 7
CALL_TIMEOUT = 240


def http_json(url: str, body: dict | None = None, timeout: float = CALL_TIMEOUT):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode(errors="replace")
        try:
            return exc.code, json.loads(text)
        except json.JSONDecodeError:
            return exc.code, {"error": text}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- embedding

def embed(model: str, texts: list[str], batch: int = 16) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), batch):
        status, data = http_json(f"{OLLAMA}/api/embed", {"model": model, "input": texts[i:i + batch], "truncate": True})
        if status != 200:
            raise RuntimeError(f"embed {model} failed: {status} {data}")
        out.extend(data["embeddings"])
    return out


def unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def bench_embed(cfg: dict, fx: dict) -> dict:
    model = cfg["embedding"]
    qp, dp = cfg.get("embed_query_prefix", ""), cfg.get("embed_doc_prefix", "")
    docs = fx["docs"]
    key = hashlib.sha256(json.dumps([model, dp, [d["id"] for d in docs]]).encode()).hexdigest()[:16]
    cache = BENCH / ".cache" / f"embed-{key}.json"
    if cache.exists():
        cached = json.loads(cache.read_text())
    else:
        embed(model, [dp + "warmup"])  # load model so throughput excludes load time
        t0 = time.time()
        vecs = embed(model, [dp + d["body"] for d in docs])
        cached = {"model": model, "docs_per_s": len(docs) / (time.time() - t0), "vecs": vecs}
        cache.parent.mkdir(exist_ok=True)
        cache.write_text(json.dumps(cached))
    dvecs = [unit(v) for v in cached["vecs"]]
    ids = [d["id"] for d in docs]

    items = fx["items"]
    embed(model, [qp + "warmup"])
    t0 = time.time()
    qvecs = [unit(v) for v in embed(model, [qp + it["question"] for it in items], batch=1)]
    q_ms = (time.time() - t0) * 1000 / len(items)

    rr, r5 = [], []
    for it, q in zip(items, qvecs):
        scores = sorted(((sum(a * b for a, b in zip(q, d)), i) for d, i in zip(dvecs, ids)), reverse=True)
        ranked = [i for _, i in scores[:10]]
        rel = set(it["relevant"])
        rank = next((n for n, i in enumerate(ranked, 1) if i in rel), None)
        rr.append(1 / rank if rank else 0.0)
        r5.append(1.0 if rank and rank <= 5 else 0.0)
    return {
        "embed_mrr10": sum(rr) / len(rr),
        "embed_recall5": sum(r5) / len(r5),
        "embed_query_ms": q_ms,
        "embed_docs_per_s": cached["docs_per_s"],
        "embed_dim": len(dvecs[0]),
    }


# ---------------------------------------------------------------- generator

def chat(model: str, messages: list[dict], tools: list | None = None, max_tokens: int = 4096):
    body = {"model": model, "messages": messages, "temperature": 0, "seed": SEED, "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools
    t0 = time.time()
    status, data = http_json(f"{OLLAMA}/v1/chat/completions", body)
    dt = time.time() - t0
    if status != 200 or not data.get("choices"):
        return None, dt
    return data["choices"][0]["message"], dt


def parse_json_obj(text: str):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def keys_hit(text: str, groups: list[list[str]]) -> bool:
    low = (text or "").lower()
    return all(any(a in low for a in grp) for grp in groups)


QA_SYSTEM = (
    "You answer questions about Roman history using only the numbered source passages provided. "
    "Reply with a single JSON object and nothing else: "
    '{"answer": "<short answer>", "source": <number of the passage that supports it>}. '
    'If the passages do not answer the question, reply {"answer": "unknown", "source": null}.'
)


def qa_context(it: dict, fx: dict, with_gold: bool) -> list[str]:
    """8 passages, deterministic order. Answerable: gold + same-topic hard negatives + other-topic
    fillers. Control (no gold): other-topic passages only, so nothing in context answers."""
    rel = set(it["relevant"])
    ids = [it["gold"]] if with_gold else []
    ids += [i for i in it["distractors"] if i not in rel] if with_gold else []
    for other in fx["items"]:
        if len(ids) >= 8:
            break
        if other["topic"] != it["topic"] and other["gold"] not in rel and other["gold"] not in ids:
            # filler from a different topic, chosen by hash so it is stable but not adjacent
            if int(hashlib.sha256((it["topic"] + other["topic"]).encode()).hexdigest(), 16) % 3 == 0:
                ids.append(other["gold"])
    ids.sort(key=lambda i: hashlib.sha256((it["topic"] + i).encode()).hexdigest())
    return ids


def bench_qa(model: str, fx: dict, timings: list) -> dict:
    """24 answerable questions (every item except each 4th) + 8 unanswerable controls."""
    by_id = {d["id"]: d for d in fx["docs"]}
    ans = cite = js = refuse = 0
    n_ans = n_unk = 0
    for idx, it in enumerate(fx["items"]):
        control = idx % 4 == 3
        ids = qa_context(it, fx, with_gold=not control)
        ctx = "\n\n".join(f"[{n}] {' '.join(by_id[i]['body'].split())}" for n, i in enumerate(ids, 1))
        msg, dt = chat(model, [
            {"role": "system", "content": QA_SYSTEM},
            {"role": "user", "content": f"Passages:\n{ctx}\n\nQuestion: {it['question']}"},
        ])
        timings.append(dt)
        content = (msg or {}).get("content") or ""
        obj = parse_json_obj(content)
        js += obj is not None
        answer = str(obj.get("answer", "")) if isinstance(obj, dict) else content
        if control:
            n_unk += 1
            refuse += "unknown" in answer.lower() and not keys_hit(answer, it["answer_keys"])
            continue
        n_ans += 1
        ans += keys_hit(answer, it["answer_keys"])
        if isinstance(obj, dict):
            try:
                cite += ids[int(obj.get("source")) - 1] in set(it["relevant"])
            except (TypeError, ValueError, IndexError):
                pass
    total = n_ans + n_unk
    return {"qa_answer_acc": ans / n_ans, "qa_cite_acc": cite / n_ans, "qa_refusal_acc": refuse / n_unk,
            "qa_json_ok": js / total,
            "qa_score": 0.6 * ans / n_ans + 0.2 * cite / n_ans + 0.2 * refuse / n_unk}


TOOLS = [
    {"type": "function", "function": {
        "name": "search_chunks",
        "description": "Search the Roman history book corpus. Returns matching text chunks.",
        "parameters": {"type": "object", "required": ["query", "mode", "limit"], "properties": {
            "query": {"type": "string", "description": "Search text"},
            "mode": {"type": "string", "enum": ["full_text", "semantic", "hybrid"],
                     "description": "full_text = keyword/BM25, semantic = dense vectors, hybrid = both"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            "source_filter": {"type": "string", "description": "Restrict to books whose title contains this text"},
        }}}},
    {"type": "function", "function": {
        "name": "lookup_chunk",
        "description": "Fetch one chunk by id plus neighbouring chunks for context.",
        "parameters": {"type": "object", "required": ["chunk_id", "before", "after"], "properties": {
            "chunk_id": {"type": "string"},
            "before": {"type": "integer", "minimum": 0, "maximum": 5},
            "after": {"type": "integer", "minimum": 0, "maximum": 5},
        }}}},
]

TOOL_SYSTEM = ("You are a research assistant for a corpus of books on Roman history. Use the provided tools "
               "to search; when you already have the evidence you need, answer in plain text without calling tools.")

_HITS = json.dumps({"hits": [
    {"id": "ebook:a4c3c1:001113", "source": "The Consul at Rome", "text": "Consular elections in the late Republic were normally held in July..."},
    {"id": "ebook:a4c3c1:001114", "source": "The Consul at Rome", "text": "In 63, Cicero presided over the electoral process ... wearing a protective cuirass."},
    {"id": "ebook:5be771:000020", "source": "Rome's Enemies Within", "text": "Catiline's supporters gathered in Etruria..."},
]})
_CONTEXT = json.dumps({"chunks": [
    {"id": "ebook:a4c3c1:001113", "text": "Consular elections in the late Republic were normally held in July."},
    {"id": "ebook:a4c3c1:001114", "text": "In 63, Cicero presided over the electoral process. On the day of the elections, Cicero presided over them on the Campus Martius, escorted by his personal guard and wearing a protective cuirass."},
    {"id": "ebook:a4c3c1:001115", "text": "Cicero also succeeded in this battle, and Catiline was not elected."},
]})
_Q63 = "Who presided over the consular elections of 63 BC, and what did he wear? Read the context around the best hit (one chunk each side) before answering."
_CALL1 = {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {
    "name": "search_chunks", "arguments": json.dumps({"query": "consular elections 63 presided", "mode": "full_text", "limit": 3})}}]}
_CALL2 = {"role": "assistant", "content": "", "tool_calls": [{"id": "c2", "type": "function", "function": {
    "name": "lookup_chunk", "arguments": json.dumps({"chunk_id": "ebook:a4c3c1:001114", "before": 1, "after": 1})}}]}

# (messages after system, expected) — expected is a list of (tool name, {arg: check}) that must all be
# called (any order), or ("ANSWER", {"content": check}) for a final text answer with no tool call.
# checks: ("eq", v) | ("has", substr) | ("int", v)
TOOL_CASES = [
    ([{"role": "user", "content": "Find the 5 most relevant passages about the Garamantes using keyword search."}],
     [("search_chunks", {"mode": ("eq", "full_text"), "limit": ("int", 5), "query": ("has", "garamant")})]),
    ([{"role": "user", "content": "Get chunk ebook:d06cc2:000691 with two chunks of context before it and one after."}],
     [("lookup_chunk", {"chunk_id": ("eq", "ebook:d06cc2:000691"), "before": ("int", 2), "after": ("int", 1)})]),
    ([{"role": "user", "content": "Run a semantic search for passages about exile used to escape prosecution; I want 8 results."}],
     [("search_chunks", {"mode": ("eq", "semantic"), "limit": ("int", 8), "query": ("has", "exile")})]),
    ([{"role": "user", "content": "Using hybrid search, find 3 passages about slaves on farms, only from Astin's book Cato the Censor."}],
     [("search_chunks", {"mode": ("eq", "hybrid"), "limit": ("int", 3), "query": ("has", "slave"),
                         "source_filter": ("has", "cato")})]),
    ([{"role": "user", "content": "Show me only the passage immediately after chunk ebook:ffee01:000010, no earlier context."}],
     [("lookup_chunk", {"chunk_id": ("eq", "ebook:ffee01:000010"), "before": ("int", 0), "after": ("int", 1)})]),
    ([{"role": "user", "content": "In one step, run two searches in parallel: a keyword search for 'Lares compitales' and a "
                                  "semantic search for 'household gods worshipped at crossroads', 4 results each."}],
     [("search_chunks", {"mode": ("eq", "full_text"), "limit": ("int", 4), "query": ("has", "compital")}),
      ("search_chunks", {"mode": ("eq", "semantic"), "limit": ("int", 4), "query": ("has", "crossroad")})]),
    ([{"role": "user", "content": _Q63}, _CALL1, {"role": "tool", "tool_call_id": "c1", "content": _HITS}],
     [("lookup_chunk", {"chunk_id": ("eq", "ebook:a4c3c1:001114"), "before": ("int", 1), "after": ("int", 1)})]),
    ([{"role": "user", "content": _Q63}, _CALL1, {"role": "tool", "tool_call_id": "c1", "content": _HITS},
      _CALL2, {"role": "tool", "tool_call_id": "c2", "content": _CONTEXT}],
     [("ANSWER", {"content": ("has", "cicero")}), ("ANSWER", {"content": ("has", "cuirass")})]),
]


def _check(val, kind: str, want) -> bool:
    if kind == "eq":
        return val == want
    if kind == "has":
        return isinstance(val, str) and want in val.lower()
    return type(val) is int and val == want  # strict integer type, not "5"


def bench_tools(model: str, timings: list) -> dict:
    total = 0.0
    for messages, expected in TOOL_CASES:
        msg, dt = chat(model, [{"role": "system", "content": TOOL_SYSTEM}, *messages], tools=TOOLS)
        timings.append(dt)
        msg = msg or {}
        calls = msg.get("tool_calls") or []
        if expected[0][0] == "ANSWER":
            content = re.sub(r"<think>.*?</think>", "", msg.get("content") or "", flags=re.S)
            oks = [not calls] + [_check(content, *chk["content"]) for _, chk in expected]
            total += sum(oks) / len(oks)
            continue
        parsed = []
        for c in calls:
            fn = c.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            parsed.append((fn.get("name"), args if isinstance(args, dict) else {}))
        case_score = 0.0
        for name, checks in expected:  # best-matching actual call per expected call
            best = 0.0
            for got_name, args in parsed:
                oks = [got_name == name] + [_check(args.get(a), *chk) for a, chk in checks.items()]
                best = max(best, sum(oks) / len(oks))
            case_score += best
        # penalise extra calls beyond what was asked
        extra = max(0, len(parsed) - len(expected))
        total += case_score / len(expected) / (1 + extra)
    return {"tool_score": total / len(TOOL_CASES)}


def bench_antfly(model: str, fx: dict, timings: list) -> dict:
    gen = {"provider": "ollama", "model": model, "url": ANTFLY_OLLAMA}
    items = {it["topic"]: it for it in fx["items"]}
    rag = 0
    for case in fx["antfly_rag"]:
        it = items[case["item"]]
        t0 = time.time()
        status, data = http_json(f"{ANTFLY}/db/v1/agents/retrieval", {
            "query": it["question"], "stream": False, "generator": gen,
            "steps": {"generation": {"enabled": True}},
            "queries": [{"table": "rome", "full_text_search": {"query": case["query"]}, "limit": 3}],
        })
        timings.append(time.time() - t0)
        if status == 200 and data.get("status") == "completed":
            text = re.sub(r"<think>.*?</think>", "", str(data.get("generation") or ""), flags=re.S)
            rag += keys_hit(text, it["answer_keys"])
    # query-builder: completed (0.25) + executes with hits (0.25) + top hits contain every expected
    # term (0.25) + top hits come from the requested book, or contain the terms again if none named (0.25)
    qb = 0.0
    for case in fx["query_builder_intents"]:
        t0 = time.time()
        status, data = http_json(f"{ANTFLY}/db/v1/agents/query-builder", {
            "intent": case["intent"], "table": "rome", "generator": gen, "interactive": False,
            "max_internal_iterations": 6,
        })
        timings.append(time.time() - t0)
        if status != 200 or data.get("status") != "completed" or not data.get("query_request"):
            continue
        qb += 0.25
        req = dict(data["query_request"])
        req.pop("table", None)
        req["limit"] = 3
        req["fields"] = ["body", "title", "source_relative_path"]
        s2, res = http_json(f"{ANTFLY}/db/v1/tables/rome/query", req, timeout=60)
        try:
            hits = [h["_source"] for h in res["responses"][0]["hits"]["hits"]]
        except (KeyError, IndexError, TypeError):
            hits = []
        if s2 != 200 or not hits:
            continue
        qb += 0.25
        terms_ok = all(all(t in str(h.get("body", "")).lower() for t in case["terms"]) for h in hits)
        qb += 0.25 * terms_ok
        if case["source"]:
            qb += 0.25 * all(case["source"] in (str(h.get("title", "")) + str(h.get("source_relative_path", ""))).lower()
                             for h in hits)
        else:
            qb += 0.25 * terms_ok
    n_rag, n_qb = len(fx["antfly_rag"]), len(fx["query_builder_intents"])
    return {"antfly_rag_acc": rag / n_rag, "antfly_qb_score": qb / n_qb,
            "antfly_score": 0.5 * rag / n_rag + 0.5 * qb / n_qb}


def main() -> int:
    cfg = json.loads(Path(os.environ.get("BENCH_CONFIG", BENCH / "models.json")).read_text())
    fx = json.loads((BENCH / "fixture.json").read_text())
    t_start = time.time()
    metrics: dict[str, float] = {}

    log(f"embedding: {cfg['embedding']}")
    metrics.update(bench_embed(cfg, fx))

    model = cfg["generator"]
    log(f"generator: {model}")
    status, _ = http_json(f"{OLLAMA}/api/show", {"model": model}, timeout=30)
    if status != 200:
        log(f"generator {model!r} not installed in Ollama")
        return 2
    chat(model, [{"role": "user", "content": "ok"}], max_tokens=8)  # load weights outside timings
    timings: list[float] = []
    metrics.update(bench_qa(model, fx, timings))
    metrics.update(bench_tools(model, timings))
    metrics.update(bench_antfly(model, fx, timings))
    metrics["gen_s_per_call"] = sum(timings) / len(timings)

    metrics["gen_quality"] = (metrics["qa_score"] + metrics["tool_score"] + metrics["antfly_score"]) / 3
    metrics["quality"] = (metrics["embed_mrr10"] + metrics["gen_quality"]) / 2
    metrics["bench_s"] = time.time() - t_start

    print(f"METRIC quality={metrics.pop('quality'):.4f}")
    for k, v in metrics.items():
        print(f"METRIC {k}={v:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
