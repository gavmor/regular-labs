"""Summarize the LongMemEval pilot from Inspect logs and snapshot manifests."""

import json
import sys
from pathlib import Path

import pandas as pd
from inspect_ai.analysis import evals_df, samples_df

LOGS = Path(sys.argv[1] if len(sys.argv) > 1 else "logs/lme-pilot")
dirs = sorted(str(p) for p in LOGS.iterdir() if p.is_dir())
CSV = Path(sys.argv[2]) if len(sys.argv) > 2 else None
runs = evals_df(dirs)
incomplete = runs[runs["status"] != "success"]
if len(incomplete):
    print(f"WARNING: {len(incomplete)} eval logs are not complete\n")
df = samples_df(dirs).merge(runs[["eval_id", "model"]], on="eval_id")
df["reader"] = df["model"].str.removeprefix("openai/")
df["correct"] = df["score_official_judge"].eq("C").astype(int)
# A Pi run that exceeds the solver's 600 s cap leaves no solver metadata and an empty answer, which scores incorrect.
df["timed_out"] = df["metadata_query_seconds"].isna()
df["metadata_query_seconds"] = df["metadata_query_seconds"].fillna(df["total_time"])

cell = df.groupby(["reader", "metadata_memory"]).agg(
    n=("correct", "size"), accuracy=("correct", "mean"), retrieval_rate=("metadata_retrieved", "mean"),
    median_s=("metadata_query_seconds", "median"), p95_s=("metadata_query_seconds", lambda s: s.quantile(0.95)),
    reader_in=("metadata_reader_input_tokens", "mean"), reader_out=("metadata_reader_output_tokens", "mean"))
if CSV:
    columns = {"reader": "reader", "metadata_memory": "memory", "id": "question_id", "metadata_category": "category", "correct": "correct",
               "metadata_query_seconds": "query_seconds", "timed_out": "timed_out", "metadata_memory_calls": "memory_calls",
               "metadata_reader_input_tokens": "reader_input_tokens", "metadata_reader_output_tokens": "reader_output_tokens"}
    df[list(columns)].rename(columns=columns).sort_values(["reader", "memory", "category", "question_id"]).to_csv(CSV, index=False)
print("Accuracy by reader x memory (n = questions per cell)\n")
print(cell.round(3).to_string(), "\n")
print("Accuracy matrix\n")
print(df.pivot_table(index="reader", columns="metadata_memory", values="correct", aggfunc="mean").round(3).to_string(), "\n")
print("Accuracy by memory x category, pooled over readers\n")
print(df.pivot_table(index="metadata_category", columns="metadata_memory", values="correct", aggfunc="mean").round(2).to_string(), "\n")

manifests = [json.loads(p.read_text()) for p in Path("snapshots").glob("*/*/manifest.json")]
ingest = pd.DataFrame([{"memory": m["arm"], "writer_in": m["writer_usage"]["input"], "writer_out": m["writer_usage"]["output"],
                        "seconds": m["seconds"], "retries": len(m.get("retries", []))} for m in manifests])
print("Ingestion per snapshot (fixed writer; plugin-internal extraction calls not included)\n")
print(ingest.groupby("memory").agg(snapshots=("seconds", "size"), mean_writer_in=("writer_in", "mean"), mean_writer_out=("writer_out", "mean"),
                                    mean_seconds=("seconds", "mean"), retries=("retries", "sum")).round(0).to_string())
