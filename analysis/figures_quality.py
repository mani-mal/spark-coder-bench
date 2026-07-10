#!/usr/bin/env python3
"""Quality/thesis figures for the report (matplotlib PNG, light surface for print).

These are the *quality-story* figures the paper leads with — distinct from the
efficiency charts in figures.py (which carry heavy measurement caveats). Three
figures, each built from a committed summary CSV so they regenerate with the rest
of the pipeline (wired into analysis/rebuild-all.sh):

  fig_l2_contract_ablation  the C1 before/after — a harness bug inverted the L2 result
  fig_quality_by_layer      L1/L2/L3 success per model, with Wilson 95% CIs
  fig_l3_truncation         nemotron's L3 last place is a token-budget artifact

Colors follow the validated data-viz palette (categorical CVD ΔE 96.7): models map
to fixed hues everywhere — gpt-oss blue, qwen orange, nemotron violet — so identity
is stable across figures. Every bar is directly labeled, so identity/value never
depend on color alone.
"""
import csv
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SUM = os.path.join(ROOT, "results", "summary")
OUT = os.path.join(ROOT, "reports", "charts")

# ---- validated palette (light surface) --------------------------------------
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
MODEL_COLOR = {                    # fixed categorical hues (validated ΔE 96.7)
    "gpt-oss-120b": "#2a78d6",     # blue
    "qwen3-coder-30b": "#eb6834",  # orange
    "nemotron-super": "#4a3aa7",   # violet
}
MODEL_SHORT = {"gpt-oss-120b": "gpt-oss", "qwen3-coder-30b": "qwen",
               "nemotron-super": "nemotron"}
MODEL_ORDER = ["gpt-oss-120b", "qwen3-coder-30b", "nemotron-super"]
BLUE_ORDINAL = ["#86b6ef", "#3987e5", "#184f95"]  # easy→hard, one-hue ordinal
BEFORE = "#b7b5ad"   # muted: the discredited (contract-invisible) measurement
AFTER = "#2a78d6"    # blue: corrected, contract-visible


def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (p, max(0.0, c - h), min(1.0, c + h))


def read(path):
    with open(os.path.join(SUM, path), newline="") as fh:
        return list(csv.reader(fh))


def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelcolor=INK2, length=0)
    ax.yaxis.grid(True, color=GRID, lw=0.8, zorder=0)
    ax.set_axisbelow(True)


def _label(ax, x, top, text, color=INK):
    ax.annotate(text, (x, top), textcoords="offset points", xytext=(0, 3),
                ha="center", va="bottom", fontsize=8.5, color=color, weight="bold")


def fig_ablation():
    """C1 before/after: L2 node working-app rate, contract-invisible vs -visible."""
    rows = {r[0]: r for r in read("l2-ablation-contract.csv")[1:] if r[1] == "node"}
    models = ["gpt-oss-120b", "qwen3-coder-30b"]
    fig, ax = plt.subplots(figsize=(6.4, 4.0), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    w = 0.38
    for i, m in enumerate(models):
        r = rows[m]
        # cols: …,before_boots(7),after_boots(8),before_working(9),after_working(10)
        N = int(r[2]); bw = int(r[9]); aw = int(r[10])
        pb, lb, hb = wilson(bw, N)
        pa, la, ha = wilson(aw, N)
        for j, (p, lo, hi, cnt, col) in enumerate(
                [(pb, lb, hb, bw, BEFORE), (pa, la, ha, aw, AFTER)]):
            x = i + (j - 0.5) * w
            ax.bar(x, p, w * 0.92, color=col, zorder=3, edgecolor=SURFACE, lw=1.5)
            ax.errorbar(x, p, yerr=[[p - lo], [hi - p]], fmt="none",
                        ecolor=INK, elinewidth=1.3, capsize=3, zorder=4)
            _label(ax, x, hi, f"{cnt}/{N}")
    ax.set_xticks(range(len(models)))
    ax.set_xticklabels([MODEL_SHORT[m] + " · node" for m in models], color=INK)
    ax.set_ylim(0, 1.02)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_ylabel("working-app rate (k/29 ≥ 0.5) · Wilson 95%", color=INK2, fontsize=9)
    ax.set_title("A single harness bug inverted the L2 conclusion (C1)",
                 color=INK, fontsize=11.5, weight="bold", loc="left", pad=10)
    handles = [plt.Rectangle((0, 0), 1, 1, color=BEFORE),
               plt.Rectangle((0, 0), 1, 1, color=AFTER)]
    ax.legend(handles, ["contract-invisible (C1 bug)", "contract-visible (baseline-v7)"],
              frameon=False, fontsize=8.5, loc="upper right", labelcolor=INK2)
    fig.text(0.01, 0.01,
             "Under the bug gpt-oss & qwen looked indistinguishable; corrected, gpt-oss "
             "clearly separates. Source: results/summary/l2-ablation-contract.csv",
             fontsize=6.8, color=MUTED)
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    fig.savefig(os.path.join(OUT, "fig_l2_contract_ablation.png"),
                facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def _l1_counts():
    c = {}
    for r in read("l1-run-ledger.csv")[1:]:
        m = r[0]; c.setdefault(m, [0, 0]); c[m][1] += 1
        if r[3] == "resolved":
            c[m][0] += 1
    return c  # model -> [resolved, N]


def _l2_node_working():
    c = {}
    for r in read("l2-run-ledger.csv")[1:]:
        if r[2] != "node":
            continue
        m = r[0]; c.setdefault(m, [0, 0]); c[m][1] += 1
        if r[8] == "1":  # working_29
            c[m][0] += 1
    return c


def _l3_counts():
    c = {}
    for r in read("l3-run-ledger.csv")[1:]:
        m = r[0]; n = int(r[5]); k = round(float(r[2]) * n)
        c[m] = [k, n]
    return c


def fig_quality_by_layer():
    """L1 resolved pass@1 · L2 node working-app rate · L3 pass@1, with Wilson CIs."""
    layers = [("L1 · SWE-bench\n(resolved pass@1, /29)", _l1_counts()),
              ("L2 · TaskFlow node\n(working app, /20)", _l2_node_working()),
              ("L3 · LiveCodeBench\n(pass@1, /512)", _l3_counts())]
    fig, ax = plt.subplots(figsize=(7.6, 4.2), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    w = 0.26
    for li, (name, data) in enumerate(layers):
        for mi, m in enumerate(MODEL_ORDER):
            if m not in data:
                continue
            k, n = data[m]
            p, lo, hi = wilson(k, n)
            x = li + (mi - 1) * w
            ax.bar(x, p, w * 0.9, color=MODEL_COLOR[m], zorder=3,
                   edgecolor=SURFACE, lw=1.2)
            ax.errorbar(x, p, yerr=[[p - lo], [hi - p]], fmt="none",
                        ecolor=INK, elinewidth=1.1, capsize=2.5, zorder=4)
            _label(ax, x, hi, f"{p*100:.0f}", color=INK2)
    ax.set_xticks(range(len(layers)))
    ax.set_xticklabels([n for n, _ in layers], color=INK, fontsize=9)
    ax.set_ylim(0, 1.05)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_ylabel("success rate · Wilson 95% CI", color=INK2, fontsize=9)
    ax.set_title("Success by layer (same box; relative comparison)",
                 color=INK, fontsize=11.5, weight="bold", loc="left", pad=10)
    handles = [plt.Rectangle((0, 0), 1, 1, color=MODEL_COLOR[m]) for m in MODEL_ORDER]
    ax.legend(handles, [MODEL_SHORT[m] for m in MODEL_ORDER], frameon=False,
              fontsize=9, ncol=3, loc="upper center", labelcolor=INK2,
              bbox_to_anchor=(0.5, 1.0))
    fig.text(0.01, 0.01,
             "L1/L2 gaps are statistically weak; L3 nemotron is budget-confounded (see "
             "fig_l3_truncation). Sources: results/summary/l{1,2,3}-run-ledger.csv",
             fontsize=6.8, color=MUTED)
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    fig.savefig(os.path.join(OUT, "fig_quality_by_layer.png"),
                facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def fig_l3_truncation():
    """Left: nemotron no-code rate by difficulty. Right: paired pass on the 327 answered."""
    raw = read("l3-conditional-analysis.csv")
    diff = {r[0]: (int(r[1]), int(r[2]), float(r[3]))
            for r in raw if r and r[0] in ("easy", "medium", "hard")}
    # cols: model, full_512_pass, full_512_pct, answered_n, answered_pass, answered_pct
    paired = {r[0]: (int(r[4]), int(r[3]), float(r[5]))  # (k=pass, n=answered, pct)
              for r in raw if r and r[0] in MODEL_ORDER and len(r) >= 6 and r[3].isdigit()}

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(9.2, 4.2), dpi=150,
                                   gridspec_kw={"width_ratios": [1, 1.15]})
    fig.patch.set_facecolor(SURFACE)

    # Left — no-code rate by difficulty (one-hue ordinal: easy→hard)
    _style(axL)
    order = ["easy", "medium", "hard"]
    for i, d in enumerate(order):
        n, nc, pct = diff[d]
        axL.bar(i, pct / 100, 0.62, color=BLUE_ORDINAL[i], zorder=3,
                edgecolor=SURFACE, lw=1.2)
        _label(axL, i, pct / 100, f"{pct:.0f}%", color=INK2)
    axL.set_xticks(range(3))
    axL.set_xticklabels([f"{d}\n(n={diff[d][0]})" for d in order], color=INK, fontsize=9)
    axL.set_ylim(0, 1.0)
    axL.yaxis.set_major_formatter(PercentFormatter(1.0))
    axL.set_ylabel("nemotron no-code rate (truncated)", color=INK2, fontsize=9)
    axL.set_title("Truncation is difficulty-correlated", color=INK, fontsize=10.5,
                  weight="bold", loc="left", pad=8)

    # Right — paired pass@1 on the 327 nemotron answered-with-code
    _style(axR)
    for i, m in enumerate(MODEL_ORDER):
        k, n, pct = paired[m]
        p, lo, hi = wilson(k, n)
        axR.bar(i, p, 0.62, color=MODEL_COLOR[m], zorder=3, edgecolor=SURFACE, lw=1.2)
        axR.errorbar(i, p, yerr=[[p - lo], [hi - p]], fmt="none", ecolor=INK,
                     elinewidth=1.1, capsize=2.5, zorder=4)
        _label(axR, i, hi, f"{pct:.1f}%", color=INK2)
    axR.set_xticks(range(3))
    axR.set_xticklabels([MODEL_SHORT[m] for m in MODEL_ORDER], color=INK, fontsize=9)
    axR.set_ylim(0, 1.05)
    axR.yaxis.set_major_formatter(PercentFormatter(1.0))
    axR.set_ylabel("pass@1 on the 327 answered-with-code · Wilson 95%",
                   color=INK2, fontsize=9)
    axR.set_title("When it answers, nemotron ≈ gpt-oss", color=INK, fontsize=10.5,
                  weight="bold", loc="left", pad=8)

    fig.suptitle("L3: nemotron's last place is a fixed-token-budget artifact, not capability",
                 color=INK, fontsize=11.5, weight="bold", x=0.01, ha="left")
    fig.text(0.01, 0.01,
             "185/512 nemotron problems produced no code (143 empty + 42 unextractable), "
             "concentrated on hard problems. Source: results/summary/l3-conditional-analysis.csv",
             fontsize=6.8, color=MUTED)
    fig.tight_layout(rect=[0, 0.04, 1, 0.95])
    fig.savefig(os.path.join(OUT, "fig_l3_truncation.png"),
                facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def main():
    os.makedirs(OUT, exist_ok=True)
    fig_ablation()
    fig_quality_by_layer()
    fig_l3_truncation()
    print("Wrote reports/charts/fig_l2_contract_ablation.png, "
          "fig_quality_by_layer.png, fig_l3_truncation.png")


if __name__ == "__main__":
    main()
