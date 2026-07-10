#!/usr/bin/env bash
# serve-model-trtllm.sh — serve ONE model on TensorRT-LLM (OpenAI-compatible) on :8355.
#
# The TRT-LLM analog of infra/vllm/serve-model.sh. Same sequential single-model model
# (128GB unified memory), same sanity gate, same manifest schema (runtime tagged
# "tensorrt-llm" so the analysis layer can A/B vLLM vs TRT-LLM). Uses the official
# DGX Spark container + trtllm-serve recipe (port 8355, --extra_llm_api_options yaml).
#
# Usage: serve-model-trtllm.sh <profile>
#   profiles live in infra/trtllm/model-profiles/<profile>.env
set -euo pipefail

PROFILE="${1:-}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROFILE_DIR="$REPO_ROOT/infra/trtllm/model-profiles"
CONFIG_DIR="$REPO_ROOT/infra/trtllm/configs"

if [[ -z "$PROFILE" || ! -f "$PROFILE_DIR/$PROFILE.env" ]]; then
  echo "Usage: $0 <profile>" >&2
  echo "Available:" >&2; ls "$PROFILE_DIR"/*.env 2>/dev/null | xargs -n1 basename | sed 's/.env$//' >&2
  exit 1
fi

LAB_ENV="$HOME/dgx-coding-lab/.env"
[[ -f "$LAB_ENV" ]] && source "$LAB_ENV"
TRT_HOST="${TRT_HOST:-0.0.0.0}"
TRT_PORT="${TRT_PORT:-8355}"                       # TRT-LLM convention on DGX Spark
TRT_API_KEY="${TRT_API_KEY:-${VLLM_API_KEY:-local-dgx-spark-key}}"
TRT_IMAGE="${TRT_IMAGE:-nvcr.io/nvidia/tensorrt-llm/release:1.3.0rc9}"
HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"

# shellcheck disable=SC1090
source "$PROFILE_DIR/$PROFILE.env"
CONFIG_YAML="$CONFIG_DIR/$PROFILE.yaml"
[[ -f "$CONFIG_YAML" ]] || { echo "[trt] missing config yaml: $CONFIG_YAML" >&2; exit 1; }

echo "[trt] profile=$PROFILE model=$MODEL_ID served=$SERVED_MODEL_NAME port=$TRT_PORT image=$TRT_IMAGE"
docker rm -f trtllm-server >/dev/null 2>&1 || true
# TRT-LLM and vLLM both want the whole GPU + most of the 128GB — never run both at once.
docker rm -f vllm-server >/dev/null 2>&1 || true

ENV_ARGS=()
# Forward HF auth + any profile-supplied TRT env (e.g. TLLM_ALLOW_LONG_MAX_MODEL_LEN for 1M ctx).
for v in HF_TOKEN TLLM_ALLOW_LONG_MAX_MODEL_LEN ${TRT_ENV_PASSTHROUGH:-}; do
  [[ -n "${!v:-}" ]] && ENV_ARGS+=( -e "$v=${!v}" )
done
# expandable_segments cuts allocator fragmentation during the big weight materialization.
# Loading the 75GB MIXED_PRECISION nemotron checkpoint without it fragmented to ~115GB and
# OOM-killed the host (see docs/findings/2026-06-27-nemotron-trtllm-memory.md).
ENV_ARGS+=( -e "PYTORCH_CUDA_ALLOC_CONF=${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}" )

# Host-protection memory cap. The 128GB pool is shared CPU+GPU; an unbounded load that climbs
# past total RAM hangs the kernel and triggers a watchdog reboot. Cap the container's cgroup so
# an over-allocation OOM-kills the CONTAINER (exit 137), never the host. Default leaves ~10GB
# for the OS; override per profile via CONTAINER_MEM_LIMIT. --memory-swap == --memory disables swap.
MEM_LIMIT="${CONTAINER_MEM_LIMIT:-112g}"
MEM_ARGS=()
[[ -n "$MEM_LIMIT" && "$MEM_LIMIT" != "none" ]] && MEM_ARGS+=( --memory "$MEM_LIMIT" --memory-swap "$MEM_LIMIT" )

# trtllm-serve flags. Parser flags are profile-supplied (nemotron needs reasoning+tool parsers;
# plain chat models may not support them — kept in EXTRA_TRT_ARGS so a profile can drop them).
# shellcheck disable=SC2086
docker run -d --name trtllm-server \
  --gpus all --ipc=host --network=host \
  --ulimit memlock=-1 --ulimit stack=67108864 \
  "${MEM_ARGS[@]}" \
  -v "$HF_HOME:/root/.cache/huggingface" \
  -v "$CONFIG_DIR:/config:ro" \
  "${ENV_ARGS[@]}" \
  "$TRT_IMAGE" \
  trtllm-serve "$MODEL_ID" \
    --host "$TRT_HOST" --port "$TRT_PORT" \
    --max_batch_size "${MAX_BATCH_SIZE:-4}" \
    --tp_size "${TP_SIZE:-1}" --ep_size "${EP_SIZE:-1}" \
    --max_num_tokens "${MAX_NUM_TOKENS:-8192}" \
    --max_seq_len "${MAX_SEQ_LEN:-65536}" \
    --extra_llm_api_options "/config/$PROFILE.yaml" \
    $EXTRA_TRT_ARGS

echo "[trt] waiting for readiness on :$TRT_PORT (TRT-LLM builds/loads engines — can take many minutes) ..."
echo "[trt] mem cap=$MEM_LIMIT  alloc_conf=${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
# Host-side watchdog: independent of the cgroup cap, kill the container if free host memory
# drops below the floor (cgroup GPU-memory accounting on Grace unified memory is not guaranteed).
MEM_FLOOR_MIB="${MEM_FLOOR_MIB:-6144}"
READY=0
for _ in $(seq 1 480); do   # 480*5s = 40 min: engine build for a 120B can be long on first load
  if curl -sf "http://127.0.0.1:$TRT_PORT/v1/models" -H "Authorization: Bearer $TRT_API_KEY" >/dev/null 2>&1; then
    READY=1; break
  fi
  AVAIL_MIB="$(awk '/^MemAvailable:/{printf "%d",$2/1024}' /proc/meminfo)"
  if [[ "$AVAIL_MIB" -lt "$MEM_FLOOR_MIB" ]]; then
    echo "[trt] *** host memory floor breached (${AVAIL_MIB}MiB < ${MEM_FLOOR_MIB}MiB) — killing container to protect host ***" >&2
    docker kill trtllm-server >/dev/null 2>&1 || true
    docker logs trtllm-server 2>&1 | tail -40 >&2
    exit 1
  fi
  if [[ "$(docker inspect -f '{{.State.Running}}' trtllm-server 2>/dev/null)" != "true" ]]; then
    echo "[trt] container exited before becoming ready — last log lines:" >&2
    docker logs trtllm-server 2>&1 | tail -40 >&2
    exit 1
  fi
  sleep 5
done
[[ "$READY" -eq 1 ]] || { echo "[trt] NOT ready after timeout; docker logs -f trtllm-server" >&2; exit 1; }
echo "[trt] ready."

# ---- sanity gate (same script/criteria as vLLM) ----
# SKIP_SANITY=1 leaves the freshly-served executor untouched by the (non-streaming) probe. Needed
# to test the streaming client as the FIRST request on TRT-LLM nemotron, where a non-streaming
# probe can wedge the executor before the real (streaming) workload runs. See docs/findings
# 2026-07-01-nemotron-trt-mtp-wedge.md.
MODEL_META="$(python3 "$REPO_ROOT/infra/vllm/model-metadata.py" --profile "$PROFILE" 2>/dev/null || echo '{}')"
if [[ "${SKIP_SANITY:-0}" == "1" ]]; then
  echo "[trt] sanity SKIPPED (SKIP_SANITY=1)"
  SANITY_JSON='{"skipped": true}'
else
  SANITY_DIR="$(mktemp -d)"
  if python3 "$REPO_ROOT/infra/vllm/sanity-check.py" --served "$SERVED_MODEL_NAME" \
       --out "$SANITY_DIR" --base-url "http://127.0.0.1:$TRT_PORT/v1" \
       --api-key "$TRT_API_KEY" --temperature "${DECODE_TEMPERATURE:-0.2}" --seed "${SEED:-0}"; then
    echo "[trt] sanity PASS"
  else
    echo "[trt] *** SANITY CHECK FAILED for $SERVED_MODEL_NAME (see manifest) ***" >&2
  fi
  SANITY_JSON="$(cat "$SANITY_DIR/sanity-check.json" 2>/dev/null || echo '{}')"
  rm -rf "$SANITY_DIR"
fi

set +e +o pipefail
MEM_USED_MIB="$(awk '/^MemTotal:/{t=$2} /^MemAvailable:/{a=$2} END{printf "%d",(t-a)/1024}' /proc/meminfo)"
mkdir -p "$REPO_ROOT/manifests"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
MANIFEST="$REPO_ROOT/manifests/serve-trtllm-${SERVED_MODEL_NAME}-${TS}.json"
TRT_VERSION="$(docker exec trtllm-server python3 -c 'import tensorrt_llm;print(tensorrt_llm.__version__)' 2>/dev/null || echo unknown)"
DRIVER="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ')"
GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 | sed 's/^ *//')"
# JSON-encode the YAML config (it contains double quotes in comments; embedding it raw
# produced invalid JSON manifests). python emits the surrounding quotes, so the template
# below references $CONFIG_YAML_JSON without wrapping quotes.
CONFIG_YAML_JSON="$(tr '\n' ' ' < "$CONFIG_YAML" | tr -s ' ' \
  | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))' 2>/dev/null || echo '""')"

cat > "$MANIFEST" <<JSON
{
  "timestamp_utc": "$TS",
  "host": "$(hostname)",
  "runtime": "tensorrt-llm",
  "profile": "$PROFILE",
  "model_id": "$MODEL_ID",
  "served_model_name": "$SERVED_MODEL_NAME",
  "serving": {
    "image": "$TRT_IMAGE",
    "trtllm_version": "$TRT_VERSION",
    "port": $TRT_PORT,
    "max_batch_size": ${MAX_BATCH_SIZE:-4},
    "tp_size": ${TP_SIZE:-1},
    "ep_size": ${EP_SIZE:-1},
    "max_num_tokens": ${MAX_NUM_TOKENS:-8192},
    "max_seq_len": ${MAX_SEQ_LEN:-65536},
    "seed": ${SEED:-0},
    "decode_temperature": ${DECODE_TEMPERATURE:-0.2},
    "extra_args": "$(echo "$EXTRA_TRT_ARGS" | tr -s ' ')",
    "config_yaml": $CONFIG_YAML_JSON
  },
  "platform": {
    "gpu_name": "$GPU_NAME",
    "driver_version": "$DRIVER",
    "arch": "$(uname -m)"
  },
  "model_metadata": $MODEL_META,
  "sanity_check": $SANITY_JSON,
  "unified_mem_used_mib_after_load": $MEM_USED_MIB,
  "fairness_note": "Runtime is TensorRT-LLM (vs vLLM for gpt-oss/qwen baselines). Quality metrics are model-driven and comparable across runtimes; throughput/energy/latency are runtime-dependent and must be read with the qwen/gpt-oss dual-runtime bridge. seed, temperature, and the OpenCode version are held identical to the vLLM runs."
}
JSON

echo "[trt] manifest -> $MANIFEST"
echo "[trt] follow logs: docker logs -f trtllm-server"
