"""Server-side configuration; no request can select a local file."""
from dataclasses import dataclass, field, replace
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / 'data' / 'local'
POINTER = LOCAL / 'application-current.json'
SERVING_CONFIG = LOCAL / 'serving-artifacts.json'
ORIGIN = 'http://localhost:5173'


def local_path(value):
    path = Path(value)
    path = (path if path.is_absolute() else ROOT/path).resolve()
    if not path.is_relative_to(LOCAL.resolve()):
        raise ValueError('Application files must be inside project local storage')
    return path


@dataclass(frozen=True)
class Settings:
    database: Path
    database_sha256: str
    hybrid_directory: Path | None = None
    metadata: Path | None = None
    metadata_sha256: str = ''
    artifact_registration: dict | None = field(default=None, repr=False)
    registration_source: Path | None = None
    expected_products: int = 12635
    expected_eligible: int = 11012
    expected_profiles: int = 12
    runtime_directory: Path = LOCAL / 'backend-runtime'
    batch_capacity: int = 100
    batch_ttl_seconds: float = 300
    maximum_demo_users: int = 1000

    @classmethod
    def from_registration(cls, registration, **kwargs):
        from .artifact_provenance import configured_path, digest
        return cls(hybrid_directory=configured_path(registration['hybrid_directory']),
                   metadata=configured_path(registration['metadata']),
                   metadata_sha256=digest(registration['metadata_sha256']),
                   artifact_registration=registration, **kwargs)

    @classmethod
    def for_preparation(cls, config_path=None):
        config = local_path(config_path or os.environ.get('SMARTSHOP_SERVING_CONFIG', str(SERVING_CONFIG)))
        registration = json.loads(config.read_text(encoding='utf-8'))
        return cls.from_registration(registration, database=LOCAL/'unused.sqlite3',
                                     database_sha256='', registration_source=config)

    @classmethod
    def from_environment(cls):
        # Configuration is operator-owned local state; no API selects a path.
        from .artifact_provenance import digest, sha256
        pointer = local_path(os.environ.get('SMARTSHOP_APP_MANIFEST', str(POINTER)))
        info = json.loads(pointer.read_text(encoding='utf-8'))
        settings = cls.for_preparation(os.environ.get('SMARTSHOP_SERVING_CONFIG') or info.get('serving_config'))
        registration = settings.artifact_registration
        if (registration['metadata_sha256'] != info['metadata_sha256']
                or registration['hybrid_manifest_sha256'] != info['model_manifest_sha256']):
            raise ValueError('Application and registered artifacts disagree')
        if 'serving_config_sha256' in info and sha256(settings.registration_source) != digest(info['serving_config_sha256']):
            raise ValueError('Application registration changed')
        return replace(settings,database=local_path(info['database']),
                       database_sha256=digest(info['database_sha256']))
