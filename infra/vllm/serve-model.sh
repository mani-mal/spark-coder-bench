#!/usr/bin/env bash
# serve-model.sh — serve ONE model on vLLM (OpenAI-compatible) on :8000, sequentially.
#
# DGX Spark has 128GB unified memory: only one large model fits at a time, so the
# A/B comparison swaps models rather than running them concurrently. After the
# server is healthy this writes a full run manifest (every effective config +
# tool versions) to manifests/ for arXiv reproducibility.
#
# Usage: serve-model.sh <profile>
#   profiles: qwen3-coder-30b | nemotron-super   (see infra/vllm/model-profiles/)
set -euo pipefail

PROFILE="${1:-}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROFILE_DIR="$REPO_ROOT/infra/vllm/model-profiles"

if [[ -z "$PROFILE" || ! -f "$PROFILE_DIR/$PROFILE.env" ]]; then
  echo "Usage: $0 <profile>" >&2
  echo "Available:" >&2; ls "$PROFILE_DIR"/*.env 2>/dev/null | xargs -n1 basename | sed 's/.env$//' >&2
  exit 1
fi

# Base settings (image, api key, HF cache) come from the lab .env if present.
LAB_ENV="$HOME/dgx-coding-lab/.env"
[[ -f "$LAB_ENV" ]] && source "$LAB_ENV"
VLLM_HOST="${VLLM_HOST:-0.0.0.0}"
VLLM_PORT="${VLLM_PORT:-8000}"
VLLM_API_KEY="${VLLM_API_KEY:-local-dgx-spark-key}"
VLLM_IMAGE="${VLLM_IMAGE:-nvcr.io/nvidia/vllm:26.02-py3}"
HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"

# shellcheck disable=SC1090
source "$PROFILE_DIR/$PROFILE.env"

echo "[serve] profile=$PROFILE model=$MODEL_ID served=$SERVED_MODEL_NAME port=$VLLM_PORT image=$VLLM_IMAGE"
docker rm -f vllm-server >/dev/null 2>&1 || true

ENV_ARGS=( -e "VLLM_API_KEY=$VLLM_API_KEY" )
for v in HF_TOKEN VLLM_FLASHINFER_MOE_BACKEND VLLM_USE_FLASHINFER_MOE_FP4 VLLM_USE_FLASHINFER_MOE_FP8; do
  [[ -n "${!v:-}" ]] && ENV_ARGS+=( -e "$v=${!v}" )
done

# shellcheck disable=SC2086
docker run -d --name vllm-server \
  --gpus all --ipc=host --network=host \
  --ulimit memlock=-1 --ulimit stack=67108864 \
  -v "$HF_HOME:/root/.cache/huggingface" \
  "${ENV_ARGS[@]}" \
  "$VLLM_IMAGE" \
  vllm serve "$MODEL_ID" \
    --host "$VLLM_HOST" --port "$VLLM_PORT" \
    --api-key "$VLLM_API_KEY" \
    --served-model-name "$SERVED_MODEL_NAME" \
    --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
    --max-model-len "$MAX_MODEL_LEN" \
    --max-num-seqs "$MAX_NUM_SEQS" \
    --max-num-batched-tokens "$MAX_NUM_BATCHED_TOKENS" \
    $EXTRA_VLLM_ARGS

echo "[serve] waiting for readiness on :$VLLM_PORT ..."
READY=0
# 360*5s = 30 min. A warm model answers in seconds; the long ceiling is for a COLD load of a large
# checkpoint (e.g. gpt-oss-120b ~61GB MXFP4) swapped in right after another model, when page cache
# is cold and 15 min was too tight (the container stays running but isn't ready yet → not a crash,
# so the fail-fast below doesn't fire). A successful load still returns immediately.
for _ in $(seq 1 360); do
  if curl -sf "http://127.0.0.1:$VLLM_PORT/v1/models" -H "Authorization: Bearer $VLLM_API_KEY" >/dev/null 2>&1; then
    READY=1; break
  fi
  # Fail fast: if the container has already exited (e.g. an unsupported quant config or
  # a parser flag crash happens in seconds), don't keep polling a dead container for 15 min.
  if [[ "$(docker inspect -f '{{.State.Running}}' vllm-server 2>/dev/null)" != "true" ]]; then
    echo "[serve] container exited before becoming ready — last log lines:" >&2
    docker logs vllm-server 2>&1 | tail -25 >&2
    exit 1
  fi
  sleep 5
done
if [[ "$READY" -ne 1 ]]; then
  echo "[serve] NOT ready after timeout; check: docker logs -f vllm-server" >&2
  exit 1
fi
echo "[serve] ready."

# ---- model metadata (registry + config.json) ----
MODEL_META="$(python3 "$REPO_ROOT/infra/vllm/model-metadata.py" --profile "$PROFILE" 2>/dev/null || echo '{}')"

# ---- SM121/FP4 sanity gate (abort timed runs if it fails) ----
SANITY_DIR="$(mktemp -d)"
if python3 "$REPO_ROOT/infra/vllm/sanity-check.py" --served "$SERVED_MODEL_NAME" \
     --out "$SANITY_DIR" --base-url "http://127.0.0.1:$VLLM_PORT/v1" \
     --api-key "$VLLM_API_KEY" --temperature "$DECODE_TEMPERATURE" --seed "$SEED"; then
  SANITY_OK=true
else
  SANITY_OK=false
  echo "[serve] *** SANITY CHECK FAILED for $SERVED_MODEL_NAME — DO NOT record timed runs;" >&2
  echo "[serve] *** likely SM121/FP4 kernel or kv-cache-dtype issue. See manifest. ***" >&2
fi
SANITY_JSON="$(cat "$SANITY_DIR/sanity-check.json" 2>/dev/null || echo '{}')"
rm -rf "$SANITY_DIR"

# Everything below is best-effort manifest metadata. Relax strict mode: several probes
# use early-exit pipelines (e.g. `nvidia-smi -q | awk '.../{exit}'`) whose upstream gets
# SIGPIPE when the reader exits, which under `set -e -o pipefail` was aborting the script
# with exit 141 BEFORE the manifest was written. The server is already up; never let
# metadata gathering kill the run.
set +e +o pipefail

# ---- MoE residency evidence (sparse-activation analysis assumes resident experts) ----
if echo "$EXTRA_VLLM_ARGS" | grep -q 'cpu-offload'; then OFFLOAD=true; else OFFLOAD=false; fi
MEM_USED_MIB="$(awk '/^MemTotal:/{t=$2} /^MemAvailable:/{a=$2} END{printf "%d",(t-a)/1024}' /proc/meminfo)"
BW_SOURCE="$(command -v dcgmi >/dev/null 2>&1 && echo 'DCGM (dcgmi dmon)' || echo 'nvidia-smi utilization.memory (proxy; DCGM not installed)')"

# ---- write run manifest ----
mkdir -p "$REPO_ROOT/manifests"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
MANIFEST="$REPO_ROOT/manifests/serve-${SERVED_MODEL_NAME}-${TS}.json"
VLLM_VERSION="$(docker exec vllm-server python -c 'import vllm;print(vllm.__version__)' 2>/dev/null || echo unknown)"
DRIVER="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ')"
CUDA="$(nvidia-smi -q 2>/dev/null | awk -F: '/CUDA Version/{print $2; exit}' | tr -d ' ')"
GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 | sed 's/^ *//')"
OS_NAME="$(. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME")"
DCGM_VER="$(command -v dcgmi >/dev/null 2>&1 && dcgmi --version 2>/dev/null | head -1 || echo 'not installed')"
TEGRA="$(command -v tegrastats >/dev/null 2>&1 && echo available || echo 'not installed')"
POWER_LEVEL="GPU-only (nvidia-smi power.draw)"
# NB: must be a full if — a bare `[[ ]] && ...` returns 1 when false and, under
# `set -e`, would abort the script before the manifest is written (it did: tegrastats
# is not installed here, so the test is always false).
if [[ "$TEGRA" == "available" ]]; then
  POWER_LEVEL="full-SoC (tegrastats) + GPU-only (nvidia-smi)"
fi

cat > "$MANIFEST" <<JSON
{
  "timestamp_utc": "$TS",
  "host": "$(hostname)",
  "profile": "$PROFILE",
  "model_id": "$MODEL_ID",
  "served_model_name": "$SERVED_MODEL_NAME",
  "serving": {
    "image": "$VLLM_IMAGE",
    "vllm_version": "$VLLM_VERSION",
    "port": $VLLM_PORT,
    "gpu_memory_utilization": $GPU_MEMORY_UTILIZATION,
    "max_model_len": $MAX_MODEL_LEN,
    "max_num_seqs": $MAX_NUM_SEQS,
    "max_num_batched_tokens": $MAX_NUM_BATCHED_TOKENS,
    "seed": $SEED,
    "decode_temperature": $DECODE_TEMPERATURE,
    "kv_cache_dtype": "$KV_CACHE_DTYPE",
    "extra_args": "$(echo "$EXTRA_VLLM_ARGS" | tr -s ' ')"
  },
  "platform": {
    "gpu_name": "$GPU_NAME",
    "driver_version": "$DRIVER",
    "cuda_version": "$CUDA",
    "os": "$OS_NAME",
    "arch": "$(uname -m)",
    "dcgm_version": "$DCGM_VER",
    "tegrastats": "$TEGRA"
  },
  "power_measurement_level": "$POWER_LEVEL",
  "bandwidth_source": "$BW_SOURCE",
  "model_metadata": $MODEL_META,
  "sanity_check": $SANITY_JSON,
  "moe_residency": {
    "all_experts_resident": $([ "$OFFLOAD" = false ] && echo true || echo false),
    "offload_detected": $OFFLOAD,
    "unified_mem_used_mib_after_load": $MEM_USED_MIB,
    "evidence": "no --cpu-offload-gb flag in serving args; vLLM loads all expert weights into unified memory by default"
  },
  "fairness_note": "Quantization differs by model (native: Qwen bf16, Nemotron NVFP4, DeepSeek bf16) — disclosed confound; no NVFP4 checkpoints for the bf16 models and FP4 on SM121 is unsafe. max_model_len and gpu_memory_utilization also differ under the 128GB unified-memory limit. seed, temperature, kv_cache_dtype, max_num_seqs and the OpenCode/vLLM versions are held identical. The intended variable is model identity."
}
JSON

echo "[serve] manifest -> $MANIFEST"
echo "[serve] follow logs: docker logs -f vllm-server"

# M16: the sanity gate must be able to ABORT a run, not just print a warning — otherwise timed
# runs get recorded against a model that failed the coherence gate and nothing downstream checks
# sanity_check.ok. The manifest is already written above (the failure is on record), so now surface
# the gate result in the exit code. Fail closed; override with ALLOW_FAILED_SANITY=1 for the
# reasoning-model case where the coherence bar is largely unexercised (budget goes to a stripped
# reasoning channel) or for deliberate debugging.
if [[ "${SANITY_OK:-false}" != "true" && "${ALLOW_FAILED_SANITY:-0}" != "1" ]]; then
  echo "[serve] *** exiting nonzero: sanity gate FAILED. Set ALLOW_FAILED_SANITY=1 to serve anyway. ***" >&2
  exit 3
fi
