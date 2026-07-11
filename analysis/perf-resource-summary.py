#!/usr/bin/env python3
"""Consolidate per-run performance + resource metrics into one cross-model table.

Sources (single host, all runs):
  - results/summary/l{1,2,3}-run-ledger.csv  -> AUTHORITATIVE wall-clock + energy
    (complete: every run has a ledger row, incl. runs with no run-summary.json)
  - results/raw/<run>/run-summary.json       -> GPU / unified-memory / KV-cache /
    throughput / TTFT (subset: only runs whose collector window succeeded)

Emits results/summary/perf-resource-summary.csv and prints a Markdown table.

Design notes / caveats baked in:
  * Duration + energy come from the ledger, NOT run-summary, so failed/partial
    metric windows (e.g. gpt-oss L3, some nemotron L1) don't drop wall-clock.
  * Gauges (util/power/temp/clock/KV) are reported as the MEDIAN of per-run means;
    unified memory as the MAX per-run peak (worst-case footprint).
  * Inference throughput/TTFT/KV exist only for the vLLM models. nemotron runs on
    TensorRT-LLM, which exposes no Prometheus -> those cells are blank by design,
    not missing data. (See docs/findings 2026-07-11-cross-model-performance-*.md)
  * L3 nemotron wall-clock is an 8-way parallel window; single-stream is ~130 h.
    Do not read the L3 duration column as a controlled single-stream speed rank.
"""
import csv, glob, json, os, statistics as st
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "results", "raw")
SUM = os.path.join(ROOT, "results", "summary")
MODELS = ["gpt-oss-120b", "qwen3-coder-30b", "nemotron-super"]
LAYERS = ["l1", "l2", "l3"]


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def dget(j, *keys):
    cur = j
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


# --- authoritative wall-clock + energy from ledgers -------------------------
ledger = defaultdict(lambda: {"dur": [], "e": []})
for L in LAYERS:
    p = os.path.join(SUM, f"{L}-run-ledger.csv")
    if not os.path.exists(p):
        continue
    for r in csv.DictReader(open(p)):
        m = r.get("model")
        if m not in MODELS:
            continue
        d = r.get("duration_s")
        e = r.get("energy_j")
        if d:
            ledger[(m, L)]["dur"].append(float(d))
        if e and r.get("energy_valid", "1") not in ("0", "false", "False"):
            ledger[(m, L)]["e"].append(float(e))


# --- resource metrics from run-summary.json ---------------------------------
def model_of(name):
    for m in MODELS:
        if name.startswith(m):
            return m
    return None


res = defaultdict(list)
for path in glob.glob(os.path.join(RAW, "*", "run-summary.json")):
    d = os.path.basename(os.path.dirname(path))
    m = model_of(d)
    L = next((c for c in LAYERS if f"-{c}-" in d), None)
    if not m or not L:
        continue
    try:
        res[(m, L)].append(json.load(open(path)))
    except Exception:
        continue

COLS = [
    "layer", "model", "runs", "dur_med_min", "dur_total_h", "dur_max_min",
    "energy_med_kJ", "energy_total_MJ", "res_n",
    "gpu_util_pct", "gpu_power_W", "gpu_temp_C", "sm_clock_MHz",
    "unified_mem_peak_MiB", "kv_cache_pct", "decode_tok_s", "prefill_tok_s",
    "ttft_p50_s",
]
rows = []
for L in LAYERS:
    for m in MODELS:
        lg = ledger.get((m, L), {"dur": [], "e": []})
        js = res.get((m, L), [])
        if not lg["dur"] and not js:
            continue
        dur, en = lg["dur"], lg["e"]
        util = [dget(j, "hardware", "gpu_util_pct", "mean") for j in js]
        powr = [dget(j, "hardware", "gpu_power_w", "mean") for j in js]
        temp = [dget(j, "hardware", "gpu_temp_c", "mean") for j in js]
        smcl = [dget(j, "hardware", "sm_clock_mhz", "mean") for j in js]
        mem = [dget(j, "hardware", "unified_mem_peak_mib") for j in js]
        kv = [dget(j, "inference", "kv_cache_usage_perc", "mean") for j in js]
        dec = [dget(j, "inference", "decode_throughput_tok_s") for j in js]
        pre = [dget(j, "inference", "prefill_throughput_tok_s") for j in js]
        ttft = [dget(j, "inference", "ttft_seconds", "p50") for j in js]
        memvals = [x for x in mem if x is not None]
        kvvals = [x * 100 for x in kv if x is not None]

        def r1(x, p=1):
            return "" if x is None else round(x, p)

        rows.append({
            "layer": L.upper(), "model": m,
            "runs": len(dur),
            "dur_med_min": r1(med(dur) / 60 if dur else None),
            "dur_total_h": r1(sum(dur) / 3600 if dur else None, 2),
            "dur_max_min": r1(max(dur) / 60 if dur else None),
            "energy_med_kJ": r1(med(en) / 1000 if en else None),
            "energy_total_MJ": r1(sum(en) / 1e6 if en else None, 3),
            "res_n": len(js),
            "gpu_util_pct": r1(med(util)),
            "gpu_power_W": r1(med(powr)),
            "gpu_temp_C": r1(med(temp), 0),
            "sm_clock_MHz": r1(med(smcl), 0),
            "unified_mem_peak_MiB": r1(max(memvals), 0) if memvals else "",
            "kv_cache_pct": r1(med(kvvals), 2) if kvvals else "",
            "decode_tok_s": r1(med(dec)),
            "prefill_tok_s": r1(med(pre), 0),
            "ttft_p50_s": r1(med(ttft), 3),
        })

out = os.path.join(SUM, "perf-resource-summary.csv")
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=COLS)
    w.writeheader()
    w.writerows(rows)

print(f"wrote {out} ({len(rows)} rows)\n")
widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in COLS}
print(" | ".join(c.ljust(widths[c]) for c in COLS))
print("-|-".join("-" * widths[c] for c in COLS))
for r in rows:
    print(" | ".join(str(r[c]).ljust(widths[c]) for c in COLS))
