# arXiv paper source

LaTeX source for the preprint *Local Coding-Model Configurations on a Single DGX Spark:
A Systems and Methodology Case Study*.

```
paper/
  main.tex          # the paper (self-contained; inline bibliography, no bibtex needed)
  figures/          # PNGs copied from reports/charts/ + architecture.pdf (vector, Fig 1)
```

## Build

```bash
pdflatex main
pdflatex main        # second pass resolves \ref / \cite numbers
```

No `bibtex`/`biber` run is required — the bibliography is an inline `thebibliography`.
Only standard TeX Live packages are used (graphicx, booktabs, amsmath, hyperref, caption,
microtype). Builds with `pdflatex`, `latexmk -pdf main`, or `tectonic main.tex`.

## Before posting — author checklist

These are the deliberate placeholders you should fill/verify (they're marked with
`% NOTE` / `% VERIFY` comments in `main.tex`):

1. **Author line** (`\author{...}`) — currently `Mani / mani-mal`. Add your display name and
   affiliation if you want one.
2. **References** — every arXiv ID / year / venue is marked `% VERIFY`. An earlier automated
   draft flagged that some precise identifiers can be wrong, so confirm each by hand
   (SWE-bench, LiveCodeBench, vLLM/PagedAttention, Switch Transformers, Wilson, McNemar,
   OpenCode). Add citations for the model cards (gpt-oss, Qwen3-Coder, Nemotron-3-Super) and
   the MXFP4/NVFP4 microscaling formats if you want them.
3. **arXiv categories** — primary `cs.SE`, cross-list `cs.PF`, `cs.LG` (per the publishing plan).
4. The architecture diagram (`figures/architecture.pdf`, a vector export of
   `docs/architecture/benchmark-architecture.drawio`) is included as Figure 1.

## Provenance

Every number in the paper maps to a committed CSV under `results/summary/` and regenerates via
`make rebuild` from the repo root. The prose is drawn from
`reports/dgx-spark-coding-model-benchmark-report.md`, `docs/methodology.md`, and the dated
findings under `docs/findings/`, reconciled with the reviewer round (case-study framing,
version-scoped vLLM claim, disclosed confounds).
