# L3 "conditional on answering" was selection-biased + mixed-denominator (C2)

**Date:** 2026-07-03
**Trigger:** Independent AI code review (`docs/audits/independent-code-review.md`, finding C2), verified against raw data.
**Status:** Corrected everywhere it was published; paired analysis committed.

---

## The published claim (now retired)

> nemotron "conditional on producing an answer passed **314/369 = 85.1%** (near gpt-oss, above
> qwen)"

This compared a *conditional* rate on nemotron's answered subset against gpt-oss/qwen's *full-512*
rates. Two independent errors:

### Problem 1 — selection bias
Truncation is strongly difficulty-correlated. From `lcb-predictions.json` (nemotron), no-code rate
by difficulty:

| difficulty | no-code | rate |
|---|---|---|
| easy | 26/182 | 14.3% |
| medium | 71/207 | 34.3% |
| hard | 88/123 | **71.5%** |

The answered subset is therefore much easier than the full set — *every* model scores higher on
it. Comparing nemotron-conditional to others-full is invalid (and, as it happens, understates
nemotron).

### Problem 2 — mixed denominator
`369 = 512 − 143`, where 143 counts only **empty outputs**. A further **42** problems produced
output with **no extractable code** (also scored fail): **185** no-code problems total. "Answered"
by the natural criterion (non-empty extracted code) is **327**, not 369.

## Corrected paired analysis

All models on the **same 327 problems nemotron answered with code**
(`analysis/l3-conditional.py` → `results/summary/l3-conditional-analysis.csv`):

| model | full 512 | on nemotron-answered 327 |
|---|---|---|
| nemotron-super (TRT) | 61.3% | **96.0%** (314/327) |
| gpt-oss-120b (vLLM) | 89.3% | 95.4% (312/327) |
| qwen3-coder-30b (vLLM) | 68.2% | 82.3% (269/327) |

The qualitative conclusion — *truncation artifact, not capability; nemotron ≈ gpt-oss when it
answers* — **survives and strengthens**. The 42 answered-but-unextractable cases are a separate
code-extraction/formatting failure mode (not truncation) and are reported as such.

## What to publish

- Raw pass@1 (comparable, fixed budget) — unchanged: gpt-oss 89.3 / qwen 68.2 / nemotron 61.3.
- Truncation rate **185/512** with the 143-empty / 42-no-extractable split.
- The **per-difficulty** no-code rates (the sharp form of the "fixed budget penalizes verbose
  reasoning" thesis — the penalty lands almost entirely on hard problems).
- The **paired** conditional rates on the 327-problem subset (nemotron 96.0 / gpt-oss 95.4 /
  qwen 82.3), never a conditional-vs-full comparison.

## Reproduce

```
python3 analysis/l3-conditional.py
```

Reads the three `results/raw/*-l3-lcb-pre2024m06-1/` dirs (`lcb-predictions.json` for
code/output presence + difficulty, `lcb-score.json` for per-problem pass@1).
