# Bounded metadata ID coverage pilot

This phase measures product-ID coverage only. It does not authorize product-text acquisition, content models, or changes to ratings, chronological partitions, or collaborative artifacts.

## Source and dependencies

Use the official [McAuley-Lab Amazon Reviews 2023 repository](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/tree/main/raw_meta_Cell_Phones_and_Accessories). Resolve its exact 40-character revision with a HEAD request, then enumerate the seven `full-00000-of-00007.parquet` through `full-00006-of-00007.parquet` files at that revision. Record published sizes and LFS SHA-256 values. Those LFS digests identify whole objects; a projected read cannot verify their whole-file checksums without downloading the other columns.

The only added dependency is user-approved `duckdb==2.0.0` in the existing Python 3.14 `.venv`. Its Parquet reader is statically linked. `httpfs` is neither installed nor loaded; extension auto-install and auto-loading are disabled. HTTPS and SQLite use Python's standard library. No global Python change is required.

## Projection and metering

1. Verify the existing subset and all partition checksums. Build a product-only matching reference from the selected subset; independently check it against read-only evaluation SQLite aggregation. Match exact strings without trimming, case conversion, or child/parent-ASIN substitution.
2. Fingerprint the existing subset, partitions, evaluation database, manifest, and CF artifact files. Only the new ignored directory receives writes.
3. For each shard, request its final eight bytes, four-byte header, and exact Parquet footer. Container metadata supplies schema and chunk offsets; it can also contain publisher statistics and is retained only in ignored caches. No product-text column data pages are requested.
4. DuckDB's local `parquet_metadata` function identifies only top-level `parent_asin` chunk ranges. Reject invalid or overlapping offsets. Merge exactly adjacent ranges only; never fetch gaps containing other columns. Sum all planned ID payload bytes before requesting them. Stop if the plan exceeds the remaining budget.
5. Request exact byte ranges with identity encoding. Require HTTP 206, the exact Content-Range, and the expected Content-Length. Reject HTTP 200 and mismatched/encoded responses without a full-file fallback. Create exclusive partial cache files at original offsets; unfetched columns contain zeros. These files are deliberately incomplete Parquet objects, not complete downloaded shards. They must never be used for text queries or copied as complete datasets.
6. Decode `SELECT parent_asin` locally in batches of 8,192 rows. Count valid IDs and repetitions in a new SQLite table with binary string keys. Aggregate overall, training-catalog, outside-training-catalog, and subset-interaction-weighted coverage. Scan every shard before declaring any target unmatched.
7. Locally verify protected checksums, file sizes, and modification times again. Save a separate receipt, because the network-enabled process cannot read sandbox-private existing artifacts.

The hard limit is **104,857,600 bytes (100 MiB)** of HTTP response payload consumed by the pilot client. The shared meter includes repository API bodies, redirects, error bodies, partial reads, and any attempted requests. There are no automatic retries. The user approved exclusion of HTTP headers and TCP/TLS overhead; these are not packet-capture or billed-egress figures. Approved pip installation and earlier browser-based source research are separate from pilot payload accounting. Unknown-length API bodies have explicit small body limits and the shared cap. Unexpected responses that cannot be fully accounted for cause an immediate stop and an incomplete-measurement flag; no exact successful-network-volume claim is made for those runs.

## Local isolation and commands

The root `.gitignore` already excludes `/data/local/` and `/.venv/`. Preparation creates a new uniquely named directory under that local-data root, refusing existing files. It contains a product-only reference, aggregate input audit, ID SQLite counts, redacted HTTP ledger, partial cache, and results. Raw product IDs stay there; no user IDs are exported. Windows directories use inherited ACLs so the approved network identity can read this new reference, without changing any existing ACL.

```powershell
.\.venv\Scripts\python.exe -B scripts/metadata_coverage_pilot.py --prepare-only
# Use the exact directory printed above; network access may require sandbox approval.
.\.venv\Scripts\python.exe -B scripts/metadata_coverage_pilot.py --prepared-run data/local/metadata-pilot-UNIQUE
.\.venv\Scripts\python.exe -B scripts/metadata_coverage_pilot.py --verify-run data/local/metadata-pilot-UNIQUE
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -I -B -m pip check
```

A prepared run is single-use: cache creation and output writes are exclusive. Do not restart with a fresh 100 MiB allowance after a partial transfer; account for previously consumed payloads before any separately reviewed recovery. An interrupted process without a persisted ledger cannot establish its complete transfer cost and must not trigger an automatic retry.

SQLite uses an 8 MiB page cache; DuckDB has a 256 MB memory limit and two threads. Neither limit is a process working-set guarantee. Check at least 768 MiB free before preparation; after listing shard sizes, the final script also checks space for all seven logical cache extents plus 256 MiB. Actual cache allocation must be reported. Sparse flags do not guarantee low physical allocation on every Windows filesystem. Runtime includes HTTP latency, ID decoding, and SQLite aggregation; process lifetime peak working set is measured through Windows process counters. Retained disk allocation is not a claim about exact peak transient disk use.

## Tests, interpretation, and next review

Synthetic tests cover range validation, budgets before I/O, redirect/error accounting, bounded unknown-length responses, no full-object fallback, redacted signed URLs, immutable revision/shard validation, partial-cache ID decoding, exact ID preservation, duplicate/invalid identifiers, weighted coverage, incomplete-scan semantics, and disabled extension installation. Existing data/evaluation/CF tests must still pass.

ID availability does not establish that titles/descriptions are populated or useful. Matching modern metadata does not establish that attributes existed before the chronological training boundary. The retrospective five-core selection and metadata snapshot can both introduce future-information bias; no ranking/evaluation policy changes are made here. Unmatched products remain eligible for existing CF/popularity fallback after later review.

For any later text acquisition, first estimate the compressed text chunks for row groups that contain selected IDs. Parquet projection reduces columns; it does not provide server-side arbitrary-ID filtering within a chunk. Spread-out IDs may require most text chunks despite matching only a small percentage of all metadata rows. A separate text-transfer budget and approval are required.

The [dataset card](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023) requests attribution to Hou et al. (2024), *Bridging Language and Items for Retrieval and Recommendation*, and its upstream sources. The [maintainer's licensing discussion](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/discussions/1) does not establish a blanket redistribution license for Amazon content. A code repository's license should not be treated as a product-content license. Keep content local and review usage terms before any later publication or deployment.

## Cleanup

Nothing is deleted automatically. After review, remove only the exact pilot run directories listed in the coverage report. Resolve each absolute path, verify its parent is this project's `data/local`, verify its leaf starts with `metadata-pilot-`, and use PowerShell `Remove-Item -LiteralPath <verified-path> -Recurse`. Never target `data/local` itself, use wildcard deletion, or remove existing evaluation/subset/CF directories. Keep the aggregate Markdown report and code; ignored ID/cache files are disposable. No cleanup is performed as part of this delivery.
