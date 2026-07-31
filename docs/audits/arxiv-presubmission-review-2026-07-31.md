# arXiv Pre-Submission Review — paper/main.tex

**Date:** 2026-07-31 · **Reviewed version:** `f83db9e` (paper: pin OpenCode 1.17.9 and add public TaskFlow companion repo), 15 pp, 10 pt two-column.
**Scope:** full correctness re-derivation of every number in the paper against the committed CSVs/ledgers, statistical re-computation (Wilson, McNemar/Holm, Fisher), clean-room compile, page-by-page PDF layout inspection, grammar/typo sweep, live verification of all 15 cited URLs, and arXiv-mechanics checklist. This round is independent of the earlier external ("OpenAI SOL") review; all of that round's agreed corrections were confirmed present.

**Verdict: one wrong number (F1), one significant layout defect (F2), and a handful of minor items. Everything else re-derives exactly. Fix F1–F4, then submit.**

---

## 1. What was verified and is correct

Every value below was independently recomputed from the committed artifacts (not from the paper):

| Claim | Source checked | Result |
|---|---|---|
| L1 raw rates 11/29, 7/29, 6/29; nemotron 6/20 model-valid; 8 `infra_missing` + 1 `watchdog_kill` | `results/summary/l1-run-ledger.csv` | exact match |
| McNemar p = 0.125 / 0.289 / 1.0; Holm 0.375 / 0.578 / 1.0 | `stats-report.txt` (b=6 c=1; b=6 c=2) + hand recomputation | exact match, Holm arithmetic correct |
| Regression 8/24 = 33.3 %, 7/22 = 31.8 %, 3/14 = 21.4 %; 1078 vs 3 P2P failures | `regression-rate.csv` | exact match |
| L2 node 0.724 / 0.178; working 16/20, 3/20; python 0.069 / 0.004; nemotron 0.009 (N=4); gpt k/25 = 0.744; pre-C1 0.252 / 0.155, 6/20, 4/20; contract-only checks 0 → 48 | `l2-rescore-25.csv`, `l2-ablation-contract.csv` | match **except qwen k/25 — see F1** |
| Wilson CIs [58.4, 91.9], [5.2, 36.0], [86.3, 91.7], [64.0, 72.1], [57.0, 65.4] | recomputed from scratch | exact match |
| Fisher exact "p ≈ 9×10⁻⁵" for 16/20 vs 3/20 | recomputed | 8.75×10⁻⁵ ✓ |
| L3 89.3 / 68.2 / 61.3 %; no-code 7 / 10 / 185 (= 143 empty + 42 no block); difficulty split 14.3 / 34.3 / 71.5 % (n = 182/207/123); conditional 96.0 / 95.4 / 82.3 on 327 | `l3-conditional-analysis.csv` | exact match |
| Energy 33.8 vs 143 (incl. runaway) vs 12.8 kJ (2.6×); L2 22.1 / 155.3, pooled 32.8 / 211 | `quality-adjusted-efficiency.csv` | exact match |
| Walltime medians 1.9 / 1.4 / 3.9 min (L1), 16.1 min (L2 nemotron); Table 6 values | `perf-resource-summary.csv` | exact match |
| Active-parameter fractions 4.4 / 10.0 / 10.8 %; 273 GB/s ≈ 6× below 1.7 TB/s; prompt-token median 98.7 % | model specs; `benchmark-summary.csv`; audit M13 | consistent |
| Appendix E subset: table sums to 29; instance listing has exactly 29 IDs; 10-of-12 repos | counted | exact match |
| Compile | tectonic, clean environment | 0 errors; one 8.7 pt overfull (F10); underfulls cosmetic |
| Cited URLs (15) | fetched live | 14 OK incl. both upstream issues, arXiv IDs, `baseline-v7` tag; 1 broken — see F9 |

---

## 2. Findings

### F1 (must fix — wrong number): qwen node k/25 is 0.184, not 0.204

§5.2 states: *"results are dual-reported as k/29 and a C1-rescored k/25 over the 25 reachable checks (gpt-oss node 0.744, qwen 0.204)."*

The 0.204 is a **denominator artifact**. Two qwen node runs (`node-6`, `node-20`, both k29 = 0) have an empty `rubric_pass_rate_25` in `benchmark-long.csv` (their `rubric-score.json` had neither a per-check list nor a `total`, so `aggregate-runs.py` filled nothing). `l2-rescore.py` then averages k/25 over the **18** non-empty runs while k/29 averages over **20**:

- mean k/25 over 18 runs = 0.2044 ← paper's number
- mean k/25 over all 20 runs (zero-runs counted as 0, same denominator as every other L2 number) = **0.1840** — which is exactly what the independently assembled `l2-ablation-contract.csv` (`after_mean_k25`) contains.

gpt-oss is unaffected (all 20 runs populated; 0.744 correct on both paths). The error is conservative for the headline (it *flatters* qwen), but it is wrong by the paper's own definition and internally inconsistent with the committed ablation CSV.

**Fix:** (a) in `l2-rescore.py`, treat an empty `rubric_pass_rate_25` on a scored run as 0 (or fix the `aggregate-runs.py` fallback) and regenerate; (b) change the paper's `qwen 0.204` → `0.184` (one place, §5.2/line ~479).

### F2 (must fix — layout): all seven figures land after the references

In the compiled PDF, Figures 1–7 sit on float pages **10–12, after the bibliography** (pages 8–9), while the text citing them is on pages 4–7. Page 9 is almost empty, page 12 holds a single figure, and Table 6 sits alone on page 15. Cause: the `figure*` (Fig. 1) blocks the float queue and every subsequent `[t]` float queues FIFO behind it until `\clearpage` before the appendix flushes them all.

**Fix options** (any one usually suffices; try in order):
1. Change all single-column figures from `[t]` to `[t!]` and relax the float limits in the preamble:
   `\setcounter{topnumber}{4} \setcounter{totalnumber}{6} \renewcommand{\topfraction}{0.95} \renewcommand{\textfraction}{0.05} \renewcommand{\floatpagefraction}{0.85}`
2. Move the Figure 1 `figure*` declaration earlier (it can only appear on the *next* page after its declaration in two-column mode).
3. If stragglers remain, `\usepackage{placeins}` + a `\FloatBarrier` at the end of Results.

### F3 (should fix): Appendices B–F are never referenced from the body

Only Appendix A is cited (§3.3, "Appendix~\ref{app:serve}"). Add pointers: §3.4 → `app:nemotron`; the DeepSeek/gate paragraph (§3.3) → `app:gate`; §5.2 → `app:contract`; Layer-1 setup (§4) → `app:subset`; §6/§7 efficiency text → `app:resource` (Table 6). Without them, five appendices are orphaned and an arXiv reader has no in-text route to them.

### F4 (should fix): decode tok/s inconsistency — mean vs median, unlabeled

§6 "Telemetry asymmetry" says gpt-oss ~26.9, qwen ~19.7 tok/s at L1; Table 6 says 26.2 and 20.1. Both are real — 26.9/19.7 are **means** from `benchmark-summary.csv`, 26.2/20.1 are **medians** from `perf-resource-summary.csv` — but the paper never says the aggregation differs, so it reads as a contradiction. Fix: use the medians in §6 too, or annotate "(mean)".

### F5 (minor wording): the ~130 h → 9.5 h juxtaposition implies a >8× speedup from 8-way concurrency

130/9.5 ≈ 13.7×, which 8 concurrent streams cannot deliver; the 130 h is a worst-case *extrapolation* (~7–9 tok/s, full-budget decode — `docs/findings/2026-07-01-nemotron-trt-mtp-wedge.md`), not a measurement. Suggest: "single-stream Layer 3 was **estimated at** ~130 h, so we ran it 8-way concurrently (~9.5 h measured)".

### F6 (minor, reproducibility claim): the ablation CSV is not regenerated by the pipeline

`analysis/rebuild-all.sh` step 3 claims `l2-rescore.py` writes *both* `l2-rescore-25.csv` **and** `l2-ablation-contract.csv`; in fact nothing in the repo writes the ablation CSV (only `figures_quality.py` reads it). Figure 4's source table is therefore a frozen hand-assembled artifact, which softens the paper's "every table and figure … regenerates via `make rebuild`" claim. Fix: add a writer (its columns are all derivable from `benchmark-long.csv` + the pre-C1 sweep), or scope the claim.

### F7 (minor): Table 6 N=27 for gpt-oss L2 vs 28 runs everywhere else

L2 is 20 node + 8 python = 28 (qwen shows 28), but gpt-oss shows N=27 — one run evidently lacked a resource-metrics capture. One caption clause ("one gpt-oss run lacks a metrics window") would preempt the question.

### F8 (trivial): bibliography [12] title/URL mismatch

Title says "NVIDIA-Nemotron-3-Super-120B-A12B model card" but the URL is the **-NVFP4** variant repo (the checkpoint actually used). Add `-NVFP4` to the title.

### F9 (minor): OCP MX spec URL returns HTTP 403

Ref [13] `opencompute.org/documents/ocp-microscaling-formats-mx-v1-0-spec-final-pdf` returned 403 on automated fetch (possibly bot-blocking — verify once in a browser). If genuinely gated, cite the arXiv MX paper (arXiv:2310.10537, "Microscaling Data Formats for Deep Learning") instead or in addition. All 14 other URLs verified live, including both upstream issue numbers (`vllm#37854`, `dgx-spark-playbooks#77` — both match the described bug) and the `baseline-v7` tag.

### F10 (typography, all cosmetic)

- One overfull hbox, 8.7 pt: Table 2 (`tab:layers`) header row (line ~290). Column widths sum to 0.88 `\linewidth` + `\tabcolsep` overhead; shave a column (e.g. 0.40 → 0.38) or set `\tabcolsep=3pt` in that table.
- §3.2's pinned-digest paragraph (lines 193–202) renders with badly stretched inter-word spacing around the unbreakable container tags (badness 10000, visible on p. 2). Consider `\sloppy` for that paragraph or rewording so each tag starts a line.
- Title breaks as "…Single DGX / Spark:". Insert a manual break: `Local Coding-Model Configurations\\ on a Single DGX Spark:`.
- Figure 1 (`architecture.jpg`) is a JPEG raster of a dense diagram — node text is illegible at print size and JPEG-artifacted (the prior reviewer also flagged this). Best: re-export as vector PDF or split; minimum: re-export as PNG at higher resolution.
- Figures 6–7 carry tiny grey footnote text below the plot area that is unreadable in print; the same caveats are already in the captions — consider dropping the footers or enlarging.
- Table 4's python column packs two quantities into one cell ("0.069 (0/8)") while the node track uses two labeled columns; the parenthetical (working apps) is never defined. Add a caption note or a fourth column.

### F11 (grammar/wording, all optional)

- Abstract: "The sharpest lesson is a single harness-validity error … **and** a fixed token budget that …" — singular subject, two coordinated lessons, ~60 words. Split into two sentences ("The sharpest lesson is a single harness-validity error that compressed … . A second lesson is a fixed token budget that …").
- Appendix E: "xarray and scikit-learn **built on neither**" — reads as a dangling "neither". Suggest "neither xarray nor scikit-learn built on aarch64" (matching §4's phrasing).
- Casing: "arm64-built" (§4, line ~317) vs "ARM64" everywhere else — pick one.
- §3.4 and Appendix B repeat the "circulating workaround … risks silently miscasting" sentences nearly verbatim; fine for arXiv, but shortening §3.4 to a pointer at App. B would save a third of a column (and helps F3).
- No doubled words or spelling errors found (automated + manual sweep).

---

## 3. arXiv mechanics checklist

1. **Add `\pdfoutput=1`** within the first 5 lines of the preamble (arXiv's pdflatex autodetection; harmless elsewhere).
2. Upload **`main.tex` + `figures/` only** — no `main.pdf`, no aux files. All packages used (`xurl`, `microtype`, `booktabs`, `listings`, …) are in TeX Live 2025; inline `thebibliography` means no `.bbl` worry. Compile verified clean.
3. Metadata abstract must be plain text: strip `\code{…}`, `\cite`, `${\sim}4\times$`, `\emph` when pasting into the arXiv abstract field (e.g. "sm_121a", "~4x").
4. Categories as planned: primary cs.SE, cross-list cs.PF, cs.LG. If this is a first cs.SE submission, check **endorsement** early.
5. **Open author decision (carried over):** byline email is `mani.malarvannan@cdw.com` — confirm CDW publication approval or switch to a durable personal address; consider adding an ORCID.
6. Carried-over style call (yours to make): 10 pt body with 9 pt tables / 7 pt listings vs the prior reviewer's ≥10 pt-everywhere preference. Current choice is standard for arXiv two-column; no action required.

---

## 4. Suggested fix order

1. F1 (number + two-line harness fix + regenerate)
2. F2 (float parameters; re-inspect PDF page by page)
3. F3, F4, F8 (five `\ref`s, one word, one bib token)
4. F5, F7, F10-overfull, F11 abstract/appendix-E sentences
5. F6, F9 and the rest as time allows

None of the findings threaten the paper's conclusions: the headline claims (serving-feasibility matrix, C1 ablation, token-budget artifact) all re-derive exactly from the committed data, and F1's correction moves a secondary sensitivity number in the direction that *strengthens* the reported gap.
