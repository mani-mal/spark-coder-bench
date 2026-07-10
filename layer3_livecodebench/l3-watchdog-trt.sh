#!/usr/bin/env bash
# l3-watchdog-trt.sh — TensorRT-LLM variant of l3-watchdog.sh for the nemotron L3 run.
#
# Why a separate file: TRT-LLM differs from vLLM in three ways the vLLM watchdog can't
# handle, so rather than risk the working vLLM watchdog we fork it:
#   1) the container is `trtllm-server` on :8355 (not `vllm-server` on :8000);
#   2) TRT-LLM exposes NO Prometheus /metrics, so we cannot count
#      vllm:request_success_total. Progress is tracked instead via the newest mtime of
#      the run log (lcb_runner's tqdm writes per problem) and the --use_cache file
#      (rewritten every cache_batch_size=16 problems);
#   3) on TRT death we re-serve via serve-model-trtllm.sh, which BLOCKS until readiness +
#      sanity (engine load can take many minutes) — so re-serve runs in the foreground.
#
# run-suite.sh reads its endpoint from $VLLM_BASE_URL; we export it pointing at :8355 so
# the OpenAI client (and every relaunch) hits TRT-LLM, not the (now torn-down) vLLM.
#
# A false TRT restart costs a full ~40-min engine reload, so the stall threshold is
# deliberately conservative (45 min > the 30-min --openai_timeout for a single request).
#
# Usage: l3-watchdog-trt.sh <profile> <end-date> <window> <runlog>
#   e.g. l3-watchdog-trt.sh nemotron-super 2024-05-31 pre2024m06 .lcb/run-nemotron-l3.log
set -uo pipefail   # deliberately NOT -e: the watchdog handles errors itself.

PROFILE="${1:?usage: l3-watchdog-trt.sh <profile> <end-date> <window> <runlog>}"
END_DATE="${2:?need end-date}"
WINDOW="${3:?need window}"
RUNLOG="${4:?need runlog path}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
# shellcheck disable=SC1091
source env.sh 2>/dev/null || true
API_KEY="${VLLM_API_KEY:-local-dgx-spark-key}"
TRT_PORT="${TRT_PORT:-8355}"
# run-suite.sh sets OPENAI_BASE_URL from L3_BASE_URL (which env.sh does NOT clobber, unlike
# VLLM_BASE_URL) — point it at TRT-LLM.
export L3_BASE_URL="http://127.0.0.1:${TRT_PORT}/v1"

RUN_ID="${PROFILE}-l3-lcb-${WINDOW}-1"
SCORE="results/raw/${RUN_ID}/lcb-score.json"
GEN_JSON=".lcb/LiveCodeBench/output/${PROFILE}/Scenario.codegeneration_1_0.2.json"
CACHE_JSON=".lcb/LiveCodeBench/cache/${PROFILE}/Scenario.codegeneration_1_0.2.json"
HEARTBEAT=".lcb/l3-watchdog-${PROFILE}.status"

MAX_RESTARTS=6
STALL_SECS=2700          # 45 min with no log/cache growth == stalled (> 30-min openai_timeout)
POLL=60

trt_up()      { docker ps --filter name=trtllm-server --filter status=running --format '{{.Names}}' | grep -q trtllm-server; }
trt_ready()   { curl -sf "http://127.0.0.1:${TRT_PORT}/v1/models" -H "Authorization: Bearer ${API_KEY}" >/dev/null 2>&1; }
gen_alive()   { ps -eo args | grep -q "[l]cb_runner.runner.main .*${PROFILE}"; }
suite_alive() { ps -eo args | grep -q "[r]un-suite.sh .*${PROFILE}"; }
# progress signal: newest mtime (epoch secs) across run log + cache file; 0 if neither exists.
progress_ts() {
  local m=0 f t
  for f in "$RUNLOG" "$CACHE_JSON"; do
    [[ -f "$f" ]] || continue
    t=$(stat -c %Y "$f" 2>/dev/null || echo 0)
    (( t > m )) && m=$t
  done
  echo "$m"
}
# Ground-truth generation signal: TRT executor iterations in the recent window. This is the
# reliable progress signal — RUNLOG mtime freezes between cache flushes (the prom-scraper stops
# writing and lcb_runner's cache only flushes every cache_batch_size problems), so mtime alone
# can look "stalled" for a long time while generation is in fact healthy. If the executor is
# iterating, it is NOT stalled.
recent_iters() { docker logs --since 130s trtllm-server 2>&1 | grep -c "iter ="; }

launch_gen() {
  setsid bash -c "cd '$REPO_ROOT' && L3_BASE_URL='$L3_BASE_URL' bash layer3_livecodebench/run-suite.sh \
    --profile $PROFILE --end-date $END_DATE --window $WINDOW --sandbox" >> "$RUNLOG" 2>&1 &
}
reserve_trt() {   # BLOCKING: serve-model-trtllm.sh waits for readiness + sanity itself.
  bash infra/trtllm/serve-model-trtllm.sh "$PROFILE" >> ".lcb/serve-${PROFILE}-watchdog.log" 2>&1
}

hb() {  # heartbeat: $1=state  $2=detail
  local age="n/a" p; p=$(progress_ts)
  [[ "$p" -gt 0 ]] && age="$(( $(date +%s) - p ))s"
  printf '%s state=%s restarts=%d last_progress=%s vllm/trt=%s gen=%s suite=%s %s\n' \
    "$(date -u +%FT%TZ)" "$1" "$restarts" "$age" \
    "$(trt_up && echo up || echo DOWN)" \
    "$(gen_alive && echo y || echo n)" \
    "$(suite_alive && echo y || echo n)" \
    "${2:-}" > "$HEARTBEAT"
}

restarts=0
last_progress_ts=$(progress_ts); [[ "$last_progress_ts" -eq 0 ]] && last_progress_ts=$(date +%s)
echo "$(date -u +%FT%TZ) watchdog-trt start profile=$PROFILE window=$WINDOW endpoint=$VLLM_BASE_URL" >> "$HEARTBEAT.log"

while :; do
  if [[ -f "$SCORE" ]]; then
    hb DONE "score written"
    echo "$(date -u +%FT%TZ) DONE score=$SCORE" >> "$HEARTBEAT.log"
    exit 0
  fi

  now=$(date +%s)
  in_eval=0; [[ -f "$GEN_JSON" ]] && in_eval=1   # gen finished -> eval/score phase (no TRT needed)

  # progress tracking (log/cache mtime advancing == something is happening)
  cur=$(progress_ts)
  if [[ "$cur" -gt "$last_progress_ts" ]]; then last_progress_ts="$cur"; fi
  # ...but the AUTHORITATIVE signal is the TRT executor iterating. Reset the stall timer whenever
  # it is, so a frozen RUNLOG between cache flushes can never trigger a false-stall restart.
  if [[ "$(recent_iters)" -gt 0 ]]; then last_progress_ts="$now"; fi

  if gen_alive || suite_alive; then
    # alive. check for a true stall (generating, TRT up, no progress for STALL_SECS).
    if [[ "$in_eval" -eq 0 ]] && trt_up && (( now - last_progress_ts > STALL_SECS )); then
      if (( restarts < MAX_RESTARTS )); then
        restarts=$((restarts+1)); hb STALL_RESTART "no progress ${STALL_SECS}s -> resume from cache"
        echo "$(date -u +%FT%TZ) STALL restart #$restarts" >> "$HEARTBEAT.log"
        pkill -f "[l]cb_runner.runner.main .*${PROFILE}" 2>/dev/null
        pkill -f "[r]un-suite.sh .*${PROFILE}" 2>/dev/null
        sleep 5; launch_gen; last_progress_ts=$(date +%s); sleep "$POLL"; continue
      else
        hb GAVE_UP "stall after $MAX_RESTARTS restarts"; exit 2
      fi
    fi
    hb RUNNING "$([[ $in_eval -eq 1 ]] && echo eval/score || echo generating)"
    sleep "$POLL"; continue
  fi

  # neither lcb_runner nor run-suite.sh alive, and no score -> crashed.
  # Re-serve TRT only if it's actually down AND we still need it (generation phase).
  # During eval the gen is cached (0 remaining -> no API calls), so a relaunch needs no TRT.
  if [[ "$in_eval" -eq 0 ]] && ! trt_ready; then
    hb TRT_DOWN "re-serving trtllm (blocking, engine load) then resuming"
    echo "$(date -u +%FT%TZ) TRT down -> re-serve" >> "$HEARTBEAT.log"
    reserve_trt || true
  fi

  if (( restarts < MAX_RESTARTS )); then
    restarts=$((restarts+1)); hb CRASH_RESTART "lcb_runner+suite gone -> resume from cache (#$restarts)"
    echo "$(date -u +%FT%TZ) CRASH restart #$restarts" >> "$HEARTBEAT.log"
    launch_gen; last_progress_ts=$(date +%s); sleep "$POLL"
  else
    hb GAVE_UP "crashed $MAX_RESTARTS times; manual look needed"
    echo "$(date -u +%FT%TZ) GAVE UP after $MAX_RESTARTS" >> "$HEARTBEAT.log"
    exit 2
  fi
done
