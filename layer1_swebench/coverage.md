# Layer 1 ARM64 coverage

- Dataset: `princeton-nlp/SWE-bench_Verified` (500 tasks; x86-64 official images).
- Host arch: aarch64 (GB10).
- Probed 43 tasks by running their GOLD patch through the official
  evaluation on this host; 29 built and resolved on ARM64.
- **Reported results use only the disclosed ARM64-buildable subset** — call it
  'pass rate on the disclosed 29-task ARM64-buildable subset', NOT
  SWE-bench Verified performance. Same tasks run on identical hardware, but equal
  task exposure does NOT mean contamination cancels: per-model training corpora and
  dedup differ, so memorization can differ on the same tasks. The subset is disclosed
  here, not silently truncated; treat cross-model gaps as descriptive.
