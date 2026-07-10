#!/usr/bin/env bash
# run-suite.sh — Layer 3 (LiveCodeBench code-generation) for ONE served model.
#
# Two clean passes, mirroring the L1/L2 conventions:
#   1) GENERATION under the 3-source metric window (run-context.sh) — clean GPU,
#      single-stream (--multiprocess 1). Produces results/raw/<run-id>/run-summary.json.
#   2) EVALUATION outside the window (executes untrusted model code → sandbox it).
#      Reuses the saved generations (--continue_existing) so NO new API calls happen;
#      lcb_runner rebuilds combined_results from the saved file and grades them.
# Then score.py → results/raw/<run-id>/lcb-score.json (pass@1 + Wilson 95% CI).
#
# The served model must already be up on :8000 with --served-model-name == <profile>,
# and <profile> must be a registered entry in lcb_runner/lm_styles.py (see lm_styles.patch).
#
# Usage:
#   run-suite.sh --profile qwen3-coder-30b --end-date 2024-05-31 --window pre2024m06 [opts]
# Options:
#   --profile NAME     served-model-name (== lm_styles model_name)         [required]
#   --end-date YMD     keep problems with contest_date <= this             [required]
#   --start-date YMD   keep problems with contest_date >= this             [optional]
#   --window LABEL     short tag for the run-id (e.g. pre2024m06)          [required]
#   --release VER      LCB release (default release_v6)
#   --n N              samples per problem (default 1 — our shared config)
#   --temperature T    decode temperature (default 0.2 — shared config)
#   --max-tokens M     max completion tokens (default 8192, held constant)
#   --openai-timeout S per-request client timeout, seconds (default 1800). MUST exceed the
#                      worst-case full generation (max_tokens / decode_tok_s); too low makes long
#                      generations time out and retry futilely, then the whole run aborts.
#   --seq K            repeat index for the run-id (default 1)
#   --sandbox          run the eval pass under bwrap (fs isolation, no net, tmpfs /tmp)
#   --no-window        run generation WITHOUT run-context.sh (debug only)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LCB_DIR="$REPO_ROOT/.lcb/LiveCodeBench"
VENV_PY="$REPO_ROOT/.lcb/venv/bin/python"
RUN_CONTEXT="$REPO_ROOT/infra/metrics/run-context.sh"

PROFILE="" END_DATE="" START_DATE="" WINDOW="" RELEASE="release_v6"
N=1 TEMP="0.2" MAX_TOKENS=8192 SEQ=1 SANDBOX=0 USE_WINDOW=1 OPENAI_TIMEOUT=1800
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    --end-date) END_DATE="$2"; shift 2 ;;
    --start-date) START_DATE="$2"; shift 2 ;;
    --window) WINDOW="$2"; shift 2 ;;
    --release) RELEASE="$2"; shift 2 ;;
    --n) N="$2"; shift 2 ;;
    --temperature) TEMP="$2"; shift 2 ;;
    --max-tokens) MAX_TOKENS="$2"; shift 2 ;;
    --openai-timeout) OPENAI_TIMEOUT="$2"; shift 2 ;;
    --seq) SEQ="$2"; shift 2 ;;
    --sandbox) SANDBOX=1; shift ;;
    --no-window) USE_WINDOW=0; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done
[[ -z "$PROFILE" || -z "$END_DATE" || -z "$WINDOW" ]] && {
  echo "Usage: $0 --profile NAME --end-date YMD --window LABEL [opts]" >&2; exit 1; }
[[ -x "$VENV_PY" ]] || { echo "Missing venv at $VENV_PY — run setup-lcb.sh first" >&2; exit 1; }

# --- env: point the OpenAI SDK at the local vLLM endpoint (read at import time) ---
# shellcheck disable=SC1091
source "$REPO_ROOT/env.sh"
# L3_BASE_URL wins over VLLM_BASE_URL. env.sh re-sources <vllm-serving-lab>/.env, which force-exports
# VLLM_BASE_URL back to :8000 — so a caller that exports VLLM_BASE_URL (e.g. for a TRT-LLM model on
# :8355) gets clobbered. Pass L3_BASE_URL instead; it is set AFTER env.sh and is not touched by it.
export OPENAI_BASE_URL="${L3_BASE_URL:-${VLLM_BASE_URL:-http://127.0.0.1:8000/v1}}"
export OPENAI_KEY="${VLLM_API_KEY:-local-dgx-spark-key}"
# datasets cache must be user-writable. env.sh points HF_HOME at ~/.cache/huggingface
# (the *model* cache, root-owned because docker pulls as root) — datasets can't write there,
# so force a user-writable HF_HOME for this process. Override with L3_HF_HOME if needed.
export HF_HOME="${L3_HF_HOME:-$REPO_ROOT/.hf-cache}"
mkdir -p "$HF_HOME"

RUN_ID="${PROFILE}-l3-lcb-${WINDOW}-${SEQ}"
OUT_DIR="$REPO_ROOT/results/raw/$RUN_ID"
echo "[l3] run_id=$RUN_ID  endpoint=$OPENAI_BASE_URL  window<=$END_DATE  n=$N temp=$TEMP"

DATE_ARGS=(--end_date "$END_DATE")
[[ -n "$START_DATE" ]] && DATE_ARGS+=(--start_date "$START_DATE")

# Generation concurrency. Default 1 (single-stream) so decode-tok/s & energy stay comparable
# to the agentic layers for the vLLM models. Override with L3_MULTIPROCESS>1 ONLY when the
# serving runtime yields no usable throughput/energy metrics anyway (TRT-LLM: no Prometheus),
# so parallelism costs nothing and rescues wall-clock. pass@1 is per-problem and unaffected by
# batching. Bounded by the server's max_batch_size. See docs/findings 2026-07-01.
GEN_MULTIPROCESS="${L3_MULTIPROCESS:-1}"
GEN_CMD=("$VENV_PY" -m lcb_runner.runner.main
  --model "$PROFILE" --scenario codegeneration --release_version "$RELEASE"
  "${DATE_ARGS[@]}" --n "$N" --temperature "$TEMP" --max_tokens "$MAX_TOKENS"
  --top_p 0.95 --multiprocess "$GEN_MULTIPROCESS" --openai_timeout "$OPENAI_TIMEOUT"
  --continue_existing
  # --use_cache persists each generation to cache/<model>/... every --cache_batch_size
  # problems (save_cache()). Without it, a post-processing crash AFTER generation but
  # BEFORE save_results loses the entire run's outputs (cost us a 12h gpt-oss run on
  # 2026-06-30). batch 16 bounds worst-case re-generation to 16 problems on resume.
  --use_cache --cache_batch_size 16)

# lcb_runner writes output/ relative to CWD → run from the LCB dir so artifacts land there.
cd "$LCB_DIR"

# --- M5: provenance guard for lcb's (model,n,temp)-only cache key ----------------
# lcb_runner keys generation output/cache by (model, n, temp) ONLY — not by window, --seq, or
# serving runtime/endpoint. So --continue_existing/--use_cache would silently reuse a DIFFERENT
# run's generations if you change only the window, the repeat index, or the runtime. Refuse to
# resume onto generations produced under different provenance; a genuine same-run resume matches.
PROV_FILE="$LCB_DIR/output/.l3-provenance-codegeneration_${N}_${TEMP}.json"
EXISTING_GEN="$(ls "$LCB_DIR"/output/*/*codegeneration_"${N}"_"${TEMP}"*.json 2>/dev/null | grep -v _eval | head -1 || true)"
if [[ -n "$EXISTING_GEN" && -f "$PROV_FILE" ]]; then
  if ! "$VENV_PY" - "$PROV_FILE" "$PROFILE" "$WINDOW" "$SEQ" "$END_DATE" "$OPENAI_BASE_URL" <<'PY'
import json, sys
f, profile, window, seq, end_date, endpoint = sys.argv[1:7]
p = json.load(open(f))
ok = (p.get("profile") == profile and str(p.get("window")) == window and
      str(p.get("seq")) == seq and str(p.get("end_date")) == end_date and
      p.get("endpoint") == endpoint)
sys.exit(0 if ok else 1)
PY
  then
    echo "[l3] ERROR (M5): existing generations for (model=$PROFILE, n=$N, temp=$TEMP) were produced" >&2
    echo "     under different provenance: $(cat "$PROV_FILE")" >&2
    echo "     Resuming would grade the wrong window/seq/runtime. Clear $LCB_DIR/output/<model>/ and" >&2
    echo "     $LCB_DIR/cache/, or run with a fresh L3_HF_HOME/output dir, then retry." >&2
    exit 1
  fi
fi

# --- Pass 1: generation under the metric window --------------------------------
echo "[l3] === generation pass ==="
if [[ "$USE_WINDOW" -eq 1 ]]; then
  bash "$RUN_CONTEXT" "$RUN_ID" -- "${GEN_CMD[@]}"
else
  "${GEN_CMD[@]}"
  mkdir -p "$OUT_DIR"
fi

# Record provenance of the generations now in the (model,n,temp) cache slot (M5).
printf '{"profile":"%s","n":%s,"temp":%s,"window":"%s","seq":"%s","end_date":"%s","endpoint":"%s"}\n' \
  "$PROFILE" "$N" "$TEMP" "$WINDOW" "$SEQ" "$END_DATE" "$OPENAI_BASE_URL" > "$PROV_FILE"

# --- Pass 2: evaluation (sandboxed; reuses saved generations, no API calls) -----
echo "[l3] === evaluation pass (sandbox=$SANDBOX) ==="
EVAL_CMD=("$VENV_PY" -m lcb_runner.runner.main
  --model "$PROFILE" --scenario codegeneration --release_version "$RELEASE"
  "${DATE_ARGS[@]}" --n "$N" --temperature "$TEMP" --max_tokens "$MAX_TOKENS"
  --top_p 0.95 --multiprocess 1 --continue_existing --evaluate
  # With the main.py filter fix, eval sees 0 "remaining" problems and does no
  # generation. Pass --openai_timeout anyway as defense: if any problem ever is
  # remaining, eval must use the long timeout, not lcb_runner's short default
  # (which caused APITimeout->AssertionError crash loops). See docs/findings 2026-06-30.
  --openai_timeout "$OPENAI_TIMEOUT"
  --num_process_evaluate 12 --timeout 6)

# Probe whether bwrap can actually create the namespaces we need. Some kernels
# (e.g. DGX Spark GB10 aarch64) deny unprivileged user/net namespace setup
# (uid-map "Permission denied" / loopback "RTM_NEWADDR Operation not permitted"),
# so bwrap is installed but unusable — fall back to lcb_runner's own per-submission
# process+timeout isolation. See coverage.md "Evaluation execution environment".
bwrap_usable() {
  command -v bwrap >/dev/null 2>&1 || return 1
  bwrap --ro-bind / / --proc /proc --unshare-net --die-with-parent -- /bin/true >/dev/null 2>&1
}

if [[ "$SANDBOX" -eq 1 ]] && bwrap_usable; then
  echo "[l3] eval under bwrap (fs-isolated, no network)"
  # fs-isolate, no network, throwaway /tmp; dataset is cached from pass 1 so go offline.
  # HF_HOME ($REPO_ROOT/.hf-cache) must be RW: datasets writes .lock files into the
  # cache dir even in offline mode, which fails on the read-only root mount.
  HF_DATASETS_OFFLINE=1 HF_HUB_OFFLINE=1 \
  bwrap --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp \
        --bind "$LCB_DIR" "$LCB_DIR" --bind "$REPO_ROOT/.lcb" "$REPO_ROOT/.lcb" \
        --bind "$HF_HOME" "$HF_HOME" \
        --unshare-net --die-with-parent \
        "${EVAL_CMD[@]}"
else
  if [[ "$SANDBOX" -eq 1 ]]; then
    echo "[l3] WARNING: --sandbox requested but bwrap cannot create namespaces on this kernel; \
running eval with lcb_runner's built-in process+timeout isolation only (no fs/net isolation). See coverage.md." >&2
  else
    echo "[l3] NOTE: eval runs untrusted generated code unsandboxed. Use --sandbox for real runs." >&2
  fi
  HF_DATASETS_OFFLINE=1 HF_HUB_OFFLINE=1 "${EVAL_CMD[@]}"
fi

# --- Score: pass@1 + Wilson 95% CI --------------------------------------------
REPR="$PROFILE"   # model_repr == model_name for our entries
# lcb_runner builds the filename from str(args.scenario), i.e. the enum repr "Scenario.codegeneration".
EVAL_ALL="$LCB_DIR/output/$REPR/Scenario.codegeneration_${N}_${TEMP}_eval_all.json"
GEN_FILE="$LCB_DIR/output/$REPR/Scenario.codegeneration_${N}_${TEMP}.json"
mkdir -p "$OUT_DIR"
[[ -f "$GEN_FILE" ]] && cp "$GEN_FILE" "$OUT_DIR/lcb-predictions.json"

"$VENV_PY" "$REPO_ROOT/layer3_livecodebench/eval/score.py" \
  --eval-all "$EVAL_ALL" --out "$OUT_DIR/lcb-score.json" \
  --n-samples "$N" --start-date "${START_DATE:-}" --end-date "$END_DATE" \
  --release-version "$RELEASE"

echo "[l3] done: $OUT_DIR/{run-summary.json,lcb-score.json,lcb-predictions.json}"
