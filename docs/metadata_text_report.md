# SmartShop-AI title/category acquisition

> Historical aggregate report. Use [fresh-clone setup](fresh_clone_setup.md) for current CLI arguments and output hand-offs; do not reuse old run paths or report filenames.

Completed 2026-11-11. **All 12,635 selected products were retrieved and all four original field values were verified.** Data is ready for a separately approved first TF-IDF content baseline. No vectorizer, recommendation model, or application feature was implemented.

## Source and output

Official source: [McAuley-Lab/Amazon-Reviews-2023](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/tree/2b6d039ed471f2ba5fd2acb718bf33b0a7e5598e/raw_meta_Cell_Phones_and_Accessories), pinned revision `2b6d039ed471f2ba5fd2acb718bf33b0a7e5598e`. Reused the seven verified Parquet shard identities, local container/ID caches, and exact product-only reference from the [ID coverage pilot](metadata_coverage_report.md).

Only `parent_asin`, `title`, `main_category`, and `categories` were decoded. Parent IDs came from cached column data; new range requests acquired the other three columns across all row groups. Full-column projection was explicitly planned because it fits the budget and permits straightforward local decoding. Compressed chunks necessarily include other products; exports contain selected products only. No descriptions, features, details, images, or video data pages were fetched. Existing container footers were reused locally rather than downloaded again.

Ignored output directory: `data/local/metadata-text-941cdc696d4e/`.

- `selected_metadata.jsonl`: exactly four original fields, sorted by exact product ID; **4,111,286 bytes / 3.921 MiB**.
- `selected_metadata.sqlite3`: the matching records, with the original category arrays serialized as JSON; **3,530,752 bytes / 3.367 MiB**.
- Plan, product reference, source fingerprints, metered/redacted ledgers, incomplete column caches, initial stopped result, final `results_recovery.json`, and `post_run_integrity.json`.
- JSONL SHA-256: `12b6cfb3a1e664ff0d2273b6f6aeddc0dda9a94aee7d8bfcc5b02876f56d178b`.

No raw metadata or identifier values are included in tracked documentation. The existing `/data/local/` ignore rule covers all generated outputs; no Git settings or ignore rules changed.

## Actual coverage and quality

| Measure | Result |
|---|---:|
| Selected product ID coverage | 12,635/12,635 — 100% |
| Training-catalog ID coverage | 11,012/11,012 — 100% |
| Outside-training-catalog ID coverage | 1,623/1,623 — 100% |
| Interaction-weighted ID coverage | 171,104/171,104 — 100% |
| Matching records / distinct IDs | 12,635 / 12,635 |
| Duplicate IDs / excess duplicate records | 0 / 0 |
| Null titles / whitespace-empty titles | 0 / 0 |
| Nonlexical, effectively unusable titles | 1 |
| Usable titles | 12,634 — 99.9921% |
| Empty `categories` arrays | 521 — 4.1235% |
| Missing/unusable `main_category` | 206 — 1.6304% |
| Products missing both category sources | 0 |
| Products with any usable approved text | 12,635 — 100% |
| Products with category text only | 1 |

Quality checks unescape HTML entities, remove tags, trim whitespace, reject common null placeholders, and require a Unicode word character. This transformation is diagnostic only: stored strings, arrays, nulls, ordering within category arrays, Unicode, and IDs remain unchanged. The one unusable title is nonlexical, not a null or blank field. There are no null category arrays; all 521 unavailable hierarchies are empty arrays and have usable main-category text. Missing main-category values have usable hierarchy text.

Usable titles have a median **153 characters / 25 word tokens**, with character lengths 9–490. There are **12,577 distinct normalized usable titles**; 50 title strings repeat across product IDs, accounting for 57 additional records. Ten usable titles contain fewer than three word tokens. These records remain distinct; no title-based deduplication or row removal occurred.

## Budget, resources, and recovered error

The 150 MiB cumulative cap conservatively includes the earlier ID pilot, leaving 131.4013 MiB for this stage. All redirect/error bodies and retries share the meter; HTTP headers and TCP/TLS overhead remain excluded under the approved accounting.

| Measurement | Actual |
|---|---:|
| New column data planned from cached footers | 112,353,284 bytes |
| New text-stage response payload, including redirects/recovery | **112,361,990 bytes / 107.1567 MiB** |
| Earlier ID pilot response payload | 19,502,184 bytes / 18.5987 MiB |
| **Combined response payload** | **131,864,174 bytes / 125.7555 MiB** |
| Hard cumulative cap | 157,286,400 bytes / 150 MiB |
| Remaining cumulative allowance | 25,422,226 bytes / 24.2445 MiB |
| Text-stage request attempts, including redirects/failure | 2,599 |
| Explicit transport recovery / further automatic retries | 1 / 0 |
| Acquisition active runtime, both attempts | **1,268.795 seconds / 21 min 8.795 sec** |
| Acquisition wall time, including recovery investigation | 1,506.233 seconds / 25 min 6.233 sec |
| Local preparation / final verification | 11.013 / 12.123 seconds |
| Peak acquisition working set, maximum of both processes | **85.633 MiB** |
| Peak final-verification working set | **92.746 MiB** |
| Retained new-run allocation before final result/receipt writes | 1,271,030,427 bytes / 1,212.15 MiB |

New column data comprises title 107,389,259 bytes, main category 978,940 bytes, and hierarchy 3,985,085 bytes; redirects add 8,706 bytes. Memory figures are process lifetime peaks; preparation memory was not separately profiled. Disk is retained allocation, not exact transient peak. Windows allocated full logical cache extents, with zeros in unfetched regions; these are incomplete files, not full downloaded shards.

One HTTPS failure occurred during shard three before a response status/body was read; its underlying cause is unknown. Recovery preserved the initial ledger, carried forward 47,760,631 already-transferred bytes, validated/skipped completed ranges, and resumed on a fresh connection. Connections closed between later shards. There was no partial-body retry, budget reset, full-shard fallback, authentication change, or new dependency. Final ledger totals and the cap were independently verified.

## Verification and reproducibility

**84 synthetic tests passed** in 2.283 seconds: the previous 68 plus 16 tests for the extended client and text acquisition. Tests cover all forbidden column families (including nested video titles), partial-cache decoding, exact values/Unicode/IDs, selected-only export, duplicate/missing-field reporting, deterministic output, persistent-connection disposal, default 100 MiB ceiling preservation, explicit 150 MiB ceiling, shared-budget retrying, and rejection of partial or out-of-order recovery ranges. `pip check` passed; DuckDB 2.0.0, NumPy 2.5.3, SciPy 1.18.1, and pip 26.2.1 remain unchanged. No package or DuckDB extension was installed.

The separate final audit verified every original field against both SQLite and JSONL using local projected caches, the JSONL checksum, unchanged product reference, ledger totals, and cap. SHA-256, sizes, and modification times of **52 existing subset, split, popularity/evaluation, CF, and ID-pilot artifact files remained unchanged**. The original full CSV and company projects were not accessed. Audit network use was zero.

Created `scripts/acquire_metadata_text.py`, `tests/test_metadata_text.py`, and this report. Updated `scripts/bounded_http.py` and its tests for explicit ceilings, optional connection reuse, and redirect-budget admission; existing pilot callers retain their original defaults. Updated the project plan's metadata status only.

```powershell
.\.venv\Scripts\python.exe -B scripts/acquire_metadata_text.py --prepare
.\.venv\Scripts\python.exe -B scripts/acquire_metadata_text.py --acquire data/local/metadata-text-UNIQUE
# Only for a validated, fully metered pre-body failure; refuses a second recovery:
.\.venv\Scripts\python.exe -B scripts/acquire_metadata_text.py --recover data/local/metadata-text-UNIQUE
.\.venv\Scripts\python.exe -B scripts/acquire_metadata_text.py --verify data/local/metadata-text-UNIQUE
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
```

Do not restart a partial operation with a new allowance or run directory. A new acquisition requires its own reviewed budget; the existing complete local metadata is reusable without network access. After review, disposable partial caches may be removed only with exact-path checks inside this run directory, preserving the JSONL, SQLite, manifests, and receipts. No cleanup was performed.

## Readiness and attribution

**Titles plus available category fields are sufficient for a manageable first TF-IDF baseline.** Titles supply varied lexical content and category fields cover every selected product. Keep the one nonlexical-title record, but treat its category-only profile as weak and retain CF/popularity fallback. Repeated titles, generic categories, compatibility wording, and noisy marketing terms limit lexical similarity; quality diagnostics are not semantic validation or evidence of recommendation performance.

The 2023 metadata snapshot has no historical field-availability guarantee for the earlier training cutoff. Retrospective five-core selection and future attribute information remain evaluation limitations. Metadata coverage does not automatically expand the frozen training candidate catalog or resolve cold-product evaluation policy. Those decisions, TF-IDF dependencies/fitting, and any content/hybrid recommendations require separate approval.

Dataset attribution: **Hou et al. (2024), [Bridging Language and Items for Retrieval and Recommendation](https://arxiv.org/abs/2403.03952)**; Amazon Reviews 2023, McAuley Lab, UC San Diego. See the [official dataset card](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/blob/2b6d039ed471f2ba5fd2acb718bf33b0a7e5598e/README.md) and [maintainer usage discussion](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/discussions/1). A code license is not assumed to grant unrestricted redistribution rights over product content. Raw metadata remains local.
