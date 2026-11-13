"""Synthetic tests only: no real dataset or dataset identifiers are accessed."""

from contextlib import redirect_stdout
from fractions import Fraction
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import csv


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "create_subset.py"
SPEC = importlib.util.spec_from_file_location("create_subset", SCRIPT)
subset = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subset)


class SamplingTests(unittest.TestCase):
    def test_console_permission_error_does_not_abort_processing(self):
        class ClosedConsole:
            def write(self, value):
                raise PermissionError("synthetic closed output pipe")

            def flush(self):
                pass

        previous = subset.PROGRESS_AVAILABLE
        try:
            subset.PROGRESS_AVAILABLE = True
            with redirect_stdout(ClosedConsole()):
                subset.emit("synthetic-progress")
            self.assertFalse(subset.PROGRESS_AVAILABLE)
        finally:
            subset.PROGRESS_AVAILABLE = previous

    def test_fixed_hash_and_exact_threshold(self):
        user = "user-0001"  # synthetic, never a real dataset ID
        golden = "1b2a11652fbb4a93fcdd80f64cc93ee0c80ffa802e476a759876c9d86b74cd66"
        self.assertEqual(subset.user_hash(user), golden)
        boundary = int(golden, 16)
        self.assertFalse(subset.sampled(user, Fraction(boundary, 1 << 256)))
        self.assertTrue(subset.sampled(user, Fraction(boundary + 1, 1 << 256)))
        self.assertFalse(subset.sampled(user, 0))
        self.assertTrue(subset.sampled(user, 1))
        self.assertNotEqual(subset.user_hash(user, 42), subset.user_hash(user, 43))
        with self.assertRaises(ValueError):
            subset.sampled(user, Fraction(17, 16))

    def test_order_independence_and_nested_samples(self):
        users = [f"synthetic-user-{i:04}" for i in range(500)]
        forward = {u for u in users if subset.sampled(u, Fraction(1, 4))}
        backward = {u for u in reversed(users) if subset.sampled(u, Fraction(1, 4))}
        larger = {u for u in users if subset.sampled(u, Fraction(1, 2))}
        self.assertEqual(forward, backward)
        self.assertTrue(forward < larger < set(users))

    def test_reproducible_across_python_hash_seeds(self):
        code = (
            "import importlib.util; "
            f"s=importlib.util.spec_from_file_location('subsetter',{str(SCRIPT)!r}); "
            "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
            "print(m.user_hash('synthetic-reproducibility-user'))"
        )
        results = []
        for seed in ("1", "98765"):
            environment = dict(os.environ, PYTHONHASHSEED=seed)
            run = subprocess.run([sys.executable, "-B", "-c", code], env=environment,
                                 capture_output=True, text=True, check=True)
            results.append(run.stdout.strip())
        self.assertEqual(results[0], results[1])

    def test_fraction_refinement_and_nonforced_target(self):
        def evaluate(fraction):
            return {"fraction": str(fraction), "after_pruning": {"interactions": int(fraction * 1_000_000)}}

        selected, attempts = subset.choose_fraction(evaluate, 100_000, 120_000)
        self.assertEqual(selected["fraction"], "7/64")
        self.assertEqual([a["fraction"] for a in attempts], ["1/16", "1/8", "3/32", "7/64"])

        def jump(fraction):
            return {"fraction": str(fraction), "after_pruning": {"interactions": 0 if fraction < Fraction(1, 2) else 400_000}}

        selected, _ = subset.choose_fraction(jump)
        self.assertEqual(selected["after_pruning"]["interactions"], 400_000)
        self.assertEqual(selected["fraction"], "1/2")

    def test_small_full_graph_fallback_and_complete_collapse(self):
        def small(fraction):
            return {"fraction": str(fraction), "after_pruning": {"interactions": int(fraction * 25)}}

        selected, _ = subset.choose_fraction(small)
        self.assertEqual(selected["fraction"], "1")
        with self.assertRaises(RuntimeError):
            subset.choose_fraction(lambda f: {"fraction": str(f), "after_pruning": {"interactions": 0}})


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.addCleanup(self.connection.close)
        subset.make_edges(self.connection)

    def insert(self, edges):
        self.connection.executemany("INSERT INTO edges VALUES (?,?)", edges)
        self.connection.commit()

    def test_cascading_pruning_needs_multiple_rounds(self):
        core = [(u, p) for u in ("a", "b") for p in ("P", "Q")]
        chain = [("c", "P"), ("c", "R"), ("d", "R"), ("d", "S"), ("e", "S")]
        self.insert(core + chain)
        with redirect_stdout(io.StringIO()):
            rounds = subset.prune_core(self.connection, 2)
        self.assertGreaterEqual(len(rounds), 5)
        self.assertEqual(set(self.connection.execute("SELECT * FROM edges")), set(core))
        self.assertEqual(sum(r["edges_removed"] for r in rounds), len(chain))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(subset.prune_core(self.connection, 2), [])

    def test_five_core_and_duplicate_pairs(self):
        edges = [(f"user-{u}", f"product-{p}") for u in range(5) for p in range(5)]
        self.insert(edges)
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute("INSERT INTO edges VALUES (?,?)", edges[0])
        self.connection.rollback()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(subset.prune_core(self.connection, 5), [])
        stats = subset.graph_statistics(self.connection)
        self.assertTrue(stats["five_core"])
        self.assertEqual(stats["users"]["median"], 5)
        self.assertEqual(stats["products"]["minimum"], 5)
        self.assertEqual(stats["sparsity"], 0)

    def test_collapsed_graph(self):
        self.insert([("user", "product")])
        with redirect_stdout(io.StringIO()):
            subset.prune_core(self.connection, 5)
        stats = subset.graph_statistics(self.connection)
        self.assertEqual(stats["interactions"], 0)
        self.assertFalse(stats["five_core"])
        self.assertIsNone(stats["sparsity"])


class PreservationAndCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="smartshop-subset-tests-")
        self.root = Path(self.temporary.name).resolve()
        self.assertTrue(self.root.is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.assertTrue(self.root.name.startswith("smartshop-subset-tests-"))
        self.addCleanup(self.safe_cleanup)

    def safe_cleanup(self):
        # Validate the exact owned directory before TemporaryDirectory's recursion.
        if not self.root.is_relative_to(Path(tempfile.gettempdir()).resolve()) or not self.root.name.startswith("smartshop-subset-tests-"):
            raise RuntimeError("Refusing unexpected test cleanup path")
        self.temporary.cleanup()

    def make_fixture(self):
        # All values below are synthetic. Cover zero-prefixed, case-sensitive,
        # Unicode IDs and alternate numeric spellings without changing semantics.
        users = ["000001", "CaseUser", "caseuser", "user-α", "user-Z"]
        products = ["0000000001", "CaseProduct", "caseproduct", "product-β", "product-Z"]
        rows = []
        for i, user in enumerate(users):
            for j, product in enumerate(products):
                rating = ["1.0", "2.00", "3", "4.000", "5.0"][j]
                timestamp = str(1_600_000_000_000 + i * 1000 + j)
                if i == 0 and j == 0:
                    timestamp = "0" + timestamp
                rows.append([user, product, rating, timestamp])
        source = self.root / "fixture.csv"
        with source.open("x", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(subset.HEADER)
            writer.writerows(rows)
        aggregation_dir = self.root / "inspected"
        aggregation_dir.mkdir()
        with redirect_stdout(io.StringIO()):
            summary = subset.inspection.inspect(source, aggregation_dir, 3)
        summary_path = aggregation_dir / "summary.json"
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        return source, aggregation_dir / "aggregation.sqlite3", summary_path, rows

    def test_end_to_end_values_and_repeated_run_checksums(self):
        source, aggregation, summary, expected_rows = self.make_fixture()
        original_source, original_aggregation = subset.checksum(source), subset.checksum(aggregation)
        with redirect_stdout(io.StringIO()):
            first = subset.run(source, summary, aggregation, self.root, self.root,
                               self.root / "report1.md", 25, 25)
            second = subset.run(source, summary, aggregation, self.root, self.root,
                                self.root / "report2.md", 25, 25)
        self.assertEqual(first["subset"]["sha256"], second["subset"]["sha256"])
        self.assertNotEqual(first["subset"]["path"], second["subset"]["path"])
        self.assertEqual(first["sampling"]["selected_fraction"], "1")
        self.assertTrue(first["subset"]["five_core"])
        with Path(first["subset"]["path"]).open(encoding="utf-8", newline="") as stream:
            reader = csv.reader(stream)
            self.assertEqual(next(reader), subset.HEADER)
            self.assertEqual(list(reader), expected_rows)
        self.assertEqual(subset.checksum(source), original_source)
        self.assertEqual(subset.checksum(aggregation), original_aggregation)
        self.assertTrue(first["temporal_diagnostics"]["no_split_files_or_row_assignments_saved"])
        # This fixture places one whole user after the global training boundary.
        global_time = first["temporal_diagnostics"]["global_chronological_80_10_10"]
        self.assertEqual(global_time["users_without_training_history"], 1)
        self.assertEqual(global_time["validation"]["interactions_with_unseen_user"], 2)
        self.assertEqual(global_time["test"]["interactions_with_unseen_user"], 3)
        for row in expected_rows:
            self.assertNotIn(row[0], (self.root / "report1.md").read_text(encoding="utf-8"))
            self.assertNotIn(row[1], (self.root / "report1.md").read_text(encoding="utf-8"))
        work = sqlite3.connect(Path(first["resources"]["scratch_directory"]) / "subset_work.sqlite3")
        try:
            columns = [r[1] for r in work.execute("PRAGMA table_info(records)")]
            self.assertNotIn("split", columns)
            self.assertNotIn("recency", columns)
            self.assertNotIn("position", columns)
        finally:
            work.close()

    def test_refuse_existing_report_and_changed_source(self):
        source, aggregation, summary, _ = self.make_fixture()
        report = self.root / "existing.md"
        report.write_text("preserve this file", encoding="utf-8")
        before = set(self.root.iterdir())
        with self.assertRaises(ValueError):
            subset.run(source, summary, aggregation, self.root, self.root, report, 25, 25)
        self.assertEqual(report.read_text(encoding="utf-8"), "preserve this file")
        self.assertEqual(set(self.root.iterdir()), before)
        original = source.read_bytes()
        source.write_bytes(original.replace(b"5.0", b"4.0", 1))
        with self.assertRaises(ValueError):
            subset.validate_input(source, summary, aggregation)

    def test_preservation_refuses_id_normalization(self):
        connection = sqlite3.connect(":memory:")
        try:
            subset.make_edges(connection)
            connection.execute("INSERT INTO edges VALUES ('000001','0000000001')")
            subset.graph_statistics(connection)
            source = self.root / "whitespace.csv"
            with source.open("x", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(subset.HEADER)
                writer.writerow([" 000001", "0000000001", "5.00", "1600000000000"])
            with self.assertRaises(ValueError):
                subset.collect_records(connection, source, 1)
        finally:
            connection.close()

    def test_five_core_can_lose_item_coverage_after_temporal_split(self):
        connection = sqlite3.connect(":memory:")
        try:
            subset.make_edges(connection)
            connection.executemany("INSERT INTO edges VALUES (?,?)", [
                (f"U{u}", f"P{p}") for u in range(5) for p in range(5)
            ])
            graph = subset.graph_statistics(connection)
            source = self.root / "coverage.csv"
            with source.open("x", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(subset.HEADER)
                for u in range(5):
                    for p in range(5):
                        writer.writerow([f"U{u}", f"P{p}", "5.0", str(1_600_000_000_000 + p * 1000 + u)])
            subset.collect_records(connection, source, 25)
            diagnostics = subset.temporal_diagnostics(connection, graph)
            per_user = diagnostics["per_user_leave_two_out"]
            self.assertEqual(per_user["user_training_minimum"], 3)
            self.assertEqual(per_user["products_without_training_history"], 2)
            self.assertEqual(per_user["validation_interactions_with_unseen_product"], 5)
            self.assertEqual(per_user["test_interactions_with_unseen_product"], 5)
            global_time = diagnostics["global_chronological_80_10_10"]
            self.assertEqual(global_time["training_interactions"], 20)
            self.assertEqual(global_time["products_without_training_history"], 1)
            self.assertEqual(global_time["test"]["interactions_with_unseen_product"], 3)
        finally:
            connection.close()

    def test_low_disk_space_stops_before_data_writes(self):
        with self.assertRaises(OSError):
            subset.check_disk(self.root, 1 << 100)


if __name__ == "__main__":
    unittest.main()
