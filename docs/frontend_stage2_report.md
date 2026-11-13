# SmartShop-AI frontend Stage 2 results

Completed the real catalog and product-details integration while retaining the
approved light editorial design. No package installation, backend endpoint change,
model retraining, metadata modification or personalized frontend integration occurred.

## Implemented behavior

Discover now requests `GET /api/v1/products` with page_size=24. Search is performed
by the backend, debounced approximately 300ms; no client-side slice of the original
twelve-item preview remains. q, category and page are URL state. Search/category
changes reset pagination, and Next/Previous honor actual API totals and boundaries.
Search commits replace the current history entry; category/page changes push entries.
Back/Forward and the product page's Back to results link restore the originating
filters/page. Exact result ranges use returned counts, including the partial last
page. Out-of-range pages offer recovery rather than false ranges.

The five featured category labels were checked against the existing read-only
catalog and accepted by the actual API. The UI does not claim they form an exhaustive
taxonomy or invent facet counts. Unknown featured-category URL values are explicitly
cleared with a notice. Product-ID order remains the server's order.

Product Details now loads its own endpoint independently, including direct links
beyond the former twelve-item preview. It shows the actual title, main category,
hierarchy, original product ID, eligibility and available historical training
interaction count/mean rating. Missing statistics display Not available, not zero;
the mean is labeled training-only and formatted to two decimals. No current
marketplace-rating, price, inventory or specification claim is added.

Eligible products request the existing TF-IDF similarity endpoint. Neighbors retain
the API's order, with at most ten and no popularity substitutions. Noneligible
products make no similarity request. Zero results, 409 responses, missing metadata,
404 products and independent request failures have explicit states and retry actions.
Similarity scores are not turned into percentages or confidence indicators.

A shared keyed resource hook handles AbortController cancellation, ten-second
timeouts, safe errors and manual retry. Changed keys hide old data before effect
cleanup; late responses are ignored even when a mocked transport disregards abort.
Typing cancels pending catalog requests while debounce settles. Product changes
cancel detail/similarity work. Loading skeletons preserve responsive grid structure.
Primary error views retain a page heading; filters, result announcements, navigation
and pagination have accessible labels/states. Mobile content reserves bottom safe-area
space above the existing navigation.

For You and AI Insights remain clearly labeled initial layouts. No profile, new-user,
personalized recommendation, explanation or metrics API is called by this frontend.
No chart, payment, login or unrelated functionality was introduced.

## Tests and build

**40 frontend tests passed across three files**, replacing preview-only assertions
with server-backed behavior. The final Vitest run took **5.59 seconds** including
its environment setup. Coverage includes:

- 24-item requests, parameter encoding and API-shape validation.
- 300ms debounce, pagination reset and initial/shared URL state.
- Back/Forward, filtered result return links and invalid/out-of-range URL recovery.
- Exact totals, empty results and pagination boundary controls.
- Abort and out-of-order response handling, timeout and safe retry.
- Independent product lookup, actual historical-statistic formatting and null handling.
- Similarity order, positive-score validation, zero results, outside-catalog/409,
  independent failure retry and cancellation on product changes.
- Loading markup, navigation accessibility and unchanged future-stage boundaries.

Synthetic test records remain isolated from the running app and production entry
graph. They do not supply products to the actual UI.

**The production build passed** using the existing project-local Node.js 26.13.1
and npm 11.20.0. Final Vite build time was **548ms**:

| Asset | Size | Gzip |
|---|---:|---:|
| HTML | 0.70 kB | 0.42 kB |
| CSS | 34.98 kB | 8.57 kB |
| JavaScript | 297.37 kB | 93.60 kB |

The offline npm dependency-tree check passed. package.json, package-lock.json and
Vite configuration remain unchanged; no dependency or system PATH change was needed.

## Actual browser verification

An isolated local Chrome/DevTools audit used the preexisting browser and portable
Node, with no extra package or browser installation. **Nineteen real flow checks
passed** against the unchanged FastAPI service, including:

1. The first 24 titles/order and total 12,635 exactly matched the API.
2. Next and Previous pages matched the corresponding server pages.
3. Search waited past an initial 120ms observation, committed after debounce,
   reset page one and matched the real server query.
4. Combined search/category filtering and Back/Forward restoration worked.
5. A genuine empty search showed no replacement products; clearing restored results.
6. Direct detail data and formatted training statistics matched the API.
7. The similar-product list matched the API's exact order.
8. Back to results restored the filtered page.
9. A real outside-training product showed missing training statistics and made no
   similarity request.
10. The real saved content-model zero-vector product produced the honest empty state.
11. The actual missing-title product and an empty category hierarchy rendered correctly.
12. An unknown product produced the distinct 404 view.
13. Page 527 contained the correct final **11 products**, with Next disabled.
14. Network-blocked catalog requests showed a safe error and recovered through Retry.

Checks overlap in this summary; the complete nineteen-item list and request evidence
are in the ignored browser-audit receipt. API responses were compared live, not
copied into shipped fixtures. No product images were downloaded or rendered, and
there were **zero uncaught JavaScript exceptions** or forbidden future-stage requests.

| Viewport width | Catalog columns | Horizontal overflow | Pagination button height |
|---|---:|---|---:|
| 320px | 1 | None | 44px |
| 390px | 1 | None | 44px |
| 768px | 2 | None | 44px |
| 1440px | 4 | None | 44px |

Product details also passed a mobile overflow check. Desktop/mobile screenshots were
visually inspected. The verified filtered Screen Protectors collection had **1,886
products**, matching the backend. These are functional/layout checks, not a full
accessibility certification or cross-browser performance benchmark.

## Limits and issues addressed

The API has no category-enumeration/facet endpoint, so the current UI offers five
verified featured filters. Other category text can still be searched globally.
Search is normalized substring matching across title/category text; categories are
whole-label matches. There is no fuzzy search or alternative catalog sort. IDs remain
in stable backend order. Readiness is checked on application startup and explicit
retry; each subsequent data request handles failures independently.

The frozen model catalog still excludes 1,623 browsable products. Similarity cannot
cover them without another approved extension. Missing titles, coarse/noisy category
assignments and historical product metadata are preserved or labeled, not rewritten
as new product facts. Ratings shown on details describe the selected training data,
not current marketplace reviews or model accuracy.

Initial test assertions were corrected for filtered-fixture offsets and text spacing.
A Windows shell-generated punctuation conversion was fixed in the catalog labels.
The browser oracle was tightened to wait for the rendered query/page rather than
only the address-bar update during React navigation. Late-response tests verify the
actual application cancellation behavior independently. No new permissions or
dependencies were required to resolve these issues.

## Files and operation

Created:

```text
frontend/src/api/ApiReadinessProvider.jsx
frontend/src/api/useApiResource.js
frontend/src/components/ui/CatalogStates.jsx
frontend/src/components/ui/Pagination.jsx
frontend/src/features/catalog/ProductDetailsPage.jsx
frontend/src/features/catalog/catalogFilters.js
frontend/src/features/catalog/catalogFilters.test.js
frontend/src/features/catalog/useCatalogFilters.js
frontend/src/styles/catalog.css
docs/frontend_stage2_report.md
```

Modified:

```text
frontend/src/api/catalog.js
frontend/src/api/catalog.test.js
frontend/src/app/App.jsx
frontend/src/app/App.test.jsx
frontend/src/components/layout/AppShell.jsx
frontend/src/components/products/ProductCard.jsx
frontend/src/features/catalog/DiscoverPage.jsx
frontend/src/features/previews/LayoutPreview.jsx
frontend/src/main.jsx
frontend/src/test/fixtures.js
docs/frontend_architecture.md
docs/frontend_stage1_report.md
docs/project_plan.md
```

Replaced and removed the obsolete preview-only
`frontend/src/features/catalog/CatalogPreviewProvider.jsx` and
`frontend/src/features/previews/ProductPreviewPage.jsx`.

Ignored audit files/screenshots are under `data/local/frontend-stage2-20261112/`;
production output remains under ignored `frontend/dist/`. Existing backend/ML code,
metadata, ratings, evaluation splits, models and prepared application catalog are
unchanged. Dependency pins and installed Python package versions are unchanged.
Exact source integrity and environment receipts accompany the local audit.

From the project root, run the API and frontend in separate terminals:

```powershell
.\.venv\Scripts\python.exe -B -m backend
```

```powershell
.\.venv\Scripts\python.exe -B scripts/frontend.py dev
```

Open **http://localhost:5173**. The frontend remains bound to localhost with strict
port 5173 and the existing CORS origin. Test and build commands are:

```powershell
.\.venv\Scripts\python.exe -B scripts/frontend.py test
.\.venv\Scripts\python.exe -B scripts/frontend.py build
```

The temporary browser/API/Vite verification processes are stopped. No Git settings,
remote, commit, push, company project or global environment setting was changed.
Stop for review before Frontend Stage 3.
