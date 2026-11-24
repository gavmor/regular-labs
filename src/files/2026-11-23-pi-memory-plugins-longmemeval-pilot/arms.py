"""Memory arms under test: plugin paths, per-phase configuration, and frozen snapshots."""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

WS = Path(__file__).resolve().parent
PI = WS / ".pi-runtime/node_modules/.bin/pi"
PLUGINS = WS / ".plugins/node_modules"
ARMS = {
    "pi-memory": PLUGINS / "pi-memory/index.ts",
    "pi-mem": PLUGINS / "pi-mem/index.ts",
    "pi-mem0": PLUGINS / "@lincolness/pi-mem0/src/index.ts",
}
MEMORY_TOOLS = {
    "pi-memory": {"memory_write", "memory_read", "memory_forget", "memory_restore", "memory_search", "memory_status", "scratchpad"},
    "pi-mem": {"search", "timeline", "get_observations", "save_memory"},
    "pi-mem0": {"mem0_memory"},
}
WRITER = "openrouter/google/gemini-3.5-flash-lite"  # same model as the judge; the Gemini free tier allows 15 requests/min
# OpenRouter serves this model from both Vertex and AI Studio; pin one upstream with no fallback.
OPENROUTER_ROUTING = {"order": ["google-vertex"], "allow_fallbacks": False}
EMBED_URL = "http://127.0.0.1:11435/v1"
EMBED_MODEL = "nomic-embed-text"
QMD_MODELS = Path.home() / ".cache/qmd/models"
DATASET_SHA256 = "d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442"


def live_home(arm: str, qid: str) -> Path:
    return WS / "live" / arm / qid / "home"


def snapshot_dir(arm: str, qid: str) -> Path:
    return WS / "snapshots" / arm / qid


def configure(home: Path, arm: str, phase: str, reader: dict | None = None) -> dict[str, str]:
    """Write the per-phase Pi config inside an isolated HOME and return its environment."""
    agent = home / ".pi/agent"
    agent.mkdir(parents=True, exist_ok=True)
    (home / "project").mkdir(exist_ok=True)
    models = home / ".cache/qmd/models"
    if not models.is_symlink():
        models.parent.mkdir(parents=True, exist_ok=True)
        models.symlink_to(QMD_MODELS, target_is_directory=True)
    providers = {"embed": {"baseUrl": EMBED_URL, "apiKey": "ollama", "api": "openai-completions", "models": [{"id": EMBED_MODEL}]},
                 "openrouter": {"modelOverrides": {WRITER.split("/", 1)[1]: {"compat": {"openRouterRouting": OPENROUTER_ROUTING}}}}}
    if reader:
        providers["bench"] = reader
    (agent / "models.json").write_text(json.dumps({"providers": providers}, indent=1))
    (agent / "settings.json").write_text(json.dumps({"mem0": {
        "extractionModel": WRITER,
        "embedder": {"provider": "openai", "config": {"model": EMBED_MODEL, "baseURL": EMBED_URL, "apiKey": "ollama"}},
        "userId": "longmemeval-user",
        "telemetry": False,
        "capture": {"enabled": phase == "ingest"},
    }}, indent=1))
    (agent / "pi-mem.json").write_text(json.dumps({"summaryModel": WRITER, "observerModel": WRITER, "embeddingProvider": "embed", "embeddingModel": EMBED_MODEL, "embeddingDims": 768}, indent=1))
    return {
        **os.environ,
        "PATH": f"{PI.parent}:{os.environ['PATH']}",  # pi-mem spawns `pi` sub-agents by name
        "HOME": str(home),
        "PI_CODING_AGENT_DIR": str(agent),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "PI_MEMORY_QMD_UPDATE": "manual" if phase == "ingest" else "off",
        "PI_MEMORY_EXIT_SUMMARY": "off",
        "QMD_FORCE_CPU": "1",
        "PI_TELEMETRY": "0",
    }


def tree_digest(root: Path) -> str:
    """Content hash of a snapshot tree; symlinks hash by target, not contents."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix().encode()
        if path.is_symlink():
            digest.update(b"L" + rel + b"\0" + os.readlink(path).encode() + b"\0")
        elif path.is_file():
            digest.update(b"F" + rel + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def restore(arm: str, qid: str) -> Path:
    """Copy a verified frozen snapshot over its live path; reads never touch the frozen copy."""
    snap = snapshot_dir(arm, qid)
    manifest = json.loads((snap / "manifest.json").read_text())
    if tree_digest(snap / "home") != manifest["digest"]:
        raise RuntimeError(f"snapshot {arm}/{qid} does not match its manifest")
    home = live_home(arm, qid)
    home.mkdir(parents=True, exist_ok=True)
    subprocess.run(["rsync", "-a", "--delete", f"{snap / 'home'}/", f"{home}/"], check=True)
    return home


def freeze(arm: str, qid: str, record: dict) -> None:
    snap = snapshot_dir(arm, qid)
    if snap.exists():
        shutil.rmtree(snap)
    snap.mkdir(parents=True)
    subprocess.run(["rsync", "-a", f"{live_home(arm, qid)}/", f"{snap / 'home'}/"], check=True)
    record["digest"] = tree_digest(snap / "home")
    tmp = snap / "manifest.json.tmp"
    tmp.write_text(json.dumps(record, indent=1))
    tmp.rename(snap / "manifest.json")


def pilot_questions(per_category: int) -> list[dict]:
    """Deterministic stratified slice of LongMemEval-S; abstention questions form their own stratum."""
    data = (WS / "longmemeval_s_cleaned.json").read_bytes()
    if hashlib.sha256(data).hexdigest() != DATASET_SHA256:
        raise ValueError("LongMemEval-S dataset does not match the pinned release")
    groups: dict[str, list[dict]] = {}
    for row in json.loads(data):
        category = "abstention" if row["question_id"].endswith("_abs") else row["question_type"]
        groups.setdefault(category, []).append({**row, "category": category})
    return [row for category in sorted(groups) for row in sorted(groups[category], key=lambda r: hashlib.sha256(r["question_id"].encode()).digest())[:per_category]]
