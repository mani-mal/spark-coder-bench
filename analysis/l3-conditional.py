#!/usr/bin/env python3
"""l3-conditional.py — corrected L3 "conditional on answering" analysis (finding C2).

The published claim compared nemotron's pass rate on the subset it answered (314/369=85.1%)
against gpt-oss/qwen's full-512 rates. That is invalid two ways:
  1. Selection bias: truncation is difficulty-correlated, so the answered subset is much easier
     than the full set — every model scores higher on it.
  2. Mixed denominator: 369 = 512 - 143 counts only EMPTY outputs; a further 42 problems produced
     output with no extractable code. The natural "answered" criterion (non-empty extracted code)
     gives 327, not 369.

This recomputes the honest, paired comparison: all models on the SAME subset of problems that
nemotron answered with code. Writes results/summary/l3-conditional-analysis.csv.
"""
import csv
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
L3 = {
    "nemotron-super": "results/raw/nemotron-super-l3-lcb-pre2024m06-1",
    "gpt-oss-120b": "results/raw/gpt-oss-120b-l3-lcb-pre2024m06-1",
    "qwen3-coder-30b": "results/raw/qwen3-coder-30b-l3-lcb-pre2024m06-1",
}


def load(model):
    d = ROOT / L3[model]
    preds = json.loads((d / "lcb-predictions.json").read_text())
    score = json.loads((d / "lcb-score.json").read_text())
    passed = {p["question_id"]: (float(p["pass_at_1"]) >= 1.0) for p in score["per_problem"]}
    out = {}
    for p in preds:
        qid = p["question_id"]
        code_list = p.get("code_list") or []
        output_list = p.get("output_list") or []
        has_code = bool(code_list and str(code_list[0]).strip())
        empty_output = not (output_list and str(output_list[0]).strip())
        out[qid] = {
            "difficulty": p.get("difficulty", "?"),
            "has_code": has_code,
            "empty_output": empty_output,
            "no_extractable": (not has_code) and (not empty_output),
            "passed": passed.get(qid, False),
        }
    return out


def main():
    data = {m: load(m) for m in L3}
    nem = data["nemotron-super"]
    qids = list(nem)

    # --- nemotron no-code breakdown by difficulty ---
    by_diff = {}
    for qid, r in nem.items():
        d = r["difficulty"]
        s = by_diff.setdefault(d, {"n": 0, "no_code": 0})
        s["n"] += 1
        if not r["has_code"]:
            s["no_code"] += 1
    empty = sum(1 for r in nem.values() if r["empty_output"])
    no_extractable = sum(1 for r in nem.values() if r["no_extractable"])
    answered = [qid for qid in qids if nem[qid]["has_code"]]

    print("=== nemotron no-code by difficulty (selection-bias evidence) ===")
    for d in ("easy", "medium", "hard"):
        s = by_diff.get(d)
        if s:
            print(f"  {d:7} no-code {s['no_code']:3}/{s['n']:3} = {s['no_code']/s['n']:.1%}")
    print(f"\n  empty output (143 in review): {empty}")
    print(f"  output but no extractable code (42 in review): {no_extractable}")
    print(f"  total no-code: {empty + no_extractable}  -> answered-with-code: {len(answered)}")

    # --- paired: every model on nemotron's answered-with-code subset ---
    print(f"\n=== paired on the {len(answered)} problems nemotron answered with code ===")
    rows = [["model", "full_512_pass", "full_512_pct",
             "on_nemotron_answered_n", "on_nemotron_answered_pass", "on_nemotron_answered_pct"]]
    for m in ("nemotron-super", "gpt-oss-120b", "qwen3-coder-30b"):
        full = sum(1 for r in data[m].values() if r["passed"])
        sub = sum(1 for qid in answered if data[m].get(qid, {}).get("passed"))
        pct = sub / len(answered)
        print(f"  {m:18} full {full:3}/512 = {full/512:.1%}   answered-subset {sub:3}/{len(answered)} = {pct:.1%}")
        rows.append([m, full, round(full / 512 * 100, 1),
                     len(answered), sub, round(pct * 100, 1)])

    out = ROOT / "results/summary/l3-conditional-analysis.csv"
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["# nemotron no-code by difficulty"])
        w.writerow(["difficulty", "n", "no_code", "no_code_pct"])
        for d in ("easy", "medium", "hard"):
            s = by_diff.get(d)
            if s:
                w.writerow([d, s["n"], s["no_code"], round(s["no_code"] / s["n"] * 100, 1)])
        w.writerow(["# no-code decomposition"])
        w.writerow(["empty_output", empty])
        w.writerow(["output_no_extractable_code", no_extractable])
        w.writerow(["answered_with_code", len(answered)])
        w.writerow([])
        w.writerows(rows)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
