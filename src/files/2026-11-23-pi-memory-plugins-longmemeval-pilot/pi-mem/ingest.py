"""Build one frozen memory snapshot per (arm, question) by replaying LongMemEval history through Pi.

A fixed writer model saves durable facts with each plugin's native tools, one fresh Pi conversation per history
session. Each snapshot is one Inspect sample: eval_set owns concurrency (max_samples, retunable mid-run with
`inspect ctl config --max-samples N`), resume, and sample retries. Pi's own auto-retry handles transient provider
errors inside a conversation; a conversation counts as failed only when Pi gives up. Frozen snapshots
(snapshots/<arm>/<qid>/manifest.json) are skipped, so snapshots built outside this log directory are reused.
"""

import argparse
import asyncio
import json
import shutil
import time
from functools import cache

from inspect_ai import Task, eval_set, task
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput
from inspect_ai.scorer import CORRECT, INCORRECT, Score, accuracy, scorer
from inspect_ai.solver import solver
from inspect_ai.util import subprocess

from arms import ARMS, MEMORY_TOOLS, PI, WRITER, configure, freeze, live_home, pilot_questions, snapshot_dir, tree_digest

WRITER_PROMPT = (
    "You maintain this user's long-term memory. Each message you receive is one past conversation between the user "
    "and an AI assistant. Save everything from it that could matter in a future conversation, using your memory tools: "
    "facts about the user, events, plans, preferences, possessions, people, numbers and dates, changes to anything "
    "known before, and specific things the assistant told or recommended to the user. Include the conversation date "
    "with each memory. Do not reply to the conversation itself."
)


def render(session: list[dict], date: str) -> str:
    turns = "\n".join(f"[{turn['role']}]: {turn['content']}" for turn in session)
    return f'<conversation date="{date}">\n{turns}\n</conversation>'


class Rpc:
    def __init__(self, proc):
        self.proc = proc
        self.counter = 0

    async def command(self, payload: dict, until: str | None = None) -> list[dict]:
        """Send one command and collect events until its response (or the named terminal event)."""
        self.counter += 1
        rid = f"c{self.counter}"
        self.proc.stdin.write((json.dumps({**payload, "id": rid}) + "\n").encode())
        await self.proc.stdin.drain()
        events, answered = [], False
        while True:
            line = await asyncio.wait_for(self.proc.stdout.readline(), timeout=600)
            if not line:
                raise RuntimeError(f"Pi exited during {payload['type']}")
            try:
                event = json.loads(line)
            except ValueError:
                continue
            events.append(event)
            if event.get("type") == "response" and event.get("id") == rid:
                if not event.get("success"):
                    raise RuntimeError(f"{payload['type']} failed: {event.get('error')}")
                if until is None or (event.get("data") or {}).get("disposition") == "handled":
                    return events
                answered = True
            elif answered and event.get("type") == until:
                return events


async def settle(arm: str, home) -> None:
    """Wait for each plugin's background writes to finish before freezing."""
    deadline = time.monotonic() + 900
    if arm == "pi-mem0":
        data = home / ".pi/agent/mem0"
        quiet = 0
        while quiet < 5:
            pending = [p for p in (data / "outbox").glob("*") if not p.name.startswith(".")]
            quiet = 0 if pending else quiet + 1
            if time.monotonic() > deadline:
                raise RuntimeError(f"mem0 outbox still has {len(pending)} items")
            await asyncio.sleep(1)
        failed = list((data / "outbox-failed").glob("*.json"))
        if failed:
            raise RuntimeError(f"mem0 gave up on {len(failed)} extraction items")
    elif arm == "pi-mem":
        lance = home / ".pi-mem/lancedb"
        while True:
            newest = max((p.stat().st_mtime for p in lance.rglob("*") if p.is_file()), default=0)
            if newest and time.time() - newest > 30:
                return
            if time.monotonic() > deadline:
                raise RuntimeError("pi-mem store never went quiet")
            await asyncio.sleep(5)


async def build(arm: str, row: dict) -> None:
    qid = row["question_id"]
    root = live_home(arm, qid).parent
    shutil.rmtree(root, ignore_errors=True)
    home = live_home(arm, qid)
    env = configure(home, arm, "ingest")
    log = (root / "pi.stderr").open("wb")
    args = [str(PI), "--mode", "rpc", "--offline", "--no-extensions", "-e", str(ARMS[arm]), "--no-skills", "--no-context-files",
            "--no-prompt-templates", "--no-builtin-tools", "--model", WRITER, "--thinking", "low",
            "--session-dir", str(root / "sessions"), "--append-system-prompt", WRITER_PROMPT]
    proc = await asyncio.create_subprocess_exec(*args, cwd=home / "project", env=env, stdin=asyncio.subprocess.PIPE,
                                                stdout=asyncio.subprocess.PIPE, stderr=log, limit=64 * 1024 * 1024)
    rpc = Rpc(proc)
    start = time.monotonic()
    usage = {"input": 0, "output": 0, "cacheRead": 0, "turns": 0}
    sessions = []
    try:
        pairs = sorted(zip(row["haystack_dates"], row["haystack_sessions"]), key=lambda pair: pair[0])
        for index, (date, session) in enumerate(pairs):
            if index:
                await rpc.command({"type": "new_session"})
            turns = [{"role": t["role"], "content": t["content"]} for t in session]  # drop has_answer evidence labels
            events = await rpc.command({"type": "prompt", "message": render(turns, date)}, until="agent_settled")
            ended = [e["message"] for e in events if e.get("type") == "message_end" and (e.get("message") or {}).get("role") == "assistant"]
            for msg in ended:
                for key in ("input", "output", "cacheRead"):
                    usage[key] += msg.get("usage", {}).get(key, 0)
                usage["turns"] += 1
            if not ended or ended[-1].get("stopReason") in ("error", "aborted"):
                raise RuntimeError(f"writer failed on session {index} after Pi's retries: {ended[-1].get('errorMessage') if ended else 'no reply'}")
            calls = [e["toolName"] for e in events if e.get("type") == "tool_execution_start"]
            sessions.append({"memory_calls": sum(c in MEMORY_TOOLS[arm] for c in calls),
                             "pi_retries": sum(e.get("type") == "auto_retry_start" for e in events)})
        await rpc.command({"type": "new_session"})  # finalize the last session's capture and drain queues
        await settle(arm, home)
    finally:
        proc.stdin.close()
        try:
            await asyncio.wait_for(proc.wait(), timeout=120)
        except TimeoutError:
            proc.kill()
            await proc.wait()
        log.close()
    if arm == "pi-memory":
        for step in (["qmd", "update"], ["qmd", "embed"]):
            result = await subprocess(step, cwd=home / "project", env=env, timeout=1800)
            if not result.success:
                raise RuntimeError(f"{' '.join(step)} failed: {result.stderr[-500:]}")
    calls = sum(s["memory_calls"] for s in sessions)
    if not calls:
        raise RuntimeError(f"{arm}/{qid}: writer never called a memory tool")
    freeze(arm, qid, {"arm": arm, "question_id": qid, "writer": WRITER, "sessions": len(sessions), "memory_calls": calls,
                      "sessions_without_writes": sum(not s["memory_calls"] for s in sessions), "writer_usage": usage,
                      "pi_retries": sum(s["pi_retries"] for s in sessions), "seconds": round(time.monotonic() - start, 1)})


@cache
def questions(per_category: int) -> dict[str, dict]:
    return {row["question_id"]: row for row in pilot_questions(per_category)}


@solver
def build_snapshot(per_category: int):
    async def solve(state, generate):
        arm, qid = state.metadata["arm"], state.metadata["question_id"]
        manifest = snapshot_dir(arm, qid) / "manifest.json"
        if not manifest.exists():
            await build(arm, questions(per_category)[qid])
        record = json.loads(manifest.read_text())
        state.output = ModelOutput.from_content("mockllm/model", json.dumps({k: v for k, v in record.items() if k != "digest"}))
        return state

    return solve


@scorer(metrics=[accuracy()])
def frozen():
    """A snapshot passes when its frozen tree matches the digest recorded at freeze time."""
    async def score(state, target):
        snap = snapshot_dir(state.metadata["arm"], state.metadata["question_id"])
        ok = await asyncio.to_thread(lambda: tree_digest(snap / "home") == json.loads((snap / "manifest.json").read_text())["digest"])
        return Score(value=CORRECT if ok else INCORRECT)

    return score


@task
def snapshots(arms: list[str], per_category: int):
    if unknown := set(arms) - set(ARMS):
        raise ValueError(f"unknown memory arms {sorted(unknown)}")
    samples = [Sample(id=f"{arm}:{qid}", input=qid, metadata={"arm": arm, "question_id": qid})
               for qid in questions(per_category) for arm in arms]
    return Task(dataset=samples, solver=build_snapshot(per_category), scorer=frozen())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-category", type=int, default=2)
    parser.add_argument("--arm", choices=ARMS, action="append")
    parser.add_argument("--jobs", type=int, default=8, help="initial max_samples; retune live with `inspect ctl config --max-samples N`")
    parser.add_argument("--sample", action="append", help="restrict to these sample ids, e.g. pi-mem:1d4da289")
    parser.add_argument("--log-dir")
    opt = parser.parse_args()
    arms = opt.arm or list(ARMS)
    done, _ = eval_set([snapshots(arms=arms, per_category=opt.per_category)], model="mockllm/model",
                       log_dir=opt.log_dir or f"logs/ingest-{opt.per_category}pc", max_tasks=1, max_samples=opt.jobs,
                       retry_on_error=2, retry_attempts=2, sample_id=opt.sample, display="plain")
    if not done:
        raise SystemExit("some snapshots did not complete; rerun the same command to resume")


if __name__ == "__main__":
    main()
