# Frontend Stage 4: AI Insights dashboard

Completed and verified on 2026-11-13. AI Insights now presents saved historical
evaluation results from the existing FastAPI metrics endpoints. No evaluation was
rerun, tuned or recomputed. The backend, data, metadata and frozen models are unchanged.
Stage 5 remains subject to review.

## Dependencies and implementation

Installed **Recharts 3.10.1** and its required peer **react-is 19.3.1**, matched to
the existing React 19.3.1 installation as required by the
[Recharts installation instructions](https://github.com/recharts/recharts#installation).
Both direct versions are exact pins; required transitive versions/integrities are
recorded in `frontend/package-lock.json`. Existing direct dependency pins are unchanged.
The offline npm dependency check passes with no invalid/missing/extraneous packages.
No unrelated packages, global installations or settings changes were introduced.

All commands used the project-local Node 26.13.1/npm 11.20.0 toolchain and the
existing project-local npm config/cache. Lifecycle scripts, audit and funding calls
were disabled during installation. The sandbox initially blocked npm registry access;
scoped approved registry access succeeded. npm initially reused react-is 17 from test
tooling, so the required runtime peer was explicitly matched to React before final
verification; the test dependency retains its own compatible nested version.

The Insights route is lazy-loaded, keeping Recharts out of the initial Discover and
For You JavaScript. The approved light editorial theme, navigation, product browsing,
details, similarity, profiles, recommendations and explanations remain intact.

## Dashboard behavior

- Prominent **Historical Evaluation** label and explanation that results are saved
  offline tests, not live shopping behavior.
- API-reported default-model badge and overall Recall@10, NDCG@10 and coverage cards.
  Hybrid is reported as default. Its CF/content weights are not supplied by these
  endpoints and are explicitly labeled unavailable, rather than hardcoded.
- Three separate comparison charts, with stable model order/colors, decimal
  Recall/NDCG scales and percentage catalog coverage. Every value axis starts at zero;
  coverage uses 0–100%. No animation, truncated baseline or artificial minimum bar.
- Validation/test selection filters only the rows for that split. Missing splits are
  disabled. No training, model selection, performance calculation or substitution
  from a different split occurs.
- Exact source values feed charts. Display rounding is eight decimal places for
  Recall/NDCG and two for percentages. The full-precision control reveals original
  JSON/JavaScript fractions, including those behind percentages. Null/missing values
  remain Not reported and real zero remains zero.
- Equivalent semantic tables, named keyboard-operable charts, Left/Right navigation,
  live tooltips, text summaries, metric definitions and evaluated-user counts.
- Per-model segment focus with independent request/retry, training-history buckets,
  warm/cold users and the four user/product combinations. Product-segment counts may
  overlap and are not added together. No absent cold-product aggregate is fabricated.
- Saved personalization/fallback fractions with a denominator caveat: their cohort
  includes users without relevant holdouts, whereas evaluated-user counts do not.
- Visible backend limitation strings, retrospective five-core bias and metadata-timing
  explanations, serving/evaluation history policies and cold-product limitations.
- Readiness, skeletons, sanitized errors, empty reports, retry, independent segment
  errors and cancellation/late-response rejection. No live polling or identity POST.

## Actual API observations and limitations

Both `GET /api/v1/metrics/models` and all four
`GET /api/v1/metrics/models/{model}` responses were inspected. The model endpoint
returns the same envelope, filtering the rows to the requested model, not a different
metric definition. Responses supply **eight model/split rows, eleven segments each**,
both validation and test, a **11,012-product training candidate catalog**, binary
relevance for 4–5 star ratings, and the default model name.

Observed test-overall values, rounded for this aggregate documentation only:

| Model | Evaluated users | Recall@10 | NDCG@10 | Catalog coverage |
|---|---:|---:|---:|---:|
| Count popularity | 6,839 | 0.00345062 | 0.00195011 | 0.14% |
| Collaborative filtering | 6,839 | 0.00494735 | 0.00300261 | 30.57% |
| Content-based | 6,839 | 0.00585148 | 0.00363137 | 77.37% |
| Hybrid | 6,839 | 0.00664107 | 0.00406017 | 73.61% |

Runtime values come exclusively from API responses; this table is not application
data. Validation has 7,779 overall evaluated users per model. The following limits
are surfaced rather than filled with assumptions:

- No fusion weights, evaluation timestamps/date ranges, interval estimates,
  significance tests, latency, online behavior or positive-target reachability rates.
- No raw interaction totals or denominators/counts for personalization usage fractions.
  Evaluated-user counts cannot reconstruct those usage cohorts.
- No independent aggregated cold-product metric. The supplied warm-user/cold-product
  and cold-user/cold-product rows are shown separately.
- Cold-product Recall/NDCG are zero under the frozen training catalog, yet catalog
  coverage can be nonzero: that coverage measures training-catalog recommendations
  shown to the segment's users, not cold products reached.
- Validation was reused for component/hybrid selection. Retrospective five-core
  selection uses future activity; metadata can postdate the training cutoff. Reported
  point estimates do not establish statistical significance or online performance.
- The saved test mask excludes training and validation seen items; online serving
  remains a training-only snapshot. Those protocols are distinguished on the page.

## Tests, build and browser verification

**93/93 frontend tests pass across eight files**: the prior 70 plus 23 new tests.
The obsolete Insights-placeholder assertion was updated to the real route/empty-report
contract. Final run took **7.98 seconds**. Tests cover formatting/precision, source chart
values, split/model selection, segments/counts, missing/null/zero fields, empty reports,
invalid/duplicate rows, sanitized errors/retry, aborts/late responses, default-model
absence, semantic tables/chart labels, and prior catalog/recommendation regressions.
Insights integration tests render actual Recharts; only browser sizing is shimmed in
jsdom. No synthetic data is imported by production modules or found in build output.

Production build passed in **674 ms**, transforming 2,558 modules:

| Output | Size | gzip |
|---|---:|---:|
| Initial JavaScript | 316.80 kB | 99.04 kB |
| Lazy Insights JavaScript | 389.51 kB | 112.32 kB |
| Shared CSS | 53.66 kB | 12.07 kB |
| HTML | 0.70 kB | 0.42 kB |

Vite reports decimal kB. The lazy chunk is fetched on Insights navigation; chart
libraries are not loaded on the initial catalog/recommendation route.

**Fourteen real-browser flow checks passed** against the actual localhost API, using
the existing Chrome executable and Node's built-in DevTools/WebSocket capabilities.
No browser or automation package was installed. Checks cover:

1. All four models/three metrics/default cards matching live API values.
2. Segment values and evaluated-user counts matching per-model responses.
3. Zero-baseline axes and coverage's full 0–100% scale.
4. Keyboard chart exploration, actual tooltip values and equivalent tables.
5. Validation/test changes across charts, cards and segment counts.
6. All model-specific segment endpoint results.
7. Full source precision without changing chart values.
8. Exact API limitations and historical evaluation caveats.
9. Responsive layouts at 320/390/768/1440px without horizontal page overflow.
10. Mobile split/model selection and focusable horizontal table scrolling.
11. Independent segment failure/retry preserving the overall comparison.
12. Metrics network failure/safe empty view/retry.
13. Discover/product-detail/similarity regression.
14. For You's real hybrid recommendations and explanation regression.

No uncaught browser exceptions occurred. Intentional network failures were recovered.
There were **zero POST requests** in this audit. Narrow-table labels remain pinned;
column widths were corrected after visual review found leading digits could be
covered. Final checks at 320px and 390px verify the entire last metric value remains
outside the pinned label and inside the scrollable region. Split/model controls are
46px tall. Chart arrows and focus visibility worked; tables have captions and scoped
headers, keyboard-focusable overflow regions, and text scroll guidance. No blocking
finding remains in the exercised flows. This is not a full WCAG/screen-reader audit;
Safari, Firefox and physical mobile devices remain untested.

Final development-browser observations: **1,312 ms** from navigation to dashboard
plus segments, **283 ms** for validation selection. Polling granularity is about
70 ms; these single-run observations are not production percentiles or API latency.
The end-of-audit Chrome JS heap snapshot was **36.75 MiB**, after navigating through
other pages; it is neither dashboard peak memory nor total process/backend RAM.

The isolated verification browser profile, screenshots and receipts are Git-ignored
under `data/local/frontend-stage4-20261113/`. Audit-owned servers were stopped after
verification. Backend/ML tests were not rerun for frontend-only changes; protected
backend, source data and artifact bytes were checked against the pre-change manifest.

## Files and local use

Created:

- `frontend/src/api/metrics.js` and `metrics.test.js`
- `frontend/src/features/insights/InsightsPage.jsx` and `InsightsPage.test.jsx`
- `frontend/src/features/insights/MetricComparison.jsx`
- `frontend/src/features/insights/metricsPresentation.js` and its test
- `frontend/src/styles/insights.css`
- `frontend/src/test/metricsFixtures.js`
- `docs/frontend_stage4_report.md`

Modified:

- `frontend/package.json` and `package-lock.json`
- `frontend/src/app/App.jsx` (lazy route) and `App.test.jsx`
- `frontend/src/api/useApiResource.js` (shared error-copy wording)
- `frontend/src/main.jsx` (stylesheet import)
- `frontend/src/test/fixtures.js` (synthetic empty metrics response)
- `docs/frontend_architecture.md` and `docs/project_plan.md`

Removed the superseded `frontend/src/features/previews/InsightsPage.jsx` placeholder.
Generated files stay under ignored `data/local/`, `frontend/dist/` and `node_modules/`.
No backend route, model, dataset, metadata, evaluation result, Git configuration,
commit, push or company project was accessed or changed outside this approved scope.

Start the unchanged API and frontend in separate terminals from the project root:

```powershell
.\.venv\Scripts\python.exe -B -m backend
```

```powershell
.\.venv\Scripts\python.exe -B scripts/frontend.py dev
```

Open **http://localhost:5173/insights**. The frontend remains localhost-only on strict
port 5173; the API is `http://127.0.0.1:8000/api/v1`. Existing CORS remains unchanged.
Stop each process with Ctrl+C. Test/build commands:

```powershell
.\.venv\Scripts\python.exe -B scripts/frontend.py test
.\.venv\Scripts\python.exe -B scripts/frontend.py build
```

Screenshots in the ignored Stage 4 directory:

- `desktop-insights-overview.png`
- `desktop-insights-charts.png`
- `desktop-insights-precision.png`
- `desktop-insights-segments.png`
- `mobile-insights-overview.png`
- `mobile-insights-charts.png`
- `mobile-insights-segments.png`
- `mobile-insights-segments-scrolled.png`

`browser-audit.json`, audit scripts, local API response receipts, `dependencies.txt`,
`baseline.json` and `delivery-validation.json` document verification. Browser flags
and isolated software rendering are audit-only, not normal startup settings. Split,
precision and segment choices are in-memory UI state and reset on route remount.
No export, additional evaluation, live monitoring, authentication or deployment feature
was added. Stop for review before Frontend Stage 5.
