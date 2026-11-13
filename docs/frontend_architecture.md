# SmartShop-AI frontend: Stages 1–5

Stage 1 provides the approved editorial visual foundation: light gray canvas,
white cards, indigo actions, teal accents, responsive navigation and category artwork.
Stage 2 connects server-side catalog browsing, full product details, historical
training statistics and eligible-product similarity. Stage 3 connects anonymous
profiles, four frozen recommendation models, cold-start creation and batch-bound
explanations. Stage 4 connects AI Insights to saved offline aggregate metrics, with
accessible comparison charts, split selection and segment tables. See
`final_qa_report.md` for final QA and `local_setup.md` for startup/troubleshooting.
Stage 5 is complete. Publication Step 38 adds portable artifact registration and a
[fresh-clone guide](fresh_clone_setup.md); publishing and deployment still require approval.

## Start locally on Windows

From the SmartShop-AI project directory, start the unchanged API in one terminal:

```powershell
.\.venv\Scripts\python.exe -B -m backend
```

Start the frontend in another terminal:

```powershell
.\.venv\Scripts\python.exe -B scripts/frontend.py dev
```

Open **http://localhost:5173**. Stop each server with Ctrl+C. Vite uses strict port
5173 for development and preview; stop the dev server before starting preview.
The origin matches the existing backend CORS allowlist. Do not use a different
frontend host/port without a separately reviewed configuration change.

The frontend launcher uses the verified project-local Node and npm and explicit
project-local npm configuration/cache paths. It does not edit PATH or persistent
environment variables, install globally, read a company npm configuration, or change
registry settings. No PowerShell execution-policy change is needed.

Useful commands:

```powershell
.\.venv\Scripts\python.exe -B scripts/frontend.py test
.\.venv\Scripts\python.exe -B scripts/frontend.py build
.\.venv\Scripts\python.exe -B scripts/frontend.py dependencies
.\.venv\Scripts\python.exe -B scripts/frontend.py preview
```

The npm scripts themselves also reference the local Windows Node executable.
They are intentionally tied to this approved portable Windows x64 toolchain.
No system Node installation is required. The helper refuses a missing toolchain
instead of falling back to another installation or downloading anything.

## Verified portable toolchain

Only these official Node distribution files were downloaded:

- `https://nodejs.org/dist/v26.13.1/node-v26.13.1-win-x64.zip`
- `https://nodejs.org/dist/v26.13.1/SHASUMS256.txt`

The archive matched its official SHA-256 before extraction:

```text
e2edda75bfb089654705cf65a13b58933bfd5f57148e8ebda916f58a2474f1f7
```

Node.js **26.13.1**, npm **11.20.0**. The extracted toolchain is at
`data/local/toolchains/node-v26.13.1-win-x64/`; the archive, checksum manifest and
verification receipt remain in `data/local/toolchains/node-26.13.1-download/`.
Both locations are covered by the existing `/data/local/` ignore rule.

Compatibility was verified against the resolved packages' Node engines and by
actually running the build/tests. Vite requires ^20.19.0 or >=22.12.0; React Router
8.5.1 requires >=22.22.0; the selected Vitest/jsdom versions explicitly support
Node >=26. No system installer, version manager, registry edit or global package
installation was used. Future toolchain changes require approval.

## Dependencies and reproducibility

All sixteen direct packages have exact versions in `frontend/package.json`,
with transitive resolution/integrity in `package-lock.json`:

| Package | Version |
|---|---:|
| react / react-dom | 19.3.1 |
| react-router | 8.5.1 |
| lucide-react | 1.72.0 |
| recharts | 3.10.1 |
| react-is (required Recharts peer, matched to React) | 19.3.1 |
| vite | 8.3.8 |
| @vitejs/plugin-react | 6.3.0 |
| tailwindcss / @tailwindcss/vite | 4.3.5 |
| vitest | 5.1.0 |
| jsdom | 31.0.0 |
| @testing-library/react | 16.3.3 |
| @testing-library/dom | 10.4.2 |
| @testing-library/jest-dom | 7.0.1 |
| @testing-library/user-event | 14.6.10 |

Tailwind uses the supported Vite plugin and CSS-first `@theme` tokens. React Router
uses declarative routes. Stage 4 added Recharts and its required React-matched peer.
No separate animation, component-kit, browser-automation or lint package was added.
Install lifecycle scripts were disabled; all required native build bindings worked
without system build tools. An offline prune removed six extraneous optional WASM
packages after initial installation; the final npm dependency tree is clean.

For a later approved dependency restore, use the same local Node/npm, the lockfile
and project-local configs/cache. Example from the project root:

```powershell
$shopNode = '.\data\local\toolchains\node-v26.13.1-win-x64\node.exe'
$shopNpm = '.\data\local\toolchains\node-v26.13.1-win-x64\node_modules\npm\bin\npm-cli.js'
& $shopNode $shopNpm --prefix frontend --userconfig=data/local/frontend-stage1-20261112/npm-user.conf --globalconfig=data/local/frontend-stage1-20261112/npm-global.conf --cache=data/local/frontend-stage1-20261112/npm-cache ci --ignore-scripts --no-audit --no-fund
```

This is a restore command, not an instruction to upgrade packages or fetch a new
Node toolchain. Raw metadata, screenshots and local receipts do not belong in source.

## API boundary

`src/api/catalog.js` uses `VITE_API_BASE_URL`, defaulting to
`http://127.0.0.1:8000/api/v1`. The supported override is illustrated in
`frontend/.env.example`; no global environment variable was created. If required,
an operator may create an ignored `frontend/.env.local` and restart Vite. Browser
environment configuration is public: never place secrets or model paths there.

Frontend API reads are:

1. `GET /health/ready`.
2. `GET /products?page=...&page_size=24`, with optional q/category, after readiness succeeds.
3. `GET /products/{product_id}` for independent detail URLs.
4. `GET /products/{product_id}/similar` only for eligible products.

The readiness provider makes only the health request. A shared keyed resource hook
handles each independent request, validates public response fields, uses a ten-second
timeout, cancels superseded/unmounted work and ignores responses even if a transport
does not honor abort. It hides mismatched old-key data before effect cleanup and
provides explicit retry. React StrictMode may start and cancel an initial development
request; these catalog requests are read-only and bounded. Stage 3 creation is separately click-triggered. Readiness is checked on app startup
and retried explicitly on failure, not continuously polled. Catalog/detail/similarity
request errors are displayed and retried independently.

Search is performed by the backend across product titles and category text, with
approximately 300ms debounce. Search, featured category and page are URL state;
changing search/category resets page one. Search commits replace the current history
entry to avoid one entry per typing pause; category and pagination changes push
entries, so Back/Forward restore those states. External URL navigation wins over an
uncommitted search draft. A typed search cancels pending catalog work immediately.

Featured categories are five actual labels verified in the read-only catalog:
Cases, Holsters & Sleeves; Screen Protectors; Chargers & Power Adapters; Smartwatch
Accessories; Automobile Accessories. The API has no category-enumeration endpoint.
The UI identifies this collection as featured, not exhaustive, and displays no
invented facet counts. Unknown URL category values are explicitly cleared with a
notice. Known labels normalize case/whitespace; invalid page numbers normalize to
one and search length is bounded to the API's 200-character limit.

Pagination uses exact API totals/ranges, 24 products per request, and correct boundary
buttons. Valid but out-of-range pages offer a first-page action rather than showing
false ranges. The API preserves binary product-ID order; no unsupported sort is
offered. Search is a case-insensitive contiguous substring match; category matching
uses whole normalized labels. There is no relevance sorting, fuzzy search or global
facet-count endpoint. Total counts apply to the current search/filter combination.

Product titles, model numbers, category hierarchy and eligibility retain their
original meaning. Details load directly, including products beyond the former
twelve-item preview. Historical statistics are labeled training-only; null values
display Not available rather than zero or invented ratings. React renders metadata
as text, not injected HTML. Empty/whitespace category fields and unavailable titles
have explicit presentation fallbacks. Back to results retains the originating URL.

Similarity requests preserve the backend's positive-cosine ordering, with at most
ten neighbors and no popularity substitution. Noneligible products do not trigger
the request. A 409 is informational; zero matches are an honest empty state; other
errors have a separate retry that does not refetch or hide the product detail.
Native scores are not rendered as match probabilities or confidence percentages.

## Routes and UI

| Route | Current behavior |
|---|---|
| `/` | Redirect to `/discover` |
| `/discover` | Real server catalog, q/category/page URL state, 24-item pages |
| `/for-you` | Anonymous historical/new profiles, frozen recommendations and evidence dialogs |
| `/products/:productId` | Independent metadata lookup, training statistics and eligible similarity |
| `/insights` | Saved historical model metrics, three accessible charts, split/segment analysis |
| Other paths | Recovery layout with a Discover link |

Unknown product IDs return a distinct not-found view; backend failures have a separate
connection/retry view. No price, stock status, rating, specification, personalized score,
probability or confidence percentage is invented. The running app never imports
synthetic test fixtures. Category icons are abstract category studies, not product images.

Shared components cover buttons, brand, desktop/mobile navigation and product cards.
The header reflects actual catalog connection state. At desktop sizes the layout
uses four product columns, then three, two and one on progressively smaller screens.
Mobile navigation is fixed at the bottom with safe-area/content padding. The hero's
decorative artwork hides on narrow screens. Product titles wrap/clamp visually while
links retain their full accessible names. Main navigation, labels, pressed filter
states, visible focus, a skip link, live result counts and reduced-motion rules are
included. Mobile search text is 16px to avoid small-input zoom behavior.

## Tests and review

Stage 2 Vitest/React Testing Library checks cover forty focused cases: URL/query contracts,
24-item requests, 300ms debounce, Back/Forward, filter/page reset, cancellation and
stale-response suppression, independent details, historical-statistics validation,
nullable metadata, similarity ordering/zero/outside/error/retry, safe errors, loading,
timeout, accessible controls and unchanged future-stage boundaries. Synthetic fixtures
remain test-only and are absent from the production entry graph. The former preview
tests were updated to assert real server-side behavior rather than preview limits.

An isolated browser audit used the preexisting Chrome executable and project-local
Node's built-in DevTools/WebSocket capabilities. No browser package or browser was
downloaded. Stage 2 checked nineteen real-browser flows and actual missing-title,
empty-category, outside-catalog and zero-vector cases. It compared page/detail/similar
responses with the API, exercised history/search/pagination and network-error retry,
and checked 320/390/768/1440px layouts without overflow or uncaught exceptions.
Requests never reached profile, personalized-recommendation, explanation or metrics
APIs. Current screenshots and browser profiles are ignored under
`data/local/frontend-stage2-20261112/`; the earlier Stage 1 receipts remain preserved.
The browser needed a software-rendered, isolated test profile within the agent
environment; this test configuration is not part of the application or normal launch.

See `frontend_stage1_report.md` for historical Stage 1 checks and
`frontend_stage2_report.md` for its build, tests, file changes and API limits.
Those are historical Stage 2 results. The temporary verification servers are stopped.
Those are historical phase boundaries; Stage 4 and final Stage 5 results are below.

## Stage 3: personalized discovery and explainability

`features/recommendations/` contains the For You feature, profile context and native
explanation dialog. `api/recommendations.js` owns transport and public-contract
validation. It reuses the existing API URL and product validation. No dependency was
added, and the existing catalog/data layer remains in place. ProductCard accepts a
child area for rank, source and explanation controls; its metadata presentation and
catalog links are shared with Discover.

The additional requests are:

- `GET /demo/profiles` after readiness succeeds.
- `POST /demo/users` with `{}` only in the create-button handler. Pending clicks are
  guarded; there is no automatic POST, automatic retry or mount-time creation.
- `GET /users/{public_alias}/recommendations?model=hybrid|content|cf|count`.
- `GET /recommendations/{batch_id}/items/{product_id}/explanation` on demand.

Hybrid is the initial requested model. The API decides the served model and all
ordering/counts. The UI preserves item ranks and sources, distinguishes popularity
from personalized slots and labels cold-start count fallback explicitly. Profiles
use the training snapshot; selecting/browsing products does not update preferences.
Public labels come from the API; raw dataset users are never frontend inputs.

Only `{public_user_id, profile_type}` is persisted under
`smartshop.selected-profile.v1` in localStorage. No model selection, label, history,
batch, recommendation payload or evidence is persisted. Storage denial keeps the
selection in memory. A restored new alias does not cause another POST. A missing
alias has an explicit recovery action. Public aliases are not authentication: this
remains a localhost-only demo and exposes no private dataset identity.

Profile/model keys remount the recommendation session, immediately clearing the
old batch, picks and dialog. Keyed resources cancel superseded work and ignore late
responses even if abort is ignored. Explanation requests are bound to the exact
batch/item/model/source/score. Known safe API error codes are retained; server
messages and unknown codes are never displayed. Ten-second timeouts and independent
retry controls apply. A creation timeout warns that the server may already have
created a profile; another explicit click creates a separate one.

Expired/evicted batches offer a refresh. The old evidence is hidden while a new
recommendation batch is loaded. Evidence is requested only if the original item
still exists in that new batch; otherwise the dialog reports its absence. New batches
can themselves expire. There is no unbounded retry or persistent explanation cache.

The dialog renders actual API reasons, linked supporting products, shared features,
component ranks and count evidence. Optional technical details retain raw score/type,
rank contributions, weights and limited-feature totals without converting them into
probabilities. Shown seeds/features are labeled as examples, since totals include all
contributors. Titles and terms render as React text, never injected HTML.

Native `showModal()` supplies modal/inert behavior. The labeled dialog focuses its
close button, traps Tab/Shift+Tab, supports Escape/native cancel, restores the trigger,
and locks background scrolling with cleanup. Its sticky header and bounded scrolling
fit mobile viewports. Controls meet 44px targets; mobile selects use 16px text.
Reduced-motion rules and existing navigation/focus styles are preserved. Native
dialog behavior is verified in Chrome; screen-reader and other-browser audits remain
future work. Unit tests shim only showModal/close for jsdom; the browser audit tests
the actual native dialog.

Current verification: 70 frontend tests, production build, fifteen real-browser
flow checks across 320/390/768/1440px. The browser compares all twelve profiles and
all four models with direct API responses, checks actual cache eviction, explicit
cold-start creation, storage/reload, failure recovery, stale requests, keyboard focus
and catalog/detail/similarity regression. Screenshots and isolated audit receipts
are ignored under `data/local/frontend-stage3-20261112/`. Normal local start/test/build
commands above are unchanged. No backend/ML changes occurred in Stage 3; analytics
integration is separately completed in Stage 4 below.

## Stage 4: historical evaluation dashboard

AI Insights is route-lazy-loaded so Recharts is fetched only when the Insights route
is visited. It reuses the readiness provider, keyed cancellation/timeout hook, error
views, theme tokens and navigation. The shared hook's generic errors now refer to the
local service rather than incorrectly naming every service a catalog.

`api/metrics.js` validates both public metrics responses and sanitizes HTTP errors.
The comparison report uses `GET /metrics/models`; segment focus uses
`GET /metrics/models/{count|cf|content|hybrid}` with independent loading/retry and
stale-model rejection. A split switch filters the already returned rows; it never
substitutes another split, changes a model or reruns an evaluation. Unsupported/missing
splits are disabled. Missing fields/nulls show Not reported; real zero remains zero.

`features/insights/metricsPresentation.js` contains presentation-only labels,
formatters and source-value selection, not evaluation calculations. Three separate
Recharts bar charts use source Recall/NDCG decimals and coverage fractions scaled by
100. Every axis starts at zero; coverage stays on 0–100%. Animations are disabled.
Model order and colors remain stable. Each chart has a named keyboard focus target,
Left/Right exploration, a live tooltip, text summary and equivalent semantic table.
The default display uses eight decimal places for Recall/NDCG and two for percentages;
the full-precision checkbox reveals the original JavaScript/JSON fractions, including
those behind percentages. Rounding never changes chart inputs.

The live API reports eight model/split rows and eleven segments per row. Segment
tables preserve evaluated-user counts and include warm/cold users, four user/product
combinations and four training-history buckets. Product-segment user counts overlap;
they must not be added. Coverage is always breadth of recommendations in the frozen
training catalog, even for users with cold-product targets. Usage fractions have
their own cohort denominator, which is not exposed as a count by these endpoints.
The UI does not infer it from the evaluated-user counts.

The default-model badge comes from `default_model`. Metrics endpoints expose no fusion
weights, evaluation dates, intervals, significance tests, online behavior or target
reachability rates. These are explicitly not supplied rather than inferred or pulled
from private artifacts. Historical Evaluation labeling, metric definitions, all API
limitations, retrospective five-core selection and metadata timing are visible.
Training-only serving history is distinguished from the test seen-item mask that can
also exclude validation interactions. Nothing is recomputed, tuned or trained.

The installed Recharts README requires a React-matched `react-is`; both runtime pins
are explicit and the dependency tree is clean. Existing React/tool/test pins remain
unchanged. [Recharts installation guidance](https://github.com/recharts/recharts#installation)
and [accessibility documentation](https://github.com/recharts/recharts/wiki/Recharts-and-accessibility)
support the integration. No new browser dependency was installed.

Current checks: 93 frontend tests and fourteen real-browser flow checks at
320/390/768/1440px, including live API equality, axes/keyboard tooltips, split/model
changes, precision, accessible scrolling, error recovery and catalog/detail/For You
regression. Charts resize without page overflow. Narrow tables scroll horizontally
with keyboard-focusable regions and a pinned label column sized to leave full metric
values readable. Screen-reader, other-browser and physical-device audits remain open.
Screenshots/receipts are ignored under `data/local/frontend-stage4-20261113/`.
Local commands above are unchanged. Those are historical Stage 4 results; final QA follows.

## Stage 5: final polish and quality assurance

The final pass preserves the four-page architecture and API contracts. Internal route
changes focus the new main region without interrupting search-query focus. Explanation
close restores a replacement trigger or picks heading after batch refresh. Supporting
text contrast and detail-art disclaimers were corrected, and browse-only detail items
use a neutral status icon. Four regression tests cover the focus issues.

All 97 frontend tests and all 181 existing Python tests pass. Production-preview QA
passed 57 grouped browser checks plus twenty page/viewport combinations across
320/390/768/1024/1440px, including keyboard, reduced motion, privacy, network errors,
timeouts and actual API equality. No package, backend, data or model changes occurred.
The final report records measured bundles/timings, screenshots and limitations.
Verification servers are stopped. Review before any GitHub publishing or deployment.
