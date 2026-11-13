# Step 38: publication preparation

Completed 2026-11-13. This change set addresses security, portability and rebuilding
instructions. It does not publish the project or finalize its README/license.

## Changes and security boundary

- `.gitignore` excludes private environments, data/text, SQLite files and sidecars,
  model bundles, toolchains, archives, logs, screenshots, caches and build outputs.
  Explicit checks confirm that `.env.example`, safe source/tests/documentation,
  SVG artwork and `frontend/package-lock.json` remain eligible.
- Backend configuration uses the ignored operator-owned
  `data/local/serving-artifacts.json`, optionally selected through process-local
  `SMARTSHOP_SERVING_CONFIG`. Configuration paths resolve against the checkout and
  must remain inside its resolved local-data directory. No request selects paths.
- `scripts/configure_serving.py` registers an explicitly chosen trusted bundle.
  It refuses an existing output, verifies metadata against the operator-supplied
  acquisition checksum, checks component/result/decision lineage, then exercises
  native artifact loading and catalog alignment. The current workspace was
  registered against its unchanged application manifest/database.
- Metrics are pinned by each registration instead of one compiled-in, run-specific
  results-file checksum. All JSON/NPZ/joblib loader inputs are checked before
  deserialization, including results and vectorizers. Missing inventory entries,
  altered bytes, escaped paths, mismatched controls, inconsistent validation
  selection or changed loaded-array fingerprints are rejected. The approved
  50/50 hybrid, c=60 and component configurations remain enforced.
- Native model fingerprint, item-order/catalog alignment, strict validation gate
  and database provenance checks remain active. New application manifests also
  bind the registration file's checksum; the existing legacy pointer/database
  retain their original model/metadata bindings.
- The registration is a **local operator trust root**, not a digital signature or
  protection against someone who can replace that root and project code. Register
  only reviewed, locally generated/trusted bundles: joblib loading can execute code.
  There is no automatic discovery or automatic acceptance of changed artifacts.
- Content evaluation accepts either a successful ordinary metadata acquisition or
  successful recovery. A present failed/corrupt recovery cannot fall back to an
  older successful result. New verification receipts bind the exact result file
  and its hash; legacy receipts still require verified values and matching metadata
  bytes. The approved metadata checksum is unchanged.
- Both metadata stages share the explicit immutable revision
  `2b6d039ed471f2ba5fd2acb718bf33b0a7e5598e`. The ID pilot verifies that the returned
  repository revision matches the request; pipeline preparation rejects another
  release before input/network processing. No metadata was acquired in this step.

## Portability and overwrite safety

[fresh_clone_setup.md](fresh_clone_setup.md) is the canonical rebuild recipe. It
covers the union of pinned Python requirements, checksum-verified project-local
Node, lockfile-based frontend restoration, exact ratings input, bounded/pinned
metadata acquisition, explicit pipeline directory hand-offs, model registration,
SQLite preparation and startup. Public documentation uses portable placeholders.
Historical reports are labeled as historical and link to the current recipe.

Evaluation CLIs require explicit input directories and new report paths rather
than historical run defaults. Producers allocate unique local run directories;
reports, registrations, verification receipts and activation pointers use exclusive
creation. An existing pointer is not replaced. On failure, preserve the partial run
for review; do not reuse its output names or reset a metadata transfer allowance.
Locally generated model manifests still record absolute lineage paths. Rebuild at
the final checkout location; moving old bundles or editing their manifests to make
them load is unsupported. A new private alias key may change public aliases while
leaving historical model metrics unchanged.

## Verification

| Check | Actual result |
|---|---|
| Complete Python backend/ML regression suite | **196 passed**, 27.718 s |
| Complete frontend regression suite | **97 passed**, 8 test files, 10.69 s |
| Production build | Passed, 872 ms; previous asset names/sizes unchanged |
| Protected existing data/model files | **111 SHA-256 comparisons**, no changed or missing files |
| Existing catalog and application pointer | Unchanged |
| Live aggregate metrics response | Exact JSON equality with pre-change saved response, all 8 model/split rows |
| Native/API recommendation parity | **48 exact batches**, all 12 historical profiles across four models |
| Explanation verification | **156 verified explanations** |
| Production-preview browser checks | **14 passed**, no uncaught browser exceptions |
| Responsive browser checks | 320, 390, 768 and 1440 px; no horizontal page overflow |

The new tests cover independent synthetic fresh registrations, legitimate rebuilt
results with different run resources/timing, tampered results/components/metadata,
omitted loader inputs, path confinement, mismatched lineage and selection, loaded
array fingerprints, immutable settings, application/config binding, overwrite
refusal, normal/recovery acquisition receipts and pinned revision failures. They
do not train or rewrite the existing models.

The localhost browser run exercised actual production assets and FastAPI responses:
all model metric/segment comparisons, validation/test switching, chart keyboard
navigation, equivalent tables, error/retry recovery, catalog/details/similarity,
personalized hybrid recommendations and explanations. It issued no demo-creation
POST requests. Owned test servers/browser processes were stopped afterward.

The isolated ASGI smoke measured 2.627 s startup and 200.6 MB working set / 210.3 MB
peak working set (decimal MB). Across 50 sequential requests per operation, median
hybrid latency was 31.70 ms and p95 33.36 ms. These exclude socket transport and use
one numeric thread; they are local measurements, not production performance claims.

| Production asset | Size | Gzip |
|---|---:|---:|
| Main JavaScript | 317.34 kB | 99.16 kB |
| Lazy-loaded Insights JavaScript | 389.51 kB | 112.32 kB |
| CSS | 54.02 kB | 12.15 kB |

The existing metrics remain unchanged, including test NDCG@10: count
0.0019501080967814742, CF 0.0030026116532387618, content
0.0036313718867508156 and hybrid 0.004060165285075184. No evaluation was recomputed,
tuned or replaced. Ranking, serving histories, API contracts and frontend behavior
are unchanged.

Private validation receipts, logs and browser captures are under
`data/local/publication-step38/`; they are ignored and must not be published.

## Files changed

New public source/documentation:

- `backend/app/artifact_provenance.py`
- `scripts/configure_serving.py`
- `tests/test_publication_provenance.py`
- `docs/fresh_clone_setup.md`
- `docs/publication_step38_report.md`

Updated public files:

- `.gitignore`
- `backend/app/config.py`, `backend/app/services/model_registry.py`
- `scripts/prepare_application_data.py`, `scripts/metadata_coverage_pilot.py`,
  `scripts/acquire_metadata_text.py`, `scripts/evaluate_popularity.py`,
  `scripts/evaluate_item_cf.py`, `scripts/evaluate_content.py`,
  `scripts/evaluate_hybrid.py`
- `tests/test_metadata_coverage.py`
- `docs/backend_architecture.md`, `docs/frontend_architecture.md`,
  `docs/local_setup.md`, `docs/project_plan.md`
- Portable-path/historical-note edits to `docs/dataset_report.md`,
  `docs/subset_report.md`, `docs/baseline_report.md`, `docs/item_cf_report.md`,
  `docs/content_report.md`, `docs/hybrid_report.md`,
  `docs/metadata_coverage_report.md`, `docs/metadata_text_report.md`

The only new serving configuration is ignored local state. No existing dataset,
metadata, split, model bundle, evaluation artifact, catalog or pointer was changed.
Frontend source, dependencies and lockfile were not changed. No packages were
installed; no datasets or metadata were downloaded. No staging, commits, pushes,
remote creation, Git configuration/authentication changes or company access occurred.

## Remaining review items

Public source, synthetic tests, pinned dependency files and rebuilding instructions
can support reproduction without distributing data. A complete clean-environment
real-data rebuild was **not performed**: it requires the exact external ratings
snapshot, lawful metadata access, disk/network resources and separate authorization
to generate/train new artifacts. Synthetic fresh-run checks and preserved-workspace
integration are narrower evidence. Other operating systems remain unverified.

Attribution: Amazon Reviews 2023, McAuley Lab / UC San Diego; Hou et al. (2024),
[Bridging Language and Items for Retrieval and Recommendation](https://arxiv.org/abs/2403.03952).
The [pinned dataset card](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/blob/2b6d039ed471f2ba5fd2acb718bf33b0a7e5598e/README.md)
identifies the source. In the [maintainer's usage discussion](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/discussions/1),
the maintainer says they cannot assign a dataset license and describes research
availability. This does not establish unrestricted redistribution rights for
product text, data or derived bundles. Keep them private pending rights review;
attribution and a future code license do not resolve those rights.

README finalization, an explicit source-code license, screenshot content/privacy
review, a final publication allowlist and the publication action remain pending.
Nothing was published or deployed. Stop for the owner's review.
