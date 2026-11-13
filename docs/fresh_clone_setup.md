# Fresh-clone setup and artifact rebuilding

This is the canonical Windows x64 bootstrap recipe. It separates public source,
private generated data, and the prepared workspace. The commands below are a recipe
for a separately authorized fresh environment: **no downloads, installations, real
data preparation or model training were performed during Step 38**. They must not
be run over the existing prepared artifacts.

The current application still starts with the commands in [local_setup.md](local_setup.md).
Its new operator registration is already present locally; the existing pointer,
database, metadata, splits and model files were not rewritten.

## 1. Source and dependencies

Use an owned checkout, set its location, and choose the verified Python 3.14 executable:

```powershell
Set-Location -LiteralPath '<PROJECT_ROOT>'
$python = '<PYTHON_3_14_EXE>'
& $python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-backend.txt -r requirements-cf.txt -r requirements-content.txt -r requirements-metadata-pilot.txt
.\.venv\Scripts\python.exe -B -m pip check
```

These groups together are required for the complete app and test suite; backend-only
requirements do not include the numerical/content stack. Python 3.14.7 is the tested
release. Existing dependency pins remain unchanged. No global Python modifications
or Pandas installation is required. Other platforms are not yet verified.

Use official project-local Node **26.13.1** / npm **11.20.0**. Obtain only these files
from `nodejs.org`, into ignored `data/local/toolchains/`:

- `https://nodejs.org/dist/v26.13.1/node-v26.13.1-win-x64.zip`
- `https://nodejs.org/dist/v26.13.1/SHASUMS256.txt`

Compare `Get-FileHash -Algorithm SHA256` for the ZIP against the manifest's exact
`node-v26.13.1-win-x64.zip` entry before extraction. The previously verified ZIP hash
was `e2edda75bfb089654705cf65a13b58933bfd5f57148e8ebda916f58a2474f1f7`.
If either check differs, stop. Extract so that this executable exists:
`data/local/toolchains/node-v26.13.1-win-x64/node.exe`. Do not edit PATH or run a system installer.

Create empty project-local npm config files only if absent, then restore the lockfile:

```powershell
$tool = Join-Path $PWD 'data/local/toolchains/node-v26.13.1-win-x64'
$npmLocal = Join-Path $PWD 'data/local/frontend-stage1-20261112'
New-Item -ItemType Directory -Force -Path $npmLocal | Out-Null
foreach ($name in @('npm-user.conf','npm-global.conf')) {
    $file = Join-Path $npmLocal $name
    if (!(Test-Path -LiteralPath $file)) { New-Item -ItemType File -Path $file | Out-Null }
}
& "$tool/node.exe" "$tool/node_modules/npm/bin/npm-cli.js" --prefix frontend "--userconfig=$npmLocal/npm-user.conf" "--globalconfig=$npmLocal/npm-global.conf" "--cache=$npmLocal/npm-cache" ci --ignore-scripts --no-audit --no-fund
```

The dated npm cache directory is an intentionally fixed, auto-created launcher setting,
not a dependency on an old data/model run. Keep these empty configs private. The helper
uses them consistently and never falls back to a company/global npm configuration.

## 2. Obtain the matching ratings input

Review access/usage rights before downloading. The official
[Amazon Reviews 2023 five-core page](https://amazon-reviews-2023.github.io/data_processing/5core.html)
lists **Cell_Phones_and_Accessories**, before splitting, with schema
`user_id,parent_asin,rating,timestamp`. Use the unsplit ratings CSV, not publisher-provided
train/test partitions. Keep it outside the checkout. Verify decompressed CSV SHA-256:

`2fb7ca7f0931aca31eb00c234d254f7e207dee18c335c9aedce4ff1c23ac96d1`

Expected bytes: 159,665,421; interactions: 2,752,785. The local historical input was
inspected, but matching current public download bytes has not been independently
verified by downloading during this work. If the input differs, stop for provenance
review; do not relax the expected subset checksum or silently substitute another release.

## 3. Pass generated paths explicitly between stages

Create one new notes directory under ignored local storage. Assign each run variable
to the **exact directory printed by the immediately preceding command**. Do not copy
historical UUIDs from reports, rename a completed model directory, overwrite existing
reports, or put generated outputs in public documentation.

```powershell
$notes = Join-Path $PWD ('data/local/rebuild-notes-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $notes | Out-Null
$ratings = '<RATINGS_CSV_OUTSIDE_CHECKOUT>'
.\.venv\Scripts\python.exe -B scripts/inspect_ratings.py --dataset "$ratings" --report "$notes/inspection.md"
$inspectionScratch = '<scratch_directory printed by inspection>'
.\.venv\Scripts\python.exe -B scripts/create_subset.py --dataset "$ratings" --inspection-summary "$inspectionScratch/summary.json" --aggregation "$inspectionScratch/aggregation.sqlite3" --report "$notes/subset.md"
$subsetRun = '<subset output directory printed by subsetting>'
.\.venv\Scripts\python.exe -B scripts/evaluate_popularity.py --subset-manifest "$subsetRun/manifest.json" --report "$notes/popularity.md"
$evaluationRun = '<run_directory printed by popularity evaluation>'
.\.venv\Scripts\python.exe -B scripts/evaluate_item_cf.py --evaluation-dir "$evaluationRun" --report "$notes/item-cf.md"
$cfRun = '<run_directory printed by CF evaluation>'
```

Inspection creates its own scratch directory outside Git; its path is printed and
retained for subsetting. The source CSV remains read-only. Popularity evaluation
creates the chronological partitions itself; do not create another split first.
The deterministic seed/core policy must produce subset SHA-256
`feebd8873792da28db06ba4e370b9757d6eb0c476ebf7f44f6dea7f3fb3b4942`.
The fixed protocol retains 171,104 interactions, 12,635 products and an 11,012-product
training catalog. A different graph needs a separate experiment/policy review.

## 4. Pinned, bounded metadata acquisition

Both acquisition stages use the same approved immutable Hugging Face revision:
`2b6d039ed471f2ba5fd2acb718bf33b0a7e5598e` of
`McAuley-Lab/Amazon-Reviews-2023`. The ID pilot verifies the requested revision in
the response; it never resolves `main`. This release rejects a different pipeline pin
before acquisition. Text acquisition reuses that verified pilot and pin.

```powershell
.\.venv\Scripts\python.exe -B scripts/metadata_coverage_pilot.py --prepare-only --evaluation "$evaluationRun" --cf-artifacts "$cfRun" --revision 2b6d039ed471f2ba5fd2acb718bf33b0a7e5598e
$pilotRun = '<prepared ID-pilot directory printed above>'
.\.venv\Scripts\python.exe -B scripts/metadata_coverage_pilot.py --prepared-run "$pilotRun"
.\.venv\Scripts\python.exe -B scripts/metadata_coverage_pilot.py --verify-run "$pilotRun"
.\.venv\Scripts\python.exe -B scripts/acquire_metadata_text.py --prepare --pilot "$pilotRun"
$metadataRun = '<prepared_directory printed by text preparation>'
.\.venv\Scripts\python.exe -B scripts/acquire_metadata_text.py --acquire "$metadataRun"
.\.venv\Scripts\python.exe -B scripts/acquire_metadata_text.py --verify "$metadataRun"
```

ID responses remain bounded to 100 MiB; total ID+text response payloads to 150 MiB,
including retries under the existing accounting. No full-shard or unbounded fallback
is permitted. Stop on budget/validation failure. Do not restart a stopped run with a
fresh allowance. Use `--recover` only for the existing validated pre-body recovery
case; it is not required after ordinary success. Verification now binds its receipt
to the exact normal or recovered result file. Legacy verified receipts remain supported.

Partial Parquet files may allocate full logical extents on Windows; allow several GiB
of free local disk. The scripts perform per-stage disk checks. Never share partial
caches, selected text, identifiers or raw HTTP ledgers as source artifacts.

## 5. Content and hybrid artifacts

```powershell
.\.venv\Scripts\python.exe -B scripts/evaluate_content.py --evaluation "$evaluationRun" --metadata "$metadataRun" --cf "$cfRun" --report "$notes/content.md"
$contentRun = '<ignored content run directory recorded by the report>'
.\.venv\Scripts\python.exe -B scripts/evaluate_hybrid.py --evaluation "$evaluationRun" --content "$contentRun" --cf "$cfRun" --report "$notes/hybrid.md"
$hybridRun = '<ignored hybrid run directory recorded by the report>'
```

These commands train/evaluate **new** artifacts and are included only as a future
rebuild recipe. They were not executed for Step 38. Existing files/reports are refused,
not overwritten. Producers keep local absolute lineage paths; registration uses
checkout-relative paths. Rebuild at the final checkout location: copying or relocating
old absolute-path manifests is not a supported shortcut. No original manifest should
be edited to make a relocated bundle appear valid.

## 6. Explicit registration, then SQLite preparation

Inspect the successful pipeline reports and verified acquisition receipt. Registration
is a local operator trust action, not automatic discovery and not a way to bless
unknown joblib/pickle files. The approved serving policy remains Hybrid 0.50/0.50,
c=60, CF K=50/lambda=10 and content df=2/title weight=0.80. If a rebuilt selection differs,
stop for review rather than changing the selection or bypassing validation.

```powershell
$metadataFile = Join-Path $metadataRun 'selected_metadata.jsonl'
$metadataSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $metadataFile).Hash.ToLowerInvariant()
# Independently compare metadataSha with the successful verified acquisition receipt.
.\.venv\Scripts\python.exe -B scripts/configure_serving.py --hybrid "$hybridRun" --metadata "$metadataFile" --metadata-sha256 "$metadataSha"
.\.venv\Scripts\python.exe -B scripts/prepare_application_data.py --activate
```

`data/local/serving-artifacts.json` pins every model-loader JSON/NPZ/joblib input and
selected metadata before deserialization. It verifies result/selection/component
lineage, frozen control results and the strict validation gate, then preserves native
fingerprint, ID/catalog alignment and database provenance checks. The operator-owned
registration is the root of trust: checksums do not authenticate an attacker who can
rewrite that root and all source artifacts/code. Never expose this file through an API.

The metrics hash is now pinned per registered build, rather than compiled from one
run's timing/path-dependent JSON. New application manifests additionally bind the
registration file hash. A fresh private alias key is generated locally; it must not
be copied from this workspace or published. New aliases may differ without changing
model rankings or historical evaluation.

To register against an already prepared catalog, additionally pass
`--application-manifest data/local/application-current.json`; its model/metadata/database
digests must agree. Registration and application activation refuse overwrite. A later
independently reviewed registration can use `--output data/local/serving-NEW.json` and
the process-local `SMARTSHOP_SERVING_CONFIG` setting. A subsequent catalog can use
`SMARTSHOP_APP_MANIFEST` as documented in [backend_architecture.md](backend_architecture.md).
Existing prepared workspaces may retain the legacy application pointer: its hashes
and the immutable catalog's model/metadata provenance are still enforced.

## 7. Start and verify

Use [local_setup.md](local_setup.md) for two-terminal startup, tests and localhost
production preview. No startup path rebuilds/trains models or downloads metadata.
Native-model APIs remain training-snapshot-only and keep the same public contracts.

Public source, pinned manifests/dependencies, synthetic tests and rebuilding code can
be shared after review. Full reproduction still requires lawful access to the exact
ratings/metadata snapshot, sufficient resources, and a separately authorized real-data
rebuild. Dataset availability is not a redistribution license. Keep all data, text,
private mappings, registrations, databases, model bundles and generated QA files local.
The [README](../README.md) and [portfolio notes](portfolio_publication.md) now document
the application and two reviewed interface-only captures. Step 40 prepared the
[MIT License](../LICENSE) for authorized original code/documentation with separate
[third-party notices](../THIRD_PARTY_NOTICES.md). Broader screenshot/data redistribution
and publishing remain pending approval.
