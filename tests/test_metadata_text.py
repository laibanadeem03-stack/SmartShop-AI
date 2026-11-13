"""Synthetic projection, exact preservation, filtering, and text coverage."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import acquire_metadata_text as text
from bounded_http import BoundedHTTP,TransferStopped
from test_bounded_http import Response,Factory


class TextTests(unittest.TestCase):
    def test_pre_body_transport_retry_uses_same_budget_and_fresh_connection(self):
        good=Factory([Response(b'abcd',206,{'Content-Length':'4','Content-Range':'bytes 0-3/20'})])
        calls=[]
        def create(host):
            calls.append(host)
            if len(calls)==1:
                class Broken:
                    def request(self,*args,**kwargs):
                        raise ConnectionResetError('synthetic transport close')
                    def close(self):
                        pass
                return Broken()
            return good(host)
        http=BoundedHTTP(4,create,keep_alive=True)
        body,_,_=text.fetch_range(http,'https://huggingface.co/a',0,3,20)
        self.assertEqual(body,b'abcd')
        self.assertEqual(http.used,4)
        self.assertEqual(len(http.ledger),2)
        self.assertEqual(http.bounded_transport_retries,1)
        http.close()

    def test_partial_body_never_retried(self):
        factory=Factory([Response(b'ab',206,{'Content-Length':'4','Content-Range':'bytes 0-3/20'})])
        http=BoundedHTTP(8,factory)
        with self.assertRaises(TransferStopped):
            text.fetch_range(http,'https://huggingface.co/a',0,3,20)
        self.assertEqual(http.used,2)
        self.assertEqual(len(factory.requests),1)

    def test_recovery_accepts_only_exact_completed_range_prefix(self):
        shards=[{'name':'first','ranges':[[4,7],[20,22]]}]
        ledger=[{'status':302,'range':[4,7],'payload_bytes':2},
                {'status':206,'range':[4,7],'payload_bytes':4},
                {'transport_error':True,'range':[20,22],'payload_bytes':0}]
        self.assertEqual(text.completed_range_prefix(ledger,shards),1)
        ledger[1]['payload_bytes']=3
        with self.assertRaises(ValueError):
            text.completed_range_prefix(ledger,shards)

    def test_four_column_projection_excludes_forbidden_pages(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            db=text.pilot.projected_database()
            try:
                full=root/'fixture.parquet'
                db.execute('''COPY (SELECT 'Cell Phones' main_category,
                    'Original &amp; Unicode '||CAST(i AS VARCHAR) title,
                    repeat('FORBIDDEN_DESCRIPTION',100) description,
                    ['FORBIDDEN_FEATURES'] features,
                    'FORBIDDEN_DETAILS' details,
                    ['FORBIDDEN_IMAGES'] images,
                    [{'title':'FORBIDDEN_VIDEOS'}] videos,
                    ['Accessories','Cases'] categories,
                    printf('P%09d',i) parent_asin FROM range(10) t(i))
                    TO ? (FORMAT PARQUET)''',[str(full)])
                raw=full.read_bytes()
                plan=text.column_plan(db,full)
                partial=root/'partial.parquet'
                text.copy_spans(full,partial,plan['local_copy_ranges'])
                for a,b in plan['new_ranges']:
                    text.pilot.put_range(partial,a,raw[a:b+1])
                rows=db.execute('SELECT parent_asin,title,main_category,categories FROM read_parquet(?) ORDER BY parent_asin',[str(partial)]).fetchall()
                self.assertEqual(len(rows),10)
                self.assertEqual(rows[0],('P000000000','Original &amp; Unicode 0','Cell Phones',['Accessories','Cases']))
                footer_start=len(raw)-8-struct.unpack('<I',raw[-8:-4])[0]
                for name in ('DESCRIPTION','FEATURES','DETAILS','IMAGES','VIDEOS'):
                    self.assertNotIn(('FORBIDDEN_'+name).encode(),partial.read_bytes()[:footer_start])
                self.assertEqual(set(plan['column_bytes']),{'title','main_category','categories'})
                self.assertEqual(sum(b-a+1 for a,b in plan['new_ranges']),sum(plan['column_bytes'].values()))
                with self.assertRaises(FileExistsError):
                    text.copy_spans(full,partial,plan['local_copy_ranges'])
            finally:
                db.close()

    def test_selected_only_exact_values_and_jsonl_roundtrip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            store=text.create_store(root/'metadata.sqlite3')
            try:
                rows=[('0000000001','  Café &amp; ケース\n',' Main ',[' X ','Y',None]),
                      ('B000000002',None,None,None),('B000000003','unselected','x',[])]
                self.assertEqual(text.store_selected(store,[rows],{'0000000001','B000000002'}),2)
                path=root/'selected.jsonl'
                text.export_jsonl(store,path)
                records=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
                self.assertEqual(records,[dict(zip(text.FIELDS,row)) for row in rows[:2]])
                self.assertNotIn('unselected',path.read_text(encoding='utf-8'))
                with self.assertRaises(FileExistsError):
                    text.export_jsonl(store,path)
            finally:
                store.close()

    def test_duplicates_and_missing_fields_reported_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=text.create_store(Path(temporary)/'metadata.sqlite3')
            try:
                rows=[('0000000001','Useful phone case','Phones',['Cases']),
                      ('B000000002','  ',None,[]),('B000000003',None,'Phones',None),
                      ('0000000001','Another original title',None,['Cases'])]
                ref={'weights':{'0000000001':5,'B000000002':3,'B000000003':2},'training':['0000000001']}
                text.store_selected(store,[rows],ref['weights'])
                result=text.summarize(store,ref,True)
                self.assertEqual(result['unique_products'],3)
                self.assertEqual(result['duplicate_ids'],1)
                self.assertEqual(result['duplicate_excess_records'],1)
                self.assertEqual(result['counts']['records'],4)
                self.assertEqual(result['counts']['missing_or_empty_titles'],2)
                self.assertEqual(result['counts']['missing_category_hierarchy'],2)
                self.assertEqual(result['counts']['missing_all_categories'],1)
                self.assertEqual(result['products_with_usable_text'],2)
                self.assertEqual(result['counts']['category_only_records'],1)
                self.assertEqual(result['interaction_weighted_coverage_percent'],100)
            finally:
                store.close()

    def test_quality_normalization_never_counts_empty_markup_as_text(self):
        for value in (None,'','  ','&nbsp;','<br/>','&lt;br&gt;','N/A','---'):
            self.assertEqual(text.normalized_text(value),'')
        self.assertEqual(text.normalized_text('<b>Café</b> &amp; Cases'),'Café  & Cases')

    def test_invalid_schema_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            db=text.pilot.projected_database()
            try:
                path=root/'missing.parquet'
                db.execute("COPY (SELECT '0000000001' parent_asin,'title' title) TO ? (FORMAT PARQUET)",[str(path)])
                with self.assertRaises(ValueError):
                    text.column_plan(db,path)
            finally:
                db.close()

    def test_invalid_category_type_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=text.create_store(Path(temporary)/'metadata.sqlite3')
            try:
                with self.assertRaises(ValueError):
                    text.store_selected(store,[[('0000000001','title',None,'not a list')]],{'0000000001'})
            finally:
                store.close()

    def test_partial_scan_does_not_label_unseen_products_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=text.create_store(Path(temporary)/'metadata.sqlite3')
            try:
                result=text.summarize(store,{'weights':{'0000000001':5},'training':[]},False)
                self.assertEqual(result['id_coverage']['unresolved'],1)
                self.assertNotIn('unmatched',result['id_coverage'])
            finally:
                store.close()

    def test_export_reproducible_across_input_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            rows=[('0000000001','A','C',['C']),('B000000002','B',None,[])]
            for number,order in enumerate((rows,list(reversed(rows)))):
                store=text.create_store(root/f'{number}.sqlite3')
                try:
                    text.store_selected(store,[order],{row[0] for row in rows})
                    text.export_jsonl(store,root/f'{number}.jsonl')
                finally:
                    store.close()
            self.assertEqual((root/'0.jsonl').read_bytes(),(root/'1.jsonl').read_bytes())


if __name__=='__main__':
    unittest.main()
