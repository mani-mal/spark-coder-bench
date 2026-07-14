# infra/metrics — three-source metric collection

Every benchmark task is wrapped in three time-synchronized collectors. All stamp
rows with `epoch_ms` (single host → epoch is the join key); `run-context.sh`
records the per-task window and `aggregate.py` joins everything.

| Source | Script | Output | Captures |
| --- | --- | --- | --- |
| A. Hardware | `collect-hw.sh` | `hw.csv` (+ `hw-dcgm.txt`, `hw-tegrastats.txt` if available) | GPU util, power→energy, temp, SM clock, throttle, PCIe, **unified memory** (`/proc/meminfo`) |
| B. Inference | `collect-vllm-prom.py` | `vllm-metrics.csv` (long format) | all `vllm:` Prometheus series: tokens, TTFT/e2e/ITL histograms, prefill/decode time, KV-cache %, queue, prefix-cache |
| C. Accounting | `collect-opencode.py` | `opencode-accounting.json` | OpenCode tokens, turns, tool calls, failures, wall-clock (best-effort; see note) |

Support: `clock-sync.py` (shared clock reference + skew check), `aggregate.py`
(join + derived metrics), `stop-collectors.sh` (manual stop).

## Run one task with full metrics

```bash
infra/metrics/run-context.sh <run-id> [--interval 0.25] [--metrics-url URL] -- <command...>
```

`run-context.sh` starts the collectors, marks the window, runs `<command>`
(typically a headless `opencode run ...`), stops the collectors, parses OpenCode
accounting, writes `window.json`, and runs `aggregate.py` → `run-summary.json`.

Example (one headless OpenCode task):

```bash
infra/metrics/run-context.sh qwen-l2-appcase-1 -- \
  opencode run -m vllm-local/qwen3-coder-30b "$(cat layer2_appcase/prompt.md)"
```

Output lands in `results/raw/<run-id>/`:
`hw.csv`, `vllm-metrics.csv`, `opencode-accounting.json`, `clock-sync.json`,
`window.json`, `command.log`, `gpu-static.txt`, `run-summary.json`.

## Derived metrics (`run-summary.json`)

energy per task (J & Wh) + **J/token = MJ/Mtok** (identical by definition) +
tokens/joule; energy split **prefill vs decode** (by time fraction); peak unified
memory; **TTFT p50/p90/p99**; **prefill vs decode throughput, reported
separately**; KV-cache usage; e2e & inter-token latency distributions.

> **GB10 notes.** (1) `nvidia-smi` works (driver 580.159.03, CUDA 13.0, `NVIDIA
> GB10`), but memory is unified LPDDR5x so it has no per-device VRAM to report →
> `nvidia-smi memory.*` comes back `Not Supported`/`[N/A]` **by design, not a
> failure**; the model footprint comes from `/proc/meminfo`. (2) Power is **GPU-only** via
> `nvidia-smi` unless DCGM/tegrastats are installed (then full-SoC); the level is
> declared in the serve manifest. (3) vLLM finalizes per-request completion
> histograms (e2e, prefill/decode time, success) just after the response returns,
> so `aggregate.py` applies a `--tail-grace-ms` (default 2000) to those counters
> while keeping gauges and energy strictly in-window.

## OpenCode accounting caveat

`collect-opencode.py` discovers OpenCode session JSON by mtime and heuristically
sums usage fields; it always writes output with a `confidence` flag and never
fails the run. Confirm the session schema for the installed OpenCode version once
and tighten the field map (or pass `--session-file`). vLLM Prometheus token
counts remain authoritative for inference accounting regardless.
