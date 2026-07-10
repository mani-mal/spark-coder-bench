#!/usr/bin/env bash
# run-benchmark.sh — full Layer 2 sweep + analysis, one command, resumable.
#
# For each model: serve it on :8000 (sanity-gated), build BOTH tracks N times with full
# 3-source metric capture, score each against the rubric. Then aggregate → stats → figures.
# Re-running resumes: a (model,track,repeat) whose rubric-score.json exists is skipped, and a
# model already serving on :8000 is not re-served.
#
# Usage:
#   ./run-benchmark.sh                      # N=3, all 3 models, both tracks
#   N=1 ./run-benchmark.sh                  # quick 1-repeat smoke of the whole pipeline
#   MODELS="gpt-oss-120b" TRACKS="node" ./run-benchmark.sh   # subset
#
# Needs: ./setup.sh already run (Node, venv, opencode). Docker is used to (re)serve models;
# the script uses `sg docker` automatically if the docker group isn't active in this shell.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"
# shellcheck disable=SC1091
source "$REPO_ROOT/env.sh"

N="${N:-3}"
# Default set = the models vLLM can actually serve. nemotron-super is EXCLUDED: its MIXED_PRECISION
# ModelOpt checkpoint is rejected by vLLM 0.15.1 (see docs/findings/2026-06-25-nemotron-super-
# vllm-mixed-precision.md). Pass MODELS="...nemotron-super..." explicitly to attempt it anyway
# (serve-model.sh now fails fast in ~6s rather than blocking the readiness window).
read -r -a MODELS <<< "${MODELS:-gpt-oss-120b qwen3-coder-30b}"
read -r -a TRACKS <<< "${TRACKS:-node python}"
PORT="${VLLM_PORT:-8000}"
KEY="${VLLM_API_KEY:-local-dgx-spark-key}"
mkdir -p "$REPO_ROOT/logs"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$REPO_ROOT/logs/run-benchmark-$TS.log"

# Mirror all output to a timestamped log.
exec > >(tee -a "$LOG") 2>&1
echo "[run] $TS  N=$N  models=${MODELS[*]}  tracks=${TRACKS[*]}  log=$LOG"

# --- single-sweep guard ---------------------------------------------------------------------
# Two sweeps running at once race on the shared vLLM server (:8000) and the shared taskflow git
# repo (each run does `git checkout -B <run-id>` on the SAME repo, so the branches flip under each
# other mid-build) and silently corrupt each other's runs. Hold an exclusive lock for the whole
# sweep; a second invocation fails fast instead of quietly producing garbage.
# NOTE: the lock fd is opened AFTER the `tee` above so the tee subprocess does not inherit it —
# otherwise a lingering tee would keep the lock held after the sweep exits and block the next run
# (this bit the chained node→python rerun on 2026-07-03).
LOCKFILE="$REPO_ROOT/.run-benchmark.lock"
exec 9>"$LOCKFILE"
if ! flock -n 9; then
  echo "[run] ERROR: another run-benchmark.sh sweep is already running (lock: $LOCKFILE)." >&2
  echo "[run] Refusing to start a second sweep — concurrent sweeps corrupt each other's runs." >&2
  echo "[run] Check it with:  pgrep -af run-benchmark.sh   (and watch logs/run-benchmark-*.log)" >&2
  echo "[run] If you are certain none is running, remove the lock:  rm $LOCKFILE" >&2
  exit 1
fi
# M8: also refuse if a Layer-1 sweep holds ITS lock — it owns the same :8000 server, and starting
# L2 here would re-serve :8000 with a different model, scoring the in-flight L1 tasks as failures.
# (L1 already makes the reciprocal check; this closes the other direction.)
if [[ -f "$REPO_ROOT/.run-benchmark-l1.lock" ]] && ! flock -n 8 8>"$REPO_ROOT/.run-benchmark-l1.lock"; then
  echo "[run] ERROR: a Layer-1 run-benchmark-l1.sh sweep is running — it owns :8000. Wait for it." >&2
  exit 1
fi

# --- docker wrapper: direct if usable, else via sg docker (group not active in this shell) ---
docker_ok() { docker ps >/dev/null 2>&1; }
# Membership must be read from /etc/group, NOT `id -nG`: a shell started before the user was
# added to the docker group is a member in /etc/group but doesn't have it active — which is
# exactly when `sg docker` is needed and works. (id -nG only shows the active session groups.)
in_docker_group() {
  id -nG 2>/dev/null | tr ' ' '\n' | grep -qx docker && return 0
  getent group docker 2>/dev/null | awk -F: '{print $4}' | tr ',' '\n' | grep -qx "${USER:-$(id -un)}"
}
serve_model() {
  local prof="$1"
  if docker_ok; then
    bash "$REPO_ROOT/infra/vllm/serve-model.sh" "$prof"
  elif in_docker_group; then
    sg docker -c "bash '$REPO_ROOT/infra/vllm/serve-model.sh' '$prof'"
  else
    echo "[run] ERROR: docker not usable and you're not in the docker group — cannot serve $prof" >&2
    return 1
  fi
}
currently_served() {
  curl -s "http://127.0.0.1:$PORT/v1/models" -H "Authorization: Bearer $KEY" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['data'][0]['id'])" 2>/dev/null
}

# --- progress accounting ---
M=${#MODELS[@]}; T=${#TRACKS[@]}; TOTAL=$((M * T * N))
# exact count of completed (model,track,repeat) runs in THIS sweep's scope
done_count() {
  local c=0 m t r
  for m in "${MODELS[@]}"; do for t in "${TRACKS[@]}"; do for r in $(seq 1 "$N"); do
    [[ -f "$REPO_ROOT/results/raw/${m}-l2-${t}-${r}/rubric-score.json" ]] && c=$((c + 1))
  done; done; done
  echo "$c"
}
echo "[run] plan: $M models × $T tracks × $N repeats = $TOTAL Layer-2 runs; already done: $(done_count)/$TOTAL"

# --- the sweep ---
mi=0
for model in "${MODELS[@]}"; do
  mi=$((mi + 1))
  echo "==================================================================="
  echo "[run] MODEL $mi/$M: $model      [sweep $(done_count)/$TOTAL done]"
  echo "==================================================================="
  if [[ "$(currently_served)" == "$model" ]]; then
    echo "[run] $model already serving on :$PORT — not re-serving"
  else
    echo "[run] serving $model (loads weights + sanity gate; a few minutes)..."
    serve_model "$model" || { echo "[run] serve failed for $model — skipping"; continue; }
  fi
  # Confirm the intended model is actually answering before spending runs on it.
  if [[ "$(currently_served)" != "$model" ]]; then
    echo "[run] $model not responding on :$PORT after serve — skipping (check docker logs vllm-server)"; continue
  fi
  ti=0
  for track in "${TRACKS[@]}"; do
    ti=$((ti + 1))
    echo "[run] --- Layer 2: $model / $track  (model $mi/$M, track $ti/$T, N=$N) ---"
    bash "$REPO_ROOT/layer2_appcase/run-appcase.sh" "$model" "$track" "$N" \
      || echo "[run] run-appcase returned non-zero for $model/$track (continuing)"
    d=$(done_count); echo "[run] PROGRESS: $d/$TOTAL runs scored ($(( d * 100 / TOTAL ))%)"
  done
done

# --- analysis (needs the venv for figures; stats + aggregate are stdlib) ---
echo "==================================================================="
echo "[run] ANALYSIS: aggregate → stats → figures"
echo "==================================================================="
# shellcheck disable=SC1091
[[ -f "$REPO_ROOT/.venv/bin/activate" ]] && source "$REPO_ROOT/.venv/bin/activate"
python3 "$REPO_ROOT/analysis/aggregate-runs.py" || echo "[run] aggregate-runs failed"
python3 "$REPO_ROOT/analysis/stats.py" --long "$REPO_ROOT/results/summary/benchmark-long.csv" \
  | tee "$REPO_ROOT/results/summary/stats-report-$TS.txt" || echo "[run] stats failed"
python3 "$REPO_ROOT/analysis/figures.py" || echo "[run] figures failed"

echo
echo "[run] DONE. Raw: results/raw/  Summary: results/summary/  Charts: reports/charts/  Log: $LOG"
echo "[run] Layer 1 (SWE-bench) is separate and needs docker without sudo — see layer1_swebench/."
