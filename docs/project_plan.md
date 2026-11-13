# SmartShop-AI project plan

Scope: an intermediate-level product recommendation engine for Cell Phones & Accessories. Dataset preparation, chronological evaluation, popularity, item CF, bounded metadata acquisition, TF-IDF content, frozen-model weighted RRF evaluation, backend Stages 1/2 and frontend Stages 1/2/3/4/5 are complete. CF was implemented ahead of the metadata-dependent content phase. This document does not authorize later phases. Stop for review before GitHub publishing, further metadata or deployment.

Current publication preparation: Step 38 security/portability is complete, with
196 Python and 97 frontend tests passed. Step 39 adds the [README](../README.md),
[data-usage attribution](data_usage.md) and [portfolio review notes](portfolio_publication.md).
Step 40 prepared the approved [MIT License](../LICENSE) and retained icon notices;
publication remains unapproved. Counts and approval statements in
the phase descriptions below describe their historical completion checkpoints.

## 1. Data foundation and reproducible evaluation

Use `docs/dataset_report.md` for source schema, data quality, activity levels, and storage needs, and `docs/subset_report.md` for the completed subset and temporal-coverage diagnostics. The original CSV and scratch databases remain outside the repository. The subset and aggregate manifest are under `/data/local/`, explicitly excluded by the root `.gitignore`. No raw records or identifier values belong in tracked documentation.

The approved source has no repeated user-product pairs or missing/invalid timestamps. `scripts/create_subset.py` reuses the inspected SQLite graph read-only, verifies the input checksum, and preserves the original ID, rating, and timestamp field values. It rejects unsupported duplicate pairs or unexpected ID whitespace rather than silently changing identity. Integer timestamp normalization is internal to diagnostics; exported values keep their original text and units.

The inspected full graph satisfies the distinct-neighbor five-core property, with 2,752,785 interactions, 380,999 users, and 111,480 products. The approved subset target was narrowed to 100,000–200,000 interactions. Seed-42 SHA-256 user samples at 1/16, 1/8, and 1/4 retained 81, 48,913, and 328,488 interactions after iterative five-neighbor pruning. The first exact midpoint refinement, 3/16, retained 171,104 interactions, 25,791 users, and 12,635 products after 34 pruning rounds. It meets the target and the distinct-neighbor five-core requirement without an arbitrary row cap. The aggregate manifest records checksums, exact fractions, every pruning round, preservation checks, resource usage, and temporal diagnostics. The source and aggregation checksums remained unchanged.

Earlier aggregate diagnostics compared per-user leave-two-out and global chronology. Leave-two-out would leave at least three training interactions per user, but 189 products without training history and 4,359 products below five training interactions. The now-approved global protocol leaves 791 users and 1,623 products without training history; 2,890 users have fewer than three training interactions. The per-user alternative remains a diagnostic rather than a second saved evaluation split.

The approved global chronological protocol is implemented in `docs/evaluation_strategy.md`. Training ends at 2021-03-16T03:32:11.064Z and validation ends at 2022-03-25T00:47:41.066Z, with inclusive upper bounds; test follows validation. Equal timestamps stay together. Verified counts are 136,883 training, 17,110 validation, and 17,111 test interactions. All original field values are preserved in ignored local outputs. All popularity statistics use training data; validation selects the method and prior strength, and test is reserved for final comparison. Global core selection uses future graph structure, and pruning favors sufficiently connected users/products, so describe results as a retrospective benchmark. Do not silently remove unsupported holdout cases or assume full-data five-core survives a split.

Subsetting and chronological splitting are complete. At the CF completion checkpoint, the combined suite had 50 passing synthetic tests, including the original 33 data/evaluation tests and 17 CF tests. Independent audits verified exact field preservation, source checksums, frozen statistics, sparse neighbors, prediction masks/source attribution, and metrics. Existing partitions remain unchanged. Later phases require review first.

## 2. Popularity baseline and evaluation harness

Implemented count popularity and three Bayesian-style quality-aware rankings (m=5, 10, 20) using training counts and means only. The candidate catalog contains all 11,012 training-observed products, including low-support products; no new five-core/minimum-five filter is applied. Validation recommendations exclude training history. Test recommendations also exclude validation history, without updating frozen popularity scores. Exact validation NDCG ties prefer count, quality_m10, quality_m5, then quality_m20.

Implemented full-training-catalog Recall@10, NDCG@10, and catalog coverage with binary relevance for 4–5 stars. Reports retain cold targets in overall denominators, count users without positive targets, separate warm/cold segments and history buckets, and report positive-target reachability. No negative sampling or dense user-product score matrix is used.

Use popularity as the initial fallback for new users. Explanations should be factual, such as training-set interaction count and mean rating. Measure typical recommendation latency locally.

Completed: count popularity had the highest validation NDCG@10 (0.00389604), versus 0.00295625 for the best smoothed variants. The selected count baseline scored test Recall@10 0.00345062, NDCG@10 0.00195011, and catalog coverage 0.00136215. It is the count control itself, so no improvement over count is claimed. Only 40.98% of positive test targets were reachable in the frozen training catalog. See `docs/baseline_report.md` for actual segments, resources, artifacts, and limitations. No test results were used for selection or tuning.

## 3. Content-based recommendations

The separately approved ID-only metadata pilot matched all 12,635 selected products, including all 1,623 products outside training, using 18.60 MiB of metered response payload. See `docs/metadata_coverage_report.md` and `docs/metadata_pilot_strategy.md` for the exact revision, seven shards, tests, resources, and ID-only scope.

The approved four-field metadata acquisition is complete; see `docs/metadata_text_report.md`. All selected IDs matched, 12,634 products have usable titles, and every product has usable main-category or hierarchy text. Only parent IDs, titles, main categories, and category hierarchies were decoded. Text-stage payload was 107.16 MiB; the combined ID-pilot/text payload stayed below the 150 MiB cap. That phase passed 84 tests without fitting a model.

Acquire additional metadata only after a separate approved decision. Continue to record provenance, licensing, category, release, and `parent_asin` compatibility. Do not assume child ASIN and parent ASIN are interchangeable. Audit duplicate keys and report both product-level and interaction-weighted join coverage.

The subsequently approved TF-IDF phase is complete. Separate title/category word unigram/bigram vectorizers fit only the 11,012 training products, with float32 CSR data, caps of 45,000/5,000 features, and min_df=1/2. Validation selected min_df=2 and title weight 0.80 from the four approved settings. Training 4–5-star seeds produce frozen normalized user profiles; one sparse catalog score column per query avoids any full item-item matrix. Every rating remains a seen exclusion, validation updates only test masks, and count supplies fallback. Existing partitions, source metadata, and CF models remain unchanged.

Selected content validation NDCG@10: 0.00768907. Test Recall@10: 0.00585148; NDCG@10: 0.00363137; catalog coverage: 77.37%. Test NDCG is 20.94% above the frozen CF control and 86.21% above count, as descriptive point estimates. Content personalized 88.70% of test users; count filled 11.30% of slots. Cold products remain unreachable in the unchanged primary catalog. The run took 281.862 seconds at 246.93 MiB peak working set; all 102 tests passed. See `docs/content_strategy.md` and `docs/content_report.md` for exact validation comparisons, resources, zero-vector limitations, chronology/metadata caveats, persisted inference bundles, and audit evidence. At that phase checkpoint, CF remained preserved and hybrid implementation had not started. The subsequently completed hybrid phase is recorded below.

## 4. Collaborative filtering

Completed positive item cosine using the existing training partition, a minimum of two shared positive users, and 128-item sparse blocks. Compared K=20/50 and shrinkage lambda=0/10 on validation only. Retained at most K outgoing neighbors per item; no full dense item-item matrix was constructed. Ratings 4–5 are positive seeds, while all ratings remain seen exclusions. Profiles and graph statistics stay frozen for test; validation history updates only test masks. Count popularity supplies fallback, without weighted hybrid blending. The selected subset and all existing splits remain unchanged.

Validation selected K=50, lambda=10: Recall@10 0.01049311, NDCG@10 0.00657693, catalog coverage 0.30938976. Test Recall@10 was 0.00494735 and NDCG@10 0.00300261, respectively 43.38% and 53.97% higher than count; catalog coverage was 0.30566655 (3,366 products versus 15 for count). These are point estimates, not significance claims. Test results did not select or change the configuration. The unchanged count control's metrics and prediction hashes reproduced exactly.

CF personalized at least one slot for 79.92% of all test users; popularity filled 34.22% of slots. Cold-product reachability remains unchanged at 40.98% of positive test targets. The run took 9.372 seconds with 125.86 MiB peak working set. The selected graph has 19,377 edges, a 0.190 MiB array payload, and a 95,837-byte compressed artifact. See `docs/item_cf_strategy.md` and `docs/item_cf_report.md` for details, zero-neighbor limitations, tests, environment, artifacts, and audit evidence. Explanations can later reference training-liked seeds and their neighbor contributions without claiming causal preferences. Matrix factorization and deep learning remain outside the initial scope.

## 5. Hybrid ranking, cold start, and explanations

Completed the separately approved weighted RRF phase without retraining or changing CF/content artifacts. Use positive personalized CF/content ranks before their backfill, normalized as 61/(60+rank), with fixed constant 60. Validation compared CF weights 0.10/0.25/0.50/0.75 and chose **0.50 CF / 0.50 content**. Missing signals are normalized per user; popularity is applied once after fusion, not as a third voting component. Full positive component lists use the same 11,012 training products, deterministic count/ID ties and chronological exclusions. No full user-catalog or product-product matrix is stored.

The saved default decision is **hybrid**: validation NDCG 0.00833246 strictly exceeded content's 0.00768907. That gate and configuration were frozen before test. Test Recall was 0.00664107, NDCG 0.00406017, catalog coverage 73.61%, and hits 87. Versus content this is 11.81% higher NDCG and 13.49% higher Recall, with 3.76 percentage points lower coverage. Personalization/fallback remain 88.70%/11.30%; cold-product targets remain unreachable. These are retrospective point estimates, not significance or online-benefit claims.

All 120 tests pass. Count, CF and content validation/test predictions and metrics reproduced exactly. The run took 570.713 seconds at 230.13 MiB peak working set; live hybrid median/p95 were 25.109/28.116 ms. The 3,254-byte hybrid manifest references frozen component hashes, with roughly 105.22 MiB of prediction/evidence outputs under ignored local storage. Exact fusion traces and audited training-seed/shared-feature evidence support later explanations. See `docs/hybrid_strategy.md` and `docs/hybrid_report.md` for artifacts, source integrity, metrics, latency and limitations. A saved default is not a deployed service.

For new users, offer popularity or an optional selection of preferred products/categories once metadata exists. For new products with metadata, use content similarity; report that the ratings-only dataset cannot establish how unseen catalog products perform. Keep each explanation tied to an actual ranking component.

The strict default rule retains content on validation ties/regressions; the loader verifies the saved gate. This run passed the rule, while adding latency and reducing catalog spread relative to content. Stop for review before application work or changing this policy.

## 6. FastAPI, SQLite, and React application

Stage 1 backend foundation is complete: a local single-worker FastAPI factory,
verified frozen-artifact registry, read-only SQLite browsing database with all
12,635 products and 11,012 eligibility flags, twelve anonymous training-backed
profiles, health checks, product search/filter/pagination/details, explicit schemas,
redacted errors and localhost React CORS. No held-out interactions enter serving
profiles. See `docs/backend_architecture.md` for run/preparation instructions and
`docs/backend_report.md` for tests, integrity checks and measured resources.
The subsequently approved Stage 2 is also complete: top-ten hybrid/count/CF/content
recommendations, count-only new local users, content similarity, verified batch
explanations and saved aggregate metrics. Inference is serialized and explanations
use a bounded 100-batch/five-minute cache. Profiles and exclusions remain training-only;
new aliases persist separately from the read-only catalog. All 181 tests pass,
including exact native/API parity across the twelve profiles and concurrent evidence
checks. See `docs/backend_stage2_report.md` for measured startup, latency, memory,
artifact integrity, endpoint list and limitations. No existing ML artifact or dependency version was changed;
approved backend dependencies are pinned separately in `requirements-backend.txt`.

Trained artifacts remain frozen and are reused by the startup registry. Application SQLite storage is separate from inspection and metadata-acquisition databases. Prototype ratings, preferences or profile updates would require later approval.

The approved Frontend Stage 1 is complete. Official Node.js 26.13.1 Windows x64
was SHA-256 verified before project-local extraction; npm 11.20.0 runs without PATH
or global-setting changes. The React/Vite/Tailwind/Lucide foundation provides a
responsive editorial shell and twelve-product real-API Discover preview. Other
routes are explicitly initial layouts. Nineteen frontend tests and the production
build pass; browser checks verified the real titles, four responsive widths, no
horizontal overflow and no Stage 2 API calls. See `docs/frontend_architecture.md`
for local commands and `docs/frontend_stage1_report.md` for exact dependencies,
files, checks and limitations.

The separately approved Frontend Stage 2 is also complete: server-side 24-product
pages, 300ms debounced search, verified featured-category filtering, URL/history
state and pagination, independent product details with historical training statistics,
and eligible-product similarity. Shared cancellation/keyed response handling prevents
stale results. Forty frontend tests and nineteen real-browser flow checks pass,
including actual metadata gaps, outside-catalog/zero-vector cases and four responsive
widths. No backend/model changes or package installations were needed. See
`docs/frontend_stage2_report.md`. Those are the historical Stage 2 checks.

The approved Frontend Stage 3 is complete: twelve anonymous historical profiles, explicit new-demo creation, the default hybrid and three comparison models, real served-model/count labels, recommendation cards and batch-bound evidence dialogs. Only the selected public alias/type is persisted. Abort/keyed state protects profile/model changes; actual cache eviction is recovered with a new batch and an item-presence check. Seventy frontend tests, the production build and fifteen real-browser flow checks pass across four widths. See `docs/frontend_stage3_report.md` for historical Stage 3 results. Preference/rating updates remain outside the approved application API.

The separately approved Frontend Stage 4 is complete: saved model-metrics integration, Recall@10/NDCG@10/coverage comparisons, validation/test selection, model-specific segment analysis, usage fractions, evaluated-user counts and historical limitations. Recharts 3.10.1 and its required React-matched react-is 19.3.1 peer are pinned locally; existing direct pins remain unchanged. All 93 frontend tests, the production build and fourteen live-browser checks pass. API-reported default selection is displayed; unavailable fusion weights and evaluation dates are not inferred. Metrics remain frozen offline results. See `docs/frontend_stage4_report.md` for historical Stage 4 results.

The approved Frontend Stage 5 is complete: focused route/dialog restoration fixes, supporting-text contrast, readable disclaimers, complete end-to-end production-preview QA and local setup instructions. All 97 frontend tests and 181 Python tests pass; 57 grouped browser checks and twenty page/viewport layouts pass at five widths. No packages, API contracts, trained models or evaluation artifacts changed. See `docs/final_qa_report.md` and `docs/local_setup.md`. Publishing and deployment remain unapproved.

Done when the local application demonstrates the baseline, content, collaborative, hybrid, and cold-start flows with reproducible setup instructions and focused checks of ranking and API behavior.

## Scope boundaries and review

The isolated `.venv` uses Python 3.14.7, NumPy 2.5.3, SciPy 1.18.1, and DuckDB 2.0.0. The separately approved content stage added scikit-learn 1.9.1, joblib 1.6.0, narwhals 2.28.0, threadpoolctl 3.8.0, and cloudpickle 3.1.2 without changing NumPy/SciPy; `requirements-content.txt` records these pins alongside the earlier requirements files. Imports and pip consistency checks passed. Global Python is unchanged and Pandas remains uninstalled. Further dependencies require approval. Defer production deployment, authentication, real-time retraining, distributed systems, neural recommenders, and elaborate experiment infrastructure.

The completed work comprises the separately approved data preparation, evaluation, popularity/CF, metadata, content, frozen-model RRF, backend Stages 1/2 and frontend Stages 1/2/3/4/5. No additional metadata descriptions, feature bullets, image/video data or product images were acquired. Frontend Stage 1 added the approved isolated Node toolchain, pinned UI/test dependencies and visual foundation; Stages 2/3 reused these dependencies and the existing API contracts; Stage 3 creates local demo users only on explicit clicks. Stage 4 adds only the approved chart library/required peer and presents the existing saved metrics. The catalog, datasets, trained components and Python package versions remain intact. Git settings/remotes/commits/pushes and company projects were not accessed or changed by these phases. Stop for review before GitHub publishing, further metadata or deployment work.

## Publication preparation: Step 38

Completed the limited security/portability change set: private generated-file exclusions,
portable public paths, explicit local artifact registration, per-build metrics integrity,
normal/recovered metadata receipts and one immutable metadata pin. Existing models,
data, splits, catalog and application pointer remain frozen. New configurations are
private operator trust roots, not automatically discovered artifacts. See
`docs/fresh_clone_setup.md` and `docs/publication_step38_report.md`. Real-data rebuilding,
README finalization, code licensing, screenshot rights and publishing remain separate
review steps.

## Portfolio documentation: Step 39

Created the professional root README, Mermaid architecture, verified model comparison,
data-usage attribution and portfolio publication notes. Two individually reviewed
AI Insights interface/aggregate captures are included with exact ignore exceptions;
product-content screenshots remain private. Existing code/models/data are unchanged.
Source-code MIT licensing is recommended but not adopted. Documentation checks pass;
the 196 Python / 97 frontend counts remain the latest Step 38 regression results,
not new test runs. Full fresh-clone reproduction remains unverified. Stop for review
before licensing, final staging or publishing.

## Final publication safety: Step 40

Reviewed the exact source candidate set, screenshots, dependency/asset notices and
licensing boundary. Prepared MIT (2026 Laiba Nadeem) for authorized original source
and documentation, retaining Lucide/Feather terms in separate third-party notices.
Data, product metadata, model bundles and other third-party content are excluded
from that grant. See [final safety review](publication_safety_review.md). No application
code, artifacts, Git configuration or credentials changed. Publication and Git
mutations require separate approval; clean-clone reproduction remains unverified.
