"""Trusted local artifact loading only; there is no model training path."""
from dataclasses import dataclass
import hashlib
import json
import sys
import threading

from ..config import ROOT, local_path
from ..artifact_provenance import verify_registration


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


@dataclass
class ModelRegistry:
    model: object
    training_fingerprint: str
    manifest_sha256: str
    inference_lock: object
    performance: dict | None = None


def load_registry(settings):
    # Existing scripts import each other by module name. Keep their code intact.
    scripts = str(ROOT/'scripts')
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import hybrid_ranker
    import popularity_baseline
    import item_cf

    directory = local_path(settings.hybrid_directory)
    if settings.artifact_registration is None:
        raise ValueError('Explicit local artifact registration is required')
    manifest, results = verify_registration(settings.artifact_registration)
    if directory != local_path(ROOT/settings.artifact_registration['hybrid_directory']):
        raise ValueError('Settings refer to a different registered bundle')
    model = hybrid_ranker.load_artifacts(directory)
    if model.cf_weight != 0.5 or len(model.items) != settings.expected_eligible:
        raise ValueError('Unapproved frozen configuration')
    if (popularity_baseline.fingerprint(model.snapshot) != manifest['training_fingerprint']
            or item_cf.array_fingerprint(model.cf.matrix,model.cf.users,model.items) != manifest['positive_fingerprint']
            or item_cf.array_fingerprint(model.cf.graph) != manifest['cf_graph_fingerprint']
            or item_cf.array_fingerprint(model.content.features,items=model.items) != manifest['content_fingerprint']):
        raise ValueError('Registered model fingerprints disagree')
    model.load_feature_names(manifest['content_directory'], manifest['content_configuration'])
    from .metrics_service import aggregate_performance
    performance = aggregate_performance(results)
    from ..schemas import MetricsResponse
    MetricsResponse.model_validate(performance)
    if any(segment['evaluated_users'] < 0 for row in performance['models'] for segment in row['segments']):
        raise ValueError('Invalid aggregate user count')
    return ModelRegistry(model, popularity_baseline.fingerprint(model.snapshot),
                         sha256(directory/'hybrid_manifest.json'), threading.Lock(), performance)
