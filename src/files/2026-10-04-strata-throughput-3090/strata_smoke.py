#!/usr/bin/env python3
"""Strata smoke test: start the engine, prove the OpenAI-compatible API, measure
generation throughput.

Runs INSIDE the built Strata image, as the Concourse task's process, while the
job holds gpu-lock. Nothing here is a substitute for the engine: this script
starts the real server and talks to it over HTTP. It never fabricates a number.

Three phases, in this order, because the order is load-bearing:

  1. calibrate (optional, --calibrate)
       `setup.py --calibrate` measures this machine's hardware-dependent engine
       settings and writes them into the run config. It MUST happen before the
       server starts, because the server reads that config at launch. The
       engine's shipped defaults were tuned on a Ryzen 5 7600 + RTX 5070; this
       box is Zen 2 + DDR4 with no AVX-512, so running with the defaults
       measures the defaults, not the hardware.
  2. serve
       `setup.py --port N` loads the model and serves. The port only opens once
       the model is resident, which for Q2_0 is tens of GB off disk into RAM --
       hence the generous --ready-timeout. /health is answered before the API
       key gate, so it is the readiness signal even on a keyed server.
  3. measure
       The prompt is cut from real upstream prose and fitted to ~32K tokens
       AS THE SERVER COUNTS THEM, by probing with max_tokens=1 and reading
       usage.prompt_tokens -- a chars-per-token estimate is not accurate
       enough on technical markdown, and upstream rejects (never truncates) a
       prompt that overruns the context. Then one streamed
       /v1/chat/completions call. Throughput is timed from the FIRST generated
       token, not from the request, so prefill is excluded from the generation
       rate; prefill is reported separately. A rate that silently included
       prefill would understate generation and be wrong in the direction that
       looks like a real result.

Exit 0 means: the engine started, the API answered, and the measured generation
rate met --pass-threshold. Any other outcome exits non-zero with the reason.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import NoReturn

# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def say(msg: str) -> None:
    """Unbuffered, timestamped stdout. Concourse shows this live; a buffered
    log on a 40-minute step looks like a hang."""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def fail(msg: str, code: int = 1) -> NoReturn:
    say(f"FAIL: {msg}")
    sys.exit(code)


class ApiError(Exception):
    """An HTTP error that carries the server's response body.

    urllib raises HTTPError with the body unread; letting that propagate turns
    a precise server-side complaint ("prompt plus max tokens exceed the
    context") into "HTTP Error 400: Bad Request" and costs a whole run to
    diagnose."""

    def __init__(self, status: int, detail: str):
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


def http_json(url: str, payload=None, api_key: str = "", timeout: int = 30):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        # Surface the server's own explanation. Build #3 lost 70 minutes of
        # staging and a turn of the 3090 to a bare "HTTP Error 400: Bad
        # Request" because this body was discarded.
        detail = e.read().decode("utf-8", "replace")[:2000]
        raise ApiError(e.code, detail) from None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"_raw": body}


def run_capture(cmd, cwd=None, env=None, timeout=None, label=""):
    """Run a command, stream it to stdout, return (rc, combined_output)."""
    say(f"$ {' '.join(cmd)}")
    p = subprocess.Popen(
        cmd, cwd=cwd, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    lines = []
    try:
        for line in p.stdout:  # type: ignore[union-attr]
            lines.append(line)
            sys.stdout.write(f"{label}{line}")
            sys.stdout.flush()
        p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()
        return 124, "".join(lines)
    return p.returncode, "".join(lines)


# --------------------------------------------------------------------------
# environment record -- what the measurement is a measurement OF
# --------------------------------------------------------------------------


def describe_environment() -> dict:
    env = {}

    try:
        meminfo = Path("/proc/meminfo").read_text()
        for key in ("MemTotal", "MemAvailable"):
            for line in meminfo.splitlines():
                if line.startswith(key + ":"):
                    env[f"{key.lower()}_kb"] = int(line.split()[1])
    except OSError as e:
        env["meminfo_error"] = str(e)

    # The memlock limit the engine will actually get. The engine page-locks
    # expert tensors; a Concourse task's default hard limit is 8192 KB, which
    # is nowhere near enough. The task wrapper raises it (privileged only) --
    # recording it here means a pinning failure is diagnosable from the results
    # file instead of being mistaken for an engine bug.
    try:
        import resource

        soft, hard = resource.getrlimit(resource.RLIMIT_MEMLOCK)
        env["memlock_soft"] = "unlimited" if soft == resource.RLIM_INFINITY else soft
        env["memlock_hard"] = "unlimited" if hard == resource.RLIM_INFINITY else hard
    except Exception as e:  # pragma: no cover
        env["memlock_error"] = str(e)

    env["nproc"] = os.cpu_count()

    rc, out = run_capture(
        ["nvidia-smi",
         "--query-gpu=name,memory.total,memory.used,driver_version",
         "--format=csv,noheader"],
        label="  nvidia-smi| ",
    )
    env["nvidia_smi_rc"] = rc
    env["nvidia_smi"] = out.strip()
    if rc != 0:
        say("WARNING: nvidia-smi failed. The engine needs the GPU; expect a "
            "load failure below rather than a slow run.")

    return env


# --------------------------------------------------------------------------
# prompt
# --------------------------------------------------------------------------


def read_corpus(doc_dir: Path) -> str:
    """All of the pinned checkout's prose, in a deterministic order.

    Source is the pinned Strata checkout's own docs. It is real
    natural-language text, it is deterministic given the pinned tag, and it
    travels with the pipeline -- no network fetch, no generated filler. Filler
    would be a different workload: repetitive text is unusually compressible
    and flatters the sampler.
    """
    files = sorted(doc_dir.glob("*.md"))
    if not files:
        fail(f"no .md files under {doc_dir} to build the prompt from")
    parts = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        parts.append(f"\n\n===== {f.name} =====\n\n{text}")
    return "".join(parts)


QUESTION = (
    "\n\n===== QUESTION =====\n\n"
    "Using only the document above, write a detailed technical summary of "
    "how this engine divides work between the GPU and system RAM, why it "
    "does so, and what a user must provide for it to run. Write at least "
    "400 words of continuous prose."
)


def count_prompt_tokens(base: str, model: str, prompt: str, api_key: str,
                        timeout: int) -> int:
    """Ask the SERVER how many tokens a prompt is, by generating one token and
    reading usage.prompt_tokens. There is no tokenize endpoint (the server
    exposes /v1/chat/completions, /v1/messages, /v1/responses, /v1/models,
    /props, /slots, /health, /v1/status), so this is the authoritative count
    available to a client."""
    r = http_json(
        f"{base}/v1/chat/completions",
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1,
            "temperature": 0.0,
            "stream": False,
        },
        api_key=api_key, timeout=timeout,
    )
    usage = r.get("usage") or {}
    if not usage.get("prompt_tokens"):
        fail("the server returned no usage.prompt_tokens, so the prompt "
             "cannot be sized against the context. Refusing to guess: a "
             "wrongly-sized prompt measures an unknown context length.")
    return int(usage["prompt_tokens"])


def fit_prompt(base: str, model: str, corpus: str, target_tokens: int,
               api_key: str, timeout: int, rounds: int = 5
               ) -> tuple[str, int, bool]:
    """Cut the corpus to ~target_tokens AS THE SERVER COUNTS THEM.

    Returns (prompt, token_count, was_last_probed). The third value matters:
    fitting sends the candidate prompt to the server, so if the prompt that
    comes back is the one probed last, the engine's KV cache is already warm
    for it and the measured call's time-to-first-token is a cache hit, not a
    prefill. Build #5 reported "182669 tok/s prefill" for exactly that reason
    -- a number that is not a measurement of anything.

    A chars-per-token estimate is not good enough here and build #3 proved it:
    4 chars/token is roughly right for ordinary English, but this corpus is
    technical markdown full of flags, paths and code, which tokenizes far
    denser. The estimate undershot, the real prompt blew past the 32768
    context, and the engine rejected the request -- correctly; upstream
    documents that a prompt plus max_tokens over the context is a 400 and is
    never silently truncated. Silently truncating here would be worse: it
    would measure an unknown context length while claiming 32K.

    So: estimate, ask the server what it actually was, rescale, repeat. Each
    probe is a real prefill and costs seconds, which is cheap against getting
    the measured context wrong.
    """
    chars_per_token = 4.0  # starting estimate only; corrected from round 1 on
    best: tuple[str, int] | None = None
    last_probed: str | None = None

    for attempt in range(1, rounds + 1):
        n_chars = min(int(target_tokens * chars_per_token), len(corpus))
        prompt = corpus[:n_chars] + QUESTION
        try:
            actual = count_prompt_tokens(base, model, prompt, api_key, timeout)
        except ApiError as e:
            if e.status != 400:
                raise
            # Over the context. Back off hard and keep going; the server just
            # told us the estimate is too generous.
            say(f"  fit round {attempt}: {n_chars} chars rejected "
                f"({e.detail.strip()[:160]}); shrinking")
            chars_per_token *= 0.7
            continue

        last_probed = prompt
        chars_per_token = n_chars / actual
        say(f"  fit round {attempt}: {n_chars} chars -> {actual} prompt tokens "
            f"({chars_per_token:.2f} chars/token)")
        if best is None or abs(actual - target_tokens) < abs(best[1] - target_tokens):
            best = (prompt, actual)
        # Within 2% is close enough; further rounds cost a prefill each and
        # buy nothing the measurement can see.
        if abs(actual - target_tokens) <= max(200, target_tokens * 0.02):
            return prompt, actual, True
        if n_chars >= len(corpus) and actual < target_tokens:
            say(f"  the whole corpus is only {actual} tokens; using it all")
            return prompt, actual, True

    if best is None:
        fail("could not fit a prompt inside the context (every probe was "
             "rejected) -- see the server messages above")
    say(f"  settled at {best[1]} prompt tokens after {rounds} rounds")
    return best[0], best[1], best[0] == last_probed


# --------------------------------------------------------------------------
# server lifecycle
# --------------------------------------------------------------------------


def start_server(strata_root: Path, port: int, log_path: Path, extra_args):
    """Launch the engine and tee its output to stdout and to the log file the
    pipeline egresses. Returns the Popen."""
    cmd = [str(strata_root / ".venv" / "bin" / "python"), "setup.py",
           "--port", str(port), *extra_args]
    say(f"starting engine: {' '.join(cmd)}")

    log = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        cmd, cwd=str(strata_root), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1,
        # Own process group, so terminate() reaches the whole engine tree and
        # not just the setup.py launcher.
        start_new_session=True,
    )

    def pump():
        for line in proc.stdout:  # type: ignore[union-attr]
            log.write(line)
            log.flush()
            sys.stdout.write(f"  engine| {line}")
            sys.stdout.flush()
        log.close()

    threading.Thread(target=pump, daemon=True).start()
    return proc


def wait_until_ready(base: str, proc, timeout_s: int, api_key: str) -> dict:
    """Poll /health until the model is loaded. /health is answered before the
    API key gate, so it works with or without a key."""
    say(f"waiting up to {timeout_s}s for {base}/health")
    deadline = time.time() + timeout_s
    last = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            fail(f"the engine exited with code {proc.returncode} before the "
                 f"API came up -- see the engine log above")
        try:
            health = http_json(f"{base}/health", timeout=10)
            state = json.dumps(health, sort_keys=True)
            if state != last:
                say(f"/health -> {state}")
                last = state
            # Accept any shape that does not say it is still loading. The
            # engine answers /health before it is ready, so "200 OK" alone is
            # not readiness.
            status = str(health.get("status", health.get("state", ""))).lower()
            if status in ("ok", "ready", "healthy", "serving"):
                return health
            if health.get("ready") is True or health.get("loaded") is True:
                return health
            if not status and "_raw" not in health:
                return health
        except (urllib.error.URLError, OSError, TimeoutError):
            pass
        time.sleep(5)
    fail(f"the API did not become ready within {timeout_s}s")
    return {}


# --------------------------------------------------------------------------
# the measured call
# --------------------------------------------------------------------------


def measure(base: str, model: str, prompt: str, max_tokens: int,
            reasoning_budget: int, api_key: str, timeout_s: int,
            prompt_was_prefilled: bool = False) -> dict:
    """One streamed completion. Generation rate is timed from the first token.

    Qwen3.8-Flash-Next is a THINKING model: it emits `reasoning_content`
    deltas before any `content`. Build #4 counted only `content`, saw none,
    and reported "the server streamed no content at all" -- while the engine's
    own log said it had generated 512 tokens at 103.7 tok/s and run out of
    budget mid-thought. Two consequences, both handled here:

      - Reasoning tokens ARE generated tokens. They go through the same decode
        path at the same rate, so the throughput window opens at the first
        token of EITHER kind. Counting only the answer would time the
        reasoning as if it were latency and understate the rate badly.
      - The request needs a reasoning budget, or the model thinks until
        max_tokens and never answers. The split is recorded so a run that was
        mostly thinking is visible rather than implied.
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,   # deterministic sampling; this is a throughput
                              # measurement, not a quality one
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if reasoning_budget > 0:
        payload["reasoning_budget_tokens"] = reasoning_budget
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    say(f"POST {base}/v1/chat/completions  (prompt {len(prompt)} chars, "
        f"streaming, max_tokens={max_tokens}, "
        f"reasoning_budget_tokens={reasoning_budget})")

    req = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=json.dumps(payload).encode(), headers=headers,
    )

    t_request = time.monotonic()
    t_first = None
    t_last = None
    n_chunks = 0
    answer_parts = []
    reasoning_parts = []
    usage = None
    # Keep the head of the raw stream. When nothing parses, this is the only
    # evidence of why -- the same lesson as reading the HTTP error body.
    raw_head = []

    try:
        resp = urllib.request.urlopen(req, timeout=timeout_s)
    except urllib.error.HTTPError as e:
        raise ApiError(e.code, e.read().decode("utf-8", "replace")[:2000]) from None

    with resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if len(raw_head) < 40 and line:
                raw_head.append(line[:400])
            if not line.startswith("data:"):
                continue
            body = line[5:].strip()
            if body == "[DONE]":
                break
            try:
                chunk = json.loads(body)
            except json.JSONDecodeError:
                continue
            if chunk.get("error"):
                raise ApiError(200, json.dumps(chunk["error"]))
            if chunk.get("usage"):
                usage = chunk["usage"]
            for choice in chunk.get("choices", []):
                delta = choice.get("delta") or {}
                content = delta.get("content") or ""
                reasoning = delta.get("reasoning_content") or ""
                if not content and not reasoning:
                    continue
                now = time.monotonic()
                if t_first is None:
                    t_first = now
                    say(f"first token after {t_first - t_request:.2f}s "
                        f"(prefill)")
                t_last = now
                n_chunks += 1
                if content:
                    answer_parts.append(content)
                if reasoning:
                    reasoning_parts.append(reasoning)

    if t_first is None:
        say("the server streamed no tokens. Raw stream head:")
        for line in raw_head:
            say(f"  | {line}")
        fail("no tokens were streamed -- see the raw stream above and the "
             "engine log")

    answer = "".join(answer_parts)
    reasoning = "".join(reasoning_parts)
    gen_seconds = max((t_last or t_first) - t_first, 1e-9)
    prefill_seconds = t_first - t_request

    # Prefer the server's own token accounting; fall back to the streamed chunk
    # count, which for this engine is one chunk per token but is NOT guaranteed
    # to be, so the fallback is labelled in the result.
    if usage and usage.get("completion_tokens"):
        completion_tokens = int(usage["completion_tokens"])
        token_source = "usage.completion_tokens"
    else:
        completion_tokens = n_chunks
        token_source = "streamed-chunk-count (server reported no usage)"

    prompt_tokens = int(usage.get("prompt_tokens", 0)) if usage else 0

    # The rate over the generation window excludes the first token itself, which
    # was produced by prefill: n tokens arrive at n-1 inter-token intervals.
    gen_tok_s = (completion_tokens - 1) / gen_seconds if completion_tokens > 1 else 0.0

    # Time-to-first-token is only a prefill measurement when the prefill
    # actually happened in this call. The fit probes send candidate prompts to
    # the server, so the winning prompt's KV cache is usually already warm and
    # the first token arrives in milliseconds. Reporting that as a prefill rate
    # produced "182669 tok/s" in build #5 -- a number with no referent.
    # Generation rate is unaffected: those tokens are decoded here either way.
    if prompt_was_prefilled:
        prefill_rate = None
        prefill_note = (
            "not measured: the prompt-fitting probes already sent this exact "
            "prompt, so the engine's KV cache was warm and time-to-first-token "
            "is a cache hit, not a prefill. Generation rate is unaffected.")
    elif prompt_tokens and prefill_seconds > 0:
        prefill_rate = round(prompt_tokens / prefill_seconds, 1)
        prefill_note = "measured on a cold prompt"
    else:
        prefill_rate = None
        prefill_note = "not available: the server reported no prompt_tokens"

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "completion_token_source": token_source,
        "time_to_first_token_s": round(prefill_seconds, 3),
        "prefill_tok_s": prefill_rate,
        "prefill_note": prefill_note,
        "generation_seconds": round(gen_seconds, 3),
        "generation_tok_s": round(gen_tok_s, 2),
        "generation_window": "first streamed token (reasoning or content) to last",
        "usage": usage,
        "streamed_chunks": n_chunks,
        "answer_chars": len(answer),
        "reasoning_chars": len(reasoning),
        "answer_head": answer[:600],
        "reasoning_head": reasoning[:600],
    }


# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strata-root", default="/opt/strata")
    ap.add_argument("--data-dir", required=True,
                    help="the prepared Strata data dir (models, pack, config)")
    ap.add_argument("--doc-dir", required=True,
                    help="directory of .md files the ~32K prompt is built from")
    ap.add_argument("--results-dir", required=True)
    ap.add_argument("--model", default="Q2_0")
    ap.add_argument("--family", default="qwen")
    ap.add_argument("--context", type=int, default=32768)
    ap.add_argument("--prompt-tokens", type=int, default=30000,
                    help="target prompt size; kept under --context to leave "
                         "room for the answer")
    ap.add_argument("--min-completion-tokens", type=int, default=256,
                    help="below this the rate is a burst, not a sustained "
                         "generation rate")
    ap.add_argument("--max-tokens", type=int, default=2048,
                    help="the completion cap. Counts against the context: "
                         "upstream rejects prompt+max_tokens over the context")
    ap.add_argument("--reasoning-budget-tokens", type=int, default=1024,
                    help="carved OUT of --max-tokens. This model thinks before "
                         "it answers; with no budget it thinks until the cap "
                         "and returns no answer. 0 disables the budget.")
    ap.add_argument("--pass-threshold", type=float, default=100.0,
                    help="generation tok/s the run must meet to exit 0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--api-key", default=os.environ.get("STRATA_API_KEY", ""))
    ap.add_argument("--ready-timeout", type=int, default=2400)
    ap.add_argument("--call-timeout", type=int, default=1800)
    ap.add_argument("--calibrate", action="store_true",
                    help="run setup.py --calibrate before serving (spec "
                         "requires this once; it rewrites the run config)")
    ap.add_argument("--calibrate-timeout", type=int, default=2400)
    args = ap.parse_args()

    strata_root = Path(args.strata_root)
    data_dir = Path(args.data_dir).resolve()
    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    base = f"http://127.0.0.1:{args.port}"

    tag = (("" if args.family == "qwen" else f"{args.family}-")
           + args.model.lower())
    cfg_src = data_dir / "config" / f"strata-{tag}.json"
    cfg_dst = strata_root / f"strata-{tag}.json"

    say("=" * 72)
    say(f"Strata smoke test: {args.family}/{args.model} @ {args.context} ctx")
    say("=" * 72)

    # ---- the install config lives on the data dir; the engine looks for it
    # next to setup.py. Same handoff the upstream docker-entrypoint.sh does.
    if not cfg_src.is_file():
        fail(f"no prepared install config at {cfg_src}. The prepare-weights "
             f"task is what writes it; this task does not download or install.")
    if not cfg_dst.exists():
        cfg_dst.symlink_to(cfg_src)
    say(f"install config: {cfg_dst} -> {cfg_src}")

    results = {
        "experiment": "strata-smoke",
        "arm_id": f"strata_{args.model.lower()}_{args.context // 1024}k",
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": args.model,
        "family": args.family,
        "context_tokens": args.context,
        "pass_threshold_tok_s": args.pass_threshold,
        "config": json.loads(cfg_src.read_text()),
        "environment": describe_environment(),
    }

    proc = None
    try:
        # ---- 1. calibrate ------------------------------------------------
        if args.calibrate:
            say("--- calibrating the engine for this machine ---")
            rc, out = run_capture(
                [str(strata_root / ".venv" / "bin" / "python"), "setup.py",
                 "--calibrate", "--no-start"],
                cwd=str(strata_root), timeout=args.calibrate_timeout,
                label="  calibrate| ",
            )
            results["calibrate"] = {
                "rc": rc,
                "tail": out[-4000:],
                # What it chose is the point: record the config AFTER, so the
                # measured run is attributable to specific settings.
                "config_after": json.loads(cfg_src.read_text())
                if cfg_src.is_file() else None,
            }
            if rc != 0:
                say(f"WARNING: --calibrate exited {rc}; continuing with the "
                    f"settings currently in the config. The measurement is "
                    f"then of UNCALIBRATED defaults -- recorded as such.")

        # ---- 2. serve ----------------------------------------------------
        log_path = results_dir / f"strata-{args.model}.log"
        proc = start_server(strata_root, args.port, log_path, [])
        health = wait_until_ready(base, proc, args.ready_timeout, args.api_key)
        results["health"] = health
        say("API is up.")

        try:
            results["status"] = http_json(f"{base}/v1/status",
                                          api_key=args.api_key)
            say(f"/v1/status -> {json.dumps(results['status'])[:800]}")
        except Exception as e:
            say(f"note: /v1/status unavailable ({e}); not fatal")

        try:
            results["models"] = http_json(f"{base}/v1/models",
                                          api_key=args.api_key)
            say(f"/v1/models -> {json.dumps(results['models'])[:400]}")
        except Exception as e:
            say(f"note: /v1/models unavailable ({e}); not fatal")

        # ---- 3. measure --------------------------------------------------
        served_model = args.model
        try:
            served_model = results["models"]["data"][0]["id"]
        except Exception:
            pass

        # max_tokens is part of the context budget: upstream rejects a request
        # whose prompt PLUS max_tokens exceeds the context, so the prompt has
        # to be sized against what is left after reserving the answer.
        #
        # The reasoning budget is carved out of max_tokens, not added to it.
        # Without one this thinking model spends the whole allowance thinking
        # and returns no answer at all -- build #4, where the engine said "the
        # reply reached max tokens while still thinking, so it has no answer".
        max_tokens = args.max_tokens
        reasoning_budget = args.reasoning_budget_tokens
        if 0 < max_tokens <= reasoning_budget:
            fail(f"--reasoning-budget-tokens ({reasoning_budget}) leaves no "
                 f"room under --max-tokens ({max_tokens}) for an answer")
        target = args.prompt_tokens
        ceiling = args.context - max_tokens - 256   # 256: chat-template overhead
        if target > ceiling:
            say(f"note: --prompt-tokens {target} leaves no room for a "
                f"{max_tokens}-token answer in a {args.context} context; "
                f"targeting {ceiling} instead")
            target = ceiling

        say(f"--- fitting the prompt to ~{target} tokens (server-counted) ---")
        corpus = read_corpus(Path(args.doc_dir))
        say(f"corpus: {len(corpus)} chars of upstream docs")
        prompt, prompt_tokens, warm = fit_prompt(
            base, served_model, corpus, target, args.api_key, args.call_timeout)
        results["prompt_fit"] = {
            "target_tokens": target,
            "fitted_tokens": prompt_tokens,
            "prompt_chars": len(prompt),
            "max_tokens": max_tokens,
            "reasoning_budget_tokens": reasoning_budget,
            "corpus_chars": len(corpus),
            "kv_cache_warm_for_this_prompt": warm,
        }

        m = measure(base, served_model, prompt, max_tokens, reasoning_budget,
                    args.api_key, args.call_timeout,
                    prompt_was_prefilled=warm)
        results["measurement"] = m

        say("-" * 72)
        say(f"prompt tokens      : {m['prompt_tokens']}")
        say(f"completion tokens  : {m['completion_tokens']} "
            f"({m['completion_token_source']})")
        say(f"  of which thinking: {m['reasoning_chars']} chars reasoning, "
            f"{m['answer_chars']} chars answer")
        say(f"time to 1st token : {m['time_to_first_token_s']}s  "
            f"({m['prefill_note']})")
        say(f"generation         : {m['generation_seconds']}s  "
            f"-> {m['generation_tok_s']} tok/s")
        say("-" * 72)

        # ---- verdict -----------------------------------------------------
        problems = []
        if m["completion_tokens"] < args.min_completion_tokens:
            problems.append(
                f"only {m['completion_tokens']} completion tokens, "
                f"below the {args.min_completion_tokens} the measurement needs "
                f"to be sustained rather than a burst")
        if not m["answer_chars"]:
            problems.append(
                "the model produced reasoning but never an answer, so the run "
                "did not exercise a complete request; raise --max-tokens or "
                "lower --reasoning-budget-tokens")
        if m["generation_tok_s"] < args.pass_threshold:
            problems.append(
                f"{m['generation_tok_s']} tok/s is below the "
                f"{args.pass_threshold} tok/s threshold")

        results["problems"] = problems
        results["passed"] = not problems
        return 0 if not problems else 2

    except ApiError as e:
        # Record what the SERVER said, in the results file as well as the log.
        # An unexplained 400 in a build log is a dead end; the body is the
        # whole diagnosis.
        say(f"FAIL: the API rejected the request -- HTTP {e.status}")
        say(f"server said: {e.detail}")
        results["problems"] = [f"HTTP {e.status} from the API: {e.detail}"]
        results["passed"] = False
        return 3

    finally:
        if proc is not None and proc.poll() is None:
            say("stopping the engine")
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                proc.wait(timeout=120)
            except Exception:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    pass
        results["ended_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        out = results_dir / "results.json"
        out.write_text(json.dumps(results, indent=2, default=str))
        say(f"wrote {out}")


if __name__ == "__main__":
    rc = main()
    if rc == 0:
        say("PASS")
    else:
        say("FAIL -- see problems[] in results.json")
    sys.exit(rc)
