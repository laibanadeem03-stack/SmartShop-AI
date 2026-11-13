# SmartShop-AI metadata ID coverage pilot

> Historical aggregate report. Use [fresh-clone setup](fresh_clone_setup.md) for current CLI arguments and output hand-offs; do not reuse old run paths or report filenames.

Completed 2026-11-11. **All 12,635 selected products have matching metadata identifiers.** This was an ID-only scan; no product-text column data pages, images, or recommendation models were acquired or trained.

## Exact source and matching reference

Official source: [McAuley-Lab/Amazon-Reviews-2023](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/tree/2b6d039ed471f2ba5fd2acb718bf33b0a7e5598e/raw_meta_Cell_Phones_and_Accessories), revision **`2b6d039ed471f2ba5fd2acb718bf33b0a7e5598e`**. Both the tree API and every shard resolve URL used this immutable revision after its discovery through HEAD. The tree's whole-object LFS SHA-256 values are recorded in the ignored result manifest. Whole-object checksums were not recomputed because doing so would require all columns.

| Parquet shard | Published bytes | Decoded ID rows | ID-column compressed bytes |
|---|---:|---:|---:|
| full-00000-of-00007.parquet | 205,041,738 | 184,070 | 2,042,763 |
| full-00001-of-00007.parquet | 193,263,612 | 184,070 | 2,041,325 |
| full-00002-of-00007.parquet | 186,934,653 | 184,070 | 2,040,808 |
| full-00003-of-00007.parquet | 178,113,001 | 184,070 | 2,039,527 |
| full-00004-of-00007.parquet | 174,751,479 | 184,070 | 2,039,306 |
| full-00005-of-00007.parquet | 164,701,086 | 184,070 | 2,039,943 |
| full-00006-of-00007.parquet | 159,266,900 | 184,070 | 2,042,623 |
| **Total** | **1,262,072,469** | **1,288,490** | **14,286,295** |

The matching reference is the exact selected product set, not the full ratings CSV or a newly sampled catalog. Selected-subset SHA-256: `feebd8873792da28db06ba4e370b9757d6eb0c476ebf7f44f6dea7f3fb3b4942`. SHA-256 of sorted exact product IDs, each followed by LF: `6de3a1adf44bd63339601e3f065ac46d056c614caa1b01e15451f136f387594f`. Existing split-manifest SHA-256: `ca61c0253b36f345c029b72532a964c88add44a3a236ad5082acd51e435f716a`.

Reference products and per-product interaction counts were checked against both the existing subset CSV and read-only evaluation SQLite aggregation. Training membership came from the existing training partition and its read-only SQLite window labels. All subset and partition checksums passed. A final local receipt recomputed the derived reference and verified unchanged SHA-256, size, and modification time for **24 protected subset/evaluation/CF files**. No original downloaded CSV or company project was accessed.

## Coverage and identifier quality

Matching is exact, case-sensitive `parent_asin` string equality. IDs are never normalized, mapped from child ASINs, or converted to numbers. Validity for this audit means exactly ten uppercase ASCII letters/digits.

| Coverage measure | Matched | Denominator | Coverage | Unmatched |
|---|---:|---:|---:|---:|
| Selected products | 12,635 | 12,635 | 100.00% | 0 |
| Training-observed product catalog | 11,012 | 11,012 | 100.00% | 0 |
| Products outside training catalog | 1,623 | 1,623 | 100.00% | 0 |
| Subset interactions, weighted by product frequency | 171,104 | 171,104 | 100.00% | 0 |

All seven shards were scanned before declaring coverage complete. Of 1,288,490 metadata rows, **1,288,489 have valid unique IDs**. There are **zero repeated valid IDs**, zero duplicate excess valid rows, zero null IDs, zero blank IDs, and **one identifier that fails the format check**. That malformed identifier is not in the selected reference. Identifier values are retained only in ignored local files and do not appear in this report.

Coverage means an ID is present; it does not establish text availability, accuracy, category quality, or when attributes became available. Matching the 1,623 products outside training does not itself make them eligible for the current frozen-catalog evaluator. No candidate catalog, evaluation protocol, CF model, or performance metric was changed.

## Method, network budget, and resources

Python standard-library HTTPS performed all pilot requests. DuckDB 2.0.0 decoded local partial Parquet caches with column projection. Its statically linked Parquet reader was already part of the approved wheel; **no DuckDB extension was installed**, and automatic extension installation/loading were disabled. The existing Python 3.14.7 venv still contains NumPy 2.5.3, SciPy 1.18.1, and pip 26.2.1. `pip check` passed.

For each file the pilot retrieved the four-byte magic header, eight-byte trailer, exact footer, and only the 185 `parent_asin` column chunks. It planned all ID bytes from the footers before acquiring those chunks. Local caches preserve original offsets, with zeros in unfetched regions. DuckDB read only the ID column data. Necessary Parquet container footers include schemas and publisher statistics for the file; these are not a guarantee of zero text fragments in container metadata and remain in ignored cache storage. No other metadata column data pages were fetched, decoded, or exported.

| Measurement | Actual |
|---|---:|
| Hard pilot HTTP response-payload budget | 104,857,600 bytes / 100 MiB |
| **Metered response payload** | **19,502,184 bytes / 18.5987 MiB** |
| ID-column chunks | 14,286,295 bytes |
| Parquet footers including trailers | 5,205,793 bytes |
| Four-byte Parquet headers | 28 bytes |
| Tree API and redirect bodies | 10,068 bytes |
| Remaining allowance | 85,355,416 bytes / 81.4013 MiB |
| HTTP request attempts, including HEAD/redirects | 1,326 |
| Automatic retries | 0 |
| Network/aggregation process elapsed time | 901.425 seconds / 15 min 1.425 sec |
| Process lifetime peak working set | 82,206,720 bytes / 78.3984 MiB |
| Working set at reporting | 61,476,864 bytes / 58.6289 MiB |
| Free disk before preparation | 28,144,099,328 bytes |
| Retained logical and allocated size at measurement | 1,285,350,411 bytes / 1,225.81 MiB |
| ID counter SQLite database | 22,802,432 bytes |

The network ledger's per-response byte totals were independently summed and verified. The user's approved accounting covers consumed HTTP response bodies, including API, redirect, and error bodies. HTTP headers and TCP/TLS overhead are excluded; this is not a packet-level measurement. Approved dependency installation and earlier browser-based source research are outside this pilot-body budget. No required measurement was left uncertain in the successful run. The ID/header/footer payload is about 1.55% of the seven full objects' size; no full object was downloaded.

Elapsed time includes remote requests, Parquet planning/decoding, and SQLite aggregation. It excludes dependency setup, local-only reference preparation, post-run audit/tests, and final result writing. A separate local projected-ID audit took 1.594 seconds and consumed **zero additional network bytes**. Peak memory is for the pilot process, not the test runner or installation process.

Windows accepted sparse flags but allocated full logical cache extents on this filesystem. Thus local partial caches occupy about 1.18 GiB despite only 18.60 MiB transferred. Unfetched data remains zeros; these files are not usable full shards. Reported allocation is a retained-size observation before final receipts, not exact peak transient disk usage. Disk remained sufficient throughout. After observing this behavior, the final script gained a tested conservative free-space check for all shard extents plus 256 MiB; this additional guard was not in the already-running network process. No network rerun was needed.

## Practicality of later selective retrieval

The local audit independently decoded the cached IDs and confirmed all 12,635 matches. They occupy **1,076 of 1,295 row groups (83.09%)**. Consequently, restricting text retrieval to matching row groups saves much less than the approximately 1% selected share of all metadata IDs might suggest. These estimates use only already acquired footers and IDs; no text data was read.

| Proposed later column | Compressed bytes in row groups containing selected IDs |
|---|---:|
| title | 89,985,017 |
| categories | 3,358,168 |
| description | 191,482,575 |
| features | 282,996,323 |
| details | 143,590,106 |
| **All five** | **711,412,189 / 678.46 MiB** |

All groups' five-column payload is 843,234,289 bytes; selected groups still need **84.37%** of it. Text pages can include nonselected products in the same group, requiring local filtering. Arbitrary-ID filtering is not a server-side capability of ordinary Parquet ranges. Row-group-selective decoding must also be validated before relying on this lower estimate; querying incompletely hydrated text columns as a full file would be unsafe.

**Recommendation:** approve a separate title-and-categories acquisition before descriptions/features/details. Their selected-group payload estimate is **93,343,185 bytes / 89.02 MiB**, versus **111,374,344 bytes / 106.21 MiB** for all groups. A separately approved **150 MiB response-payload cap** would allow a simpler full-column-projection option if selective row-group decoding is impractical, while still avoiding the full 1.26 GB dataset and all unapproved columns. Reuse this revision and local ID caches, compute exact ranges before transfer, filter exported text to selected IDs, and enforce a new explicit cap. None of the existing pilot's remaining allowance was used for text. No next-stage approval is assumed.

The present ID-only method is practical on this Windows setup, with low network payload and modest memory, but many small HTTPS requests make it slow. Later content evaluation must address the retrospective five-core selection, 2023 metadata snapshot timing, missing text, and the frozen training-catalog policy separately. ID coverage alone neither resolves cold-product ranking nor proves future content quality. If later joins ever become incomplete, preserve unmatched items for CF/popularity fallback rather than silently dropping them.

## Validation, files, setup errors, and cleanup

**68 synthetic tests passed** in 1.907 seconds: the 50 previous tests plus 18 focused pilot tests. New tests cover exact range validation, admission before network I/O, rejection of whole objects, redirect/error accounting, bounded unknown-length bodies, truncated bodies, signed-URL redaction, immutable revision/seven-shard checks, projected decoding from zero-filled partial caches, original ID identity, duplicates/invalid IDs, weighted/partial coverage, static Parquet/no HTTP extension, and conservative disk reservation. Existing data, evaluation, popularity, and CF regressions passed unchanged. `pip check` reported no broken requirements.

Created project files:

- `scripts/bounded_http.py`: bounded standard-library public HTTPS client.
- `scripts/metadata_coverage_pilot.py`: isolated reference preparation, ID-only scan, and local integrity verification.
- `scripts/audit_metadata_pilot.py`: independent local coverage/ledger audit and footer-only locality estimates.
- `tests/test_bounded_http.py` and `tests/test_metadata_coverage.py`.
- `requirements-metadata-pilot.txt`: approved DuckDB pin only.
- `docs/metadata_pilot_strategy.md` and this report.

Successful ignored run: `data/local/metadata-pilot-d11977c4ace0/`. It contains a product-only reference, input fingerprints, incomplete cache files, ID counter database, aggregate `results.json`, `post_run_integrity.json`, and `local_audit.json`. Source revision, seven LFS digests, exact ranges, metered request ledger, counts, timing, and memory are recorded there. Signed URL queries are excluded from logs. Existing `.gitignore` already protected these paths and `.venv`; no ignore-rule change was necessary.

Recovered setup issues: sandbox sockets blocked the initial pip request and initial pilot request. The approved package installation succeeded with network escalation. The first escalated pilot could not read sandbox-private existing manifests; it transferred no metadata. The solution was local-only preparation of a product reference in a new directory with inherited ACLs, followed by the network stage and local-only final verification. No existing file ACL, Git setting, or global Python setting was changed. The stopped zero-transfer run remains at `data/local/metadata-pilot-bzlqpirz/`; its zero-match fields are unresolved lower bounds, not the final coverage result.

Both pilot directories are disposable after review. Follow the exact-path, parent-boundary checks in [the cleanup procedure](metadata_pilot_strategy.md#cleanup); remove only verified `metadata-pilot-*` directories with `Remove-Item -LiteralPath`, never the local-data root or subset/evaluation/CF directories. No automatic cleanup was performed.

Dataset provenance, citation, and usage limitations are linked in [the pilot strategy](metadata_pilot_strategy.md). This delivery stops before any product-text acquisition or content/hybrid model implementation.
