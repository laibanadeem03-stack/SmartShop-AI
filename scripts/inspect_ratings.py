"""Read-only ratings inspection using only Python's standard library.

The input is never written. Each run creates a fresh, disposable SQLite directory
outside the project. Reports and scratch files are created exclusively, never
overwritten. Scratch files contain identifiers; the Markdown report does not.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import sys
import tempfile
import time


MIB = 1024 ** 2
NULL_MARKERS = {"null", "none", "na", "n/a", "nan"}
ALIASES = {
    "user": {"user_id", "reviewerid", "userid"},
    "product": {"parent_asin", "asin", "product_id", "productid"},
    "rating": {"rating", "overall"},
    "timestamp": {"timestamp", "unixreviewtime"},
}


def missing(value):
    return not value.strip() or value.strip().lower() in NULL_MARKERS


def process_memory():
    """Return process working set and lifetime peak; no external dependencies."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in (
                    "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
                )
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD,
        ]
        c = Counters()
        c.cb = ctypes.sizeof(c)
        if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(c), c.cb):
            return {"working_set_bytes": c.WorkingSetSize,
                    "peak_working_set_bytes": c.PeakWorkingSetSize}
        return {"measurement_unavailable": True}
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return {"peak_working_set_bytes": peak if sys.platform == "darwin" else peak * 1024}
    except ImportError:
        return {"measurement_unavailable": True}


def distribution(connection, table, column):
    """Exact degree statistics; consume the frequency histogram as a cursor."""
    n, total, lo, hi = connection.execute(
        f"SELECT COUNT(*), COALESCE(SUM({column}),0), MIN({column}), MAX({column}) FROM {table}"
    ).fetchone()
    below = connection.execute(
        f"SELECT COUNT(*) FROM {table} WHERE {column}<5"
    ).fetchone()[0]
    if not n:
        return {"entities": 0, "interactions": 0, "minimum": None, "mean": None,
                "median": None, "p90": None, "p95": None, "p99": None,
                "maximum": None, "below_five": 0, "at_least_five": 0}
    ranks = {"median_low": (n + 1) // 2, "median_high": n // 2 + 1,
             **{f"p{p}": math.ceil(n * p / 100) for p in (90, 95, 99)}}
    values = {}
    cumulative = 0
    for degree, frequency in connection.execute(
        f"SELECT {column}, COUNT(*) FROM {table} GROUP BY {column} ORDER BY {column}"
    ):
        cumulative += frequency
        for key, rank in ranks.items():
            if key not in values and cumulative >= rank:
                values[key] = degree
    return {"entities": n, "interactions": total, "minimum": lo, "mean": total / n,
            "median": (values["median_low"] + values["median_high"]) / 2,
            **{key: values[key] for key in ("p90", "p95", "p99")},
            "maximum": hi, "below_five": below, "at_least_five": n - below}


def duplicate_summary(connection, column):
    pairs, repeated, excess, maximum = connection.execute(
        f"SELECT COUNT(*), COALESCE(SUM({column}>1),0), "
        f"COALESCE(SUM({column}-1),0), COALESCE(MAX({column}),0) "
        f"FROM pairs WHERE {column}>0"
    ).fetchone()
    return {"distinct_pairs": pairs, "repeated_pairs": repeated,
            "excess_interactions": excess, "maximum_pair_multiplicity": maximum}


def scratch_size(directory):
    return sum(p.stat().st_size for p in directory.iterdir() if p.is_file())


def iso_epoch(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def inspect(dataset, scratch, batch_size):
    started = time.perf_counter()
    before = dataset.stat()
    digest = hashlib.sha256()
    with dataset.open("rb") as source:
        for block in iter(lambda: source.read(MIB), b""):
            digest.update(block)

    # SQLite temporary sorting files are isolated beside the newly created DB.
    os.environ["SQLITE_TMPDIR"] = str(scratch)
    connection = sqlite3.connect(scratch / "aggregation.sqlite3")
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA synchronous=OFF")
    connection.execute("PRAGMA cache_size=-32768")
    connection.execute("PRAGMA temp_store=FILE")
    connection.execute("PRAGMA mmap_size=0")
    escaped = str(scratch).replace("'", "''")
    connection.execute(f"PRAGMA temp_store_directory='{escaped}'")
    connection.executescript("""
        CREATE TABLE raw_users (id TEXT PRIMARY KEY, n INTEGER NOT NULL) WITHOUT ROWID;
        CREATE TABLE raw_products (id TEXT PRIMARY KEY, n INTEGER NOT NULL) WITHOUT ROWID;
        CREATE TABLE pairs (
            user_id TEXT NOT NULL, product_id TEXT NOT NULL,
            raw_n INTEGER NOT NULL, valid_n INTEGER NOT NULL,
            PRIMARY KEY (user_id, product_id)
        ) WITHOUT ROWID;
    """)

    raw_users, raw_products, pairs = Counter(), Counter(), {}
    rating_raw, rating_valid = Counter(), Counter()
    totals = Counter()
    timestamp_units = Counter()
    time_min = time_max = None
    memory_sample = Counter()
    largest_batch_keys = 0
    boundary_disk_peak = 0

    def flush():
        nonlocal largest_batch_keys, boundary_disk_peak
        largest_batch_keys = max(largest_batch_keys, len(pairs))
        with connection:
            for table, counts in (("raw_users", raw_users), ("raw_products", raw_products)):
                connection.executemany(
                    f"INSERT INTO {table} VALUES (?,?) "
                    "ON CONFLICT(id) DO UPDATE SET n=n+excluded.n", counts.items()
                )
            connection.executemany(
                "INSERT INTO pairs VALUES (?,?,?,?) "
                "ON CONFLICT(user_id,product_id) DO UPDATE SET "
                "raw_n=raw_n+excluded.raw_n, valid_n=valid_n+excluded.valid_n",
                ((u, p, counts[0], counts[1]) for (u, p), counts in pairs.items()),
            )
        raw_users.clear()
        raw_products.clear()
        pairs.clear()
        boundary_disk_peak = max(boundary_disk_peak, scratch_size(scratch))

    try:
        with dataset.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source, strict=True)
            header = next(reader)
            normalized = [s.strip().lower() for s in header]
            indexes = {}
            for role, aliases in ALIASES.items():
                matches = [i for i, name in enumerate(normalized) if name in aliases]
                if len(matches) != 1:
                    raise ValueError(f"Expected exactly one recognized {role} column")
                indexes[role] = matches[0]
            if len(header) != 4 or len(set(normalized)) != 4:
                raise ValueError("This inspector expects exactly four distinct recognized columns")
            blanks = [0] * len(header)
            markers = [0] * len(header)
            for row in reader:
                totals["records"] += 1
                for i in range(len(header)):
                    value = row[i].strip() if i < len(row) else ""
                    blanks[i] += not value
                    markers[i] += bool(value) and value.lower() in NULL_MARKERS
                if len(row) != len(header):
                    totals["malformed_width"] += 1
                    continue
                totals["well_formed"] += 1
                user, product, rating_text, timestamp = (
                    row[indexes[k]].strip() for k in ("user", "product", "rating", "timestamp")
                )
                has_user, has_product = not missing(user), not missing(product)
                totals["missing_user"] += not has_user
                totals["missing_product"] += not has_product
                if has_user:
                    raw_users[user] += 1
                if has_product:
                    raw_products[product] += 1
                if missing(rating_text):
                    totals["missing_rating"] += 1
                    rating = None
                else:
                    try:
                        rating = float(rating_text)
                        if not math.isfinite(rating):
                            raise ValueError
                    except ValueError:
                        rating = None
                        totals["nonnumeric_or_nonfinite_rating"] += 1
                if rating is not None:
                    rating_raw[rating] += 1
                in_range = rating is not None and 1 <= rating <= 5
                if rating is not None and not in_range:
                    totals["rating_outside_1_to_5"] += 1
                if in_range and not rating.is_integer():
                    totals["fractional_ratings"] += 1
                valid = has_user and has_product and in_range
                totals["valid"] += valid
                if valid:
                    rating_valid[rating] += 1
                if has_user and has_product:
                    counts = pairs.setdefault((user, product), [0, 0])
                    counts[0] += 1
                    counts[1] += valid
                if missing(timestamp):
                    totals["missing_timestamp"] += 1
                else:
                    try:
                        numeric_time = int(timestamp)
                        unit = "milliseconds" if abs(numeric_time) >= 100_000_000_000 else "seconds"
                        seconds = numeric_time / 1000 if unit == "milliseconds" else numeric_time
                        iso_epoch(seconds)  # Check platform datetime range.
                        timestamp_units[unit] += 1
                        time_min = seconds if time_min is None else min(time_min, seconds)
                        time_max = seconds if time_max is None else max(time_max, seconds)
                    except (ValueError, OverflowError, OSError):
                        totals["invalid_timestamp"] += 1
                if memory_sample["records"] < 10_000:
                    memory_sample["records"] += 1
                    memory_sample["python_row_bytes"] += (
                        8 + sys.getsizeof(row) + sum(sys.getsizeof(v) for v in row)
                    )
                    memory_sample["dataframe_object_bytes"] += (
                        sys.getsizeof(user) + sys.getsizeof(product) + 32
                    )
                if totals["well_formed"] % batch_size == 0:
                    flush()
                if totals["records"] % 250_000 == 0:
                    print(json.dumps({"event": "progress", "records": totals["records"],
                                      "elapsed_seconds": round(time.perf_counter() - started, 1),
                                      "scratch_mib": round(scratch_size(scratch) / MIB, 1)}), flush=True)
            flush()

        connection.executescript("""
            CREATE TABLE valid_users AS
                SELECT user_id AS id, SUM(valid_n) AS n, COUNT(*) AS degree
                FROM pairs WHERE valid_n>0 GROUP BY user_id;
            CREATE TABLE valid_products AS
                SELECT product_id AS id, SUM(valid_n) AS n, COUNT(*) AS degree
                FROM pairs WHERE valid_n>0 GROUP BY product_id;
        """)
        stages = {}
        raw_duplicates = duplicate_summary(connection, "raw_n")
        valid_duplicates = duplicate_summary(connection, "valid_n")
        for stage, user_table, product_table, degree_column, interactions in (
            ("raw", "raw_users", "raw_products", "n", totals["records"]),
            ("valid", "valid_users", "valid_products", "n", totals["valid"]),
            ("deduplicated", "valid_users", "valid_products", "degree", valid_duplicates["distinct_pairs"]),
        ):
            users = distribution(connection, user_table, degree_column)
            products = distribution(connection, product_table, degree_column)
            stages[stage] = {"interactions": interactions, "users": users, "products": products,
                             "five_core": bool(users["entities"] and products["entities"]
                                               and users["below_five"] == 0
                                               and products["below_five"] == 0)}
        boundary_disk_peak = max(boundary_disk_peak, scratch_size(scratch))
        pages = connection.execute("PRAGMA page_count").fetchone()[0]
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
    finally:
        connection.close()

    after = dataset.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError("Source size or modification time changed during inspection; discard results")
    unique_pairs = valid_duplicates["distinct_pairs"]
    users_n = stages["deduplicated"]["users"]["entities"]
    products_n = stages["deduplicated"]["products"]["entities"]
    sample_n = memory_sample["records"]
    result = {
        "inspection_time_utc": datetime.now(timezone.utc).isoformat(),
        "source": {"path": str(dataset), "bytes": before.st_size,
                   "modified_utc": datetime.fromtimestamp(before.st_mtime, timezone.utc).isoformat(),
                   "sha256": digest.hexdigest(), "size_and_mtime_unchanged": True},
        "runtime": {"python": platform.python_version(), "executable": sys.executable,
                    "sqlite": sqlite3.sqlite_version, "elapsed_seconds": time.perf_counter() - started},
        "schema": {"header_present": True, "encoding": "utf-8-sig (accepts plain UTF-8)",
                   "delimiter": ",", "columns": [
                       {"name": name, "blank_or_absent": blanks[i], "null_markers": markers[i],
                        "missing_total": blanks[i] + markers[i]} for i, name in enumerate(header)]},
        "totals": dict(totals), "stages": stages,
        "duplicates": {"raw": raw_duplicates, "valid": valid_duplicates},
        "ratings": {"raw_numeric": dict(sorted(rating_raw.items())),
                    "valid": dict(sorted(rating_valid.items()))},
        "timestamps": {"units": dict(timestamp_units),
                       "minimum_utc": iso_epoch(time_min) if time_min is not None else None,
                       "maximum_utc": iso_epoch(time_max) if time_max is not None else None},
        "memory": {**process_memory(), "sqlite_cache_budget_bytes": 32 * MIB,
                   "batch_records": batch_size, "largest_batch_pair_keys": largest_batch_keys,
                   "sample_records": sample_n,
                   "python_rows_estimate_bytes": (round(memory_sample["python_row_bytes"] / sample_n * totals["records"]) if sample_n else 0),
                   "object_dataframe_estimate_bytes": (round(memory_sample["dataframe_object_bytes"] / sample_n * totals["records"]) if sample_n else 0),
                   "csr_float32_int32_bytes": 8 * unique_pairs + 4 * (users_n + 1),
                   "coo_float32_int32_bytes": 12 * unique_pairs,
                   "dense_float32_bytes": 4 * users_n * products_n},
        "scratch": {"directory": str(scratch), "database_bytes": pages * page_size,
                    "observed_boundary_disk_peak_bytes": boundary_disk_peak,
                    "retained_files_bytes_before_summary": scratch_size(scratch)},
    }
    assert stages["valid"]["users"]["interactions"] == totals["valid"]
    assert stages["valid"]["products"]["interactions"] == totals["valid"]
    assert stages["deduplicated"]["users"]["interactions"] == unique_pairs
    assert stages["deduplicated"]["products"]["interactions"] == unique_pairs
    assert unique_pairs + valid_duplicates["excess_interactions"] == totals["valid"]
    return result


def number(value):
    if value is None:
        return "—"
    return f"{value:,.2f}" if isinstance(value, float) else f"{value:,}"


def report_markdown(r):
    graph = r["stages"]["deduplicated"]
    dedup_observation = (
        "The present dataset has no repeated valid pairs or missing timestamps, so that policy would not discard any valid rows."
        if not r["duplicates"]["valid"]["excess_interactions"] and not r["totals"].get("missing_timestamp", 0)
        else "Any surviving rating selection remains a later preprocessing step."
    )
    if graph["five_core"]:
        core_guidance = (
            f"The full deduplicated graph already satisfies the distinct-neighbor 5-core property: "
            f"{number(graph['interactions'])} edges, {number(graph['users']['entities'])} users, and "
            f"{number(graph['products']['entities'])} products. Initial five-neighbor pruning would remove "
            "nothing. Sampling can break this property, so the sampled graph still needs iterative pruning."
        )
    else:
        core_guidance = (
            "Start by iteratively pruning the full graph to at least five distinct neighbors on both sides; "
            "a single-pass filter does not ensure this property. The size of the surviving core is not yet measured."
        )
    lines = [
        "# SmartShop-AI dataset inspection", "",
        f"Inspection completed at {r['inspection_time_utc']} (UTC).", "",
        "## Source and reproducibility", "",
        f"- Source: `{r['source']['path']}`; retained outside this project.",
        f"- Size: {number(r['source']['bytes'])} bytes ({r['source']['bytes']/MIB:.2f} MiB).",
        f"- SHA-256: `{r['source']['sha256']}`.",
        f"- Source modification time: {r['source']['modified_utc']}.",
        "- Source was opened only for reading. Size and modification time were unchanged at completion.",
        f"- Python {r['runtime']['python']}; SQLite {r['runtime']['sqlite']}.",
        f"- Interpreter: `{r['runtime']['executable']}`.",
        f"- Runtime: {r['runtime']['elapsed_seconds']:.2f} seconds, including the checksum pass.",
        "- Workspace was empty before this task; no existing project configuration or AGENTS.md was present.",
        "- The `python` and `py` WindowsApps aliases failed to launch; `python3.14` worked.", "",
        "Re-run from the project directory with an unused output filename:", "",
        "```powershell",
        'python3.14 -I -B scripts/inspect_ratings.py --dataset "C:\\Users\\ai.development\\Downloads\\Cell_Phones_and_Accessories.csv" --report docs/dataset_report_rerun.md',
        "```", "",
        "## Method and definitions", "",
        "The standard-library CSV reader streams UTF-8 records; a separate bounded binary pass calculates SHA-256. "
        "SQLite aggregates exact counts in batches. No Pandas, NumPy, package installation, network access, model training, "
        "or subset export is involved. IDs are trimmed and compared case-sensitively as strings.", "",
        "- **Raw:** all parsed data records, excluding the header. Raw entity/degree and pair aggregates use structurally "
        "correct rows and available nonmissing IDs, irrespective of rating validity. Missing counterpart IDs can make raw "
        "user and product degree totals differ from raw record totals.",
        "- **Valid:** structurally correct rows with both IDs present and a finite numeric rating in [1, 5]. "
        "Timestamp validity is reported separately and does not exclude an otherwise usable rating.",
        "- **Deduplicated:** one edge per valid user-product pair. This inspection counts those edges without selecting "
        "a surviving rating, producing a subset, or assigning a deduplicated rating distribution.",
        "- Missing values include whitespace-only/absent cells and case-insensitive null, none, NA, N/A, and NaN markers. "
        "Row shape, missing-value, and invalid-value counts may overlap.",
        "- Percentiles use nearest rank; the median averages the middle two values when necessary.", "",
        "## Schema and data quality", "",
        "The CSV has a header and four comma-separated columns. No title, description, category, price, or review text column is present.", "",
        "| Column | Blank/absent | Null markers | Total missing |",
        "|---|---:|---:|---:|",
    ]
    for c in r["schema"]["columns"]:
        lines.append(f"| {c['name']} | {number(c['blank_or_absent'])} | {number(c['null_markers'])} | {number(c['missing_total'])} |")
    lines += ["", "| Quality check | Count |", "|---|---:|"]
    for key in ("records", "well_formed", "malformed_width", "valid", "missing_user", "missing_product",
                "missing_rating", "nonnumeric_or_nonfinite_rating", "rating_outside_1_to_5",
                "fractional_ratings", "missing_timestamp", "invalid_timestamp"):
        lines.append(f"| {key} | {number(r['totals'].get(key, 0))} |")
    lines += ["", f"Timestamp unit counts: {json.dumps(r['timestamps']['units'], sort_keys=True)}.",
              f"Timestamp range (UTC): {r['timestamps']['minimum_utc']} to {r['timestamps']['maximum_utc']}.",
              "Epoch integers with absolute magnitude at least 100,000,000,000 are interpreted as milliseconds; "
              "smaller integers as seconds. This is a heuristic, not metadata supplied by the CSV.", "",
              "## Interaction counts and 5-core verification", "",
              "| Stage | Interactions | Unique users | Unique products | Users below 5 | Products below 5 | 5-core holds |",
              "|---|---:|---:|---:|---:|---:|---|"]
    for stage, s in r["stages"].items():
        lines.append(f"| {stage} | {number(s['interactions'])} | {number(s['users']['entities'])} | "
                     f"{number(s['products']['entities'])} | {number(s['users']['below_five'])} | "
                     f"{number(s['products']['below_five'])} | {'Yes' if s['five_core'] else 'No'} |")
    lines += ["", "Raw and valid 5-core checks count rows, including repeat pairs. The deduplicated check "
              "requires five distinct products per user and five distinct users per product. No iterative core "
              "pruning was performed; these checks describe the complete supplied graph.", "",
              "## Interactions per user and product", "",
              "| Stage | Entity | Min | Median | Mean | P90 | P95 | P99 | Max | At least 5 |",
              "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for stage, s in r["stages"].items():
        for entity in ("users", "products"):
            d = s[entity]
            lines.append(f"| {stage} | {entity} | " + " | ".join(
                number(d[key]) for key in ("minimum", "median", "mean", "p90", "p95", "p99", "maximum", "at_least_five")
            ) + " |")
    lines += ["", "## Rating distribution", "",
              "| Rating | Raw numeric rows | Valid rows | Share of valid rows |",
              "|---|---:|---:|---:|"]
    valid_total = r["totals"].get("valid", 0)
    for rating, count in r["ratings"]["raw_numeric"].items():
        valid_count = r["ratings"]["valid"].get(rating, 0)
        pct = f"{valid_count / valid_total:.2%}" if valid_total else "—"
        lines.append(f"| {rating:g} | {number(count)} | {number(valid_count)} | {pct} |")
    lines += ["", "## Duplicate user-product interactions", "",
              "| Stage | Distinct pairs | Pairs occurring more than once | Excess rows | Maximum multiplicity |",
              "|---|---:|---:|---:|---:|"]
    for stage, d in r["duplicates"].items():
        lines.append(f"| {stage} | " + " | ".join(number(d[key]) for key in (
            "distinct_pairs", "repeated_pairs", "excess_interactions", "maximum_pair_multiplicity")) + " |")
    lines += ["", "Deduplicated edges have zero repeated pairs by definition. This checks repeated user-product "
              "interactions, not byte-identical source records or rating conflicts.", "",
              "## Memory and disk", "", "| Measurement or estimate | MiB |", "|---|---:|"]
    mem = r["memory"]
    for key, label in (
        ("peak_working_set_bytes", "Observed process lifetime peak working set"),
        ("working_set_bytes", "Working set after aggregation"),
        ("sqlite_cache_budget_bytes", "Configured SQLite cache budget (not a process memory limit)"),
        ("python_rows_estimate_bytes", "Estimated full list of Python string rows"),
        ("object_dataframe_estimate_bytes", "Estimated object-ID dataframe with float64 rating/int64 timestamp"),
        ("csr_float32_int32_bytes", "Deduplicated CSR payload: float32 values/int32 indexes"),
        ("coo_float32_int32_bytes", "Deduplicated COO payload: float32 values/int32 coordinates"),
        ("dense_float32_bytes", "Hypothetical dense float32 user-product matrix"),
    ):
        if key in mem:
            lines.append(f"| {label} | {mem[key]/MIB:,.2f} |")
    lines += [f"| Retained SQLite database | {r['scratch']['database_bytes']/MIB:,.2f} |",
              f"| Largest scratch size observed at batch/phase boundaries | {r['scratch']['observed_boundary_disk_peak_bytes']/MIB:,.2f} |", "",
              f"Batch size: {number(mem['batch_records'])} records; maximum distinct pairs in a batch: "
              f"{number(mem['largest_batch_pair_keys'])}. In-memory estimates use the first {number(mem['sample_records'])} "
              "well-formed rows and CPython object sizes. They are planning estimates, not measured Pandas allocations. "
              "The dataframe estimate assumes independently allocated ID strings, two object pointers, and two 8-byte numeric columns. "
              "Parser temporaries, indexes, allocator overhead, model workspaces, and string-interning/categorical savings are excluded. "
              "Sparse estimates exclude ID maps and model overhead. Never build the dense matrix.", "",
              "SQLite sorting uses disk-backed temporary storage in the dedicated scratch directory. Boundary disk measurements "
              "exclude short-lived internal sort files already removed by SQLite; they are not an exact peak disk measurement. "
              "Allow several times the source size in free scratch space for reruns. Journal and synchronous writes are disabled "
              "only for the disposable scratch database; interrupted runs are not resumable.", "",
              "## Recommended subset (proposal only)", "",
              "Use all valid interactions to form the deduplicated graph before sampling. Deduplicate by the latest valid "
              "timestamp, with source record number as a deterministic tie-breaker. Prefer valid timestamps over missing "
              "ones; if all timestamps for a pair are missing, choose the last source record. "
              + dedup_observation, "",
              core_guidance, "",
              "Target roughly 100,000–300,000 deduplicated interactions initially, subject to the surviving core. Select users "
              "by a fixed-seed SHA-256 hash threshold (never Python's randomized hash), retain their interactions, and repeat "
              "the five-neighbor pruning to convergence. Test a predeclared sequence of increasing sampling fractions, "
              "starting at 1/16 and doubling through the complete core, if the result is too small or collapses. Use seed "
              "42: hash the UTF-8 bytes of `42`, a zero byte, and the normalized user ID; interpret the SHA-256 digest "
              "as an unsigned big-endian integer and retain it below `fraction * 2**256` using exact integer arithmetic. Record "
              "every attempted fraction and output graph statistics. The target is a sizing goal, not a guaranteed feasible size; "
              "prefer a viable larger core over an arbitrary row cap. No subset was created in this task.", "",
              "Freeze the subset specification with the source checksum, schema, normalization rules, deduplication order, "
              "seed, sampling fraction, pruning threshold, algorithm version, and final counts. Keep outputs outside Git. "
              "Use the deduplicated graph statistics above to judge activity; raw row counts can overstate usable history.", "",
              "For evaluation, reserve one latest interaction for validation and one for test for eligible users, keeping "
              "at least three training interactions for users with five neighbors. Fit popularity counts, similarity indexes, "
              "and hybrid weights only using their designated training/validation data. Report products absent from training "
              "as cold-start cases. Global core selection uses the full graph, so label this a retrospective benchmark; it "
              "does not by itself establish future deployment performance.", "",
              "## Metadata matching", "",
              "Join future metadata on `parent_asin`, preserving string values and identifier granularity. A child/variant "
              "ASIN is not automatically equivalent to a parent ASIN. Confirm the matching metadata release and category "
              "from its documentation before acquiring anything: the local filename alone does not prove provenance. "
              "Enforce one metadata row per parent key or explicitly consolidate duplicates before joining. Measure "
              "coverage of unique products and interactions, check unmatched keys, and prevent joins from multiplying rows. "
              "Titles, descriptions, and categories may support TF-IDF later; they are absent from this CSV. Metadata "
              "availability, licensing, identifier compatibility, and completeness have not been verified. Nothing was downloaded.", "",
              "## Scratch isolation and cleanup", "",
              f"This run owns the newly created directory `{r['scratch']['directory']}`. It is outside the workspace and "
              "contains `aggregation.sqlite3` (including identifiers) and an aggregate-only `summary.json`. No pre-existing "
              "scratch file was reused or overwritten. Treat the database as local data, never as a repository artifact.", "",
              "Scratch files are retained for review; this task did not delete them. After review, cleanup may remove only "
              "this exact directory after resolving its absolute path, confirming it is under the intended temporary "
              "parent and outside the workspace, and checking its contents. Do not use wildcards or delete the temporary "
              "parent. Cleanup is ordinary file deletion, not secure erasure. If interrupted, the script prints its owned "
              "scratch path so the same checks can be applied to that incomplete run.", "",
              "## Limitations", "",
              "No provenance or category membership verification, metadata inspection, row-level duplicate conflict audit, "
              "rating-survivor selection, iterative core extraction, subset feasibility experiment, model fitting, or "
              "recommendation evaluation was performed. Identifier semantics are inferred from the provided column names. "
              "Missingness counts detect the documented markers rather than every possible sentinel. Memory estimates "
              "are sample-dependent. The source checksum plus unchanged size/mtime supports reproducibility but does not "
              "provide a transactional snapshot against concurrent external modification. Reports contain aggregate statistics "
              "and column names only, without raw records or user/product ID values.", "",
              "See `docs/project_plan.md` for the proposed development phases. All later implementation and data acquisition "
              "remain subject to review; this task ends after inspection and planning.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--scratch-parent", type=Path, default=Path(tempfile.gettempdir()))
    parser.add_argument("--batch-size", type=int, default=10_000)
    args = parser.parse_args()
    dataset, report = args.dataset.resolve(strict=True), args.report.resolve()
    project = Path(__file__).resolve().parents[1]
    parent = args.scratch_parent.resolve(strict=True)
    if not dataset.is_file():
        parser.error("dataset must be a regular file")
    if report.exists() or report == dataset:
        parser.error("report must be a new path; refusing to overwrite anything")
    if parent.is_relative_to(project):
        parser.error("scratch storage must be outside the project")
    # Also reject any ancestor Git working tree without reading unrelated projects.
    if any((p / ".git").exists() for p in (parent, *parent.parents)):
        parser.error("scratch storage must be outside Git working trees")
    if not 1 <= args.batch_size <= 100_000:
        parser.error("batch size must be between 1 and 100,000")
    if not report.parent.is_dir():
        parser.error("report parent directory must already exist")
    scratch = Path(tempfile.mkdtemp(prefix="smartshop-inspection-", dir=parent))
    print(json.dumps({"event": "scratch_created", "directory": str(scratch)}), flush=True)
    try:
        result = inspect(dataset, scratch, args.batch_size)
        with (scratch / "summary.json").open("x", encoding="utf-8") as output:
            json.dump(result, output, indent=2)
            output.write("\n")
        with report.open("x", encoding="utf-8", newline="\n") as output:
            output.write(report_markdown(result))
    except Exception as error:
        # Avoid echoing CSV contents or identifiers through exception messages.
        print(json.dumps({"event": "failed", "error_type": type(error).__name__,
                          "scratch_directory": str(scratch), "report_may_be_incomplete": report.exists()}),
              file=sys.stderr, flush=True)
        return 1
    print(json.dumps({"event": "complete", "records": result["totals"]["records"],
                      "report": str(report), "scratch_directory": str(scratch)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
