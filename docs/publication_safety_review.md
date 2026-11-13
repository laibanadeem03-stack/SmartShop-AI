# Step 40: final publication safety and license review

Reviewed 2026-11-13. This is preparation for a source repository, not publication
or clearance to distribute data/model bundles. No Git mutations, credential-store
access, package installations, data downloads or application changes occurred.

## License decision and ownership scope

The candidate source, documentation, fixtures and small SVG mark were reviewed for
upstream/copy notices and incompatible material. No obvious ownership blocker was
identified in the authored source/documentation. Fixtures are synthetic; no
third-party application source, fonts, photographs, UI templates or vendored
dependency implementations were found in the candidate set. This finding relies
on the owner's authorization for original project material and is not an independent
chain-of-title certification.

Prepared the standard [MIT License](../LICENSE) with **Copyright (c) 2026 Laiba Nadeem**,
as conditionally approved. Its text is unmodified apart from year/holder substitution.
The scope is original source and documentation owned by, or authorized for licensing
by, that holder. README and [data usage](data_usage.md) explicitly state that it
grants no rights to external datasets, Amazon Reviews 2023, product metadata,
generated model artifacts, private identities, trademarks or other third-party
content. These local data/model resources are not distributed.

## Third-party notices actually identified

The UI imports Lucide, and the approved screenshots visibly contain Lucide artwork.
The layer-style favicon/mark is also covered to the extent it incorporates/adapts
that artwork. The installed `lucide-react==1.72.0` license contains an ISC notice
for Lucide and a retained MIT notice for Feather-derived icons, including Compass.
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) preserves the complete installed
license text, including both notices and the upstream icon list. It is linked from
the README and data-usage document. This addresses a real icon attribution issue,
not a new requirement to attach every installed dependency's license.

Other dependencies are pinned references, not distributed implementations. The npm
lockfile contains MIT, ISC, Apache-2.0, BSD, MPL-2.0, 0BSD and BlueOak expressions;
Python requirements include permissive packages and MPL-2.0 certifi. Neither those
packages, their installations nor compiled bundles are in the candidate set.
Their terms remain applicable to any future redistribution. No separate
Apache-style `NOTICE` requirement was identified for material actually copied into
this candidate set, so no `NOTICE` file is created. Future bundle/deployment review
must examine the actual distributed dependency/transitive contents again.

Sources checked: [MIT standard text](https://opensource.org/license/mit),
[Lucide license](https://lucide.dev/license), installed package license files and
[dataset maintainer usage discussion](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/discussions/1).
Dataset availability and attribution do not establish unrestricted data redistribution.

## Exact publication boundary

The candidate set is the deduplicated union returned by read-only
`git ls-files --cached --others --exclude-standard -z`, measured as files on disk.
It includes source/tests/docs, dependency manifests, the standard license, retained
icon notices, `.env.example`, and exactly two reviewed PNGs. File count and bytes
below include this review document; they exclude `.git/` and all ignored resources.

Final proposed publication set: **149 files, 1,302,051 bytes**.

| Location | Files |
|---|---:|
| Root files | 8 |
| Backend | 25 |
| Documentation, including two reviewed images | 31 |
| Frontend source/configuration/lockfile | 47 |
| Scripts | 20 |
| Python tests | 18 |
| **Total** | **149** |

Sizes refer to current working-tree bytes, not a future Git object/ZIP size; staging
or line-ending conversion could change the latter. A private per-file SHA-256/size
inventory is retained at `data/local/publication-step40/candidate_inventory.json`.
It is ignored and is not a file to publish.

## Security, privacy and ignore checks

Every candidate was read: text was checked for prohibited data/binary extensions,
private-key blocks, common provider-token formats, quoted credential values,
credentials in URLs, personal absolute paths, email addresses, dataset-like IDs,
unexpected external symlinks and unapproved binaries. The only non-text candidates
are the two reviewed PNGs. The lockfile's resolved HTTP packages all use the public
`registry.npmjs.org`; no embedded registry credentials/private host was found.

Initial pattern matches were ten false positives: one intentionally invalid URL
in a host-validation test and nine lines of explicitly constructed synthetic
product-ID fixtures. Those were inspected in context. No actual keys/tokens, raw
dataset identities, product metadata exports, private/company information or
machine-specific user paths were identified. The copyright holder's public name
and upstream copyright/academic credits are intentional attribution.

Ignore probes cover data, metadata/model outputs, database sidecars, private alias
keys/registrations, environments, toolchains, archives, logs, caches, build outputs
and unreviewed screenshots. `.env.example`, safe source, lockfile and the two exact
approved PNG paths remain eligible. No ignored file was force-added. All 111
protected existing data/model/catalog/pointer files retain their baseline hashes.
This is a scoped static review, not a guarantee against every possible secret format.

## Screenshot findings

Both approved images were visually reviewed again. They show only interface labels,
aggregate historical metrics and catalog/cohort sizes. No product titles, descriptions,
photos, dataset user/profile IDs, explanations, browser chrome, paths or credentials
are visible. Their 1440 x 1000 and 390 x 1000 dimensions match the earlier review.
PNG chunks are limited to IHDR/IDAT/IEND, with no embedded textual/EXIF metadata;
hashes match the reviewed local originals. The icon notices above are retained.
This does not clear other captures or grant rights to underlying product content.

## Documentation and metric verification

- **31 Markdown files, 70 local file/image links, three heading anchors and 24 ignore
  probes** passed checks, including fenced blocks and table structure. Hosted GitHub
  Mermaid rendering remains visually unverified.
- **331 metric/count cells across 78 rows** in popularity, CF, content and hybrid
  report comparison/segment tables match saved JSON results at displayed precision,
  with percentage/decimal units accounted for. Count's nonpersonalized/fallback
  behavior is handled explicitly where older results omit a usage object.
- README comparison values and validation NDCG values match the saved model metrics.
  The frozen hybrid manifest still reports CF weight 0.50, content complement 0.50
  and rank constant 60. Selection/test methodology is unchanged.
- Latest 196 Python / 97 frontend counts remain recorded Step 38 results, not new
  executions. No application test suite, model inference, evaluation or training
  was run for this documentation/license review.
- Fresh-clone end-to-end rebuilding is explicitly **unverified**. Source availability,
  lawful data access, exact matching snapshot bytes and ignored artifact rebuilding
  remain requirements. Only the prepared Windows environment is verified.

## Remaining blockers and next safe step

No blocking secret/private-data inclusion or unresolved source/icon licensing issue
was identified in this exact source-only candidate set after retaining the notices.
External dataset/product-content redistribution rights remain unresolved; exclusion
is maintained rather than treating the MIT license as permission. Full clean-environment
reproduction and hosted rendering are limitations, not completed checks.

Next, the owner should review the license scope, retained notices and exact inventory.
If approved separately, prepare an explicit staging allowlist from that inventory,
recheck it against fresh status/ignore results, and review the staged diff before
any later commit or repository creation. This step authorizes none of those actions.
