#!/usr/bin/env bash
# run-suite.sh — Layer 1 top-level command. Run a whole ARM64 subset for one model,
# N repeats per task, resumable (a task+repeat with resolved.json is skipped), then
# aggregate. Wrap each task in full 3-source metrics via run-task.py.
#
# Usage:
#   layer1_swebench/run-suite.sh <profile> [n_repeats] [instances_json]
#     profile        : qwen3-coder-30b | nemotron-super  (must match the SERVED model)
#     n_repeats      : default 3 (pilot; final N comes from analysis/stats power analysis)
#     instances_json : default layer1_swebench/subset-verified.json (.arm64_buildable[])
#
# Prereqs: model served on :8000 (infra/vllm/serve-model.sh), opencode on PATH,
# swebench + datasets installed, Docker usable.
set -uo pipefail

PROFILE="${1:-}"; N="${2:-3}"; INST_JSON="${3:-}"
[[ -z "$PROFILE" ]] && { echo "Usage: $0 <profile> [n_repeats] [instances_json]" >&2; exit 1; }

# Runtime selection (env overrides; defaults reproduce the original vLLM behavior, run-ids unchanged).
#   PROVIDER     (default vllm-local; use trt-local for TensorRT-LLM)
#   RUNTIME_TAG  (default empty; set e.g. "trt" so TRT-LLM run-ids don't collide with vLLM ones)
#   METRICS_URL  (default http://127.0.0.1:8000/metrics; use :8355 for TensorRT-LLM)
PROVIDER="${PROVIDER:-vllm-local}"
RUNTIME_TAG="${RUNTIME_TAG:-}"
TAG="${RUNTIME_TAG:+-$RUNTIME_TAG}"   # "-trt" or ""
METRICS_URL="${METRICS_URL:-http://127.0.0.1:8000/metrics}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INST_JSON="${INST_JSON:-$REPO_ROOT/layer1_swebench/subset-verified.json}"
[[ -f "$INST_JSON" ]] || { echo "instances file not found: $INST_JSON (run select-arm64-subset.py --verify first)" >&2; exit 1; }

# Use the repo venv python: run-task.py needs datasets/swebench and aggregate-runs.py needs
# pandas, none of which are in the host's system python3 (PEP 668 / externally-managed). This
# also makes run-task.py's `sys.executable` resolve to the venv for the swebench eval subprocess.
PY="$REPO_ROOT/.venv/bin/python"; [[ -x "$PY" ]] || PY="python3"

# Force a USER-writable HF cache for the dataset. env.sh / the lab .env point HF_HOME at
# ~/.cache/huggingface, which is ROOT-owned here (model weights were pulled inside the vLLM
# container as root), so a host-side `load_dataset` there dies with PermissionError. This step
# is purely host-side (dataset + docker eval), never serves a model, so overriding is safe; the
# vLLM serve step sets its own HF_HOME and is unaffected. Allow an explicit LAYER1_HF_HOME.
export HF_HOME="${LAYER1_HF_HOME:-$REPO_ROOT/.hf-cache}"
mkdir -p "$HF_HOME"
[[ -z "${HF_TOKEN:-}" && -f "$HOME/sec.txt" ]] && export "$(grep -E '^HF_TOKEN=' "$HOME/sec.txt")"

mapfile -t INSTANCES < <("$PY" -c "import json,sys;d=json.load(open('$INST_JSON'));print('\n'.join(d.get('arm64_buildable', d.get('probed', []))))")
echo "[suite] $PROFILE${TAG} (provider=$PROVIDER): ${#INSTANCES[@]} instances x $N repeats  metrics=$METRICS_URL"

for inst in "${INSTANCES[@]}"; do
  for r in $(seq 1 "$N"); do
    RUN_ID="${PROFILE}${TAG}-l1-${inst}-${r}"
    if [[ -f "$REPO_ROOT/results/raw/$RUN_ID/resolved.json" ]]; then
      echo "[suite] $RUN_ID done — skipping"; continue
    fi
    echo "[suite] >>> $RUN_ID"
    "$PY" "$REPO_ROOT/layer1_swebench/run-task.py" \
      --instance-id "$inst" --profile "$PROFILE" --repeat "$r" \
      --provider "$PROVIDER" --runtime-tag "$RUNTIME_TAG" --metrics-url "$METRICS_URL" || \
      echo "[suite] run-task failed for $RUN_ID (continuing)"
  done
done

echo "[suite] aggregating..."
"$PY" "$REPO_ROOT/analysis/aggregate-runs.py" || true
echo "[suite] done. Stats: python3 analysis/stats.py --long results/summary/benchmark-long.csv"
