#!/usr/bin/env python3
"""Quality-adjusted efficiency: cost/energy/time per *successful* task.

The llm_eval taxonomy's headline: "The most useful final comparison should not be
'Model A generates 50 tok/s and B generates 40.' It should be GPU-hours (or energy)
per successfully completed task." We self-host, so energy is the cost proxy
(no per-token dollar price). Every input already lives in the ledgers.

Success definition per layer:
  L1 (SWE-bench Verified subset) -> outcome == "resolved"
  L2 (app-build)                 -> working_29 truthy (acceptance fraction >= 0.5)
  L3 is single-shot pass@1 over a fixed 512-problem set, already a rate; efficiency
     per solved problem is energy_total / (pass@1 * n) -- reported in the doc, not here.

Emits results/summary/quality-adjusted-efficiency.csv and prints a table.
Wall-clock is single-stream serial time on one box; "tasks/hour" is throughput at
the concurrency each layer actually ran (mostly seq=1), NOT a max-concurrency figure.
"""
import csv, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUM = os.path.join(ROOT, "results", "summary")
MODELS = ["gpt-oss-120b", "qwen3-coder-30b", "nemotron-super"]


def load(name):
    p = os.path.join(SUM, name)
    return list(csv.DictReader(open(p))) if os.path.exists(p) else []


def truthy(v):
    return str(v).strip().lower() in ("1", "true", "yes")


rows = []
# --- L1 ---
# The headline energy-per-success EXCLUDES operational non-attempts (is_model_valid == 0):
# an infra failure or the ~13 h watchdog runaway burned energy but was never a model attempt,
# and folding it into "energy per successful task" mismeasures model efficiency (for nemotron
# the single runaway is ~76% of its L1 energy). The operational-failure-INCLUSIVE value is kept
# alongside as a disclosed sensitivity. gpt-oss/qwen have no operational failures, so the two
# coincide for them.
l1 = load("l1-run-ledger.csv")
for m in MODELS:
    mr = [r for r in l1 if r["model"] == m]
    valid = [r for r in mr if truthy(r.get("is_model_valid"))]
    solved = [r for r in mr if r["outcome"].strip().lower() == "resolved"]
    dur = [float(r["duration_s"]) for r in valid if r["duration_s"]]
    en = [float(r["energy_j"]) for r in valid if r.get("energy_j")]
    en_all = [float(r["energy_j"]) for r in mr if r.get("energy_j")]
    ns = len(solved)
    rows.append({
        "layer": "L1", "model": m, "attempted": len(mr), "succeeded": ns,
        "success_rate": round(ns / len(mr), 3) if mr else "",
        "tasks_per_hour": round(ns / (sum(dur) / 3600), 2) if ns and dur else "",
        "energy_kJ_per_success": round(sum(en) / ns / 1000, 1) if ns and en else "",
        "energy_kJ_per_success_incl_opfail": round(sum(en_all) / ns / 1000, 1) if ns and en_all else "",
        "energy_windows": len(en),
        "gpu_min_per_success": round(sum(dur) / ns / 60, 1) if ns and dur else "",
    })
# --- L2 ---
# Every Layer-2 working app occurs on the Node track, so the headline energy-per-working-app
# uses NODE-track energy only. The both-tracks-POOLED value folds in Python-track energy that
# produced zero working apps (inflating the numerator by ~35-48%); it is kept as a disclosed
# sensitivity.
l2 = load("l2-run-ledger.csv")
for m in MODELS:
    mr = [r for r in l2 if r["model"] == m]
    work = [r for r in mr if truthy(r.get("working_29"))]
    node = [r for r in mr if r.get("track", "").strip().lower() == "node"]
    dur = [float(r["duration_s"]) for r in node if r["duration_s"]]
    en = [float(r["energy_j"]) for r in node if r.get("energy_j")]
    en_pooled = [float(r["energy_j"]) for r in mr if r.get("energy_j")]
    nw = len(work)
    rows.append({
        "layer": "L2", "model": m, "attempted": len(mr), "succeeded": nw,
        "success_rate": round(nw / len(mr), 3) if mr else "",
        "tasks_per_hour": round(nw / (sum(dur) / 3600), 2) if nw and dur else "",
        "energy_kJ_per_success": round(sum(en) / nw / 1000, 1) if nw and en else "",
        "energy_kJ_per_success_incl_opfail": round(sum(en_pooled) / nw / 1000, 1) if nw and en_pooled else "",
        "energy_windows": len(en),
        "gpu_min_per_success": round(sum(dur) / nw / 60, 1) if nw and dur else "",
    })

COLS = ["layer", "model", "attempted", "succeeded", "success_rate",
        "tasks_per_hour", "energy_kJ_per_success", "energy_kJ_per_success_incl_opfail",
        "energy_windows", "gpu_min_per_success"]
out = os.path.join(SUM, "quality-adjusted-efficiency.csv")
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=COLS)
    w.writeheader()
    w.writerows(rows)

print(f"wrote {out}\n")
wch = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in COLS}
print(" | ".join(c.ljust(wch[c]) for c in COLS))
print("-|-".join("-" * wch[c] for c in COLS))
for r in rows:
    print(" | ".join(str(r[c]).ljust(wch[c]) for c in COLS))
