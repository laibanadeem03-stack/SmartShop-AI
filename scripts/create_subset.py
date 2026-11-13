"""Create a reproducible ratings subset with SQLite and the standard library.

Read the input and inspection aggregation in read-only mode. Sample users with
seeded SHA-256, prune distinct user/product edges to a fixed point, and export
unchanged CSV field values in source order. Only aggregate temporal diagnostics
are calculated: this script does not save evaluation split assignments.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import importlib.util
import itertools
import json
import math
from pathlib import Path
import platform
import shutil
import sqlite3
import sys
import tempfile
import time
import traceback


VERSION = "1.0"
MIB = 1024 ** 2
HEADER = ["user_id", "parent_asin", "rating", "timestamp"]
FRACTIONS = tuple(Fraction(1, denominator) for denominator in (16, 8, 4, 2, 1))
PROGRESS_AVAILABLE = True
_spec = importlib.util.spec_from_file_location(
    "ratings_inspection", Path(__file__).with_name("inspect_ratings.py")
)
inspection = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(inspection)


def emit(event, **values):
    # Console/pipe failures must not abort successful data processing. Windows
    # can report a closed output pipe as PermissionError rather than BrokenPipe.
    global PROGRESS_AVAILABLE
    if PROGRESS_AVAILABLE:
        try:
            print(json.dumps({"event": event, **values}), flush=True)
        except (BrokenPipeError, PermissionError):
            PROGRESS_AVAILABLE = False


def checksum(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(MIB), b""):
            digest.update(block)
    return digest.hexdigest()


def user_hash(user_id, seed=42):
    """Hash the exact UTF-8 ID, with a zero-byte separator after the seed."""
    return hashlib.sha256(str(seed).encode("ascii") + b"\0" + user_id.encode("utf-8")).hexdigest()


def sampled(user_id, fraction, seed=42):
    fraction = Fraction(fraction)
    if not 0 <= fraction <= 1:
        raise ValueError("Sampling fraction must be in [0, 1]")
    threshold = (fraction.numerator * (1 << 256)) // fraction.denominator
    return int(user_hash(user_id, seed), 16) < threshold


def check_disk(path, required):
    usage = shutil.disk_usage(path)
    if usage.free < required:
        raise OSError("Insufficient free disk space for the documented safety margin")
    return usage._asdict()


def configure(connection, scratch):
    # The writable database is disposable, but retain normal rollback semantics.
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA cache_size=-32768")
    connection.execute("PRAGMA mmap_size=0")
    connection.execute("PRAGMA temp_store=FILE")
    escaped = str(scratch).replace("'", "''")
    connection.execute(f"PRAGMA temp_store_directory='{escaped}'")


def make_edges(connection):
    connection.executescript("""
        DROP TABLE IF EXISTS edges;
        CREATE TABLE edges (
            user_id TEXT NOT NULL, product_id TEXT NOT NULL,
            PRIMARY KEY(user_id, product_id)
        ) WITHOUT ROWID;
    """)


def prune_core(connection, minimum=5):
    """Simultaneously remove deficient vertices, repeating until stable.

    The edges primary key guarantees counts are distinct neighbors rather than
    repeated ratings. Logs contain only aggregate deletion counts.
    """
    if minimum < 1:
        raise ValueError("Minimum degree must be positive")
    connection.executescript("""
        CREATE INDEX IF NOT EXISTS edges_product ON edges(product_id, user_id);
        CREATE TEMP TABLE IF NOT EXISTS weak_users(id TEXT PRIMARY KEY) WITHOUT ROWID;
        CREATE TEMP TABLE IF NOT EXISTS weak_products(id TEXT PRIMARY KEY) WITHOUT ROWID;
    """)
    history = []
    while True:
        with connection:
            connection.execute("DELETE FROM weak_users")
            connection.execute("DELETE FROM weak_products")
            connection.execute(
                "INSERT INTO weak_users SELECT user_id FROM edges GROUP BY user_id HAVING COUNT(*)<?",
                (minimum,),
            )
            connection.execute(
                "INSERT INTO weak_products SELECT product_id FROM edges GROUP BY product_id HAVING COUNT(*)<?",
                (minimum,),
            )
            weak_users = connection.execute("SELECT COUNT(*) FROM weak_users").fetchone()[0]
            weak_products = connection.execute("SELECT COUNT(*) FROM weak_products").fetchone()[0]
            if not weak_users and not weak_products:
                break
            before = connection.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            removed = connection.execute(
                "DELETE FROM edges WHERE user_id IN (SELECT id FROM weak_users) "
                "OR product_id IN (SELECT id FROM weak_products)"
            ).rowcount
        if removed <= 0:
            raise RuntimeError("Graph pruning failed to make progress")
        step = {"round": len(history) + 1, "users_below_minimum": weak_users,
                "products_below_minimum": weak_products, "edges_before": before,
                "edges_removed": removed, "edges_after": before - removed}
        history.append(step)
        emit("pruning_round", **step)
    return history


def graph_statistics(connection, minimum=5):
    connection.executescript("""
        DROP TABLE IF EXISTS user_degrees;
        DROP TABLE IF EXISTS product_degrees;
        CREATE TABLE user_degrees AS SELECT user_id AS id, COUNT(*) AS n FROM edges GROUP BY user_id;
        CREATE TABLE product_degrees AS SELECT product_id AS id, COUNT(*) AS n FROM edges GROUP BY product_id;
    """)
    users = inspection.distribution(connection, "user_degrees", "n")
    products = inspection.distribution(connection, "product_degrees", "n")
    n = connection.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    possible = users["entities"] * products["entities"]
    if users["interactions"] != n or products["interactions"] != n:
        raise RuntimeError("Graph degree totals disagree")
    return {"interactions": n, "unique_users": users["entities"],
            "unique_products": products["entities"], "users": users, "products": products,
            "density": n / possible if possible else None,
            "sparsity": 1 - n / possible if possible else None,
            "five_core": bool(n and users["minimum"] >= 5 and products["minimum"] >= 5),
            "minimum_degree_holds": bool(n and users["minimum"] >= minimum and products["minimum"] >= minimum)}


def prepare_ranked_users(connection, seed=42, batch_size=10_000):
    connection.execute(
        "CREATE TABLE ranked_users(user_id TEXT PRIMARY KEY, hash TEXT NOT NULL) WITHOUT ROWID"
    )
    cursor = connection.execute("SELECT id FROM inspected.valid_users ORDER BY id COLLATE BINARY")
    while batch := cursor.fetchmany(batch_size):
        with connection:
            connection.executemany(
                "INSERT INTO ranked_users VALUES (?,?)", ((user, user_hash(user, seed)) for (user,) in batch)
            )


def evaluate_fraction(connection, fraction, minimum=5):
    started = time.perf_counter()
    connection.executescript("""
        DROP TABLE IF EXISTS sampled_users;
        CREATE TABLE sampled_users(user_id TEXT PRIMARY KEY) WITHOUT ROWID;
    """)
    if fraction == 1:
        connection.execute("INSERT INTO sampled_users SELECT user_id FROM ranked_users")
    else:
        threshold = (fraction.numerator * (1 << 256)) // fraction.denominator
        connection.execute(
            "INSERT INTO sampled_users SELECT user_id FROM ranked_users WHERE hash<?",
            (f"{threshold:064x}",),
        )
    connection.commit()
    make_edges(connection)
    with connection:
        connection.execute("""
            INSERT INTO edges SELECT p.user_id, p.product_id
            FROM sampled_users AS s JOIN inspected.pairs AS p ON p.user_id=s.user_id
            WHERE p.valid_n>0
        """)
    before = {
        "sampled_users": connection.execute("SELECT COUNT(*) FROM sampled_users").fetchone()[0],
        "interactions": connection.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
        "unique_products": connection.execute("SELECT COUNT(DISTINCT product_id) FROM edges").fetchone()[0],
    }
    emit("sample_created", fraction=str(fraction), **before)
    rounds = prune_core(connection, minimum)
    result = {"fraction": str(fraction), "before_pruning": before,
              "pruning_rounds": rounds, "after_pruning": graph_statistics(connection, minimum),
              "elapsed_seconds": time.perf_counter() - started}
    emit("fraction_complete", fraction=str(fraction),
         interactions=result["after_pruning"]["interactions"], rounds=len(rounds))
    return result


def choose_fraction(evaluate, lower=100_000, upper=200_000, refinements=8):
    """Double exact fractions, then bisect an overshoot without cutting edges."""
    if not 1 <= lower <= upper or refinements < 0:
        raise ValueError("Invalid target interval or refinement count")
    attempts = []

    def run(fraction):
        result = evaluate(fraction)
        attempts.append(result)
        # Nested hash samples and their maximal k-cores must be monotone.
        counts = sorted((Fraction(a["fraction"]), a["after_pruning"]["interactions"]) for a in attempts)
        if any(a[1] > b[1] for a, b in zip(counts, counts[1:])):
            raise RuntimeError("Nested-core sizes were not monotone")
        return result

    low = Fraction(0)
    best = None
    for fraction in FRACTIONS:
        result = run(fraction)
        count = result["after_pruning"]["interactions"]
        if count >= lower:
            best = result
            if count <= upper:
                return result, attempts
            high = fraction
            for _ in range(refinements):
                mid = (low + high) / 2
                candidate = run(mid)
                count = candidate["after_pruning"]["interactions"]
                if count < lower:
                    low = mid
                else:
                    high, best = mid, candidate
                    if count <= upper:
                        return candidate, attempts
            return best, attempts
        low = fraction
    nonempty = [a for a in attempts if a["after_pruning"]["interactions"]]
    if not nonempty:
        raise RuntimeError("Every sampled graph collapsed, including the full input")
    return max(nonempty, key=lambda a: a["after_pruning"]["interactions"]), attempts


def timestamp_ms(value):
    integer = int(value)
    # Same documented unit heuristic as inspection; integer ordering avoids float loss.
    return integer if abs(integer) >= 100_000_000_000 else integer * 1000


def collect_records(connection, dataset, expected_rows, batch_size=10_000):
    connection.execute("""
        CREATE TABLE records(
            source_row INTEGER PRIMARY KEY,
            user_id TEXT NOT NULL, product_id TEXT NOT NULL,
            rating_text TEXT NOT NULL, timestamp_text TEXT NOT NULL,
            timestamp_ms INTEGER NOT NULL,
            UNIQUE(user_id, product_id)
        )
    """)
    users = {row[0] for row in connection.execute("SELECT id FROM user_degrees")}
    batch = []
    matched = 0
    records_seen = 0
    with Path(dataset).open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source, strict=True)
        if next(reader) != HEADER:
            raise ValueError("Expected the inspected four-column header")
        for row_number, row in enumerate(reader, 1):
            records_seen = row_number
            if len(row) != 4:
                raise ValueError("Unexpected CSV row width; no data was silently discarded")
            user, product, rating, timestamp = row
            if not user or not product or user != user.strip() or product != product.strip():
                raise ValueError("Input IDs conflict with the inspected exact-ID graph; refusing normalization")
            if user not in users:
                continue
            if not connection.execute(
                "SELECT 1 FROM edges WHERE user_id=? AND product_id=?", (user, product)
            ).fetchone():
                continue
            value = float(rating)
            if not math.isfinite(value) or not 1 <= value <= 5:
                raise ValueError("Unexpected invalid selected rating")
            batch.append((row_number, user, product, rating, timestamp, timestamp_ms(timestamp)))
            matched += 1
            if len(batch) >= batch_size:
                with connection:
                    connection.executemany("INSERT INTO records VALUES (?,?,?,?,?,?)", batch)
                batch.clear()
            if matched % 100_000 == 0:
                emit("records_preserved", selected_records=matched)
        with connection:
            connection.executemany("INSERT INTO records VALUES (?,?,?,?,?,?)", batch)
    graph_rows = connection.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    if records_seen != expected_rows or matched != graph_rows:
        raise RuntimeError("CSV and inspected graph do not agree on selected edges or total rows")
    connection.executescript("""
        CREATE INDEX records_user_time ON records(user_id, timestamp_ms DESC, source_row DESC);
        CREATE INDEX records_time ON records(timestamp_ms, source_row);
    """)
    return {"input_records_seen": records_seen, "matched_records": matched,
            "field_values_preserved": True, "source_order_preserved": True,
            "id_normalization_applied": False}


def export_and_validate(connection, output):
    with Path(output).open("x", encoding="utf-8", newline="") as destination:
        writer = csv.writer(destination, lineterminator="\n")
        writer.writerow(HEADER)
        for row in connection.execute(
            "SELECT user_id, product_id, rating_text, timestamp_text FROM records ORDER BY source_row"
        ):
            writer.writerow(row)
    count = 0
    with Path(output).open("r", encoding="utf-8", newline="") as source:
        reader = csv.reader(source, strict=True)
        if next(reader) != HEADER:
            raise RuntimeError("Export header did not round-trip")
        expected = connection.execute(
            "SELECT user_id, product_id, rating_text, timestamp_text FROM records ORDER BY source_row"
        )
        for actual, original in itertools.zip_longest(reader, expected):
            if actual is None or original is None or tuple(actual) != original:
                raise RuntimeError("Export did not preserve original field values and order")
            count += 1
    return {"rows_validated": count, "all_fields_round_trip": True, "sha256": checksum(output),
            "bytes": Path(output).stat().st_size}


def temporal_diagnostics(connection, graph):
    """Aggregate hypothetical protocols, never persisting row split labels."""
    n, users = graph["interactions"], graph["unique_users"]
    per_user = """
        WITH ranked AS (
            SELECT user_id, product_id, timestamp_ms, ROW_NUMBER() OVER (
                PARTITION BY user_id ORDER BY timestamp_ms DESC, source_row DESC
            ) AS recency FROM records
        ), products AS (
            SELECT product_id, SUM(recency>2) AS train_n,
                   SUM(recency=2) AS validation_n, SUM(recency=1) AS test_n
            FROM ranked GROUP BY product_id
        )
    """
    row = connection.execute(per_user + """
        SELECT COUNT(*), MIN(train_n), SUM(train_n=0), SUM(train_n<5),
               SUM(CASE WHEN train_n=0 THEN validation_n ELSE 0 END),
               SUM(CASE WHEN train_n=0 THEN test_n ELSE 0 END)
        FROM products
    """).fetchone()
    train_max, test_min, val_min = connection.execute(per_user + """
        SELECT MAX(CASE WHEN recency>2 THEN timestamp_ms END),
               MIN(CASE WHEN recency=1 THEN timestamp_ms END),
               MIN(CASE WHEN recency=2 THEN timestamp_ms END) FROM ranked
    """).fetchone()
    tied_users = connection.execute("""
        WITH ranked AS (
            SELECT user_id, timestamp_ms, ROW_NUMBER() OVER (
                PARTITION BY user_id ORDER BY timestamp_ms DESC, source_row DESC
            ) AS recency FROM records
        ) SELECT COUNT(*) FROM (
            SELECT user_id FROM ranked GROUP BY user_id
            HAVING MAX(CASE WHEN recency=1 THEN timestamp_ms END)=MAX(CASE WHEN recency=2 THEN timestamp_ms END)
                OR MAX(CASE WHEN recency=2 THEN timestamp_ms END)=MAX(CASE WHEN recency=3 THEN timestamp_ms END)
        )
    """).fetchone()[0]
    leave_two = {
        "protocol": "Latest one per user test; previous one validation; all other rows training (diagnostic only)",
        "training_interactions": n - 2 * users, "validation_interactions": users, "test_interactions": users,
        "training_users": users, "users_without_training_history": 0,
        "user_training_minimum": graph["users"]["minimum"] - 2,
        "user_training_median": graph["users"]["median"] - 2,
        "user_training_mean": (n - 2 * users) / users,
        "product_training_minimum": row[1], "products_without_training_history": row[2],
        "products_below_five_training_interactions": row[3],
        "validation_interactions_with_unseen_product": row[4],
        "test_interactions_with_unseen_product": row[5],
        "users_with_ties_across_holdout_boundaries": tied_users,
        "maximum_training_timestamp_ms": train_max, "minimum_test_timestamp_ms": test_min,
        "minimum_validation_timestamp_ms": val_min,
    }
    train_end, validation_end = n * 8 // 10, n * 9 // 10
    global_cte = f"""
        WITH ranked AS (
            SELECT user_id, product_id, timestamp_ms,
                   ROW_NUMBER() OVER (ORDER BY timestamp_ms, source_row) AS position FROM records
        ), users AS (
            SELECT user_id, SUM(position<={train_end}) AS train_n FROM ranked GROUP BY user_id
        ), products AS (
            SELECT product_id, SUM(position<={train_end}) AS train_n FROM ranked GROUP BY product_id
        )
    """
    user_stats = connection.execute(global_cte + """
        SELECT MIN(train_n), AVG(train_n), SUM(train_n=0), SUM(train_n<3) FROM users
    """).fetchone()
    product_stats = connection.execute(global_cte + """
        SELECT MIN(train_n), AVG(train_n), SUM(train_n=0), SUM(train_n<5) FROM products
    """).fetchone()
    coverage = {}
    for name, begin, end in (("validation", train_end, validation_end), ("test", validation_end, n)):
        cold = connection.execute(global_cte + """
            SELECT SUM(u.train_n=0), SUM(p.train_n=0), SUM(u.train_n=0 OR p.train_n=0),
                   COUNT(DISTINCT CASE WHEN u.train_n=0 THEN r.user_id END),
                   COUNT(DISTINCT CASE WHEN p.train_n=0 THEN r.product_id END)
            FROM ranked r JOIN users u ON r.user_id=u.user_id
            JOIN products p ON r.product_id=p.product_id WHERE position>? AND position<=?
        """, (begin, end)).fetchone()
        coverage[name] = {
            "interactions": end - begin, "interactions_with_unseen_user": cold[0] or 0,
            "interactions_with_unseen_product": cold[1] or 0,
            "interactions_with_either_unseen": cold[2] or 0,
            "unique_unseen_users": cold[3], "unique_unseen_products": cold[4],
        }
    train_cut, val_cut, minimum_time, maximum_time = connection.execute(global_cte + f"""
        SELECT MAX(CASE WHEN position<={train_end} THEN timestamp_ms END),
               MAX(CASE WHEN position<={validation_end} THEN timestamp_ms END),
               MIN(timestamp_ms), MAX(timestamp_ms) FROM ranked
    """).fetchone()
    boundary_ties = connection.execute(
        "SELECT COUNT(*) FROM records WHERE timestamp_ms IN (?,?)", (train_cut, val_cut)
    ).fetchone()[0]
    global_time = {
        "protocol": "Global chronological 80/10/10 by (timestamp_ms, source_row); diagnostic only",
        "training_interactions": train_end, **coverage,
        "user_training_minimum": user_stats[0], "user_training_mean": user_stats[1],
        "users_without_training_history": user_stats[2],
        "users_below_three_training_interactions": user_stats[3],
        "product_training_minimum": product_stats[0], "product_training_mean": product_stats[1],
        "products_without_training_history": product_stats[2],
        "products_below_five_training_interactions": product_stats[3],
        "training_boundary_timestamp_ms": train_cut, "validation_boundary_timestamp_ms": val_cut,
        "rows_at_boundary_timestamps": boundary_ties,
    }
    return {"no_split_files_or_row_assignments_saved": True,
            "timestamp_order": "Integer milliseconds using the inspection unit heuristic; source-row tie-breaker",
            "timestamp_minimum_ms": minimum_time, "timestamp_maximum_ms": maximum_time,
            "per_user_leave_two_out": leave_two, "global_chronological_80_10_10": global_time}


def directory_bytes(directory):
    return sum(p.stat().st_size for p in Path(directory).rglob("*") if p.is_file())


def validate_input(dataset, summary_path, aggregation):
    summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    if Path(summary["source"]["path"]).resolve() != dataset:
        raise ValueError("Inspection summary belongs to a different input path")
    if dataset.stat().st_size != summary["source"]["bytes"]:
        raise ValueError("Input size differs from the inspected source")
    if checksum(dataset) != summary["source"]["sha256"]:
        raise ValueError("Input checksum differs from the inspected source")
    if summary["totals"]["records"] != summary["totals"]["valid"]:
        raise ValueError("This pipeline requires the already validated complete source")
    if summary["duplicates"]["valid"]["excess_interactions"]:
        raise ValueError("Deduplicate repeated pairs explicitly before using this pipeline")
    if summary["totals"].get("invalid_timestamp", 0) or summary["totals"].get("missing_timestamp", 0):
        raise ValueError("Complete valid timestamps are required for temporal diagnostics")
    if not aggregation.is_file():
        raise ValueError("The inspected aggregation is missing")
    return summary


def run(dataset, summary_path, aggregation, output_parent, scratch_parent,
        report=None, lower=100_000, upper=200_000, refinements=8, seed=42):
    started = time.perf_counter()
    dataset = Path(dataset).resolve(strict=True)
    aggregation = Path(aggregation).resolve(strict=True)
    summary_path = Path(summary_path).resolve(strict=True)
    output_parent = Path(output_parent).resolve(strict=True)
    scratch_parent = Path(scratch_parent).resolve(strict=True)
    report = Path(report).resolve() if report else None
    project = Path(__file__).resolve().parents[1]
    if report and (report.exists() or not report.parent.is_dir()):
        raise ValueError("Report requires an existing parent and a new filename")
    if scratch_parent.is_relative_to(project) or any(
        (p / ".git").exists() for p in (scratch_parent, *scratch_parent.parents)
    ):
        raise ValueError("Scratch storage must be outside the project and Git working trees")
    if output_parent.is_relative_to(project):
        ignored = project / "data" / "local"
        ignore_file = project / ".gitignore"
        if not output_parent.is_relative_to(ignored) or not ignore_file.is_file() or "/data/local/" not in ignore_file.read_text(encoding="utf-8").splitlines():
            raise ValueError("Output inside this project must be under explicitly ignored data/local")
    elif any((p / ".git").exists() for p in (output_parent, *output_parent.parents)):
        raise ValueError("External output must be outside Git working trees")
    required = dataset.stat().st_size * 6 + 128 * MIB
    disk_before = {"output": check_disk(output_parent, required), "scratch": check_disk(scratch_parent, required)}
    source_before = dataset.stat()
    summary = validate_input(dataset, summary_path, aggregation)
    aggregation_hash = checksum(aggregation)
    scratch = Path(tempfile.mkdtemp(prefix="smartshop-subset-work-", dir=scratch_parent))
    output = Path(tempfile.mkdtemp(prefix=f"smartshop-seed{seed}-", dir=output_parent))
    emit("run_created", output_directory=str(output), scratch_directory=str(scratch),
         disk_free_bytes=disk_before["scratch"]["free"], estimated_required_bytes=required)
    work_db = scratch / "subset_work.sqlite3"
    work_db.touch(exist_ok=False)
    connection = sqlite3.connect(work_db.as_uri(), uri=True)
    try:
        configure(connection, scratch)
        connection.execute("ATTACH DATABASE ? AS inspected", (aggregation.as_uri() + "?mode=ro",))
        connection.execute("PRAGMA inspected.cache_size=-32768")
        if connection.execute("PRAGMA inspected.quick_check").fetchone()[0] != "ok":
            raise RuntimeError("Inspection database failed its integrity check")
        pair_count, total_valid, lo, hi = connection.execute(
            "SELECT COUNT(*), SUM(valid_n), MIN(valid_n), MAX(valid_n) FROM inspected.pairs"
        ).fetchone()
        if pair_count != summary["totals"]["records"] or total_valid != pair_count or lo != 1 or hi != 1:
            raise RuntimeError("Inspection graph does not match its validated summary")
        prepare_ranked_users(connection, seed)

        def evaluate(fraction):
            check_disk(scratch, 128 * MIB)
            return evaluate_fraction(connection, fraction)

        selected, attempts = choose_fraction(evaluate, lower, upper, refinements)
        if attempts[-1]["fraction"] != selected["fraction"]:
            rebuilt = evaluate(Fraction(selected["fraction"]))
            if rebuilt["after_pruning"] != selected["after_pruning"]:
                raise RuntimeError("Selected core was not reproducible on rebuilding")
        graph = selected["after_pruning"]
        if not graph["five_core"]:
            raise RuntimeError("Selected graph does not meet the five-neighbor requirement")
        check_disk(output, 128 * MIB + graph["interactions"] * 128)
        preservation = collect_records(connection, dataset, summary["totals"]["records"])
        subset = output / "ratings_subset.csv"
        exported = export_and_validate(connection, subset)
        if exported["rows_validated"] != graph["interactions"]:
            raise RuntimeError("Export and graph interaction counts disagree")
        ratings = dict(connection.execute(
            "SELECT CAST(rating_text AS REAL), COUNT(*) FROM records GROUP BY CAST(rating_text AS REAL) ORDER BY 1"
        ))
        if sum(ratings.values()) != graph["interactions"]:
            raise RuntimeError("Rating counts disagree with graph size")
        temporal = temporal_diagnostics(connection, graph)
        if connection.execute("PRAGMA main.quick_check").fetchone()[0] != "ok":
            raise RuntimeError("Working database failed its integrity check")
    except Exception:
        emit("run_incomplete", output_directory=str(output), scratch_directory=str(scratch))
        raise
    finally:
        connection.close()
    source_after = dataset.stat()
    if (source_before.st_size, source_before.st_mtime_ns) != (source_after.st_size, source_after.st_mtime_ns) or checksum(dataset) != summary["source"]["sha256"]:
        raise RuntimeError("Original input changed during the run; do not use this subset")
    if checksum(aggregation) != aggregation_hash:
        raise RuntimeError("The read-only inspection aggregation changed during the run")
    result = {
        "status": "complete", "algorithm_version": VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "input": {"path": str(dataset), "sha256": summary["source"]["sha256"],
                  "bytes": source_before.st_size, "interactions": summary["totals"]["records"],
                  "unique_users": summary["stages"]["deduplicated"]["users"]["entities"],
                  "unique_products": summary["stages"]["deduplicated"]["products"]["entities"],
                  "rating_distribution": summary["ratings"]["valid"], "unchanged_size_mtime_and_sha256": True},
        "aggregation": {"path": str(aggregation), "sha256": aggregation_hash,
                        "opened_read_only": True, "unchanged_sha256": True},
        "sampling": {"seed": seed, "hash": "SHA-256(ASCII(seed) + zero byte + UTF-8 exact user ID)",
                     "comparison": "unsigned big-endian digest < floor(fraction * 2**256)",
                     "initial_fractions": [str(f) for f in FRACTIONS], "maximum_bisections": refinements,
                     "target_lower": lower, "target_upper": upper, "selected_fraction": selected["fraction"],
                     "within_target": lower <= graph["interactions"] <= upper,
                     "minimum_distinct_neighbors": 5, "attempts": attempts,
                     "selection_policy": "First core in target; bisect overshoot at most eight times; otherwise retain smallest viable overshoot or largest available undershoot"},
        "subset": {"path": str(subset), **exported, **graph, "rating_distribution": ratings,
                   "retained_interaction_fraction": graph["interactions"] / summary["totals"]["records"],
                   "preservation": preservation},
        "temporal_diagnostics": temporal,
        "resources": {"elapsed_seconds": time.perf_counter() - started,
                      "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                      "progress_output_available": PROGRESS_AVAILABLE,
                      **inspection.process_memory(), "disk_before": disk_before,
                      "disk_after": {"output": shutil.disk_usage(output)._asdict(),
                                     "scratch": shutil.disk_usage(scratch)._asdict()},
                      "conservative_disk_reservation_bytes": required,
                      "scratch_directory": str(scratch), "scratch_retained_bytes": directory_bytes(scratch),
                      "output_bytes_before_manifest": directory_bytes(output),
                      "sqlite_main_and_attached_cache_budget_each_bytes": 32 * MIB},
    }
    with (output / "manifest.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    if report:
        with report.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(report_markdown(result))
    emit("complete", interactions=graph["interactions"], users=graph["unique_users"],
         products=graph["unique_products"], fraction=selected["fraction"],
         subset_path=str(subset), manifest_path=str(output / "manifest.json"))
    return result


def report_markdown(r):
    n = inspection.number
    s, sampling, resources = r["subset"], r["sampling"], r["resources"]
    t = r["temporal_diagnostics"]
    per, global_time = t["per_user_leave_two_out"], t["global_chronological_80_10_10"]
    lines = ["# SmartShop-AI reproducible subset report", "",
             f"Completed at {r['created_utc']} (UTC), algorithm version {r['algorithm_version']}.", "",
             "## Input, output, and preservation", "",
             f"- Original CSV: `{r['input']['path']}`.",
             f"- Input SHA-256: `{r['input']['sha256']}`.",
             f"- Read-only inspection aggregation: `{r['aggregation']['path']}`.",
             f"- Aggregation SHA-256: `{r['aggregation']['sha256']}`.",
             "- Original CSV size, modification time, and checksum were unchanged; the aggregation checksum was also unchanged.",
             f"- Subset CSV: `{s['path']}`.",
             f"- Subset SHA-256: `{s['sha256']}`; {n(s['bytes'])} bytes ({s['bytes']/MIB:.2f} MiB).",
             f"- Aggregate manifest: `{Path(s['path']).with_name('manifest.json')}`.",
             "- Columns remain `user_id`, `parent_asin`, `rating`, `timestamp`. All four field values round-tripped "
             "exactly against selected source rows; IDs retain string identity, case, and leading zeros. Ratings and "
             "timestamps retain their original text and units. Source record order is preserved. CSV quoting/newlines "
             "may differ, so the subset is not a byte-level excerpt of the input.",
             "- The source contains no duplicate pairs. This pipeline refuses duplicate pairs or unexpected ID whitespace "
             "instead of silently deduplicating or changing ID meaning.",
             "- Output is under `/data/local/`, explicitly excluded by the root `.gitignore`. The subsetting script runs no Git commands.", "",
             "## Deterministic sampling and pruning", "",
             f"Seed: **{sampling['seed']}**. Compute SHA-256 over ASCII seed, one zero byte, and the exact UTF-8 user ID. "
             "Interpret the 256-bit digest as an unsigned big-endian integer and retain a user when it is below "
             "`floor(fraction * 2**256)`. Fractions and thresholds use integer/rational arithmetic; Python's randomized "
             "hash and input enumeration order do not affect selection.", "",
             "Try 1/16, 1/8, 1/4, 1/2, then 1 until a pruned graph reaches the lower target. If it exceeds the upper "
             "target, bisect the exact fraction interval between the latest undershoot and overshoot up to eight times. "
             "Choose the first result in the target interval. If no refinement reaches the target, retain the smallest "
             "observed viable overshoot; if even the full graph is smaller than the lower target, use the largest available "
             "nonempty core. Never cut rows from a converged core merely to hit a size cap.", "",
             "Within each sample, count distinct pairs using a SQLite primary key. Simultaneously remove users and products "
             "with fewer than five distinct neighbors, recompute degrees, and repeat until neither side is deficient. "
             "The manifest retains every pruning round. Retained hash samples are nested; the implementation checks "
             "that converged-core interaction counts are monotone with the sampling fraction.", "",
             f"Requested target: {n(sampling['target_lower'])}–{n(sampling['target_upper'])} interactions. "
             f"Selected fraction: **{sampling['selected_fraction']}**. Within target: **{sampling['within_target']}**.", "",
             "| Fraction | Sampled users | Edges before pruning | Pruning rounds | Retained edges | Retained users | Retained products |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for a in sampling["attempts"]:
        before, after = a["before_pruning"], a["after_pruning"]
        lines.append(f"| {a['fraction']} | {n(before['sampled_users'])} | {n(before['interactions'])} | "
                     f"{len(a['pruning_rounds'])} | {n(after['interactions'])} | {n(after['unique_users'])} | {n(after['unique_products'])} |")
    lines += ["", "## Subset statistics", "", "| Measure | Value |", "|---|---:|",
              f"| Interactions / distinct pairs | {n(s['interactions'])} |",
              f"| Unique users | {n(s['unique_users'])} |", f"| Unique products | {n(s['unique_products'])} |",
              f"| Sparsity: 1 − edges / (users × products) | {s['sparsity']:.8%} |",
              f"| Density | {s['density']:.8%} |", f"| Distinct-neighbor 5-core holds | {s['five_core']} |",
              f"| Original interactions retained | {s['retained_interaction_fraction']:.2%} |", "",
              "| Entity | Minimum | Median | Mean | P90 | P95 | P99 | Maximum |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for entity in ("users", "products"):
        lines.append(f"| {entity} | " + " | ".join(n(s[entity][key]) for key in (
            "minimum", "median", "mean", "p90", "p95", "p99", "maximum")) + " |")
    lines += ["", "| Rating | Subset count | Subset share | Source share |", "|---|---:|---:|---:|"]
    source_ratings = {float(k): v for k, v in r["input"]["rating_distribution"].items()}
    for rating, count in s["rating_distribution"].items():
        source_count = source_ratings.get(float(rating), 0)
        lines.append(f"| {float(rating):g} | {n(count)} | {count/s['interactions']:.2%} | {source_count/r['input']['interactions']:.2%} |")
    lines += ["", "## Prospective temporal coverage diagnostics", "",
              "These are aggregate what-if calculations only. No final evaluation split files, row labels, or user "
              "assignments were saved. All diagnostics order integer epoch milliseconds, breaking timestamp ties by "
              "source record number; no timestamp field in the export is rewritten.", "",
              "### Per-user chronological leave-two-out", "",
              "Hypothesis: reserve each user's latest interaction for test, the previous one for validation, and keep "
              "the rest for training. This construction preserves at least three training interactions per retained "
              "user, but does not preserve five interactions or product coverage in training.", "",
              "| Measure | Value |", "|---|---:|",
              f"| Training / validation / test interactions | {n(per['training_interactions'])} / {n(per['validation_interactions'])} / {n(per['test_interactions'])} |",
              f"| User training minimum / median | {n(per['user_training_minimum'])} / {n(per['user_training_median'])} |",
              f"| Users without training history | {n(per['users_without_training_history'])} |",
              f"| Product training minimum | {n(per['product_training_minimum'])} |",
              f"| Products without training history | {n(per['products_without_training_history'])} |",
              f"| Products below five training interactions | {n(per['products_below_five_training_interactions'])} |",
              f"| Validation interactions with unseen products | {n(per['validation_interactions_with_unseen_product'])} |",
              f"| Test interactions with unseen products | {n(per['test_interactions_with_unseen_product'])} |",
              f"| Users with timestamp ties across holdout boundaries | {n(per['users_with_ties_across_holdout_boundaries'])} |", "",
              "Per-user chronology does not enforce one common time cutoff: another user's training interaction may "
              "occur after a test interaction. Ties resolved by record number are deterministic, not evidence of a real "
              "within-timestamp event order. A later evaluation design must explicitly decide how to handle these issues.", "",
              "### Global chronological 80/10/10", "",
              "Hypothesis: order all interactions by timestamp and source record number, allocate the first 80% to "
              "training, the next 10% to validation, and the rest to test. Validation does not update training history "
              "for these diagnostics. Boundary dates are descriptive, not frozen evaluation cutoffs.", "",
              "| Measure | Value |", "|---|---:|",
              f"| Training / validation / test interactions | {n(global_time['training_interactions'])} / {n(global_time['validation']['interactions'])} / {n(global_time['test']['interactions'])} |",
              f"| User training minimum | {n(global_time['user_training_minimum'])} |",
              f"| Users without training history | {n(global_time['users_without_training_history'])} |",
              f"| Users below three training interactions | {n(global_time['users_below_three_training_interactions'])} |",
              f"| Product training minimum | {n(global_time['product_training_minimum'])} |",
              f"| Products without training history | {n(global_time['products_without_training_history'])} |",
              f"| Products below five training interactions | {n(global_time['products_below_five_training_interactions'])} |"]
    for name in ("training", "validation"):
        boundary = global_time[f"{name}_boundary_timestamp_ms"]
        lines.append(f"| {name.title()} boundary (UTC) | {datetime.fromtimestamp(boundary/1000, timezone.utc).isoformat()} |")
    lines += ["", "| Holdout | Interactions | Unseen-user rows | Unseen-product rows | Either unseen | Unique unseen users | Unique unseen products |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for name in ("validation", "test"):
        lines.append(f"| {name} | " + " | ".join(n(global_time[name][key]) for key in (
            "interactions", "interactions_with_unseen_user", "interactions_with_unseen_product",
            "interactions_with_either_unseen", "unique_unseen_users", "unique_unseen_products")) + " |")
    lines += ["", "## Selection bias and evaluation limitations", "",
              "Hash-based user inclusion is deterministic and rating-independent, but the final sample is not a random "
              "sample of interactions: all retained histories are clustered by user, then graph pruning favors users and "
              "products with sufficient activity and connectivity. Long-tail, new-user, and new-product cases are "
              "underrepresented. Sampling-fraction adjustment uses graph size, not model scores or held-out ratings.", "",
              "Core selection examines the full interaction graph, including events that a future chronological benchmark "
              "might hold out. It therefore uses future participation information. This subset is suitable for a "
              "retrospective intermediate-level prototype; it is not an unbiased simulation of future deployment. A "
              "deployment-oriented benchmark should define cutoffs and eligibility using only data available at the time, "
              "then separately report warm-start and cold-start results. Filtering unsupported holdout users/products "
              "would inflate apparent coverage; report both excluded counts and overall coverage if such a policy is chosen.", "",
              "A full-data 5-core does not guarantee adequate training degrees after any split. Do not re-core training "
              "and discard difficult held-out cases without recording the resulting population change. Temporal diagnostics "
              "do not assess recommendation accuracy. No metadata was downloaded and product-category provenance "
              "remains unverified beyond the supplied file and schema.", "",
              "## Resources, reproducibility, and cleanup", "",
              f"- Python {resources['python']}; SQLite {resources['sqlite']}; standard library only.",
              f"- Runtime: {resources['elapsed_seconds']:.2f} seconds.",
              f"- Peak working set: {resources.get('peak_working_set_bytes', 0)/MIB:.2f} MiB.",
              f"- Free disk before: {resources['disk_before']['scratch']['free']/MIB:,.2f} MiB. Conservative reservation: {resources['conservative_disk_reservation_bytes']/MIB:,.2f} MiB.",
              f"- Retained scratch: {resources['scratch_retained_bytes']/MIB:.2f} MiB at `{resources['scratch_directory']}`.",
              f"- Output CSV size: {s['bytes']/MIB:.2f} MiB; manifest size is additional.",
              "- Streaming uses 10,000-row batches plus a retained-user membership set. Main and attached SQLite page "
              "cache budgets are 32 MiB each; these are not process memory limits. SQLite sorting is disk-backed in the "
              "dedicated scratch directory. Retained disk sizes exclude transient sort files and rollback journals, "
              "so they are not exact peak disk measurements.", "",
              "Rerun from the project root, with a new report filename:", "", "```powershell",
              f'python3.14 -I -B scripts/create_subset.py --dataset "{r["input"]["path"]}" --inspection-summary "{Path(r["aggregation"]["path"]).with_name("summary.json")}" --aggregation "{r["aggregation"]["path"]}" --report docs/subset_report_rerun.md',
              "python3.14 -I -B -m unittest discover -s tests -p test_create_subset.py -v", "```", "",
              "Every run creates new unique output and scratch directories and refuses to overwrite an existing report. "
              "Reproducibility is defined by identical input bytes, script version, seed, exact fraction-selection policy, "
              "and subset checksum, not by randomly generated directory names or runtime measurements. A manifest with "
              "`status: complete` is written only after export, graph, and input-integrity checks pass.", "",
              "The inspection aggregation is reused read-only and is never removed by this script. Scratch is retained "
              "for review and contains source identifiers. After review, cleanup may remove only the exact owned scratch "
              "directory above, after resolving its absolute path and verifying it is under the intended temporary parent "
              "and outside the workspace. Do not delete the temporary parent or use wildcards. Preserve the subset CSV "
              "and manifest for subsequent approved phases. Synthetic test directories are separate, verified descendants "
              "of the OS temporary directory and are cleaned by the tests themselves.", "",
              "No final evaluation split, model, frontend, backend, package installation, metadata download, or Git "
              "initialization/configuration/commit/push is part of this phase. Stop for review before later phases.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--inspection-summary", required=True, type=Path)
    parser.add_argument("--aggregation", required=True, type=Path)
    parser.add_argument("--output-parent", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "local")
    parser.add_argument("--scratch-parent", type=Path, default=Path(tempfile.gettempdir()))
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--target-min", type=int, default=100_000)
    parser.add_argument("--target-max", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.seed != 42:
        parser.error("This approved subset specification fixes the seed at 42")
    if not 1 <= args.target_min <= args.target_max:
        parser.error("Expected 1 <= target-min <= target-max")
    # Only make the explicitly ignored local output parent; all run files remain new.
    project = Path(__file__).resolve().parents[1]
    output = args.output_parent.resolve()
    if output == project / "data" / "local" and "/data/local/" in (project / ".gitignore").read_text(encoding="utf-8").splitlines():
        output.mkdir(parents=True, exist_ok=True)
    try:
        run(args.dataset, args.inspection_summary, args.aggregation, output,
            args.scratch_parent, args.report, args.target_min, args.target_max, seed=args.seed)
    except Exception as error:
        # Never include data-bearing exception details or identifiers in logs.
        emit("failed", error_type=type(error).__name__,
             frames=[{"file": Path(frame.filename).name, "function": frame.name, "line": frame.lineno}
                     for frame in traceback.extract_tb(error.__traceback__)])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
