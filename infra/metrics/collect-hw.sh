#!/usr/bin/env bash
# collect-hw.sh — hardware telemetry collector (source A of 3).
#
# Writes timestamped (epoch_ms) rows so it can be joined with the vLLM inference
# series and OpenCode accounting later. Designed to be launched/stopped by
# run-context.sh, but also runs standalone.
#
# Primary stream (always): nvidia-smi + /proc/meminfo merged into hw.csv.
# DGX Spark (GB10) uses UNIFIED memory => nvidia-smi memory.* is [N/A]; the real
# model footprint comes from /proc/meminfo (host_mem_used_kib).
# Supplementary streams (only if the tool exists), each to its own file:
#   - DCGM      : dcgmi dmon            -> hw-dcgm.txt   (SM activity %, mem-bw %, power)
#   - tegrastats: tegrastats            -> hw-tegrastats.txt (full-SoC power rails)
#
# Usage: collect-hw.sh <out_dir> [interval_seconds=0.25]
set -uo pipefail

OUT_DIR="${1:-}"
INTERVAL="${2:-0.25}"
if [[ -z "$OUT_DIR" ]]; then
  echo "Usage: $0 <out_dir> [interval_seconds]" >&2
  exit 1
fi
mkdir -p "$OUT_DIR"

CSV="$OUT_DIR/hw.csv"
PIDFILE="$OUT_DIR/hw.pid"
DCGM_OUT="$OUT_DIR/hw-dcgm.txt"
TEGRA_OUT="$OUT_DIR/hw-tegrastats.txt"
STATIC="$OUT_DIR/gpu-static.txt"
echo "$$" > "$PIDFILE"

GPU_FIELDS="utilization.gpu,utilization.memory,memory.used,temperature.gpu,power.draw,power.draw.instant,power.draw.average,pstate,clocks.sm,clocks.gr,clocks_throttle_reasons.active,pcie.link.gen.current,pcie.link.width.current"

echo "iso_time,epoch_ms,gpu_util_pct,mem_util_pct,gpu_mem_used_mib,gpu_temp_c,power_draw_w,power_inst_w,power_avg_w,pstate,sm_clock_mhz,gr_clock_mhz,throttle_active_hex,pcie_gen,pcie_width,host_mem_total_kib,host_mem_used_kib,host_mem_avail_kib,cpu_load1" > "$CSV"

# one-time static snapshot
nvidia-smi -q > "$STATIC" 2>&1 || true

# --- supplementary collectors (background, best-effort) ---
DCGM_PID=""; TEGRA_PID=""
INTERVAL_MS="$(awk -v i="$INTERVAL" 'BEGIN{printf "%d", i*1000}')"
if command -v dcgmi >/dev/null 2>&1; then
  # SM activity, mem-copy util, power usage, gpu temp, sm clock; -d in ms
  dcgmi dmon -e 1002,1003,155,150,100 -d "$INTERVAL_MS" > "$DCGM_OUT" 2>&1 &
  DCGM_PID=$!
  echo "[collect-hw] DCGM dmon started (pid $DCGM_PID)" >&2
fi
if command -v tegrastats >/dev/null 2>&1; then
  tegrastats --interval "$INTERVAL_MS" > "$TEGRA_OUT" 2>&1 &
  TEGRA_PID=$!
  echo "[collect-hw] tegrastats started (pid $TEGRA_PID)" >&2
fi

cleanup() {
  [[ -n "$DCGM_PID" ]] && kill "$DCGM_PID" 2>/dev/null || true
  [[ -n "$TEGRA_PID" ]] && kill "$TEGRA_PID" 2>/dev/null || true
  rm -f "$PIDFILE"
  exit 0
}
trap cleanup INT TERM

# --- primary loop ---
while true; do
  iso="$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
  ms="$(date +%s%3N)"
  gpu="$(nvidia-smi --query-gpu="$GPU_FIELDS" --format=csv,noheader,nounits 2>/dev/null | head -1)"
  gpu="${gpu//, /,}"
  # M14: a transient nvidia-smi failure or partial line would otherwise left-shift every later
  # column (the power column would receive the CPU load average, feeding bogus ~1 W samples into
  # the energy integral). GPU_FIELDS has 13 fields; if we don't get exactly 13, emit blanks so the
  # 19-column layout stays aligned and the sample is dropped downstream instead of silently misread.
  if [[ -z "$gpu" || "$(awk -F, '{print NF}' <<<"$gpu")" -ne 13 ]]; then
    gpu=",,,,,,,,,,,,"
  fi
  read -r mt mu ma <<<"$(awk '/^MemTotal:/{t=$2} /^MemAvailable:/{a=$2} END{printf "%s %s %s", t, t-a, a}' /proc/meminfo)"
  load1="$(awk '{print $1}' /proc/loadavg)"
  echo "${iso},${ms},${gpu},${mt},${mu},${ma},${load1}" >> "$CSV"
  sleep "$INTERVAL"
done
