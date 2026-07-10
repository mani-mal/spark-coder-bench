#!/usr/bin/env bash
# run-benchmark-l1.sh — full Layer 1 (SWE-bench Verified, arm64 subset) sweep, resumable.
#
# For each model: serve it on :8000 (sanity-gated), then run the arm64-buildable subset N
# times per task (run-suite.sh → run-task.py: clone → opencode agent → patch → official
# SWE-bench eval, all metric-wrapped). Then aggregate. Re-running resumes: a (model,task,
# repeat) whose resolved.json exists is skipped; a model already serving is not re-served.
#
# WHY THIS IS SEPARATE FROM run-benchmark.sh (Layer 2): Layer 1 scoring runs the official
# swebench evaluation in Docker, so the whole suite must execute inside the docker group
# (via `sg docker`) and needs the user-writable HF dataset cache + opencode on PATH. Layer 2
# only needs node/npm + opencode, no docker for scoring.
#
# Usage:
#   ./run-benchmark-l1.sh                                   # N=1 pilot, both models, full subset
#   N=3 ./run-benchmark-l1.sh                               # 3 repeats per task
#   MODELS="qwen3-coder-30b" ./run-benchmark-l1.sh          # one model
#   SUBSET=layer1_swebench/subset-verified.json ./run-benchmark-l1.sh
#
# Needs: ./setup.sh already run; the arm64 subset selected (select-arm64-subset.py --verify);
# no wrong-arch ubuntu:22.04 cached (see docs/findings/2026-06-26-layer1-arm64-enablement.md).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"
# shellcheck disable=SC1091
source "$REPO_ROOT/env.sh"

# --- single-sweep guard (separate lock from Layer 2; both share the :8000 server though) ----
LOCKFILE="$REPO_ROOT/.run-benchmark-l1.lock"
exec 9>"$LOCKFILE"
if ! flock -n 9; then
  echo "[l1] ERROR: another Layer-1 sweep is already running (lock: $LOCKFILE)." >&2
  echo "[l1] Concurrent sweeps race on the :8000 server and the docker build cache. Refusing." >&2
  exit 1
fi
# Also refuse if a Layer 2 sweep holds its lock — they'd fight over :8000.
if [[ -f "$REPO_ROOT/.run-benchmark.lock" ]] && ! flock -n 8 8>"$REPO_ROOT/.run-benchmark.lock"; then
  echo "[l1] ERROR: a Layer-2 run-benchmark.sh sweep is running — it owns :8000. Wait for it." >&2
  exit 1
fi

N="${N:-1}"
read -r -a MODELS <<< "${MODELS:-gpt-oss-120b qwen3-coder-30b}"
SUBSET="${SUBSET:-$REPO_ROOT/layer1_swebench/subset-verified.json}"
PORT="${VLLM_PORT:-8000}"
KEY="${VLLM_API_KEY:-local-dgx-spark-key}"
# Layer 1 needs: user-writable HF dataset cache (model cache is root-owned), opencode on PATH,
# and the HF token for un-throttled dataset pulls. FORCE .hf-cache: env.sh sourced the lab .env
# which set HF_HOME=~/.cache/huggingface (root-owned) — a host-side load_dataset there fails with
# PermissionError. serve-model.sh re-sources the lab .env so the vLLM container still mounts the
# root-owned weights cache; only the host-side dataset path needs to be writable.
export HF_HOME="$REPO_ROOT/.hf-cache"; mkdir -p "$HF_HOME"
export PATH="$HOME/.opencode/bin:$PATH"
export VLLM_API_KEY="$KEY"
[[ -z "${HF_TOKEN:-}" && -f "$HOME/sec.txt" ]] && export "$(grep -E '^HF_TOKEN=' "$HOME/sec.txt")"

mkdir -p "$REPO_ROOT/logs"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$REPO_ROOT/logs/run-benchmark-l1-$TS.log"
exec > >(tee -a "$LOG") 2>&1

[[ -f "$SUBSET" ]] || { echo "[l1] subset not found: $SUBSET (run select-arm64-subset.py --verify)"; exit 1; }
mapfile -t TASKS < <(python3 -c "import json;d=json.load(open('$SUBSET'));print('\n'.join(d.get('arm64_buildable', [])))")
echo "[l1] $TS  N=$N  models=${MODELS[*]}  tasks=${#TASKS[@]}  subset=$SUBSET  log=$LOG"

# --- docker wrapper (same logic as run-benchmark.sh): direct if usable, else via sg docker ---
docker_ok() { docker ps >/dev/null 2>&1; }
in_docker_group() {
  id -nG 2>/dev/null | tr ' ' '\n' | grep -qx docker && return 0
  getent group docker 2>/dev/null | awk -F: '{print $4}' | tr ',' '\n' | grep -qx "${USER:-$(id -un)}"
}
# Run an arbitrary command string with docker access (direct or via sg docker), preserving the
# Layer-1 env (PATH/HF_HOME/HF_TOKEN/VLLM_API_KEY) into the sg subshell.
with_docker() {
  local cmd="$1"
  if docker_ok; then
    bash -c "$cmd"
  elif in_docker_group; then
    sg docker -c "PATH='$PATH' HF_HOME='$HF_HOME' HF_TOKEN='${HF_TOKEN:-}' VLLM_API_KEY='$VLLM_API_KEY' $cmd"
  else
    echo "[l1] ERROR: docker not usable and not in docker group" >&2; return 1
  fi
}
currently_served() {
  curl -s "http://127.0.0.1:$PORT/v1/models" -H "Authorization: Bearer $KEY" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['data'][0]['id'])" 2>/dev/null
}
done_count() {
  local c=0 m t
  for m in "${MODELS[@]}"; do for t in "${TASKS[@]}"; do for r in $(seq 1 "$N"); do
    [[ -f "$REPO_ROOT/results/raw/${m}-l1-${t}-${r}/resolved.json" ]] && c=$((c + 1))
  done; done; done
  echo "$c"
}
TOTAL=$(( ${#MODELS[@]} * ${#TASKS[@]} * N ))
echo "[l1] plan: ${#MODELS[@]} models × ${#TASKS[@]} tasks × $N = $TOTAL runs; already done: $(done_count)/$TOTAL"

# --- the sweep ---
mi=0
for model in "${MODELS[@]}"; do
  mi=$((mi + 1))
  echo "==================================================================="
  echo "[l1] MODEL $mi/${#MODELS[@]}: $model   [sweep $(done_count)/$TOTAL done]"
  echo "==================================================================="
  if [[ "$(currently_served)" == "$model" ]]; then
    echo "[l1] $model already serving on :$PORT — not re-serving"
  else
    echo "[l1] serving $model ..."
    with_docker "bash '$REPO_ROOT/infra/vllm/serve-model.sh' '$model'" \
      || { echo "[l1] serve failed for $model — skipping"; continue; }
  fi
  [[ "$(currently_served)" == "$model" ]] || { echo "[l1] $model not responding — skipping"; continue; }

  # run the whole subset for this model (run-suite.sh is itself resumable + aggregates per call)
  with_docker "bash '$REPO_ROOT/layer1_swebench/run-suite.sh' '$model' '$N' '$SUBSET'" \
    || echo "[l1] run-suite returned non-zero for $model (continuing)"
  d=$(done_count); echo "[l1] PROGRESS: $d/$TOTAL runs scored ($(( TOTAL>0 ? d * 100 / TOTAL : 0 ))%)"
done

# --- analysis ---
echo "[l1] ANALYSIS: aggregate → stats"
# shellcheck disable=SC1091
[[ -f "$REPO_ROOT/.venv/bin/activate" ]] && source "$REPO_ROOT/.venv/bin/activate"
python3 "$REPO_ROOT/analysis/aggregate-runs.py" || echo "[l1] aggregate failed"
python3 "$REPO_ROOT/analysis/stats.py" --long "$REPO_ROOT/results/summary/benchmark-long.csv" \
  | tee "$REPO_ROOT/results/summary/stats-report-l1-$TS.txt" || echo "[l1] stats failed"

echo
echo "[l1] DONE. Raw: results/raw/<model>-l1-<task>-<rep>/  Log: $LOG"
