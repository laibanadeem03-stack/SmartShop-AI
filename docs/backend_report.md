# SmartShop-AI backend Stage 1 results

Historical Stage 1 report. Stage 2 is now complete; see `backend_stage2_report.md`
for recommendation, explanation and metrics endpoints, current tests and resources.

Stage 1 is complete: localhost FastAPI foundation, frozen-artifact readiness,
reproducible application SQLite preparation, products, anonymous profiles and API
contracts. No Stage 2 routes or frontend were implemented.

## Data and integrity

| Check | Result |
|---|---:|
| Browsable products | 12,635 |
| Training-catalog eligible | 11,012 |
| Outside training catalog | 1,623 |
| Usable original titles | 12,634 |
| Missing/unusable-title display fallbacks | 1 |
| Anonymous profiles | 12 |
| Profiles per light/moderate/active bucket | 4 / 4 / 4 |
| Held-out interactions loaded into application data | 0 |

All four metadata fields were compared exactly against the verified source after
database insertion. Integration tests paginated through all products and verified
metadata, display fallbacks, uniqueness, total counts and every eligibility flag.
Every private profile mapping belongs to the frozen training snapshot. Serving
startup and endpoints pass an integration guard that rejects reads of validation,
test or subset CSVs; training functions are patched to raise during integration.

The metadata SHA-256 remains
`12b6cfb3a1e664ff0d2273b6f6aeddc0dda9a94aee7d8bfcc5b02876f56d178b`.
Two independent final preparation runs produced the identical database SHA-256:
`646e41199346597a5014218168fd115bd8af66fecde9c2829ed750aab171fce0`.
They reused the same private alias key; labels and private mappings are reproducible.
No raw identities or product records appear in this report.

Active database: `data/local/application-d9f51414e4b3/app.sqlite3`.
Reproduction copy: `data/local/application-0e4c661fdc16/app.sqlite3`.
Default pointer: `data/local/application-current.json`.
Private key: `data/local/backend-demo-alias-key.bin`.
Audit receipts: `data/local/backend-stage1-20261112/`.
All these paths are Git-ignored. No existing data or model file was rewritten.

## Dependencies

Installed FastAPI 0.162.5, Pydantic 2.14.3, Uvicorn 0.54.0, HTTPX 0.28.1 and
their required dependencies, exactly pinned in `requirements-backend.txt`.
Seventeen packages were added; no preexisting package version changed. In
particular NumPy 2.5.3, SciPy 1.18.1 and scikit-learn 1.9.1 remain unchanged.
Imports and pip check passed. No optional Uvicorn extras, ORM, HTTPX2, global
packages, or model/data downloads were added. The required opentelemetry-api
dependency does not add an exporter or configure telemetry in this application.

## Resources and API checks

| Measurement | Observed |
|---|---:|
| Final active database preparation, excluding imports/Python startup | 1.762 s |
| Independent reproduction preparation, excluding imports | 1.857 s |
| Active preparation peak working set | 169.57 MiB |
| Database size per copy | 12,906,496 bytes / 12.31 MiB |
| API lifespan startup, in-process audit | 2.536 s |
| Launch to successful readiness, actual localhost Uvicorn process | 3.811 s |
| In-process endpoint audit elapsed, excluding initial imports | 6.284 s |
| In-process audit lifetime peak working set | 190.41 MiB |
| Audit recommendation calls | 0 |

The preparation checked 128 MiB minimum free disk; about 21.96 GiB was available
at the initial environment check. Active and reproducibility database copies total
24.62 MiB, plus small manifests, private key and audit/install/test logs. Model
files are referenced in place, not copied or trained. Peak working set is a
process-lifetime Windows measure, not isolated incremental model memory.

Each endpoint below was measured for 50 sequential requests using TestClient;
timings include HTTPX/ASGI dispatch, validation, SQLite and JSON serialization,
but exclude real socket transport and concurrent load.

| Endpoint operation | Median ms | p95 ms |
|---|---:|---:|
| Liveness | 3.555 | 4.585 |
| Readiness | 3.400 | 4.315 |
| Product page | 5.226 | 6.372 |
| Title/category substring search | 35.298 | 36.555 |
| Exact normalized category filter | 15.629 | 16.569 |
| Product detail | 4.038 | 5.320 |
| Demo profiles | 4.623 | 6.070 |

The separate real-loopback smoke test used the delivered `python -B -m backend`
launcher on 127.0.0.1:8000 with one worker. Readiness, product browsing and profile
listing returned 200 with the correct totals; the unauthorized metrics endpoint
returned 404. That temporary server was stopped after verification. These timings
are local observations, not production latency guarantees.

## Tests, fixes and limitations

All 151 tests passed: the original 120 plus 26 new synthetic contract/preparation
tests and five real-artifact integration tests. Coverage includes search/filter
semantics, stable pagination, metadata preservation, SQL injection literals,
schema rejection, missing titles, cold-catalog products, alias privacy, error
redaction, CORS allowlisting, read-only connections, artifact failure, checksum
tampering, missing resources, reproducibility, shutdown and absent Stage 2 routes.
The final suite took 7.058 seconds, excluding interpreter/import startup. SHA-256,
size and modification-time checks verified 148 preexisting files unchanged; the
only intentional change among 149 inventoried existing files was project_plan.md.
This inventory includes the existing ML code, data, metadata, split and model
artifacts. No prior benchmark was recomputed or tuned during this application phase.
New local output totaled about 25.26 MiB before the final delivery receipt, including
the active database, reproduction copy and audit/install/test logs.

The initial synthetic run exposed two Windows cleanup errors from unclosed test
SQLite handles; those handles now close explicitly. A live-launch check also
exposed owner-only permissions on newly created temporary directories. Application
preparation now uses ordinary exclusive mkdir and inherits local workspace access.
The separate network-enabled tool account could not read older owner-only frozen
artifact directories. The same-account loopback test passed without altering any
existing artifact permissions. Launching under another OS account requires that
account already have read access; permission changes are outside this stage.

Starlette emits a deprecation warning for its functioning HTTPX-based test client.
No unapproved replacement dependency was installed. A plain substring scan is
sufficient for this catalog but search is the slowest implemented endpoint; FTS
can be considered after measuring frontend needs. Readiness validates resources
at startup, rather than continuously detecting external edits. Never edit the
active immutable database in place.

Anonymous aliases are not authentication; this service is for loopback use.
Historical review activity is not a real customer account. No held-out history,
new-user preference learning, inference endpoint, similarity, explanations, metrics
route, React UI or deployment/authentication system is part of this delivery.
The existing hybrid/CF/content/popularity artifacts and retrospective evaluation
limitations remain unchanged. Dataset attribution and usage constraints remain
as documented in `metadata_text_report.md`.

## Files

Created 26 project files; modified only docs/project_plan.md. Complete inventory:

```text
backend/__init__.py
backend/__main__.py
backend/app/__init__.py
backend/app/config.py
backend/app/dependencies.py
backend/app/errors.py
backend/app/main.py
backend/app/schemas.py
backend/app/repositories/__init__.py
backend/app/repositories/sqlite_repository.py
backend/app/routers/__init__.py
backend/app/routers/health.py
backend/app/routers/products.py
backend/app/routers/users.py
backend/app/services/__init__.py
backend/app/services/catalog_service.py
backend/app/services/identity_service.py
backend/app/services/model_registry.py
scripts/prepare_application_data.py
scripts/verify_backend.py
requirements-backend.txt
tests/backend_fixtures.py
tests/test_api_contracts.py
tests/test_api_integration.py
docs/backend_architecture.md
docs/backend_report.md
docs/project_plan.md (updated)
```

Private database/key/pointer/manifests and installation/audit/test receipts are
under the ignored local paths listed above. The delivery receipt records exact
file hashes and the environment inventory. No existing Git ignore rule changed.

Run and test commands are in `backend_architecture.md`. No Git settings, remotes,
commits or pushes were changed. No company project was accessed. Stop for review
before Stage 2.
