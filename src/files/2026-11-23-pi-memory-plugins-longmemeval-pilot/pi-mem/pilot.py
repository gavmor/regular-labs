"""Run the LongMemEval pilot: one hot local reader at a time, every memory arm against frozen snapshots.

Inspect's eval_set owns retries, sample reuse, and resume: rerun this script with the same arguments to continue.
"""

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from inspect_ai import eval_set

from arms import ARMS, WS, pilot_questions, snapshot_dir
from longmemeval import longmemeval

sys.path.insert(0, str(WS.parent / "pi-bench"))
from run import VARIANTS  # noqa: E402  reader GGUF paths from the earlier Pi benchmark

READERS = ["original", "openuncensored", "unbound", "atomicchat", "qwen38"]
PORT = 8092
CTX = 32768  # per slot


def serve(reader: str, log: Path, parallel: int = 1) -> subprocess.Popen:
    """Serve one reader fully on the GPU with `parallel` slots of CTX tokens each."""
    if reader == "original":
        bindir, libs, extra = WS.parents[1] / "llama.cpp", f"{WS.parents[1] / 'llama.cpp'}:/usr/local/lib/ollama/cuda_v13", ["--lazy-mode", "off"]
    else:
        bindir = WS.parent / "b12633/llama-b12633"
        libs, extra = str(bindir), []
    flags = ["-m", str(WS.parent / VARIANTS[reader]), "--alias", reader, "-ngl", "all", "--fit", "off", "-ot", ".*=CUDA0",
             "-fa", "on", "-ctk", "q8_0", "-ctv", "q8_0", "-b", "512", "-ub", "256", "-c", str(CTX * parallel), "-np", str(parallel),
             "--temp", "0", "--seed", "42", "--reasoning-effort", "low", "--reasoning-budget", "4096",
             "--host", "127.0.0.1", "--port", str(PORT), "-lv", "4", *extra]
    server = subprocess.Popen([str(bindir / "llama-server"), *flags], env={"LD_LIBRARY_PATH": libs, "PATH": "/usr/bin:/bin"},
                              stdout=log.open("w"), stderr=subprocess.STDOUT)
    for _ in range(180):
        if server.poll() is not None:
            raise RuntimeError(f"{reader} server exited {server.returncode}; see {log}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/v1/models", timeout=1) as response:
                row, = json.load(response)["data"]
            if row["id"] == reader and row["meta"]["n_ctx"] == CTX:  # reported per slot
                text = log.read_text()
                layers = re.search(r"offloaded (\d+)/(\d+) layers to GPU", text)
                if not layers or layers[1] != layers[2]:
                    raise RuntimeError(f"{reader} is not fully on the GPU; see {log}")
                if f"n_slots = {parallel}, n_ctx_slot = {CTX}" not in text:
                    raise RuntimeError(f"{reader} did not start {parallel} slots of {CTX} tokens; see {log}")
                return server
        except OSError:
            pass
        time.sleep(1)
    server.kill()
    raise RuntimeError(f"{reader} server never became ready; see {log}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reader", choices=READERS, action="append")
    parser.add_argument("--memory", choices=["none", *ARMS], action="append")
    parser.add_argument("--sample", action="append", help="restrict to these question ids (smoke runs)")
    parser.add_argument("--per-category", type=int, default=2)
    parser.add_argument("--log-dir", default="logs/lme-pilot")
    parser.add_argument("--parallel", type=int, default=1, help="llama-server slots and concurrent answers (the pilot used 1)")
    opt = parser.parse_args()
    arms = opt.memory or ["none", *ARMS]
    rows = [row for row in pilot_questions(opt.per_category) if not opt.sample or row["question_id"] in opt.sample]
    missing = [f"{arm}/{row['question_id']}" for arm in arms if arm != "none" for row in rows
               if not (snapshot_dir(arm, row["question_id"]) / "manifest.json").exists()]
    if missing:
        raise SystemExit(f"{len(missing)} snapshots missing (run ingest.py first): {missing[:5]}")
    ok = True
    for reader in opt.reader or READERS:
        log_dir = Path(opt.log_dir) / reader
        log_dir.mkdir(parents=True, exist_ok=True)
        server = serve(reader, log_dir / "llama-server.log", opt.parallel)
        try:
            done, _ = eval_set([longmemeval(memory=arm, per_category=opt.per_category) for arm in arms], model=f"openai/{reader}",
                               model_base_url=f"http://127.0.0.1:{PORT}/v1", log_dir=str(log_dir), max_tasks=1, max_samples=opt.parallel,
                               retry_attempts=2, sample_id=opt.sample, display="plain")
            ok &= done
        finally:
            server.terminate()
            try:
                server.wait(timeout=30)
            except subprocess.TimeoutExpired:
                server.kill()
    if not ok:
        raise SystemExit("some tasks did not complete; rerun the same command to resume")


if __name__ == "__main__":
    main()
