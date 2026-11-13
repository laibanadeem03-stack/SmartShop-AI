from contextlib import contextmanager
import json
import sqlite3


class CatalogRepository:
    def __init__(self, path):
        self.path = path

    @contextmanager
    def connection(self):
        # The prepared catalog remains immutable; new demo users live separately.
        con = sqlite3.connect(self.path.as_uri() + '?mode=ro&immutable=1', uri=True)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA query_only=ON')
        try:
            yield con
        finally:
            con.close()

    def validate(self, settings, registry):
        with self.connection() as con:
            if con.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ValueError('Application database integrity failed')
            info = dict(con.execute('SELECT key,value FROM application_manifest'))
            if (info['schema_version'] != '1'
                    or info['metadata_sha256'] != settings.metadata_sha256
                    or info['training_fingerprint'] != registry.training_fingerprint
                    or info['model_manifest_sha256'] != registry.manifest_sha256):
                raise ValueError('Application provenance mismatch')
            counts = con.execute('SELECT COUNT(*),SUM(recommendation_eligible) FROM products').fetchone()
            profiles = con.execute('SELECT COUNT(*) FROM demo_profiles').fetchone()[0]
            eligible = {r[0] for r in con.execute('SELECT parent_asin FROM products WHERE recommendation_eligible=1')}
            mapped = {r[0] for r in con.execute('SELECT dataset_user_id FROM dataset_user_aliases')}
            if (tuple(counts) != (settings.expected_products, settings.expected_eligible)
                    or profiles != settings.expected_profiles or eligible != set(registry.model.items)
                    or not mapped.issubset(registry.model.snapshot['seen']) or len(mapped) != profiles):
                raise ValueError('Application counts or mappings disagree')

    @staticmethod
    def public_product(row, detail=False):
        # An allowlist prevents leaking private columns if the DB schema grows.
        result = {'product_id': row['parent_asin'],
                  'title': row['title'] if row['title_available'] else 'Title unavailable',
                  'title_available': bool(row['title_available']),
                  'main_category': row['main_category'],
                  'categories': json.loads(row['categories_json']),
                  'recommendation_eligible': bool(row['recommendation_eligible'])}
        if detail:
            result.update(training_interaction_count=row['training_interaction_count'],
                          training_mean_rating=row['training_mean_rating'])
        return result

    def products(self, query):
        clauses, args = [], []
        if query.q and query.q.strip():
            # instr treats percent, underscore, quotes and backslashes literally.
            clauses.append('instr(p.search_text,?)>0')
            args.append(' '.join(query.q.casefold().split()))
        if query.category and query.category.strip():
            clauses.append('EXISTS(SELECT 1 FROM product_categories c WHERE c.parent_asin=p.parent_asin AND c.normalized=?)')
            args.append(' '.join(query.category.casefold().split()))
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        with self.connection() as con:
            total = con.execute('SELECT COUNT(*) FROM products p'+where, args).fetchone()[0]
            rows = con.execute('SELECT p.* FROM products p'+where+' ORDER BY p.parent_asin COLLATE BINARY LIMIT ? OFFSET ?',
                               [*args, query.page_size, (query.page-1)*query.page_size]).fetchall()
        return {'items': [self.public_product(row) for row in rows], 'total': total,
                'page': query.page, 'page_size': query.page_size}

    def product(self, identifier):
        with self.connection() as con:
            row = con.execute('SELECT * FROM products WHERE parent_asin=?', (identifier,)).fetchone()
        return self.public_product(row, detail=True) if row is not None else None

    def profiles(self):
        with self.connection() as con:
            rows = con.execute('SELECT public_user_id,label,profile_type,activity FROM demo_profiles ORDER BY label').fetchall()
        return {'items': [dict(row) for row in rows], 'total': len(rows)}

    def private_user(self, alias):
        """This mapping is consumed by the inference adapter, never serialized."""
        with self.connection() as con:
            row = con.execute('SELECT dataset_user_id FROM dataset_user_aliases WHERE public_user_id=?', (alias,)).fetchone()
        return row[0] if row is not None else None

    def product_summaries(self, identifiers):
        if not identifiers:
            return {}
        marks = ','.join('?' for _ in identifiers)
        with self.connection() as con:
            rows = con.execute('SELECT * FROM products WHERE parent_asin IN ('+marks+')', list(identifiers)).fetchall()
        return {row['parent_asin']: self.public_product(row) for row in rows}
