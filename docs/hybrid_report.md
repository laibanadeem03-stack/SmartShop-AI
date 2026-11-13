# SmartShop-AI weighted RRF hybrid results

> Historical aggregate report. Use [fresh-clone setup](fresh_clone_setup.md) for current CLI arguments and output hand-offs; do not reuse old run paths or report filenames.

Best hybrid: **hybrid_cf50**, CF weight 0.50; content weight 0.50. Fixed rank constant: 60.
Default decision: **hybrid**. Strict validation improvement: **True**.

The saved default is the 50/50 hybrid because validation NDCG improved from 0.007689071988795832 to 0.008332458110108376 (**+8.37%**). The decision was persisted before test evaluation; it does not deploy a backend or overwrite either component model.

## Validation

| Model | Recall@10 | NDCG@10 | Catalog coverage | Personalized users | Fallback slots |
|---|---:|---:|---:|---:|---:|
| count | 0.00672564 | 0.00389604 | 0.00118053 | 0.00% | 100.00% |
| item_cf_k50_lambda10 | 0.01049311 | 0.00657693 | 0.30938976 | 83.91% | 30.43% |
| tfidf_df2_title80 | 0.01284492 | 0.00768907 | 0.79740283 | 92.28% | 7.72% |
| hybrid_cf10 | 0.01269495 | 0.00782913 | 0.79685797 | 92.28% | 7.72% |
| hybrid_cf25 | 0.01316707 | 0.00827093 | 0.79395205 | 92.28% | 7.72% |
| hybrid_cf50 | 0.01375632 | 0.00833246 | 0.75626589 | 92.28% | 7.72% |
| hybrid_cf75 | 0.01293451 | 0.00799925 | 0.72275699 | 92.28% | 7.72% |

## Frozen test comparison

| Model | Recall@10 | NDCG@10 | Catalog coverage | Hits | Personalized users | Fallback slots |
|---|---:|---:|---:|---:|---:|---:|
| count | 0.00345062 | 0.00195011 | 0.00136215 | 48 | 0.00% | 100.00% |
| item_cf_k50_lambda10 | 0.00494735 | 0.00300261 | 0.30566655 | 64 | 79.92% | 34.22% |
| tfidf_df2_title80 | 0.00585148 | 0.00363137 | 0.77370142 | 77 | 88.70% | 11.30% |
| hybrid_cf50 | 0.00664107 | 0.00406017 | 0.73610607 | 87 | 88.70% | 11.30% |

Versus content, test NDCG improved **11.81%**, Recall improved **13.49%**, and positive hits increased from 77 to 87. Catalog coverage declined from 77.37% to 73.61% (**3.76 percentage points**). Versus CF, NDCG improved 35.22% and Recall 34.23%; versus count, the increases were 108.20% and 92.46%. These are point estimates with modest absolute hit counts, not statistical-significance or online-benefit claims. No test result changed the weights or the validation gate.

## Challenger test segments

| Segment | Positive users | Recall@10 | NDCG@10 |
|---|---:|---:|---:|
| overall | 6839 | 0.00664107 | 0.00406017 |
| warm_users | 6206 | 0.00687149 | 0.00405147 |
| cold_users | 633 | 0.00438201 | 0.00414546 |
| warm_user_warm_product | 3344 | 0.01476027 | 0.00844985 |
| cold_user_warm_product | 446 | 0.00813848 | 0.00680627 |
| warm_user_cold_product | 4114 | 0.00000000 | 0.00000000 |
| cold_user_cold_product | 531 | 0.00000000 | 0.00000000 |
| history_0 | 633 | 0.00438201 | 0.00414546 |
| history_1_2 | 1455 | 0.00737304 | 0.00470860 |
| history_3_4 | 2590 | 0.00799871 | 0.00433502 |
| history_5_plus | 2161 | 0.00518279 | 0.00326917 |

## Runtime and integrity

Pipeline: 570.713 seconds; process peak working set 230.13 MiB; retained output before result/report writes 105.14 MiB.
Live hybrid query median 25.109 ms; p95 28.116 ms, excluding evidence-file export.

The pipeline took **9 min 30.713 sec** including native control replays, the shared validation grid, live test ranking and evidence export; Python startup and separate delivery audits are excluded. The validation shared generation/fusion pass took 275.531 seconds and cached only 376,120 top-10 recommendations across four variants, not a user-catalog score matrix. Cached metric lookup was about 1.5 microseconds and is explicitly distinguished from model computation in results. Live test hybrid inference was slower than content (median 5.720 ms, p95 7.534 ms) and CF (median 0.038 ms, p95 0.151 ms). Full callback timing including evidence export was median 25.304 ms/p95 28.453 ms. No API latency guarantee is implied.

Run files occupied **105.22 MiB** before the final audit/delivery receipt. The selected hybrid manifest is **3,254 bytes** and references existing component files by hash; no new trained arrays are saved. Full fusion traces occupy 40,499,990 bytes (38.62 MiB), with 1,161,475 bytes (1.11 MiB) of enriched evidence for the first 128 sorted test users. Retained size is not an exact peak transient disk measurement.

Personalization remains **7,332/8,266 users (88.70%)**, equal to content; popularity fills **9,340/82,660 slots (11.30%)**. Per-item personalized support comprises 46,708 both-signal slots, 26,534 content-only slots, and 78 CF-only slots. Per-user availability comprises 6,606 users with both signals, 726 with content only, zero with CF only, and 934 with neither. Item support and user availability are different measures. Cold users retain count fallback with Recall 0.00438201/NDCG 0.00414546. Both cold-product target segments still have zero hits; positive test-target reachability remains 40.98%.

Ignored run: `<PROJECT_ROOT>\data\local\hybrid-3qctrm8u`. Component models are referenced by fingerprint/hash, not retrained or overwritten.

Count, CF, and content validation/test cohorts, segment metrics, and prediction hashes reproduce exactly. Selection and the strict default gate were saved before test interaction reads. No post-test weight changes or automatic threshold relaxation occurred. Test compares the locked challenger even if content wins the default gate. Default means a saved selection manifest, not a deployed service.

**All 120 synthetic tests passed** (2.836 seconds), including all 102 original tests unchanged. New coverage includes exact reciprocal-rank arithmetic and agreement, missing/zero signals, post-filter availability, rejection of per-item renormalization, single fallback and no component-backfill contamination, scale invariance, deterministic ties, invalid signals, changed-mask rejection, frozen profiles, no dense conversion, supported/stale/fabricated evidence, strict full-precision default gates, no-retraining integration, selection-before-test, exact controls, and artifact/default-gate tamper rejection. Final `pip check` passed; the environment is unchanged and no package was installed.

An independent post-run audit verified all 82,660 lightweight fusion traces against exported recommendations, eligibility, ranks, weights, source labels and arithmetic; replayed 128 users exactly; and regenerated all 1,280 rich explanations exactly. All 102 unique existing files covered by current/historical receipts retained their hashes, sizes and modification times, including datasets, metadata and prior model artifacts. The audit took 16.467 seconds at 189.10 MiB peak working set. It also reloaded the saved hybrid/default and verified the strict gate. Evidence is aggregate-only in ignored `audit.json`. A final loader-only hardening check rejects a manifest whose default contradicts its validation selection; scoring, selected weights and predictions were not changed.

Created `scripts/hybrid_ranker.py`, `scripts/evaluate_hybrid.py`, `tests/test_hybrid_ranker.py`, `tests/test_hybrid_evaluation.py`, `docs/hybrid_strategy.md`, and this report; updated the project plan. Existing recommendation/evaluation implementations and requirement files were not modified. No downloads, new dependencies, model retraining, UI/backend work, Git changes, or company-project access occurred.

All candidate products stay within the 11,012 training catalog. Training-only profiles and frozen scores are preserved; validation changes only test seen masks. Personalization/fallback rates include all holdout users, while ranking metrics/catalog coverage use the existing positive-user cohort. Cold products remain unreachable.

Full per-item fusion traces and a bounded rich-evidence sample are saved locally. Evidence identifies positive component support, ordinal ranks, raw scores, effective weights, rank contributions, training-liked CF seeds and shared TF-IDF features. Popularity is applied once after fusion and is never counted as personalized evidence. Scores are ranking values, not probabilities or confidence percentages.

Metadata snapshot timing, retrospective five-core selection, repeated use of validation for component/weight selection, and loss of score magnitude in RRF remain limitations. Point-estimate gains are not significance or online-benefit claims. See `docs/hybrid_strategy.md` for algorithm, tests, and reproduction. No backend/frontend, downloads, new dependencies, or Git configuration/commit/push actions were performed. Stop for review.
