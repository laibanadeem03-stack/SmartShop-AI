"""Validate four popularity candidates, freeze selection, then evaluate test."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_evaluation as preparation
import popularity_baseline as popularity


# Predeclared tie priority: simplest baseline, then the default prior, then others.
CANDIDATES = (("count", "count", None), ("quality_m10", "quality", 10),
              ("quality_m5", "quality", 5), ("quality_m20", "quality", 20))
FOUR_SEGMENTS = ("warm_user_warm_product", "cold_user_warm_product",
                 "warm_user_cold_product", "cold_user_cold_product")
SEGMENTS = ("overall", *FOUR_SEGMENTS, "warm_users", "cold_users",
            "history_0", "history_1_2", "history_3_4", "history_5_plus")


def ranking_metrics(recommended, relevant, k=10):
    top = list(recommended[:k])
    if k < 1 or len(top) != len(set(top)):
        raise ValueError("Expected positive k and distinct recommendations")
    if not relevant:
        return {"recall": None, "ndcg": None, "hits": 0}
    hits = sum(product in relevant for product in top)
    dcg = sum(1 / math.log2(rank + 1) for rank, product in enumerate(top, 1) if product in relevant)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(k, len(relevant)) + 1))
    return {"recall": hits / len(relevant), "ndcg": dcg / ideal, "hits": hits}


def segment_name(warm_user, warm_product):
    return f"{'warm' if warm_user else 'cold'}_user_{'warm' if warm_product else 'cold'}_product"


def history_bucket(count):
    return "history_0" if count == 0 else "history_1_2" if count <= 2 else "history_3_4" if count <= 4 else "history_5_plus"


def evaluate_window(rows, ranking, snapshot, seen, begin_exclusive, end_inclusive=None, prediction_path=None,
                    recommender=None):
    started = time.perf_counter()
    catalog = set(snapshot["items"])
    if {product for product, _ in ranking} != catalog or len(ranking) != len(catalog):
        raise ValueError("Ranking must cover the full training catalog exactly once")
    users, positives = set(), {}
    raw = {name: {"interactions": 0, "positive_interactions": 0, "users": set(), "products": set()} for name in FOUR_SEGMENTS}
    total = positive_total = 0
    for user, product, rating, timestamp in rows:
        stamp = int(timestamp)
        if stamp <= begin_exclusive or (end_inclusive is not None and stamp > end_inclusive):
            raise ValueError("Holdout contains an interaction outside its window")
        users.add(user)
        positive = float(rating) >= 4
        if positive:
            positives.setdefault(user, set()).add(product)
        warm_user = user in snapshot["seen"]
        name = segment_name(warm_user, product in catalog)
        raw[name]["interactions"] += 1
        raw[name]["positive_interactions"] += positive
        raw[name]["users"].add(user)
        raw[name]["products"].add(product)
        total += 1
        positive_total += positive
    accumulators = {name: {"users": 0, "relevant": 0, "hits": 0, "recall_sum": 0.0,
                           "ndcg_sum": 0.0, "recommended": set(), "reachable": 0,
                           "fewer_than_ten": 0} for name in SEGMENTS}
    latencies = []
    all_fewer = 0
    output = Path(prediction_path).open("x", encoding="utf-8", newline="") if prediction_path else None
    try:
        writer = csv.writer(output, lineterminator="\n") if output else None
        if writer:
            header = ["user_id", "rank", "parent_asin", "score", "training_user_interactions"]
            writer.writerow(header if recommender is None else header + ["recommendation_source"])
        for user in sorted(users):
            history = seen.get(user, set())
            tick = time.perf_counter_ns()
            recommendations = (popularity.recommend(ranking, history) if recommender is None
                               else recommender(user, history, 10))
            latencies.append(time.perf_counter_ns() - tick)
            products = [product for product, _ in recommendations]
            if (len(products) > 10 or len(products) != len(set(products)) or
                    not set(products).issubset(catalog) or
                    any(not math.isfinite(float(score)) for _, score in recommendations)):
                raise RuntimeError("Invalid recommendation list")
            if set(products) & history:
                raise RuntimeError("Previously interacted product was recommended")
            all_fewer += len(products) < 10
            training_count = snapshot["user_counts"].get(user, 0)
            if writer:
                sources = getattr(recommender, "last_sources", ["personalized"] * len(recommendations))
                for rank, (product, score) in enumerate(recommendations, 1):
                    row = [user, rank, product, format(score, ".17g"), training_count]
                    writer.writerow(row if recommender is None else row + [sources[rank - 1]])
            relevant = positives.get(user, set())
            if not relevant:
                continue
            warm_user = user in snapshot["seen"]
            groups = {"overall": relevant, "warm_users" if warm_user else "cold_users": relevant,
                      history_bucket(training_count): relevant}
            for warm_product in (True, False):
                groups[segment_name(warm_user, warm_product)] = {
                    product for product in relevant if (product in catalog) == warm_product
                }
            for name, targets in groups.items():
                if not targets:
                    continue
                metrics = ranking_metrics(products, targets)
                accumulator = accumulators[name]
                accumulator["users"] += 1
                accumulator["relevant"] += len(targets)
                accumulator["hits"] += metrics["hits"]
                accumulator["recall_sum"] += metrics["recall"]
                accumulator["ndcg_sum"] += metrics["ndcg"]
                accumulator["recommended"].update(products)
                accumulator["reachable"] += len((targets & catalog) - history)
                accumulator["fewer_than_ten"] += len(products) < 10
    finally:
        if output:
            output.close()
    segments = {}
    for name, a in accumulators.items():
        segments[name] = {
            "evaluated_users": a["users"], "positive_interactions": a["relevant"],
            "hits_at_10": a["hits"],
            "recall_at_10": a["recall_sum"] / a["users"] if a["users"] else None,
            "ndcg_at_10": a["ndcg_sum"] / a["users"] if a["users"] else None,
            "catalog_coverage_at_10": len(a["recommended"]) / len(catalog),
            "distinct_recommended_products": len(a["recommended"]),
            "reachable_positive_interactions": a["reachable"],
            "positive_target_reachability": a["reachable"] / a["relevant"] if a["relevant"] else None,
            "users_receiving_fewer_than_10": a["fewer_than_ten"],
        }
    raw_segments = {name: {"interactions": value["interactions"],
                           "positive_interactions": value["positive_interactions"],
                           "unique_users": len(value["users"]), "unique_products": len(value["products"])}
                    for name, value in raw.items()}
    latency_sorted = sorted(latencies)
    result = {
        "cohort": {"interactions": total, "positive_interactions": positive_total,
                   "users_with_interactions": len(users), "users_with_positive_holdout": len(positives),
                   "users_without_positive_holdout": len(users) - len(positives),
                   "all_users_receiving_fewer_than_10": all_fewer, "training_catalog_products": len(catalog),
                   "all_rating_segments": raw_segments},
        "segments": segments,
        "resources": {"elapsed_seconds": time.perf_counter() - started,
                      "recommendation_latency_median_microseconds": statistics.median(latencies) / 1000 if latencies else None,
                      "recommendation_latency_p95_microseconds": latency_sorted[math.ceil(len(latencies) * .95) - 1] / 1000 if latencies else None},
    }
    if prediction_path:
        result["predictions"] = {"path": str(prediction_path), "sha256": preparation.sha256(prediction_path)}
    return result


def select_candidate(validation_results):
    available = [(name, validation_results[name]["segments"]["overall"]["ndcg_at_10"])
                 for name, _, _ in CANDIDATES]
    if any(value is None for _, value in available):
        raise ValueError("Validation requires at least one user with a positive holdout")
    # max returns the first exact tie, so CANDIDATES fixes the tie preference.
    return max(available, key=lambda pair: pair[1])[0]


def run(subset_manifest, report_path):
    started = time.perf_counter()
    report = Path(report_path).resolve()
    if report.exists() or not report.parent.is_dir():
        raise ValueError("Report requires a new filename under an existing directory")
    directory, split = preparation.prepare_approved(subset_manifest)
    protocol = split["protocol"]
    train_end = protocol["train_end_inclusive_ms"]
    validation_end = protocol["validation_end_inclusive_ms"]
    tick = time.perf_counter()
    snapshot = popularity.fit_training(preparation.iter_rows(split["partitions"]["train"]["path"]), train_end)
    frozen = popularity.fingerprint(snapshot)
    preparation.write_json(directory / "training_snapshot.json", popularity.snapshot_payload(snapshot))
    fit_seconds = time.perf_counter() - tick
    validation_rows = list(preparation.iter_rows(split["partitions"]["validation"]["path"]))
    rankings = {name: popularity.build_ranking(snapshot, method, m) for name, method, m in CANDIDATES}
    preparation.write_json(directory / "rankings.json", rankings)
    validation = {}
    for name, _, _ in CANDIDATES:
        validation[name] = evaluate_window(
            validation_rows, rankings[name], snapshot, snapshot["seen"], train_end, validation_end,
            directory / f"validation_predictions_{name}.csv",
        )
    selected = select_candidate(validation)
    selection = {
        "selected_baseline": selected, "criterion": "validation overall macro NDCG@10",
        "tie_priority": [name for name, _, _ in CANDIDATES],
        "validation_ndcg_at_10": {name: value["segments"]["overall"]["ndcg_at_10"] for name, value in validation.items()},
        "training_fingerprint": frozen, "test_accessed_for_selection": False,
    }
    # This file is saved before the first evaluation read of test.csv.
    preparation.write_json(directory / "validation_selection.json", selection)
    test_seen = popularity.extend_history(snapshot["seen"], validation_rows, validation_end)
    if popularity.fingerprint(snapshot) != frozen:
        raise RuntimeError("Validation or mask construction changed the frozen model")
    test_rows = list(preparation.iter_rows(split["partitions"]["test"]["path"]))
    test = {}
    for name in dict.fromkeys(("count", selected)):
        test[name] = evaluate_window(
            test_rows, rankings[name], snapshot, test_seen, validation_end,
            prediction_path=directory / f"test_predictions_{name}.csv",
        )
    if popularity.fingerprint(snapshot) != frozen:
        raise RuntimeError("Test evaluation changed frozen training statistics")
    # Verify only the prepared subset, its provenance manifest, and generated files.
    source = split["source"]
    after = Path(source["path"]).stat()
    if preparation.sha256(source["path"]) != source["sha256"] or after.st_mtime_ns != source["mtime_ns"]:
        raise RuntimeError("Selected subset changed during evaluation")
    provenance = json.loads((directory / "subset_provenance.json").read_text(encoding="utf-8"))
    if preparation.sha256(provenance["manifest_path"]) != provenance["manifest_sha256"]:
        raise RuntimeError("Subset provenance manifest changed")
    for metadata in split["partitions"].values():
        if preparation.sha256(metadata["path"]) != metadata["sha256"]:
            raise RuntimeError("A generated partition changed during evaluation")
    chosen = test[selected]["segments"]["overall"]
    control = test["count"]["segments"]["overall"]
    comparison = {metric: {"selected": chosen[metric], "count": control[metric],
                           "absolute_difference": chosen[metric] - control[metric],
                           "relative_change": chosen[metric] / control[metric] - 1 if control[metric] else None}
                  for metric in ("recall_at_10", "ndcg_at_10", "catalog_coverage_at_10")}
    inspection = preparation.load_local("inspect_ratings")
    result = {
        "status": "complete", "protocol_version": "1.0", "run_directory": str(directory),
        "split_manifest": split, "selection": selection,
        "training": {"interactions": snapshot["interaction_count"], "users": len(snapshot["seen"]),
                     "products": len(snapshot["items"]), "global_mean_rating": snapshot["global_mean"],
                     "fingerprint": frozen, "frozen_statistics_unchanged": True},
        "validation": validation, "test": test, "test_comparison_with_count": comparison,
        "integrity": {"subset_unchanged": True, "subset_manifest_unchanged": True,
                      "partition_fields_and_counts_verified": True, "split_checksums_unchanged": True,
                      "original_full_csv_accessed": False, "test_used_for_selection": False},
        "resources": {"elapsed_seconds": time.perf_counter() - started, "fit_seconds": fit_seconds,
                      **inspection.process_memory(), "python": platform.python_version(),
                      "retained_run_bytes_before_results": sum(p.stat().st_size for p in directory.iterdir() if p.is_file())},
        "implementation_sha256": {name: preparation.sha256(Path(__file__).with_name(name)) for name in
                                  ("prepare_evaluation.py", "popularity_baseline.py", "evaluate_popularity.py")},
    }
    preparation.write_json(directory / "results.json", result)
    with report.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(report_markdown(result))
    return result


def percent(value):
    return "N/A" if value is None else f"{value:.6%}"


def report_markdown(r):
    selected = r["selection"]["selected_baseline"]
    split, resources = r["split_manifest"], r["resources"]
    lines = ["# SmartShop-AI popularity baseline results", "",
             f"Selected baseline: **{selected}**, chosen solely by overall validation macro NDCG@10.", "",
             "## Data integrity and protocol", "",
             f"- Prepared subset SHA-256: `{split['source']['sha256']}`.",
             "- The selected subset and its manifest were unchanged. The full downloaded CSV was not accessed.",
             "- Every partition row round-tripped all four original field values. Ratings, string IDs, timestamps, "
             "and within-partition source order were preserved. The partitions reconstruct every subset record exactly once.",
             "- Fixed UTC millisecond cutoffs: training through 2021-03-16T03:32:11.064Z; validation through "
             "2022-03-25T00:47:41.066Z; remaining rows are test. Equal timestamps stay together.",
             f"- Training: {r['training']['interactions']:,} interactions, {r['training']['users']:,} users, "
             f"{r['training']['products']:,} products; mean rating {r['training']['global_mean_rating']:.8f}.",
             "- Counts, priors, and scores were fit on training only and fingerprinted before and after evaluation. "
             "Validation selects the method and prior strength; it updates only the seen mask before test. Test does not "
             "update scores or select parameters. The selection artifact was saved before loading test for ranking evaluation.", "",
             "| Partition | Interactions | Users | Products | Relevant interactions (4–5 stars) |",
             "|---|---:|---:|---:|---:|"]
    for name, p in split["partitions"].items():
        lines.append(f"| {name} | {p['interactions']:,} | {p['unique_users']:,} | {p['unique_products']:,} | {p['positive_interactions']:,} |")
    lines += ["", "## Validation comparison", "",
              "| Candidate | Recall@10 | NDCG@10 | Catalog coverage@10 | Positive users | Hits |",
              "|---|---:|---:|---:|---:|---:|"]
    for name, _, _ in CANDIDATES:
        m = r["validation"][name]["segments"]["overall"]
        lines.append(f"| {name} | {percent(m['recall_at_10'])} | {percent(m['ndcg_at_10'])} | "
                     f"{percent(m['catalog_coverage_at_10'])} | {m['evaluated_users']:,} | {m['hits_at_10']:,} |")
    lines += ["", "Exact NDCG ties prefer count, quality_m10, quality_m5, then quality_m20. Selection uses "
              "full-precision metrics, not rounded table values. Count is a selectable candidate, not only a control.", "",
              "## Test comparison", "",
              "Only the validation-selected baseline and the predeclared count control were evaluated on test.", "",
              "| Candidate | Recall@10 | NDCG@10 | Catalog coverage@10 | Positive users | Hits |",
              "|---|---:|---:|---:|---:|---:|"]
    for name, value in r["test"].items():
        m = value["segments"]["overall"]
        lines.append(f"| {name} | {percent(m['recall_at_10'])} | {percent(m['ndcg_at_10'])} | "
                     f"{percent(m['catalog_coverage_at_10'])} | {m['evaluated_users']:,} | {m['hits_at_10']:,} |")
    delta = r["test_comparison_with_count"]
    if selected == "count":
        conclusion = "Count popularity won validation (including the fixed tie rule), so the final baseline is the simple count ranking. No improvement over count is claimed."
    else:
        ndcg_delta = delta["ndcg_at_10"]["absolute_difference"]
        conclusion = (f"The smoothed ranking won validation. On test its NDCG@10 is "
                      f"{'higher' if ndcg_delta > 0 else 'lower' if ndcg_delta < 0 else 'equal'} compared with count, "
                      f"with an absolute difference of {ndcg_delta:.10f}. "
                      "The test result did not change the selected baseline or any parameter.")
    lines += ["", conclusion, "", "| Test measure | Selected minus count | Relative change |",
              "|---|---:|---:|"]
    for metric, values in delta.items():
        lines.append(f"| {metric} | {values['absolute_difference']:.10f} | {percent(values['relative_change'])} |")
    lines += ["", "Differences are descriptive point estimates; no statistical-significance claim is made.", "",
              "## Warm-start and cold-start coverage", "",
              "Known means at least one interaction in the frozen training snapshot. User counts can overlap between "
              "product segments when a user has both known and unknown positive targets. Overall metrics include cold "
              "targets in their denominators. All training-observed products remain eligible; there is no new five-core filter.", ""]
    for window, value in (("validation", r["validation"][selected]), ("test", r["test"][selected])):
        c = value["cohort"]
        overall = value["segments"]["overall"]
        lines += [f"### {window.title()} selected-baseline segments", "",
                  f"Window users: {c['users_with_interactions']:,}; positive users: {c['users_with_positive_holdout']:,}; "
                  f"users without positive targets: {c['users_without_positive_holdout']:,}. "
                  f"Users receiving fewer than ten recommendations: {c['all_users_receiving_fewer_than_10']:,}.", "",
                  f"Positive-target reachability in the frozen catalog after seen filtering: "
                  f"{overall['reachable_positive_interactions']:,}/{overall['positive_interactions']:,} "
                  f"({percent(overall['positive_target_reachability'])}). This is interaction-weighted, while Recall/NDCG are user-macro averages.", "",
                  "| Segment | All-rating rows | Positive targets | Positive users | Recall@10 | NDCG@10 |",
                  "|---|---:|---:|---:|---:|---:|"]
        for name in FOUR_SEGMENTS:
            raw = c["all_rating_segments"][name]
            m = value["segments"][name]
            lines.append(f"| {name} | {raw['interactions']:,} | {m['positive_interactions']:,} | {m['evaluated_users']:,} | "
                         f"{percent(m['recall_at_10'])} | {percent(m['ndcg_at_10'])} |")
        lines += ["", "| Training-user history | Positive users | Recall@10 | NDCG@10 |", "|---|---:|---:|---:|"]
        for name in ("history_0", "history_1_2", "history_3_4", "history_5_plus"):
            m = value["segments"][name]
            lines.append(f"| {name} | {m['evaluated_users']:,} | {percent(m['recall_at_10'])} | {percent(m['ndcg_at_10'])} |")
    lines += ["", "Cold users receive the global ranking after available-history filtering. Cold products have no "
              "training score and cannot appear in the training-catalog recommendations, so their positive targets are "
              "misses, not dropped cases. Users first observed in validation remain cold relative to the frozen training "
              "snapshot even when their validation interactions are used in the test seen mask.", "",
              "## Metric definitions and limitations", "",
              "Recall@10 is hits divided by all positive targets for the user; NDCG@10 uses binary gains and log2(rank+1) "
              "discounts divided by the ideal gain for min(10, number of positives). Users with no positives have undefined "
              "Recall/NDCG and are counted explicitly. Catalog coverage is the union of recommended products for the same "
              "positive-user cohort divided by the complete training catalog. Recommendations use the full catalog and "
              "never sampled negatives. Ratings 1–3 yield zero ranking gain; all ratings contribute to training count and "
              "mean rating, and every previous interaction is excluded irrespective of its star rating. An unobserved "
              "product is not established negative feedback.", "",
              "The existing subset was selected retrospectively using the complete interaction graph. Its five-core "
              "selection and iterative pruning use future activity and favor sufficiently connected users/products. "
              "Chronological partitions prevent additional future-rating leakage into scores but cannot remove that "
              "selection bias. The frozen catalog and scores also become stale over a long holdout horizon. Unknown "
              "products are intentionally unsupported without metadata or an approved catalog-expansion policy. "
              "Results are a retrospective offline comparison, not an unbiased deployment or causal evaluation. "
              "Five-core does not guarantee sufficient training history after splitting.", "",
              "## Resources and artifacts", "",
              f"- Total measured pipeline time: {resources['elapsed_seconds']:.3f} seconds, including split preparation, prediction export, and integrity checks.",
              f"- Split preparation: {split['resources']['elapsed_seconds']:.3f} seconds; training aggregation: {resources['fit_seconds']:.3f} seconds.",
              f"- Process lifetime peak working set: {resources.get('peak_working_set_bytes', 0)/preparation.MIB:.2f} MiB.",
              f"- Retained run files before results/report: {resources['retained_run_bytes_before_results']/preparation.MIB:.2f} MiB (not a peak disk measurement).",
              f"- Python {resources['python']}; standard library only.",
              f"- Run directory: `{r['run_directory']}`.",
              "- Artifacts include train/validation/test CSVs, split manifest, subset provenance, SQLite validation database, "
              "training snapshot, all four catalog rankings, validation selection, validation predictions for all "
              "candidates, test predictions for selected/count, and aggregate `results.json`. IDs appear only in ignored local artifacts.", "",
              "| Window | Candidate | Evaluation/export seconds | Recommendation median µs | Recommendation P95 µs |",
              "|---|---|---:|---:|---:|"]
    for window in ("validation", "test"):
        for name, value in r[window].items():
            timing = value["resources"]
            lines.append(f"| {window} | {name} | {timing['elapsed_seconds']:.3f} | "
                         f"{timing['recommendation_latency_median_microseconds']:.3f} | "
                         f"{timing['recommendation_latency_p95_microseconds']:.3f} |")
    lines += ["", "Recommendation latency covers only the in-process filtered ranking call; it excludes CSV I/O, "
              "metric computation, network service, and application startup. Overall elapsed time excludes the final "
              "results/report writes. See `docs/evaluation_strategy.md` for the fixed protocol and commands. "
              "Preserve the complete run for reproducibility. Future cleanup should target only this exact owned "
              "directory after resolving and checking that it is beneath the intended ignored local-data parent; "
              "never remove the prepared subset or its parent as part of evaluation cleanup.", "",
              "No packages, metadata, collaborative filtering, hybrid model, frontend, backend, or Git configuration "
              "changes were introduced. Stop for review before proceeding to later phases.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subset-manifest", required=True, type=Path)
    parser.add_argument("--report", type=Path, required=True, help="New output filename")
    args = parser.parse_args()
    result = run(args.subset_manifest, args.report)
    print(json.dumps({"status": result["status"], "selected": result["selection"]["selected_baseline"],
                      "run_directory": result["run_directory"], "test_metrics": result["test"][result["selection"]["selected_baseline"]]["segments"]["overall"]}))


if __name__ == "__main__":
    main()
