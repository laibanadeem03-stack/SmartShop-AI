# SmartShop-AI item-based collaborative filtering strategy

The approved implementation adds positive item cosine with bounded sparse neighbor lists, preserving the existing chronological evaluation protocol. Content-based filtering, weighted hybrid ranking, metadata acquisition, frontend/backend features, and Git configuration or publishing are outside scope.

## Stage 1: isolated environment

The project `.venv` was created with the verified Python 3.14.7 installation after adding the anchored `/.venv/` ignore rule. Read-only `git check-ignore --no-index` confirmed exclusion before package installation. The venv does not inherit global site-packages and does not require activation or PowerShell policy changes.

`requirements-cf.txt` pins NumPy 2.5.3 and SciPy 1.18.1. Only those two binary-wheel distributions were installed, using the venv interpreter, `--no-deps`, and `--no-cache-dir`; pip is the installer bundled by venv creation. Imports, sparse arithmetic, installed versions, and `pip check` passed. A sandbox network restriction initially blocked PyPI; the approved escalation downloaded the same packages. No global Python or company environment was changed.

```powershell
.\.venv\Scripts\python.exe -I -B -m pip check
.\.venv\Scripts\python.exe -I -B -m unittest discover -s tests -v
```

## Training-only representations

Read existing `data/local/evaluation-ej957b9_/train.csv` after verifying its recorded checksum. Do not regenerate the subset or splits or access the original downloaded CSV.

Create deterministic, sorted original-string user/product mappings from training. The positive CSR matrix B has a one for each 4–5 star training interaction; other entries are absent. Keep all training users and all training-observed products, including zero-positive rows/columns. Keep separate seen histories and count-popularity statistics using every original 1–5 star rating. Ratings 1–2 and neutral 3 do not seed similar-item recommendations, but all seen products are excluded. No negative-similarity penalty is introduced.

The matrix uses float32 ones and int32-capable indices. Shared-user counts do not use uint8 and cannot wrap after 255. No original rating text, timestamp, user ID, or product ID is rewritten.

## Similarity and neighbor storage

For training-positive supports d_i and shared-positive-user counts c_ij:

```
similarity(i,j) = c_ij / sqrt(d_i*d_j) * c_ij / (c_ij + lambda)
```

Require at least two shared positive users; remove self-links. Compute `B.T[block] @ B` as sparse blocks of at most 128 item rows. Apply support filtering and shrinkage before selecting neighbors. Store float32 similarities sorted by descending stored similarity and then original item-ID index. Retain at most K outgoing neighbors per row. Never allocate a full dense item-item or user-item prediction matrix. A top-K graph can be directional even though its underlying cosine is symmetric.

Compare exactly four configurations: K20/lambda0, K20/lambda10, K50/lambda0, and K50/lambda10. Build each shrinkage's K50 graph once and reuse the first 20 sorted neighbors for K20. Exact validation NDCG ties prefer the listed order. The parameter set and tie rule are fixed before examining CF results.

## Personalized ranking and fallback

For user u, sum outgoing neighbor weights from products positively rated in training. Exclude all products in the supplied pre-window seen mask. Sort positive CF scores by descending score, descending training popularity, then original product ID. Backfill remaining positions using the frozen count ranking without duplicates or seen products. Backfill products have zero CF score, with popularity determining their order; no weighted popularity/CF blend is implemented.

The complete training catalog remains the candidate universe: products outside the sparse neighbor union have zero CF score and remain available through backfill. Cold users, users without positive seeds, and isolated profiles fall back to count. Test seed profiles do not learn from validation ratings; validation changes only the seen mask. Cold validation-only users remain cold relative to the training model.

## Existing evaluation, unchanged data

Reuse `split_manifest.json` and its immutable partitions: 136,883 training, 17,110 validation, and 17,111 test interactions. Cutoffs, binary relevance at 4 stars, macro Recall@10/NDCG@10, training-catalog coverage, no-positive-user handling, all four warm/cold segments, and history buckets remain as documented in `docs/evaluation_strategy.md`. Unknown-product positive targets remain misses in overall denominators. No new five-core filtering or negative sampling is applied.

The evaluator adds only an optional per-user recommendation hook, output-list validation, and a source column for CF prediction CSVs. Its existing global popularity path retains the original prediction format. Recomputed count cohorts, all segment metrics, and prediction hashes must exactly match the previous baseline before a CF run can complete.

Choose the best CF by validation overall macro NDCG@10. Persist `validation_selection.json` before test file bytes are read. Count remains the recommended project default unless CF strictly improves validation NDCG. Evaluate only the locked CF configuration and the count control on test, without reselection or retuning. Fingerprint the count snapshot, positive matrix, and all neighbor graphs before/after evaluation. Verify input split checksums and modification times and selected-subset checksum/metadata at completion.

## Coverage and usage attribution

In addition to ranking metrics and cold-start segments, record the fraction of all holdout users receiving at least one CF-supported recommendation, users receiving only fallback, personalized slot counts, and fallback fraction of all returned slots. These usage denominators include users without positive held-out targets; ranking Recall/NDCG denominators do not. Each CF prediction row labels `collaborative` or `popularity_fallback`. No future targets are used to decide a user's recommendations.

## Reproducibility and artifacts

```powershell
.\.venv\Scripts\python.exe -I -B scripts/evaluate_item_cf.py --evaluation-dir data/local/evaluation-ej957b9_ --report docs/item_cf_report.md
```

Use a fresh report filename for reruns. Each run creates an isolated ignored `data/local/item_cf-<run>/` directory containing environment metadata, sparse positive inputs, original-ID mappings, four neighbor graphs, validation selection, prediction files, aggregate results, graph statistics, and implementation checksums. Existing source partitions, manifests, and historical baseline reports are read only. Tracked documents contain aggregate statistics rather than raw IDs.

Measure process peak working set, total pipeline and training-ingestion time, shared K50 build time, neighbor array payloads, compressed model sizes, and retained disk usage. Shared build times are not additive across K20/K50. Exclude final result/report writes from reported pipeline time and identify retained size as distinct from peak disk usage.

Synthetic tests cover cosine arithmetic, shrinkage, minimum support, zero vectors, large co-rater counts, deterministic top-K/ties, block-size invariance, prohibition of dense conversion, ID integrity, future-input rejection, frozen seed profiles, cold fallback, seen filtering, denominator preservation, source labels, selection before test, and unchanged popularity behavior. Keep the existing tests as regression checks.

After review, cleanup may remove only a resolved, verified owned CF run directory beneath the intended ignored local-data parent. Preserve the original subset, existing evaluation run, and other model runs. The venv should remain for reproducibility; any later removal must verify the exact `.venv` path within this workspace. No cleanup is performed by the training/evaluation scripts.

## Limitations

Five-core subsetting was retrospective and uses future participation; chronological training does not undo that selection bias. Short histories, limited overlaps, zero-positive products, stale frozen scores/catalog, and popularity backfill can limit both personalization and reach. This method cannot recover products absent from training. Offline improvements are point estimates, not proof of statistical significance, causal benefit, or online performance. Later metadata/content or hybrid work requires a separate approved phase.
