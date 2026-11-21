#!/usr/bin/env bash
# Fetch the pinned Inkling 2 Mini smoke-test toolchain and weights.
#
# Runs in the LOCK-FREE prepare phase of concourse/gpu-workload-template.yml
# (cwd = prepared-workspace). Nothing here touches the 3090, which is the point:
# a 16.4 GiB weight download must never hold the cluster's single GPU mutex.
#
# Every URL is pinned to an immutable ref and every artifact is hash-checked:
#   weights  huggingface.co/unsloth/Inkling-2-Mini-GGUF @ ae9327c5fbc7
#            Inkling-2-Mini-UD-Q4_K_XL.gguf (17,629,759,456 B)
#   runtime  unslothai/llama.cpp release b12588-mix-c0c3de8,
#            linux-x64 cuda12-portable bundle (sm_86 is in its arch list).
#            The vendor build is required because the repo-root GGUFs use the
#            looped-layer layout; upstream llama.cpp needs the separate
#            Mainline_Support conversion instead.
#
# Why the weights are pulled as parallel byte ranges: one TLS connection from
# a Concourse task to the HF CDN measured ~2 MB/s (16.4 GiB => ~2 h, past any
# sane prepare timeout), while 8 concurrent ranges from the same host measured
# ~16 MB/s. The ranges are concatenated in order and then sha256-verified, so
# the integrity guarantee is identical to a single-stream download.
#
# The cuda12 bundle (not cuda13) is deliberate: it links libcudart/libcublas
# soname 12, which the pinned pytorch/pytorch:2.9.1-cuda12.8 runtime image ships.
# The cuda13 bundle wants libcudart.so.13 and cannot load there.
set -euo pipefail

ROOT=${ROOT:-$PWD}
MODEL_DIR=${MODEL_DIR:-$ROOT/models/inkling-2-mini}
LLAMACPP_ROOT=${LLAMACPP_ROOT:-$ROOT/llamacpp}
LLAMACPP_DIR=${LLAMACPP_DIR:-$LLAMACPP_ROOT/llama-b12588-mix-c0c3de8}
LOG_DIR=${LOG_DIR:-$ROOT/../prep-log}
CHUNK_DIR=${CHUNK_DIR:-$ROOT/.model-chunks}
# Concurrent range requests. 12 is the measured-safe point on this box: the
# ranges are 1.4 GiB each, so peak extra disk is one model's worth.
CONCURRENCY=${CONCURRENCY:-12}

MODEL_URL="https://huggingface.co/unsloth/Inkling-2-Mini-GGUF/resolve/ae9327c5fbc7333116ba32eee78bb5d2bbefae4f/Inkling-2-Mini-UD-Q4_K_XL.gguf"
MODEL_FILE="$MODEL_DIR/Inkling-2-Mini-UD-Q4_K_XL.gguf"
MODEL_SIZE=17629759456
MODEL_SHA256="e62d463c135ffe283df8d94b279a96ca145ac128b52ce854478613045bf4de15"

RUNTIME_URL="https://github.com/unslothai/llama.cpp/releases/download/b12588-mix-c0c3de8/app-b12588-mix-c0c3de8-linux-x64-cuda12-portable.tar.gz"
RUNTIME_TAR="$LLAMACPP_ROOT/app-b12588-mix-c0c3de8-linux-x64-cuda12-portable.tar.gz"
RUNTIME_SHA256="4c30d5e3b3d7242cf3f214977c09a0d06102c71a713c256749909dcafa9f5980"

mkdir -p "$MODEL_DIR" "$LLAMACPP_ROOT" "$LLAMACPP_DIR" "$LOG_DIR"

verify() { # verify <file> <sha256> <label>
  echo "[fetch] verifying $3 sha256"
  echo "$2  $1" | sha256sum -c -
  echo "[fetch] $3: sha256 OK"
}

download_ranges() { # download_ranges <url> <dest> <total_bytes> <chunks>
  local url=$1 dest=$2 total=$3 chunks=$4
  local chunk_size=$(( (total + chunks - 1) / chunks ))
  mkdir -p "$CHUNK_DIR"
  export MODEL_URL="$url" CHUNK_SIZE="$chunk_size" CHUNK_DIR TOTAL_BYTES="$total"
  echo "[fetch] weights: $chunks ranges of $chunk_size B in parallel"
  seq 0 $((chunks - 1)) | xargs -P "$chunks" -I{} bash -c '
    set -euo pipefail
    start=$(( {} * CHUNK_SIZE ))
    end=$(( start + CHUNK_SIZE - 1 ))
    [ "$end" -ge "$TOTAL_BYTES" ] && end=$(( TOTAL_BYTES - 1 ))
    want=$(( end - start + 1 ))
    out="$CHUNK_DIR/chunk-$(printf "%02d" {})"
    for attempt in 1 2 3 4 5; do
      # No -C - here: resuming inside a byte range is not meaningful, the whole
      # range is re-fetched instead.
      curl -fsSL --connect-timeout 20 --max-time 3600 -r "$start-$end" -o "$out" "$MODEL_URL" || true
      have=$(stat -c %s "$out" 2>/dev/null || echo 0)
      if [ "$have" -eq "$want" ]; then exit 0; fi
      echo "[fetch] range {} short (${have}/${want}), attempt ${attempt}/5"
      sleep $(( attempt * 3 ))
    done
    echo "[fetch] FAILED range {} after 5 attempts"
    exit 1
  '
  : > "$dest"
  for i in $(seq 0 $((chunks - 1))); do
    cat "$CHUNK_DIR/chunk-$(printf "%02d" "$i")" >> "$dest"
  done
  rm -rf "$CHUNK_DIR"
  echo "[fetch] weights: concatenated $(stat -c %s "$dest") B into $dest"
}

# --- runtime first: 419 MB, and it is the cheap place to discover that the
# base image is missing a system library. Paying 16.4 GiB of download before
# finding out is what a previous revision of this script did.
if [ -f "$RUNTIME_TAR" ] && echo "$RUNTIME_SHA256  $RUNTIME_TAR" | sha256sum -c --status -; then
  echo "[fetch] llama.cpp: tarball already present and hash-verified"
else
  echo "[fetch] llama.cpp: downloading $RUNTIME_URL"
  curl -fsSL --retry 10 --retry-all-errors --retry-delay 5 --connect-timeout 20 \
       -o "$RUNTIME_TAR" "$RUNTIME_URL"
  verify "$RUNTIME_TAR" "$RUNTIME_SHA256" "llama.cpp b12588-mix-c0c3de8 cuda12"
fi

if [ ! -x "$LLAMACPP_DIR/llama-server" ]; then
  tar xzf "$RUNTIME_TAR" -C "$LLAMACPP_DIR"
fi

# libgomp.so.1 (OpenMP, needed by llama-server) is not on the loader path in the
# pinned image: it lives in the conda prefix. Fail here in the prepare phase,
# in seconds, rather than inside the lock. Scoped to this one command: exporting
# it would shadow the system libcurl that the downloads below depend on.
LD_LIBRARY_PATH="$LLAMACPP_DIR:/opt/conda/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  "$LLAMACPP_DIR/llama-server" --version 2>&1 | tee "$LOG_DIR/inkling2-runtime-version.txt"

# --- weights ---------------------------------------------------------------
if [ -f "$MODEL_FILE" ] && echo "$MODEL_SHA256  $MODEL_FILE" | sha256sum -c --status -; then
  echo "[fetch] weights: already present and hash-verified"
else
  download_ranges "$MODEL_URL" "$MODEL_FILE" "$MODEL_SIZE" "$CONCURRENCY"
  verify "$MODEL_FILE" "$MODEL_SHA256" "weights UD-Q4_K_XL"
fi

python3 - "$MODEL_FILE" "$LLAMACPP_DIR" "$LOG_DIR" <<'PY'
import json, os, sys, time

model, llamacpp, log_dir = sys.argv[1:4]
record = {
    "model_path": os.path.abspath(model),
    "model_bytes": os.path.getsize(model),
    "model_sha256": "e62d463c135ffe283df8d94b279a96ca145ac128b52ce854478613045bf4de15",
    "model_repo": "unsloth/Inkling-2-Mini-GGUF",
    "model_repo_revision": "ae9327c5fbc7333116ba32eee78bb5d2bbefae4f",
    "model_file": "Inkling-2-Mini-UD-Q4_K_XL.gguf",
    "llamacpp_dir": os.path.abspath(llamacpp),
    "llamacpp_release": "b12588-mix-c0c3de8",
    "llamacpp_variant": "linux-x64-cuda12-portable",
    "llamacpp_tarball_sha256": "4c30d5e3b3d7242cf3f214977c09a0d06102c71a713c256749909dcafa9f5980",
    "build_info": open(os.path.join(llamacpp, "BUILD_INFO.txt")).read(),
    "fetched_at_unix": int(time.time()),
}
os.makedirs(log_dir, exist_ok=True)
with open(os.path.join(log_dir, "inkling2-toolchain.json"), "w") as fh:
    json.dump(record, fh, indent=2, sort_keys=True)
print(json.dumps({k: record[k] for k in ("model_file", "model_bytes", "llamacpp_release", "llamacpp_variant")}, indent=2))
PY

echo "[fetch] toolchain staged at $ROOT (models + llamacpp)"
