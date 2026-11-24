"""Build one frozen memory snapshot per (arm, question) by replaying LongMemEval history through Pi.

A fixed writer model saves durable facts with each plugin's native tools, one fresh Pi conversation
per history session. Completed snapshots (snapshots/<arm>/<qid>/manifest.json) are skipped on rerun.
"""

import argparse
import asyncio
import json
import shutil
import subprocess
import time

from arms import ARMS, MEMORY_TOOLS, PI, WRITER, configure, freeze, live_home, pilot_questions, snapshot_dir

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


async def ingest(arm: str, row: dict) -> None:
    qid = row["question_id"]
    if (snapshot_dir(arm, qid) / "manifest.json").exists():
        return
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
    sessions, retries = [], []
    try:
        pairs = sorted(zip(row["haystack_dates"], row["haystack_sessions"]), key=lambda pair: pair[0])
        for index, (date, session) in enumerate(pairs):
            turns = [{"role": t["role"], "content": t["content"]} for t in session]  # drop has_answer evidence labels
            for attempt in range(1, 4):
                if index or attempt > 1:
                    await rpc.command({"type": "new_session"})
                events = await rpc.command({"type": "prompt", "message": render(turns, date)}, until="agent_settled")
                ended = [e["message"] for e in events if e.get("type") == "message_end" and (e.get("message") or {}).get("role") == "assistant"]
                for msg in ended:
                    for key in ("input", "output", "cacheRead"):
                        usage[key] += msg.get("usage", {}).get(key, 0)
                    usage["turns"] += 1
                failure = next((m.get("errorMessage") for m in ended if m.get("stopReason") in ("error", "aborted")), None)
                if failure is None:
                    break
                retries.append({"session": index, "attempt": attempt, "error": str(failure)[:300]})
                if attempt == 3:
                    raise RuntimeError(f"writer failed on session {index} after 3 attempts: {failure}")
                await asyncio.sleep(10 * attempt)
            calls = [e["toolName"] for e in events if e.get("type") == "tool_execution_start"]
            sessions.append({"date": date, "memory_calls": sum(c in MEMORY_TOOLS[arm] for c in calls), "attempts": attempt})
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
            subprocess.run(step, cwd=home / "project", env=env, check=True, capture_output=True, timeout=1800)
    calls = sum(s["memory_calls"] for s in sessions)
    if not calls:
        raise RuntimeError(f"{arm}/{qid}: writer never called a memory tool")
    freeze(arm, qid, {"arm": arm, "question_id": qid, "writer": WRITER, "sessions": len(sessions), "memory_calls": calls,
                      "sessions_without_writes": sum(not s["memory_calls"] for s in sessions), "writer_usage": usage,
                      "retries": retries, "seconds": round(time.monotonic() - start, 1)})
    print(f"froze {arm}/{qid}: {len(sessions)} sessions, {calls} memory calls, {time.monotonic() - start:.0f}s", flush=True)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-category", type=int, default=2)
    parser.add_argument("--arm", choices=ARMS, action="append")
    parser.add_argument("--question", action="append")
    parser.add_argument("--jobs", type=int, default=6)
    opt = parser.parse_args()
    rows = [r for r in pilot_questions(opt.per_category) if not opt.question or r["question_id"] in opt.question]
    gate = asyncio.Semaphore(opt.jobs)
    failures = []

    async def job(arm, row):
        async with gate:
            try:
                await ingest(arm, row)
            except Exception as error:
                failures.append(f"{arm}/{row['question_id']}: {error}")
                print(f"FAILED {failures[-1]}", flush=True)

    await asyncio.gather(*(job(arm, row) for row in rows for arm in (opt.arm or ARMS)))
    if failures:
        raise SystemExit(f"{len(failures)} snapshot(s) failed; rerun to retry them")


if __name__ == "__main__":
    asyncio.run(main())
