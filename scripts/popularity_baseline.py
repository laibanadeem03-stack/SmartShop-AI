"""Frozen training-only count and smoothed quality-aware popularity rankings."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_evaluation as preparation


def fit_training(rows, train_end):
    items, seen, user_counts = {}, {}, Counter()
    ratings_sum = 0.0
    n = 0
    for user, product, rating_text, timestamp_text in rows:
        if int(timestamp_text) > train_end:
            raise ValueError("Future interaction cannot enter the training snapshot")
        rating = float(rating_text)
        if not math.isfinite(rating) or not 1 <= rating <= 5:
            raise ValueError("Invalid training rating")
        history = seen.setdefault(user, set())
        if product in history:
            raise ValueError("Repeated training user-product pair")
        history.add(product)
        item = items.setdefault(product, {"count": 0, "rating_sum": 0.0})
        item["count"] += 1
        item["rating_sum"] += rating
        user_counts[user] += 1
        ratings_sum += rating
        n += 1
    if not n:
        raise ValueError("Cannot fit an empty training partition")
    return {"items": items, "seen": seen, "user_counts": dict(user_counts),
            "interaction_count": n, "global_mean": ratings_sum / n,
            "train_end_ms": train_end}


def snapshot_payload(snapshot):
    return {**snapshot, "seen": {u: sorted(products) for u, products in snapshot["seen"].items()}}


def fingerprint(snapshot):
    serialized = json.dumps(snapshot_payload(snapshot), sort_keys=True, ensure_ascii=True,
                            separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def quality_score(count, rating_sum, global_mean, m):
    if count < 1 or m <= 0:
        raise ValueError("Positive count and prior strength are required")
    quality = (rating_sum + m * global_mean) / (count + m)
    return ((quality - 1) / 4) * math.log1p(count)


def build_ranking(snapshot, method="count", m=None):
    if method not in ("count", "quality") or (method == "quality" and m not in (5, 10, 20)):
        raise ValueError("Unsupported baseline specification")
    ranking = []
    for product, item in snapshot["items"].items():
        score = float(item["count"]) if method == "count" else quality_score(
            item["count"], item["rating_sum"], snapshot["global_mean"], m
        )
        ranking.append((product, score))
    return sorted(ranking, key=lambda pair: (-pair[1], -snapshot["items"][pair[0]]["count"], pair[0]))


def recommend(ranking, seen, k=10):
    if k < 1:
        raise ValueError("k must be positive")
    result = []
    for product, score in ranking:
        if product not in seen:
            result.append((product, score))
            if len(result) == k:
                break
    return result


def extend_history(training_seen, rows, validation_end):
    """Copy masks, never mutate frozen training statistics or history."""
    past = {user: set(products) for user, products in training_seen.items()}
    for user, product, _rating, timestamp in rows:
        if int(timestamp) > validation_end:
            raise ValueError("Future interaction cannot enter a pre-test seen mask")
        past.setdefault(user, set()).add(product)
    return past


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-csv", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    train = preparation.require_local(args.train_csv)
    output = preparation.require_local(args.output)
    snapshot = fit_training(preparation.iter_rows(train), preparation.TRAIN_END)
    preparation.write_json(output, {"fingerprint": fingerprint(snapshot), "training": snapshot_payload(snapshot)})
    print(json.dumps({"training_interactions": snapshot["interaction_count"],
                      "training_products": len(snapshot["items"]), "output": str(output)}))


if __name__ == "__main__":
    main()
