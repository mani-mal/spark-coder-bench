#!/usr/bin/env bash
# run-context.sh — wrap ONE task in the full 3-source metric collection.
#
# Starts the hardware + vLLM collectors, records the task window (epoch_ms),
# runs the given command (e.g. an `opencode run ...` invocation), stops the
# collectors, parses OpenCode accounting, and (by default) aggregates.
#
# Usage:
#   run-context.sh <run-id> [--interval S] [--metrics-url URL]
#                  [--results-root DIR] [--no-aggregate] -- <command...>
#
# Example:
#   run-context.sh qwen-l2-appcase-1 -- \
#       opencode run -m vllm-local/qwen3-coder-30b "$(cat layer2_appcase/prompt.md)"
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
METRICS_DIR="$REPO_ROOT/infra/metrics"

RUN_ID=""
INTERVAL="0.25"
METRICS_URL="http://127.0.0.1:8000/metrics"
RESULTS_ROOT="$REPO_ROOT/results/raw"
DO_AGG=1
CMD=()

# parse args up to `--`
while [[ $# -gt 0 ]]; do
  case "$1" in
    --interval) INTERVAL="$2"; shift 2 ;;
    --metrics-url) METRICS_URL="$2"; shift 2 ;;
    --results-root) RESULTS_ROOT="$2"; shift 2 ;;
    --no-aggregate) DO_AGG=0; shift ;;
    --) shift; CMD=("$@"); break ;;
    *) if [[ -z "$RUN_ID" ]]; then RUN_ID="$1"; shift; else echo "Unexpected arg: $1" >&2; exit 1; fi ;;
  esac
done

if [[ -z "$RUN_ID" || ${#CMD[@]} -eq 0 ]]; then
  echo "Usage: $0 <run-id> [opts] -- <command...>" >&2
  exit 1
fi

OUT_DIR="$RESULTS_ROOT/$RUN_ID"
mkdir -p "$OUT_DIR"
echo "[run-context] run-id=$RUN_ID out=$OUT_DIR interval=${INTERVAL}s"

# 1) clock reference
python3 "$METRICS_DIR/clock-sync.py" --out "$OUT_DIR" >/dev/null

# 2) start collectors
bash "$METRICS_DIR/collect-hw.sh" "$OUT_DIR" "$INTERVAL" &
HW_PID=$!
python3 "$METRICS_DIR/collect-vllm-prom.py" --out "$OUT_DIR" --url "$METRICS_URL" --interval "$INTERVAL" &
PROM_PID=$!

# let collectors warm up so the window has lead-in samples
sleep 0.6

# 3) task window + command
WIN_START=$(date +%s%3N)
echo "[run-context] window start $WIN_START — running: ${CMD[*]}"
set +e
"${CMD[@]}" > "$OUT_DIR/command.log" 2>&1
EXIT_CODE=$?
set -e 2>/dev/null || true
WIN_END=$(date +%s%3N)
echo "[run-context] window end $WIN_END (exit=$EXIT_CODE)"

# capture a short tail of telemetry: vLLM finalizes per-request completion metrics
# (e2e latency, prefill/decode time, request_success) just after the response returns.
sleep 1.5

# 4) stop collectors
kill -TERM "$HW_PID" "$PROM_PID" 2>/dev/null || true
wait "$HW_PID" 2>/dev/null || true
wait "$PROM_PID" 2>/dev/null || true

# 5) OpenCode accounting (best-effort; never fails the run)
python3 "$METRICS_DIR/collect-opencode.py" --out "$OUT_DIR" --start "$WIN_START" --end "$WIN_END" || true

# 6) window manifest
DURATION_MS=$((WIN_END - WIN_START))
# JSON-encode the command properly: the build prompt is multi-line, and raw newlines /
# control chars inside a JSON string are invalid (they made aggregate.py fail and skip
# run-summary.json). Let python json.dumps do the escaping (it emits the surrounding quotes).
CMD_JSON="$(printf '%s' "${CMD[*]}" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
cat > "$OUT_DIR/window.json" <<JSON
{
  "run_id": "$RUN_ID",
  "window_start_epoch_ms": $WIN_START,
  "window_end_epoch_ms": $WIN_END,
  "duration_ms": $DURATION_MS,
  "exit_code": $EXIT_CODE,
  "command": $CMD_JSON,
  "interval_seconds": $INTERVAL,
  "metrics_url": "$METRICS_URL"
}
JSON

echo "[run-context] wrote window.json (duration ${DURATION_MS}ms)"

# 7) aggregate
if [[ "$DO_AGG" -eq 1 ]]; then
  python3 "$METRICS_DIR/aggregate.py" "$RUN_ID" --results-root "$RESULTS_ROOT" || \
    echo "[run-context] aggregate failed (see above); raw data is intact in $OUT_DIR" >&2
fi

exit "$EXIT_CODE"
