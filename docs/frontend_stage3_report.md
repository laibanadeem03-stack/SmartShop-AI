# Frontend Stage 3: personalized recommendations and explainability

Completed 2026-11-12. The existing editorial shell and catalog remain intact.
For You now connects to the existing FastAPI service, with Hybrid as the initial
requested model (frozen CF/content weights 0.50/0.50, RRF constant 60). No backend,
model, metadata, split, subset or dependency change was required. Stage 4 is not
implemented or authorized by this report.

## Delivered experience

- Twelve API-provided anonymous historical profiles, with labels/activity supplied
  by the backend. Selection uses public aliases, never private dataset identities.
- Explicit creation of a new local demo user through the create button and an empty
  POST body. Duplicate pending clicks are guarded. Mounting/navigation/reload never
  creates an identity automatically.
- Hybrid, content, CF and count selection using the exact backend enum values.
  Returned order, ranks, metadata, sources, eligibility, personalized counts and
  popularity/fallback counts are preserved without client reranking.
- Actual served-model labeling, including forced count-popularity for cold-start
  profiles. No preference submission or learning occurs while browsing.
- Shared catalog-style cards, real titles/categories, abstract category icons,
  product-detail links and on-demand explanations.
- Batch-bound evidence dialogs showing actual reasons, linked seed products,
  shared title/category features, component ranks and count evidence when present.
  Raw scores/types, similarities, contributions and weights are optional technical
  details. These are ranking quantities, not probabilities or confidence levels.
  Limited seed/feature lists are distinguished from all-contributor totals.
- Immediate session clearing on profile/model changes, cancellation, and late-response
  rejection. Expired/evicted batches offer an explicit refresh and request evidence
  only if the product is still in the new batch. If absent, the dialog says so.
- Independent loading/error/retry/empty states, unavailable-profile recovery,
  storage-denial handling and bounded request timeouts. Creation timeout messaging
  warns that the server might already have created an identity.
- Only the selected public alias/type is persisted locally. Batches, traces,
  recommendations, model choices and histories are not persisted.

## Tests and production build

Project-local Node **26.13.1** / npm **11.20.0** were reused. Package manifest and
lockfile are byte-identical to Stage 2; no packages were installed.

**70/70 frontend tests pass across five files** (30 added; the prior 40 remain,
with the obsolete For You preview assertion updated). Final run: 5.87 seconds.
Coverage includes profile/model selection, persistence/reload, explicit creation,
duplicate-click suppression, cold fallback, exact ordering/counts, explanation fidelity,
score/batch/item binding, expired-batch refresh, disappeared-item handling, refresh
failure/retry, model/profile races, dismissed-dialog cancellation, safe errors,
creation timeout, storage denial, native-dialog keyboard logic and Stage 1/2 regression.
Synthetic fixtures remain test-only and are absent from built JavaScript.

The production build passed in **488 ms** with 2,181 transformed modules:

| Output | Size | gzip |
|---|---:|---:|
| JavaScript | 318.00 kB | 98.92 kB |
| CSS | 42.77 kB | 10.14 kB |
| HTML | 0.70 kB | 0.41 kB |

These are Vite's decimal kB measurements. Build/tests used the existing local
launcher; no system Node, PATH changes or additional tooling was needed. Python/ML
tests were not rerun for this frontend-only change; protected source/artifact hashes
were verified instead. Existing catalog frontend tests were rerun in the full suite.

## Actual browser verification

Fifteen flow checks passed using the installed Chrome executable against the real
localhost API and Vite service. No browser or automation package was downloaded.
The final audit compared all twelve profiles and all four models with direct API
results; checked actual evidence, count fallback, public-alias persistence/reload,
unavailable-profile recovery, failure/retry, superseded requests and catalog/detail/
similarity regression. Real cache eviction was induced with 101 bounded count
recommendation requests; the stale batch returned 404 and the UI obtained a new batch
before fetching evidence. No server cache configuration was modified.

The final browser run created **two local demo identities through explicit UI clicks**,
one desktop and one mobile, and exercised both popularity explanations. Earlier
verification passes also created local demo identities; they remain in the existing
runtime identity database. No catalog or frozen artifact was modified or deleted.
No analytics/metrics endpoint was requested. No uncaught browser exceptions occurred;
intentional blocked-network errors were exercised and recovered.

Responsive checks passed at **320, 390, 768 and 1440 pixels**, with one, one, two and
three recommendation columns respectively. There was no horizontal overflow in the
page or dialog. Desktop and mobile profile/model controls, recommendation cards and
dialogs were exercised, including mobile cold-start creation and explanation.

Measured local UI-flow timings in the final development-browser run:

| Flow | Elapsed |
|---|---:|
| First hybrid profile selection to rendered recommendations | 213 ms |
| Content model switch | 92 ms |
| CF model switch | 87 ms |
| Count model switch | 93 ms |
| Hybrid model switch | 112 ms |
| Hybrid explanation opening to rendered evidence | 163 ms |

These are single-run end-to-end observations with approximately 60 ms audit polling,
not API-only latency, percentiles, production performance or a load test. This stage
did not measure peak RAM.

Accessibility checks verified labeled controls, native modal behavior, close-button
initial focus, Tab/Shift+Tab wrap, Escape/native cancel, trigger focus restoration,
background scroll restoration and visible keyboard focus. New selects are at least
46 px high; explanation and close controls are at least 44 px high. Mobile selects
use 16 px text. Reduced-motion styles are retained. Unit tests shim jsdom's missing
dialog methods; the browser audit verifies the actual native dialog. No blocking
finding occurred in these checks. This is not a complete WCAG or screen-reader audit;
physical mobile devices, Safari and Firefox were not tested.

Screenshots and reproducible audit scripts/receipts are Git-ignored under
`data/local/frontend-stage3-20261112/`:

- `desktop-for-you.png`
- `desktop-explanation.png`
- `mobile-for-you-profile.png`
- `mobile-for-you-picks.png`
- `mobile-explanation.png`
- `mobile-cold-start.png`
- `browser-audit.json`, `browser-audit.mjs`, `run-browser-audit.py`
- `baseline.json`, `file-integrity.json`, `delivery-validation.json`

The audit used a new isolated Chrome profile and software-rendered headless flags
needed by the agent environment, not a personal browser profile or normal app launch.
Only processes started by the audit were stopped afterward.

## Source files

Created:

- `frontend/src/api/recommendations.js`
- `frontend/src/api/recommendations.test.js`
- `frontend/src/features/recommendations/ProfileProvider.jsx`
- `frontend/src/features/recommendations/ForYouPage.jsx`
- `frontend/src/features/recommendations/ForYouPage.test.jsx`
- `frontend/src/features/recommendations/ExplanationDialog.jsx`
- `frontend/src/styles/recommendations.css`
- `frontend/src/test/recommendationFixtures.js`
- `docs/frontend_stage3_report.md`

Modified:

- `frontend/src/app/App.jsx` and `App.test.jsx`
- `frontend/src/components/products/ProductCard.jsx` (shared child-content slot)
- `frontend/src/features/catalog/DiscoverPage.jsx` (For You call-to-action copy)
- `frontend/src/main.jsx` (feature stylesheet)
- `frontend/src/test/fixtures.js` and `setup.js`
- `docs/frontend_architecture.md` and `docs/project_plan.md`

Removed the superseded preview: `frontend/src/features/previews/ForYouPage.jsx`.
Generated bundles, screenshots, browser caches and audit receipts stay in existing
ignored directories. The final integrity receipt records protected file checks and
the complete source inventory. No Git configuration, commits, pushes or company
projects were accessed or changed.

## Run locally

From the project root, in separate terminals:

```powershell
.\.venv\Scripts\python.exe -B -m backend
```

```powershell
.\.venv\Scripts\python.exe -B scripts/frontend.py dev
```

Open **http://localhost:5173/for-you**. The API remains at
`http://127.0.0.1:8000/api/v1`; Vite is localhost-only on strict port 5173 and matches
the existing CORS allowlist. Stop both with Ctrl+C. Verification servers are stopped.

```powershell
.\.venv\Scripts\python.exe -B scripts/frontend.py test
.\.venv\Scripts\python.exe -B scripts/frontend.py build
```

## Remaining limitations

This is a local historical demo without authentication or identity recovery across
machines. A new-user alias works only while its identity exists in the local runtime
database; only the currently selected alias is saved, not an account/profile list.
There is no UI deletion or rating submission, and new users do not acquire training
history. The backend caps local demo identities at 1,000.

Explanation batches expire after five minutes, earlier eviction or restart; even a
refreshed batch may expire again. Refresh is explicit, never an automatic loop.
All recommendations use the frozen training catalog and training-only profiles.
Metadata can postdate the training cutoff; retrospective subset/evaluation caveats
and cold-product limitations remain. Explanations describe computed support, not
causal preferences or product suitability guarantees. AI Insights charts, preference
learning, authentication and deployment remain outside Stage 3. Stop for Stage 4 review.
