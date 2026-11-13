"""Create verified chronological partitions from the approved subset only."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import itertools
import json
import math
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "data" / "local"
HEADER = ["user_id", "parent_asin", "rating", "timestamp"]
TRAIN_END = 1_615_865_531_064
VALIDATION_END = 1_648_169_261_066
APPROVED_SHA256 = "feebd8873792da28db06ba4e370b9757d6eb0c476ebf7f44f6dea7f3fb3b4942"
EXPECTED_COUNTS = {"train": 136_883, "validation": 17_110, "test": 17_111}
MIB = 1024 ** 2


def load_local(name):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha256(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(MIB), b""):
            result.update(chunk)
    return result.hexdigest()


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def require_local(path):
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(LOCAL.resolve()):
        raise ValueError("Data paths must be within this project's ignored data/local directory")
    if "/data/local/" not in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines():
        raise ValueError("The explicit local-data ignore rule is missing")
    return resolved


def iter_rows(path):
    """Yield the original strings; numeric interpretation never rewrites fields."""
    with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        if next(reader, None) != HEADER:
            raise ValueError("Unexpected ratings header")
        for row in reader:
            if len(row) != 4:
                raise ValueError("Unexpected ratings row width")
            user, product, rating, timestamp = row
            if not user or not product or user != user.strip() or product != product.strip():
                raise ValueError("Invalid ID; refusing to normalize its identity")
            value = float(rating)
            if not math.isfinite(value) or not 1 <= value <= 5:
                raise ValueError("Invalid rating")
            if not timestamp or not timestamp.isascii() or not timestamp.isdigit():
                raise ValueError("Expected a nonnegative integer epoch-millisecond timestamp")
            yield tuple(row)


def partition(timestamp, train_end=TRAIN_END, validation_end=VALIDATION_END):
    if train_end >= validation_end:
        raise ValueError("Chronological cutoffs must be increasing")
    value = int(timestamp)
    return "train" if value <= train_end else "validation" if value <= validation_end else "test"


def prepare(source, expected_sha, output_parent, train_end=TRAIN_END,
            validation_end=VALIDATION_END, expected_counts=None):
    """Generic helper also used with small, isolated synthetic fixtures."""
    started = time.perf_counter()
    source = Path(source).resolve(strict=True)
    parent = Path(output_parent).resolve(strict=True)
    if train_end >= validation_end:
        raise ValueError("Chronological cutoffs must be increasing")
    before = source.stat()
    if sha256(source) != expected_sha:
        raise ValueError("Subset checksum differs from the approved manifest")
    disk = shutil.disk_usage(parent)
    required = before.st_size * 12 + 128 * MIB
    if disk.free < required:
        raise OSError("Insufficient disk space for the conservative evaluation budget")
    directory = Path(tempfile.mkdtemp(prefix="evaluation-", dir=parent))
    database = directory / "evaluation.sqlite3"
    database.touch(exist_ok=False)
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA cache_size=-32768")
        connection.execute("PRAGMA temp_store=FILE")
        escaped = str(directory).replace("'", "''")
        connection.execute(f"PRAGMA temp_store_directory='{escaped}'")
        connection.execute("""
            CREATE TABLE interactions(
                source_row INTEGER PRIMARY KEY, user_id TEXT NOT NULL,
                product_id TEXT NOT NULL, rating_text TEXT NOT NULL,
                timestamp_text TEXT NOT NULL, timestamp_ms INTEGER NOT NULL,
                rating_value REAL NOT NULL, window TEXT NOT NULL,
                UNIQUE(user_id, product_id)
            )
        """)
        batch = []
        count = 0
        for number, row in enumerate(iter_rows(source), 1):
            timestamp = int(row[3])
            batch.append((number, *row, timestamp, float(row[2]),
                          partition(timestamp, train_end, validation_end)))
            count += 1
            if len(batch) == 10_000:
                with connection:
                    connection.executemany("INSERT INTO interactions VALUES (?,?,?,?,?,?,?,?)", batch)
                batch.clear()
        with connection:
            connection.executemany("INSERT INTO interactions VALUES (?,?,?,?,?,?,?,?)", batch)
        connection.execute("CREATE INDEX window_order ON interactions(window,source_row)")
        connection.commit()
        if not count:
            raise ValueError("Cannot partition an empty dataset")
        if connection.execute("""
            SELECT 1 FROM interactions GROUP BY timestamp_ms
            HAVING COUNT(DISTINCT window)>1 LIMIT 1
        """).fetchone():
            raise RuntimeError("Equal timestamps crossed a partition boundary")
        windows = {}
        for window in ("train", "validation", "test"):
            path = directory / f"{window}.csv"
            sql = "SELECT user_id,product_id,rating_text,timestamp_text FROM interactions WHERE window=? ORDER BY source_row"
            with path.open("x", encoding="utf-8", newline="") as output:
                writer = csv.writer(output, lineterminator="\n")
                writer.writerow(HEADER)
                writer.writerows(connection.execute(sql, (window,)))
            validated = 0
            for actual, expected in itertools.zip_longest(iter_rows(path), connection.execute(sql, (window,))):
                if actual != expected:
                    raise RuntimeError("Partition did not preserve exact source fields and order")
                validated += 1
            n, users, products, positives, lo, hi = connection.execute("""
                SELECT COUNT(*),COUNT(DISTINCT user_id),COUNT(DISTINCT product_id),
                       COALESCE(SUM(rating_value>=4),0),MIN(timestamp_ms),MAX(timestamp_ms)
                FROM interactions WHERE window=?
            """, (window,)).fetchone()
            if validated != n:
                raise RuntimeError("Partition counts disagree")
            if lo is not None and (partition(lo, train_end, validation_end) != window or
                                   partition(hi, train_end, validation_end) != window):
                raise RuntimeError("Partition time bounds disagree")
            windows[window] = {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size,
                               "interactions": n, "unique_users": users, "unique_products": products,
                               "positive_interactions": positives, "timestamp_min_ms": lo,
                               "timestamp_max_ms": hi, "all_original_fields_verified": True}
        if sum(w["interactions"] for w in windows.values()) != count:
            raise RuntimeError("Partitions do not reconstruct the subset")
        if expected_counts is not None and {name: w["interactions"] for name, w in windows.items()} != expected_counts:
            raise RuntimeError("Actual partition counts differ from the approved diagnostic")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("Evaluation database failed its integrity check")
    finally:
        connection.close()
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or sha256(source) != expected_sha:
        raise RuntimeError("Subset changed while preparing partitions")
    manifest = {
        "status": "complete", "protocol_version": "1.0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": {"path": str(source), "sha256": expected_sha, "bytes": before.st_size,
                   "mtime_ns": before.st_mtime_ns, "interactions": count, "unchanged": True},
        "protocol": {"train_end_inclusive_ms": train_end,
                     "validation_end_inclusive_ms": validation_end, "timestamp_unit": "epoch milliseconds",
                     "rules": ["train: t<=T1", "validation: T1<t<=T2", "test: t>T2"],
                     "equal_timestamps_kept_together": True, "relevant_rating_minimum": 4,
                     "scores_fit_on_training_only": True, "test_seen_filter": "training plus validation",
                     "cold_start_definition": "zero interactions in the frozen training snapshot"},
        "partitions": windows,
        "resources": {"elapsed_seconds": time.perf_counter() - started,
                      "disk_free_before_bytes": disk.free, "reserved_disk_budget_bytes": required,
                      "database_bytes": database.stat().st_size},
    }
    write_json(directory / "split_manifest.json", manifest)
    return directory, manifest


def prepare_approved(subset_manifest, output_parent=LOCAL):
    manifest_path = require_local(subset_manifest)
    prior_hash = sha256(manifest_path)
    prior = json.loads(manifest_path.read_text(encoding="utf-8"))
    if prior.get("status") != "complete" or prior["subset"]["sha256"] != APPROVED_SHA256:
        raise ValueError("Expected the approved completed subset manifest")
    source = require_local(prior["subset"]["path"])
    parent = require_local(output_parent)
    parent.mkdir(parents=True, exist_ok=True)
    directory, result = prepare(source, APPROVED_SHA256, parent, expected_counts=EXPECTED_COUNTS)
    if sha256(manifest_path) != prior_hash:
        raise RuntimeError("The subset manifest changed during preparation")
    write_json(directory / "subset_provenance.json", {
        "manifest_path": str(manifest_path), "manifest_sha256": prior_hash,
        "subset_sha256": APPROVED_SHA256, "original_full_csv_accessed": False,
    })
    return directory, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subset-manifest", required=True, type=Path)
    parser.add_argument("--output-parent", type=Path, default=LOCAL)
    args = parser.parse_args()
    directory, manifest = prepare_approved(args.subset_manifest, args.output_parent)
    print(json.dumps({"run_directory": str(directory), "partition_counts": {
        key: value["interactions"] for key, value in manifest["partitions"].items()}}))


if __name__ == "__main__":
    main()
