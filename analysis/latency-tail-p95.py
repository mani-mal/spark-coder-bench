#!/usr/bin/env python3
"""p95 tail latency (TTFT + end-to-end) per model x layer — from raw histograms.

The taxonomy's minimum latency checklist asks p50/**p95**; our run-summary.json
carried p50/p90/p99 but not p95. No re-run needed: the raw vLLM latency histograms
(`vllm:time_to_first_token_seconds_bucket`, `vllm:e2e_request_latency_seconds_bucket`)
are saved in every run's vllm-metrics.csv. This recomputes the full p50/p90/p95/p99
by reusing aggregate.py's CANONICAL hist_quantiles (identical method to the existing
percentiles), so p95 is consistent with the numbers already published.

Emits results/summary/latency-tail-p95.csv (per-run) + prints a per-model x layer
median-of-p95 table. vLLM models only (TRT/nemotron exposes no Prometheus histograms).
"""
import csv, glob, json, os, sys, statistics as st
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "infra", "metrics"))
import aggregate  # load_vllm, hist_quantiles — canonical window/interpolation logic

RAW = os.path.join(ROOT, "results", "raw")
SUM = os.path.join(ROOT, "results", "summary")
MODELS = ["gpt-oss-120b", "qwen3-coder-30b", "nemotron-super"]
LAYERS = ["l1", "l2", "l3"]
TAIL_GRACE_MS = 2000  # aggregate.py default: completion metrics may finalize just after window


def model_of(name):
    return next((m for m in MODELS if name.startswith(m)), None)


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(st.median(xs), 4) if xs else None


rows = []
for path in sorted(glob.glob(os.path.join(RAW, "*", "window.json"))):
    run_dir = os.path.dirname(path)
    name = os.path.basename(run_dir)
    m = model_of(name)
    L = next((c for c in LAYERS if f"-{c}-" in name), None)
    if not m or not L:
        continue
    if not os.path.exists(os.path.join(run_dir, "vllm-metrics.csv")):
        continue
    try:
        win = json.load(open(path))
        start = win["window_start_epoch_ms"]
        end = win["window_end_epoch_ms"]
        _, buckets = aggregate.load_vllm(Path(run_dir))
    except Exception:
        continue
    ttft = aggregate.hist_quantiles(buckets, "vllm:time_to_first_token_seconds", start, end + TAIL_GRACE_MS)
    e2e = aggregate.hist_quantiles(buckets, "vllm:e2e_request_latency_seconds", start, end + TAIL_GRACE_MS)
    if not ttft and not e2e:
        continue
    rows.append({
        "run_id": name, "model": m, "layer": L.upper(),
        "ttft_p50": (ttft or {}).get("p50"), "ttft_p90": (ttft or {}).get("p90"),
        "ttft_p95": (ttft or {}).get("p95"), "ttft_p99": (ttft or {}).get("p99"),
        "e2e_p50": (e2e or {}).get("p50"), "e2e_p90": (e2e or {}).get("p90"),
        "e2e_p95": (e2e or {}).get("p95"), "e2e_p99": (e2e or {}).get("p99"),
        "n_requests": (e2e or ttft or {}).get("count"),
    })

if not rows:
    # public checkout omits the heavy raw vllm-metrics.csv streams; don't clobber the
    # ported result CSV with an empty one.
    print("No vLLM latency histograms found (raw streams absent in this checkout); "
          "leaving results/summary/latency-tail-p95.csv untouched.")
    sys.exit(0)

os.makedirs(SUM, exist_ok=True)
out = os.path.join(SUM, "latency-tail-p95.csv")
cols = ["run_id", "model", "layer", "ttft_p50", "ttft_p90", "ttft_p95", "ttft_p99",
        "e2e_p50", "e2e_p90", "e2e_p95", "e2e_p99", "n_requests"]
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)
print(f"wrote {out} ({len(rows)} runs)\n")

# per model x layer: median of per-run p95 (and p50 for context)
print(f"{'layer':5} {'model':16} {'runs':4} {'ttft_p50':8} {'ttft_p95':8} {'e2e_p50':8} {'e2e_p95':8}")
print("-" * 62)
for L in LAYERS:
    for m in MODELS:
        g = [r for r in rows if r["model"] == m and r["layer"] == L.upper()]
        if not g:
            continue
        def col(k):
            v = med([r[k] for r in g])
            return "—" if v is None else f"{v:.3f}"
        print(f"{L.upper():5} {m:16} {len(g):<4} {col('ttft_p50'):8} {col('ttft_p95'):8} {col('e2e_p50'):8} {col('e2e_p95'):8}")
