"""Synthetic tests for training-only scores, identity, history, and rankings."""

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import popularity_baseline as popularity


class PopularityTests(unittest.TestCase):
    def test_all_ratings_contribute_to_weighted_training_mean(self):
        snapshot = popularity.fit_training([
            ("0001", "A", "1.00", "100"), ("user-α", "A", "5", "100"),
            ("CaseUser", "B", "3", "100"), ("caseuser", "b", "2", "100"),
        ], 100)
        self.assertEqual(snapshot["interaction_count"], 4)
        self.assertEqual(snapshot["global_mean"], 2.75)
        self.assertEqual(snapshot["items"]["A"]["count"], 2)
        self.assertEqual(snapshot["items"]["A"]["rating_sum"], 6)
        self.assertEqual(set(snapshot["seen"]), {"0001", "user-α", "CaseUser", "caseuser"})
        self.assertEqual(set(snapshot["items"]), {"A", "B", "b"})

    def test_hand_calculated_quality_score_and_prior_strength(self):
        self.assertAlmostEqual(popularity.quality_score(10, 40, 3, 10), 1.4986845454989817)
        self.assertGreater(popularity.quality_score(1, 5, 3, 5), popularity.quality_score(1, 5, 3, 20))
        self.assertEqual(popularity.quality_score(10, 10, 1, 10), 0)
        with self.assertRaises(ValueError):
            popularity.quality_score(0, 0, 3, 10)

    def test_count_and_quality_rankings_and_stable_ties(self):
        rows = [(f"bad-{i}", "popular-poor", "1", "100") for i in range(10)]
        rows += [(f"good-{i}", "good", "5", "100") for i in range(8)]
        snapshot = popularity.fit_training(rows, 100)
        self.assertEqual(popularity.build_ranking(snapshot)[0][0], "popular-poor")
        self.assertEqual(popularity.build_ranking(snapshot, "quality", 10)[0][0], "good")
        tied = popularity.fit_training([("U1", "b", "5", "100"), ("U2", "A", "5", "100"), ("U3", "0001", "5", "100")], 100)
        self.assertEqual([p for p, _ in popularity.build_ranking(tied)], ["0001", "A", "b"])

    def test_reversed_input_same_fingerprint_and_rankings(self):
        rows = [("U1", "P1", "4", "100"), ("U2", "P2", "5", "100"), ("U3", "P1", "1", "100")]
        first = popularity.fit_training(rows, 100)
        second = popularity.fit_training(reversed(rows), 100)
        self.assertEqual(popularity.fingerprint(first), popularity.fingerprint(second))
        self.assertEqual(popularity.build_ranking(first, "quality", 20), popularity.build_ranking(second, "quality", 20))

    def test_training_rejects_future_rows_duplicates_and_empty_input(self):
        for rows in ([('U', 'P', '5', '101')], [], [("U", "P", "1", "100"), ("U", "P", "5", "100")]):
            with self.assertRaises(ValueError):
                popularity.fit_training(rows, 100)

    def test_filtering_all_ratings_and_copying_validation_history(self):
        snapshot = popularity.fit_training([("U", "P1", "1", "100"), ("V", "P2", "5", "100"), ("W", "P3", "4", "100")], 100)
        frozen = copy.deepcopy(snapshot)
        history = popularity.extend_history(snapshot["seen"], [("U", "P2", "2", "200")], 200)
        self.assertEqual(history["U"], {"P1", "P2"})
        self.assertEqual([p for p, _ in popularity.recommend(popularity.build_ranking(snapshot), history["U"])], ["P3"])
        self.assertEqual(snapshot, frozen)
        with self.assertRaises(ValueError):
            popularity.extend_history(snapshot["seen"], [("U", "P3", "5", "201")], 200)

    def test_new_user_short_catalog_empty_candidates_and_no_padding(self):
        ranking = [("P", 2.0), ("Q", 1.0)]
        self.assertEqual(popularity.recommend(ranking, set()), ranking)
        self.assertEqual(popularity.recommend(ranking, {"P", "Q"}), [])
        self.assertEqual(popularity.recommend(ranking, set(), 1), [("P", 2.0)])
        with self.assertRaises(ValueError):
            popularity.recommend(ranking, set(), 0)


if __name__ == "__main__":
    unittest.main()
