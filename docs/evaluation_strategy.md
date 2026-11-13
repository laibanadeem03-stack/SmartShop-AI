# SmartShop-AI chronological evaluation strategy

This is the shared historical evaluation protocol, originally implemented for the popularity baseline and subsequently reused by CF, content and hybrid models. It evaluates future-window top-10 recommendations on the prepared subset. Current application status and model comparisons are in the [README](../README.md).

The later item-based CF phase reuses these immutable partitions and metric definitions; see `docs/item_cf_strategy.md` and `docs/item_cf_report.md`. The evaluator now accepts a per-user recommendation callback while its original popularity behavior and prediction format remain unchanged. CF test profiles remain training-only; validation affects only seen-item filtering.

## Input and partitions

Read only the prepared subset whose SHA-256 is `feebd8873792da28db06ba4e370b9757d6eb0c476ebf7f44f6dea7f3fb3b4942`. Read its completed manifest under ignored `data/local/`; do not access the original full downloaded CSV. Verify subset and manifest checksums before and after the pipeline. Each run creates new unique artifacts and refuses to overwrite an existing report.

Use integer epoch milliseconds, with fixed inclusive boundaries:

| Partition | Rule | Expected interactions |
|---|---|---:|
| Training | t <= 1615865531064 (2021-03-16T03:32:11.064Z) | 136,883 |
| Validation | 1615865531064 < t <= 1648169261066 (2022-03-25T00:47:41.066Z) | 17,110 |
| Test | t > 1648169261066 | 17,111 |

These approximately 80/10/10 boundaries come from the approved aggregate diagnostics. Preserve all rows with an equal timestamp in the same partition. Verify actual counts, exact four-field round-tripping, disjoint unique user-product pairs, time bounds, reconstruction of all subset records, and unchanged source bytes. Preserve ID strings, rating text, timestamp text/units, and source order within each output partition. SQLite stores numeric timestamp/rating interpretations separately for checks; it does not rewrite exported fields.

## Frozen training snapshot and candidate catalog

Fit only training interactions. Include all 1–5 star ratings in product counts and means and retain users with short histories. Do not apply another five-core or minimum-five-support filter. A product with at least one training interaction belongs to the candidate catalog.

For validation, exclude all products the user interacted with in training, irrespective of rating. For test, also exclude validation interactions because they precede the test window. Copy seen masks before extension; never mutate the training snapshot. Fingerprint the frozen training aggregates and original training history before and after evaluation.

Produce one top-10 list per user with interactions in the holdout window. All that user's 4–5 star targets in the window form ground truth. Test events never update scores, candidate availability, or seen masks. This is a static future-window benchmark over a long horizon; scores remain frozen at the earlier training boundary even for test. Refit on training plus validation and rolling-window evaluation are separate future experiments.

## Four predeclared baseline candidates

The control ranks products by training interaction count. The three quality-aware variants use prior strengths m=5, 10, and 20:

```
q_i = (rating_sum_i + m * training_global_mean) / (training_count_i + m)
score_i = ((q_i - 1) / 4) * ln(1 + training_count_i)
```

The global mean is interaction-weighted, using training ratings only. This Bayesian-style shrinkage plus logarithmic popularity is a ranking heuristic, not a calibrated probability or a claim of empirical superiority. Products with no training interactions have no candidate score. Sort by descending score, then descending training count, then lexicographic original product ID. The count control uses the same tie policy and full candidate universe.

Select the **final method as well as m**, including count as a selectable method, by highest validation overall macro NDCG@10. Use full precision. Exact ties prefer count, quality_m10, quality_m5, then quality_m20. This priority was fixed before examining metrics. Save `validation_selection.json` before reading test for ranking evaluation. Evaluate test only for the selected method and the predeclared count control. Test results never change the selection.

## Relevance and metrics

Ratings 4 and 5 have binary relevance gain 1; ratings 1–3 have gain 0. Ratings 1–2 remain explicit negative feedback and 3 is neutral; none are discarded or rewritten. Unrated products are not confirmed dislikes.

For each user with at least one positive held-out target:

- Recall@10 = positive targets retrieved / all positive targets in the window.
- DCG@10 = sum of binary relevance / log2(rank+1), ranks starting at 1.
- NDCG@10 = DCG@10 / ideal DCG for min(10, number of positive targets).

Macro-average Recall and NDCG across eligible users. Users without positive targets have undefined Recall/NDCG: report their counts instead of assigning zero or hiding them. Catalog coverage@10 is the number of distinct products recommended across the same positive-user cohort divided by the full training-observed catalog size. Generate predictions for all holdout users so recommendation availability can also be audited.

Do not sample negatives, create a dense score matrix, or filter ground-truth targets to the candidate catalog. A positive unknown product is an unreachable miss in the overall denominator. Also report interaction-weighted positive-target reachability; it is not interchangeable with macro Recall. Report users receiving fewer than ten recommendations. An empty segment has undefined Recall/NDCG, not evidence of zero performance.

## Warm and cold segments

Known users/products have at least one training interaction. Report four positive-target segments: warm user/warm product, cold user/warm product, warm user/cold product, and cold user/cold product. Also report aggregate warm-user/cold-user metrics and training-user history buckets 0, 1–2, 3–4, and 5+. User counts may overlap across product segments; do not sum them as distinct people.

Cold users receive the global ranking after available-history exclusion. Cold products cannot be recommended from the frozen training catalog and therefore receive zero hits while remaining in denominators. A user who first appears in validation remains cold relative to this frozen model, even though validation history is available for filtering at test time. Report all-rating interaction counts separately from positive-target counts.

The 5-core source graph does not guarantee training coverage. Preserve unsupported cases and report them. No product launch, stock, or catalog-availability metadata exists; training observation is only a proxy for the available catalog.

## Bias and interpretation

The subset was selected retrospectively using the whole graph, including future participation. User sampling and iterative five-neighbor pruning favor connected users/products and underrepresent long-tail and cold-start cases. A chronological split prevents additional future ratings from entering scores but cannot undo selection bias. Offline active-user cohorts and observed ratings are also selective; these metrics do not establish causal or online product quality.

Compare selected versus count using actual validation/test point estimates. Do not claim statistical significance without a separate uncertainty analysis. A quality-aware candidate is not presumed better: if count wins validation, retain count; if the validation winner loses on test, report that without retuning.

## Commands and artifacts

For the current end-to-end rebuild sequence and explicit output-directory hand-offs,
use [fresh-clone setup](fresh_clone_setup.md). The following example applies only
to a separately authorized fresh run, with an existing prepared subset and a new
report filename under an existing ignored directory:

```powershell
.\.venv\Scripts\python.exe -B scripts/evaluate_popularity.py --subset-manifest data/local/SUBSET_RUN/manifest.json --report data/local/REBUILD_NOTES/popularity.md
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

For reruns, use a new report filename. `scripts/prepare_evaluation.py --subset-manifest ...` can create verified partitions separately. `scripts/popularity_baseline.py --train-csv ... --output ...` can save a training snapshot independently. Data-bearing CLI paths must remain under this project's explicitly ignored `data/local/`; report only aggregates in tracked documentation.

Each unique run stores split CSVs and checksums, a split manifest, provenance, a SQLite validation database, the frozen training snapshot, four full rankings, validation-selected parameters, prediction CSVs, implementation checksums, aggregate metrics, execution time, working-set memory, and local recommendation latency. Retain the run for review. Cleanup must be limited to the exact verified owned run directory; preserve the prepared subset, its manifest, and other runs. No Git configuration changes, commits, pushes, downloads, or dependency installation are performed by the pipeline.
