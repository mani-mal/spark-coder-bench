#!/usr/bin/env python3
"""aggregate.py — join the 3 metric sources for one task window and derive the
published metrics. Stdlib only.

Reads results/raw/<run-id>/:
  - window.json            (task window start/end epoch_ms)
  - hw.csv                 (hardware time series)            [source A]
  - vllm-metrics.csv       (vLLM Prometheus long-format)     [source B]
  - opencode-accounting.json (agent accounting)             [source C]
  - clock-sync.json        (clock reference)
Writes results/raw/<run-id>/run-summary.json and prints it.

Derived metrics: energy per task (J & Wh) + J/token + MJ/Mtok, energy split
prefill/decode, peak unified memory, TTFT p50/p90/p99, prefill vs decode
throughput (separate), KV-cache usage, tokens-per-joule.

Usage: aggregate.py <run-id> [--results-root DIR]
"""
import argparse
import bisect
import csv
import json
import math
from collections import defaultdict
from pathlib import Path


def to_float(x):
    if x is None:
        return None
    x = str(x).strip()
    if x == "" or x.upper().startswith("[N/A") or x.upper() == "N/A":
        return None
    try:
        return float(x)
    except ValueError:
        return None


# ---------- hardware (source A) ----------
def load_hw(run_dir):
    p = run_dir / "hw.csv"
    if not p.exists():
        return []
    with p.open() as f:
        return list(csv.DictReader(f))


def hw_window(rows, start, end):
    return [r for r in rows
            if (ms := to_float(r.get("epoch_ms"))) is not None and start <= ms <= end]


def stats(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return {"mean": round(sum(vals) / len(vals), 3),
            "min": round(min(vals), 3), "max": round(max(vals), 3), "n": len(vals)}


def trapz_energy_j(rows):
    pts = []
    for r in rows:
        t = to_float(r.get("epoch_ms"))
        p = to_float(r.get("power_draw_w"))
        if t is not None and p is not None:
            pts.append((t / 1000.0, p))  # seconds
    if len(pts) < 2:
        return None
    j = 0.0
    for (t0, p0), (t1, p1) in zip(pts, pts[1:]):
        dt = t1 - t0
        if dt > 0:
            j += 0.5 * (p0 + p1) * dt
    return j


# ---------- vLLM (source B) ----------
def load_vllm(run_dir):
    """Return (scalars, buckets):
       scalars[name] = sorted list of (ms, value_summed_across_labels)
       buckets[name][le] = sorted list of (ms, value_summed_across_labels)
    """
    p = run_dir / "vllm-metrics.csv"
    scal_tmp = defaultdict(lambda: defaultdict(float))     # name -> ms -> val
    buck_tmp = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))  # name -> le -> ms -> val
    if not p.exists():
        return {}, {}
    with p.open() as f:
        for row in csv.DictReader(f):
            ms = to_float(row["epoch_ms"])
            val = to_float(row["value"])
            if ms is None or val is None:
                continue
            name, le = row["metric"], row["le"]
            if name.endswith("_bucket"):
                base = name[: -len("_bucket")]
                buck_tmp[base][le][ms] += val
            else:
                scal_tmp[name][ms] += val
    scalars = {n: sorted(d.items()) for n, d in scal_tmp.items()}
    buckets = {n: {le: sorted(d.items()) for le, d in les.items()} for n, les in buck_tmp.items()}
    return scalars, buckets


def value_at(series, t):
    """Last value at or before time t (cumulative counter convention)."""
    if not series:
        return None
    ms = [s[0] for s in series]
    i = bisect.bisect_right(ms, t) - 1
    if i < 0:
        return None
    return series[i][1]


def counter_delta(scalars, name, start, end):
    s = scalars.get(name)
    if not s:
        return None
    v0 = value_at(s, start)
    v1 = value_at(s, end)
    if v0 is None:
        v0 = s[0][1]
    if v1 is None:
        return None
    return max(0.0, v1 - v0)


def gauge_stats(scalars, name, start, end):
    s = scalars.get(name)
    if not s:
        return None
    return stats([v for (ms, v) in s if start <= ms <= end])


def hist_quantiles(buckets, name, start, end, qs=(0.5, 0.9, 0.95, 0.99)):
    les = buckets.get(name)
    if not les:
        return None
    # delta per bucket over the window -> events that completed in-window
    deltas = []
    for le, series in les.items():
        v0 = value_at(series, start)
        v1 = value_at(series, end)
        if v0 is None:
            v0 = series[0][1] if series else 0.0
        if v1 is None:
            continue
        bound = math.inf if le in ("+Inf", "inf", "Inf") else float(le)
        deltas.append((bound, max(0.0, v1 - v0)))
    if not deltas:
        return None
    deltas.sort(key=lambda x: x[0])
    total = deltas[-1][1]  # cumulative count at +Inf
    if total <= 0:
        return None
    out = {}
    for q in qs:
        target = q * total
        prev_bound, prev_cum = 0.0, 0.0
        chosen = None
        for bound, cum in deltas:
            if cum >= target:
                if bound == math.inf:
                    chosen = prev_bound
                elif cum > prev_cum:
                    frac = (target - prev_cum) / (cum - prev_cum)
                    chosen = prev_bound + frac * (bound - prev_bound)
                else:
                    chosen = bound
                break
            prev_bound, prev_cum = bound, cum
        out[f"p{int(q*100)}"] = round(chosen, 4) if chosen is not None else None
    out["count"] = int(total)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--results-root")
    ap.add_argument("--tail-grace-ms", type=int, default=2000,
                    help="grace appended to the window for per-request COMPLETION metrics "
                         "(vLLM finalizes them just after the response returns); resource "
                         "gauges and energy stay strictly in-window")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    results_root = Path(args.results_root) if args.results_root else repo_root / "results" / "raw"
    run_dir = results_root / args.run_id

    win = json.loads((run_dir / "window.json").read_text())
    start, end = win["window_start_epoch_ms"], win["window_end_epoch_ms"]
    end_infer = end + args.tail_grace_ms  # for completion counters/histograms only
    duration_s = (end - start) / 1000.0

    # --- hardware ---
    hw = hw_window(load_hw(run_dir), start, end)
    energy_j = trapz_energy_j(hw)
    mem_used_mib = [to_float(r.get("host_mem_used_kib")) for r in hw]
    mem_used_mib = [v / 1024.0 for v in mem_used_mib if v is not None]
    hardware = {
        "gpu_util_pct": stats([to_float(r.get("gpu_util_pct")) for r in hw]),
        "gpu_power_w": stats([to_float(r.get("power_draw_w")) for r in hw]),
        "gpu_temp_c": stats([to_float(r.get("gpu_temp_c")) for r in hw]),
        "sm_clock_mhz": stats([to_float(r.get("sm_clock_mhz")) for r in hw]),
        # memory-controller utilization % = bandwidth-pressure PROXY (nvidia-smi; true
        # GB/s needs DCGM). Central to the dense-vs-sparse / sparsity-ratio analysis.
        "mem_controller_util_pct": stats([to_float(r.get("mem_util_pct")) for r in hw]),
        "bandwidth_source": "nvidia-smi utilization.memory (proxy; DCGM not installed)",
        "unified_mem_used_mib": stats(mem_used_mib),
        "unified_mem_peak_mib": round(max(mem_used_mib), 1) if mem_used_mib else None,
        "samples": len(hw),
    }

    # --- inference ---
    scalars, buckets = load_vllm(run_dir)
    prompt_tok = counter_delta(scalars, "vllm:prompt_tokens_total", start, end_infer)
    gen_tok = counter_delta(scalars, "vllm:generation_tokens_total", start, end_infer)
    prefill_t = counter_delta(scalars, "vllm:request_prefill_time_seconds_sum", start, end_infer)
    decode_t = counter_delta(scalars, "vllm:request_decode_time_seconds_sum", start, end_infer)
    pref_hits = counter_delta(scalars, "vllm:prefix_cache_hits_total", start, end_infer)
    pref_q = counter_delta(scalars, "vllm:prefix_cache_queries_total", start, end_infer)

    def div(a, b):
        return round(a / b, 2) if (a is not None and b not in (None, 0)) else None

    inference = {
        "prompt_tokens": prompt_tok,
        "generation_tokens": gen_tok,
        "total_tokens": (prompt_tok or 0) + (gen_tok or 0) if (prompt_tok or gen_tok) else None,
        "prefill_throughput_tok_s": div(prompt_tok, prefill_t),
        "decode_throughput_tok_s": div(gen_tok, decode_t),
        "prefill_time_s": round(prefill_t, 3) if prefill_t is not None else None,
        "decode_time_s": round(decode_t, 3) if decode_t is not None else None,
        "ttft_seconds": hist_quantiles(buckets, "vllm:time_to_first_token_seconds", start, end_infer),
        "e2e_latency_seconds": hist_quantiles(buckets, "vllm:e2e_request_latency_seconds", start, end_infer),
        "inter_token_latency_seconds": hist_quantiles(buckets, "vllm:inter_token_latency_seconds", start, end_infer),
        "kv_cache_usage_perc": gauge_stats(scalars, "vllm:kv_cache_usage_perc", start, end),
        "num_requests_running": gauge_stats(scalars, "vllm:num_requests_running", start, end),
        "num_requests_waiting": gauge_stats(scalars, "vllm:num_requests_waiting", start, end),
        "prefix_cache_hit_rate": div(pref_hits, pref_q),
        "requests_succeeded": counter_delta(scalars, "vllm:request_success_total", start, end_infer),
    }

    # --- energy (derived) ---
    total_tok = inference["total_tokens"]
    energy = {"power_level": "GPU-only (nvidia-smi power.draw); declare DCGM/tegrastats in manifest if used"}
    if energy_j is not None:
        energy["energy_j"] = round(energy_j, 2)
        energy["energy_wh"] = round(energy_j / 3600.0, 4)
        if total_tok:
            energy["j_per_token"] = round(energy_j / total_tok, 4)
            energy["mj_per_mtok"] = round(energy_j / total_tok, 4)  # identical to J/token by definition
            energy["tokens_per_joule"] = round(total_tok / energy_j, 3)
        # phase split by time fraction (approximate under concurrency)
        if prefill_t is not None and decode_t is not None and (prefill_t + decode_t) > 0:
            frac_p = prefill_t / (prefill_t + decode_t)
            energy["energy_prefill_j"] = round(energy_j * frac_p, 2)
            energy["energy_decode_j"] = round(energy_j * (1 - frac_p), 2)
            energy["phase_split_note"] = "energy attributed by prefill/decode time fraction; approximate when requests overlap"

    # --- accounting (source C) ---
    acct_path = run_dir / "opencode-accounting.json"
    accounting = json.loads(acct_path.read_text()) if acct_path.exists() else None

    # model metadata (parse profile from run-id, look up registry)
    model_block = None
    profile = None
    for sep in ("-l1-", "-l2-"):
        if sep in args.run_id:
            profile = args.run_id.split(sep, 1)[0]
            break
    if profile:
        try:
            reg = json.loads((repo_root / "infra" / "models.json").read_text())
            mm = next((m for m in reg["models"] if m["profile"] == profile), None)
            if mm:
                model_block = {k: mm.get(k) for k in
                               ("profile", "arch", "total_params_b", "active_params_b",
                                "num_experts", "experts_per_token", "quant", "license")}
                if mm.get("total_params_b") and mm.get("active_params_b"):
                    model_block["sparsity_active_fraction"] = round(
                        mm["active_params_b"] / mm["total_params_b"], 4)
        except Exception:
            pass

    clock = run_dir / "clock-sync.json"
    summary = {
        "run_id": args.run_id,
        "model": model_block,
        "duration_seconds": round(duration_s, 3),
        "exit_code": win.get("exit_code"),
        "clock_offset_spread_ms": json.loads(clock.read_text()).get("offset_spread_ms") if clock.exists() else None,
        "hardware": hardware,
        "inference": inference,
        "energy": energy,
        "accounting": accounting,
    }

    out = run_dir / "run-summary.json"
    out.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
