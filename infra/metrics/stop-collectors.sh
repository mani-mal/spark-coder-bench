#!/usr/bin/env bash
# stop-metrics.sh — stop a running collect-gpu-metrics.sh sampler for a given run-id.
# Usage: harness/stop-metrics.sh <run-id>
set -uo pipefail

RUN_ID="${1:-}"
if [[ -z "$RUN_ID" ]]; then
  echo "Usage: $0 <run-id>" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$REPO_ROOT/results/raw/$RUN_ID/sampler.pid"

if [[ ! -f "$PIDFILE" ]]; then
  echo "No sampler PID file for run '$RUN_ID' ($PIDFILE). Nothing to stop." >&2
  exit 1
fi

PID="$(cat "$PIDFILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill -TERM "$PID"
  echo "Sent TERM to sampler PID $PID for run '$RUN_ID'."
else
  echo "Sampler PID $PID not running; removing stale PID file."
  rm -f "$PIDFILE"
fi
