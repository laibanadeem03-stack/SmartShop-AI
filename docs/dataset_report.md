# SmartShop-AI dataset inspection

> Historical aggregate report. Use [fresh-clone setup](fresh_clone_setup.md) for current CLI arguments and output hand-offs; do not reuse old run paths or report filenames.

Inspection completed at 2026-11-11T05:27:54.306083+00:00 (UTC).

## Source and reproducibility

- Source: `<RATINGS_CSV>`; retained outside this project.
- Size: 159,665,421 bytes (152.27 MiB).
- SHA-256: `2fb7ca7f0931aca31eb00c234d254f7e207dee18c335c9aedce4ff1c23ac96d1`.
- Source modification time: 2026-11-11T05:13:45.661556+00:00.
- Source was opened only for reading. Size and modification time were unchanged at completion.
- Python 3.14.7; SQLite 3.50.4.
- Interpreter: `<PYTHON_3_14_EXE>`.
- Runtime: 63.75 seconds, including the checksum pass.
- Workspace was empty before this task; no existing project configuration or AGENTS.md was present.
- The `python` and `py` WindowsApps aliases failed to launch; `python3.14` worked.

Re-run from the project directory with an unused output filename:

```powershell
python3.14 -I -B scripts/inspect_ratings.py --dataset "<RATINGS_CSV>" --report docs/dataset_report_rerun.md
```

## Method and definitions

The standard-library CSV reader streams UTF-8 records; a separate bounded binary pass calculates SHA-256. SQLite aggregates exact counts in batches. No Pandas, NumPy, package installation, network access, model training, or subset export is involved. IDs are trimmed and compared case-sensitively as strings.

- **Raw:** all parsed data records, excluding the header. Raw entity/degree and pair aggregates use structurally correct rows and available nonmissing IDs, irrespective of rating validity. Missing counterpart IDs can make raw user and product degree totals differ from raw record totals.
- **Valid:** structurally correct rows with both IDs present and a finite numeric rating in [1, 5]. Timestamp validity is reported separately and does not exclude an otherwise usable rating.
- **Deduplicated:** one edge per valid user-product pair. This inspection counts those edges without selecting a surviving rating, producing a subset, or assigning a deduplicated rating distribution.
- Missing values include whitespace-only/absent cells and case-insensitive null, none, NA, N/A, and NaN markers. Row shape, missing-value, and invalid-value counts may overlap.
- Percentiles use nearest rank; the median averages the middle two values when necessary.

## Schema and data quality

The CSV has a header and four comma-separated columns. No title, description, category, price, or review text column is present.

| Column | Blank/absent | Null markers | Total missing |
|---|---:|---:|---:|
| user_id | 0 | 0 | 0 |
| parent_asin | 0 | 0 | 0 |
| rating | 0 | 0 | 0 |
| timestamp | 0 | 0 | 0 |

| Quality check | Count |
|---|---:|
| records | 2,752,785 |
| well_formed | 2,752,785 |
| malformed_width | 0 |
| valid | 2,752,785 |
| missing_user | 0 |
| missing_product | 0 |
| missing_rating | 0 |
| nonnumeric_or_nonfinite_rating | 0 |
| rating_outside_1_to_5 | 0 |
| fractional_ratings | 0 |
| missing_timestamp | 0 |
| invalid_timestamp | 0 |

Timestamp unit counts: {"milliseconds": 2752785}.
Timestamp range (UTC): 2003-05-07T18:52:41+00:00 to 2023-09-06T00:18:04.465000+00:00.
Epoch integers with absolute magnitude at least 100,000,000,000 are interpreted as milliseconds; smaller integers as seconds. This is a heuristic, not metadata supplied by the CSV.

## Interaction counts and 5-core verification

| Stage | Interactions | Unique users | Unique products | Users below 5 | Products below 5 | 5-core holds |
|---|---:|---:|---:|---:|---:|---|
| raw | 2,752,785 | 380,999 | 111,480 | 0 | 0 | Yes |
| valid | 2,752,785 | 380,999 | 111,480 | 0 | 0 | Yes |
| deduplicated | 2,752,785 | 380,999 | 111,480 | 0 | 0 | Yes |

Raw and valid 5-core checks count rows, including repeat pairs. The deduplicated check requires five distinct products per user and five distinct users per product. No iterative core pruning was performed; these checks describe the complete supplied graph.

## Interactions per user and product

| Stage | Entity | Min | Median | Mean | P90 | P95 | P99 | Max | At least 5 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| raw | users | 5 | 6.00 | 7.23 | 11 | 14 | 23 | 294 | 380,999 |
| raw | products | 5 | 10.00 | 24.69 | 46 | 78 | 241 | 6,188 | 111,480 |
| valid | users | 5 | 6.00 | 7.23 | 11 | 14 | 23 | 294 | 380,999 |
| valid | products | 5 | 10.00 | 24.69 | 46 | 78 | 241 | 6,188 | 111,480 |
| deduplicated | users | 5 | 6.00 | 7.23 | 11 | 14 | 23 | 294 | 380,999 |
| deduplicated | products | 5 | 10.00 | 24.69 | 46 | 78 | 241 | 6,188 | 111,480 |

## Rating distribution

| Rating | Raw numeric rows | Valid rows | Share of valid rows |
|---|---:|---:|---:|
| 1 | 233,527 | 233,527 | 8.48% |
| 2 | 139,612 | 139,612 | 5.07% |
| 3 | 214,488 | 214,488 | 7.79% |
| 4 | 370,293 | 370,293 | 13.45% |
| 5 | 1,794,865 | 1,794,865 | 65.20% |

## Duplicate user-product interactions

| Stage | Distinct pairs | Pairs occurring more than once | Excess rows | Maximum multiplicity |
|---|---:|---:|---:|---:|
| raw | 2,752,785 | 0 | 0 | 1 |
| valid | 2,752,785 | 0 | 0 | 1 |

Deduplicated edges have zero repeated pairs by definition. This checks repeated user-product interactions, not byte-identical source records or rating conflicts.

## Memory and disk

| Measurement or estimate | MiB |
|---|---:|
| Observed process lifetime peak working set | 95.09 |
| Working set after aggregation | 27.38 |
| Configured SQLite cache budget (not a process memory limit) | 32.00 |
| Estimated full list of Python string rows | 824.33 |
| Estimated object-ID dataframe with float64 rating/int64 timestamp | 399.04 |
| Deduplicated CSR payload: float32 values/int32 indexes | 22.46 |
| Deduplicated COO payload: float32 values/int32 coordinates | 31.50 |
| Hypothetical dense float32 user-product matrix | 162,024.57 |
| Retained SQLite database | 173.07 |
| Largest scratch size observed at batch/phase boundaries | 173.07 |

Batch size: 10,000 records; maximum distinct pairs in a batch: 10,000. In-memory estimates use the first 10,000 well-formed rows and CPython object sizes. They are planning estimates, not measured Pandas allocations. The dataframe estimate assumes independently allocated ID strings, two object pointers, and two 8-byte numeric columns. Parser temporaries, indexes, allocator overhead, model workspaces, and string-interning/categorical savings are excluded. Sparse estimates exclude ID maps and model overhead. Never build the dense matrix.

SQLite sorting uses disk-backed temporary storage in the dedicated scratch directory. Boundary disk measurements exclude short-lived internal sort files already removed by SQLite; they are not an exact peak disk measurement. Allow several times the source size in free scratch space for reruns. Journal and synchronous writes are disabled only for the disposable scratch database; interrupted runs are not resumable.

## Recommended subset (proposal only)

Use all valid interactions to form the deduplicated graph before sampling. Deduplicate by the latest valid timestamp, with source record number as a deterministic tie-breaker. Prefer valid timestamps over missing ones; if all timestamps for a pair are missing, choose the last source record. The present dataset has no repeated pairs or missing timestamps, so that policy would not discard any rows.

The full deduplicated graph already satisfies the distinct-neighbor 5-core property: 2,752,785 edges, 380,999 users, and 111,480 products. Initial five-neighbor pruning would remove nothing. Sampling can break this property, so the sampled graph still needs iterative pruning.

Target roughly 100,000–300,000 deduplicated interactions initially, subject to the surviving core. Select users by a fixed-seed SHA-256 hash threshold (never Python's randomized hash), retain their interactions, and repeat the five-neighbor pruning to convergence. Test a predeclared sequence of increasing sampling fractions, starting at 1/16 and doubling through the complete core, if the result is too small or collapses. Use seed 42: hash the UTF-8 bytes of `42`, a zero byte, and the normalized user ID; interpret the SHA-256 digest as an unsigned big-endian integer and retain it below `fraction * 2**256` using exact integer arithmetic. Record every attempted fraction and output graph statistics. The target is a sizing goal, not a guaranteed feasible size; prefer a viable larger core over an arbitrary row cap. No subset was created in this task.

At 1/16, the expected interaction count before pruning is about 172,049; the realized size and surviving core are unmeasured. Since the median user has only six distinct products, losing a few neighbors may remove many users. Do not promise that a small sampled 5-core will survive. If every small fraction fails the activity/size checks, retain a larger core. The full graph's approximately 22.46 MiB CSR payload also makes it a possible fallback for later memory-aware experiments, although model and identifier-map memory will be larger.

Freeze the subset specification with the source checksum, schema, normalization rules, deduplication order, seed, sampling fraction, pruning threshold, algorithm version, and final counts. Keep outputs outside Git. Use the deduplicated graph statistics above to judge activity; raw row counts can overstate usable history.

For evaluation, reserve one latest interaction for validation and one for test for eligible users, keeping at least three training interactions for users with five neighbors. Fit popularity counts, similarity indexes, and hybrid weights only using their designated training/validation data. Report products absent from training as cold-start cases. Global core selection uses the full graph, so label this a retrospective benchmark; it does not by itself establish future deployment performance.

## Metadata matching

Join future metadata on `parent_asin`, preserving string values and identifier granularity. A child/variant ASIN is not automatically equivalent to a parent ASIN. Confirm the matching metadata release and category from its documentation before acquiring anything: the local filename alone does not prove provenance. Enforce one metadata row per parent key or explicitly consolidate duplicates before joining. Measure coverage of unique products and interactions, check unmatched keys, and prevent joins from multiplying rows. Titles, descriptions, and categories may support TF-IDF later; they are absent from this CSV. Metadata availability, licensing, identifier compatibility, and completeness have not been verified. Nothing was downloaded.

## Scratch isolation and cleanup

This run owns the newly created directory `<INSPECTION_SCRATCH>`. It is outside the workspace and contains `aggregation.sqlite3` (including identifiers) and an aggregate-only `summary.json`. No pre-existing scratch file was reused or overwritten. Treat the database as local data, never as a repository artifact.

Scratch files are retained for review; this task did not delete them. After review, cleanup may remove only this exact directory after resolving its absolute path, confirming it is under the intended temporary parent and outside the workspace, and checking its contents. Do not use wildcards or delete the temporary parent. Cleanup is ordinary file deletion, not secure erasure. If interrupted, the script prints its owned scratch path so the same checks can be applied to that incomplete run.

The small synthetic validation also created two owned directories under the same temporary parent:

- `<TEMP_SCRATCH_DIR>`: synthetic CSV fixtures, a fixture report, and its `core-scratch` subdirectory.
- `<INSPECTION_SCRATCH>`: the synthetic fixture's aggregation database and summary.

These contain synthetic test identifiers only and are also retained for review. Apply the same exact-directory checks before any later cleanup. No original CSV was copied into them.

## Validation and errors

Synthetic fixtures checked exact raw/valid/deduplicated counts, repeated-pair counting, missing and invalid values, median calculation, epoch seconds and milliseconds, both passing and failing 5-core graphs, source size/mtime stability, report omission of fixture IDs, and refusal to overwrite an existing report. The actual run also checked agreement between user totals, product totals, pair totals, and duplicate excess counts. A final independent read-only SHA-256 pass matched the original inspection checksum, and source size/modification time remained unchanged. All checks passed.

The `python` and `py` executable aliases failed with "The file cannot be accessed by the system." The working `python3.14` interpreter completed inspection without installation or configuration changes. The full dataset run completed without errors. No subset, models, frontend, backend, or Git configuration was created or changed.

## Limitations

No provenance or category membership verification, metadata inspection, row-level duplicate conflict audit, rating-survivor selection, iterative core extraction, subset feasibility experiment, model fitting, or recommendation evaluation was performed. Identifier semantics are inferred from the provided column names. Missingness counts detect the documented markers rather than every possible sentinel. Memory estimates are sample-dependent. The source checksum plus unchanged size/mtime supports reproducibility but does not provide a transactional snapshot against concurrent external modification. Reports contain aggregate statistics and column names only, without raw records or user/product ID values.

See `docs/project_plan.md` for the proposed development phases. All later implementation and data acquisition remain subject to review; this task ends after inspection and planning.
