"""LongMemEval-S through standalone Pi: one Inspect task per memory arm, graded with the official prompts."""

import asyncio
import hashlib
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.log import transcript
from inspect_ai.model import GenerateConfig, ModelOutput, ModelUsage, get_model
from inspect_ai.scorer import CORRECT, INCORRECT, Score, accuracy, scorer, stderr
from inspect_ai.solver import solver
from inspect_ai.util import subprocess

from arms import ARMS, MEMORY_TOOLS, OPENROUTER_ROUTING, PI, configure, pilot_questions, restore

JUDGE_SOURCE = Path(__file__).with_name("evaluate_qa.py")  # LongMemEval @ 9e0b455f, src/evaluation/evaluate_qa.py
if hashlib.sha256(JUDGE_SOURCE.read_bytes()).hexdigest() != "ecce9c4c79dc89d99534ac17b383a5cbb5b9f0c69ee98adaf0684742e3d95251":
    raise RuntimeError("evaluate_qa.py does not match the pinned LongMemEval commit")
from evaluate_qa import get_anscheck_prompt  # noqa: E402

READER_PROMPT = (
    "You are answering a question about the user's past conversations with you. The current date is {date}. "
    "Use your memory tools to look up the relevant history before answering, then answer concisely. "
    "If the information is not in your memory, say that you don't know."
)


@solver
def pi_reader(memory: str, endpoint: str, context_window: int):
    async def solve(state, generate):
        model = state.model.name
        meta = state.metadata
        reader = {"baseUrl": endpoint, "apiKey": "local", "api": "openai-completions",
                  "compat": {"maxTokensField": "max_tokens", "supportsDeveloperRole": False},
                  "models": [{"id": model, "contextWindow": context_window, "maxTokens": 8192}]}
        with TemporaryDirectory(prefix="lme-none-") as scratch:
            if memory == "none":
                home = Path(scratch)
                plugin = ["--no-tools"]
            else:
                home = await asyncio.to_thread(restore, memory, str(state.sample_id))
                plugin = ["-e", str(ARMS[memory]), "--no-builtin-tools"]
            env = configure(home, memory, "read", reader)
            args = [str(PI), "--mode", "json", "--print", "--offline", "--no-session", "--no-skills", "--no-context-files",
                    "--no-prompt-templates", "--no-extensions", *plugin, "--model", f"bench/{model}", "--thinking", "off",
                    "--append-system-prompt", READER_PROMPT.format(date=meta["question_date"]), state.input_text]
            start = time.monotonic()
            result = await subprocess(args, cwd=home / "project", env=env, timeout=600)
            elapsed = time.monotonic() - start
        if result.returncode:
            raise RuntimeError(f"Pi exited {result.returncode}: {result.stderr.strip()[-2000:]}")
        events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
        assistant = [e["message"] for e in events if e.get("type") == "message_end" and e["message"].get("role") == "assistant"]
        if not assistant or any(m.get("model") != model or m.get("stopReason") in ("error", "aborted") for m in assistant):
            raise RuntimeError(f"Pi did not complete on {model}: {[m.get('errorMessage') for m in assistant]}")
        tools = [e["toolName"] for e in events if e.get("type") == "tool_execution_start"]
        final = assistant[-1]
        usage = ModelUsage(input_tokens=sum(m["usage"]["input"] for m in assistant), output_tokens=sum(m["usage"]["output"] for m in assistant),
                           total_tokens=sum(m["usage"]["totalTokens"] for m in assistant))
        answer = "".join(block["text"] for block in final["content"] if block["type"] == "text").strip()
        state.output = ModelOutput.from_content(str(state.model), answer, stop_reason="max_tokens" if final["stopReason"] == "length" else "stop")
        state.output.usage = usage
        memory_calls = sum(name in MEMORY_TOOLS.get(memory, ()) for name in tools)
        meta.update(query_seconds=round(elapsed, 3), memory_calls=memory_calls, retrieved=memory_calls > 0,
                    reader_input_tokens=usage.input_tokens, reader_output_tokens=usage.output_tokens)
        transcript().info({"tools": tools, "pi_messages": assistant})
        return state

    return solve


@scorer(metrics=[accuracy(), stderr()])
def official_judge(judge: str):
    grader = get_model(judge, config=GenerateConfig(temperature=0, max_tokens=256), provider=OPENROUTER_ROUTING)

    async def score(state, target):
        response = state.output.completion
        if not response:
            return Score(value=INCORRECT, answer="", explanation="Pi produced no visible answer.")
        meta = state.metadata
        prompt = get_anscheck_prompt(meta["question_type"], state.input_text, target.text, response,
                                     abstention=str(state.sample_id).endswith("_abs"))
        verdict = (await grader.generate(prompt)).completion
        return Score(value=CORRECT if "yes" in verdict.lower() else INCORRECT, answer=response, explanation=verdict)

    return score


@task
def longmemeval(memory: str = "none", endpoint: str = "http://127.0.0.1:8092/v1", context_window: int = 32768,
                per_category: int = 2, judge: str = "openrouter/google/gemini-3.5-flash-lite"):
    if memory != "none" and memory not in ARMS:
        raise ValueError(f"unknown memory arm {memory}")
    samples = [Sample(id=row["question_id"], input=row["question"], target=str(row["answer"]),
                      metadata={"category": row["category"], "question_type": row["question_type"],
                                "question_date": row["question_date"], "memory": memory})
               for row in pilot_questions(per_category)]
    return Task(dataset=samples, solver=pi_reader(memory, endpoint, context_window), scorer=official_judge(judge),
                metadata={"memory": memory})
