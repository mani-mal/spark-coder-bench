#!/usr/bin/env bash
# run-appcase.sh — Layer 2 top-level command. Build TaskFlow Local with one model
# on one track, N times, each run fully metric-wrapped and scored by the 29-check API
# acceptance suite (TaskFlow API acceptance-check fraction, k/29 — NOT full-stack quality).
# Resumable: a repeat whose rubric-score.json already exists is skipped.
#
# Usage:
#   layer2_appcase/run-appcase.sh <profile> <track> [n_repeats]
#     profile : gpt-oss-120b | nemotron-super | qwen3-coder-30b  (must match the SERVED model)
#     track   : node | python
#
# Prereqs: the matching model is already served (infra/vllm/serve-model.sh <profile>)
# and OpenCode is on PATH with the vllm-local provider configured.
#
# Env overrides:
#   TASKFLOW_DIR (default ~/projects/taskflow-local-app-benchmark)
#   BASELINE     (default baseline-v6)
#   METRICS_URL  (default http://127.0.0.1:8000/metrics; use :8355 for TensorRT-LLM)
#   PROVIDER     (default vllm-local; use trt-local for the TensorRT-LLM runtime)
#   RUNTIME_TAG  (default empty; set e.g. "trt" so TRT-LLM run-ids don't collide with vLLM ones)
set -uo pipefail

PROFILE="${1:-}"; TRACK="${2:-}"; N="${3:-3}"
if [[ -z "$PROFILE" || -z "$TRACK" ]]; then
  echo "Usage: $0 <profile> <track:node|python> [n_repeats]" >&2; exit 1
fi
[[ "$TRACK" == "node" || "$TRACK" == "python" ]] || { echo "track must be node|python" >&2; exit 1; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TASKFLOW_DIR="${TASKFLOW_DIR:-$HOME/projects/taskflow-local-app-benchmark}"
BASELINE="${BASELINE:-baseline-v6}"
METRICS_URL="${METRICS_URL:-http://127.0.0.1:8000/metrics}"
PROVIDER="${PROVIDER:-vllm-local}"
RUNTIME_TAG="${RUNTIME_TAG:-}"        # e.g. "trt"; empty keeps vLLM run-ids unchanged
TAG="${RUNTIME_TAG:+-$RUNTIME_TAG}"   # "-trt" or ""
APP_TRACK_DIR="$TASKFLOW_DIR/apps/${TRACK}-track"
PROMPT_FILE="$REPO_ROOT/layer2_appcase/prompt.md"
OPENCODE_BIN="${OPENCODE_BIN:-opencode}"

command -v "$OPENCODE_BIN" >/dev/null 2>&1 || { echo "opencode not found on PATH (set OPENCODE_BIN)" >&2; exit 1; }
[[ -d "$TASKFLOW_DIR/.git" ]] || { echo "TASKFLOW_DIR is not a git repo: $TASKFLOW_DIR" >&2; exit 1; }

for r in $(seq 1 "$N"); do
  RUN_ID="${PROFILE}${TAG}-l2-${TRACK}-${r}"
  OUT="$REPO_ROOT/results/raw/$RUN_ID"
  if [[ -f "$OUT/rubric-score.json" ]]; then
    echo "[appcase] $RUN_ID already scored — skipping (resumable)"; continue
  fi
  echo "==================================================================="
  echo "[appcase] run $RUN_ID  (profile=$PROFILE track=$TRACK repeat=$r/$N)"
  echo "==================================================================="

  # fresh app state from the frozen baseline on a per-run branch.
  # SCRUB the working tree first: the rubric's `npm install` / venv leave modified-tracked files
  # (e.g. apps/*/frontend/package-lock.json) and untracked build artifacts (node_modules, .venv,
  # *.db). Without this, `git checkout` aborts ("local changes would be overwritten") and every
  # subsequent run cascades into the same failure. reset --hard discards tracked changes;
  # clean -fdx removes untracked/ignored build output.
  ( cd "$TASKFLOW_DIR" \
      && git reset -q --hard \
      && git clean -fdxq \
      && git checkout -q "$BASELINE" \
      && git checkout -q -B "$RUN_ID" ) \
    || { echo "[appcase] git checkout failed for $RUN_ID" >&2; continue; }

  PROMPT="$(cat "$PROMPT_FILE")
TRACK FOR THIS RUN: build the ${TRACK} track in apps/${TRACK}-track/ only."

  # build the app with full 3-source metric capture.
  # A heartbeat shows the build is alive during long silent stretches (the model reasons
  # for minutes streaming JSON to the captured log, not the terminal).
  echo "[appcase] BUILD start: $RUN_ID  ($(date -u +%H:%M:%SZ)) — opencode is working, heartbeat every 30s"
  _bstart=$SECONDS
  ( while true; do sleep 30; echo "[appcase]   ...still building $RUN_ID ($((SECONDS-_bstart))s elapsed)"; done ) &
  _hb=$!
  "$REPO_ROOT/infra/metrics/run-context.sh" "$RUN_ID" --metrics-url "$METRICS_URL" -- \
    "$OPENCODE_BIN" run --format json -m "${PROVIDER}/${PROFILE}" --dir "$TASKFLOW_DIR" "$PROMPT" \
    || echo "[appcase] opencode build returned non-zero for $RUN_ID (continuing to score what exists)"
  kill "$_hb" 2>/dev/null; wait "$_hb" 2>/dev/null
  echo "[appcase] BUILD done:  $RUN_ID  ($((SECONDS-_bstart))s)"

  # commit whatever was produced, on the run branch
  ( cd "$TASKFLOW_DIR" && git add -A && git commit -q -m "Layer2 $RUN_ID build" || true )

  # score against the pinned contract (starts backend, builds frontend, runs app tests)
  echo "[appcase] SCORE start: $RUN_ID — npm/pytest build+test (this also takes a minute)"
  if [[ -d "$APP_TRACK_DIR" ]]; then
    python3 "$REPO_ROOT/layer2_appcase/rubric_tests/run_rubric.py" \
      --track "$TRACK" --app-dir "$APP_TRACK_DIR" --start --build --test --out "$OUT" \
      || echo "[appcase] rubric scoring errored for $RUN_ID (see $OUT)"
  else
    echo "[appcase] expected app dir missing: $APP_TRACK_DIR — recording zero score" >&2
    python3 - "$OUT" "$TRACK" <<'PY'
import json,sys,os
out,track=sys.argv[1],sys.argv[2]; os.makedirs(out,exist_ok=True)
json.dump({"track":track,"pass_rate":0.0,"passed":0,"total":0,
           "error":"app track dir not produced by the model"}, open(os.path.join(out,"rubric-score.json"),"w"), indent=2)
PY
  fi
  echo "[appcase] $RUN_ID done -> $OUT (run-summary.json + rubric-score.json)"
done

echo "[appcase] all repeats complete for $PROFILE/$TRACK. Aggregate with analysis/aggregate-runs.py"
