# SmartShop-AI reproducible subset report

> Historical aggregate report. Use [fresh-clone setup](fresh_clone_setup.md) for current CLI arguments and output hand-offs; do not reuse old run paths or report filenames.

Completed at 2026-11-11T05:54:31.624365+00:00 (UTC), algorithm version 1.0.

## Input, output, and preservation

- Original CSV: `<RATINGS_CSV>`.
- Input SHA-256: `2fb7ca7f0931aca31eb00c234d254f7e207dee18c335c9aedce4ff1c23ac96d1`.
- Read-only inspection aggregation: `<INSPECTION_SCRATCH>\aggregation.sqlite3`.
- Aggregation SHA-256: `8ecd93b57de2e99038bc49ce95908c3c3766d3924809c8641c009b771aab23aa`.
- Original CSV size, modification time, and checksum were unchanged; the aggregation checksum was also unchanged.
- Subset CSV: `<PROJECT_ROOT>\data\local\smartshop-seed42-ule7q0db\ratings_subset.csv`.
- Subset SHA-256: `feebd8873792da28db06ba4e370b9757d6eb0c476ebf7f44f6dea7f3fb3b4942`; 9,924,141 bytes (9.46 MiB).
- Aggregate manifest: `<PROJECT_ROOT>\data\local\smartshop-seed42-ule7q0db\manifest.json`.
- Columns remain `user_id`, `parent_asin`, `rating`, `timestamp`. All four field values round-tripped exactly against selected source rows; IDs retain string identity, case, and leading zeros. Ratings and timestamps retain their original text and units. Source record order is preserved. CSV quoting/newlines may differ, so the subset is not a byte-level excerpt of the input.
- The source contains no duplicate pairs. This pipeline refuses duplicate pairs or unexpected ID whitespace instead of silently deduplicating or changing ID meaning.
- Output is under `/data/local/`, explicitly excluded by the root `.gitignore`. The subsetting script runs no Git commands.

## Deterministic sampling and pruning

Seed: **42**. Compute SHA-256 over ASCII seed, one zero byte, and the exact UTF-8 user ID. Interpret the 256-bit digest as an unsigned big-endian integer and retain a user when it is below `floor(fraction * 2**256)`. Fractions and thresholds use integer/rational arithmetic; Python's randomized hash and input enumeration order do not affect selection.

Try 1/16, 1/8, 1/4, 1/2, then 1 until a pruned graph reaches the lower target. If it exceeds the upper target, bisect the exact fraction interval between the latest undershoot and overshoot up to eight times. Choose the first result in the target interval. If no refinement reaches the target, retain the smallest observed viable overshoot; if even the full graph is smaller than the lower target, use the largest available nonempty core. Never cut rows from a converged core merely to hit a size cap.

Within each sample, count distinct pairs using a SQLite primary key. Simultaneously remove users and products with fewer than five distinct neighbors, recompute degrees, and repeat until neither side is deficient. The manifest retains every pruning round. Retained hash samples are nested; the implementation checks that converged-core interaction counts are monotone with the sampling fraction.

Requested target: 100,000–200,000 interactions. Selected fraction: **3/16**. Within target: **True**.

| Fraction | Sampled users | Edges before pruning | Pruning rounds | Retained edges | Retained users | Retained products |
|---|---:|---:|---:|---:|---:|---:|
| 1/16 | 24,022 | 172,897 | 22 | 81 | 16 | 7 |
| 1/8 | 47,916 | 345,617 | 37 | 48,913 | 7,749 | 4,184 |
| 1/4 | 95,598 | 690,864 | 22 | 328,488 | 48,064 | 22,383 |
| 3/16 | 71,835 | 518,027 | 34 | 171,104 | 25,791 | 12,635 |

## Subset statistics

| Measure | Value |
|---|---:|
| Interactions / distinct pairs | 171,104 |
| Unique users | 25,791 |
| Unique products | 12,635 |
| Sparsity: 1 − edges / (users × products) | 99.94749306% |
| Density | 0.05250694% |
| Distinct-neighbor 5-core holds | True |
| Original interactions retained | 6.22% |

| Entity | Minimum | Median | Mean | P90 | P95 | P99 | Maximum |
|---|---:|---:|---:|---:|---:|---:|---:|
| users | 5 | 6.00 | 6.63 | 9 | 11 | 18 | 59 |
| products | 5 | 8.00 | 13.54 | 25 | 39 | 97 | 685 |

| Rating | Subset count | Subset share | Source share |
|---|---:|---:|---:|
| 1 | 12,887 | 7.53% | 8.48% |
| 2 | 8,075 | 4.72% | 5.07% |
| 3 | 12,379 | 7.23% | 7.79% |
| 4 | 22,631 | 13.23% | 13.45% |
| 5 | 115,132 | 67.29% | 65.20% |

## Prospective temporal coverage diagnostics

These are aggregate what-if calculations only. No final evaluation split files, row labels, or user assignments were saved. All diagnostics order integer epoch milliseconds, breaking timestamp ties by source record number; no timestamp field in the export is rewritten.

### Per-user chronological leave-two-out

Hypothesis: reserve each user's latest interaction for test, the previous one for validation, and keep the rest for training. This construction preserves at least three training interactions per retained user, but does not preserve five interactions or product coverage in training.

| Measure | Value |
|---|---:|
| Training / validation / test interactions | 119,522 / 25,791 / 25,791 |
| User training minimum / median | 3 / 4.00 |
| Users without training history | 0 |
| Product training minimum | 0 |
| Products without training history | 189 |
| Products below five training interactions | 4,359 |
| Validation interactions with unseen products | 380 |
| Test interactions with unseen products | 807 |
| Users with timestamp ties across holdout boundaries | 2 |

Per-user chronology does not enforce one common time cutoff: another user's training interaction may occur after a test interaction. Ties resolved by record number are deterministic, not evidence of a real within-timestamp event order. A later evaluation design must explicitly decide how to handle these issues.

### Global chronological 80/10/10

Hypothesis: order all interactions by timestamp and source record number, allocate the first 80% to training, the next 10% to validation, and the rest to test. Validation does not update training history for these diagnostics. Boundary dates are descriptive, not frozen evaluation cutoffs.

| Measure | Value |
|---|---:|
| Training / validation / test interactions | 136,883 / 17,110 / 17,111 |
| User training minimum | 0 |
| Users without training history | 791 |
| Users below three training interactions | 2,890 |
| Product training minimum | 0 |
| Products without training history | 1,623 |
| Products below five training interactions | 3,004 |
| Training boundary (UTC) | 2021-03-16T03:32:11.064000+00:00 |
| Validation boundary (UTC) | 2022-03-25T00:47:41.066000+00:00 |

| Holdout | Interactions | Unseen-user rows | Unseen-product rows | Either unseen | Unique unseen users | Unique unseen products |
|---|---:|---:|---:|---:|---:|---:|
| validation | 17,110 | 1,676 | 4,422 | 5,724 | 462 | 993 |
| test | 17,111 | 3,145 | 9,967 | 11,244 | 663 | 1,568 |

## Selection bias and evaluation limitations

Hash-based user inclusion is deterministic and rating-independent, but the final sample is not a random sample of interactions: all retained histories are clustered by user, then graph pruning favors users and products with sufficient activity and connectivity. Long-tail, new-user, and new-product cases are underrepresented. Sampling-fraction adjustment uses graph size, not model scores or held-out ratings.

Core selection examines the full interaction graph, including events that a future chronological benchmark might hold out. It therefore uses future participation information. This subset is suitable for a retrospective intermediate-level prototype; it is not an unbiased simulation of future deployment. A deployment-oriented benchmark should define cutoffs and eligibility using only data available at the time, then separately report warm-start and cold-start results. Filtering unsupported holdout users/products would inflate apparent coverage; report both excluded counts and overall coverage if such a policy is chosen.

A full-data 5-core does not guarantee adequate training degrees after any split. Do not re-core training and discard difficult held-out cases without recording the resulting population change. Temporal diagnostics do not assess recommendation accuracy. No metadata was downloaded and product-category provenance remains unverified beyond the supplied file and schema.

The source already satisfies 5-core; its upstream filtering history is not independently established. Additional sampling and pruning compound any upstream selection bias. The subset's five-star share is 67.29%, compared with 65.20% in the supplied source, so rating-independent sampling does not imply an unchanged final rating distribution.

## Validation and errors

All **14 synthetic tests passed after creating the subset**. They cover the fixed hash vector and exact threshold boundary, input-order and Python-hash-seed independence, nested samples, deterministic fraction refinement, fallback when the target cannot be met, cascading pruning over multiple rounds, complete collapse, duplicate-pair rejection, ID case/Unicode/leading-zero preservation, unchanged rating/timestamp text, repeated-run subset checksums, refusal to overwrite reports, changed-input detection, ID-normalization refusal, low-disk rejection, closed-console handling, and temporal loss of user/product training coverage despite a full-data five-core.

An independent verification streamed the actual exported CSV, recounted users/products/ratings and distinct pairs, confirmed degree minima and medians, and checked every retained user's seed-42 hash membership. A separate stream over all 2,752,785 source records confirmed that all 171,104 exported records are an exact ordered subsequence of the original field values. Source, aggregation, and subset checksums matched. No retained user or product ID values appeared in the Markdown documentation.

Aggregate verification results and SHA-256 hashes of the implementation and tests are saved in `data/local/smartshop-seed42-ule7q0db/validation.json`. The additional validation took 5.49 seconds and did not create evaluation splits or models.

The first CLI attempt and an outside-sandbox retry returned `PermissionError`. The row-preservation step subsequently succeeded with progress output captured, suggesting an output-pipe issue; the precise OS cause was not established. Progress logging now tolerates `PermissionError`/`BrokenPipeError`, with a regression test. A fresh complete run then succeeded without errors and produced the reviewed CSV and manifest. The earlier attempts were not used as completed subsets.

Final workspace checks found a `.git` directory that was absent from the initial listing for this phase. Its origin is unknown. No Git commands were executed by this workflow, and no `.git` files were edited. Existing Git metadata was left untouched; no claim is made that external Git state remained unchanged during the session.

## Resources, reproducibility, and cleanup

- Python 3.14.7; SQLite 3.50.4; standard library only.
- Runtime: 74.59 seconds.
- Peak working set: 139.85 MiB.
- Free disk before: 27,066.96 MiB. Conservative reservation: 1,041.61 MiB.
- Retained scratch: 107.93 MiB at `<TEMP_SCRATCH_DIR>`.
- Output CSV size: 9.46 MiB; manifest size is additional.
- Streaming uses 10,000-row batches plus a retained-user membership set. Main and attached SQLite page cache budgets are 32 MiB each; these are not process memory limits. SQLite sorting is disk-backed in the dedicated scratch directory. Retained disk sizes exclude transient sort files and rollback journals, so they are not exact peak disk measurements.

Rerun from the project root, with a new report filename:

```powershell
python3.14 -I -B scripts/create_subset.py --dataset "<RATINGS_CSV>" --inspection-summary "<INSPECTION_SCRATCH>\summary.json" --aggregation "<INSPECTION_SCRATCH>\aggregation.sqlite3" --report docs/subset_report_rerun.md
python3.14 -I -B -m unittest discover -s tests -p test_create_subset.py -v
```

Every run creates new unique output and scratch directories and refuses to overwrite an existing report. Reproducibility is defined by identical input bytes, script version, seed, exact fraction-selection policy, and subset checksum, not by randomly generated directory names or runtime measurements. A manifest with `status: complete` is written only after export, graph, and input-integrity checks pass.

The inspection aggregation is reused read-only and is never removed by this script. Scratch is retained for review and contains source identifiers. After review, cleanup may remove only the exact owned scratch directory above, after resolving its absolute path and verifying it is under the intended temporary parent and outside the workspace. Do not delete the temporary parent or use wildcards. Preserve the subset CSV and manifest for subsequent approved phases. Synthetic test directories are separate, verified descendants of the OS temporary directory and are cleaned by the tests themselves.

The first attempt also owns these retained artifacts:

- `<TEMP_SCRATCH_DIR>`: a 107.93 MiB diagnostic/working database containing identifiers, not a completed exported subset. Apply the same exact-directory and temporary-parent checks before later cleanup.
- `data/local/smartshop-seed42-9uvhm6us`: an empty, ignored directory with no completion manifest. If removing it after review, first resolve its absolute path and verify it is this exact directory beneath the intended `data/local` parent; an ordinary empty-directory removal is sufficient.

No existing data or scratch files were overwritten or deleted. The original inspection scratch directory is distinct from both subsetting directories and remains intact. The completed run's retained disk size above excludes the earlier attempt's separate working database.

No final evaluation split, model, frontend, backend, package installation, metadata download, or Git initialization/configuration/commit/push is part of this phase. Stop for review before later phases.
