"""Register a trusted local pipeline bundle; never train or rewrite existing files."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from backend.app.config import LOCAL, SERVING_CONFIG, Settings, local_path
from backend.app.artifact_provenance import build_registration, configured_path, read_json, sha256
from backend.app.services.model_registry import load_registry


def register(hybrid, metadata, metadata_sha256, output=SERVING_CONFIG, application_manifest=None):
    output = local_path(output)
    if output.exists():
        raise FileExistsError('Refusing to overwrite a serving registration')
    registration = build_registration(hybrid, metadata, metadata_sha256)
    if application_manifest is not None:
        app = read_json(local_path(application_manifest))
        if (app['metadata_sha256'] != registration['metadata_sha256']
                or app['model_manifest_sha256'] != registration['hybrid_manifest_sha256']
                or sha256(configured_path(app['database'])) != app['database_sha256']):
            raise ValueError('Prepared application does not match this bundle')
    settings = Settings.from_registration(registration,database=LOCAL/'unused.sqlite3',database_sha256='')
    registry = load_registry(settings)  # Native fingerprints, IDs, selection and evidence names.
    import content_tfidf
    records = content_tfidf.load_metadata(settings.metadata,settings.metadata_sha256)
    if len(records) != settings.expected_products or not set(registry.model.items).issubset(records):
        raise ValueError('Metadata and training catalogs disagree')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as stream:
        json.dump(registration,stream,indent=2,allow_nan=False)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hybrid',type=Path,required=True)
    parser.add_argument('--metadata',type=Path,required=True,help='Verified selected_metadata.jsonl')
    parser.add_argument('--metadata-sha256',required=True,help='Checksum from the reviewed acquisition receipt')
    parser.add_argument('--output',type=Path,default=SERVING_CONFIG)
    parser.add_argument('--application-manifest',type=Path,help='Also bind registration to an existing prepared catalog')
    args = parser.parse_args()
    result = register(args.hybrid,args.metadata,args.metadata_sha256,args.output,args.application_manifest)
    print(json.dumps({'status':'registered','configuration':str(result.relative_to(ROOT))}))
