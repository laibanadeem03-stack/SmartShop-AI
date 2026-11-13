"""Reuse frozen chronological splits; tune item CF on validation only."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import time

import numpy as np
import scipy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_evaluation as preparation
import popularity_baseline as popularity
import evaluate_popularity as evaluation
import item_cf


# Fixed before viewing CF metrics; exact ties favor smaller models and less shrinkage.
CONFIGURATIONS = ((20, 0), (20, 10), (50, 0), (50, 10))


def name_for(k, shrinkage):
    return f"item_cf_k{k}_lambda{shrinkage}"


def choose_configuration(validation):
    names = [name_for(k, lam) for k, lam in CONFIGURATIONS]
    if any(validation[n]["segments"]["overall"]["ndcg_at_10"] is None for n in names):
        raise ValueError("Validation has no positive-user cohort")
    return max(names, key=lambda n: validation[n]["segments"]["overall"]["ndcg_at_10"])


def verify_partition(metadata):
    path = preparation.require_local(metadata["path"])
    if preparation.sha256(path) != metadata["sha256"]:
        raise ValueError("An existing evaluation partition changed")
    return path


def assert_same_metrics(actual, expected):
    """Timings and output filenames may differ; metric and cohort values may not."""
    if actual["cohort"] != expected["cohort"] or actual["segments"] != expected["segments"]:
        raise RuntimeError("Count-popularity metrics changed after evaluator refactoring")
    if actual["predictions"]["sha256"] != expected["predictions"]["sha256"]:
        raise RuntimeError("Count-popularity prediction bytes changed")


def run(source_directory, report_path):
    started = time.perf_counter()
    source_directory = preparation.require_local(source_directory)
    report = Path(report_path).resolve()
    if report.exists() or not report.parent.is_dir():
        raise ValueError("Report requires a new filename in an existing directory")
    manifest_path = source_directory / "split_manifest.json"
    manifest_sha = preparation.sha256(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise ValueError("The existing evaluation run is incomplete")
    train_end = manifest["protocol"]["train_end_inclusive_ms"]
    validation_end = manifest["protocol"]["validation_end_inclusive_ms"]
    train = verify_partition(manifest["partitions"]["train"])
    validation_path = verify_partition(manifest["partitions"]["validation"])
    # Test CSV bytes are not read until after validation selection is persisted.
    protected = {path: (path.stat().st_size, path.stat().st_mtime_ns, preparation.sha256(path))
                 for path in (manifest_path, train, validation_path)}
    subset_path = preparation.require_local(manifest["source"]["path"])
    subset_before = (subset_path.stat().st_size, subset_path.stat().st_mtime_ns)
    if shutil.disk_usage(preparation.LOCAL).free < 256 * preparation.MIB:
        raise OSError("Insufficient free space for CF artifacts")
    directory = Path(tempfile.mkdtemp(prefix="item_cf-", dir=preparation.LOCAL))
    environment = {
        "python": platform.python_version(), "executable": sys.executable,
        "prefix": sys.prefix, "base_prefix": sys.base_prefix,
        "isolated_venv": sys.prefix != sys.base_prefix,
        "numpy": np.__version__, "scipy": scipy.__version__,
        "dependencies": {dist.metadata["Name"]: dist.version for dist in __import__("importlib.metadata", fromlist=["distributions"]).distributions()},
    }
    preparation.write_json(directory / "environment.json", environment)
    tick = time.perf_counter()
    snapshot = popularity.fit_training(preparation.iter_rows(train), train_end)
    count_rank = popularity.build_ranking(snapshot)
    matrix, users, items = item_cf.positive_matrix(preparation.iter_rows(train), snapshot)
    training_seconds = time.perf_counter() - tick
    frozen_snapshot = popularity.fingerprint(snapshot)
    frozen_matrix = item_cf.array_fingerprint(matrix, users, items)
    item_cf.save_sparse(directory / "positive_training.npz", matrix)
    preparation.write_json(directory / "id_mappings.json", {"users": users, "products": items})
    graphs, graph_stats = {}, {}
    for shrinkage in (0, 10):
        graph50, stats = item_cf.build_neighbors(matrix, 50, shrinkage, minimum_shared=2, block_size=128)
        for k in (20, 50):
            name = name_for(k, shrinkage)
            graph = graph50 if k == 50 else item_cf.trim_neighbors(graph50, k)
            graphs[name] = graph
            graph_stats[name] = {**stats, "k": k, "edges": graph.nnz,
                                 "payload_bytes": item_cf.payload_bytes(graph),
                                 "maximum_neighbors": min(k, stats["maximum_neighbors"]),
                                 "fingerprint": item_cf.array_fingerprint(graph),
                                 "graph_fit_reused_from_maximum_k": k == 20}
            path = directory / f"neighbors_{name}.npz"
            item_cf.save_sparse(path, graph)
            graph_stats[name]["artifact_bytes"] = path.stat().st_size
            graph_stats[name]["artifact_sha256"] = preparation.sha256(path)
    validation_rows = list(preparation.iter_rows(validation_path))
    if len(validation_rows) != manifest["partitions"]["validation"]["interactions"]:
        raise RuntimeError("Validation record count differs from its manifest")
    validation = {"count": evaluation.evaluate_window(
        validation_rows, count_rank, snapshot, snapshot["seen"], train_end, validation_end,
        directory / "validation_predictions_count.csv")}
    for k, shrinkage in CONFIGURATIONS:
        name = name_for(k, shrinkage)
        recommender = item_cf.ItemRecommender(matrix, users, items, graphs[name], snapshot)
        validation[name] = evaluation.evaluate_window(
            validation_rows, count_rank, snapshot, snapshot["seen"], train_end, validation_end,
            directory / f"validation_predictions_{name}.csv", recommender=recommender)
        validation[name]["personalization"] = recommender.usage_summary()
    selected = choose_configuration(validation)
    selected_ndcg = validation[selected]["segments"]["overall"]["ndcg_at_10"]
    count_ndcg = validation["count"]["segments"]["overall"]["ndcg_at_10"]
    selection = {
        "best_cf_configuration": selected, "criterion": "validation overall macro NDCG@10",
        "tie_priority": [name_for(k, lam) for k, lam in CONFIGURATIONS],
        "validation_ndcg": {name: value["segments"]["overall"]["ndcg_at_10"] for name, value in validation.items()},
        "recommended_default": selected if selected_ndcg > count_ndcg else "count",
        "test_used_for_selection": False, "frozen_training_fingerprint": frozen_snapshot,
        "frozen_positive_matrix_fingerprint": frozen_matrix,
        "selected_graph_fingerprint": graph_stats[selected]["fingerprint"],
    }
    preparation.write_json(directory / "validation_selection.json", selection)
    prior = json.loads((source_directory / "results.json").read_text(encoding="utf-8"))
    assert_same_metrics(validation["count"], prior["validation"]["count"])
    if frozen_snapshot != prior["training"]["fingerprint"]:
        raise RuntimeError("Training statistics differ from the original baseline")
    test_seen = popularity.extend_history(snapshot["seen"], validation_rows, validation_end)
    test_path = verify_partition(manifest["partitions"]["test"])
    protected[test_path] = (test_path.stat().st_size, test_path.stat().st_mtime_ns, preparation.sha256(test_path))
    test_rows = list(preparation.iter_rows(test_path))
    if len(test_rows) != manifest["partitions"]["test"]["interactions"]:
        raise RuntimeError("Test record count differs from its manifest")
    test = {"count": evaluation.evaluate_window(
        test_rows, count_rank, snapshot, test_seen, validation_end,
        prediction_path=directory / "test_predictions_count.csv")}
    assert_same_metrics(test["count"], prior["test"]["count"])
    recommender = item_cf.ItemRecommender(matrix, users, items, graphs[selected], snapshot)
    test[selected] = evaluation.evaluate_window(
        test_rows, count_rank, snapshot, test_seen, validation_end,
        prediction_path=directory / f"test_predictions_{selected}.csv", recommender=recommender)
    test[selected]["personalization"] = recommender.usage_summary()
    if popularity.fingerprint(snapshot) != frozen_snapshot or item_cf.array_fingerprint(matrix, users, items) != frozen_matrix:
        raise RuntimeError("Evaluation changed training statistics or seed profiles")
    if any(item_cf.array_fingerprint(graph) != graph_stats[name]["fingerprint"] for name, graph in graphs.items()):
        raise RuntimeError("Evaluation changed a frozen neighbor graph")
    for path, expected in protected.items():
        actual = (path.stat().st_size, path.stat().st_mtime_ns, preparation.sha256(path))
        if actual != expected:
            raise RuntimeError("An existing evaluation input changed")
    if preparation.sha256(manifest_path) != manifest_sha or preparation.sha256(subset_path) != manifest["source"]["sha256"]:
        raise RuntimeError("Existing manifest or selected subset changed")
    if (subset_path.stat().st_size, subset_path.stat().st_mtime_ns) != subset_before:
        raise RuntimeError("Selected subset metadata changed")
    inspection = preparation.load_local("inspect_ratings")
    comparison = {}
    for metric in ("recall_at_10", "ndcg_at_10", "catalog_coverage_at_10"):
        cf = test[selected]["segments"]["overall"][metric]
        control = test["count"]["segments"]["overall"][metric]
        comparison[metric] = {"cf": cf, "count": control, "absolute_difference": cf - control,
                              "relative_change": cf / control - 1 if control else None}
    result = {
        "status": "complete", "algorithm_version": "1.0", "created_utc": datetime.now(timezone.utc).isoformat(),
        "run_directory": str(directory), "source_evaluation_directory": str(source_directory),
        "source_split_manifest_sha256": manifest_sha, "split_metadata": manifest,
        "environment": environment, "selection": selection, "validation": validation, "test": test,
        "test_comparison": comparison, "graphs": graph_stats,
        "training": {"interactions": snapshot["interaction_count"], "users": len(users), "products": len(items),
                     "positive_interactions": matrix.nnz, "positive_matrix_payload_bytes": item_cf.payload_bytes(matrix),
                     "users_without_positive_seeds": int(np.count_nonzero(np.diff(matrix.indptr) == 0)),
                     "fingerprint": frozen_snapshot, "training_and_profiles_unchanged": True},
        "integrity": {"existing_splits_unchanged": True, "subset_unchanged": True,
                      "test_read_after_selection": True, "original_full_csv_accessed": False,
                      "count_metrics_identical": True, "count_prediction_hashes_identical": True},
        "resources": {"elapsed_seconds": time.perf_counter() - started, "training_input_seconds": training_seconds,
                      **inspection.process_memory(),
                      "retained_artifact_bytes_before_results": sum(p.stat().st_size for p in directory.iterdir() if p.is_file())},
        "implementation_sha256": {name: preparation.sha256(Path(__file__).with_name(name)) for name in
                                  ("item_cf.py", "evaluate_item_cf.py", "evaluate_popularity.py", "popularity_baseline.py")},
    }
    preparation.write_json(directory / "results.json", result)
    with report.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(report_markdown(result))
    return result


def report_markdown(r):
    selected = r["selection"]["best_cf_configuration"]
    env, resources = r["environment"], r["resources"]
    lines = ["# SmartShop-AI item-based collaborative filtering results", "",
             f"Best CF configuration: **{selected}**, selected using validation macro NDCG@10 only.",
             f"Validation-selected project default: **{r['selection']['recommended_default']}**.", "",
             "## Environment and inputs", "",
             f"- Python {env['python']}; NumPy {env['numpy']}; SciPy {env['scipy']}.",
             f"- Isolated interpreter: `{env['executable']}`. Global site-packages are not inherited.",
             "- Root `.gitignore` excludes `.venv/` and `data/local/`. Venv exclusion was confirmed before installation; both exclusions were verified afterward.",
             "- Only NumPy and SciPy were installed, using pinned binary wheels and no dependency additions. Pip is the venv's bundled installer.",
             "- Imports, sparse arithmetic, and `pip check` passed. The initial sandbox blocked PyPI sockets; an approved network escalation completed the same two-package installation.",
             f"- Reused evaluation directory: `{r['source_evaluation_directory']}`.",
             f"- Split manifest SHA-256: `{r['source_split_manifest_sha256']}`.",
             "- Existing subset and train/validation/test partitions were not modified. Their checksums and modification times were verified. The original downloaded CSV was never accessed.", "",
             "## Method and leakage controls", "",
             "Only training 4–5 star observations enter the binary sparse positive matrix. Ratings 1–3 do not seed recommendations; all ratings remain in seen-item histories. Minimum shared positive-user support is two. Similarity is positive cosine multiplied by c/(c+lambda). Diagonal links are removed before row-wise top-K selection. Similarities are stored as float32 with deterministic original-ID tie ordering. The graph can be directional after top-K pruning.", "",
             "Sparse co-occurrence is computed in blocks of at most 128 item rows. No full dense item-item or user-item prediction matrix is constructed. K=20 lists reuse the first 20 entries of the correctly sorted K=50 graph for the same shrinkage. Training seed profiles, graph statistics, and count fallback remain frozen. Validation history changes only the test seen mask. User scores sum neighbors of their positive training seeds; ties use training count then original product ID. Unsupported candidates have zero CF score and remain eligible for count-popularity backfill.", "",
             f"Training: {r['training']['interactions']:,} interactions, {r['training']['positive_interactions']:,} positives, "
             f"{r['training']['users']:,} users, {r['training']['products']:,} products. "
             f"Users without positive training seeds: {r['training']['users_without_positive_seeds']:,}.", "",
             "## Validation comparison", "",
             "All metrics use a 0–1 scale. Personalized-user and fallback-slot percentages include all holdout users, including users without positive targets.", "",
             "| Model | Recall@10 | NDCG@10 | Catalog coverage | Users personalized | Fallback slots |",
             "|---|---:|---:|---:|---:|---:|"]
    for name in ["count", *(name_for(k, lam) for k, lam in CONFIGURATIONS)]:
        value = r["validation"][name]
        m = value["segments"]["overall"]
        usage = value.get("personalization", {})
        lines.append(f"| {name} | {m['recall_at_10']:.8f} | {m['ndcg_at_10']:.8f} | {m['catalog_coverage_at_10']:.8f} | "
                     f"{usage.get('fraction_users_personalized', 0):.2%} | {usage.get('fraction_fallback_slots', 1):.2%} |")
    lines += ["", "Exact CF NDCG ties prefer K20/lambda0, K20/lambda10, K50/lambda0, then K50/lambda10. The best CF configuration is locked before test bytes are read. Count remains the recommended default unless CF strictly improves validation NDCG. Both the locked CF method and count are tested for the predeclared comparison; test does not change selection.", "",
              "## Test comparison", "",
              "| Model | Recall@10 | NDCG@10 | Catalog coverage | Hits | Users personalized | Fallback slots |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for name in ("count", selected):
        value = r["test"][name]; m = value["segments"]["overall"]
        usage = value.get("personalization", {})
        lines.append(f"| {name} | {m['recall_at_10']:.8f} | {m['ndcg_at_10']:.8f} | {m['catalog_coverage_at_10']:.8f} | "
                     f"{m['hits_at_10']:,} | {usage.get('fraction_users_personalized', 0):.2%} | {usage.get('fraction_fallback_slots', 1):.2%} |")
    lines += ["", "| Metric | CF minus count | Relative change |", "|---|---:|---:|"]
    for name, value in r["test_comparison"].items():
        change = "N/A" if value["relative_change"] is None else f"{value['relative_change']:.2%}"
        lines.append(f"| {name} | {value['absolute_difference']:.8f} | {change} |")
    lines += ["", "Differences are descriptive point estimates; no statistical-significance claim is made.", "",
              "## Warm-start and cold-start results", "",
              "Known users/products have at least one training interaction. Segment targets include only positives in that segment, so user counts overlap across product segments. Overall metrics include every positive target, including unreachable products. No second five-core filter or negative sampling is applied.", ""]
    for window in ("validation", "test"):
        value = r[window][selected]; overall = value["segments"]["overall"]
        lines += [f"### {window.title()}", "",
                  f"Positive users: {value['cohort']['users_with_positive_holdout']:,}; no-positive users: "
                  f"{value['cohort']['users_without_positive_holdout']:,}. Positive-target reachability: "
                  f"{overall['positive_target_reachability']:.2%}. Users receiving fewer than ten recommendations: "
                  f"{value['cohort']['all_users_receiving_fewer_than_10']:,}.", "",
                  "| Segment | Positive users | Positive targets | Recall@10 | NDCG@10 |", "|---|---:|---:|---:|---:|"]
        for name in evaluation.FOUR_SEGMENTS:
            m = value["segments"][name]
            recall = "N/A" if m["recall_at_10"] is None else f"{m['recall_at_10']:.8f}"
            ndcg = "N/A" if m["ndcg_at_10"] is None else f"{m['ndcg_at_10']:.8f}"
            lines.append(f"| {name} | {m['evaluated_users']:,} | {m['positive_interactions']:,} | {recall} | {ndcg} |")
        usage = value["personalization"]
        lines += ["", f"Personalized users: {usage.get('users_with_personalized_recommendations', 0):,}/{usage['users']:,}; "
                  f"personalized slots: {usage.get('personalized_slots', 0):,}; "
                  f"fallback slots: {usage.get('fallback_slots', 0):,}/{usage['total_slots']:,}.", ""]
    lines += ["Cold users and users without useful seeds/neighbors receive count fallback. Cold products cannot be scored by this frozen collaborative graph; their positives remain zero-hit cases. Validation-only users remain cold relative to training even when their past validation interactions enter the test exclusion mask.", "",
              "## Runtime, memory, and model artifacts", "",
              f"- Total pipeline time: {resources['elapsed_seconds']:.3f} seconds, excluding final result/report writes.",
              f"- Training ingestion: {resources['training_input_seconds']:.3f} seconds.",
              f"- Process peak working set: {resources.get('peak_working_set_bytes', 0)/preparation.MIB:.2f} MiB.",
              f"- Positive matrix array payload: {r['training']['positive_matrix_payload_bytes']/preparation.MIB:.3f} MiB.",
              f"- Retained artifact files before result/report: {resources['retained_artifact_bytes_before_results']/preparation.MIB:.2f} MiB.",
              f"- Run directory: `{r['run_directory']}`.", "",
              "| Graph | Edges | Zero-neighbor items | Array payload MiB | Compressed file MiB | Largest block nonzeros | Max-K build seconds |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for name, stats in r["graphs"].items():
        lines.append(f"| {name} | {stats['edges']:,} | {stats['items_without_neighbors']:,} | "
                     f"{stats['payload_bytes']/preparation.MIB:.3f} | {stats['artifact_bytes']/preparation.MIB:.3f} | "
                     f"{stats['largest_block_nonzeros']:,} | {stats['elapsed_seconds']:.3f} |")
    lines += ["", "K20 rows reuse their same-shrinkage K50 build; those build timings are shared, not additive. Compressed file size differs from in-memory array payload. Reported retained disk usage is not exact peak disk usage.", "",
              "## Integrity, limitations, and review", "",
              "Count-popularity validation/test cohort metrics, every segment metric, and prediction CSV checksums exactly reproduce the previous baseline. Frozen training snapshot, positive matrix, and all neighbor graph fingerprints were unchanged after validation/test. Existing subset and splits retained their original checksums and modification times.", "",
              "The evaluator changed only its recommendation hook, list validation, and optional CF-source column; existing count prediction format and metric definitions remain unchanged. CF prediction files label collaborative versus popularity-fallback slots. Model arrays, original string-ID mappings, environment metadata, selection, predictions, aggregate results, and code checksums are under the ignored run directory. Tracked documentation contains no dataset identifiers.", "",
              "Retrospective five-core selection uses future participation and favors connected users/products. Sparse overlaps, short histories, popularity backfill, and the long frozen-catalog horizon remain limitations. Ratings 1–2 are not used as positive seeds and are excluded as seen, but do not generate negative-neighbor penalties. This method cannot recover unseen products without a separate content/catalog policy. Higher offline accuracy or coverage is not proof of online benefit.", "",
              "See `docs/item_cf_strategy.md` for reproducibility commands and cleanup. No original CSV access, metadata acquisition, content/hybrid model, frontend/backend, global Python modification, or Git configuration/remote/commit/push operation is part of this implementation. Stop for review.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True, help="New output filename; existing reports are never overwritten")
    args = parser.parse_args()
    result = run(args.evaluation_dir, args.report)
    selected = result["selection"]["best_cf_configuration"]
    print(json.dumps({"status": result["status"], "selected_cf": selected,
                      "recommended_default": result["selection"]["recommended_default"],
                      "test_metrics": result["test"][selected]["segments"]["overall"],
                      "personalization": result["test"][selected]["personalization"],
                      "run_directory": result["run_directory"]}))


if __name__ == "__main__":
    main()
