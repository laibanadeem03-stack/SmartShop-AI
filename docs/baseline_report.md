# SmartShop-AI popularity baseline results

> Historical aggregate report. Use [fresh-clone setup](fresh_clone_setup.md) for current CLI arguments and output hand-offs; do not reuse old run paths or report filenames.

Selected baseline: **count**, chosen solely by overall validation macro NDCG@10.

## Data integrity and protocol

- Prepared subset SHA-256: `feebd8873792da28db06ba4e370b9757d6eb0c476ebf7f44f6dea7f3fb3b4942`.
- The selected subset and its manifest were unchanged. The full downloaded CSV was not accessed.
- Every partition row round-tripped all four original field values. Ratings, string IDs, timestamps, and within-partition source order were preserved. The partitions reconstruct every subset record exactly once.
- Fixed UTC millisecond cutoffs: training through 2021-03-16T03:32:11.064Z; validation through 2022-03-25T00:47:41.066Z; remaining rows are test. Equal timestamps stay together.
- Training: 136,883 interactions, 25,000 users, 11,012 products; mean rating 4.29717350.
- Counts, priors, and scores were fit on training only and fingerprinted before and after evaluation. Validation selects the method and prior strength; it updates only the seen mask before test. Test does not update scores or select parameters. The selection artifact was saved before loading test for ranking evaluation.

| Partition | Interactions | Users | Products | Relevant interactions (4–5 stars) |
|---|---:|---:|---:|---:|
| train | 136,883 | 25,000 | 11,012 | 110,964 |
| validation | 17,110 | 9,403 | 4,540 | 13,248 |
| test | 17,111 | 8,266 | 4,038 | 13,551 |

## Validation comparison

| Candidate | Recall@10 | NDCG@10 | Catalog coverage@10 | Positive users | Hits |
|---|---:|---:|---:|---:|---:|
| count | 0.672564% | 0.389604% | 0.118053% | 7,779 | 101 |
| quality_m10 | 0.625744% | 0.295625% | 0.118053% | 7,779 | 92 |
| quality_m5 | 0.625744% | 0.292561% | 0.118053% | 7,779 | 92 |
| quality_m20 | 0.625744% | 0.295625% | 0.118053% | 7,779 | 92 |

Exact NDCG ties prefer count, quality_m10, quality_m5, then quality_m20. Selection uses full-precision metrics, not rounded table values. Count is a selectable candidate, not only a control.

## Test comparison

Only the validation-selected baseline and the predeclared count control were evaluated on test.

| Candidate | Recall@10 | NDCG@10 | Catalog coverage@10 | Positive users | Hits |
|---|---:|---:|---:|---:|---:|
| count | 0.345062% | 0.195011% | 0.136215% | 6,839 | 48 |

Count popularity had strictly higher validation NDCG than every smoothed candidate, so the final baseline is the simple count ranking. The best smoothed validation NDCG was 24.12% lower than count. No improvement over count is claimed. Unselected smoothed variants were not evaluated on test; their test performance is unknown.

| Test measure | Selected minus count | Relative change |
|---|---:|---:|
| recall_at_10 | 0.0000000000 | 0.000000% |
| ndcg_at_10 | 0.0000000000 | 0.000000% |
| catalog_coverage_at_10 | 0.0000000000 | 0.000000% |

Differences are descriptive point estimates; no statistical-significance claim is made.

## Warm-start and cold-start coverage

Known means at least one interaction in the frozen training snapshot. User counts can overlap between product segments when a user has both known and unknown positive targets. Overall metrics include cold targets in their denominators. All training-observed products remain eligible; there is no new five-core filter.

Across the complete prepared subset, **791 users and 1,623 products have no training interactions**. Window-specific counts below include all rating levels; the positive-user column is the subset of those cold users with at least one 4–5 star target.

| Window | Users without training history | Distinct products without training history | Positive users without training history | Positive cold-product targets |
|---|---:|---:|---:|---:|
| validation | 462 | 993 | 433 | 3,459 |
| test | 663 | 1,568 | 633 | 7,998 |

### Validation selected-baseline segments

Window users: 9,403; positive users: 7,779; users without positive targets: 1,624. Users receiving fewer than ten recommendations: 0.

Positive-target reachability in the frozen catalog after seen filtering: 9,789/13,248 (73.890399%). This is interaction-weighted, while Recall/NDCG are user-macro averages.

| Segment | All-rating rows | Positive targets | Positive users | Recall@10 | NDCG@10 |
|---|---:|---:|---:|---:|---:|
| warm_user_warm_product | 11,386 | 8,726 | 5,891 | 0.936868% | 0.509379% |
| cold_user_warm_product | 1,302 | 1,063 | 392 | 1.194838% | 0.821663% |
| warm_user_cold_product | 4,048 | 3,158 | 2,578 | 0.000000% | 0.000000% |
| cold_user_cold_product | 374 | 301 | 194 | 0.000000% | 0.000000% |

| Training-user history | Positive users | Recall@10 | NDCG@10 |
|---|---:|---:|---:|
| history_0 | 433 | 0.839207% | 0.629243% |
| history_1_2 | 1,482 | 0.714768% | 0.489725% |
| history_3_4 | 3,153 | 0.621381% | 0.312859% |
| history_5_plus | 2,711 | 0.682405% | 0.385853% |

### Test selected-baseline segments

Window users: 8,266; positive users: 6,839; users without positive targets: 1,427. Users receiving fewer than ten recommendations: 0.

Positive-target reachability in the frozen catalog after seen filtering: 5,553/13,551 (40.978526%). This is interaction-weighted, while Recall/NDCG are user-macro averages.

| Segment | All-rating rows | Positive targets | Positive users | Recall@10 | NDCG@10 |
|---|---:|---:|---:|---:|---:|
| warm_user_warm_product | 5,867 | 4,463 | 3,344 | 0.730163% | 0.354583% |
| cold_user_warm_product | 1,277 | 1,090 | 446 | 0.813848% | 0.680627% |
| warm_user_cold_product | 8,099 | 6,372 | 4,114 | 0.000000% | 0.000000% |
| cold_user_cold_product | 1,868 | 1,626 | 531 | 0.000000% | 0.000000% |

| Training-user history | Positive users | Recall@10 | NDCG@10 |
|---|---:|---:|---:|
| history_0 | 633 | 0.438201% | 0.414546% |
| history_1_2 | 1,455 | 0.308706% | 0.176653% |
| history_3_4 | 2,590 | 0.482625% | 0.238972% |
| history_5_plus | 2,161 | 0.177387% | 0.090377% |

Cold users receive the global ranking after available-history filtering. Cold products have no training score and cannot appear in the training-catalog recommendations, so their positive targets are misses, not dropped cases. Users first observed in validation remain cold relative to the frozen training snapshot even when their validation interactions are used in the test seen mask.

## Metric definitions and limitations

Recall@10 is hits divided by all positive targets for the user; NDCG@10 uses binary gains and log2(rank+1) discounts divided by the ideal gain for min(10, number of positives). Users with no positives have undefined Recall/NDCG and are counted explicitly. Catalog coverage is the union of recommended products for the same positive-user cohort divided by the complete training catalog. Recommendations use the full catalog and never sampled negatives. Ratings 1–3 yield zero ranking gain; all ratings contribute to training count and mean rating, and every previous interaction is excluded irrespective of its star rating. An unobserved product is not established negative feedback.

The existing subset was selected retrospectively using the complete interaction graph. Its five-core selection and iterative pruning use future activity and favor sufficiently connected users/products. Chronological partitions prevent additional future-rating leakage into scores but cannot remove that selection bias. The frozen catalog and scores also become stale over a long holdout horizon. Unknown products are intentionally unsupported without metadata or an approved catalog-expansion policy. Results are a retrospective offline comparison, not an unbiased deployment or causal evaluation. Five-core does not guarantee sufficient training history after splitting.

## Verification and tests

All **33 synthetic tests passed after the real pipeline run** (19 evaluation/popularity tests plus the 14 existing subsetting tests). They cover exact boundary timestamps, partition reconstruction, unchanged string IDs and numeric field text, future-rating perturbations, frozen statistics, count/quality scoring, full-catalog requirements, seen masks, all four cold-start segments, hand-calculated metrics, macro averaging, undefined no-positive cases, deterministic tie priority, and reproducible partitions/rankings. An end-to-end fixture verifies that the selected validation winner is saved before test evaluation and remains selected even when it performs worse on synthetic test data.

An independent audit reconstructed all 171,104 subset records from the saved partitions with exact field equality and order, rebuilt training counts/means/history, checked every full-catalog ranking, and verified every exported prediction against its available-history mask. It independently recalculated all four validation metrics and the selected test metrics, including warm/cold segments, matching within an absolute tolerance of 1e-14. Subset, subset-manifest, split, and implementation checksums matched. No dataset ID values were found in tracked Markdown documentation. Aggregate evidence is in the ignored run's `audit.json`; the audit took 4.34 seconds in addition to the main pipeline.

The ignored run's `post_run_validation.json` records the 33-test pass, independently verified training-coverage counts, test-file hashes, implementation-check status, and the final report hash. The measured final test-suite time was 1.227 seconds.

No pipeline or test errors occurred. There was no retuning after examining test results. The initial full-catalog baseline is weak: even among warm users and warm products, test Recall@10 is only 0.730163%. Cold-product unreachability explains part of the overall limitation, but does not alone explain the low warm-start accuracy or narrow recommendation coverage.

## Resources and artifacts

- Total measured pipeline time: 8.490 seconds, including split preparation, prediction export, and integrity checks.
- Split preparation: 4.206 seconds; training aggregation: 0.941 seconds.
- Process lifetime peak working set: 95.85 MiB.
- Retained run files before results/report: 67.52 MiB (not a peak disk measurement).
- Python 3.14.7; standard library only.
- Run directory: `<PROJECT_ROOT>\data\local\evaluation-ej957b9_`.
- Artifacts include train/validation/test CSVs, split manifest, subset provenance, SQLite validation database, training snapshot, all four catalog rankings, validation selection, validation predictions for all candidates, test predictions for selected/count, and aggregate `results.json`. IDs appear only in ignored local artifacts.

| Window | Candidate | Evaluation/export seconds | Recommendation median µs | Recommendation P95 µs |
|---|---|---:|---:|---:|
| validation | count | 0.487 | 1.800 | 2.200 |
| validation | quality_m10 | 0.546 | 1.900 | 2.400 |
| validation | quality_m5 | 0.544 | 1.800 | 2.300 |
| validation | quality_m20 | 0.550 | 1.800 | 2.300 |
| test | count | 0.434 | 1.800 | 2.300 |

Recommendation latency covers only the in-process filtered ranking call; it excludes CSV I/O, metric computation, network service, and application startup. Overall elapsed time excludes the final results/report writes. See `docs/evaluation_strategy.md` for the fixed protocol and commands. Preserve the complete run for reproducibility. Future cleanup should target only this exact owned directory after resolving and checking that it is beneath the intended ignored local-data parent; never remove the prepared subset or its parent as part of evaluation cleanup.

No packages, metadata, collaborative filtering, hybrid model, frontend, backend, or Git configuration changes were introduced. Stop for review before proceeding to later phases.
