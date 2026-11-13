# SmartShop-AI TF-IDF content strategy

This phase adds an independently evaluated content recommender. It does not combine CF/content/popularity scores, expand the primary catalog, acquire metadata, or implement application features. Count popularity is backfill, matching the existing CF protocol.

## Environment and verified inputs

Use the existing ignored `.venv`, Python 3.14.7. `requirements-content.txt` pins NumPy 2.5.3 and SciPy 1.18.1 unchanged, plus the approved scikit-learn 1.9.1, joblib 1.6.0, narwhals 2.28.0, threadpoolctl 3.8.0, and cloudpickle 3.1.2. Binary-wheel installation used `--no-deps` so no unapproved additions/upgrades could occur; imports and `pip check` passed. Global Python is unchanged. The sandbox blocked initial PyPI access; the approved network escalation installed the same five-package set.

Reuse `data/local/evaluation-ej957b9_/split_manifest.json`, the verified `data/local/metadata-text-941cdc696d4e/selected_metadata.jsonl`, and frozen CF artifacts in `data/local/item_cf-gm9467qd/`. The original full CSV is never accessed. Only metadata `parent_asin`, `title`, `main_category`, and `categories` are used. Metadata source and attribution are recorded in `docs/metadata_text_report.md`; its JSONL SHA-256 is `12b6cfb3a1e664ff0d2273b6f6aeddc0dda9a94aee7d8bfcc5b02876f56d178b`.

Original ratings, IDs, timestamps, metadata and existing artifacts are read-only. Hash, size, and modification-time checks protect their integrity. Test interaction/checksum reads and prior control-result loading are deferred until a persisted validation-selection file exists.

## Text representation

Create derived text only: unescape HTML, remove comments and tags, casefold and collapse whitespace. Preserve model numbers, single-character words, negation, Unicode, and technical strings such as USB-C/PD/20W. IDs are exact join keys, never text features. Main-category and hierarchy labels are normalized and deduplicated while retaining order. Null, placeholder, punctuation-only, and empty text becomes an empty derived field; raw values remain unchanged.

Fit one document per unique **training-catalog product**, in sorted original-ID order: 11,012 products. Metadata for the 1,623 products outside that catalog never contributes to vocabulary or IDF. There is no interaction-frequency weighting of documents.

Separate title/category `TfidfVectorizer` models use word unigrams/bigrams, token pattern `(?u)\b\w+\b`, `float32`, L2 normalization, smoothed IDF, sublinear TF, no stop-word list, and `max_df=0.95`. Caps are 45,000 title and 5,000 category features. The two field fits for each min_df are reused for both weights. An empty/pruned field gets a sparse zero-width block; it never drops a product.

For title weight alpha, concatenate `sqrt(alpha)*title_vector` and `sqrt(1-alpha)*category_vector`, then L2-normalize the combined row. Renormalization handles unavailable fields. This weighting is within the content representation; it uses no collaborative scores.

Four configurations and exact-NDCG tie priority, fixed before evaluation:

1. `tfidf_df2_title80`: min_df=2, alpha=0.80.
2. `tfidf_df2_title95`: min_df=2, alpha=0.95.
3. `tfidf_df1_title80`: min_df=1, alpha=0.80.
4. `tfidf_df1_title95`: min_df=1, alpha=0.95.

Select the largest validation macro NDCG@10; first listed wins an exact tie. No test-driven parameter revision or automatic project-default replacement occurs.

## Profiles, cosine scoring and fallback

Reuse the existing training-only positive matrix builder. Ratings 4 and 5 are equal positive seeds; 1–3 do not seed a profile and all ratings remain seen exclusions. Sum a user's normalized item vectors and normalize the sparse result; this equals the normalized mean. Profiles contain training interactions only, remain frozen for test, and are calculated on demand rather than materializing a dense user-feature table.

Score one profile against the product matrix with a sparse dot product. Both sides are normalized, so this is cosine similarity. Rank all strictly positive unseen scores by descending score, descending training interaction count, then exact product ID. No score rounding or negative sampling is used. One related-product query also produces only one score column and excludes itself. Never construct the full product-product similarity matrix, even as a nominally sparse object; generic shared terms could make it nearly dense.

Cold users, users without usable positive seeds, zero vectors, and short candidate lists use the frozen count ranking as backfill. Backfill scores are zero and prediction source labels distinguish `content` from `popularity_fallback`, consistently with the CF evaluator's interface. Zero-vector catalog items remain eligible for popularity backfill. No records are silently removed or attributes invented.

## Chronological evaluation and reporting

Reuse all existing split bytes and cutoffs: train 136,883, validation 17,110, test 17,111 interactions. Validation excludes all training history. Test excludes training plus validation history; validation does not change profiles, vocabularies, IDF, or count statistics. All primary candidates are the original 11,012 training products. The 1,623 outside-training products remain unreachable targets in overall denominators.

Use the unchanged evaluator callback and metric definitions. Recall/NDCG use binary 4–5-star relevance and the positive-user cohort. Users without positive targets remain separately counted. Catalog coverage uses the same positive-user cohort and full training catalog denominator. Personalization/fallback rates use all holdout users. Report overall, warm/cold-user, four user/product warm/cold segments, and history buckets; segment users can overlap.

After selection, replay count and the saved K50/lambda10 CF graph, without rebuilding CF similarities. Require identical validation/test cohorts, segment metrics and prediction hashes versus prior runs. Freeze feature/IDF/profile/popularity fingerprints before test and verify afterward. Report actual model sparsity, zero vectors, vocabulary sizes, payload/file sizes, phase runtime, process working set, median/p95 recommendation latency, and source integrity. Cold-product reachability does not improve merely because metadata exists.

## Reproduction, tests and artifacts

```powershell
.\.venv\Scripts\python.exe -I -B -m pip check
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
.\.venv\Scripts\python.exe -B scripts/evaluate_content.py
```

The CLI fixes native numeric thread pools to one for reproducibility and creates an exclusive unique directory under ignored `data/local/content-tfidf-*`. A rerun needs a new report filename, supplied with `--report docs/content_report_rerun.md`; it does not overwrite existing artifacts or reports.

Each run stores environment versions, two vectorizer pairs, sparse field/combined matrices, training positive matrix, the frozen all-rating count/history snapshot and count ranking, original string-ID mappings, validation predictions for four configurations, frozen selection, selected test predictions, replayed control predictions, input-integrity receipts, model hashes and aggregate results. `content_tfidf.load_artifacts(run_directory)` verifies and reloads the selected inference bundle without reading training CSVs. The trusted local joblib artifacts also permit later text transformation. IDs and raw text never belong in tracked reports.

Synthetic tests cover cleaning/model numbers, category deduplication, train-only vocabulary/IDF, future-only tokens, row/ID alignment, hand-computed weighted cosine, float32/CSR/caps, deterministic ties, negative-only/cold/zero-vector fallback, seen masks, frozen profiles, future-row rejection, no dense conversion, schema/checksum/duplicate rejection, exact selection priority, and an end-to-end selection-before-test guard with exact count/CF controls. Existing 84 tests are rerun unchanged.

## Interpretation and next review

Current metadata may not describe what was known at the March 2021 training cutoff. Train-only IDF cannot restore historical titles/categories. Retrospective five-core selection uses future participation; metadata/selection bias remains even with chronological rating separation. Generic categories, marketing vocabulary, repeated titles, literal lexical matching and sparse positive histories may limit relevance or compatibility. Point-estimate gains do not establish statistical significance or online benefit. A high personalized-user percentage measures availability, not quality.

No additional metadata, hybrid ranking, frontend/backend, Git setting/remote/commit/push change, or company-project access is authorized here. Preserve the current CF baseline pending review. Cleanup is not automatic: after review, resolve and verify the exact owned `content-tfidf-*` directory is directly under this project's `data/local` before any `Remove-Item -LiteralPath` operation. Never remove the source evaluation, CF, metadata, or subset directories. Stop after reporting results.
