# Data usage and attribution

This document records source provenance and the repository's distribution boundary.
It does not grant dataset permissions. The separate source-code license is scoped below.

## Source and citation

SmartShop-AI uses the **Cell Phones & Accessories** category from **Amazon Reviews
2023**, collected by **McAuley Lab, UC San Diego**.

- [Official dataset website](https://amazon-reviews-2023.github.io/)
- [Official five-core ratings source](https://amazon-reviews-2023.github.io/data_processing/5core.html)
- [Pinned Hugging Face dataset card](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/blob/2b6d039ed471f2ba5fd2acb718bf33b0a7e5598e/README.md)
- [Pinned category metadata shards](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/tree/2b6d039ed471f2ba5fd2acb718bf33b0a7e5598e/raw_meta_Cell_Phones_and_Accessories)
- [Maintainer usage/license discussion](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/discussions/1)

The official site supplies this 2024 citation, matching the original paper version
[arXiv:2403.03952v1](https://arxiv.org/abs/2403.03952v1). Later arXiv revisions may
use a different title or author list; this is the source's original attribution:

```bibtex
@article{hou2024bridging,
  title={Bridging Language and Items for Retrieval and Recommendation},
  author={Hou, Yupeng and Li, Jiacheng and He, Zhankui and Yan, An and Chen, Xiusi and McAuley, Julian},
  journal={arXiv preprint arXiv:2403.03952},
  year={2024}
}
```

## Verified local provenance

The inspected ratings CSV has SHA-256
`2fb7ca7f0931aca31eb00c234d254f7e207dee18c335c9aedce4ff1c23ac96d1`.
It contains 2,752,785 interactions. The deterministic subset has 171,104
interactions, 25,791 users and 12,635 products; its distinct-neighbor five-core
property holds before the chronological split.

Metadata acquisition uses immutable repository revision
`2b6d039ed471f2ba5fd2acb718bf33b0a7e5598e`, seven Parquet shards, column projection
and metered range requests. Only `parent_asin`, `title`, `main_category` and
`categories` were acquired. All subset products matched; 12,634 have usable titles
and every product has usable category text. Descriptions, feature bullets, images
and videos were not acquired. Product joins preserve parent IDs, and ratings and
timestamps retain their source meaning.

See [inspection](dataset_report.md), [subsetting](subset_report.md),
[metadata coverage](metadata_coverage_report.md), [text acquisition](metadata_text_report.md)
and [rebuild instructions](fresh_clone_setup.md) for checksums and methods. A present
public source URL does not prove that future downloads will match the inspected bytes.

## Usage rights: verified facts and unresolved questions

The maintainer's linked discussion says the lab cannot assign a dataset license and
describes making it available primarily for research. The dataset card and citation
establish the source; they do **not** establish unrestricted redistribution rights.
No assertion is made that attribution alone authorizes public redistribution,
commercial use, screenshots of substantial product content, or derived model bundles.
The paper's own license is not a license for all underlying Amazon content.

Review applicable terms and rights before acquiring or reusing data. External access
requirements and source availability can change. The project does not redistribute
tokens or provide a means of bypassing upstream access controls. This documentation
is a provenance record, not a legal determination that a particular use is permitted.

## Repository distribution boundary

The planned public source repository contains implementation code, synthetic tests,
aggregate evaluation reports, setup instructions and reviewed interface captures.
It does **not** distribute:

- Raw or selected rating records, user IDs or product-ID exports.
- Downloaded metadata, product text, partial Parquet caches or raw transfer ledgers.
- Generated model bundles, vectorizers, matrices, predictions or evidence traces.
- Private alias mappings, alias keys, application/runtime databases or operator registrations.
- Local toolchains, environment files, logs or unreviewed screenshots.

Two reviewed AI Insights screenshots contain only interface labels and aggregate
historical results. Their review is recorded in [portfolio publication notes](portfolio_publication.md#screenshot-review).
This narrow inclusion is not clearance to distribute screenshots containing product
metadata, profile histories or recommendation evidence.

## Reproduction and evaluation caveats

A new developer must obtain lawful access to matching source inputs and rebuild the
ignored local resources. Fresh-clone end-to-end reproduction has not been verified.
The currently prepared workspace and synthetic fresh-registration tests are narrower
evidence. Do not relax integrity checks when a source snapshot or selection differs.

Five-core graph selection uses future participation retrospectively. Current product
metadata may not represent titles/categories at the earlier training cutoff. The
11,012-product training catalog excludes cold products even though all 12,635 can
be browsed. Low absolute offline metrics and validation reuse limit interpretation;
they are not live-shopping, causal or statistical-significance claims.

## Source code and third-party dependencies

The root [MIT License](../LICENSE), copyright 2026 Laiba Nadeem, covers original
source code and documentation owned by, or authorized for licensing by, its holder.
It grants **no rights** to external datasets, downloaded product metadata, generated
model artifacts, private identity resources, or other third-party content. Those
local data/model resources are not distributed. It does not relicense dependencies
or trademarks. [Third-party notices](../THIRD_PARTY_NOTICES.md) retain the applicable
Lucide/Feather icon terms; other dependencies retain their upstream licenses.
