#!/usr/bin/env python3
"""stats.py — statistical treatment for the benchmark (pure Python stdlib).

Implements the rigor the study requires without external deps:
  - success rate as an ESTIMATE with small-sample intervals: Wilson, Jeffreys
    (Bayesian beta-binomial), Clopper-Pearson (exact)
  - pass@k (Chen et al. unbiased) and pass^k (reliability: all k succeed)
  - paired significance: McNemar (exact + continuity-corrected chi^2) and a
    paired bootstrap on per-task differences (p-value + CI)
  - power analysis: required N to detect a given effect (two-proportion, normal approx)

CLI:
  stats.py --selftest                      # validate the math against known values
  stats.py --long <benchmark-long.csv>     # compute CIs + pairwise tests from results
"""
import argparse
import csv
import math
import random
from collections import defaultdict


# ---------- regularized incomplete beta (for exact/Bayesian intervals) ----------
def _betacf(a, b, x, itmax=200, eps=3e-12):
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delt = d * c
        h *= delt
        if abs(delt - 1.0) < eps:
            break
    return h


def betainc(a, b, x):
    """Regularized incomplete beta I_x(a,b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1 - x) / b


def betaincinv(a, b, p, lo=0.0, hi=1.0):
    """Inverse of betainc in x via bisection (I is monotincreasing in x)."""
    if p <= 0:
        return 0.0
    if p >= 1:
        return 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if betainc(a, b, mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ---------- intervals ----------
def wilson_ci(k, n, z=1.959963984540054):
    if n == 0:
        return (0.0, 0.0, 1.0)
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / denom
    return (p, max(0.0, center - half), min(1.0, center + half))


def jeffreys_ci(k, n, alpha=0.05):
    """Bayesian beta-binomial interval with Jeffreys prior Beta(0.5,0.5)."""
    if n == 0:
        return (0.0, 0.0, 1.0)
    a, b = k + 0.5, n - k + 0.5
    lo = 0.0 if k == 0 else betaincinv(a, b, alpha / 2)
    hi = 1.0 if k == n else betaincinv(a, b, 1 - alpha / 2)
    return (k / n, lo, hi)


def clopper_pearson_ci(k, n, alpha=0.05):
    if n == 0:
        return (0.0, 0.0, 1.0)
    lo = 0.0 if k == 0 else betaincinv(k, n - k + 1, alpha / 2)
    hi = 1.0 if k == n else betaincinv(k + 1, n - k, 1 - alpha / 2)
    return (k / n, lo, hi)


# ---------- pass@k / pass^k ----------
def pass_at_k(n, c, k):
    """Prob that >=1 of k samples passes (Chen et al. unbiased estimator)."""
    if k > n:
        raise ValueError("k>n")
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n, c, k):
    """Prob that ALL k sampled attempts pass (reliability)."""
    if k > n:
        raise ValueError("k>n")
    if c < k:
        return 0.0
    return math.comb(c, k) / math.comb(n, k)


# ---------- paired significance ----------
def mcnemar_exact(b, c):
    """Exact two-sided McNemar p (binomial on discordant pairs b,c)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) * (0.5 ** n)
    return min(1.0, 2 * tail)


def mcnemar_chi2(b, c):
    """Continuity-corrected chi^2 statistic + approx p (1 dof)."""
    if b + c == 0:
        return (0.0, 1.0)
    chi2 = (abs(b - c) - 1) ** 2 / (b + c)
    # survival of chi^2 with 1 dof = erfc(sqrt(chi2/2))
    p = math.erfc(math.sqrt(chi2 / 2.0))
    return (chi2, p)


def holm_bonferroni(pairs, alpha=0.05):
    """pairs: list of (label, p). Returns [(label, p, p_adj, reject)] with step-down
    Holm correction (controls FWER across the multiple pairwise comparisons)."""
    m = len(pairs)
    order = sorted(range(m), key=lambda i: pairs[i][1])
    adj = [0.0] * m
    running = 0.0
    for rank, idx in enumerate(order):
        a = (m - rank) * pairs[idx][1]
        running = min(1.0, max(a, running))  # enforce monotonic non-decreasing
        adj[idx] = running
    return [(pairs[i][0], pairs[i][1], adj[i], adj[i] < alpha) for i in range(m)]


def paired_bootstrap_diff(a_rates, b_rates, iters=10000, seed=0):
    """Per-task paired bootstrap of mean(a-b). Returns (mean_diff, lo, hi, p_two_sided)."""
    assert len(a_rates) == len(b_rates) and a_rates
    diffs = [a - b for a, b in zip(a_rates, b_rates)]
    n = len(diffs)
    rng = random.Random(seed)
    obs = sum(diffs) / n
    means = []
    for _ in range(iters):
        s = sum(diffs[rng.randrange(n)] for _ in range(n)) / n
        means.append(s)
    means.sort()
    lo = means[int(0.025 * iters)]
    hi = means[min(iters - 1, int(0.975 * iters))]
    # two-sided p via bootstrap distribution centered at 0
    centered = [m - obs for m in means]
    extreme = sum(1 for m in centered if abs(m) >= abs(obs))
    p = (extreme + 1) / (iters + 1)
    return (obs, lo, hi, p)


# ---------- power analysis ----------
def _z(p):  # inverse normal CDF (Acklam approximation)
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p <= ph:
        q = p - 0.5; r = q*q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    q = math.sqrt(-2*math.log(1-p))
    return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


def required_n_two_proportion(p1, p2, alpha=0.05, power=0.8):
    """Required N PER GROUP to detect p1 vs p2 (two-sided, normal approx)."""
    if p1 == p2:
        return math.inf
    za = _z(1 - alpha / 2)
    zb = _z(power)
    pbar = (p1 + p2) / 2
    num = (za * math.sqrt(2 * pbar * (1 - pbar)) + zb * math.sqrt(p1*(1-p1) + p2*(1-p2))) ** 2
    return math.ceil(num / (p1 - p2) ** 2)


# ---------- selftest ----------
def selftest():
    ok = True

    def check(name, cond, got=None):
        nonlocal ok
        ok = ok and cond
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  got={got}" if got is not None else ""))

    check("betainc(2,3,0.5)=0.6875", abs(betainc(2, 3, 0.5) - 0.6875) < 1e-6, betainc(2, 3, 0.5))
    check("betaincinv roundtrip", abs(betaincinv(2, 3, betainc(2, 3, 0.42)) - 0.42) < 1e-4)
    p, lo, hi = wilson_ci(8, 10)
    check("wilson 8/10 brackets phat", lo < 0.8 < hi and 0.4 < lo and hi < 0.98, (round(lo, 3), round(hi, 3)))
    _, jlo, jhi = jeffreys_ci(8, 10)
    check("jeffreys 8/10 in (0,1)", 0 < jlo < 0.8 < jhi < 1, (round(jlo, 3), round(jhi, 3)))
    check("clopper-pearson 0/10 lower=0", clopper_pearson_ci(0, 10)[1] == 0.0)
    check("pass@1 (5,2)=0.4", abs(pass_at_k(5, 2, 1) - 0.4) < 1e-9, pass_at_k(5, 2, 1))
    check("pass@2 (5,2)=0.7", abs(pass_at_k(5, 2, 2) - 0.7) < 1e-9, pass_at_k(5, 2, 2))
    check("pass^2 (5,2)=0.1", abs(pass_hat_k(5, 2, 2) - 0.1) < 1e-9, pass_hat_k(5, 2, 2))
    check("mcnemar_exact(10,2) significant", mcnemar_exact(10, 2) < 0.05, round(mcnemar_exact(10, 2), 4))
    check("mcnemar_exact(5,5)=1.0", abs(mcnemar_exact(5, 5) - 1.0) < 1e-9)
    mdiff, blo, bhi, bp = paired_bootstrap_diff([1, 1, 1, 0, 1], [0, 0, 1, 0, 0])
    check("bootstrap mean diff=0.6", abs(mdiff - 0.6) < 1e-9, mdiff)
    n = required_n_two_proportion(0.5, 0.6)
    check("power n(0.5 vs 0.6)~387", 350 < n < 420, n)
    hb = holm_bonferroni([("a", 0.01), ("b", 0.04), ("c", 0.03)])
    adj_a = next(x[2] for x in hb if x[0] == "a")
    check("holm adj for p=0.01 (m=3) = 0.03", abs(adj_a - 0.03) < 1e-9, adj_a)
    check("holm monotonic", [x[2] for x in sorted(hb, key=lambda y: y[1])] ==
          sorted(x[2] for x in hb))
    print("\nSELFTEST:", "ALL PASS" if ok else "FAILURES PRESENT")
    return ok


# ---------- CSV report ----------
def report_from_long(path):
    rows = list(csv.DictReader(open(path)))
    # Layer 1: binary per-(model,task) outcomes -> pass@1 with CIs + pairwise McNemar
    # M18: rows with a blank resolved have no scored outcome (infra failures) and are excluded from
    # the pass@1/McNemar denominator — but say so out loud instead of dropping them silently.
    l1_blank = [r for r in rows if r.get("layer") == "l1" and (r.get("resolved") or "").strip() == ""]
    if l1_blank:
        print(f"\n[stats] NOTE: excluding {len(l1_blank)} Layer-1 row(s) with no scored outcome "
              f"(blank resolved) from pass@1/McNemar — see the run ledger for their taxonomy.")
    l1 = [r for r in rows if r.get("layer") == "l1" and r.get("resolved") not in (None, "")]
    if l1:
        print("\n=== Layer 1 (SWE-bench) success — 3-way ===")
        # group by (model, task) -> list of resolved across repeats
        mt = defaultdict(lambda: defaultdict(list))
        for r in l1:
            mt[r["model"]][r["track_or_task"]].append(int(float(r["resolved"])))
        # per-model: pass@1 (aggregate) + CIs, and pass@k / pass^k averaged over tasks
        task_binary = {}  # model -> {task: majority outcome} for paired tests
        for model, tasks in mt.items():
            attempts = sum(len(v) for v in tasks.values())
            succ = sum(sum(v) for v in tasks.values())
            _, wlo, whi = wilson_ci(succ, attempts)
            _, jlo, jhi = jeffreys_ci(succ, attempts)
            print(f"  {model}: pass@1 {succ}/{attempts} = {succ/attempts:.3f}  "
                  f"Wilson95 [{wlo:.3f},{whi:.3f}]  Jeffreys95 [{jlo:.3f},{jhi:.3f}]")
            for k in (2, 3):
                pk = [pass_at_k(len(v), sum(v), k) for v in tasks.values() if len(v) >= k]
                phk = [pass_hat_k(len(v), sum(v), k) for v in tasks.values() if len(v) >= k]
                if pk:
                    print(f"      pass@{k}={sum(pk)/len(pk):.3f}  pass^{k}={sum(phk)/len(phk):.3f}  "
                          f"(over {len(pk)} tasks with >={k} repeats)")
            task_binary[model] = {t: (1 if sum(v) * 2 >= len(v) and sum(v) > 0 else 0)
                                  for t, v in tasks.items()}
        # pairwise McNemar with Holm-Bonferroni correction (multiple comparisons)
        models = list(mt)
        raw = []
        for i in range(len(models)):
            for j in range(i + 1, len(models)):
                A, B = task_binary[models[i]], task_binary[models[j]]
                common = set(A) & set(B)
                b = sum(1 for t in common if A[t] == 1 and B[t] == 0)
                c = sum(1 for t in common if A[t] == 0 and B[t] == 1)
                raw.append((f"{models[i]} vs {models[j]}", mcnemar_exact(b, c), b, c))
        if raw:
            adj = holm_bonferroni([(lbl, p) for (lbl, p, _, _) in raw])
            print("  pairwise McNemar (Holm-Bonferroni, alpha=0.05):")
            for (lbl, p, padj, rej), (_, _, b, c) in zip(adj, raw):
                print(f"    {lbl}: b={b} c={c} p={p:.4f} p_adj={padj:.4f} "
                      f"{'SIGNIFICANT' if rej else 'ns'}")
    # Layer 2: continuous rubric pass-rate -> mean±std + bootstrap diff
    l2 = [r for r in rows if r.get("layer") == "l2" and r.get("rubric_pass_rate") not in (None, "")]
    if l2:
        print("\n=== Layer 2 (app-case) rubric pass-rate ===")
        by_key = defaultdict(list)
        for r in l2:
            by_key[(r["model"], r["track_or_task"])].append(float(r["rubric_pass_rate"]))
        for (model, track), vals in by_key.items():
            mean = sum(vals) / len(vals)
            std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
            print(f"  {model}/{track}: mean={mean:.3f} std={std:.3f} n={len(vals)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--long", help="results/summary/benchmark-long.csv")
    args = ap.parse_args()
    if args.selftest:
        raise SystemExit(0 if selftest() else 1)
    if args.long:
        report_from_long(args.long)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
