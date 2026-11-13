# SmartShop-AI item-based collaborative filtering results

> Historical aggregate report. Use [fresh-clone setup](fresh_clone_setup.md) for current CLI arguments and output hand-offs; do not reuse old run paths or report filenames.

Best CF configuration: **item_cf_k50_lambda10**, selected using validation macro NDCG@10 only.
Validation-selected project default: **item_cf_k50_lambda10**.

## Environment and inputs

- Python 3.14.7; NumPy 2.5.3; SciPy 1.18.1.
- Isolated interpreter: `<PROJECT_ROOT>\.venv\Scripts\python.exe`. Global site-packages are not inherited.
- Root `.gitignore` excludes `.venv/` and `data/local/`. Venv exclusion was confirmed before installation; both exclusions were verified afterward.
- Only NumPy and SciPy were installed, using pinned binary wheels and no dependency additions. Pip is the venv's bundled installer.
- Imports, sparse arithmetic, and `pip check` passed. The initial sandbox blocked PyPI sockets; an approved network escalation completed the same two-package installation.
- Reused evaluation directory: `<PROJECT_ROOT>\data\local\evaluation-ej957b9_`.
- Split manifest SHA-256: `ca61c0253b36f345c029b72532a964c88add44a3a236ad5082acd51e435f716a`.
- Existing subset and train/validation/test partitions were not modified. Their checksums and modification times were verified. The original downloaded CSV was never accessed.

## Method and leakage controls

Only training 4–5 star observations enter the binary sparse positive matrix. Ratings 1–3 do not seed recommendations; all ratings remain in seen-item histories. Minimum shared positive-user support is two. Similarity is positive cosine multiplied by c/(c+lambda). Diagonal links are removed before row-wise top-K selection. Similarities are stored as float32 with deterministic original-ID tie ordering. The graph can be directional after top-K pruning.

Sparse co-occurrence is computed in blocks of at most 128 item rows. No full dense item-item or user-item prediction matrix is constructed. K=20 lists reuse the first 20 entries of the correctly sorted K=50 graph for the same shrinkage. Training seed profiles, graph statistics, and count fallback remain frozen. Validation history changes only the test seen mask. User scores sum neighbors of their positive training seeds; ties use training count then original product ID. Unsupported candidates have zero CF score and remain eligible for count-popularity backfill.

Training: 136,883 interactions, 110,964 positives, 25,000 users, 11,012 products. Users without positive training seeds: 442.

## Validation comparison

All metrics use a 0–1 scale. Personalized-user and fallback-slot percentages include all holdout users, including users without positive targets.

| Model | Recall@10 | NDCG@10 | Catalog coverage | Users personalized | Fallback slots |
|---|---:|---:|---:|---:|---:|
| count | 0.00672564 | 0.00389604 | 0.00118053 | 0.00% | 100.00% |
| item_cf_k20_lambda0 | 0.00934144 | 0.00553820 | 0.32864148 | 83.91% | 30.43% |
| item_cf_k20_lambda10 | 0.01045026 | 0.00653590 | 0.30948057 | 83.91% | 30.43% |
| item_cf_k50_lambda0 | 0.00947000 | 0.00564461 | 0.32973120 | 83.91% | 30.43% |
| item_cf_k50_lambda10 | 0.01049311 | 0.00657693 | 0.30938976 | 83.91% | 30.43% |

Exact CF NDCG ties prefer K20/lambda0, K20/lambda10, K50/lambda0, then K50/lambda10. The best CF configuration is locked before test bytes are read. Count remains the recommended default unless CF strictly improves validation NDCG. Both the locked CF method and count are tested for the predeclared comparison; test does not change selection.

## Test comparison

| Model | Recall@10 | NDCG@10 | Catalog coverage | Hits | Users personalized | Fallback slots |
|---|---:|---:|---:|---:|---:|---:|
| count | 0.00345062 | 0.00195011 | 0.00136215 | 48 | 0.00% | 100.00% |
| item_cf_k50_lambda10 | 0.00494735 | 0.00300261 | 0.30566655 | 64 | 79.92% | 34.22% |

| Metric | CF minus count | Relative change |
|---|---:|---:|
| recall_at_10 | 0.00149673 | 43.38% |
| ndcg_at_10 | 0.00105250 | 53.97% |
| catalog_coverage_at_10 | 0.30430440 | 22340.00% |

Differences are descriptive point estimates; no statistical-significance claim is made.

## Warm-start and cold-start results

Known users/products have at least one training interaction. Segment targets include only positives in that segment, so user counts overlap across product segments. Overall metrics include every positive target, including unreachable products. No second five-core filter or negative sampling is applied.

### Validation

Positive users: 7,779; no-positive users: 1,624. Positive-target reachability: 73.89%. Users receiving fewer than ten recommendations: 0.

| Segment | Positive users | Positive targets | Recall@10 | NDCG@10 |
|---|---:|---:|---:|---:|
| warm_user_warm_product | 5,891 | 8,726 | 0.01426033 | 0.00865048 |
| cold_user_warm_product | 392 | 1,063 | 0.01194838 | 0.00821663 |
| warm_user_cold_product | 2,578 | 3,158 | 0.00000000 | 0.00000000 |
| cold_user_cold_product | 194 | 301 | 0.00000000 | 0.00000000 |

Personalized users: 7,890/9,403; personalized slots: 65,414; fallback slots: 28,616/94,030.

### Test

Positive users: 6,839; no-positive users: 1,427. Positive-target reachability: 40.98%. Users receiving fewer than ten recommendations: 0.

| Segment | Positive users | Positive targets | Recall@10 | NDCG@10 |
|---|---:|---:|---:|---:|
| warm_user_warm_product | 3,344 | 4,463 | 0.01070610 | 0.00597810 |
| cold_user_warm_product | 446 | 1,090 | 0.00813848 | 0.00680627 |
| warm_user_cold_product | 4,114 | 6,372 | 0.00000000 | 0.00000000 |
| cold_user_cold_product | 531 | 1,626 | 0.00000000 | 0.00000000 |

Personalized users: 6,606/8,266; personalized slots: 54,372; fallback slots: 28,288/82,660.

Cold users and users without useful seeds/neighbors receive count fallback. Cold products cannot be scored by this frozen collaborative graph; their positives remain zero-hit cases. Validation-only users remain cold relative to training even when their past validation interactions enter the test exclusion mask.

## Runtime, memory, and model artifacts

- Total pipeline time: 9.372 seconds, excluding final result/report writes.
- Training ingestion: 1.260 seconds.
- Process peak working set: 125.86 MiB.
- Positive matrix array payload: 0.942 MiB.
- Retained artifact files before result/report: 42.59 MiB.
- Run directory: `<PROJECT_ROOT>\data\local\item_cf-gm9467qd`.

| Graph | Edges | Zero-neighbor items | Array payload MiB | Compressed file MiB | Largest block nonzeros | Max-K build seconds |
|---|---:|---:|---:|---:|---:|---:|
| item_cf_k20_lambda0 | 16,293 | 6,760 | 0.166 | 0.077 | 9,012 | 0.175 |
| item_cf_k50_lambda0 | 19,377 | 6,760 | 0.190 | 0.090 | 9,012 | 0.175 |
| item_cf_k20_lambda10 | 16,293 | 6,760 | 0.166 | 0.079 | 9,012 | 0.170 |
| item_cf_k50_lambda10 | 19,377 | 6,760 | 0.190 | 0.091 | 9,012 | 0.170 |

K20 rows reuse their same-shrinkage K50 build; those build timings are shared, not additive. Compressed file size differs from in-memory array payload. Reported retained disk usage is not exact peak disk usage.

## Integrity, limitations, and review

All **50 synthetic tests passed after the real run**, including the original 33 regression tests and 17 CF tests. The final suite took 1.365 seconds. Tests cover cosine arithmetic, shrinkage, shared-user filtering, co-rater counts above 255, zero vectors, ID preservation, deterministic top-K/ties, directional pruning, block-size invariance, dense-conversion prohibition, sparse artifact round-trips, cold fallback, seen exclusions, future-row rejection, frozen profiles, callback validation, unchanged popularity metrics, and selection before test reads. The isolated environment's final `pip check` again reported no broken requirements.

An independent audit verified all positive profiles and every neighbor row for all four configurations using row-local shared-user counters, without allocating a full item-item matrix. It recomputed all exported recommendations, CF/fallback source labels and usage totals, and overall plus four-way segment metrics for all validation candidates and both test models. Metrics matched within absolute tolerance 1e-14; support-filtered neighbor scores matched within 1e-7. The audit took 10.16 seconds in a separate process and is saved as aggregate-only `audit.json` in the ignored run directory. No dataset IDs were found in tracked Markdown documentation.

Final environment checks confirmed global NumPy remained at 2.5.3 and SciPy was absent from global Python. The venv contains only NumPy, SciPy, and its bundled pip. The original full CSV and company projects were not accessed. The only recovered setup error was the initial sandbox network block; no model or test failures occurred.

Count-popularity validation/test cohort metrics, every segment metric, and prediction CSV checksums exactly reproduce the previous baseline. Frozen training snapshot, positive matrix, and all neighbor graph fingerprints were unchanged after validation/test. Existing subset and splits retained their original checksums and modification times.

The evaluator changed only its recommendation hook, list validation, and optional CF-source column; existing count prediction format and metric definitions remain unchanged. CF prediction files label collaborative versus popularity-fallback slots. Model arrays, original string-ID mappings, environment metadata, selection, predictions, aggregate results, and code checksums are under the ignored run directory. Tracked documentation contains no dataset identifiers.

Retrospective five-core selection uses future participation and favors connected users/products. Sparse overlaps, short histories, popularity backfill, and the long frozen-catalog horizon remain limitations. Ratings 1–2 are not used as positive seeds and are excluded as seen, but do not generate negative-neighbor penalties. This method cannot recover unseen products without a separate content/catalog policy. Higher offline accuracy or coverage is not proof of online benefit.

The selected graph has 6,760 items with no supported outgoing neighbors, including 80 items with no positive training ratings. Relative test gains are 43.38% Recall and 53.97% NDCG, but absolute Recall remains 0.00494735, with 64 positive hits versus 48 for count. Interpret the larger catalog spread alongside these modest absolute hit counts; no significance test or online experiment was performed.

See `docs/item_cf_strategy.md` for reproducibility commands and cleanup. No original CSV access, metadata acquisition, content/hybrid model, frontend/backend, global Python modification, or Git configuration/remote/commit/push operation is part of this implementation. Stop for review.
