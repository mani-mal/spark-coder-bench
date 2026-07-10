#!/usr/bin/env python3
"""aggregate-runs.py — combine per-run artifacts into tidy, publishable tables.

Scans results/raw/<run-id>/ for run-summary.json (+ rubric-score.json for Layer 2,
resolved.json for Layer 1) and writes:
  results/summary/benchmark-long.csv     one row per run, all metrics (tidy long format)
  results/summary/benchmark-summary.csv  mean±std per (model, layer, track) group

run-id convention: "<model>-l2-<track>-<repeat>" or "<model>-l1-<task>-<repeat>".
Stdlib only.

Usage: aggregate-runs.py [--results-root results/raw] [--out results/summary]
"""
import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

LONG_COLS = [
    "run_id", "model", "runtime", "layer", "track_or_task", "repeat",
    "resolved", "rubric_pass_rate", "rubric_pass_rate_25",
    "lcb_pass_at_1", "lcb_ci_lo", "lcb_ci_hi", "lcb_n",
    "arch", "total_params_b", "active_params_b", "sparsity_active_fraction", "quant",
    "duration_s", "energy_j", "energy_wh", "j_per_token", "j_per_gen_token",
    "tokens_per_joule", "energy_valid",
    "prefill_tok_s", "decode_tok_s",
    "ttft_p50", "ttft_p90", "ttft_p99", "e2e_p50",
    "gpu_util_mean", "gpu_power_mean", "mem_util_mean", "unified_mem_peak_mib",
    "prompt_tokens", "generation_tokens", "total_tokens", "exit_code",
]
NUMERIC = [c for c in LONG_COLS if c not in
           ("run_id", "model", "runtime", "layer", "track_or_task", "repeat",
            "arch", "quant", "energy_valid")]

# M9: the nemotron L3 run-id is keyed "nemotron-super" while its L1/L2 run-ids carry the
# "-trt" runtime tag, splitting one model into two across every per-model grouping. Unify to
# the served-model name; nemotron is TRT-only so no information is lost (runtime is captured
# in its own column below).
CANON_MODEL = {"nemotron-super-trt": "nemotron-super"}
# C1: these four L2 checks depend on unguessable api-contract.md specifics (exact routes / JSON
# keys). That contract was never present in the frozen app workspace (baseline-v4, which added
# it, is not an ancestor of baseline-v6), so the checks are structurally unreachable and scored
# 0 across all 61 runs of every model. We keep the canonical k/29 rate AND publish a k/25 rate
# over the reachable checks, computed here from the stored per-check results (raw untouched).
UNREACHABLE_L2_CHECKS = {
    "dashboard_summary_keys", "project_archive", "project_edit", "task_update_status",
}

# Nemotron ran only on TensorRT-LLM; the two coder baselines only on vLLM (see the
# serving-feasibility matrix / manifests). Runtime is kept explicit so efficiency figures can
# avoid pooling incomparable runtimes (M11/M17).
RUNTIME_BY_MODEL = {"nemotron-super": "tensorrt-llm"}

# Energy-capture sanity floors (C4/M7): a watchdog restart can overwrite window.json so the
# efficiency window covers only the final segment while the score covers all generations,
# yielding physically-impossible energies (~1 J/problem). Real decode on this box is ~1 J per
# GENERATED token and ~2000-2900 J per L3 problem; these floors sit 2-3 orders below that and
# well below the smallest valid observation, so they reject only broken captures.
J_PER_GEN_TOKEN_FLOOR = 0.01
J_PER_PROBLEM_FLOOR = 100.0
# Metrics derived from the (corrupted) capture window; blanked when the window is rejected.
WINDOW_COLS = ["duration_s", "energy_j", "energy_wh", "j_per_token", "j_per_gen_token",
               "tokens_per_joule", "prefill_tok_s", "decode_tok_s",
               "ttft_p50", "ttft_p90", "ttft_p99", "e2e_p50",
               "gpu_util_mean", "gpu_power_mean", "mem_util_mean", "unified_mem_peak_mib"]


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse_run_id(run_id):
    for layer in ("l1", "l2", "l3"):
        sep = f"-{layer}-"
        if sep in run_id:
            model, rest = run_id.split(sep, 1)
            tail, repeat = rest.rsplit("-", 1)
            return CANON_MODEL.get(model, model), layer, tail, repeat
    return None


def g(d, *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur or cur[p] is None:
            return default
        cur = cur[p]
    return cur


def build_row(run_dir, run_id, model, layer, tail, repeat):
    # run-summary.json carries the metrics (energy/throughput/hw). It can be absent when the
    # metrics wrapper was killed mid-run (e.g. the 30-min stuck-agent guard) or a transient
    # network drop — but resolved.json/rubric-score.json (the GROUND-TRUTH outcome) may still
    # exist. Those runs MUST still count toward the L1 resolved-rate / L2 pass-rate denominator,
    # else excluding all-zero guard-killed tasks silently inflates the score. Tolerate a missing
    # summary: keep the outcome, leave metrics blank.
    sf = run_dir / "run-summary.json"
    s = json.loads(sf.read_text()) if sf.exists() else {}
    inf, hw, en = s.get("inference", {}), s.get("hardware", {}), s.get("energy", {})
    mdl = s.get("model") or {}
    row = {c: "" for c in LONG_COLS}
    row.update({
        "run_id": run_id, "model": model,
        "runtime": RUNTIME_BY_MODEL.get(model, "vllm"),
        "layer": layer,
        "track_or_task": tail, "repeat": repeat,
        "arch": mdl.get("arch", ""),
        "total_params_b": mdl.get("total_params_b", ""),
        "active_params_b": mdl.get("active_params_b", ""),
        "sparsity_active_fraction": mdl.get("sparsity_active_fraction", ""),
        "quant": mdl.get("quant", ""),
        # nvidia-smi memory-controller util reads N/A on GB10 unified memory (documented); the
        # collector records 0.0, which is not a measurement. Leave blank so it is never
        # published as if measured.
        "mem_util_mean": "",
        "duration_s": s.get("duration_seconds", ""),
        "exit_code": s.get("exit_code", ""),
        "energy_j": g(en, "energy_j", default=""),
        "energy_wh": g(en, "energy_wh", default=""),
        "j_per_token": g(en, "j_per_token", default=""),
        "tokens_per_joule": g(en, "tokens_per_joule", default=""),
        "prefill_tok_s": inf.get("prefill_throughput_tok_s", ""),
        "decode_tok_s": inf.get("decode_throughput_tok_s", ""),
        "ttft_p50": g(inf, "ttft_seconds", "p50", default=""),
        "ttft_p90": g(inf, "ttft_seconds", "p90", default=""),
        "ttft_p99": g(inf, "ttft_seconds", "p99", default=""),
        "e2e_p50": g(inf, "e2e_latency_seconds", "p50", default=""),
        "gpu_util_mean": g(hw, "gpu_util_pct", "mean", default=""),
        "gpu_power_mean": g(hw, "gpu_power_w", "mean", default=""),
        "unified_mem_peak_mib": hw.get("unified_mem_peak_mib", ""),
        "prompt_tokens": inf.get("prompt_tokens", ""),
        "generation_tokens": inf.get("generation_tokens", ""),
        "total_tokens": inf.get("total_tokens", ""),
    })
    rub = run_dir / "rubric-score.json"
    if rub.exists():
        rd = json.loads(rub.read_text())
        row["rubric_pass_rate"] = rd.get("pass_rate", "")
        # k/25: pass rate over the reachable checks only (C1). The unreachable checks never
        # pass, so when the per-check list is absent (error runs) the passed count is already
        # all-reachable and we divide by 25 directly.
        checks = rd.get("checks")
        if checks:
            reachable = [c for c in checks if c.get("name") not in UNREACHABLE_L2_CHECKS]
            if reachable:
                passed_25 = sum(1 for c in reachable if c.get("passed"))
                row["rubric_pass_rate_25"] = round(passed_25 / len(reachable), 4)
        elif rd.get("total"):
            row["rubric_pass_rate_25"] = round((rd.get("passed", 0) or 0) / 25, 4)
    res = run_dir / "resolved.json"
    if res.exists():
        row["resolved"] = json.loads(res.read_text()).get("resolved", "")
    # Layer 3 (LiveCodeBench): pass@1 + Wilson CI from lcb-score.json
    lcb = run_dir / "lcb-score.json"
    if lcb.exists():
        sc = json.loads(lcb.read_text())
        row["lcb_pass_at_1"] = sc.get("pass_at_1", "")
        ci = sc.get("wilson_ci_95") or ["", ""]
        row["lcb_ci_lo"], row["lcb_ci_hi"] = ci[0], ci[1]
        row["lcb_n"] = sc.get("n", "")

    # Report J/generated-token alongside the (prompt-dominated) J/total-token so decode energy
    # is legible (M13). Generated tokens are ~1-2% of total under the agent loop's re-sent
    # context, so tokens_per_joule/j_per_token are dominated by re-submitted prompt tokens.
    e_j, gen = _f(row["energy_j"]), _f(row["generation_tokens"])
    if e_j is not None and gen and gen > 0:
        row["j_per_gen_token"] = round(e_j / gen, 6)

    # Energy-capture sanity (C4/M7): reject physically-impossible energies from a restart-
    # truncated window. Judge per generated token when available, else per L3 problem (TRT
    # runs expose no token counts but do capture hardware energy over the full run).
    if e_j is not None:
        valid = True
        if gen and gen > 0:
            valid = (e_j / gen) >= J_PER_GEN_TOKEN_FLOOR
        else:
            n = _f(row["lcb_n"])
            if n and n > 0:
                valid = (e_j / n) >= J_PER_PROBLEM_FLOOR
        if not valid:
            print(f"[aggregate] REJECT energy for {run_id}: energy_j={e_j} implies a "
                  f"broken capture window (see M7); blanking window-derived metrics.")
            for c in WINDOW_COLS:
                row[c] = ""
            row["energy_valid"] = 0
        else:
            row["energy_valid"] = 1
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-root", default="results/raw")
    ap.add_argument("--out", default="results/summary")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    root = (repo_root / args.results_root) if not Path(args.results_root).is_absolute() else Path(args.results_root)
    out = (repo_root / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for run_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        # Include a run if it has EITHER metrics (run-summary.json) OR a ground-truth outcome
        # (resolved.json / rubric-score.json). Outcome-only runs (guard-killed, no metrics) must
        # still count so the resolved-rate denominator stays honest.
        if not any((run_dir / f).exists() for f in
                   ("run-summary.json", "resolved.json", "rubric-score.json", "lcb-score.json")):
            continue
        parsed = parse_run_id(run_dir.name)
        if not parsed:
            continue
        try:
            rows.append(build_row(run_dir, run_dir.name, *parsed))
        except Exception as e:
            print(f"[aggregate] skip {run_dir.name}: {e}")

    long_path = out / "benchmark-long.csv"
    with long_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LONG_COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"[aggregate] wrote {long_path} ({len(rows)} runs)")

    # summary: mean±std per (model, layer, track_or_task collapsed)
    groups = defaultdict(list)
    for r in rows:
        key = (r["model"], r["layer"], r["track_or_task"] if r["layer"] == "l2" else "all")
        groups[key].append(r)

    sum_path = out / "benchmark-summary.csv"
    with sum_path.open("w", newline="") as f:
        cols = ["model", "layer", "group", "n"] + [f"{c}_mean" for c in NUMERIC] + [f"{c}_std" for c in NUMERIC]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for (model, layer, grp), recs in sorted(groups.items()):
            out_row = {"model": model, "layer": layer, "group": grp, "n": len(recs)}
            for c in NUMERIC:
                vals = []
                for r in recs:
                    try:
                        vals.append(float(r[c]))
                    except (ValueError, TypeError):
                        pass
                out_row[f"{c}_mean"] = round(statistics.mean(vals), 4) if vals else ""
                out_row[f"{c}_std"] = round(statistics.pstdev(vals), 4) if len(vals) > 1 else (0.0 if vals else "")
            w.writerow(out_row)
            print(f"  {model}/{layer}/{grp}: n={len(recs)}")
    print(f"[aggregate] wrote {sum_path}")


if __name__ == "__main__":
    main()
