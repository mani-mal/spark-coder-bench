#!/usr/bin/env python3
"""score.py — turn an lcb_runner code-generation eval into our pass@1 + Wilson 95% CI.

Reads LiveCodeBench's per-problem eval file
  <lcb>/output/<model_repr>/codegeneration_<n>_<temp>_eval_all.json
(each instance carries `question_id`, `contest_date`, `graded_list`, `pass@1`) and
writes results/raw/<run-id>/lcb-score.json in the L3 schema:

  {n, passed, pass_at_1, pass_at_1_pct, wilson_ci_95:[lo,hi], n_samples,
   window:{start,end,release_version}, per_problem:[{question_id,contest_date,pass_at_1}]}

pass@1 here is our SHARED single-sample config (n_samples=1, temp 0.2), held identical
to L1/L2 — NOT the LCB-leaderboard sampling config, so these numbers are comparable
across our own models only (disclosed in coverage.md). Stdlib only.
"""
import argparse
import json
import math
from pathlib import Path


def wilson_ci(passed: int, n: int, z: float = 1.96):
    """Wilson score interval for a binomial proportion (passed/n)."""
    if n == 0:
        return (0.0, 0.0)
    p = passed / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-all", required=True, help="path to ..._eval_all.json")
    ap.add_argument("--out", required=True, help="path to write lcb-score.json")
    ap.add_argument("--n-samples", type=int, default=1, help="samples per problem (--n)")
    ap.add_argument("--expect-n", type=int, default=None,
                    help="expected #problems in this window; assert alignment (M6)")
    ap.add_argument("--start-date", default=None)
    ap.add_argument("--end-date", default=None)
    ap.add_argument("--release-version", default="release_v6")
    args = ap.parse_args()

    instances = json.loads(Path(args.eval_all).read_text())
    if not isinstance(instances, list) or not instances:
        raise SystemExit(f"empty/invalid eval-all file: {args.eval_all}")

    per_problem = []
    for inst in instances:
        pa1 = inst.get("pass@1")
        if pa1 is None and "graded_list" in inst:
            gl = inst["graded_list"]
            pa1 = (gl.count(True) / len(gl)) if gl else 0.0
        per_problem.append({
            "question_id": inst.get("question_id"),
            "contest_date": inst.get("contest_date"),
            "pass_at_1": pa1,
        })

    # M6: guard against a misaligned resume-merge. lcb's resume path merges saved generations
    # without filtering by the current window's question_ids and zips sorted lists at eval time, so
    # a second window for the same model/temp could silently grade (problem, generation) pairs that
    # don't correspond. Duplicate or missing question_ids are the observable symptom — fail loudly.
    qids = [pp["question_id"] for pp in per_problem]
    if None in qids:
        raise SystemExit("score.py: an instance is missing question_id — cannot verify alignment")
    if len(set(qids)) != len(qids):
        dupes = sorted({q for q in qids if qids.count(q) > 1})
        raise SystemExit(f"score.py: duplicate question_ids in eval-all (misaligned merge?): {dupes[:10]}")
    if args.expect_n is not None and len(per_problem) != args.expect_n:
        raise SystemExit(f"score.py: expected {args.expect_n} problems for this window, "
                         f"got {len(per_problem)} — window/generation mismatch")

    n = len(per_problem)
    values = [pp["pass_at_1"] or 0.0 for pp in per_problem]
    mean_pass_at_1 = sum(values) / n

    # Wilson CI is a binomial-proportion interval — exact for our single-sample runs
    # (each problem is a Bernoulli trial). passed = #problems solved.
    passed = sum(1 for v in values if v >= 0.999)
    if args.n_samples != 1:
        # n>1: pass_at_1 becomes a per-problem fraction; round to the nearest solved
        # count for the binomial CI and flag it. We run n=1, so this path is unused.
        passed = round(sum(values))
    lo, hi = wilson_ci(passed, n)

    score = {
        "n": n,
        "passed": passed,
        "pass_at_1": round(mean_pass_at_1, 6),
        "pass_at_1_pct": round(mean_pass_at_1 * 100, 3),
        "wilson_ci_95": [round(lo, 6), round(hi, 6)],
        "wilson_ci_95_pct": [round(lo * 100, 3), round(hi * 100, 3)],
        "n_samples": args.n_samples,
        "window": {
            "start": args.start_date,
            "end": args.end_date,
            "release_version": args.release_version,
        },
        "per_problem": per_problem,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(score, indent=2))
    print(f"[score] n={n} passed={passed} pass@1={score['pass_at_1_pct']}% "
          f"CI95=[{score['wilson_ci_95_pct'][0]}, {score['wilson_ci_95_pct'][1]}]% -> {args.out}")


if __name__ == "__main__":
    main()
