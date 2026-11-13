# SmartShop-AI frozen-model weighted RRF

This phase combines the existing CF and content rankings without fitting either model. It installs nothing and acquires no data. The existing content model is the reference default; the hybrid becomes the saved default only after a strict validation NDCG improvement. No backend, frontend, or service deployment is included.

## Components and compatibility

Load `data/local/item_cf-gm9467qd/` (K50/lambda10/minimum shared support two) and `data/local/content-tfidf-w4fi9e0t/` (min_df=2/title weight 0.80). Their 25,000-user and 11,012-product mappings, binary training-positive matrices, training snapshot fingerprints and split manifests must agree. Verify graph, feature, snapshot and mapping hashes before use. Share one positive matrix in memory. Vectorizers, CF graphs and profiles are not retrained or updated.

Both component public recommendation methods already append popularity. The hybrid never uses those backfilled lists as personalized input. Its adapter reads CF's raw `score_candidates` and computes one sparse content-profile/catalog score column from frozen vectors. Filter nonpositive scores and seen products, reject invalid/nonfinite/off-catalog signals, and rank all eligible positives. Do not truncate either list to ten before fusion or sample negative candidates.

## Fusion and availability

For each component with eligible personalized candidates, assign one-based ordinal ranks after the existing descending-score, descending-training-count, original-ID tie policy. Convert rank r to `61/(60+r)`; absent items contribute zero. The constant 60 follows the established [RRF formulation](https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf); scaling by 61 sets the first-ranked contribution to one without changing ordering.

`hybrid_score = effective_cf_weight * cf_rank_value + effective_content_weight * content_rank_value`.

Approved global CF weights are 0.10, 0.25, 0.50, and 0.75, with the complement assigned to content. When both components have eligible candidates, retain those weights. When only one is available, give it effective weight one. When neither is available, both effective weights are zero. Availability is determined after exclusions; no per-item weight renormalization is applied. An item supported by one component still receives zero from the other even when both are globally available for that user.

Rank fused positives by descending fusion score, descending training count, then exact product ID. Fill any remaining slots using the frozen count ranking once, without duplicates or seen items. Fallback scores are zero and their source is `popularity_fallback`. Other per-item sources are `hybrid_both`, `cf_only`, and `content_only`. Source support is not inferred merely from the user's global signal availability. Scores are ranking values, not probabilities or confidence percentages.

## Selection and chronology

Reuse the existing approximately 80/10/10 global chronological split: train 136,883, validation 17,110, test 17,111 interactions. Profiles and all component statistics remain training-only; 4–5-star items supply positive seeds while every rating enters exclusion masks. Validation excludes training history. Test additionally excludes validation history, which never becomes new profile seeds. Candidates remain the 11,012 frozen training products; cold products remain misses in overall denominators.

Select the largest validation macro NDCG@10 from the four weights. Exact hybrid ties prefer 0.10, then 0.25, 0.50, 0.75. Compare with the reproduced original content validation NDCG at full precision: strict `>` selects hybrid, equality/regression selects content. Persist both challenger selection and default decision before test interaction reads or interpreting prior test-result JSON. A test loss is reported without retuning or reversing the predeclared gate. The locked best challenger is tested even when it does not become default.

Replay count, CF and content with their unchanged native interfaces and require exact validation/test cohort/segment metrics and prediction hashes against the saved controls. Their native scores/source labels are preserved; pure components are not represented as RRF endpoints. Reuse the unchanged evaluator's 4–5-star relevance, positive-user macro metrics and catalog-coverage denominator. Report cold segments/history buckets, users without positive targets, personalization/fallback rates across all holdout users, and support modes/sources.

## Processing and measured latency

Validation computes one component-score/rank state per user and uses it for all four weights. Cache only four top-10 prediction/source lists per user, then replay them through the unchanged evaluator. Do not cache a full user-catalog score matrix. Validation resource records explicitly distinguish cached metric lookup time from the measured component-preparation-plus-fusion cost attributed to each variant. Shared work is counted once in total pipeline wall time.

The locked test challenger runs live. Its core call is timed independently from evidence JSONL export, and the evaluator's callback-with-export timing is retained separately. Report median/p95 query time, total measured pipeline time, Windows process peak working set, actual output sizes and referenced model sizes. This is a local offline benchmark, not an API latency guarantee.

## Evidence and future explanations

Export every selected test recommendation's component ranks, raw scores, configured/effective weights, separate rank contributions, source and training interaction count. Contributions must sum to the fusion score. Keep this data and all original IDs in ignored output files only.

For a bounded deterministic sample of 128 test users, enrich traces with the strongest contributing training-liked CF seeds and shared title/category TF-IDF features. Check CF seed sums against the raw CF score and text-feature contributions against the original content cosine within float32 tolerance. Reject stale-user or fabricated traces. Verify vectorizer feature-name alignment against the saved field fingerprints without fitting or transforming text. Other recommendations can be explained on demand with the same helper.

Future FastAPI responses can expose product ID, rank, ranking score/type, source, model version, and reasons built from this evidence. A CF reason can refer to shared positive-rating patterns with liked items; content reasons can cite actual overlapping terms/categories. A fallback reason refers to training rating-interaction counts. Do not claim purchases, causal preferences, present-day availability, or probabilities. No endpoint or frontend is created here.

## Reproduction and artifacts

```powershell
.\.venv\Scripts\python.exe -I -B -m pip check
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
.\.venv\Scripts\python.exe -B scripts/evaluate_hybrid.py
```

CLI numeric thread pools are limited to one. Each run creates a unique ignored `data/local/hybrid-*` directory and refuses to overwrite the report. Use `--report docs/hybrid_report_rerun.md` for a separately reviewed rerun. Outputs include environment, four validation prediction sets, original control replays, selection, test predictions, full lightweight fusion traces, rich sampled evidence, input integrity, results and `hybrid_manifest.json`. The manifest references immutable source model files by path/hash; no model arrays are duplicated or retrained. `hybrid_ranker.load_artifacts(run_directory)` reloads the saved default; `challenger=True` explicitly loads the selected hybrid when content won the gate.

Synthetic tests cover hand-computed ranks/fusion, missing signals and post-exclusion availability, no per-item normalization, fallback isolation, no component backfill contamination, magnitude invariance, deterministic ties, invalid weights/scores/catalog entries, mask changes, frozen histories, zero vectors, no dense conversion, evidence support/staleness, exact/strict default gates, cached-window guards, no-retraining integration, selection before test, unchanged controls, artifact reload and hash rejection. Existing 102 tests remain unchanged.

RRF discards score magnitudes and can overvalue agreement or short/weak rankings. Weight selection reuses validation already used for the components, increasing overfitting risk. Current metadata may postdate the March 2021 training cutoff, and retrospective five-core selection uses future participation. More personalized recommendations or catalog spread is not proof of quality; report absolute hits and point estimates without significance claims. No cold-product coverage improvement is possible under this fixed-catalog protocol.

No automatic cleanup occurs. After review, resolve the exact owned hybrid directory and verify its parent is this project's `data/local` before any `Remove-Item -LiteralPath` operation. Never delete source CF/content/evaluation/metadata/subset directories. No Git settings, remotes, commits, pushes, company projects or additional dependencies are part of this phase. Stop for review.
