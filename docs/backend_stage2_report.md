# SmartShop-AI backend Stage 2 results

Stage 2 is complete. The local API reuses the frozen count, CF, content and selected
hybrid models, adds count-only new demo identities, content similarity, verified
explanations and saved aggregate performance. Existing models were not retrained,
retuned, replaced or rewritten. No dependency was installed or changed.

## Endpoints

All paths below have prefix `/api/v1`.

| Method/path | Behavior |
|---|---|
| `GET /health/live` | Process liveness |
| `GET /health/ready` | Frozen-model and catalog startup readiness |
| `GET /products` | Existing browsing, pagination, search and category filtering |
| `GET /products/{product_id}` | Verified product details |
| `GET /demo/profiles` | The existing twelve anonymous training-backed profiles |
| `POST /demo/users` | Empty JSON body `{}`; create a new local alias (201) |
| `GET /users/{public_user_id}/recommendations` | Top ten, hybrid by default; model=hybrid/count/cf/content |
| `GET /products/{product_id}/similar` | Existing sparse TF-IDF content similarity |
| `GET /recommendations/{batch_id}/items/{product_id}/explanation` | Actual evidence for a returned item, subject to batch lifetime |
| `GET /metrics/models` | Saved validation/test aggregate results for four models |
| `GET /metrics/models/{model}` | Saved results for one public model name |

Recommendations include verified product titles, nullable main categories, category
lists and training-catalog eligibility. Every recommendation and similar candidate
belongs to the unchanged 11,012-product training catalog. All 12,635 products remain
browsable. Out-of-catalog similarity queries return 409; a zero-vector query returns
an empty similarity list without popularity padding.

## Ranking, histories and evidence

The default remains weighted RRF, CF 0.50/content 0.50/c=60. The original hybrid
adapter ranks positive signals before component-level backfill, normalizes missing
signals per user and applies count fallback once. Comparison requests call the
native frozen CF/content methods or frozen count ranking, preserving their scores.

Serving uses only positive training ratings as seeds and all training interactions
as exclusions. No validation/test ratings, clicks or new-user feedback are added.
Raw dataset IDs resolve privately from the existing alias table. Sending a raw
training ID instead of an alias returns a sanitized 404. New users are stored only
in `data/local/backend-runtime/demo_users.sqlite3`, separate from the immutable
catalog; they receive count popularity for every requested model, with the requested
and served models distinguished. One new local test identity remains from the live
smoke test. The curated profile listing still has twelve entries.

Ranking and explanation work share one inference lock. Returned evidence is captured
inside that lock; mutable last-result fields and latency lists are cleared on success
or failure. Explicit signals are reconstructed for explanations instead of reading
another request's last state. Similarity also uses the lock. The launcher uses one
worker and loads the existing numeric libraries before setting one-thread limits.

The process-local cache is bounded to 100 batches and 300 seconds from creation,
with FIFO capacity eviction and lazy expiry. It stores only up to ten returned
items/traces, private subject references and frozen exclusion masks; no full catalog
score arrays are retained. Defensive copies prevent callers from altering cached
state. Expired/evicted/restarted batches and unreturned items receive sanitized 404s.

Explanations replay the native ranking with the identical mask, verify cached fusion
traces, and use the existing frozen-artifact evidence helper for exact CF seed sums
and TF-IDF contribution checks. They do not serve archived test-user explanations,
whose exclusions could differ from this serving policy. Reasons are deterministic
templates tied to the actual request's evidence. Up to three seed products/shared
features are displayed; totals include all contributors. Native comparison reasons
expose only the component used. Popularity reasons use training rating-interaction
counts. No purchases, causal preferences or present-day product availability are
inferred. Scores retain explicit types and are not probabilities/confidence percentages.

## Verification

**181 tests passed**, including all original 120 ML tests, the 31 Stage 1 tests
(with obsolete Stage 2-absence assertions updated), 23 new synthetic Stage 2 tests,
and seven real-artifact Stage 2 integration tests. The final full suite took 21.726
seconds; the subprocess elapsed time including interpreter/imports was 25.079 seconds.

Checks include exact native/API scores and product order for all twelve profiles
and all four models, exclusions, deterministic ranking, new-user persistence/fallback,
no held-out-row reads, zero vectors, missing signals, per-user normalization, schema
and error privacy, raw-ID rejection, explicit CORS, cache expiry/eviction, corrupted
trace rejection, lock release after failures and concurrent subject/evidence isolation.
Real integration checked 120 hybrid item explanations plus 108 native explanation
examples. It verified both fusion sums and native component support, including that
CF seed products are actually positive training entries.

The separate resource audit repeated **48 exact native/API batch comparisons** and
verified **156 explanations** (all 120 hybrid items plus one per native model/profile).
It confirmed training-snapshot and positive-matrix fingerprints unchanged, the
catalog checksum unchanged, and exactly 100 cache entries under sustained requests.
Synthetic concurrency instrumentation measured at most one active inference
preparation, and real concurrent profile/explanation requests also passed.

The initial full integration run found recursive null-field exclusion in explanation
serialization: nullable main_category was being omitted. The route now excludes
unset evidence sections while preserving explicitly null product fields, and the
full suite passes. Starlette's preexisting HTTPX test-adapter deprecation warning
remains; its approved adapter works and no replacement package was installed.

## Measured resources

| Measurement | Observed |
|---|---:|
| Actual single-worker launch to readiness | 3.811 s |
| Final in-process lifespan startup (excluding initial imports) | 2.294 s |
| Final API audit elapsed (excluding initial imports) | 13.724 s |
| Final audit lifetime peak working set | 200.89 MiB |
| Original read-only catalog | 12,906,496 bytes / 12.31 MiB; unchanged |
| New local-identity database | 12,288 bytes / 12 KiB |
| New model-array artifact bytes | 0 |
| Cache at audited capacity | 100 batches, at most 1,000 returned items |

The peak is the Windows process-lifetime peak, not isolated incremental model
memory. The audit saturated the cache before reporting memory. Approximately
0.16 MiB of new local runtime/audit/test outputs was retained before final delivery
receipts, excluding source code and Python bytecode caches. Both audit passes used
isolated local demo stores; the delivered default runtime store is separate.

Latency observations are local sequential measurements, not production guarantees.
The final in-process audit ran after the test suite and used 50 requests per operation.
The independent live-loopback smoke test used 20 per operation. Recommendations
rotate across the twelve curated profiles; explanations repeat one actual batch.

| Operation | Live median ms | Live p95 ms | In-process median ms | In-process p95 ms |
|---|---:|---:|---:|---:|
| Count | 3.656 | 4.279 | 5.484 | 7.072 |
| CF | 3.820 | 4.273 | 5.847 | 7.245 |
| Content | 9.912 | 11.174 | 11.944 | 14.553 |
| Hybrid | 28.800 | 30.688 | 31.775 | 33.502 |
| New-user count fallback | 3.984 | 4.557 | 5.864 | 7.130 |
| Similar products | 6.565 | 7.548 | 8.485 | 9.653 |
| Explanation | 28.149 | 30.977 | 30.437 | 36.390 |
| Saved metrics | 2.694 | 3.267 | 4.187 | 5.365 |

The in-process test client adds different dispatch overhead than live HTTP; the two
measurements are separate observations. Concurrent requests can wait for the shared
lock. The live test used 127.0.0.1:8000, verified all Stage 2 operations without exposing
paths/internal exceptions, and stopped its server after verification.

## Saved performance and demo usage

No holdout evaluation was rerun or used for model selection. The metrics endpoint
returns saved aggregate values exactly, including warm/cold segments.

| Frozen model | Saved test Recall@10 | Saved test NDCG@10 | Saved catalog coverage |
|---|---:|---:|---:|
| Count | 0.00345062 | 0.00195011 | 0.14% |
| CF | 0.00494735 | 0.00300261 | 30.57% |
| Content | 0.00585148 | 0.00363137 | 77.37% |
| Hybrid | 0.00664107 | 0.00406017 | 73.61% |

The twelve-profile serving audit personalized 120/120 hybrid slots, 120/120 content
slots and 86/120 CF slots (11/12 CF users); count supplied all 120 count-only slots.
These are illustrative training-profile usage counts, not new ranking-quality
estimates. They differ from saved holdout usage because the cohort/masks differ.
The original test protocol additionally excludes validation history. The API labels
the serving history policy separately from those saved evaluation definitions.

## Integrity, files and limits

An inventory of 179 preexisting files verified **164 unchanged by SHA-256, size and
modification time**. The fifteen intentional changes are application/test/documentation
files listed below. Existing dataset, metadata, catalog, split, ML module and artifact
files are unchanged. All 26 installed package versions match the initial inventory;
pip check passed. No original downloaded CSV, company project, Git configuration,
remote, commit or push was accessed or changed.

Created ten project files:

```text
backend/app/repositories/demo_repository.py
backend/app/routers/recommendations.py
backend/app/routers/metrics.py
backend/app/services/batch_cache.py
backend/app/services/recommendation_service.py
backend/app/services/metrics_service.py
scripts/verify_backend_stage2.py
tests/test_api_recommendations.py
tests/test_api_recommendation_integration.py
docs/backend_stage2_report.md
```

Modified fifteen files:

```text
backend/__main__.py
backend/app/config.py
backend/app/dependencies.py
backend/app/errors.py
backend/app/main.py
backend/app/schemas.py
backend/app/repositories/sqlite_repository.py
backend/app/routers/users.py
backend/app/services/identity_service.py
backend/app/services/model_registry.py
tests/backend_fixtures.py
tests/test_api_contracts.py
docs/backend_architecture.md
docs/backend_report.md
docs/project_plan.md
```

Runtime stores and receipts remain under already ignored `data/local/`, including
`backend-runtime/`, `backend-stage2-20261112/` and two isolated `backend-stage2-audit-*`
directories. Original ignore rules and dependency pins were not edited. No trained
arrays, predictions or metadata copies were exported. Exact hashes and environment
inventories are in the private delivery receipt.

The application is localhost-only and has no production authentication. Aliases
reduce accidental identity disclosure; they are not a security boundary for remote
deployment. New-user creation is capped at 1,000 and has no preference/rating update
feature. Batch expiry/restart requires fetching recommendations again. Similarity
cannot cover the 1,623 out-of-training products without another approved extension.
Current metadata may postdate training; retrospective five-core selection and reused
validation tuning remain benchmark limitations. Saved point estimates do not establish
online benefit or statistical significance. Frozen directories require launching-account
read permission; no existing permissions were changed.

Run/start/API examples are in `backend_architecture.md`; no additional installation
is required. Dataset attribution remains Amazon Reviews 2023, McAuley Lab, UC San
Diego; Hou et al. (2024). The pinned source and usage constraints remain documented
in `metadata_text_report.md`. Stop for review before frontend development.
