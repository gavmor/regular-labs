#!/usr/bin/env python3
"""Inkling 2 Mini smoke test on the RTX 3090 (task t_c6bcc3aa).

Runs inside the gpu-locked Concourse task of concourse/gpu-workload-template.yml.
Stdlib only -- the pinned pytorch image provides Python, the llama.cpp bundle
provides the runtime, this file provides the measurement.

What it does, in order:

  1. Records the starting GPU state (nothing from a previous arm may be resident).
  2. Optional OLLAMA_URL arm: one 8-token request to the host fleet daemon with
     keep_alive=0, to settle empirically whether Ollama can serve this model on
     CUDA-Host (vendor docs list Ollama support for Inkling 2 Mini on Apple
     silicon only). Failure here is recorded, not fatal -- the llama.cpp arm is
     the one under test.
  3. llama.cpp arm: start llama-server with the UD-Q4_K_XL GGUF fully offloaded,
     wait for /health, sample VRAM throughout, generate one fixed prompt at a
     fixed seed, and pull the runtime's own timings out of the response.
  4. Shuts the server down and proves the card is released again.

Pass requires all of: generated text non-empty, >= MIN_NEW_TOKENS new tokens,
>= MIN_TOK_S the runtime's own predicted tokens/second, and >= MIN_VRAM_MIB of
VRAM growth while loaded (a CPU-only fallback would pass the first three and
fail this one).

Exit codes: 0 pass, 1 fail (checks), 2 setup/harness failure.
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------- config ----

MODEL = os.environ.get(
    "MODEL_PATH", "../models/inkling-2-mini/Inkling-2-Mini-UD-Q4_K_XL.gguf"
)
LLAMACPP_DIR = os.environ.get("LLAMACPP_DIR", "../llamacpp/llama-b12588-mix-c0c3de8")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "task-out")

HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", "9931"))
CTX = int(os.environ.get("CTX", "4096"))
N_GPU_LAYERS = os.environ.get("N_GPU_LAYERS", "999")
THREADS = os.environ.get("THREADS", str(max(4, (os.cpu_count() or 8) // 2)))
MIN_NEW_TOKENS = int(os.environ.get("MIN_NEW_TOKENS", "32"))
MIN_TOK_S = float(os.environ.get("MIN_TOK_S", "3.0"))
MIN_VRAM_MIB = int(os.environ.get("MIN_VRAM_MIB", "8000"))
# Free VRAM required before we start loading: 16.4 GiB of weights plus buffers.
MIN_FREE_VRAM_MIB = int(os.environ.get("MIN_FREE_VRAM_MIB", "18000"))
LOAD_TIMEOUT_S = int(os.environ.get("LOAD_TIMEOUT_S", "900"))
GEN_TIMEOUT_S = int(os.environ.get("GEN_TIMEOUT_S", "600"))

PROMPT = os.environ.get(
    "PROMPT",
    "In two sentences, explain why a graphics card's memory bandwidth matters "
    "more than its raw FLOPs when generating tokens from a large language model.",
)
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "320"))
SEED = int(os.environ.get("SEED", "42"))
TEMPERATURE = float(os.environ.get("TEMPERATURE", "0.2"))

OLLAMA_URL = os.environ.get("OLLAMA_URL", "").rstrip("/")
OLLAMA_MODEL = os.environ.get(
    "OLLAMA_MODEL", "hf.co/unsloth/Inkling-2-Mini-GGUF:UD-Q4_K_XL"
)
OLLAMA_TIMEOUT_S = int(os.environ.get("OLLAMA_TIMEOUT_S", "300"))


def log(msg):
    print(f"[inkling2-smoke] {msg}", flush=True)


# ------------------------------------------------------------------ utils ----


def run(cmd, timeout=120, env=None):
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=env
        )
        return {"cmd": cmd, "rc": p.returncode, "out": p.stdout.strip()}
    except Exception as exc:  # noqa: BLE001 - record, never crash the harness
        return {"cmd": cmd, "rc": None, "out": f"{type(exc).__name__}: {exc}"}


def cuda_library_dirs():
    """Locate libcudart/libcublas 12 for the vendored llama.cpp bundle.

    The pinned pytorch runtime image has no /usr/local/cuda: the CUDA 12 runtime
    libraries live in the torch wheels (site-packages/nvidia/*/lib) or a conda
    prefix. libggml-cuda.so links libcudart.so.12, libcublas.so.12 and
    libcublasLt.so.12, so those exact directories have to be on LD_LIBRARY_PATH
    or the CUDA backend silently fails to load and everything runs on CPU.
    """
    wanted = ("libcudart.so.12", "libcublas.so.12", "libcublasLt.so.12")
    roots = []
    try:
        import torch  # noqa: PLC0415 - optional, only to locate its wheels

        mod_path = getattr(torch, "__file__", None)
        if mod_path:
            pkg = os.path.dirname(os.path.dirname(os.path.abspath(mod_path)))
            roots.extend(
                [
                    os.path.join(pkg, "nvidia"),
                    os.path.join(os.path.dirname(pkg), "lib"),
                    "/opt/conda/lib",
                ]
            )
    except Exception:  # noqa: BLE001 - torch is a locator here, not a dependency
        pass
    roots.extend(["/usr/local/cuda/lib64", "/usr/local/nvidia/lib64"])

    found = {}
    for root in roots:
        if not os.path.isdir(root):
            continue
        for base, _dirs, files in os.walk(root):
            for name in files:
                if name in wanted and name not in found:
                    found[name] = base
            if len(found) == len(wanted):
                break
        if len(found) == len(wanted):
            break
    return sorted(set(found.values())), sorted(found)


def gpu_state():
    q = run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.used,utilization.gpu,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    if q["rc"] != 0:
        return {"error": q["out"]}
    name, total, used, util, drv = [f.strip() for f in q["out"].split(",")[:5]]
    return {
        "name": name,
        "memory_total_mib": int(total),
        "memory_used_mib": int(used),
        "utilization_pct": int(util),
        "driver_version": drv,
    }


def http_json(url, payload=None, timeout=60, method=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method or ("POST" if payload is not None else "GET"),
        headers={"Content-Type": "application/json"},
    )
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(body) if body else None
            except json.JSONDecodeError:
                parsed = None
            return {
                "ok": True,
                "status": resp.status,
                "json": parsed,
                "text": body,
                "elapsed_s": round(time.time() - started, 3),
            }
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        return {
            "ok": False,
            "status": exc.code,
            "json": None,
            "text": detail,
            "elapsed_s": round(time.time() - started, 3),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status": None,
            "json": None,
            "text": f"{type(exc).__name__}: {exc}",
            "elapsed_s": round(time.time() - started, 3),
        }


class VramSampler(threading.Thread):
    """0.5 s VRAM/utilization sampler; keeps peak readings across both arms.

    The stop Event is deliberately NOT called ``_stop``: threading.Thread uses
    that name for its own internal method, and shadowing it makes join() raise
    "TypeError: 'Event' object is not callable" -- which is exactly how an
    earlier revision turned a passing 51 tok/s run into a harness_error.
    """

    def __init__(self):
        super().__init__(daemon=True)
        self.samples = []
        self._stop_event = threading.Event()

    def run(self):
        while not self._stop_event.is_set():
            st = gpu_state()
            if "memory_used_mib" in st:
                self.samples.append(
                    (round(time.time(), 2), st["memory_used_mib"], st["utilization_pct"])
                )
            self._stop_event.wait(0.5)

    def stop(self):
        self._stop_event.set()
        self.join(timeout=5)

    def peak(self):
        return max((s[1] for s in self.samples), default=0)

    def peak_util(self):
        return max((s[2] for s in self.samples), default=0)


def tail(path, lines=40):
    try:
        with open(path, "r", errors="replace") as fh:
            return "".join(fh.readlines()[-lines:])
    except OSError:
        return ""


# ------------------------------------------------------------------- arms ----


def ollama_arm(results):
    """Best-effort probe of the fleet Ollama daemon. Never fatal."""
    if not OLLAMA_URL:
        results["ollama_arm"] = {"skipped": "OLLAMA_URL unset"}
        return
    log(f"ollama arm: probing {OLLAMA_URL} (model {OLLAMA_MODEL}, keep_alive=0)")
    ver = http_json(f"{OLLAMA_URL}/api/version", timeout=30)
    arm = {"endpoint": OLLAMA_URL, "model": OLLAMA_MODEL, "version": ver.get("json")}

    started = time.time()
    resp = http_json(
        f"{OLLAMA_URL}/api/chat",
        {
            "model": OLLAMA_MODEL,
            "messages": [{"role": "user", "content": "Reply with the word: ready"}],
            "stream": False,
            "keep_alive": 0,
            "options": {"num_predict": 8, "temperature": 0.2, "seed": SEED},
        },
        timeout=OLLAMA_TIMEOUT_S,
    )
    arm["elapsed_s"] = round(time.time() - started, 1)
    arm["http_status"] = resp["status"]
    if resp["ok"] and resp["json"]:
        msg = (resp["json"].get("message") or {}).get("content", "")
        arm["outcome"] = "generated"
        arm["text"] = msg
        arm["eval_count"] = resp["json"].get("eval_count")
        arm["eval_duration_ns"] = resp["json"].get("eval_duration")
        if resp["json"].get("eval_count") and resp["json"].get("eval_duration"):
            arm["tok_s"] = round(
                resp["json"]["eval_count"]
                / (resp["json"]["eval_duration"] / 1e9),
                2,
            )
    else:
        arm["outcome"] = "error"
        arm["error"] = (resp["text"] or "")[:4000]
    log(f"ollama arm: {arm['outcome']} (status={arm['http_status']}, {arm['elapsed_s']}s)")

    # Wait for the daemon to drop the model so the llama.cpp arm sees free VRAM.
    unloaded = False
    for _ in range(30):
        ps = http_json(f"{OLLAMA_URL}/api/ps", timeout=15)
        models = (ps.get("json") or {}).get("models") or []
        if not models:
            unloaded = True
            break
        time.sleep(2)
    arm["model_unloaded_before_next_arm"] = unloaded
    results["ollama_arm"] = arm
    with open(os.path.join(OUTPUT_DIR, "ollama-arm.json"), "w") as fh:
        json.dump(arm, fh, indent=2, sort_keys=True)


def llamacpp_arm(results):
    # Absolute paths: Popen applies cwd= before exec, so a relative program path
    # would be resolved from inside LLAMACPP_DIR and never be found.
    global MODEL, LLAMACPP_DIR
    MODEL = os.path.abspath(MODEL)
    LLAMACPP_DIR = os.path.abspath(LLAMACPP_DIR)
    server_bin = os.path.join(LLAMACPP_DIR, "llama-server")
    server_log = os.path.join(OUTPUT_DIR, "server.log")
    if not os.path.isfile(server_bin):
        results["verdict"] = "harness_error"
        results["reason"] = f"llama-server not found at {server_bin}"
        return

    cmd = [
        server_bin,
        "--model", MODEL,
        "--ctx-size", str(CTX),
        "--n-gpu-layers", str(N_GPU_LAYERS),
        "--threads", str(THREADS),
        "--host", HOST,
        "--port", str(PORT),
        "--no-webui",
        "--metrics",
        "--parallel", "1",
        "--seed", str(SEED),
        "--temp", str(TEMPERATURE),
    ]
    lib_dirs, lib_found = cuda_library_dirs()
    env = dict(os.environ)
    # /opt/conda/lib is where the pinned image keeps libgomp.so.1 (llama-server
    # is OpenMP-linked and the loader does not search the conda prefix).
    extra = [d for d in ("/opt/conda/lib",) if os.path.isdir(d)]
    env["LD_LIBRARY_PATH"] = os.pathsep.join(
        lib_dirs
        + [LLAMACPP_DIR]
        + extra
        + ([env["LD_LIBRARY_PATH"]] if env.get("LD_LIBRARY_PATH") else [])
    )
    ldd = run(["ldd", os.path.join(LLAMACPP_DIR, "libggml-cuda.so")], env=env)
    ldd_server = run(["ldd", server_bin], env=env)
    unresolved = [
        line.strip()
        for line in ((ldd["out"] or "") + "\n" + (ldd_server["out"] or "")).splitlines()
        if "not found" in line
    ]
    results["cuda_backend"] = {
        "library_dirs": lib_dirs,
        "libraries_found": lib_found,
        "unresolved": unresolved,
        "ldd_libggml_cuda": ldd["out"],
        "ldd_llama_server": ldd_server["out"],
        "LD_LIBRARY_PATH": env["LD_LIBRARY_PATH"],
    }
    log(f"cuda libs found: {lib_found}; unresolved: {len(unresolved)}")
    if unresolved:
        results["verdict"] = "harness_error"
        results["reason"] = (
            "libggml-cuda.so cannot resolve its CUDA libraries: " + "; ".join(unresolved)
        )
        return

    log("llama.cpp arm: starting " + " ".join(cmd))
    base = gpu_state()
    free_mib = base.get("memory_total_mib", 0) - base.get("memory_used_mib", 0)
    results["vram_free_before_load_mib"] = free_mib
    # Refuse to load into a card someone else is holding: the failure would
    # surface as a CUDA allocation error mid-load, which reads like a model
    # problem rather than a busy-GPU problem.
    if free_mib < MIN_FREE_VRAM_MIB:
        results["verdict"] = "harness_error"
        results["reason"] = (
            f"only {free_mib} MiB VRAM free on the 3090 (< {MIN_FREE_VRAM_MIB}); "
            "another process holds the card, refusing to load"
        )
        with open(os.path.join(OUTPUT_DIR, "nvidia-smi.txt"), "w") as fh:
            fh.write(run(["nvidia-smi"]).get("out", "") + "\n")
        return
    sampler = VramSampler()
    sampler.start()

    load_t0 = time.time()
    with open(server_log, "wb") as log_fh:
        proc = subprocess.Popen(
            cmd,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            cwd=LLAMACPP_DIR,
            env=env,
            start_new_session=True,
        )

    health = {"ok": False}
    deadline = load_t0 + LOAD_TIMEOUT_S
    try:
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            health = http_json(f"http://{HOST}:{PORT}/health", timeout=5)
            if health.get("ok"):
                break
            time.sleep(2)
        load_s = round(time.time() - load_t0, 1)
        loaded_state = gpu_state()
        loaded = health.get("ok", False)

        arm = {
            "server_cmd": cmd,
            "load_seconds": load_s,
            "health": health.get("json") or health.get("text"),
            "gpu_before": base,
            "gpu_after_load": loaded_state,
            "ctx_size": CTX,
            "n_gpu_layers": N_GPU_LAYERS,
            "server_exited": proc.poll(),
        }
        if not loaded:
            arm["server_log_tail"] = tail(server_log, 60)
            results["llamacpp_arm"] = arm
            results["verdict"] = "fail"
            results["reason"] = (
                f"llama-server never became healthy in {load_s}s "
                f"(exit={proc.poll()}); see server.log"
            )
            return

        log(f"llama.cpp arm: healthy after {load_s}s, generating {MAX_TOKENS} tokens")
        gen_t0 = time.time()
        gen = http_json(
            f"http://{HOST}:{PORT}/v1/chat/completions",
            {
                "messages": [{"role": "user", "content": PROMPT}],
                "max_tokens": MAX_TOKENS,
                "temperature": TEMPERATURE,
                "seed": SEED,
                "stream": False,
            },
            timeout=GEN_TIMEOUT_S,
        )
        gen_wall_s = round(time.time() - gen_t0, 2)
        arm["generation_wall_seconds"] = gen_wall_s
        arm["generation_http_status"] = gen["status"]

        text, reasoning, timings, usage = "", "", {}, {}
        if gen["ok"] and gen["json"]:
            choice = (gen["json"].get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            text = msg.get("content") or ""
            # This model's chat template enables reasoning preservation by
            # default, so a short generation can put every token on the
            # reasoning channel and leave `content` empty. Both are recorded;
            # the coherence read below uses whichever carries the tokens.
            reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
            timings = gen["json"].get("timings") or {}
            usage = gen["json"].get("usage") or {}
        else:
            # Raw /completion fallback: same model, no chat template in the path.
            log("chat completions failed, falling back to /completion")
            raw = http_json(
                f"http://{HOST}:{PORT}/completion",
                {
                    "prompt": PROMPT,
                    "n_predict": MAX_TOKENS,
                    "temperature": TEMPERATURE,
                    "seed": SEED,
                    "stream": False,
                },
                timeout=GEN_TIMEOUT_S,
            )
            arm["completion_fallback"] = {
                "http_status": raw["status"],
                "error": None if raw["ok"] else (raw["text"] or "")[:2000],
            }
            if raw["ok"] and raw["json"]:
                text = raw["json"].get("content", "") or ""
                timings = raw["json"].get("timings") or {}
                usage = {
                    "prompt_tokens": timings.get("prompt_n"),
                    "completion_tokens": timings.get("predicted_n"),
                }
            else:
                arm["error"] = (gen["text"] or "")[:2000]

        # Runtime-reported throughput is the primary number; the wall-clock
        # figure is a cross-check that includes HTTP and template overhead.
        new_tokens = timings.get("predicted_n") or (usage.get("completion_tokens") or 0)
        tok_s = timings.get("predicted_per_second") or 0.0
        wall_tok_s = round(new_tokens / gen_wall_s, 2) if gen_wall_s else 0.0
        peak = sampler.peak()

        # Coherence is read off whichever channel carries the tokens.
        visible = text if text.strip() else reasoning
        channel = "content" if text.strip() else ("reasoning_content" if reasoning.strip() else "none")
        words = visible.split()
        distinct_ratio = (
            round(len(set(w.lower() for w in words)) / len(words), 3) if words else 0.0
        )
        arm.update(
            {
                "text": text,
                "reasoning_text": reasoning,
                "text_channel": channel,
                "text_chars": len(visible),
                "text_words": len(words),
                "distinct_word_ratio": distinct_ratio,
                "prompt_tokens": timings.get("prompt_n") or usage.get("prompt_tokens"),
                "new_tokens": new_tokens,
                "tok_s_runtime": round(tok_s, 2),
                "tok_s_wall": wall_tok_s,
                "prompt_ms": timings.get("prompt_ms"),
                "predicted_ms": timings.get("predicted_ms"),
                "timings": timings,
                "usage": usage,
                "peak_vram_mib": peak,
                "peak_utilization_pct": sampler.peak_util(),
                "vram_delta_mib": peak - base.get("memory_used_mib", 0),
                "seed": SEED,
                "temperature": TEMPERATURE,
                "max_tokens": MAX_TOKENS,
                "prompt": PROMPT,
            }
        )
        results["llamacpp_arm"] = arm

        with open(os.path.join(OUTPUT_DIR, "output.txt"), "w") as fh:
            fh.write(f"### channel: {channel}\n\n")
            if text.strip():
                fh.write("## content\n" + text + "\n")
            if reasoning.strip():
                fh.write("\n## reasoning_content\n" + reasoning + "\n")
            fh.write(
                f"\n--- seed={SEED} temp={TEMPERATURE} max_tokens={MAX_TOKENS} "
                f"new_tokens={new_tokens} tok_s(runtime)={arm['tok_s_runtime']} "
                f"peak_vram_mib={peak} ---\n"
            )

        failures = []
        if not visible.strip():
            failures.append("generated text is empty on both content and reasoning channels")
        if new_tokens < MIN_NEW_TOKENS:
            failures.append(f"only {new_tokens} tokens generated (< {MIN_NEW_TOKENS})")
        if tok_s < MIN_TOK_S:
            failures.append(
                f"runtime reported {tok_s} tok/s (< {MIN_TOK_S}); likely CPU fallback"
            )
        if arm["vram_delta_mib"] < MIN_VRAM_MIB:
            failures.append(
                f"VRAM grew only {arm['vram_delta_mib']} MiB (< {MIN_VRAM_MIB}); "
                "weights are not resident on the 3090"
            )
        if distinct_ratio and distinct_ratio < 0.15:
            results.setdefault("warnings", []).append(
                f"degenerate repetition: distinct word ratio {distinct_ratio}"
            )
        results["verdict"] = "fail" if failures else "pass"
        if failures:
            results["reason"] = "; ".join(failures)
    finally:
        # Always leave the card free, whatever happened above.
        #
        # Ordered and individually guarded: cleanup must not be able to skip the
        # kill. Build #5 stranded a llama-server holding 17.8 GiB of VRAM for 13
        # minutes because sampler.stop() raised before the SIGTERM ran, and the
        # next build then had no room to load the model.
        def _quiet(step, *args, **kwargs):
            try:
                return step(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                results.setdefault("cleanup_warnings", []).append(
                    f"{getattr(step, '__name__', str(step))}: {type(exc).__name__}: {exc}"
                )
                return None

        _quiet(sampler.stop)
        shutdown: dict = {"exit_before_kill": proc.poll()}
        if proc.poll() is None:
            _quiet(lambda: os.killpg(os.getpgid(proc.pid), signal.SIGTERM))
            for _ in range(30):
                if proc.poll() is not None:
                    break
                time.sleep(1)
        shutdown["exit_after_sigterm"] = proc.poll()
        if proc.poll() is None:
            _quiet(lambda: os.killpg(os.getpgid(proc.pid), signal.SIGKILL))
            _quiet(lambda: proc.wait(timeout=30))
            shutdown["killed_sigkill"] = True
        time.sleep(3)
        shutdown["gpu_after_shutdown"] = gpu_state()
        if "llamacpp_arm" in results:
            results["llamacpp_arm"]["shutdown"] = shutdown
            results["llamacpp_arm"]["vram_samples"] = sampler.samples[
                :: max(1, len(sampler.samples) // 200)
            ]
        results["shutdown"] = shutdown
        with open(os.path.join(OUTPUT_DIR, "gpu-samples.txt"), "w") as fh:
            for ts, used, util in sampler.samples:
                fh.write(f"{ts} {used} {util}\n")


# ------------------------------------------------------------------- main ----


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    results = {
        "task": "t_c6bcc3aa",
        "experiment": "inkling2-mini-smoke",
        "design": "smoke",
        "claim_under_test": (
            "Inkling 2 Mini UD-Q4_K_XL generates coherent text on one RTX 3090 "
            "(24 GiB, sm_86) through the vendor llama.cpp build."
        ),
        "started_at_unix": int(time.time()),
        "gpu_start": gpu_state(),
        "host": run(["uname", "-srm"]).get("out"),
        "python": sys.version.split()[0],
        "config": {
            "model": MODEL,
            "llamacpp_dir": LLAMACPP_DIR,
            "ctx": CTX,
            "n_gpu_layers": N_GPU_LAYERS,
            "threads": THREADS,
            "seed": SEED,
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
            "ollama_url": OLLAMA_URL or None,
        },
    }
    log(f"model: {MODEL}")
    if not os.path.isfile(MODEL):
        results["verdict"] = "harness_error"
        results["reason"] = f"model file missing: {MODEL}"
        write_results(results)
        return 2

    try:
        ollama_arm(results)
        llamacpp_arm(results)
    except Exception as exc:  # noqa: BLE001 - report, never traceback-only
        results["verdict"] = "harness_error"
        results["reason"] = f"{type(exc).__name__}: {exc}"
        write_results(results)
        return 2

    write_results(results)
    return 0 if results.get("verdict") == "pass" else 1


def write_results(results):
    results["finished_at_unix"] = int(time.time())
    with open(os.path.join(OUTPUT_DIR, "results.json"), "w") as fh:
        json.dump(results, fh, indent=2, sort_keys=True, default=str)

    arm = results.get("llamacpp_arm") or {}
    lines = [
        "# Inkling 2 Mini smoke — RESULT",
        "",
        f"verdict: **{results.get('verdict')}**",
        f"reason: {results.get('reason') or 'all checks passed'}",
        "",
        "| measurement | value |",
        "| :-- | :-- |",
        f"| model | `Inkling-2-Mini-UD-Q4_K_XL.gguf` (16.42 GiB) |",
        f"| runtime | llama.cpp `b12588-mix-c0c3de8` linux-x64-cuda12-portable |",
        f"| GPU | {(results.get('gpu_start') or {}).get('name')} "
        f"({(results.get('gpu_start') or {}).get('memory_total_mib')} MiB, driver "
        f"{(results.get('gpu_start') or {}).get('driver_version')}) |",
        f"| load time | {arm.get('load_seconds')} s |",
        f"| new tokens | {arm.get('new_tokens')} |",
        f"| tok/s (runtime) | {arm.get('tok_s_runtime')} |",
        f"| tok/s (wall incl. overhead) | {arm.get('tok_s_wall')} |",
        f"| prompt eval | {arm.get('prompt_tokens')} tokens in "
        f"{round((arm.get('prompt_ms') or 0) / 1000, 2)} s |",
        f"| peak VRAM | {arm.get('peak_vram_mib')} MiB "
        f"(+{arm.get('vram_delta_mib')} MiB over idle) |",
        f"| peak GPU util | {arm.get('peak_utilization_pct')}% |",
        f"| Ollama arm | {(results.get('ollama_arm') or {}).get('outcome', 'skipped')} |",
        "",
        "## Prompt",
        "",
        f"> {arm.get('prompt')}",
        "",
        "## Generated text",
        "",
        f"channel: `{arm.get('text_channel')}`",
        "",
        "```",
        arm.get("text") or "<empty content>",
        "```",
        "",
        "## Reasoning channel (if any)",
        "",
        "```",
        arm.get("reasoning_text") or "<empty>",
        "```",
    ]
    with open(os.path.join(OUTPUT_DIR, "summary.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")

    log(
        f"verdict={results.get('verdict')} reason={results.get('reason') or 'all checks passed'}"
    )
    log(
        "tok_s(runtime)={} new_tokens={} peak_vram_mib={} load_s={}".format(
            arm.get("tok_s_runtime"),
            arm.get("new_tokens"),
            arm.get("peak_vram_mib"),
            arm.get("load_seconds"),
        )
    )
    print(json.dumps({k: v for k, v in results.items() if k != "llamacpp_arm"}, indent=2, default=str), flush=True)


if __name__ == "__main__":
    sys.exit(main())
