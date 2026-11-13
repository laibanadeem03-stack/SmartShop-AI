"""Synthetic CF evaluation, baseline compatibility, and leakage tests."""

import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_item_cf import fixture
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import item_cf
import popularity_baseline as popularity
import prepare_evaluation as preparation
import evaluate_popularity as evaluation
import evaluate_item_cf as cf_evaluation


class EvaluationTests(unittest.TestCase):
    def test_popularity_callback_leaves_all_metrics_unchanged(self):
        _, snapshot, _, _, _ = fixture()
        ranking = popularity.build_ranking(snapshot)
        events = [("U3", "Q", "5", "150"), ("cold-user", "P", "4", "150"),
                  ("cold-user", "future", "5", "150"), ("no-positive", "Q", "1", "150")]
        old = evaluation.evaluate_window(events, ranking, snapshot, snapshot["seen"], 100, 200)
        new = evaluation.evaluate_window(events, ranking, snapshot, snapshot["seen"], 100, 200,
                                        recommender=lambda user, seen, k: popularity.recommend(ranking, seen, k))
        self.assertEqual(old["cohort"], new["cohort"])
        self.assertEqual(old["segments"], new["segments"])

    def test_cf_segments_keep_cold_targets_in_denominators(self):
        _, snapshot, matrix, users, items = fixture()
        graph, _ = item_cf.build_neighbors(matrix)
        model = item_cf.ItemRecommender(matrix, users, items, graph, snapshot)
        events = [("U3", "Q", "5", "150"), ("U3", "future", "5", "150"),
                  ("cold", "P", "4", "150")]
        result = evaluation.evaluate_window(events, popularity.build_ranking(snapshot), snapshot, snapshot["seen"],
                                             100, 200, recommender=model)
        self.assertEqual(result["segments"]["overall"]["recall_at_10"], .75)
        self.assertEqual(result["segments"]["warm_user_cold_product"]["recall_at_10"], 0)
        self.assertEqual(result["segments"]["cold_user_warm_product"]["recall_at_10"], 1)

    def test_validation_masks_do_not_change_seed_profiles(self):
        _, snapshot, matrix, users, items = fixture()
        graph, _ = item_cf.build_neighbors(matrix)
        before = item_cf.array_fingerprint(matrix, users, items)
        frozen = popularity.fingerprint(snapshot)
        past = popularity.extend_history(snapshot["seen"], [("U3", "Q", "1", "150"), ("new", "P", "5", "150")], 200)
        model = item_cf.ItemRecommender(matrix, users, items, graph, snapshot)
        self.assertNotIn("Q", {p for p, _ in model("U3", past["U3"])})
        self.assertTrue(all(source == "popularity_fallback" for source in model.last_sources))
        model("new", past["new"])
        self.assertTrue(all(source == "popularity_fallback" for source in model.last_sources))
        self.assertEqual(before, item_cf.array_fingerprint(matrix, users, items))
        self.assertEqual(frozen, popularity.fingerprint(snapshot))

    def test_invalid_callback_candidates_are_rejected(self):
        _, snapshot, _, _, _ = fixture()
        for output in ([("future", 1)], [("Q", 1), ("Q", 1)], [("P", 1)]):
            with self.assertRaises(RuntimeError):
                evaluation.evaluate_window([("U3", "Q", "5", "150")], popularity.build_ranking(snapshot), snapshot,
                                           snapshot["seen"], 100, 200, recommender=lambda *args: output)

    def test_fixed_validation_selection_and_exact_ties(self):
        values = {cf_evaluation.name_for(k, lam): {"segments": {"overall": {"ndcg_at_10": .1}}}
                  for k, lam in cf_evaluation.CONFIGURATIONS}
        self.assertEqual(cf_evaluation.choose_configuration(values), "item_cf_k20_lambda0")
        values["item_cf_k50_lambda10"]["segments"]["overall"]["ndcg_at_10"] = .10000000001
        self.assertEqual(cf_evaluation.choose_configuration(values), "item_cf_k50_lambda10")


class PipelineTests(unittest.TestCase):
    def test_selection_precedes_test_reads_and_baseline_is_preserved(self):
        temporary = tempfile.TemporaryDirectory(prefix="smartshop-cf-pipeline-test-")
        root = Path(temporary.name).resolve()
        self.assertTrue(root.is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.assertTrue(root.name.startswith("smartshop-cf-pipeline-test-"))
        try:
            rows, _, _, _, _ = fixture()
            rows += [("U3", "Q", "5", "150"), ("new-user", "P", "4", "150"),
                     ("U3", "S", "5", "250"), ("new-test-user", "Q", "5", "250")]
            source = root / "fixture.csv"
            with source.open("x", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream); writer.writerow(preparation.HEADER); writer.writerows(rows)
            baseline_dir, manifest = preparation.prepare(source, preparation.sha256(source), root, 100, 200)
            provenance = root / "provenance.json"; provenance.write_text("{}", encoding="utf-8")
            preparation.write_json(baseline_dir / "subset_provenance.json", {"manifest_path": str(provenance), "manifest_sha256": preparation.sha256(provenance)})
            with patch.object(preparation, "prepare_approved", return_value=(baseline_dir, manifest)):
                evaluation.run(provenance, root / "baseline.md")
            original_iter = preparation.iter_rows
            test_reads = []

            def watched(path):
                if Path(path).name == "test.csv":
                    directories = list(root.glob("item_cf-*"))
                    self.assertEqual(len(directories), 1)
                    selection = json.loads((directories[0] / "validation_selection.json").read_text(encoding="utf-8"))
                    self.assertFalse(selection["test_used_for_selection"])
                    test_reads.append(True)
                return original_iter(path)

            with patch.object(preparation, "require_local", side_effect=lambda p: Path(p).resolve()), patch.object(preparation, "LOCAL", root), patch.object(preparation, "iter_rows", side_effect=watched):
                result = cf_evaluation.run(baseline_dir, root / "cf.md")
            self.assertTrue(test_reads)
            self.assertTrue(result["integrity"]["count_metrics_identical"])
            self.assertTrue(result["integrity"]["count_prediction_hashes_identical"])
            self.assertTrue(result["training"]["training_and_profiles_unchanged"])
            self.assertEqual(set(result["test"]), {"count", result["selection"]["best_cf_configuration"]})
        finally:
            if not root.is_relative_to(Path(tempfile.gettempdir()).resolve()) or not root.name.startswith("smartshop-cf-pipeline-test-"):
                raise RuntimeError("Unexpected cleanup path")
            temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
