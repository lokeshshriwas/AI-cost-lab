# Spend log

Monthly API credit: $40 (Team plan, 2 Standard seats). Expires each billing cycle, no rollover.
Auto-reload: OFF. Workspace: `ai-cost-lab` (API keys must be workspace-scoped in this org).

| Date | What ran | Model(s) | Cost (USD) | Month total |
| --- | --- | --- | --- | --- |
| 2026-11-01 | Phase 1 cache check (1 real call, 21 in / 7 out tokens) | claude-haiku-5-5 | 0.000006 | 0.000006 |
| 2026-11-01 | Phase 2 smoke run: extraction, 5 tasks (`costlab run --limit 5 --mode record`, run 1) | claude-haiku-5-5 | 0.000457 | 0.000463 |
| 2026-11-01 | Phase 2 smoke run: qa, 5 tasks (run 2) | claude-haiku-5-5 | 0.000726 | 0.001189 |
| 2026-11-01 | Phase 2 smoke run: codefix, 5 tasks (run 3) | claude-haiku-5-5 | 0.000188 | 0.001377 |
| 2026-11-01 | Phase 2 full baseline: extraction 50, qa 50, codefix 30 (runs 4-6). Run totals $0.011999; the first 5 tasks per workload replayed from the smoke cache ($0.001371, not re-billed) | claude-haiku-5-5 | 0.010628 | 0.012005 |
| 2026-11-01 | Phase 3 smoke runs: prompt-caching, trim-context, low-effort, cascade x 3 workloads, 5 tasks (runs 7-18); 35 new calls, rest replayed | claude-haiku-5-5 | 0.002351 | 0.014356 |
| 2026-11-01 | Phase 3 full runs: same 4 strategies x 3 workloads (runs 19-30); 278 new calls. Haiku $0.019179, Sonnet (4 cascade escalations) $0.007402 | claude-haiku-5-5, claude-sonnet-5-5 | 0.026581 | 0.040937 |
| 2026-11-01 | Phase 3 caching+low-effort smoke (runs 34-36, 15 new calls) | claude-haiku-5-5 | 0.000903 | 0.041840 |
| 2026-11-01 | Phase 3 caching+low-effort full (runs 37-39, 115 new calls) | claude-haiku-5-5 | 0.006485 | 0.048325 |
| 2026-11-01 | Phase 3 batch smoke, extraction, 5 tasks (msgbatch_01UiUwSbaQPEpoDeXZEJCh3J; job was killed for low memory before collecting, results recovered with `import_batch`, replayed as run 40) | claude-haiku-5-5 | 0.000228 | 0.048553 |
| 2026-11-01 | Phase 3 caching+low-effort --batch: smoke qa + codefix, full extraction + qa + codefix (runs 41-45, 125 new calls, all at batch price) | claude-haiku-5-5 | 0.003355 | 0.051908 |
| 2026-11-04 | Gate 4 batch repeats: caching+low-effort --batch repeat1 codefix (run 54), repeat2 extraction (62), qa (msgbatch_018Qom24ME8GuaTKB3UqtxYF, collected after a network drop with `import_batch`, replayed as run 68), codefix (71) | claude-haiku-5-5 | 0.004852 | 0.083187 |
| 2026-11-04 | Model comparison: Sonnet 5.5 smoke + full baseline, 3 workloads (runs 55-57, 61, 63, 64) | claude-sonnet-5-5 | 0.202288 | 0.285475 |
| 2026-11-04 | Model comparison: Opus 5.5 smoke + full baseline (runs 58-60, 65; qa and codefix re-run as 69, 70 after 66 tasks hit connection errors; errored calls were not billed) | claude-opus-5-5 | 0.471220 | 0.756695 |
| 2026-11-01 | Gate 4 repeat runs (fresh calls, `--repeat-tag`): baseline repeat1 + repeat2 on all 3 workloads (runs 46-51); caching+low-effort --batch repeat1 on extraction (run 52) and qa (msgbatch_019RhW1NFqxDux89kvcwsTce, collected after a network drop with `import_batch`, replayed as run 53). Codefix batch failed before sending (no charge) | claude-haiku-5-5 | 0.026427 | 0.078335 |
