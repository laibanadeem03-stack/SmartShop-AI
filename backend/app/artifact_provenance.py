"""Explicit operator registration is the trust root; hashes precede model loading.

This validates provenance, not arbitrary pickle safety or evaluator correctness.
Only register locally produced/trusted artifacts after reviewing their pipeline run.
"""
import hashlib
import json
import math
import re
from pathlib import Path

from .config import ROOT, local_path


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def digest(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Invalid provenance digest')
    return value


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def relative(path):
    return local_path(path).relative_to(ROOT).as_posix()


def configured_path(value):
    if not isinstance(value, str) or not value:
        raise ValueError('Missing local artifact path')
    path = Path(value)
    return local_path(path if path.is_absolute() else ROOT/path)


def bundle_paths(directory):
    manifest = read_json(directory/'hybrid_manifest.json')
    content = configured_path(manifest['content_directory'])
    cf = configured_path(manifest['cf_directory'])
    paths = {p for folder in (directory,content,cf) for p in folder.iterdir()
             if p.is_file() and p.suffix in ('.json','.npz','.joblib')}
    for name in manifest['component_file_sha256']:
        paths.add(configured_path(name))
    return paths, manifest, content, cf


def validate_lineage(directory):
    """Cross-check saved decisions/results without evaluating held-out interactions."""
    paths, manifest, content, cf = bundle_paths(directory)
    result = read_json(directory/'results.json')
    decision = read_json(directory/'validation_selection.json')
    if result['status'] != 'complete' or result['selection'] != decision:
        raise ValueError('Result and frozen decision disagree')
    for key in ('content_directory','cf_directory','content_configuration','cf_configuration',
                'training_fingerprint','positive_fingerprint','content_fingerprint','cf_graph_fingerprint'):
        if result['components'][key] != manifest[key]:
            raise ValueError('Metrics belong to a different component bundle')
    if (manifest['rank_constant'] != 60 or decision['rank_constant'] != 60
            or manifest['selected_cf_weight'] != 0.5 or decision['selected_cf_weight'] != 0.5
            or manifest['default_model'] != 'hybrid' or decision['default_model'] != 'hybrid'
            or manifest['content_configuration'] != 'tfidf_df2_title80'
            or manifest['cf_configuration'] != 'item_cf_k50_lambda10'
            or manifest['scores_are_probabilities'] is not False
            or manifest['score_type'] != 'normalized_weighted_rrf'
            or decision['test_used_for_selection'] is not False):
        raise ValueError('Frozen serving policy differs from approval')
    expected_fingerprints = {'training':manifest['training_fingerprint'],
        'positive':manifest['positive_fingerprint'], 'content':manifest['content_fingerprint'],
        'cf_graph':manifest['cf_graph_fingerprint']}
    if decision['frozen_component_fingerprints'] != expected_fingerprints:
        raise ValueError('Selection fingerprints disagree')
    for value in expected_fingerprints.values():
        digest(value)
    names = ['hybrid_cf10','hybrid_cf25','hybrid_cf50','hybrid_cf75']
    content_name = manifest['content_configuration']
    scores = {name:result['validation'][name]['segments']['overall']['ndcg_at_10']
              for name in [content_name,*names]}
    if any(type(v) not in (int,float) or not math.isfinite(v) or not 0 <= v <= 1 for v in scores.values()):
        raise ValueError('Invalid saved validation score')
    best = max(names, key=lambda name:scores[name])
    if (best != 'hybrid_cf50' or decision['selected_hybrid'] != best
            or decision['validation_ndcg'] != scores or decision['tie_priority'] != names
            or decision['best_hybrid_validation_ndcg'] != scores[best]
            or decision['content_validation_ndcg'] != scores[content_name]
            or not scores[best] > scores[content_name]
            or decision['strict_validation_improvement'] is not True):
        raise ValueError('Saved validation gate is inconsistent')
    for name, expected in manifest['component_file_sha256'].items():
        if sha256(configured_path(name)) != digest(expected):
            raise ValueError('Frozen component hash mismatch')
    for folder, model in ((cf,manifest['cf_configuration']),(content,content_name)):
        prior = read_json(folder/'results.json')
        for split in ('validation','test'):
            actual, saved = result[split][model], prior[split][model]
            if actual['cohort'] != saved['cohort'] or actual['segments'] != saved['segments']:
                raise ValueError('Frozen control metrics changed')
            if actual['predictions']['sha256'] != saved['predictions']['sha256']:
                raise ValueError('Frozen control prediction provenance changed')
    prior = read_json(content/'results.json')
    for split in ('validation','test'):
        for key in ('cohort','segments'):
            if result[split]['count'][key] != prior[split]['count'][key]:
                raise ValueError('Count control differs from the frozen content evaluation')
    integrity = result['integrity']
    if any(integrity.get(key) is not True for key in ('source_files_unchanged',
            'component_models_unchanged','all_original_controls_identical','test_read_after_default_decision')) or integrity.get('existing_models_retrained') is not False:
        raise ValueError('Incomplete pipeline integrity evidence')
    return paths, manifest, result


def build_registration(directory, metadata, metadata_sha256):
    directory, metadata = local_path(directory), local_path(metadata)
    if sha256(metadata) != digest(metadata_sha256):
        raise ValueError('Metadata differs from the operator-supplied checksum')
    paths, manifest, _ = validate_lineage(directory)
    paths.add(metadata)
    return {'schema_version':1, 'hybrid_directory':relative(directory),
        'metadata':relative(metadata), 'metadata_sha256':metadata_sha256,
        'hybrid_manifest_sha256':sha256(directory/'hybrid_manifest.json'),
        'training_fingerprint':manifest['training_fingerprint'],
        'files':{relative(p):sha256(p) for p in sorted(paths)}}


def verify_registration(registration):
    if type(registration.get('schema_version')) is not int or registration['schema_version'] != 1 or not isinstance(registration.get('files'),dict):
        raise ValueError('Invalid local serving registration')
    for name, expected in registration['files'].items():
        if sha256(configured_path(name)) != digest(expected):
            raise ValueError('Registered artifact bytes changed')
    directory = configured_path(registration['hybrid_directory'])
    metadata = configured_path(registration['metadata'])
    paths, manifest, result = validate_lineage(directory)
    required = {relative(p) for p in paths|{metadata}}
    if not required.issubset(registration['files']):
        raise ValueError('Registration omits a model-loader input')
    if (sha256(metadata) != digest(registration['metadata_sha256'])
            or sha256(directory/'hybrid_manifest.json') != digest(registration['hybrid_manifest_sha256'])
            or manifest['training_fingerprint'] != registration['training_fingerprint']):
        raise ValueError('Registration provenance mismatch')
    return manifest, result
