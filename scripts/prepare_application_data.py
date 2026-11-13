"""Prepare an isolated, reproducible catalog DB from verified local inputs only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import shutil
import sqlite3
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT/'scripts') not in sys.path:
    sys.path.insert(0, str(ROOT/'scripts'))
from backend.app.config import LOCAL, POINTER, Settings, local_path
from backend.app.services.model_registry import load_registry, sha256
from inspect_ratings import process_memory
import content_tfidf as content

SCHEMA = '''
CREATE TABLE products(
 parent_asin TEXT PRIMARY KEY COLLATE BINARY,
 title TEXT, title_available INTEGER NOT NULL CHECK(title_available IN(0,1)),
 main_category TEXT, categories_json TEXT NOT NULL, search_text TEXT NOT NULL,
 recommendation_eligible INTEGER NOT NULL CHECK(recommendation_eligible IN(0,1)),
 training_interaction_count INTEGER, training_mean_rating REAL);
CREATE TABLE product_categories(
 parent_asin TEXT NOT NULL REFERENCES products(parent_asin), normalized TEXT NOT NULL,
 PRIMARY KEY(parent_asin,normalized));
CREATE INDEX category_lookup ON product_categories(normalized,parent_asin);
CREATE TABLE demo_profiles(
 public_user_id TEXT PRIMARY KEY,label TEXT UNIQUE NOT NULL,
 profile_type TEXT NOT NULL CHECK(profile_type='dataset_backed'),
 activity TEXT NOT NULL CHECK(activity IN('light','moderate','active')));
CREATE TABLE dataset_user_aliases(
 public_user_id TEXT PRIMARY KEY REFERENCES demo_profiles(public_user_id),
 dataset_user_id TEXT UNIQUE NOT NULL);
CREATE TABLE application_manifest(key TEXT PRIMARY KEY,value TEXT NOT NULL);
'''


def normalize(value):
    return ' '.join(value.casefold().split())


def select_profiles(snapshot, key, count=12):
    """Four profiles per training-history bucket, deterministic with a private key.

    Neither held-out participation nor model performance is used for selection.
    Public aliases are keyed HMACs, not a public unsalted hash of dataset IDs.
    """
    if len(key) != 32 or count < 1 or count > len(snapshot['seen']):
        raise ValueError('Invalid profile key or count')
    def order(user):
        return hashlib.sha256(('smartshop-demo-selection-42\0'+user).encode()).digest()
    def activity(user):
        n = snapshot['user_counts'][user]
        return 'light' if n <= 2 else 'moderate' if n <= 4 else 'active'
    chosen = []
    for bucket in ('light', 'moderate', 'active'):
        pool = sorted((u for u in snapshot['seen'] if activity(u)==bucket), key=order)
        chosen.extend(pool[:count//3])
    remaining = sorted((u for u in snapshot['seen'] if u not in chosen), key=order)
    chosen.extend(remaining[:count-len(chosen)])
    return [{'public_user_id': 'demo_'+hmac.new(key, ('alias\0'+u).encode(), 'sha256').hexdigest()[:32],
             'label': f'Demo profile {i:02d}', 'profile_type': 'dataset_backed',
             'activity': activity(u), 'dataset_user_id': u}
            for i,u in enumerate(chosen,1)]


def prepare_database(destination, records, registry, metadata_sha256, key, profile_count=12):
    """Create a new DB, preserving all four original metadata fields verbatim."""
    if destination.exists():
        raise FileExistsError('Refusing to overwrite an application database')
    snapshot = registry.model.snapshot
    eligible = set(registry.model.items)
    if not eligible.issubset(records):
        raise ValueError('Training products missing from metadata')
    profiles = select_profiles(snapshot, key, profile_count)
    con = sqlite3.connect(destination)
    try:
        con.execute('PRAGMA foreign_keys=ON')
        con.executescript(SCHEMA)
        with con:
            for identifier in sorted(records):
                record = records[identifier]
                labels = [v for v in [record['main_category'], *record['categories']] if v]
                normalized = {normalize(v) for v in labels if normalize(v)}
                stat = snapshot['items'].get(identifier)
                con.execute('INSERT INTO products VALUES(?,?,?,?,?,?,?,?,?)', (
                    identifier, record['title'], int(bool(content.clean_text(record['title']))),
                    record['main_category'], json.dumps(record['categories'],ensure_ascii=False),
                    normalize(' '.join([record['title'] or '', *labels])), int(identifier in eligible),
                    stat['count'] if stat else None, stat['rating_sum']/stat['count'] if stat else None))
                con.executemany('INSERT INTO product_categories VALUES(?,?)', [(identifier,v) for v in sorted(normalized)])
            for profile in profiles:
                con.execute('INSERT INTO demo_profiles VALUES(?,?,?,?)', tuple(profile[k] for k in
                            ('public_user_id','label','profile_type','activity')))
                con.execute('INSERT INTO dataset_user_aliases VALUES(?,?)',
                            (profile['public_user_id'],profile['dataset_user_id']))
            info = {'schema_version':'1', 'metadata_sha256':metadata_sha256,
                    'training_fingerprint':registry.training_fingerprint,
                    'model_manifest_sha256':registry.manifest_sha256,
                    'profile_selection':'sha256-seed42-training-history-stratified-v1',
                    'alias_key_fingerprint':hashlib.sha256(key).hexdigest(),
                    'history_policy':'training_only', 'held_out_interactions_loaded':'false'}
            con.executemany('INSERT INTO application_manifest VALUES(?,?)', sorted(info.items()))
        if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Prepared database failed integrity check')
        # Compare all original fields, not only aggregate coverage.
        for identifier,title,main,categories in con.execute('SELECT parent_asin,title,main_category,categories_json FROM products'):
            if {'parent_asin':identifier,'title':title,'main_category':main,'categories':json.loads(categories)} != records[identifier]:
                raise ValueError('Metadata values changed during preparation')
    finally:
        con.close()
    return {'products':len(records),'eligible_products':len(eligible),'outside_training':len(records)-len(eligible),
            'demo_profiles':len(profiles),'unusable_titles':sum(not content.clean_text(r['title']) for r in records.values()),
            'metadata_values_preserved':True,'held_out_interactions_loaded':False}


def get_key(path):
    path = local_path(path)
    try:
        with path.open('xb') as stream:
            key = secrets.token_bytes(32)
            stream.write(key)
    except FileExistsError:
        key = path.read_bytes()
    if len(key) != 32:
        raise ValueError('Invalid local alias key')
    return key


def run(activate=False, key_file=None):
    started = time.perf_counter()
    if activate and POINTER.exists():
        raise FileExistsError('An active manifest already exists; use the new manifest via environment configuration')
    LOCAL.mkdir(exist_ok=True)
    if shutil.disk_usage(LOCAL).free < 128*1024*1024:
        raise OSError('At least 128 MiB free disk is required')
    defaults = Settings.for_preparation()
    registry = load_registry(defaults)
    records = content.load_metadata(defaults.metadata, defaults.metadata_sha256)
    if len(records) != defaults.expected_products:
        raise ValueError('Unexpected metadata product count')
    key = get_key(key_file or LOCAL/'backend-demo-alias-key.bin')
    # Python 3.14's Windows tempfile.mkdtemp uses an owner-only DACL. In a
    # sandbox that would prevent the actual workspace user from opening the DB.
    # A normal exclusive mkdir inherits the project's existing local-data ACL.
    directory = LOCAL / ('application-'+uuid4().hex[:12])
    directory.mkdir(mode=0o755)
    db = directory/'app.sqlite3'
    counts = prepare_database(db,records,registry,defaults.metadata_sha256,key)
    # Verify the original source again, never alter it or the frozen artifacts.
    if sha256(defaults.metadata) != defaults.metadata_sha256:
        raise ValueError('Metadata changed while preparing application data')
    manifest = {'database':db.relative_to(ROOT).as_posix(),'database_sha256':sha256(db),
                'created_utc':datetime.now(timezone.utc).isoformat(),
                'metadata_sha256':defaults.metadata_sha256,
                'model_manifest_sha256':registry.manifest_sha256,
                'serving_config':defaults.registration_source.relative_to(ROOT).as_posix(),
                'serving_config_sha256':sha256(defaults.registration_source),
                'counts':counts,'elapsed_seconds':time.perf_counter()-started,
                'memory':process_memory(),'database_bytes':db.stat().st_size,
                'free_disk_bytes':shutil.disk_usage(LOCAL).free,
                'reproduction':'Same source checksums, script, SQLite version and private alias key reproduce DB bytes.'}
    manifest_path = directory/'application_manifest.json'
    with manifest_path.open('x',encoding='utf-8') as stream:
        json.dump(manifest,stream,indent=2)
    if activate:
        with POINTER.open('x',encoding='utf-8') as stream:
            json.dump(manifest,stream,indent=2)
    print(json.dumps({'manifest':str(manifest_path),**counts,'database_bytes':manifest['database_bytes'],
                      'elapsed_seconds':manifest['elapsed_seconds'],'memory':manifest['memory']},indent=2))
    return manifest_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activate',action='store_true',help='Create the default ignored pointer; never overwrite it')
    parser.add_argument('--alias-key-file',type=Path,help='Existing or new private 32-byte key under data/local')
    args = parser.parse_args()
    run(args.activate,args.alias_key_file)
