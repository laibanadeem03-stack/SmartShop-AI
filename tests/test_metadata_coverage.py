"""Synthetic local Parquet projection and exact identifier coverage tests."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import metadata_coverage_pilot as pilot
from bounded_http import BoundedHTTP
from test_bounded_http import Factory, Response


class CoverageTests(unittest.TestCase):
    def test_sparse_partial_parquet_decodes_only_id_chunks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            db = pilot.projected_database()
            try:
                full = root/'fixture.parquet'
                db.execute('CREATE TABLE fixture AS SELECT printf(\'P%09d\',i) AS parent_asin, repeat(\'unapproved synthetic text\',20)||i AS description FROM range(10000) t(i)')
                db.execute('COPY fixture TO ? (FORMAT PARQUET, ROW_GROUP_SIZE 2048)', [str(full)])
                raw = full.read_bytes()
                footer_start = len(raw)-8-struct.unpack('<I',raw[-8:-4])[0]
                partial = root/'partial.parquet'
                pilot.sparse_file(partial, len(raw))
                pilot.put_range(partial,0,raw[:4])
                pilot.put_range(partial,footer_start,raw[footer_start:])
                ranges, rows = pilot.id_ranges(db,partial,footer_start)
                self.assertEqual(rows,10000)
                self.assertGreater(len(ranges),1)
                self.assertLess(sum(b-a+1 for a,b in ranges),len(raw)-len(raw[footer_start:]))
                for a,b in ranges:
                    pilot.put_range(partial,a,raw[a:b+1])
                decoded = [row[0] for batch in pilot.decoded_batches(db,partial) for row in batch]
                self.assertEqual(decoded,[f'P{i:09d}' for i in range(10000)])
                self.assertNotIn(b'unapproved synthetic text',partial.read_bytes()[:footer_start])
                with self.assertRaises(FileExistsError):
                    pilot.sparse_file(partial,1)
            finally:
                db.close()

    def test_exact_ids_duplicates_invalid_and_interaction_weights(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = pilot.id_store(Path(temporary)/'ids.sqlite3')
            try:
                rows = [('0000000001',),('B000000002',),('B000000002',),(None,),('',),(' ',),('b000000002',),(' B000000002',)]
                counts = pilot.ingest_ids(store,[rows[:2],rows[2:]])
                self.assertEqual(counts,{'rows':8,'valid_rows':3,'null_ids':1,'blank_ids':2,'malformed_ids':2})
                result = pilot.coverage(store,{'0000000001':7,'B000000002':2,'B000000003':1}, {'0000000001'}, True)
                self.assertEqual(result['overall']['matched'],2)
                self.assertEqual(result['outside_training_catalog']['percent'],50)
                self.assertEqual(result['interaction_weighted']['percent'],90)
                self.assertEqual(result['metadata_duplicated_valid_ids'],1)
                self.assertEqual(result['metadata_duplicate_valid_excess_rows'],1)
                self.assertEqual(store.execute('SELECT id FROM identifiers ORDER BY id').fetchall(),[('0000000001',),('B000000002',)])
                partial = pilot.coverage(store,{'0000000001':7,'B000000003':1},set(),False)
                self.assertIn('unresolved',partial['overall'])
                self.assertNotIn('unmatched',partial['overall'])
                self.assertTrue(partial['partial_percentages_are_lower_bounds'])
            finally:
                store.close()

    def test_reference_hash_is_order_independent_and_identity_sensitive(self):
        self.assertEqual(pilot.identifier_hash(['A','B']),pilot.identifier_hash(['B','A']))
        self.assertNotEqual(pilot.identifier_hash(['A']),pilot.identifier_hash(['a']))
        self.assertNotEqual(pilot.identifier_hash(['01']),pilot.identifier_hash(['1']))

    def test_pin_rejects_nonimmutable_revision(self):
        http = BoundedHTTP(connection_factory=Factory([Response(headers={'x-repo-commit':'main'})]))
        with self.assertRaises(pilot.TransferStopped):
            pilot.pin_and_list(http)

    def test_explicit_pin_never_uses_main_and_rejects_alias_before_network(self):
        factory = Factory([])
        http = BoundedHTTP(connection_factory=factory)
        for revision in ('main','latest','a'*39):
            with self.assertRaises(pilot.TransferStopped):
                pilot.pin_and_list(http,revision)
        self.assertEqual(factory.requests,[])
        factory = Factory([Response(headers={'x-repo-commit':'b'*40})])
        with self.assertRaises(pilot.TransferStopped):
            pilot.pin_and_list(BoundedHTTP(connection_factory=factory),'a'*40)
        self.assertIn('/resolve/'+'a'*40+'/',factory.requests[0][2])

    def test_pipeline_rejects_a_different_revision_before_accessing_inputs(self):
        with self.assertRaises(ValueError):
            pilot.prepare_run(Path('missing-evaluation'),Path('missing-cf'),'b'*40)

    def test_pin_requires_exactly_seven_distinct_shards(self):
        revision = 'a'*40
        entries = [{'path':pilot.FOLDER+'/'+name,'type':'file','size':100} for name in pilot.NAMES]
        factory = Factory([Response(headers={'x-repo-commit':revision}),
                           Response(json.dumps(entries).encode())])
        http = BoundedHTTP(connection_factory=factory)
        actual, shards = pilot.pin_and_list(http,revision)
        self.assertEqual(actual,revision)
        self.assertEqual([s['name'] for s in shards],pilot.NAMES)
        self.assertIn(revision,factory.requests[1][2])
        entries[-1] = entries[0]
        http = BoundedHTTP(connection_factory=Factory([
            Response(headers={'x-repo-commit':revision}),Response(json.dumps(entries).encode())]))
        with self.assertRaises(pilot.TransferStopped):
            pilot.pin_and_list(http,revision)

    def test_footer_range_planning_is_id_only_and_budgeted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            db = pilot.projected_database()
            try:
                full = root/'source.parquet'
                db.execute("COPY (SELECT '0000000001' parent_asin, 'synthetic title' title) TO ? (FORMAT PARQUET)",[str(full)])
                raw = full.read_bytes()
                footer_start = len(raw)-8-struct.unpack('<I',raw[-8:-4])[0]
                spans = [(len(raw)-8,len(raw)-1),(0,3),(footer_start,len(raw)-9)]
                responses = [Response(raw[a:b+1],206,{'Content-Length':str(b-a+1),
                              'Content-Range':f'bytes {a}-{b}/{len(raw)}'}) for a,b in spans]
                http = BoundedHTTP(connection_factory=Factory(responses))
                plan = pilot.plan_shard(http,db,root,'a'*40,{'name':'fixture','path':'fixture','bytes':len(raw)})
                self.assertEqual(plan['rows'],1)
                self.assertEqual(http.used,12+(len(raw)-8-footer_start))
                self.assertLess(plan['id_compressed_bytes'],footer_start-4)
                # Planning has not yet fetched ID or text data pages.
                with plan['cache'].open('rb') as stream:
                    self.assertEqual(stream.read(footer_start)[4:],b'\0'*(footer_start-4))
                with self.assertRaises(pilot.TransferStopped):
                    http.admit(http.limit-http.used+1)
            finally:
                db.close()

    def test_static_parquet_and_no_httpfs(self):
        db = pilot.projected_database()
        try:
            self.assertFalse(db.execute("SELECT loaded FROM duckdb_extensions() WHERE extension_name='httpfs'").fetchone()[0])
            self.assertFalse(db.execute("SELECT current_setting('autoinstall_known_extensions')").fetchone()[0])
            self.assertFalse(db.execute("SELECT current_setting('autoload_known_extensions')").fetchone()[0])
        finally:
            db.close()

    def test_disk_check_does_not_assume_sparse_allocation(self):
        shards = [{'bytes':200*pilot.MIB} for _ in range(7)]
        with self.assertRaises(OSError):
            pilot.check_cache_space(shards,768*pilot.MIB)
        self.assertEqual(pilot.check_cache_space(shards,2048*pilot.MIB),1656*pilot.MIB)


if __name__ == '__main__':
    unittest.main()
