#!/usr/bin/env python3
"""Robust, failure-aware re-summary of the benchmark long CSV (stdlib only).

Motivated by the 2026-07-02 external audit (findings #5, #6, #7, #8). The published
figures (analysis/figures.py) use plain arithmetic means with no failure taxonomy or
outlier policy, so:

  * infrastructure/evaluator failures (DNS-dropped clones, watchdog kills, missing
    measurement) are silently counted as *model* failures in the L1 denominator, and
  * one ~13 h Nemotron L1 runaway (exit_code 143, 655 kJ) dominates the mean L1 energy.

This script does NOT rerun anything. It reclassifies the EXISTING rows into typed
outcomes and reports both the raw and the failure-separated numbers, plus robust
(median/IQR) energy summaries with an operational-failure sensitivity, and the full
L2 acceptance-fraction distributions (which are bounded, zero-inflated, and bimodal —
a mean±SD is inadequate). Outputs:

  results/summary/l1-run-ledger.csv   per-L1-row typed outcome + validity
  stdout                              human-readable tables

Outcome taxonomy (reconstructed post-hoc from exit_code + metric presence; a real
run should record these at collection time — see the audit note):

  resolved         resolved == 1
  unresolved_valid resolved == 0, has metrics, normal exit  -> genuine model failure
  watchdog_kill    resolved == 0, exit_code == 143          -> operational runaway
  infra_missing    resolved == 0, no metrics captured       -> clone/DNS/guard-drop,
                                                                never a measured attempt

Only `resolved` and `unresolved_valid` are clean model outcomes; `watchdog_kill` and
`infra_missing` are operational and are excluded from the model-valid denominator.
"""
import csv
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LONG_CSV = os.path.join(ROOT, "results", "summary", "benchmark-long.csv")
LEDGER_CSV = os.path.join(ROOT, "results", "summary", "l1-run-ledger.csv")
L2_LEDGER_CSV = os.path.join(ROOT, "results", "summary", "l2-run-ledger.csv")
L3_LEDGER_CSV = os.path.join(ROOT, "results", "summary", "l3-run-ledger.csv")

MODEL_OUTCOMES = ("resolved", "unresolved_valid")          # clean model outcomes
OPERATIONAL = ("watchdog_kill", "infra_missing")           # excluded from model denom


def _f(x):
    x = (x or "").strip()
    return float(x) if x else None


def classify_l1(row):
    res = (row["resolved"] or "").strip()
    if res == "1":
        return "resolved"
    if res != "0":
        # M18: a blank/absent resolved means no resolved.json was written — an infra failure with
        # NO scored outcome (e.g. run-task.py's M1 infra-error path). Do not brand it a genuine
        # model failure ("unresolved_valid"); it is operational and excluded from the model denom.
        return "infra_missing"
    # res == "0": a genuine scored failure — sub-classify infra vs valid by metrics/exit code.
    ec = (row["exit_code"] or "").strip()
    has_metrics = bool((row["duration_s"] or "").strip())
    if not has_metrics:
        return "infra_missing"
    if ec == "143":
        return "watchdog_kill"
    return "unresolved_valid"


def load_rows():
    with open(LONG_CSV, newline="") as fh:
        return list(csv.DictReader(fh))


def iqr_block(vals):
    """Return dict of robust summary stats for a list of floats (>=1)."""
    vals = sorted(vals)
    n = len(vals)
    out = {"n": n, "mean": statistics.mean(vals), "median": statistics.median(vals),
           "min": vals[0], "max": vals[-1]}
    if n >= 2:
        # inclusive quantiles; p25/p75 -> IQR
        q = statistics.quantiles(vals, n=4, method="inclusive")
        out["p25"], out["p75"] = q[0], q[2]
    else:
        out["p25"] = out["p75"] = vals[0]
    return out


def l1_taxonomy(rows):
    l1 = [r for r in rows if r["layer"] == "l1"]
    by_model = {}
    for r in l1:
        by_model.setdefault(r["model"], []).append((r, classify_l1(r)))
    # write ledger
    os.makedirs(os.path.dirname(LEDGER_CSV), exist_ok=True)
    with open(LEDGER_CSV, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["model", "task", "repeat", "outcome", "is_model_valid",
                    "exit_code", "duration_s", "energy_j"])
        for model in sorted(by_model):
            for r, oc in by_model[model]:
                w.writerow([model, r["track_or_task"], r["repeat"], oc,
                            int(oc in MODEL_OUTCOMES), r["exit_code"],
                            r["duration_s"], r["energy_j"]])

    print("=" * 78)
    print("LAYER 1 — failure taxonomy and failure-separated resolved rate")
    print("=" * 78)
    print("Raw rate = resolved / N_total (as published).")
    print("Model-valid rate = resolved / (resolved + unresolved_valid), excluding")
    print("operational outcomes (watchdog_kill, infra_missing) from the denominator.\n")
    header = ("model", "N", "resolv", "unres_valid", "watchdog", "infra_miss",
              "raw", "model_valid")
    print("{:<20}{:>4}{:>8}{:>12}{:>10}{:>11}{:>9}{:>13}".format(*header))
    for model in sorted(by_model):
        ocs = [oc for _, oc in by_model[model]]
        n = len(ocs)
        c = {k: ocs.count(k) for k in
             ("resolved", "unresolved_valid", "watchdog_kill", "infra_missing")}
        valid = c["resolved"] + c["unresolved_valid"]
        raw = c["resolved"] / n if n else 0.0
        mv = c["resolved"] / valid if valid else float("nan")
        raw_s = f"{c['resolved']}/{n}={raw:.1%}"
        mv_s = f"{c['resolved']}/{valid}={mv:.1%}" if valid else "n/a"
        print("{:<20}{:>4}{:>8}{:>12}{:>10}{:>11}{:>9}{:>13}".format(
            model, n, c["resolved"], c["unresolved_valid"], c["watchdog_kill"],
            c["infra_missing"], "", ""))
        print(" " * 20 + f"raw={raw_s}   model-valid={mv_s}")
    print(f"\nPer-run ledger written: {os.path.relpath(LEDGER_CSV, ROOT)}")


def energy_summary(rows):
    print("\n" + "=" * 78)
    print("ENERGY — robust summary + operational-failure sensitivity (per model/layer)")
    print("=" * 78)
    print("Arithmetic mean is dominated by operational runaways; report median/IQR.")
    print("'excl-oper' drops watchdog_kill (exit 143) rows.\n")
    groups = {}
    for r in rows:
        key = (r["model"], r["layer"])
        e = _f(r["energy_j"])
        if e is None:
            continue
        oper = r["layer"] == "l1" and classify_l1(r) in OPERATIONAL
        groups.setdefault(key, []).append((e, oper))
    print("{:<20}{:<4}{:>4}{:>11}{:>11}{:>11}{:>12}{:>12}".format(
        "model", "lyr", "n", "mean_kJ", "median_kJ", "IQR_kJ", "max_kJ", "mean_excl"))
    for key in sorted(groups):
        model, layer = key
        allv = [e for e, _ in groups[key]]
        keep = [e for e, oper in groups[key] if not oper]
        b = iqr_block(allv)
        mean_excl = statistics.mean(keep) if keep else float("nan")
        iqr = b["p75"] - b["p25"]
        print("{:<20}{:<4}{:>4}{:>11.1f}{:>11.1f}{:>11.1f}{:>12.1f}{:>12.1f}".format(
            model, layer, b["n"], b["mean"] / 1e3, b["median"] / 1e3, iqr / 1e3,
            b["max"] / 1e3, mean_excl / 1e3))
    print("\nNote: mean_kJ is 'per run' and mixes different token counts / tool time /"
          " dependency installs — not a like-for-like efficiency figure.")


def classify_l2(row):
    """Typed per-run outcome for a Layer-2 (app-build) row.

    scored          rubric_pass_rate present -> a real graded attempt (k/29 known)
    infra_missing   rubric_pass_rate blank   -> app never scored (harness/serving drop)

    Only `scored` rows count toward the acceptance-fraction distribution.
    """
    v = (row.get("rubric_pass_rate") or "").strip()
    return "scored" if v else "infra_missing"


def l2_ledger(rows):
    """Write the per-run Layer-2 ledger (regenerable from benchmark-long.csv).

    Mirrors l1-run-ledger.csv but for the app-build layer: one row per
    (model, track, repeat) with both the 29-check and the C1-rescored 25-check
    acceptance fractions, the working-app flags at each denominator, and the
    energy/validity provenance. See docs/findings/2026-07-03-l2-* for C1.
    """
    l2 = [r for r in rows if r["layer"] == "l2"]
    os.makedirs(os.path.dirname(L2_LEDGER_CSV), exist_ok=True)
    with open(L2_LEDGER_CSV, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["model", "runtime", "track", "repeat", "outcome",
                    "is_model_valid", "pass_29", "pass_25", "working_29",
                    "working_25", "energy_j", "energy_valid", "exit_code",
                    "duration_s"])
        for r in sorted(l2, key=lambda r: (r["model"], r.get("track_or_task", ""),
                                           r["repeat"])):
            oc = classify_l2(r)
            p29 = _f(r.get("rubric_pass_rate"))
            p25 = _f(r.get("rubric_pass_rate_25"))
            w.writerow([
                r["model"], r["runtime"], r.get("track_or_task", ""), r["repeat"],
                oc, int(oc == "scored"),
                r.get("rubric_pass_rate", ""), r.get("rubric_pass_rate_25", ""),
                "" if p29 is None else int(p29 >= 0.5),
                "" if p25 is None else int(p25 >= 0.5),
                r.get("energy_j", ""), r.get("energy_valid", ""),
                r.get("exit_code", ""), r.get("duration_s", "")])
    print(f"Per-run L2 ledger written: {os.path.relpath(L2_LEDGER_CSV, ROOT)}")


def l3_ledger(rows):
    """Write the per-run Layer-3 (LiveCodeBench) ledger, regenerable from the long CSV.

    One row per served configuration: pass@1 with its Wilson 95% CI, n, and the
    energy/validity provenance. L3 is a single sweep per model (n=512 problems),
    so this is a compact per-config record rather than per-task.
    """
    l3 = [r for r in rows if r["layer"] == "l3"]
    os.makedirs(os.path.dirname(L3_LEDGER_CSV), exist_ok=True)
    with open(L3_LEDGER_CSV, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["model", "runtime", "lcb_pass_at_1", "ci_lo", "ci_hi",
                    "lcb_n", "energy_j", "energy_valid", "duration_s"])
        for r in sorted(l3, key=lambda r: r["model"]):
            w.writerow([
                r["model"], r["runtime"], r.get("lcb_pass_at_1", ""),
                r.get("lcb_ci_lo", ""), r.get("lcb_ci_hi", ""),
                r.get("lcb_n", ""), r.get("energy_j", ""),
                r.get("energy_valid", ""), r.get("duration_s", "")])
    print(f"Per-run L3 ledger written: {os.path.relpath(L3_LEDGER_CSV, ROOT)}")


def l2_distributions(rows):
    print("\n" + "=" * 78)
    print("LAYER 2 — full acceptance-fraction (k/29) distributions, not mean±SD")
    print("=" * 78)
    print("Bounded [0,1], zero-inflated, often bimodal. 'working' = k/29 >= 0.5")
    print("(an arbitrary, unvalidated cutoff — reported for continuity only).\n")
    groups = {}
    for r in rows:
        if r["layer"] != "l2":
            continue
        v = _f(r["rubric_pass_rate"])
        if v is None:
            continue
        groups.setdefault((r["model"], r.get("track_or_task", "")), []).append(v)
    print("{:<20}{:<8}{:>4}{:>8}{:>8}{:>8}{:>9}  distribution".format(
        "model", "track", "n", "mean", "median", "work%", "zeros"))
    for key in sorted(groups):
        model, track = key
        vals = sorted(groups[key])
        n = len(vals)
        work = sum(1 for v in vals if v >= 0.5)
        zeros = sum(1 for v in vals if v == 0.0)
        dist = " ".join(f"{v:.2f}" for v in vals)
        print("{:<20}{:<8}{:>4}{:>8.3f}{:>8.3f}{:>7}{:>9}  {}".format(
            model, track, n, statistics.mean(vals), statistics.median(vals),
            f"{work}/{n}", f"{zeros}/{n}", dist))


def selftest():
    r_res = {"resolved": "1", "exit_code": "0", "duration_s": "10", "energy_j": "1"}
    r_val = {"resolved": "0", "exit_code": "0", "duration_s": "10", "energy_j": "1"}
    r_wd = {"resolved": "0", "exit_code": "143", "duration_s": "999", "energy_j": "1"}
    r_inf = {"resolved": "0", "exit_code": "", "duration_s": "", "energy_j": ""}
    assert classify_l1(r_res) == "resolved"
    assert classify_l1(r_val) == "unresolved_valid"
    assert classify_l1(r_wd) == "watchdog_kill"
    assert classify_l1(r_inf) == "infra_missing"
    b = iqr_block([1.0, 2.0, 3.0, 4.0])
    assert b["median"] == 2.5 and b["min"] == 1.0 and b["max"] == 4.0
    assert classify_l2({"rubric_pass_rate": "0.5172"}) == "scored"
    assert classify_l2({"rubric_pass_rate": ""}) == "infra_missing"
    assert classify_l2({}) == "infra_missing"
    print("SELFTEST: ALL PASS")
    return 0


def main():
    if "--selftest" in sys.argv:
        return selftest()
    rows = load_rows()
    l1_taxonomy(rows)
    energy_summary(rows)
    l2_distributions(rows)
    l2_ledger(rows)
    l3_ledger(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
