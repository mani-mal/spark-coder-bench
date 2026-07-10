#!/usr/bin/env python3
"""l2-rescore.py — Layer 2 dual-report table (finding C1): k/29 vs k/25 reachable.

Four L2 checks required an api-contract.md that was never in the app workspace (baseline-v4/v6
lineage break) and scored 0 across all runs. This reads benchmark-long.csv (which carries both
rubric_pass_rate and rubric_pass_rate_25 from aggregate-runs.py) and writes the per-cell
comparison with working-app counts on both denominators. Stdlib only.

Usage: l2-rescore.py [--long results/summary/benchmark-long.csv] [--out results/summary/l2-rescore-25.csv]
"""
import argparse
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--long", default=str(ROOT / "results/summary/benchmark-long.csv"))
    ap.add_argument("--out", default=str(ROOT / "results/summary/l2-rescore-25.csv"))
    args = ap.parse_args()

    rows = [r for r in csv.DictReader(open(args.long)) if r["layer"] == "l2"]
    grp = defaultdict(list)
    for r in rows:
        grp[(r["model"], r["track_or_task"])].append(r)

    out_rows = [["model", "track", "N", "mean_pass_29", "mean_pass_25",
                 "working_app_29", "working_app_25"]]
    print(f"{'model':16} {'track':7} {'N':>3} {'mean29':>7} {'mean25':>7} {'work29':>7} {'work25':>7}")
    for k in sorted(grp):
        recs = grp[k]
        r29 = [f(r["rubric_pass_rate"]) for r in recs if f(r["rubric_pass_rate"]) is not None]
        r25 = [f(r["rubric_pass_rate_25"]) for r in recs if f(r["rubric_pass_rate_25"]) is not None]
        n = len(recs)
        m29 = sum(r29) / len(r29) if r29 else 0.0
        m25 = sum(r25) / len(r25) if r25 else 0.0
        w29 = sum(1 for x in r29 if x >= 0.5)
        w25 = sum(1 for x in r25 if x >= 0.5)
        print(f"{k[0]:16} {k[1]:7} {n:>3} {m29:>7.4f} {m25:>7.4f} {w29:>3}/{n:<3} {w25:>3}/{n:<3}")
        out_rows.append([k[0], k[1], n, round(m29, 4), round(m25, 4), f"{w29}/{n}", f"{w25}/{n}"])

    with open(args.out, "w", newline="") as fh:
        csv.writer(fh).writerows(out_rows)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
