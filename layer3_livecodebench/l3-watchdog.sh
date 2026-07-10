#!/usr/bin/env bash
# l3-watchdog.sh — keep a long L3 run alive with fast failure detection + auto-resume.
#
# Why: an L3 generation is ~12h single-stream. A crash/stall/vLLM-death that goes
# unnoticed wastes the whole night. run-suite.sh now generates with --use_cache, so a
# relaunch resumes from cache (loses <= cache_batch_size=16 problems). This watchdog is
# the thing that *notices* a failure within ~60s and does the relaunch automatically.
#
# It writes a heartbeat file you can `cat` at any time, auto-restarts vLLM if it dies,
# and gives up after MAX_RESTARTS to avoid an infinite crash loop.
#
# Usage: l3-watchdog.sh <profile> <end-date> <window> <runlog>
#   e.g. l3-watchdog.sh gpt-oss-120b 2024-05-31 pre2024m06 .lcb/run-gpt-oss-l3.log
set -uo pipefail   # deliberately NOT -e: the watchdog handles errors itself.

PROFILE="${1:?usage: l3-watchdog.sh <profile> <end-date> <window> <runlog>}"
END_DATE="${2:?need end-date}"
WINDOW="${3:?need window}"
RUNLOG="${4:?need runlog path}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
# shellcheck disable=SC1091
source env.sh 2>/dev/null || true
API_KEY="${VLLM_API_KEY:-local-dgx-spark-key}"

RUN_ID="${PROFILE}-l3-lcb-${WINDOW}-1"
SCORE="results/raw/${RUN_ID}/lcb-score.json"
GEN_JSON=".lcb/LiveCodeBench/output/${PROFILE}/Scenario.codegeneration_1_0.2.json"
HEARTBEAT=".lcb/l3-watchdog-${PROFILE}.status"

MAX_RESTARTS=6
STALL_SECS=1500          # 25 min with no new completion while generating == stalled
POLL=60

vllm_up()    { docker ps --filter name=vllm-server --filter status=running --format '{{.Names}}' | grep -q vllm-server; }
gen_alive()  { ps -eo args | grep -q "[l]cb_runner.runner.main .*${PROFILE}"; }
suite_alive(){ ps -eo args | grep -q "[r]un-suite.sh .*${PROFILE}"; }
completions(){ curl -s "http://127.0.0.1:8000/metrics" -H "Authorization: Bearer ${API_KEY}" 2>/dev/null \
                 | awk '/^vllm:request_success_total/{s+=$2} END{printf "%d", s+0}'; }

launch_gen() {
  setsid bash -c "cd '$REPO_ROOT' && bash layer3_livecodebench/run-suite.sh \
    --profile $PROFILE --end-date $END_DATE --window $WINDOW --sandbox" >> "$RUNLOG" 2>&1 &
}
restart_vllm() {
  setsid bash -c "cd '$REPO_ROOT' && bash infra/vllm/serve-model.sh $PROFILE" \
    >> ".lcb/serve-${PROFILE}-watchdog.log" 2>&1 &
}

hb() {  # heartbeat: $1=state  $2=detail
  printf '%s state=%s restarts=%d completions=%s vllm=%s gen=%s suite=%s %s\n' \
    "$(date -u +%FT%TZ)" "$1" "$restarts" "$(completions)" \
    "$(vllm_up && echo up || echo DOWN)" \
    "$(gen_alive && echo y || echo n)" \
    "$(suite_alive && echo y || echo n)" \
    "${2:-}" > "$HEARTBEAT"
}

restarts=0
last_count=-1
last_progress_ts=$(date +%s)
echo "$(date -u +%FT%TZ) watchdog start profile=$PROFILE window=$WINDOW" >> "$HEARTBEAT.log"

while :; do
  if [[ -f "$SCORE" ]]; then
    hb DONE "score written"
    echo "$(date -u +%FT%TZ) DONE score=$SCORE" >> "$HEARTBEAT.log"
    exit 0
  fi

  now=$(date +%s)
  in_eval=0; [[ -f "$GEN_JSON" ]] && in_eval=1   # gen finished -> eval/score phase

  # progress tracking (only meaningful during generation)
  cur=$(completions)
  if [[ "$cur" =~ ^[0-9]+$ && "$cur" -gt "$last_count" ]]; then
    last_count="$cur"; last_progress_ts="$now"
  fi

  if gen_alive || suite_alive; then
    # alive. check for a true stall (generating, vLLM up, no progress for STALL_SECS).
    if [[ "$in_eval" -eq 0 ]] && vllm_up && (( now - last_progress_ts > STALL_SECS )); then
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
  if ! vllm_up; then
    hb VLLM_DOWN "restarting vllm then resuming"
    echo "$(date -u +%FT%TZ) vLLM down -> restart" >> "$HEARTBEAT.log"
    restart_vllm
    # wait up to 10 min for vLLM to come back before resuming generation
    for _ in $(seq 1 40); do vllm_up && curl -sf "http://127.0.0.1:8000/v1/models" \
        -H "Authorization: Bearer ${API_KEY}" >/dev/null 2>&1 && break; sleep 15; done
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
