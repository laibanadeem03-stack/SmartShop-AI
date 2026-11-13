"""Synthetic sparse similarity, identity, fallback, and reproducibility tests."""

import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scipy import sparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import item_cf
import popularity_baseline as popularity


def fixture():
    rows = [("U1", "P", "5", "50"), ("U1", "Q", "4", "50"),
            ("U2", "P", "4", "50"), ("U2", "Q", "5", "50"),
            ("U3", "P", "5", "50"), ("U3", "R", "4", "50"),
            ("U4", "S", "1", "50"), ("U5", "T", "3", "50")]
    snapshot = popularity.fit_training(rows, 100)
    matrix, users, items = item_cf.positive_matrix(rows, snapshot)
    return rows, snapshot, matrix, users, items


class SimilarityTests(unittest.TestCase):
    def test_hand_computed_cosine_support_and_shrinkage(self):
        _, _, matrix, _, items = fixture()
        graph, stats = item_cf.build_neighbors(matrix, 50, 0, block_size=2)
        p, q, r = (items.index(item) for item in ("P", "Q", "R"))
        self.assertAlmostEqual(float(graph[p, q]), 2 / math.sqrt(6), places=7)
        self.assertEqual(float(graph[p, r]), 0)  # One shared user is insufficient.
        self.assertTrue(np.all(graph.diagonal() == 0))
        shrunk, _ = item_cf.build_neighbors(matrix, 50, 10, block_size=2)
        self.assertAlmostEqual(float(shrunk[p, q]), (2 / math.sqrt(6)) * 2 / 12, places=7)
        self.assertEqual(stats["positive_zero_columns"], 2)
        self.assertEqual(stats["items_without_neighbors"], 3)

    def test_block_invariance_and_no_dense_conversion(self):
        _, _, matrix, _, _ = fixture()
        with patch.object(sparse.csr_array, "toarray", side_effect=AssertionError("Dense conversion forbidden")), patch.object(sparse.csr_array, "todense", side_effect=AssertionError("Dense conversion forbidden")):
            one, s1 = item_cf.build_neighbors(matrix, 20, 10, block_size=1)
            three, s3 = item_cf.build_neighbors(matrix, 20, 10, block_size=3)
        for a, b in ((one.data, three.data), (one.indices, three.indices), (one.indptr, three.indptr)):
            np.testing.assert_array_equal(a, b)
        self.assertEqual(s1["largest_block_rows"], 1)
        self.assertLessEqual(s3["largest_block_rows"], 3)

    def test_topk_ties_and_direction_after_pruning(self):
        rows = [(u, p, "5", "50") for u in ("U1", "U2") for p in ("A", "B", "C")]
        snapshot = popularity.fit_training(rows, 100)
        matrix, _, _ = item_cf.positive_matrix(rows, snapshot)
        graph, _ = item_cf.build_neighbors(matrix, 1, 0)
        self.assertEqual(graph.nnz, 3)
        self.assertEqual(float(graph[0, 1]), 1)
        self.assertEqual(float(graph[2, 0]), 1)
        self.assertEqual(float(graph[0, 2]), 0)
        full, _ = item_cf.build_neighbors(matrix, 2, 0)
        trimmed = item_cf.trim_neighbors(full, 1)
        np.testing.assert_array_equal(graph.indices, trimmed.indices)
        np.testing.assert_array_equal(graph.data, trimmed.data)

    def test_more_than_255_shared_users_does_not_overflow(self):
        matrix = sparse.csr_array((np.ones(600, dtype=np.float32),
                                   (np.repeat(np.arange(300), 2), np.tile([0, 1], 300))), shape=(300, 2))
        graph, _ = item_cf.build_neighbors(matrix, 1, 10, block_size=1)
        self.assertAlmostEqual(float(graph[0, 1]), 300 / 310, places=7)

    def test_zero_vectors_and_stricter_support(self):
        _, _, matrix, _, _ = fixture()
        graph, _ = item_cf.build_neighbors(matrix, 50, 10, minimum_shared=3)
        self.assertEqual(graph.nnz, 0)
        empty = sparse.csr_array((3, 4), dtype=np.float32)
        graph, stats = item_cf.build_neighbors(empty)
        self.assertEqual(graph.nnz, 0)
        self.assertEqual(stats["items_without_neighbors"], 4)

    def test_invalid_parameters_or_nonbinary_matrix(self):
        _, _, matrix, _, _ = fixture()
        for parameters in ({"k": 0}, {"shrinkage": -1}, {"block_size": 0}, {"minimum_shared": 0}):
            with self.assertRaises(ValueError):
                item_cf.build_neighbors(matrix, **parameters)
        invalid = matrix.copy(); invalid.data[0] = 2
        with self.assertRaises(ValueError):
            item_cf.build_neighbors(invalid)


class ProfileAndRecommendationTests(unittest.TestCase):
    def test_ratings_and_id_identity_are_preserved(self):
        rows = [("000001", "0000000001", "4.00", "050"),
                ("CaseUser", "CaseProduct", "5", "50"),
                ("caseuser", "caseproduct", "2", "50"),
                ("user-α", "product-β", "3", "50")]
        first = popularity.fit_training(rows, 100)
        matrix, users, items = item_cf.positive_matrix(rows, first)
        self.assertEqual(matrix.nnz, 2)
        self.assertEqual(set(users), {row[0] for row in rows})
        self.assertEqual(set(items), {row[1] for row in rows})
        second = popularity.fit_training(reversed(rows), 100)
        reverse, u2, i2 = item_cf.positive_matrix(reversed(rows), second)
        self.assertEqual(item_cf.array_fingerprint(matrix, users, items), item_cf.array_fingerprint(reverse, u2, i2))

    def test_future_or_incomplete_training_is_rejected(self):
        rows, snapshot, _, _, _ = fixture()
        with self.assertRaises(ValueError):
            item_cf.positive_matrix(rows[:-1], snapshot)
        future = [(*rows[0][:3], "101"), *rows[1:]]
        with self.assertRaises(ValueError):
            item_cf.positive_matrix(future, snapshot)
        with self.assertRaises(ValueError):
            item_cf.positive_matrix(rows + [rows[0]], snapshot)

    def test_personalization_fallback_and_exclusions(self):
        _, snapshot, matrix, users, items = fixture()
        graph, _ = item_cf.build_neighbors(matrix, 50, 0)
        model = item_cf.ItemRecommender(matrix, users, items, graph, snapshot)
        fingerprint = item_cf.array_fingerprint(graph)
        recs = model("U3", snapshot["seen"]["U3"])
        self.assertEqual(recs[0][0], "Q")
        self.assertEqual(model.last_sources, ["collaborative", "popularity_fallback", "popularity_fallback"])
        self.assertFalse({p for p, _ in recs} & snapshot["seen"]["U3"])
        cold = model("new-user", set())
        self.assertEqual([p for p, _ in cold], [p for p, _ in popularity.recommend(popularity.build_ranking(snapshot), set())])
        self.assertEqual(model.usage_summary()["users_with_personalized_recommendations"], 1)
        self.assertEqual(model.usage_summary()["fraction_users_personalized"], .5)
        self.assertEqual(model.usage_summary()["fraction_fallback_slots"], 7 / 8)
        self.assertEqual(item_cf.array_fingerprint(graph), fingerprint)

    def test_negative_only_user_falls_back_and_never_recommends_seen(self):
        _, snapshot, matrix, users, items = fixture()
        graph, _ = item_cf.build_neighbors(matrix)
        model = item_cf.ItemRecommender(matrix, users, items, graph, snapshot)
        recs = model("U4", {"S", "P"})
        self.assertFalse({"S", "P"} & {p for p, _ in recs})
        self.assertTrue(all(source == "popularity_fallback" for source in model.last_sources))
        self.assertEqual(model("new-user", set(items)), [])

    def test_sparse_artifact_roundtrip_and_overwrite_refusal(self):
        _, _, matrix, _, _ = fixture()
        with tempfile.TemporaryDirectory(prefix="smartshop-cf-artifact-test-") as temporary:
            root = Path(temporary).resolve()
            self.assertTrue(root.is_relative_to(Path(tempfile.gettempdir()).resolve()))
            self.assertTrue(root.name.startswith("smartshop-cf-artifact-test-"))
            path = root / "matrix.npz"
            item_cf.save_sparse(path, matrix)
            restored = sparse.load_npz(path)
            self.assertEqual(item_cf.array_fingerprint(matrix), item_cf.array_fingerprint(restored))
            with self.assertRaises(FileExistsError):
                item_cf.save_sparse(path, matrix)


if __name__ == "__main__":
    unittest.main()
