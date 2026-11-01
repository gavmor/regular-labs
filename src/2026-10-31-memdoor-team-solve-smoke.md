# Memdoor's eight-role DAG solves the sample problem on a local 30B MoE while skipping two contracted handoffs

*Status: smoke-tested, N=1. The upstream Memdoor team-solve workflow at revision `ce126a8` produces an optimal O(N) solution to its sample problem on a locally served Qwen3-Coder-30B-A3B quant, passing all 5 public samples and 1,451 independent oracle cases in 85 seconds, while omitting the contracted `plan.md` and `review.md` artifacts.*

## The question

[Memdoor](https://github.com/guregodevo/memdoor) implements file-coordinated multi-agent workflows where distinct LLM roles collaborate via structured directory handoffs. The repository publishes an eight-step `team-solve` sample workflow:

- `ideate-a` and `ideate-b`: two parallel independent ideator roles proposing algorithmic approaches.
- `plan`: a synthesizer role combining both ideations into `notes.md` and `plan.md`.
- `solve`: an implementation role writing `solution.py`.
- `test`: an execution role running `check-samples.sh` and recording `test-status.txt`.
- `review`: an auditing role assessing test output and code against the plan, writing `review.md`.
- `repair`: a conditional repair role triggered if tests fail.
- `verify`: a final verification gate confirming checker status.

The mechanical question under test is whether this workflow, run at pinned commit `ce126a8dec855c99c73da58e230460a3c57e5140` against its own sample problem ("count balanced substrings") with an approved, locally served model under the Concourse GPU lock, drives all eight steps to completion and exits 0 on its own sample checker.

## Method

One problem, one model, one repair round, N=1. This is a smoke test with an eyeball exit, designed to verify workflow reproducibility, ledger fidelity, and independent solution correctness.

**The model and serving runtime.** Upstream evaluated Qwen3.8-27B in FP8 via OpenRouter across up to ten rounds on LiveCodeBench Hard problems. Under the lab's standing discipline, all generative execution runs inside Concourse on an NVIDIA RTX 3090 under `gpu-lock` with no external cloud API access. The model under test is `hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:UD-Q4_K_XL` (a 30B MoE with ~3.3B active parameters per token), served keyless on Ollama 0.40.13.

**The host and isolation.** Tasks run inside containerized Concourse workers on `tower` (AMD Ryzen 7 3700X, 62.7 GiB RAM, RTX 3090 24 GB, driver 595.91.07). The Memdoor CLI binary is built from source Go code at commit `ce126a8`, stubbing the untracked `web/dist` tree to satisfy `//go:embed` without pulling a Node toolchain into the builder. To prevent the workflow engine from recursing into upstream's separate benchmark suites (`bench/single-lcb` and `bench/team-llm-lcb`), the task container stages an allowlist of exactly nine files (`check-samples.sh` and the eight step YAMLs).

**Two separate verdicts.**
1. `public_sample_verdict`: Upstream's `check-samples.sh` running against the 5 public sample tests.
2. `independent_oracle_verdict`: A standalone deterministic brute-force grader (`concourse/scripts/memdoor_oracle.py`) evaluating 1,451 pseudo-random string cases seeded at `20261031`.

**The decision rule:**
- **PASS**: Workflow completes, `check-samples.sh` exits 0 (`PUBLIC_PASS`), and the independent oracle exits 0 with 0 mismatches (`ORACLE_PASS`).
- **PARTIAL / WRONG**: Public checker passes but oracle fails (`PUBLIC_PASS` with `ORACLE_FAIL`), revealing sample overfitting.
- **FAIL**: Workflow engine error, syntax crash, or checker exit non-zero.

## Results

| Metric | Measured | Target / Reference |
|---|---|---|
| **Public sample verdict** | **PUBLIC_PASS** (5/5 passed) | `check-samples.sh` exit 0 |
| **Independent oracle verdict** | **ORACLE_PASS** (1,451/1,451 passed) | 0 mismatches, 0 crashes, 0 timeouts |
| **Workflow wall clock** | **85 seconds** | 90-minute ceiling |
| **Workflow engine tasks** | **8 / 8 done** | 8 registered steps |
| **Generated algorithm** | **O(N) prefix coordinate map** | Hash-map tracking `(count_a - count_b, count_b - count_c)` |
| **Contracted files present** | `notes.md`, `solution.py`, `test-output.log`, `test-status.txt`, `final-test-output.log` | Documented step outputs |
| **Contracted files missing** | `plan.md`, `review.md` | Expected from `plan` and `review` steps |
| **Notes line count** | 76 lines | ≥ 50 lines required by plan prompt |
| **Proposal markers** | Proposal A: 1, Proposal B: 1 | Both proposals synthesized |

**Verdict: PASS.** Both public and independent oracle checks exit 0.

The generated `solution.py` implements an optimal linear-time algorithm:

```python
import sys
from collections import defaultdict

line = sys.stdin.read().strip()
counts = defaultdict(int)
counts[(0, 0)] = 1
result = 0
count_a = count_b = count_c = 0

for char in line:
    if char == 'a':
        count_a += 1
    elif char == 'b':
        count_b += 1
    elif char == 'c':
        count_c += 1
    coord = (count_a - count_b, count_b - count_c)
    result += counts[coord]
    counts[coord] += 1

print(result)
```

## Role compliance and ledger fidelity

The engine's terminal report of `8/8 done` masks an operational gap in ledger hygiene.

The `plan` prompt instructs the planner role to inspect the parallel ideations and write two distinct artifacts: a synthesis document `notes.md` (minimum 50 lines) and an actionable implementation specification `plan.md`. The model produced a 76-line `notes.md` that successfully synthesized both Proposal A (coordinate counting) and Proposal B (prefix difference), but failed to create `plan.md`.

Similarly, the `review` step evaluated test execution and exited cleanly without writing `review.md`. The downstream `solve` and `repair` roles proceeded by reading `notes.md` directly. While the final code is mathematically sound and passes 1,451 test cases, the agent roles silently omitted two of their contracted file handoffs.

## What this does not settle

- **N=1 smoke test on one problem.** This run confirms that the Memdoor engine executes its DAG and that Qwen3-Coder-30B-A3B can solve the sample problem in 85 seconds. It does not measure performance across diverse programming tasks.
- **No benchmark parity comparison.** Upstream claims a 9.8/10 score on LiveCodeBench Hard problems using Qwen3.8-27B in FP8 via OpenRouter over a 10-round benchmark loop. This experiment runs a single sample problem with one repair round on local GGUF weights; it carries no statistical comparison to upstream's benchmark score.
- **Run-to-run compliance variance.** In an earlier build of this pipeline, the agent roles stalled without writing code (`incomplete` outcome in 27s). Prompt adherence and file generation exhibit non-zero variance across runs.
- **Hidden test generalization.** The sample problem does not ship with hidden test cases. While the independent oracle tests 1,451 synthetic strings, it does not assess competitive programming edge cases like integer overflow or memory exhaustion on massive inputs.

## Cost

- **Compute to output.** 85 seconds of workflow execution for 32 lines of verified Python. Total Concourse job wall clock is **22m30s**, of which ~17 minutes is off-lock model streaming, image caching, and binary compilation.
- **Peak memory.** 20,154 MiB of 24,576 MiB VRAM (82% of the RTX 3090) allocated to `llama-server` under Ollama.
- **Calendar time from the ask: 2 hours 41 minutes.** Task `t_77af9edd` was assigned at 19:13 PDT; build 4 completed successfully at 21:54 PDT.
- **Failed pipeline builds leading to the pass:**
  - **Build #1, 36m55s (aborted)**: `apt-get` stalled on an interactive `tzdata` debconf prompt inside the GPU lock. Resolved by setting `DEBIAN_FRONTEND=noninteractive`.
  - **Build #2, 22m34s (failed)**: The experiment completed and passed, but the S3 `put:` failed with `NoSuchBucket` because bucket `blades68-3d` did not exist on MinIO. Resolved by creating the dedicated `memdoor-team-solve` bucket.
  - **Build #3, 24m48s (failed)**: The agent roles generated no code in 27s (`incomplete`). The script exited 1 immediately, stranding debug logs inside the dead container before egress. Resolved by decoupling artifact egress from the downstream `verdict-gate`.

## Files

- [`memdoor-team-solve-pipeline.yml`](files/2026-10-31-memdoor-team-solve-smoke/memdoor-team-solve-pipeline.yml) — Concourse pipeline definition with GPU lock and post-egress verdict gate
- [`protocol.yml`](files/2026-10-31-memdoor-team-solve-smoke/protocol.yml) — Pre-registered experiment protocol and divergence register
- [`results.json`](files/2026-10-31-memdoor-team-solve-smoke/results.json) — Structured run metrics, timings, and ledger fidelity measurements
- [`oracle-report.json`](files/2026-10-31-memdoor-team-solve-smoke/oracle-report.json) — Independent brute-force oracle verification results (1,451 cases)
- [`solution.py`](files/2026-10-31-memdoor-team-solve-smoke/solution.py) — Generated Python solution
- [`notes.md`](files/2026-10-31-memdoor-team-solve-smoke/notes.md) — Synthesized ledger notes generated by the planner role
