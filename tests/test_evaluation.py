"""Synthetic partition, metric, segmentation, and orchestration regression tests."""

from contextlib import redirect_stdout
import csv
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import prepare_evaluation as preparation
import popularity_baseline as popularity
import evaluate_popularity as evaluation


class SyntheticWorkspace(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="smartshop-evaluation-tests-")
        self.root = Path(self.temporary.name).resolve()
        self.addCleanup(self.safe_cleanup)

    def safe_cleanup(self):
        if not self.root.is_relative_to(Path(tempfile.gettempdir()).resolve()) or not self.root.name.startswith("smartshop-evaluation-tests-"):
            raise RuntimeError("Unexpected test cleanup target")
        self.temporary.cleanup()

    def csv(self, name, rows):
        path = self.root / name
        with path.open("x", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(preparation.HEADER)
            writer.writerows(rows)
        return path


class PartitionTests(SyntheticWorkspace):
    def test_equal_timestamps_boundaries_and_exact_fields(self):
        rows = [("000001", "0000000001", "4.00", "00100"),
                ("CaseUser", "CaseProduct", "1.0", "100"),
                ("caseuser", "caseproduct", "5.000", "101"),
                ("user-α", "product-β", "2", "200"),
                ("last-user", "last-product", "3.00", "201")]
        source = self.csv("fixture.csv", rows)
        original = source.read_bytes()
        directory, manifest = preparation.prepare(source, preparation.sha256(source), self.root, 100, 200)
        self.assertEqual([manifest["partitions"][k]["interactions"] for k in ("train", "validation", "test")], [2, 2, 1])
        reconstructed = []
        for name, expected in (("train", rows[:2]), ("validation", rows[2:4]), ("test", rows[4:])):
            actual = list(preparation.iter_rows(directory / f"{name}.csv"))
            self.assertEqual(actual, expected)
            reconstructed.extend(actual)
        self.assertEqual(reconstructed, rows)
        self.assertEqual(source.read_bytes(), original)
        self.assertTrue(manifest["protocol"]["equal_timestamps_kept_together"])

    def test_partition_reproducibility_and_checksum_rejection(self):
        source = self.csv("fixture.csv", [("U1", "P1", "1", "50"), ("U2", "P2", "5", "150"), ("U3", "P3", "4", "250")])
        first, one = preparation.prepare(source, preparation.sha256(source), self.root, 100, 200)
        second, two = preparation.prepare(source, preparation.sha256(source), self.root, 100, 200)
        self.assertNotEqual(first, second)
        self.assertEqual([p["sha256"] for p in one["partitions"].values()], [p["sha256"] for p in two["partitions"].values()])
        before = set(self.root.iterdir())
        with self.assertRaises(ValueError):
            preparation.prepare(source, "0" * 64, self.root, 100, 200)
        self.assertEqual(before, set(self.root.iterdir()))

    def test_no_duplicate_pair_or_invalid_id_is_silently_normalized(self):
        duplicate = self.csv("duplicates.csv", [("U", "P", "1", "50"), ("U", "P", "5", "150")])
        with self.assertRaises(Exception):
            preparation.prepare(duplicate, preparation.sha256(duplicate), self.root, 100, 200)
        whitespace = self.csv("whitespace.csv", [(" U", "P", "4", "100")])
        with self.assertRaises(ValueError):
            list(preparation.iter_rows(whitespace))

    def test_future_perturbations_do_not_change_training(self):
        train = [("U1", "P1", "1", "50"), ("U2", "P2", "5", "100")]
        snapshots = []
        for name, future in (("one.csv", [("future", "P1", "5", "150")]),
                             ("two.csv", [("future", "P1", "1", "150"), ("new", "new-product", "5", "300")])):
            path = self.csv(name, train + future)
            _, manifest = preparation.prepare(path, preparation.sha256(path), self.root, 100, 200)
            snapshots.append(popularity.fit_training(preparation.iter_rows(manifest["partitions"]["train"]["path"]), 100))
        self.assertEqual(popularity.fingerprint(snapshots[0]), popularity.fingerprint(snapshots[1]))
        for _, method, m in evaluation.CANDIDATES:
            self.assertEqual(popularity.build_ranking(snapshots[0], method, m), popularity.build_ranking(snapshots[1], method, m))

    def test_invalid_cutoff_order_and_count_expectation(self):
        with self.assertRaises(ValueError):
            preparation.partition(100, 200, 100)
        path = self.csv("fixture.csv", [("U", "P", "4", "50")])
        with self.assertRaises(RuntimeError):
            preparation.prepare(path, preparation.sha256(path), self.root, 100, 200, {"train": 2, "validation": 0, "test": 0})


class MetricTests(unittest.TestCase):
    def test_hand_calculated_perfect_miss_and_discount(self):
        perfect = evaluation.ranking_metrics(["A", "B"], {"A", "B"})
        self.assertEqual(perfect["recall"], 1)
        self.assertEqual(perfect["ndcg"], 1)
        missed = evaluation.ranking_metrics(["X"], {"A"})
        self.assertEqual(missed["recall"], 0)
        self.assertEqual(missed["ndcg"], 0)
        discounted = evaluation.ranking_metrics(["X", "A"], {"A", "B"})
        self.assertEqual(discounted["recall"], .5)
        self.assertAlmostEqual(discounted["ndcg"], .38685280723454163)

    def test_empty_ground_truth_duplicate_predictions_and_k(self):
        self.assertIsNone(evaluation.ranking_metrics(["A"], set())["ndcg"])
        with self.assertRaises(ValueError):
            evaluation.ranking_metrics(["A", "A"], {"A"})
        with self.assertRaises(ValueError):
            evaluation.ranking_metrics(["A"], {"A"}, 0)
        self.assertEqual(evaluation.ranking_metrics(["X"] * 10 + ["A"], {"A"}, 1)["hits"], 0)


class EvaluationTests(SyntheticWorkspace):
    def snapshot(self):
        return popularity.fit_training([("known-user", "P", "5", "50"), ("other-user", "Q", "1", "50")], 100)

    def test_macro_averaging_unknown_targets_and_no_positive_users(self):
        snapshot = self.snapshot()
        rows = [("new-A", "P", "4", "150"), ("new-A", "future-product", "5", "150"),
                ("new-B", "P", "5", "150"), ("no-positive", "P", "3", "150")]
        result = evaluation.evaluate_window(rows, popularity.build_ranking(snapshot), snapshot, snapshot["seen"], 100, 200)
        overall = result["segments"]["overall"]
        self.assertEqual(overall["recall_at_10"], .75)
        self.assertAlmostEqual(overall["ndcg_at_10"], .8065735963827292)
        self.assertEqual(overall["positive_interactions"], 3)
        self.assertEqual(overall["reachable_positive_interactions"], 2)
        self.assertEqual(overall["catalog_coverage_at_10"], 1)
        self.assertEqual(result["cohort"]["users_without_positive_holdout"], 1)
        self.assertEqual(result["segments"]["cold_user_cold_product"]["recall_at_10"], 0)
        self.assertIsNone(result["segments"]["warm_user_cold_product"]["ndcg_at_10"])

    def test_all_four_segments_and_available_history_filtering(self):
        snapshot = self.snapshot()
        rows = [("known-user", "Q", "4", "150"), ("known-user", "future1", "5", "150"),
                ("new-user", "P", "5", "150"), ("new-user", "future2", "4", "150")]
        path = self.root / "predictions.csv"
        result = evaluation.evaluate_window(rows, popularity.build_ranking(snapshot), snapshot, snapshot["seen"], 100, 200, path)
        for name in evaluation.FOUR_SEGMENTS:
            self.assertEqual(result["segments"][name]["evaluated_users"], 1)
        self.assertEqual(result["segments"]["warm_user_warm_product"]["recall_at_10"], 1)
        with path.open(encoding="utf-8", newline="") as stream:
            predictions = list(csv.DictReader(stream))
        self.assertFalse(any(p["user_id"] == "known-user" and p["parent_asin"] == "P" for p in predictions))
        before = popularity.fingerprint(snapshot)
        past = popularity.extend_history(snapshot["seen"], [("new-user", "P", "1", "150")], 200)
        test = evaluation.evaluate_window([("new-user", "Q", "5", "250")], popularity.build_ranking(snapshot), snapshot, past, 200)
        self.assertEqual(test["segments"]["cold_user_warm_product"]["recall_at_10"], 1)
        self.assertEqual(popularity.fingerprint(snapshot), before)
        self.assertNotIn("new-user", snapshot["seen"])

    def test_reject_incomplete_catalog_and_future_window(self):
        snapshot = self.snapshot()
        with self.assertRaises(ValueError):
            evaluation.evaluate_window([], [("P", 1)], snapshot, {}, 100, 200)
        with self.assertRaises(ValueError):
            evaluation.evaluate_window([("U", "P", "5", "201")], popularity.build_ranking(snapshot), snapshot, {}, 100, 200)

    def test_fixed_selection_priority_and_no_positive_validation(self):
        results = {name: {"segments": {"overall": {"ndcg_at_10": .5}}} for name, _, _ in evaluation.CANDIDATES}
        self.assertEqual(evaluation.select_candidate(results), "count")
        results["quality_m20"]["segments"]["overall"]["ndcg_at_10"] = .50000000001
        self.assertEqual(evaluation.select_candidate(results), "quality_m20")
        results["count"]["segments"]["overall"]["ndcg_at_10"] = None
        with self.assertRaises(ValueError):
            evaluation.select_candidate(results)

    def test_end_to_end_selection_is_saved_before_test_and_never_reselected(self):
        rows = [(f"poor-{i}", "poor-product", "1", "50") for i in range(10)]
        rows += [(f"good-{i}", "good-product", "5", "50") for i in range(8)]
        rows += [("validation-user", "good-product", "5", "150"), ("test-user", "poor-product", "5", "250")]
        source = self.csv("fixture.csv", rows)
        provenance = self.root / "provenance.json"
        provenance.write_text("{}", encoding="utf-8")
        directory, manifest = preparation.prepare(source, preparation.sha256(source), self.root, 100, 200)
        preparation.write_json(directory / "subset_provenance.json", {"manifest_path": str(provenance), "manifest_sha256": preparation.sha256(provenance)})
        original_iter = preparation.iter_rows
        test_reads = []

        def watched(path):
            if Path(path).name == "test.csv":
                saved = json.loads((directory / "validation_selection.json").read_text(encoding="utf-8"))
                self.assertEqual(saved["selected_baseline"], "quality_m10")
                test_reads.append(True)
            return original_iter(path)

        with patch.object(preparation, "prepare_approved", return_value=(directory, manifest)), patch.object(preparation, "iter_rows", side_effect=watched):
            result = evaluation.run(provenance, self.root / "report.md")
        self.assertTrue(test_reads)
        self.assertEqual(result["selection"]["selected_baseline"], "quality_m10")
        self.assertLess(result["test"]["quality_m10"]["segments"]["overall"]["ndcg_at_10"], result["test"]["count"]["segments"]["overall"]["ndcg_at_10"])
        self.assertEqual(set(result["test"]), {"count", "quality_m10"})
        self.assertFalse(result["integrity"]["test_used_for_selection"])
        self.assertTrue(result["training"]["frozen_statistics_unchanged"])
        before = (self.root / "report.md").read_bytes()
        with self.assertRaises(ValueError):
            evaluation.run(provenance, self.root / "report.md")
        self.assertEqual((self.root / "report.md").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
