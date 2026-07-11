#!/usr/bin/env python3
"""figures_perf.py — performance/resource figures for the report (2026-07-11 additions).

Built from the consolidated summary CSVs (already computed; see their scripts):
  results/summary/perf-resource-summary.csv        (analysis/perf-resource-summary.py)
  results/summary/quality-adjusted-efficiency.csv  (analysis/quality-adjusted-efficiency.py)
  results/summary/regression-rate.csv              (analysis/regression-rate.py)
  results/summary/latency-tail-p95.csv             (analysis/latency-tail-p95.py)

Figures:
  fig_walltime_by_layer   median wall-clock per task, model x layer (telemetry-SYMMETRIC:
                          all 3 models have wall-clock; nemotron's L1 mean is runaway-skewed
                          so MEDIAN is plotted, noted in caption)
  fig_energy_per_success  energy per SUCCESSFUL task (kJ), model x {L1,L2} — the ~11x gap
  fig_regression_rate     resolve-rate vs regression-rate (of applied L1 patches) per model
  fig_latency_tail        TTFT p50 vs p95, model x layer (vLLM only — TRT exposes no histograms)

Same house style as figures.py: each figure ALWAYS writes its data CSV; the PNG renders
only if matplotlib is importable. Blank (not "nan") where a metric is structurally absent
(nemotron throughput/latency on TRT; gpt-oss L3 metric-window failure).

Usage: figures_perf.py [--summary results/summary] [--out reports/charts]
"""
import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAVE_MPL = True
except Exception:
    HAVE_MPL = False

MODELS = ["gpt-oss-120b", "qwen3-coder-30b", "nemotron-super"]
SHORT = {"gpt-oss-120b": "gpt-oss", "qwen3-coder-30b": "qwen", "nemotron-super": "nemotron"}


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load(path):
    return list(csv.DictReader(open(path))) if path.exists() else []


def write_csv(out, name, header, rows):
    with (out / f"{name}.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def grouped_bar(out, name, groups, series, ylabel, title, note=None, blank_val=0):
    """groups = x-axis category labels; series = {legend_name: [values aligned to groups]}."""
    if not HAVE_MPL:
        return
    x = range(len(groups))
    width = 0.8 / max(1, len(series))
    fig, ax = plt.subplots(figsize=(8.5, 5))
    for i, (sname, vals) in enumerate(series.items()):
        plot_vals = [v if v is not None else blank_val for v in vals]
        bars = ax.bar([xi + i * width for xi in x], plot_vals, width, label=sname)
        for b, v in zip(bars, vals):
            if v is None:
                ax.text(b.get_x() + b.get_width() / 2, blank_val, "n/a", ha="center",
                        va="bottom", fontsize=7, color="gray", rotation=90)
    ax.set_xticks([xi + width * (len(series) - 1) / 2 for xi in x])
    ax.set_xticklabels(groups, rotation=20, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    if note:
        # wrap=True reflows to figure width; bbox_inches="tight" on save keeps it from clipping.
        fig.subplots_adjust(bottom=0.28)
        fig.text(0.5, 0.02, note, ha="center", va="bottom", fontsize=7.5,
                 color="dimgray", wrap=True)
    fig.savefig(out / f"{name}.png", dpi=140, bbox_inches="tight")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", default="results/summary")
    ap.add_argument("--out", default="reports/charts")
    args = ap.parse_args()
    repo = Path(__file__).resolve().parents[1]
    S = (repo / args.summary) if not Path(args.summary).is_absolute() else Path(args.summary)
    out = (repo / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # ---- 1) wall-clock per task, model x layer (median; telemetry-symmetric) ----
    perf = load(S / "perf-resource-summary.csv")
    pf = {(r["layer"], r["model"]): r for r in perf}
    layers = ["L1", "L2", "L3"]   # full set used for the memory/latency panels below
    # Wall-clock PER TASK is only defined for the agentic layers: L1/L2 report per-task
    # duration, whereas L3 duration is the whole 512-problem run (a different unit — plotting
    # them together would be a unit error and would flatten L1/L2). L3 wall-clock is the
    # ~130 h single-stream / ~9.5 h 8-way story in the report body (S7), not this figure.
    wlayers = ["L1", "L2"]
    write_csv(out, "fig_walltime_by_layer", ["layer", "model", "dur_median_min", "runs"],
              [[L, m, pf.get((L, m), {}).get("dur_med_min", ""), pf.get((L, m), {}).get("runs", "")]
               for L in wlayers for m in MODELS if (L, m) in pf])
    grouped_bar(
        out, "fig_walltime_by_layer", wlayers,
        {SHORT[m]: [fnum(pf.get((L, m), {}).get("dur_med_min")) for L in wlayers] for m in MODELS},
        "median minutes / task", "Wall-clock per task (median), agentic layers L1/L2",
        note="Per-task median (nemotron L1 mean is skewed by a ~13 h verbose runaway). "
             "L3 excluded: its duration is whole-run (512 problems), not per task — see report S7.")

    # ---- 2) energy per SUCCESSFUL task (kJ), model x {L1,L2} ----
    qae = load(S / "quality-adjusted-efficiency.csv")
    qf = {(r["layer"], r["model"]): r for r in qae}
    qlayers = ["L1", "L2"]
    write_csv(out, "fig_energy_per_success",
              ["layer", "model", "energy_kJ_per_success", "succeeded", "attempted"],
              [[L, m, qf.get((L, m), {}).get("energy_kJ_per_success", ""),
                qf.get((L, m), {}).get("succeeded", ""), qf.get((L, m), {}).get("attempted", "")]
               for L in qlayers for m in MODELS if (L, m) in qf])
    grouped_bar(
        out, "fig_energy_per_success", qlayers,
        {SHORT[m]: [fnum(qf.get((L, m), {}).get("energy_kJ_per_success")) for L in qlayers] for m in MODELS},
        "kJ per successful task", "Quality-adjusted efficiency: energy per SUCCESSFUL task",
        note="Lower is better. Blank = 0 successes (nemotron L2). Energy is the self-hosted "
             "cost proxy; runtime-confounded (nemotron on TRT).")

    # ---- 3) resolve vs regression rate (of applied L1 patches) ----
    reg = {r["model"]: r for r in load(S / "regression-rate.csv")}
    def resolve_rate(m):
        r = reg.get(m, {})
        ap_ = fnum(r.get("patches_applied_evaluated")); rs = fnum(r.get("resolved"))
        return round(rs / ap_, 3) if ap_ else None
    write_csv(out, "fig_regression_rate",
              ["model", "applied", "resolved", "resolve_rate_of_applied",
               "regression_rate_of_applied", "pass_to_pass_tests_broken"],
              [[m, reg.get(m, {}).get("patches_applied_evaluated", ""),
                reg.get(m, {}).get("resolved", ""), resolve_rate(m),
                reg.get(m, {}).get("regression_rate_of_applied", ""),
                reg.get(m, {}).get("pass_to_pass_tests_failed", "")] for m in MODELS])
    grouped_bar(
        out, "fig_regression_rate", [SHORT[m] for m in MODELS],
        {"resolve rate": [resolve_rate(m) for m in MODELS],
         "regression rate": [fnum(reg.get(m, {}).get("regression_rate_of_applied")) for m in MODELS]},
        "fraction of applied patches", "L1: resolves-most AND regresses-most (of applied patches)",
        note="Applied/evaluated patches: gpt-oss 24, qwen 22, nemotron 14 (29-task subset — "
             "directional). gpt-oss broke 1078 PASS_TO_PASS tests vs nemotron 3.")

    # ---- 4) TTFT tail: p50 vs p95, model x layer (vLLM only) ----
    tail = load(S / "latency-tail-p95.csv")
    med = defaultdict(lambda: defaultdict(list))
    for r in tail:
        for col in ("ttft_p50", "ttft_p95"):
            v = fnum(r.get(col))
            if v is not None:
                med[(r["layer"], r["model"])][col].append(v)
    tkeys = [(L, m) for L in layers for m in MODELS if (L, m) in med]
    def tmed(k, c):
        vs = med[k][c]
        return round(statistics.median(vs), 3) if vs else None
    write_csv(out, "fig_latency_tail", ["layer", "model", "ttft_p50_med", "ttft_p95_med", "n_runs"],
              [[k[0], k[1], tmed(k, "ttft_p50"), tmed(k, "ttft_p95"), len(med[k]["ttft_p50"])]
               for k in tkeys])
    glabels = [f"{k[0]}/{SHORT[k[1]]}" for k in tkeys]
    grouped_bar(
        out, "fig_latency_tail", glabels,
        {"TTFT p50": [tmed(k, "ttft_p50") for k in tkeys],
         "TTFT p95": [tmed(k, "ttft_p95") for k in tkeys]},
        "seconds", "TTFT tail: p50 vs p95 (median across runs)",
        note="vLLM models only — nemotron (TRT) exposes no latency histograms; "
             "gpt-oss L3 excluded (metric-window failure).")

    print(f"[figures_perf] wrote data CSVs to {out}"
          + ("" if HAVE_MPL else "  (matplotlib not installed -> PNGs skipped)"))


if __name__ == "__main__":
    main()
