"""Training-only sparse positive item cosine, bounded neighbors, and fallback."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy import sparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import popularity_baseline as popularity


def positive_matrix(rows, snapshot):
    """Retain every training ID; only observed 4–5 ratings enter B."""
    users = sorted(snapshot["seen"])
    items = sorted(snapshot["items"])
    user_index = {value: i for i, value in enumerate(users)}
    item_index = {value: i for i, value in enumerate(items)}
    row_indices, column_indices = [], []
    observed = set()
    count = 0
    for user, item, rating, timestamp in rows:
        if int(timestamp) > snapshot["train_end_ms"]:
            raise ValueError("Future interaction cannot enter CF training")
        if user not in user_index or item not in item_index or item not in snapshot["seen"][user]:
            raise ValueError("CF rows disagree with the training snapshot")
        if (user, item) in observed:
            raise ValueError("Repeated training pair")
        observed.add((user, item))
        value = float(rating)
        if not np.isfinite(value) or not 1 <= value <= 5:
            raise ValueError("Invalid CF training rating")
        count += 1
        if value >= 4:
            row_indices.append(user_index[user])
            column_indices.append(item_index[item])
    if count != snapshot["interaction_count"]:
        raise ValueError("CF training rows are incomplete")
    matrix = sparse.csr_array(
        (np.ones(len(row_indices), dtype=np.float32),
         (np.asarray(row_indices, dtype=np.int32), np.asarray(column_indices, dtype=np.int32))),
        shape=(len(users), len(items)), dtype=np.float32,
    )
    matrix.sort_indices()
    return matrix, users, items


def array_fingerprint(matrix, users=None, items=None):
    digest = hashlib.sha256()
    digest.update(json.dumps([matrix.shape, users, items], ensure_ascii=True).encode("utf-8"))
    for array in (matrix.indptr, matrix.indices, matrix.data):
        digest.update(str(array.dtype).encode("ascii"))
        digest.update(array.tobytes())
    return digest.hexdigest()


def payload_bytes(matrix):
    return matrix.indptr.nbytes + matrix.indices.nbytes + matrix.data.nbytes


def build_neighbors(matrix, k=50, shrinkage=10, minimum_shared=2, block_size=128):
    """Compute one bounded sparse block, prune rows, then discard the block.

    Values are float32, not uint8: shared-user counts cannot wrap at 255.
    Stored rows are sorted by descending stored similarity then item index.
    """
    if k < 1 or shrinkage < 0 or minimum_shared < 1 or block_size < 1:
        raise ValueError("Invalid neighbor parameters")
    if matrix.dtype != np.float32:
        raise ValueError("Positive matrix must use float32 counts")
    if matrix.nnz and not np.all(matrix.data == 1):
        raise ValueError("Expected binary positive interactions")
    started = time.perf_counter()
    n_items = matrix.shape[1]
    item_rows = matrix.T.tocsr()
    support = np.asarray(matrix.sum(axis=0), dtype=np.float64).ravel()
    indices, values, indptr = [], [], [0]
    maximum_block_nnz = 0
    maximum_rows = 0
    for begin in range(0, n_items, block_size):
        end = min(begin + block_size, n_items)
        shared = (item_rows[begin:end] @ matrix).tocsr()
        maximum_block_nnz = max(maximum_block_nnz, shared.nnz)
        maximum_rows = max(maximum_rows, end - begin)
        for local_row, item in enumerate(range(begin, end)):
            start, stop = shared.indptr[local_row:local_row + 2]
            candidates = shared.indices[start:stop]
            counts = shared.data[start:stop]
            keep = (candidates != item) & (counts >= minimum_shared)
            candidates = candidates[keep]
            counts = counts[keep].astype(np.float64)
            if len(candidates):
                similarities = counts / np.sqrt(support[item] * support[candidates])
                similarities *= counts / (counts + shrinkage)
                similarities = similarities.astype(np.float32)
                order = np.lexsort((candidates, -similarities))[:k]
                indices.extend(candidates[order].tolist())
                values.extend(similarities[order].tolist())
            indptr.append(len(indices))
        del shared
    graph = sparse.csr_array((np.asarray(values, dtype=np.float32),
                              np.asarray(indices, dtype=np.int32),
                              np.asarray(indptr, dtype=np.int32)), shape=(n_items, n_items))
    degrees = np.diff(graph.indptr)
    return graph, {
        "k": k, "shrinkage": shrinkage, "minimum_shared": minimum_shared,
        "block_size": block_size, "largest_block_rows": maximum_rows,
        "largest_block_nonzeros": maximum_block_nnz,
        "edges": graph.nnz, "items_without_neighbors": int(np.count_nonzero(degrees == 0)),
        "maximum_neighbors": int(degrees.max()) if len(degrees) else 0,
        "positive_zero_columns": int(np.count_nonzero(support == 0)),
        "payload_bytes": payload_bytes(graph), "elapsed_seconds": time.perf_counter() - started,
        "full_dense_item_matrix_created": False,
        "row_order": "descending float32 similarity, then original item ID index",
    }


def trim_neighbors(graph, k):
    if k < 1:
        raise ValueError("k must be positive")
    values, indices, indptr = [], [], [0]
    for row in range(graph.shape[0]):
        begin, end = graph.indptr[row:row + 2]
        end = min(end, begin + k)
        values.extend(graph.data[begin:end].tolist())
        indices.extend(graph.indices[begin:end].tolist())
        indptr.append(len(values))
    return sparse.csr_array((np.asarray(values, dtype=np.float32), np.asarray(indices, dtype=np.int32),
                             np.asarray(indptr, dtype=np.int32)), shape=graph.shape)


def save_sparse(path, matrix):
    with Path(path).open("xb") as stream:
        sparse.save_npz(stream, matrix, compressed=True)


class ItemRecommender:
    """Seed profiles and graph remain frozen; only the supplied mask varies."""

    def __init__(self, matrix, users, items, graph, snapshot):
        if matrix.shape != (len(users), len(items)) or graph.shape != (len(items), len(items)):
            raise ValueError("Matrix, graph, and mappings disagree")
        self.matrix, self.graph = matrix, graph
        self.users, self.items = users, items
        self.user_index = {user: i for i, user in enumerate(users)}
        self.snapshot = snapshot
        self.fallback = popularity.build_ranking(snapshot)
        self.usage = Counter()
        self.last_sources = []

    def score_candidates(self, user, seen):
        row = self.user_index.get(user)
        if row is None:
            return {}
        scores = {}
        begin, end = self.matrix.indptr[row:row + 2]
        for seed in self.matrix.indices[begin:end]:
            start, stop = self.graph.indptr[seed:seed + 2]
            for candidate, similarity in zip(self.graph.indices[start:stop], self.graph.data[start:stop]):
                product = self.items[int(candidate)]
                if product not in seen:
                    scores[product] = scores.get(product, 0.0) + float(similarity)
        return scores

    def __call__(self, user, seen, k=10):
        if k < 1:
            raise ValueError("k must be positive")
        scores = self.score_candidates(user, seen)
        ranked = sorted(scores, key=lambda p: (-scores[p], -self.snapshot["items"][p]["count"], p))
        result = [(product, scores[product]) for product in ranked[:k]]
        personalized = len(result)
        chosen = set(product for product, _ in result)
        if len(result) < k:
            for product, _ in self.fallback:
                if product not in seen and product not in chosen:
                    result.append((product, 0.0))
                    chosen.add(product)
                    if len(result) == k:
                        break
        self.usage["users"] += 1
        self.usage["users_with_personalized_recommendations"] += personalized > 0
        self.usage["users_with_only_fallback"] += personalized == 0
        self.usage["personalized_slots"] += personalized
        self.usage["fallback_slots"] += len(result) - personalized
        self.usage["total_slots"] += len(result)
        self.last_sources = ["collaborative"] * personalized + ["popularity_fallback"] * (len(result) - personalized)
        return result

    def usage_summary(self):
        c = self.usage
        return {**dict(c),
                "fraction_users_personalized": c["users_with_personalized_recommendations"] / c["users"] if c["users"] else 0,
                "fraction_fallback_slots": c["fallback_slots"] / c["total_slots"] if c["total_slots"] else 0}
