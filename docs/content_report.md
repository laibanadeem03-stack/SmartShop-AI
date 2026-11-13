# SmartShop-AI TF-IDF content results

> Historical aggregate report. Use [fresh-clone setup](fresh_clone_setup.md) for current CLI arguments and output hand-offs; do not reuse old run paths or report filenames.

Selected content model: **tfidf_df2_title80**, using validation macro NDCG@10 only.

Parameters: min_df=2, title/category weight 0.80/0.20, word unigrams/bigrams, max_df=0.95, smoothed IDF, sublinear TF, L2 normalization, float32 CSR. Actual fitted vocabularies are 23,910 title and 383 category features; caps remain 45,000 and 5,000. Vocabulary and IDF were fitted only on the 11,012 training-catalog products.

## Validation

| Model | Recall@10 | NDCG@10 | Catalog coverage | Personalized users | Fallback slots |
|---|---:|---:|---:|---:|---:|
| count | 0.00672564 | 0.00389604 | 0.00118053 | 0.00% | 100.00% |
| item_cf_k50_lambda10 | 0.01049311 | 0.00657693 | 0.30938976 | 83.91% | 30.43% |
| tfidf_df2_title80 | 0.01284492 | 0.00768907 | 0.79740283 | 92.28% | 7.72% |
| tfidf_df2_title95 | 0.01288747 | 0.00752457 | 0.80993462 | 92.28% | 7.72% |
| tfidf_df1_title80 | 0.01312345 | 0.00749267 | 0.76434798 | 92.28% | 7.72% |
| tfidf_df1_title95 | 0.01321956 | 0.00751117 | 0.77079550 | 92.28% | 7.72% |

## Frozen test comparison

| Model | Recall@10 | NDCG@10 | Catalog coverage | Hits | Personalized users | Fallback slots |
|---|---:|---:|---:|---:|---:|---:|
| count | 0.00345062 | 0.00195011 | 0.00136215 | 48 | 0.00% | 100.00% |
| item_cf_k50_lambda10 | 0.00494735 | 0.00300261 | 0.30566655 | 64 | 79.92% | 34.22% |
| tfidf_df2_title80 | 0.00585148 | 0.00363137 | 0.77370142 | 77 | 88.70% | 11.30% |

Test NDCG is **20.94% above CF** and **86.21% above count**. Recall is respectively 18.28% and 69.58% higher. These are descriptive relative changes with only 77 positive hits, not significance claims. Higher catalog spread measures recommendation reach, not proof of relevance or online benefit. Test outcomes did not change the selected configuration.

## Selected-model test segments

| Segment | Positive users | Recall@10 | NDCG@10 |
|---|---:|---:|---:|
| overall | 6839 | 0.00585148 | 0.00363137 |
| warm_users | 6206 | 0.00600136 | 0.00357894 |
| cold_users | 633 | 0.00438201 | 0.00414546 |
| warm_user_warm_product | 3344 | 0.01261713 | 0.00712773 |
| cold_user_warm_product | 446 | 0.00813848 | 0.00680627 |
| warm_user_cold_product | 4114 | 0.00000000 | 0.00000000 |
| cold_user_cold_product | 531 | 0.00000000 | 0.00000000 |
| history_0 | 633 | 0.00438201 | 0.00414546 |
| history_1_2 | 1455 | 0.00594120 | 0.00410449 |
| history_3_4 | 2590 | 0.00589447 | 0.00309450 |
| history_5_plus | 2161 | 0.00616998 | 0.00380568 |

## Models and resources

| Model | Shape | Nonzeros | Zero rows | Array MiB | File MiB |
|---|---|---:|---:|---:|---:|
| tfidf_df2_title80 | [11012, 24293] | 523,902 | 1 | 4.039 | 2.076 |
| tfidf_df2_title95 | [11012, 24293] | 523,902 | 1 | 4.039 | 2.081 |
| tfidf_df1_title80 | [11012, 45500] | 545,109 | 0 | 4.201 | 2.185 |
| tfidf_df1_title95 | [11012, 45500] | 545,109 | 0 | 4.201 | 2.192 |

Pipeline time: 281.862 seconds. Peak working set: 246.93 MiB. Retained artifacts before result/report writes: 66.80 MiB.

Test recommendation latency: median **5.865 ms**, p95 **7.867 ms**, versus replayed CF median 0.044 ms and p95 0.169 ms. Content scores the full catalog per user and is slower than bounded-neighbor CF. Vectorizer fitting took 0.922 seconds for min_df=2 and 0.988 seconds for min_df=1; these fits were reused across weights. The selected CSR payload is 4,235,268 bytes (4.039 MiB), compressed feature file 2,176,344 bytes (2.076 MiB), and associated vectorizer pair 251,395 bytes. Saved run files occupied 73.06 MiB after the additional inference state/audit files, before the final delivery receipt. These are retained sizes, not exact transient disk peaks. Pipeline timing excludes package installation, interpreter imports, and separate post-run delivery audits/bundle writes.

The selected matrix has one zero-vector product despite complete metadata ID coverage. Its nonlexical title and pruned category terms produce no usable features. That product remains in the catalog for count backfill. Cold users use count fallback; cold-user Recall/NDCG match the control. Cold-product target segments have zero hits, and positive test target reachability stays 40.98%. Content personalized 7,332/8,266 test users and filled 73,320 slots; count supplied 9,340/82,660 slots for the remaining 934 users. No user received fewer than ten results.

Ignored run: `<PROJECT_ROOT>\data\local\content-tfidf-w4fi9e0t`. Metadata SHA-256: `12b6cfb3a1e664ff0d2273b6f6aeddc0dda9a94aee7d8bfcc5b02876f56d178b`.

## Interpretation and integrity

All primary candidates, vocabulary, and IDF use the same 11,012 training-observed products. Ratings 4–5 seed frozen profiles; every rating enters seen masks. Test masks include validation history, but profiles, IDF, and popularity stay frozen. Off-catalog positives remain misses in overall metrics. No negative sampling, full item-item matrix, CF blending, or candidate expansion is used.

Count and frozen CF validation/test cohort metrics and prediction hashes reproduce their prior results exactly. Source subset, partitions, metadata, and CF files remain unchanged. Model selection and tie priority were saved before test interactions were read. Personalized-user/fallback rates use all holdout users; ranking metrics and catalog coverage use the existing positive-user cohort.

**All 102 synthetic tests passed** after final persistence checks (2.787 seconds), including the original 84 unchanged tests. Tests cover train-only vocabulary/IDF, ID alignment, equal 4/5-star seeds, hand-computed profiles/cosine, technical model numbers, CSR/float32/caps, deterministic ties, zero-vector/cold/negative-only fallback, exclusions, no dense conversion, frozen histories, source checksum/schema checks, exact baseline controls, selection-before-test, complete-bundle reload, and tamper rejection. Imports and final `pip check` passed; NumPy/SciPy stayed at their existing versions. No metadata or images were downloaded.

The inline audit protected 43 existing inputs. An additional local audit checked 52 earlier source artifacts against their pre-acquisition hashes/sizes/modification times, independently verified every fitted IDF from training-catalog document frequencies (maximum float32 error below 1e-6), reloaded all field/weight artifacts with exact field-transform agreement, and replayed 128 saved test-user recommendation lists/scores/source labels exactly. It took 8.657 seconds at 197.27 MiB peak working set, separate from the main pipeline. Aggregate evidence is in ignored `audit.json`.

The first saved bundle needed the frozen count/all-rating-history state for independent reload. This was added after evaluation, with fingerprint verification, plus a tested `load_artifacts` helper; no vectorizer was refitted, setting changed, or prediction reranked. Future runs save this state directly. `bundle_validation.json` records the matching original training/model fingerprints. The original run's implementation hashes remain in `results.json`; final delivery hashes additionally cover the persistence changes.

Created `scripts/content_tfidf.py`, `scripts/evaluate_content.py`, `tests/test_content_tfidf.py`, `tests/test_content_evaluation.py`, `requirements-content.txt`, `docs/content_strategy.md`, and this report; updated `docs/project_plan.md`. Existing evaluator/CF/popularity code was not modified. Models, ID mappings, histories, and predictions stay under the ignored run directory. Dependency setup required the already approved network escalation after the sandbox rejected PyPI access; no additional packages or permissions outside the approved scope were used.

The current metadata snapshot may not reflect titles/categories available at the March 2021 training cutoff. Fitting IDF on training products cannot remove historical-attribute uncertainty. Retrospective five-core selection, generic category overlap, short/marketing text, and repeated titles remain limitations. Cold products stay unreachable under this frozen training-catalog protocol. Offline differences are point estimates, not significance or online-benefit claims.

The approved CF baseline remains unchanged; choosing the best content configuration does not automatically replace the project default. See `docs/content_strategy.md` for configuration, tests, environment, and reproduction commands. Stop for review before hybrid or application work.
