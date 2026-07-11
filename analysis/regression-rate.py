#!/usr/bin/env python3
"""L1 regression rate — did a model's patch break previously-passing tests?

SWE-bench ships two test sets per task: FAIL_TO_PASS (the bug to fix) and
PASS_TO_PASS (tests already passing that MUST stay passing). A regression = a
patch that applied and ran but flipped >=1 PASS_TO_PASS test to failing
(equivalently, a non-empty tests_status.PASS_TO_PASS.failure / PASS_TO_FAIL).

No re-run needed: SWE-bench retained the per-instance eval reports at
logs/run_evaluation/<eval_run_id>/<model>/<instance>/report.json. This parses them.

Important framing: by SWE-bench's definition, resolved==True REQUIRES all
PASS_TO_PASS still pass, so regressions can ONLY occur among UNRESOLVED runs. The
rate therefore characterizes *failure quality* (does a wrong attempt also cause
collateral damage), not the winners. Denominator = runs whose patch applied and
was evaluated (patch_successfully_applied), since a patch that never applied
cannot regress anything.

Emits results/summary/regression-rate.csv and prints a per-model table.
"""
import csv, glob, json, os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL = os.path.join(ROOT, "logs", "run_evaluation")
SUM = os.path.join(ROOT, "results", "summary")
MODELS = ["gpt-oss-120b", "qwen3-coder-30b", "nemotron-super"]


def model_of(path):
    return next((m for m in MODELS if f"/{m}/" in path or f"-{m}-" in path or f"{m}" in path.split(os.sep)), None)


agg = defaultdict(lambda: {"applied": 0, "resolved": 0, "regressed": 0,
                           "ptp_tests": 0, "ptp_failed": 0, "instances": []})
per_run = []
for rep in sorted(glob.glob(os.path.join(EVAL, "*", "*", "*", "report.json"))):
    # path: logs/run_evaluation/<eval_run_id>/<model>/<instance>/report.json
    parts = rep.split(os.sep)
    model = next((p for p in parts if p in MODELS), None)
    if not model:
        continue
    instance = parts[-2]
    try:
        d = json.load(open(rep))
    except Exception:
        continue
    # report is keyed by instance_id
    r = d.get(instance) or next(iter(d.values()), {})
    applied = bool(r.get("patch_successfully_applied"))
    resolved = bool(r.get("resolved"))
    ts = r.get("tests_status", {}) or {}
    ptp = ts.get("PASS_TO_PASS", {}) or {}
    ptf = ts.get("PASS_TO_FAIL", {}) or {}
    ptp_fail = len(ptp.get("failure", [])) + len(ptf.get("failure", []) if isinstance(ptf, dict) else [])
    ptp_total = len(ptp.get("success", [])) + len(ptp.get("failure", []))
    regressed = applied and ptp_fail > 0
    a = agg[model]
    if applied:
        a["applied"] += 1
        a["ptp_tests"] += ptp_total
        a["ptp_failed"] += ptp_fail
        if resolved:
            a["resolved"] += 1
        if regressed:
            a["regressed"] += 1
            a["instances"].append(instance)
    per_run.append({"model": model, "instance": instance, "applied": int(applied),
                    "resolved": int(resolved), "pass_to_pass_total": ptp_total,
                    "pass_to_pass_failed": ptp_fail, "regressed": int(regressed)})

rows = []
for m in MODELS:
    a = agg[m]
    ap = a["applied"]
    rows.append({
        "model": m,
        "patches_applied_evaluated": ap,
        "resolved": a["resolved"],
        "regressions": a["regressed"],
        "regression_rate_of_applied": round(a["regressed"] / ap, 3) if ap else "",
        "pass_to_pass_tests_run": a["ptp_tests"],
        "pass_to_pass_tests_failed": a["ptp_failed"],
        "regressed_instances": ";".join(a["instances"]),
    })

if not any(agg[m]["applied"] for m in MODELS):
    # public checkout omits logs/run_evaluation/*/report.json; don't clobber the ported CSV.
    print("No SWE-bench eval reports found under logs/run_evaluation/ (absent in this "
          "checkout); leaving results/summary/regression-rate*.csv untouched.")
    raise SystemExit(0)

os.makedirs(SUM, exist_ok=True)
out = os.path.join(SUM, "regression-rate.csv")
cols = ["model", "patches_applied_evaluated", "resolved", "regressions",
        "regression_rate_of_applied", "pass_to_pass_tests_run",
        "pass_to_pass_tests_failed", "regressed_instances"]
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)

# also drop the per-run detail
with open(os.path.join(SUM, "regression-rate-per-run.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["model", "instance", "applied", "resolved",
                                      "pass_to_pass_total", "pass_to_pass_failed", "regressed"])
    w.writeheader()
    w.writerows(sorted(per_run, key=lambda r: (r["model"], r["instance"])))

print(f"wrote {out}\n")
hdr = ["model", "applied", "resolved", "regressions", "regr_rate", "PtP_run", "PtP_failed"]
print("  ".join(h.ljust(16 if i == 0 else 10) for i, h in enumerate(hdr)))
for r in rows:
    print("  ".join(str(v).ljust(16 if i == 0 else 10) for i, v in enumerate(
        [r["model"], r["patches_applied_evaluated"], r["resolved"], r["regressions"],
         r["regression_rate_of_applied"], r["pass_to_pass_tests_run"], r["pass_to_pass_tests_failed"]])))
if any(r["regressed_instances"] for r in rows):
    print("\nRegressed instances:")
    for r in rows:
        if r["regressed_instances"]:
            print(f"  {r['model']}: {r['regressed_instances']}")
