"""Mutable local identities are isolated from catalog and model databases."""
from contextlib import closing
import sqlite3
import threading
from uuid import uuid4

from ..config import local_path
from ..errors import ApiError


class DemoRepository:
    def __init__(self, directory, limit=1000):
        if not 1 <= limit <= 1000:
            raise ValueError('Invalid local user bound')
        directory = local_path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.path, self.limit, self.lock = directory/'demo_users.sqlite3', limit, threading.Lock()
        with closing(sqlite3.connect(self.path)) as con:
            if con.execute('PRAGMA user_version').fetchone()[0] not in (0,1):
                raise ValueError('Unsupported local identity schema')
            con.execute('CREATE TABLE IF NOT EXISTS local_users(public_user_id TEXT PRIMARY KEY, label TEXT NOT NULL)')
            con.execute('PRAGMA user_version=1')
            con.commit()

    def create(self):
        with self.lock, closing(sqlite3.connect(self.path)) as con:
            with con:
                con.execute('BEGIN IMMEDIATE')
                count = con.execute('SELECT COUNT(*) FROM local_users').fetchone()[0]
                if count >= self.limit:
                    raise ApiError(409, 'LOCAL_USER_LIMIT', 'The local demo-user limit has been reached.')
                result = {'public_user_id':'new_'+uuid4().hex, 'label':'New demo user', 'profile_type':'new_demo'}
                con.execute('INSERT INTO local_users VALUES(?,?)', (result['public_user_id'], result['label']))
        return result

    def exists(self, alias):
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro', uri=True)) as con:
            return con.execute('SELECT 1 FROM local_users WHERE public_user_id=?', (alias,)).fetchone() is not None
