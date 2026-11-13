# SmartShop-AI backend: Stages 1 and 2

Stage 1 implements local catalog browsing, anonymous dataset-backed demo listings,
health checks and API contracts. Stage 2 adds frozen-model recommendations,
count-only cold start for new local identities, content similarity, verified
explanations and saved aggregate metrics. The React frontend is implemented; current local and fresh setup guides are linked below.

See [local_setup.md](local_setup.md), [fresh_clone_setup.md](fresh_clone_setup.md) and the Step 38 report for current registration/provenance requirements.

## Run locally

From the SmartShop-AI workspace in PowerShell:

```powershell
# Existing prepared workspace; fresh installs need all requirement groups:
# See fresh_clone_setup.md for the complete dependency/bootstrap recipe.
.\.venv\Scripts\python.exe -I -B -m pip check
.\.venv\Scripts\python.exe -B -m backend
```

The launcher binds to `127.0.0.1:8000`, uses one worker, disables access logging,
and limits numerical thread pools to one. Stop it with Ctrl+C. API documentation:
`http://127.0.0.1:8000/docs`; readiness:
`http://127.0.0.1:8000/api/v1/health/ready`.

The prepared default pointer already exists at `data/local/application-current.json`.
The current database is bound to the ignored operator registration `data/local/serving-artifacts.json`; no environment override is needed for the delivered workspace. There is no auto-reload,
database rebuilding, model training, or download on startup.

## Prepare reproducible local application data

```powershell
# First preparation only, when the default pointer does not exist:
.\.venv\Scripts\python.exe -B scripts/prepare_application_data.py --activate

# Subsequent preparations create a fresh directory without changing that pointer:
.\.venv\Scripts\python.exe -B scripts/prepare_application_data.py
# To serve a newly prepared copy, use the manifest path printed by the command:
$env:SMARTSHOP_APP_MANIFEST = 'data/local/application-UNIQUE/application_manifest.json'
.\.venv\Scripts\python.exe -B -m backend
# Remove the optional process-local override to return to the delivered default:
Remove-Item Env:SMARTSHOP_APP_MANIFEST -ErrorAction SilentlyContinue
```

Preparation refuses existing database files and refuses to overwrite an active
pointer. It checks at least 128 MiB free disk, verifies the fixed metadata checksum
and frozen hybrid bundle, and uses only the saved training snapshot for eligibility,
statistics and profile selection. It never reads source ratings, validation/test
interactions, or evaluation prediction rows. All four original metadata fields are
checked for exact preservation after insertion. Title fallback is presentation only.

Each run creates `data/local/application-UNIQUE/app.sqlite3` and an aggregate
`application_manifest.json`. The private 32-byte alias key is reused from
`data/local/backend-demo-alias-key.bin`; an optional `--alias-key-file` must also
resolve inside `data/local`. Preserve this key locally to reproduce aliases.
Identical source files, script, private key, and SQLite version reproduce database
bytes; timestamps in the external run manifests intentionally differ.

Application directories use normal exclusive directory creation, inheriting the
workspace's existing local-data permissions. Windows Python 3.14 owner-only
temporary-directory permissions must not accidentally lock out the operator.
The launching account must also have read access to the preexisting frozen model
directories. This stage does not alter their permissions or contents.

## Modules and lifecycle

`backend/app/main.py` is an application factory with a lifespan context. Configuration
is server-side; `SMARTSHOP_APP_MANIFEST` may select only a manifest within this
workspace's resolved `data/local` directory. No request accepts a local file path.

At startup the application verifies database and metadata SHA-256 values, loads the
frozen hybrid through its existing integrity-checking loader, and validates database
provenance, counts, training eligibility and private mapping membership. Snapshot,
matrix, graph, ID mappings, configuration and strict validation-gate checks remain
in the original engine loader. A registry holds the loaded CF/content/hybrid state
and a shared inference lock. Stage 2 also loads the trusted, hash-verified frozen
vectorizers for feature-name alignment, without fitting or transforming text.
The saved aggregate-results file has a pinned SHA-256 and is projected to a public
allowlist at startup. Prediction rows and held-out ratings are never loaded.

Products and anonymous identities have separate routers, services and a SQLite
repository. Each repository operation opens a short-lived `mode=ro&immutable=1`
connection with `query_only=ON`, and explicitly closes it. A separate mutable
SQLite repository persists only newly created local demo aliases. An operator must never
edit the active database in place: prepare a new copy and restart instead.

Startup failures are logged by exception class only. Liveness remains available;
readiness and data endpoints return a generic 503. Readiness reports startup-validated
state, not continuous file checks. Shutdown clears application-held references.

## API contracts

All application routes have prefix `/api/v1`.

| Method/path | Response |
|---|---|
| `GET /health/live` | `HealthResponse`: status alive |
| `GET /health/ready` | status ready and public model version, or generic 503 |
| `GET /products` | `ProductPage`: items, page, page_size, total |
| `GET /products/{product_id}` | `ProductDetail`, or 404 |
| `GET /demo/profiles` | `DemoProfiles`: twelve public aliases and labels |
| `POST /demo/users` | Empty JSON body `{}`; 201 NewDemoUser with a fresh public alias |
| `GET /users/{public_user_id}/recommendations` | Top ten from hybrid by default; optional model=count/cf/content/hybrid |
| `GET /products/{product_id}/similar` | Up to ten positive content-cosine matches |
| `GET /recommendations/{batch_id}/items/{product_id}/explanation` | Verified evidence for an item actually returned in that batch |
| `GET /metrics/models` | Eight saved model/split aggregate rows, including segments |
| `GET /metrics/models/{model}` | The chosen public model's validation/test aggregates |

Products accept page 1 through 1,000,000, page_size 1 through 100 (default 20),
q up to 200 characters, and category up to 300. Extra query fields are rejected.
Pages use exact binary product-ID ordering; out-of-range pages return an empty list.
Search is normalized, case-insensitive, contiguous substring matching over title,
main category and hierarchy labels. Percent and underscore are literal characters,
not SQL wildcards. Category filtering matches a whole normalized main-category or
hierarchy label; repeated category labels do not duplicate products. Search/filter
values are passed as SQLite parameters.

`ProductSummary` exposes product_id, title, title_available, nullable main_category,
categories and recommendation_eligible. `ProductDetail` also exposes nullable
training_interaction_count and training_mean_rating. These describe historical
training ratings, not current sales, inventory or an up-to-date marketplace rating.
The one unusable title displays as `Title unavailable`; its original text remains
unchanged in the database. All 12,635 products are browsable; eligibility is true
only for the existing 11,012-product training catalog.

Profiles expose public_user_id, label, profile_type=dataset_backed and activity.
There are four profiles from each training-history bucket: light (1-2), moderate
(3-4), active (5+). Seed-42 SHA-256 ordering selects users within buckets without
looking at holdout participation or recommendation success. Keyed HMAC aliases
are stable for the same private key. Raw identities are stored only in a private
database mapping table. The inference service resolves aliases internally; public
listings never read that table and no endpoint returns raw identities. Profiles represent
historical review activity, not identified customers or application accounts.

Pydantic response models and repository allowlists restrict public fields. Errors
use `{"error":{"code":"...","message":"...","request_id":"..."}}`, with the
same ID in `X-Request-ID`. Invalid requests return 422 without echoing inputs;
unknown products/routes/users or expired batches return 404; a known product outside
the similarity catalog or the local-user capacity limit returns 409; unavailable resources return 503; unexpected
failures return a generic 500. Responses do not include local paths, stack traces,
raw dataset user IDs, or model internals.

## Local storage and frontend boundary

Catalog tables are products, product_categories, demo_profiles, dataset_user_aliases
and application_manifest. There are no holdout interactions or live preference tables.
New users live in `data/local/backend-runtime/demo_users.sqlite3`, table local_users,
independently of the frozen catalog. UUID aliases are generated by the server; input
cannot specify a raw dataset identity, profile history, rating or custom artifact.
New identities persist across restarts, up to 1,000 users, and have no training seeds.
Their IDs must be retained by the caller; the curated profile listing remains twelve.
One synthetic local identity was created by the live Stage 2 smoke test.
All databases, private keys, pointer files, audit logs and manifests remain under
the already ignored `/data/local/`; `.venv/` is also already ignored. Do not serve
these directories as static files. SQLite browsing has no new package requirement.

CORS allows exactly `http://localhost:5173`, GET/POST and Accept/Content-Type, without
credentials. This is browser-origin configuration, not authentication. Keep the
service on loopback. No public authentication, remote deployment or frontend is
included. A later React client can fetch these routes and render
titles/categories as text; it must not inject product text as HTML.

## Verification and boundaries

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p 'test_api*.py' -v
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
# Use a new report filename: this command refuses to overwrite a report.
.\.venv\Scripts\python.exe -B scripts/verify_backend.py --report data/local/backend-audit-UNIQUE.json
```

Real-artifact integration tests require prepared application data; otherwise they
report a skip. Synthetic tests use isolated local fixtures and do not need real
user identities. The delivered full suite runs both. The installed Starlette test
client currently warns that its HTTPX adapter is deprecated in favor of HTTPX2.
The approved HTTPX adapter works; HTTPX2 was not installed.

See `backend_report.md` for historical Stage 1 measurements and
`backend_stage2_report.md` for current recommendation resources and checks.
Frontend development needs separate approval. Frozen benchmark caveats remain: retrospective five-core selection,
current metadata that may postdate the training cutoff, and unreachable products
outside the primary training catalog. Neither application stage changes evaluation results.

## Frozen inference and evidence

All recommendation candidates remain in the 11,012-product training catalog.
Dataset-backed requests use only their frozen training positives (ratings 4-5)
as seeds, and all their training ratings as exclusions. The service never extends
histories with validation/test interactions, clicks or newly created demo identities.
The requested model cannot change weights, graph size, TF-IDF settings or k: k is ten.

Hybrid uses the saved default (CF 0.50/content 0.50/c=60). It ranks personalized
signals before component backfill, renormalizes missing signals per user, then
applies count fallback once. CF/content comparison requests call their original
native methods, and count uses the frozen training ranking. New identities always
receive count recommendations, including when another model was requested;
responses distinguish requested_model from model and mark cold_start=true.
Known profiles with no usable positive signals may also fall back, but do not
become new-user identities. Personalized and nonpersonalized slot counts are explicit.

Scores retain native values and an explicit score_type: normalized_weighted_rrf,
positive_cosine_sum, cosine_similarity, training_interaction_count or fallback_zero.
Native CF/content/hybrid fallback slots retain zero scores. Count-only responses,
including new-user fallback, retain training interaction-count scores. Scores must
not be formatted as probabilities or confidence percentages, or compared across
different score types. Count-only slots are nonpersonalized in response counters.

Recommendation, similarity and explanation computation is serialized with one
registry lock. Per-request evidence is captured before releasing that lock and
mutable last-result fields are cleared, including on errors. The launcher preloads
numeric libraries before applying threadpool limits, so the limit applies to the
libraries actually used. No full product-product or user-product score matrix is built.

The explanation cache is process-local: maximum 100 batches, a fixed 300-second
TTL from creation, FIFO capacity eviction, defensive copies and lazy expiry on
lookup/insertion. Reads do not extend lifetime. Cached values contain only up to
ten returned items, their traces, a private subject reference and a frozen exclusion
mask; full catalog signal vectors are not cached. Expiry, eviction and restart all
make batches unavailable with a sanitized 404. Shutdown clears the cache.

Personalized explanations replay the same frozen model/mask and verify the cached
ranking. The existing evidence helper verifies CF seed-similarity sums and shared
TF-IDF contributions. Native comparison explanations expose only their own support,
not another component's evidence. Hybrid explanations also return actual ranks,
configured/effective weights, c=60 and separate rank contributions summing to the
returned score. Reasons are deterministic templates over this evidence, not generated
claims. No purchase, causal preference or present-day availability is inferred.

At most three contributing positive-training seed products and three shared title/
category features are displayed. These are partial lists; total support fields use
all contributing seeds/features, not only the displayed examples. Fallback reasons
reference actual frozen training rating counts. Supporting products use verified
titles/categories, with nullable fields preserved consistently across endpoints.

Similarity is the existing sparse content method, excludes the query and never adds
popularity. Zero vectors return an empty list. Products outside the training catalog
are browsable but return 409 for similarity; extending their features is a future
policy decision, not an automatic change to the benchmark catalog.

Metrics are saved retrospective validation/test aggregates for all four frozen
models, including warm/cold segments, Recall@10, NDCG@10, catalog coverage and
personalization/fallback fractions. They are not recomputed from live traffic. The
original test benchmark excludes validation history as well as training history;
the serving demonstration excludes training only. These histories are explicitly
distinguished in the response. Viewing test aggregates cannot tune/retrain a model.

Example PowerShell flow after starting the server in a separate terminal:

```powershell
$shopProfiles = Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/demo/profiles'
$shopAlias = $shopProfiles.items[0].public_user_id
$shopBatch = Invoke-RestMethod "http://127.0.0.1:8000/api/v1/users/$shopAlias/recommendations?model=hybrid"
$shopProduct = $shopBatch.items[0].product.product_id
$shopBatchId = $shopBatch.batch_id
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/recommendations/$shopBatchId/items/$shopProduct/explanation"
$shopNew = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/v1/demo/users' -ContentType 'application/json' -Body '{}'
$shopNewAlias = $shopNew.public_user_id
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/users/$shopNewAlias/recommendations"
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/products/$shopProduct/similar"
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/metrics/models'
.\.venv\Scripts\python.exe -B scripts/verify_backend_stage2.py --report data/local/backend-stage2-audit-UNIQUE.json
```

The audit uses an isolated local mutable-user directory and refuses existing report
files. It measures native/API parity, explanation arithmetic, frozen-state integrity,
cache capacity, latency and memory. It does not install packages, download data,
modify the catalog, or run training/evaluation against held-out interaction rows.

Metadata attribution remains Amazon Reviews 2023, McAuley Lab, UC San Diego;
Hou et al. (2024), *Bridging Language and Items for Retrieval and Recommendation*.
The pinned source and usage discussion are documented in `metadata_text_report.md`.
Raw product metadata stays local; a code license does not imply unrestricted
redistribution rights for product content.
