"""Training-catalog-only TF-IDF, sparse preference profiles, count fallback."""
from __future__ import annotations

from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import re
import time

import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

import item_cf
import popularity_baseline as popularity

TITLE_CAP = 45_000
CATEGORY_CAP = 5_000
FIELDS = {'parent_asin', 'title', 'main_category', 'categories'}


def clean_text(value):
    if value is None:
        return ''
    if not isinstance(value, str):
        raise ValueError('Text must be a string or null')
    text = re.sub(r'<!--.*?-->', ' ', html.unescape(value), flags=re.DOTALL)
    text = re.sub(r'</?[A-Za-z][^>]*>', ' ', text).casefold()
    text = ' '.join(text.split())
    if text in ('none', 'null', 'nan', 'na', 'n/a') or not re.search(r'\w', text):
        return ''
    return text


def load_metadata(path, expected_sha256):
    import prepare_evaluation as preparation
    if preparation.sha256(path) != expected_sha256:
        raise ValueError('Metadata checksum differs from the verified acquisition')
    records = {}
    with Path(path).open(encoding='utf-8') as stream:
        for line in stream:
            record = json.loads(line)
            if set(record) != FIELDS:
                raise ValueError('Unexpected metadata schema')
            identifier = record['parent_asin']
            if not isinstance(identifier, str) or not identifier or identifier != identifier.strip():
                raise ValueError('Invalid original identifier; no normalization allowed')
            if identifier in records:
                raise ValueError('Duplicate metadata identifier')
            if any(v is not None and not isinstance(v, str) for v in (record['title'], record['main_category'])):
                raise ValueError('Invalid scalar metadata type')
            if not isinstance(record['categories'], list) or any(not isinstance(v, str) for v in record['categories']):
                raise ValueError('Invalid category hierarchy')
            records[identifier] = record
    return records


def documents(records, items):
    if len(items) != len(set(items)):
        raise ValueError('Repeated catalog identifier')
    titles, categories = [], []
    for identifier in items:
        if identifier not in records:
            raise ValueError('Training product is missing verified metadata')
        record = records[identifier]
        titles.append(clean_text(record['title']))
        labels = []
        for value in [record['main_category'], *record['categories']]:
            label = clean_text(value)
            if label and label not in labels:
                labels.append(label)
        categories.append(' '.join(labels))
    return titles, categories


def fit_field(documents_, min_df, cap, max_df=0.95):
    vectorizer = TfidfVectorizer(
        analyzer='word', ngram_range=(1, 2), token_pattern=r'(?u)\b\w+\b',
        lowercase=False, stop_words=None, min_df=min_df, max_df=max_df,
        max_features=cap, dtype=np.float32, norm='l2',
        smooth_idf=True, sublinear_tf=True,
    )
    try:
        matrix = vectorizer.fit_transform(documents_)
    except ValueError as error:
        if not any(message in str(error) for message in (
                'empty vocabulary', 'After pruning, no terms remain',
                'max_df corresponds to < documents than min_df')):
            raise
        return None, sparse.csr_matrix((len(documents_), 0), dtype=np.float32)
    matrix = sparse.csr_matrix(matrix, dtype=np.float32)
    matrix.sort_indices()
    return vectorizer, matrix


def fit_fields(records, items, min_df, title_cap=TITLE_CAP, category_cap=CATEGORY_CAP, max_df=0.95):
    if min_df not in (1, 2) or not items or not 0 < title_cap <= TITLE_CAP or not 0 < category_cap <= CATEGORY_CAP:
        raise ValueError('Unsupported vocabulary configuration')
    started = time.perf_counter()
    titles, categories = documents(records, items)
    tv, title = fit_field(titles, min_df, title_cap, max_df)
    cv, category = fit_field(categories, min_df, category_cap, max_df)
    return {'title_vectorizer': tv, 'category_vectorizer': cv,
            'title': title, 'category': category, 'items': list(items),
            'min_df': min_df, 'fit_seconds': time.perf_counter()-started,
            'clean_empty_titles': sum(not x for x in titles),
            'clean_empty_categories': sum(not x for x in categories)}


def combine_fields(fields, title_weight):
    if title_weight not in (0.80, 0.95):
        raise ValueError('Unsupported title weight')
    title, category = fields['title'], fields['category']
    matrix = sparse.hstack((title.multiply(np.float32(np.sqrt(title_weight))),
                            category.multiply(np.float32(np.sqrt(1-title_weight)))), format='csr', dtype=np.float32)
    if matrix.shape[1]:
        matrix = normalize(matrix, norm='l2', copy=True)
    matrix = sparse.csr_matrix(matrix, dtype=np.float32)
    matrix.eliminate_zeros()
    matrix.sort_indices()
    return matrix


def field_fingerprint(fields):
    payload = []
    for name in ('title', 'category'):
        vectorizer = fields[name+'_vectorizer']
        payload.append(None if vectorizer is None else {
            'vocabulary': {term: int(index) for term,index in vectorizer.vocabulary_.items()},
            'idf': vectorizer.idf_.tolist(),
        })
        payload.append(item_cf.array_fingerprint(fields[name]))
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def ordered_scores(scores, items, counts, seen, k):
    """Sort only one query's nonzero scores; no product-product matrix."""
    if scores.shape != (len(items), 1):
        raise ValueError('Expected one catalog score vector')
    column = scores.tocoo()
    valid = np.isfinite(column.data) & (column.data > 0)
    indices, values = column.row[valid], column.data[valid]
    order = np.lexsort((indices, -counts[indices], -values))
    result = []
    for index in order:
        product = items[int(indices[index])]
        if product not in seen:
            result.append((product, float(values[index])))
            if len(result) == k:
                break
    return result


def load_artifacts(directory):
    """Reload the selected, complete local inference bundle without CSV reads."""
    import prepare_evaluation as preparation
    directory = preparation.require_local(directory)
    result = json.loads((directory/'results.json').read_text(encoding='utf-8'))
    selection = json.loads((directory/'validation_selection.json').read_text(encoding='utf-8'))
    selected = selection['selected_content']
    saved = json.loads((directory/'training_snapshot.json').read_text(encoding='utf-8'))
    snapshot = saved['training']
    snapshot['seen'] = {user: set(values) for user,values in snapshot['seen'].items()}
    mapping = json.loads((directory/'id_mappings.json').read_text(encoding='utf-8'))
    positive = sparse.load_npz(directory/'positive_training.npz')
    features = sparse.load_npz(directory/f'features_{selected}.npz')
    if (popularity.fingerprint(snapshot) != selection['training_fingerprint']
            or saved['fingerprint'] != selection['training_fingerprint']
            or item_cf.array_fingerprint(positive,mapping['users'],mapping['products']) != selection['positive_fingerprint']
            or item_cf.array_fingerprint(features,items=mapping['products']) != result['models'][selected]['fingerprint']):
        raise ValueError('Saved inference bundle fingerprint mismatch')
    return ContentRecommender(positive,mapping['users'],mapping['products'],features,snapshot)


class ContentRecommender:
    """Only masks vary between windows. Seed ratings and text fit stay frozen."""

    def __init__(self, positive, users, items, features, snapshot):
        if (positive.shape != (len(users), len(items)) or features.shape[0] != len(items)
                or items != sorted(snapshot['items']) or users != sorted(snapshot['seen'])
                or features.dtype != np.float32 or positive.dtype != np.float32):
            raise ValueError('Feature, profile, catalog alignment or dtype mismatch')
        self.positive, self.users, self.items, self.features = positive, users, items, features
        self.user_index = {user: index for index, user in enumerate(users)}
        self.snapshot = snapshot
        self.counts = np.asarray([snapshot['items'][item]['count'] for item in items], dtype=np.int64)
        self.fallback = popularity.build_ranking(snapshot)
        self.usage = Counter()
        self.last_sources = []

    def profile(self, user):
        index = self.user_index.get(user)
        if index is None or not self.features.shape[1]:
            return sparse.csr_matrix((1, self.features.shape[1]), dtype=np.float32)
        profile = sparse.csr_matrix(self.positive[index:index+1] @ self.features, dtype=np.float32)
        # Normalized sum equals normalized mean of nonzero item vectors.
        return sparse.csr_matrix(normalize(profile, norm='l2', copy=True), dtype=np.float32)

    def __call__(self, user, seen, k=10):
        if k < 1:
            raise ValueError('k must be positive')
        profile = self.profile(user)
        result = (ordered_scores(self.features @ profile.T, self.items, self.counts, seen, k)
                  if profile.nnz else [])
        personalized = len(result)
        chosen = {product for product, _ in result}
        if len(result) < k:
            for product, _ in self.fallback:
                if product not in seen and product not in chosen:
                    result.append((product, 0.0))
                    chosen.add(product)
                    if len(result) == k:
                        break
        self.usage['users'] += 1
        self.usage['users_with_personalized_recommendations'] += personalized > 0
        self.usage['users_with_only_fallback'] += personalized == 0
        self.usage['personalized_slots'] += personalized
        self.usage['fallback_slots'] += len(result)-personalized
        self.usage['total_slots'] += len(result)
        self.last_sources = ['content']*personalized + ['popularity_fallback']*(len(result)-personalized)
        return result

    def usage_summary(self):
        c = self.usage
        return {**dict(c), 'fraction_users_personalized': c['users_with_personalized_recommendations']/c['users'] if c['users'] else 0,
                'fraction_fallback_slots': c['fallback_slots']/c['total_slots'] if c['total_slots'] else 0}

    def similar_items(self, product, k=10):
        if k < 1 or product not in self.snapshot['items']:
            raise ValueError('Expected a training-catalog query and positive k')
        index = self.items.index(product)
        if not self.features.shape[1]:
            return []
        return ordered_scores(self.features @ self.features[index:index+1].T,
                              self.items, self.counts, {product}, k)
