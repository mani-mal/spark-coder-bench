# Independent review — code, metrics, and arXiv readiness

**Reviewer:** the AI assistant (an AI reviewer model 5), independent pass
**Date:** 2026-07-03
**Repo state reviewed:** `main` @ `3975ce8` (post–Bucket A reframe), clean tree, pushed to origin
**Companion repo:** `taskflow-local-app-benchmark` (tags `baseline-v1..v6`)
**Prior audit:** `docs/audits/benchmark-audit-and-arxiv-recommendation.md` (2026-07-02) and its
verification note `docs/findings/2026-07-02-audit-verification-and-decision.md`

**Method.** Four parallel review passes (analysis/statistics code; layer-1/2/3 harnesses; infra
serving + metrics collection; docs/data/publication surface), each cross-checked against the live
data in `results/raw/` (154 run dirs), `results/summary/`, `reports/charts/`, and 36 manifests.
Headline numbers were recomputed from the long CSV. This review deliberately looked for issues
the external audit did *not* find; overlap with it is noted explicitly in §6.

---

## Executive summary

The Bucket A reframe was genuinely executed and the repo is in far better shape than at the
external audit: docs are largely reconciled, the L2 metric is renamed, a failure taxonomy and
robust re-summary exist, publication inputs are committed and pushed, and `robust-summary.py`
regenerates its ledger byte-identically. The statistics library is solid (Wilson/Jeffreys/
Clopper–Pearson/McNemar/Holm all verified correct; all headline quality numbers reproduce
exactly from the long CSV).

However, this review found **four new critical problems** that must be fixed before any
publication, plus a cluster of major issues concentrated in the *efficiency/figures* pipeline
and the *published interpretation of L3*:

1. **The Layer 2 contract was never visible to the models.** The graded API contract exists
   only in the harness repo; `baseline-v6` (the tree every L2 run starts from) does not contain
   `benchmark-spec/api-contract.md`. Root cause: the file was added at `baseline-v4`, but
   **v4 is not an ancestor of v6** — the tag lineages diverged and the file was lost. Four of
   the 29 checks depend on unguessable specifics and scored **0/61 across all runs of all
   models** (`dashboard_summary_keys`, `project_archive`, `project_edit`, `task_update_status`).
2. **The published L3 "conditional-on-answering" statistic is selection-biased and its
   denominator mixes two criteria.** Truncation is strongly difficulty-correlated (71.5% of
   *hard* problems produced no code vs 14.3% of easy), so comparing nemotron's conditional rate
   (85.1%) against other models' *full-set* rates is invalid. Recomputed correctly (all models
   paired on the same answered subset), the qualitative claim survives and strengthens:
   **nemotron 96.0%, gpt-oss 95.4%, qwen 82.3%** on the 327 problems nemotron answered with code.
3. **The efficiency/figures pipeline contains real errors:** the Pareto chart inflates nemotron
   L1 quality (0.2857 vs the published 0.2069); gpt-oss's L3 energy capture is broken by ~3
   orders of magnitude (543 J for 512 problems vs ~1.0–1.5 MJ for the other models); the
   per-model "efficiency table" pools incomparable layers; TTFT figures average percentiles.
4. **10 of 12 TRT-LLM manifests are invalid JSON** (unescaped quotes from embedded YAML
   comments) — the reproducibility record for exactly the nemotron arm is machine-unreadable.

**arXiv verdict (short form):** the external audit's conclusion stands — *do not publish as a
model-ranking paper; publish as a systems + methodology case study* — and the reframe is the
right call. But the reframed paper is **not yet submission-ready** either: findings 1–4 above
sit squarely inside the material a methodology paper would present as evidence. The good news
is that almost everything is fixable by **rescoring, reanalysis, and documentation** — no new
model runs are strictly required — and finding 1 can honestly be *converted into a
contribution* (it is a textbook instance of the paper's own thesis: harness validity errors
dominate model effects at this scale). Detailed assessment in §7.

---

## 1. Critical findings (new in this review)

### C1. L2 models were graded against a contract they could not see

- **Evidence.** `layer2_appcase/prompt.md:8` tells the model: *"Frozen API contract you MUST
  implement exactly: `benchmark-spec/api-contract.md`"*. `git ls-tree -r baseline-v6` in the
  app repo shows `benchmark-spec/` contains only app-requirements / evaluation-rubric /
  expected-output / run-protocol — **no api-contract.md**. The contract lives only in the
  harness repo (`layer2_appcase/api-contract.md`) and is never copied into the workspace or
  inlined into the prompt. `AGENTS.md`, the OpenCode config, and the track prompts contain none
  of the exact routes/keys either.
- **Root cause.** App-repo commit `8b89ebd` ("Add pinned API contract to frozen spec") is
  tagged `baseline-v4` — but `git merge-base --is-ancestor baseline-v4 baseline-v6` fails:
  **v4 is not on v6's lineage**. The contract was added on a branch that v5/v6 never included.
  The runner default moved v4 → v6 without noticing the file was gone.
- **Impact.** Checks requiring unguessable specifics are structurally unreachable — confirmed
  empirically: `dashboard_summary_keys`, `project_archive`, `project_edit`,
  `task_update_status` scored **0 in all 61 L2 runs across all three models** (≈4/29 ≈ 14% of
  the metric). Additional checks (`PATCH` vs `PUT`, exact 4000 port, exact JSON shapes) were
  guessable only via the requirements doc's prose. The k/29 numbers therefore measure
  "contract inference from prose" plus luck on exact routes, not acceptance against a
  *communicated* contract. The relative ordering partially survives (same handicap for all
  models), but the absolute numbers (0.252 / 0.155 / 0.009) understate all models, the
  "working app ≥ 0.5" threshold sits on a 29-denominator that includes 4 dead checks, and the
  README/HELP language ("must implement the frozen contract *exactly*") is false as executed.
- **Not disclosed** in `layer2_appcase/COVERAGE.md` or anywhere else.
- **Fix options.** (a) *Rescore existing runs* on the 25 reachable checks (k/25), re-derive
  the working-app threshold, and disclose the incident — no reruns needed; ordering is
  preserved, absolute levels rise ~16% relative. (b) *Rerun L2* from a baseline that actually
  contains the contract (Bucket B territory). For the methodology paper, (a) + a candid
  finding note is defensible and on-thesis.

### C2. L3 conditional-pass framing: selection bias + mixed denominator (published in HELP.md §6, BENCHMARK_OVERVIEW §4)

- **Published claim:** nemotron "conditional on producing an answer passed 314/369 = 85.1%
  (near gpt-oss, above qwen)" — comparing a conditional rate on nemotron's answered subset
  against gpt-oss/qwen's full-512 rates.
- **Problem 1 — selection bias.** Truncation is strongly difficulty-correlated. From
  `lcb-predictions.json` (nemotron): no-code rate by difficulty = easy 26/182 (14.3%),
  medium 71/207 (34.3%), **hard 88/123 (71.5%)**. The answered subset is therefore much easier
  than the full set; *every* model scores higher on it. Comparing nemotron-conditional to
  others-full is invalid (and, as it happens, *understates* nemotron).
- **Problem 2 — mixed denominator.** The 369 figure = 512 − 143, where 143 counts only
  **empty outputs**. But a further **42 problems produced output with no extractable code**
  (both scored fail): 185 no-code problems total. "Answered" by the natural criterion
  (non-empty extracted code) is 327, not 369.
- **Corrected paired analysis** (all models on the same 327 answered-with-code problems):
  | model | full 512 | on nemotron-answered 327 |
  |---|---|---|
  | nemotron-super (TRT) | 61.3% | **96.0%** (314/327) |
  | gpt-oss-120b (vLLM) | 89.3% | 95.4% |
  | qwen3-coder-30b (vLLM) | 68.2% | 82.3% |
  The qualitative conclusion (*truncation artifact, not capability; nemotron ≈ gpt-oss when it
  answers*) survives and **strengthens** — but the published arithmetic and comparison basis
  must be corrected, and the 42 answered-but-unextractable cases separately reported (they are
  a code-extraction/formatting failure mode, not truncation).
- Also flag hards-vs-easies in the paper: on the full set the truncation penalty lands almost
  entirely on hard problems, which is a sharper statement of the "fixed budget penalizes
  verbose reasoning" thesis than the aggregate 27.9%.

### C3. Pareto figure inflates nemotron L1 quality (`analysis/figures.py:134-143`)

`fig_success_energy` averages quality only over rows where **both** quality and `energy_j`
are present. Nemotron's 8 metric-less L1 runs (all failures, kept in the honest denominator by
`aggregate-runs.py`) drop out → published `reports/charts/fig_success_energy.csv` says
nemotron L1 quality **0.2857** (6/21) vs the headline **0.2069** (6/29) — +38% relative, for
exactly the arm with missing telemetry. This silently reintroduces the survivorship bias that
`aggregate-runs.py:55-61` was explicitly fixed to prevent. Fix: average quality over all rows;
pair energy only where present (or plot model-valid and raw as two series).

### C4. gpt-oss L3 energy capture is broken (~3 orders of magnitude)

`benchmark-long.csv` L3 energies: gpt-oss **543.52 J** (0.151 Wh) vs qwen 1,007,353 J and
nemotron 1,478,690 J. 543 J for a multi-hour 512-problem generation run is physically
impossible — this is a broken/partial capture window (consistent with M7 below: watchdog
restarts overwrite `window.json`, and the gpt-oss L3 run had documented crashes/restarts).
It flows unguarded into `fig_energy_per_task` and any per-layer Wh statement. Fix: mark the
cell invalid (or recompute from the full hw time series if retained); add a J/token sanity
bound to the aggregation so impossible energies fail loudly.

### C5. 10 of 12 TRT-LLM manifests are invalid JSON (`infra/trtllm/serve-model-trtllm.sh:158`)

`config_yaml` is embedded into the manifest heredoc without escaping; the YAML comments contain
double quotes. Verified: every `serve-trtllm-nemotron-*` and `serve-trtllm-qwen3-*` manifest
fails `json.load`; only the two gpt-oss TRT manifests parse. The machine-readable
reproducibility record — the thing the manifests exist for — is broken for precisely the
nemotron arm. Fix: JSON-encode the YAML string (e.g. via `python3 -c 'json.dumps'`) and
regenerate/repair the 10 files (content is intact; it's an escaping bug).

---

## 2. Major findings

### Scoring & fairness (layer harnesses)

| # | Where | Defect | Consequence |
|---|---|---|---|
| M1 | `layer1_swebench/run-task.py:86-92,107-112` | opencode/run-context exit code never checked; empty diff → `resolved.json {"resolved":0}` written and resume-skipped forever | Server death mid-sweep records the rest of that model's tasks as legitimate failures. external AI audit flagged the pattern; the *permanence via resume-skip* is the sharper part. The `l1-run-ledger` taxonomy now labels 8 nemotron rows `infra_missing` — good — but the mechanism remains for future runs |
| M2 | `run-task.py:115,127-131` | Eval report filename omits the instance id (`<profile>.l1-<profile><tag>-<repeat>.json`, written to CWD — the stray repo-root JSONs are these); glob fallback can silently read a **stale previous instance's report** and score `resolved=0` | Wrong-task attribution on any eval crash; also the root-dir litter is tracked in git |
| M3 | `run-task.py:74-77` | Retry reuses a dirty `/tmp/swebench-work/<run_id>` (prior attempt's staged changes survive `git checkout` to the same commit) | Scored diff can mix two attempts |
| M4 | `layer2_appcase/rubric_tests/run_rubric.py:321-333,361-365` | No check that :4000 is free pre-boot; teardown is one SIGTERM, no SIGKILL escalation or port verification | A leaked backend from a previous run (even a different model) can be health-polled and scored as the current app — cross-model leakage risk, undisclosed |
| M5 | `layer3_livecodebench/run-suite.sh:76` + lcb cache paths | Generations keyed only by (model, n, temp) — no window/seq/runtime | `--seq 2` repeats would silently reuse seq-1 generations (repeats not independent); a vLLM-then-TRT rerun of the same profile would reuse the other runtime's generations; L3 run-id lacks the `-trt` tag (see M9) |
| M6 | patched lcb `main.py:52-56,89-91` | Resume merge never filters saved generations against the current window's question_ids; eval zips sorted lists | A second window for the same model/temp would silently grade misaligned (problem, generation) pairs. Latent today (one window per model); cheap assert in `eval/score.py` would catch it |
| M7 | `l3-watchdog.sh:42-45`, `-trt.sh:70-73` | Each watchdog restart reruns `run-context.sh` with the same run-id, **overwriting** `window.json`/`run-summary.json` | After any restart, L3 efficiency metrics cover only the final segment while the score covers all generations — direct cause of C4; distorts J/token for exactly the crash-prone runs |
| M8 | `run-benchmark.sh:28-36` | L2 driver never checks the L1 lock (L1 checks L2's) | Starting an L2 sweep during an L1 sweep re-serves :8000 with a different model; in-flight L1 tasks then score 0 via M1 |
| M9 | run-id scheme | L3 nemotron run is keyed `nemotron-super` while its L1/L2 rows are `nemotron-super-trt` | Every per-model grouping treats them as two models: nemotron's L3 never joins its record; figure CSVs contain a phantom mostly-blank `nemotron-super` row; `aggregate.py` also emits `"model": null` for all 37 `-trt` L1/L2 run-summaries and the L3 id (profile parse only handles `-l1-`/`-l2-` and requires verbatim registry match) |
| M10 | `layer3_livecodebench/coverage.md:54` | Claims "seed 0 shared" for L3, but `GEN_CMD` passes **no seed** (OpenAI kwargs contain none) | Disclosure inaccuracy in a fairness table — must be corrected in the paper |

### Metrics & figures (analysis/infra)

| # | Where | Defect | Consequence |
|---|---|---|---|
| M11 | `figures.py:158-189` | Per-model efficiency table pools **layers** (L1 binary outcomes averaged with L2 fractions; qwen's pool includes its L3 row where gpt-oss's L3 tok/J is blank) | Published `fig_efficiency_table.csv` cross-model deltas partly reflect which layers emitted metrics, not model differences |
| M12 | `figures.py:64-79,113-120` | No CIs/error bars on any figure; `fig_ttft` plots the **mean of per-run p50/p90/p99** labeled as TTFT percentiles | Mean-of-percentiles is not a percentile; 3-sample and 29-sample bars read as equally precise |
| M13 | tokens/joule definition | `total_tokens/energy_j` with prompt tokens at a **median 98.7% of total** (agent loop re-sends context every turn, largely KV-cache hits) | "77 tok/J" is dominated by re-submitted prompt tokens, not decode work; internally consistent across vLLM models but not a decode-energy figure and never caveated. Report J/generated-token (or both) |
| M14 | `collect-hw.sh:67-71` | No field-count guard on the nvidia-smi line; a transient failure left-shifts the CSV row (power column receives load-average) | Bogus ~1 W samples would silently enter the trapezoid energy integral. Latent (all 154 runs currently have clean 19-col rows) but the failure mode is silent |
| M15 | `run-context.sh` (no traps) + `stop-collectors.sh` | Interrupt orphans the infinite-loop collectors; and the recovery tool is dead code (wrong `REPO_ROOT`, looks for `sampler.pid` while collectors write `hw.pid`/`vllm-prom.pid`) | Re-running the same run-id then has two writers interleaving `hw.csv` |
| M16 | `serve-model.sh:90-98`, TRT twin | Sanity-gate result is advisory: `SANITY_OK` never affects the exit code; script exits 0 with a failed-gate server left serving; watchdogs re-serve through this path | Timed runs can be recorded against a model that failed the coherence gate; nothing downstream checks `sanity_check.ok` |
| M17 | `models.json:7` vs TRT configs | Registry claims `max_num_seqs:1` / `kv auto` "held identical across all models", but TRT ran `MAX_BATCH_SIZE=8/4` and fp8 KV | The fairness claim in the single source of truth contradicts the actual TRT serving config; only YAML comments disclose it (HELP.md §7 does disclose the fp8 KV) |
| M18 | `stats.py:261` (+ `robust-summary.py:52-61`) | L1 rows with blank `resolved` are silently dropped from the CI/McNemar denominator; the taxonomy classifies blank as `unresolved_valid` (only `=="1"` tested) | Latent today (no blank rows), but the exact ambiguous case the taxonomy exists for would be mislabeled and the stats denominator quietly shrunk |

---

## 3. Minor findings (abridged; file:line, one-liner)

**Analysis.** `aggregate-runs.py:154-167` group `n` vs per-column non-blank n mismatch (energy mean over 21 rows labeled n=29); `:167` `pstdev` published as "std" (understates spread ~15–22% at n=3–4); `:131-132` unparseable run-dir names dropped without logging; `stats.py:182-183` bootstrap percentile off-by-one (negligible); `:150` McNemar continuity χ² not clamped at b==c (unused path); `:271-283` pooled Wilson over repeats assumes independence + majority rule breaks ties toward success (no live effect, repeats=1); paired-bootstrap and power-analysis functions are dead code — L2 gets no inferential statistic at all; `figures.py:99` writes literal `nan` strings into `fig_throughput.csv`; `fig_energy_per_task` mixes 88 mostly-n=1 L1 task bars with aggregated views; `mem_util_mean` is 0.0 in every row (never captured) yet published in the efficiency table as if measured.

**Harnesses.** `layer1/run-suite.sh:46` falls back to the unverified `probed` subset list; `layer3/eval/score.py` trusts CLI window metadata with no n/window assert (would catch M6); `setup-lcb.sh:46-62` silently skips *both* patches if `git apply --check` fails on drift, and step-4 verification checks only the registry patch; watchdog stall detection blind spots (vLLM counter reset after restart; stale output JSON disables stall detection; `pkill` can corrupt `save_cache()` mid-write); `contract.py:46` failing venv pytest re-runs under system python (recorded, not scored); `run_rubric.py:262-270` `shell=True` + timeout kills only the shell (build children linger → feeds M4); no timeout on the opencode build step in either L1 or L2; `run-benchmark-l1.sh:80` HF_TOKEN visible in `ps`; streaming patch makes the 1800 s client timeout per-read-gap (total generation time effectively uncapped; comment describes old semantics); `start-python-backend.sh` imports (executes) model code on the host at scoring time, unnoted in coverage docs.

**Infra.** Readiness-timeout leaves a still-loading container that can become ready ungated minutes later; `aggregate.py:128` masks Prometheus counter resets as delta=0; collector kill at +1.5 s < 2000 ms tail-grace default (histogram finalization can land in neither); `run-context.sh:66` belatedly enables `set -e` mid-script; `models.json` nemotron expert counts null while manifests carry 512/22 (registry/manifest disagreement); TRT serves **unauthenticated** on 0.0.0.0:8355 (the Authorization header in its own sanity check is decorative) — asymmetric with vLLM and worth a security note; `sanity-check.py` coherence bar (≥30 words + "def") mostly unexercised for reasoning models whose budget goes to the stripped reasoning channel.

**Docs/publication surface.**
- `docs/HELP.md` §4 still says L3 grading runs "in a `bwrap` sandbox" — contradicts
  `layer3_livecodebench/coverage.md` (bwrap cannot run on this kernel; disclosed fallback).
  HELP §3 table also still says "29-check rubric pass rate" where the renamed metric is used
  elsewhere.
- `docs/publishing-plan.md` is stale: "two models", "n=4", implies the 100-point "fixed
  rubric", references `reports/dgx-spark-coding-model-benchmark-report.md` which does not exist.
- **No LICENSE and no CITATION.cff** — the publishing plan itself requires a license; blocking
  for GitHub/arXiv release.
- `reports/screenshots/` is empty; the canonical write-up has not been started.
- Three stray single-task SWE-bench report JSONs tracked at repo root (M2's litter):
  `gpt-oss-120b.l1-*.json`, `qwen3-coder-30b.l1-*.json`, `nemotron-super.l1-*-trt-1.json`.
- App-repo follow-ups from the external-audit note (README `baseline-v1` → v6; `opencode.json`
  Nemotron mislabeled vLLM) were deferred and, as of this review, still open — now joined by
  the much bigger v4/v6 lineage problem (C1).

---

## 4. Verified correct (what holds up)

- **All headline quality numbers reproduce exactly** from `benchmark-long.csv`: L1 11/29,
  7/29, 6/29; L2 node N=20 0.2517/0.1552, nemotron 0.0086 (N=4); python N=8 0.056/0.000; L3
  0.8926/0.6816/0.6133 at n=512 (all ×512 integral). `benchmark-summary.csv` means match.
- **Statistics library:** Wilson (recomputed, matches to 1e-5), Jeffreys, Clopper–Pearson,
  Chen-et-al pass@k, exact McNemar (correctly *paired* on the shared 29-task set — the external audit
  audit's caution here was already known to be moot), Holm–Bonferroni, inverse-normal — all
  correct; `--selftest` passes.
- **Energy integration** is a true trapezoid over irregular timestamps; counter-vs-gauge usage
  in the Prometheus collector is correct; histogram quantiles use per-bucket window deltas with
  proper +Inf handling; unified-memory measurement correctly sourced from `/proc/meminfo`;
  power/energy capture is runtime-symmetric (same GPU-only nvidia-smi stream for both).
- **L2 canonical denominator** works as designed: exactly 29 checks, non-booting backend scores
  k/29 with `frontend_build`/`lockfile_present` still independently evaluated; the node-17
  missing-layout crash is fixed; the `(npm ci || npm install)` fix is correct and can't be
  gamed (lockfile captured pre-install).
- **L1 mechanics:** the ARM64 shim only corrects swebench's hardcoded x86 arch and defers to the
  official CLI; resume keys prevent double-counting; the aggregator's outcome-only handling
  keeps guard-killed zeros in the denominator (the survivorship fix held).
- **L3 window filter** (`contest_date ≤ 2024-05-31`, inclusive, both passes) and score math
  check out; the two lcb crash patches alter scores only in the intended, disclosed direction
  and apply to all models identically.
- **Serve-manifest bug** from the June notes is fixed (manifests written after sanity
  regardless of PASS/FAIL — though see M16 on the gate being advisory).
- **Reproducibility posture:** raw artifacts + dated findings remain unusually transparent;
  `robust-summary.py` regenerates `l1-run-ledger.csv` byte-identically; vLLM profiles ↔
  registry ↔ vLLM manifests are consistent (TRT side has the M17/C5 gaps).
- **Bucket A was really executed**, not just planned: metric renamed, docs reconciled (README/
  HELP/OVERVIEW/methodology tell one story), causal language stripped from evergreen docs,
  "contamination cancels" removed, failure taxonomy + model-valid rates added, publication
  inputs committed, main pushed.

---

## 5. Metrics review — what the numbers currently support

- **Quality (L1/L2/L3 raw):** internally consistent and reproducible. L1/L2 differences remain
  statistically weak (McNemar p=0.125/0.289/1.0; L2 CIs overlap) — fine for the methodology
  framing, fatal for a ranking framing. C1 caps L2's construct validity at "contract-inference
  from prose," and the k/29 absolute levels should be rescored to k/25 or re-disclosed.
- **L3:** the strongest layer evidentially (n=512, paired set, executed tests), but the
  published nemotron narrative needs the C2 correction, and per-difficulty truncation should be
  reported. A paired bootstrap/permutation over problems (recommended by the external audit,
  functions already exist in `stats.py`) should replace lone Wilson intervals for model
  contrasts.
- **Efficiency:** the weakest pillar. Between C3 (Pareto denominator), C4 (broken L3 energy),
  M7 (restart-truncated windows), M11 (layer pooling), M12 (mean-of-percentiles), M13
  (prompt-token-dominated tok/J), and the structural TRT telemetry gap, **no efficiency figure
  in `reports/charts/` should be published as-is.** Energy-per-task for L1/L2 vLLM runs is
  salvageable (median/IQR, runaway-censored, as `robust-summary.py` already does); L3 energy
  and the pooled efficiency table are not, without recomputation.

---

## 6. Relationship to the external audit

- **Confirmed executed:** its Bucket A items are done and verifiably so (§4).
- **New here, not in external audit:** C1 (invisible contract + v4/v6 lineage break), C2 (conditional-
  rate selection bias + mixed denominator, with corrected paired numbers), C3 (Pareto
  inflation), C4 (broken L3 energy), C5 (invalid TRT manifests), M2/M3 (stale eval report,
  dirty retry workdir), M4 (stale-backend scoring), M5–M7 (L3 cache keying, window-merge
  misalignment, watchdog window overwrite), M9 (model-key split), M10 (L3 actually unseeded),
  M11–M15, M17, and the doc/licensing gaps in §3.
- **an external AI model items still open:** run ledger exists for L1 only (extend to L2/L3); no explicit
  inclusion manifest for analysis (aggregation still consumes every raw dir); container
  digests/dataset checksums not yet pinned as immutable hashes; no clean-clone
  rebuild-every-table command; app-repo README/opencode.json fixes still pending; isolation for
  generated-code execution unchanged (disclosed).
- **One external-audit claim to retire:** its McNemar-misapplication caution was already answered in the
  verification note; this review re-verified the pairing is correct.

---

## 7. arXiv assessment

**As a model-ranking paper: no.** Unchanged from the external audit, and C1 independently sinks
it — Layer 2's absolute scores were produced under a broken information condition.

**As the reframed systems + methodology case study: yes, it is worth publishing — after the
fixes below.** Honest assessment of the contribution:

*What is genuinely valuable (and reasonably novel as a documented case study):*
1. The **GB10/sm_121a serving-feasibility matrix** — no model serves on both runtimes; three
   documented blockers with root causes; NVFP4 MIXED_PRECISION vLLM rejection; MXFP4-via-
   weight-only-Marlin disclosure. Practitioner-useful and not documented elsewhere in one place.
2. The **methodology results**: low-N ranking flips (N=1→8→20 inverting twice), the
   DeepSeek autonomous-tool-use gate (code-gen ≠ agentic competence, with receipts), the
   truncation-artifact analysis (strengthened by C2's per-difficulty and paired-subset
   corrections), infra-vs-model failure taxonomy with model-valid rates, unified-memory
   measurement pitfalls, and — if disclosed candidly — C1 itself as a case study in harness
   construct validity. A paper whose thesis is "at local-eval scale, harness and serving
   effects dominate model effects" is *strengthened* by every finding in this review.
3. **Transparency artifacts**: dated findings, raw retention, deterministic rescoring.

*What limits it:* single box, single run per L1/L3 cell, three configurations, no causal
design — all fine *if* the claims stay descriptive; the evergreen docs now mostly do.
Realistic venue: arXiv (cs.SE, cross-list cs.PF/cs.LG) as a technical report / experience
paper; workshop-paper strength rather than a main-conference empirical paper.

**Gate list before submission (ordered; all are reanalysis/docs except where noted):**
1. Fix C5 (manifest JSON) and regenerate the 10 TRT manifests.
2. Resolve C1: rescore L2 as k/25 (or dual-report k/29 + k/25), re-derive working-app
   flags, write the finding note, fix COVERAGE.md, and fix the app-repo baseline lineage
   (new tag containing the contract) for any future runs.
3. Correct the L3 narrative per C2 (paired-subset table, 185 vs 143 split, per-difficulty
   truncation) everywhere it appears (HELP §6, OVERVIEW §4, findings headline).
4. Rebuild the figures pipeline: C3 denominator, drop/flag the C4 energy cell, un-pool M11,
   add CIs, replace mean-of-percentiles, report J/generated-token alongside tok/J, blank the
   never-captured `mem_util` column, unify the nemotron model key (M9).
5. Reconcile remaining disclosures: L3 unseeded (M10), bwrap claim in HELP §4, models.json
   `shared` block vs TRT reality (M17), publishing-plan rewrite.
6. Add LICENSE + CITATION.cff; remove the stray root JSONs; extend the run ledger to L2/L3;
   pin container digests and dataset checksums; provide the one-command
   rebuild-all-tables entry point.
7. Then write the actual paper (`reports/…report.md` → LaTeX) drawing language *only* from the
   evergreen docs, with the §2 coupling table and every table/figure mapped to a source CSV +
   regeneration command.
8. Optional but high-value if any new compute is spent: L2 rerun with the contract visible
   (turns C1 into a before/after ablation — the single most interesting experiment this
   dataset now suggests), and N≥3 L1 repeats for the significance story.

**Bottom line:** the project clears the "worth publishing on arXiv" bar as a systems +
methodology case study — its raw-artifact transparency is genuinely above the norm for this
genre — but items 1–5 are mandatory first: several of the *published numbers and figures*
(L2 absolute scores, the 85.1% conditional claim, every efficiency chart, the TRT manifests)
are currently wrong or invalid, and an arXiv reader can find each of them the same way this
review did.
