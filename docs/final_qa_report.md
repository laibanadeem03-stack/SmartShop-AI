# SmartShop-AI: final UI and integration QA

**Stage 5, 2026-11-13.** Local portfolio application verified; publishing/deployment
is not authorized. See [local setup](local_setup.md) for normal startup, preview,
tests and troubleshooting. No new package/browser, backend contract or model change.

## Results

| Check | Result |
|---|---|
| Frontend regression suite | **97/97**, eight files, 8.74 seconds |
| Existing Python backend/ML suite | **181/181**, no skips/failures, 23.390 seconds test time; 26.98 seconds including process startup |
| Production build | Passed, 699 ms, 2,558 transformed modules |
| Production-preview browser flow groups | **57 passed**: catalog 19, recommendations 15, Insights 14, final quality 9 |
| Page/viewport layout matrix | **20 passed**: four pages × 320/390/768/1024/1440px |
| Browser exceptions | None; intentional network failures recovered |
| Dependencies | Existing pins unchanged; no installs |

Python tests exercise synthetic fixture algorithms and frozen-artifact API parity,
including training-only histories, exclusion masks, explanations, concurrency and
metadata integrity. They do not retrain real models or recreate evaluation results.
Protected backend, subset, metadata, split and model artifacts were checked against
the pre-change SHA-256 manifest. Mutable local demo identities are separate; the
browser recommendation audit created two through explicit desktop/mobile UI clicks.

## Issues reproduced and fixed

- Internal route navigation previously left keyboard focus on removed content or old
  navigation. Focus now moves to the new main region on pathname changes; search/query
  updates preserve input focus. Existing pagination focus remains intact.
- Closing an explanation after refreshing an expired batch lost focus because its
  original card had been replaced. It now restores the replacement item's explanation
  button, or the picks heading if the item disappeared. Restoration is restricted to
  the originating recommendation session so it does not steal another page's focus.
- Product-detail illustration disclaimers were only 6–7px. They now use readable
  10px text, contrast and wrapping. Browse-only detail items no longer show an eligible
  catalog checkmark and use a neutral status style.
- Contrast checks found small supporting labels below 4.5:1: section headings/kickers,
  back links, featured filters, hero notes and the For You callout. Their foregrounds,
  plus browse-only and search-placeholder text, were darkened within the existing palette.

Three new regression assertions failed before the focus fixes and pass afterward;
a fourth protects search focus during URL updates. The remaining 93 tests still pass.
No broad redesign or unrelated feature was added.

## Browser, accessibility and network audit

The preexisting Chrome executable ran with an isolated ignored test profile against
the real API and built production assets on localhost. Mobile checks are emulation,
not physical-device tests. All four pages had one H1, no detected unlabeled visible
controls and no horizontal page overflow at all five widths. Wide analytics tables
scroll inside named keyboard-focusable regions; their pinned labels do not cover
metric values. Three-line card-title truncation is intentional; full accessible link
names and detail-page titles retain original metadata.

Checks exercised search/debounce, verified category filtering, pagination and URL
history, listing/details return paths, similarity, all twelve profiles, all four
recommendation models, source/rank/count preservation, verified explanations, actual
bounded-cache eviction/refresh, and cold-start count fallback. Metrics charts/tables,
split/model selectors and precise source fractions matched the live saved-report API.

Keyboard checks verified route focus, skip/navigation controls, explanation initial
focus, Tab/Shift+Tab trapping, Escape, post-refresh restoration, chart arrows/tooltips,
and table scrolling. Reduced-motion emulation disables smooth scrolling/transitions;
chart animations remain disabled. Programmatic main-text contrast checks passed after
the fixes in all twenty normal layouts, excluding hidden/disabled/decorative text.
This scoped check is not a full WCAG certification or screen-reader audit.

Production checks covered backend-unavailable states, invalid frontend/product routes,
real empty searches, an actual ten-second timeout under 11-second network latency,
manual retry, superseded requests and stale-response rejection. No automatic retry
or idle request loop was detected: initial Discover made one readiness and one catalog
request; Insights split/precision changes made **zero** extra API calls. Development
StrictMode can start/cancel an initial GET; production measurements avoid that effect.

## Privacy and authenticity

- Development Vite returned 403 for probes targeting ignored data, the application
  pointer, virtual-environment files and Git configuration. Production preview returned
  no private content, including a synthetic sentinel. Public assets contain no raw data.
- Built JavaScript contains no local model paths, ignored-data paths or synthetic test
  fixtures; no source maps were emitted. App requests observed in the quality phase
  stayed on localhost/loopback, with no external images, fonts or analytics calls.
- API/identity integration tests preserve public aliases and sanitized errors. Only
  selected public alias/type persists; histories, batches and explanation traces do not.
- Titles, categories, statistics and recommendation evidence remain API-sourced. No
  prices, images, inventory, purchases, preference learning or probabilities were invented.

## Measured production footprint

| Asset | Vite size | gzip |
|---|---:|---:|
| Initial JavaScript | 317.34 kB | 99.16 kB |
| Lazy Insights JavaScript | 389.51 kB | 112.32 kB |
| Shared CSS | 54.02 kB | 12.15 kB |
| HTML | 0.70 kB | 0.41 kB |

Sizes are decimal kB. Route-lazy Recharts keeps its payload off initial Discover/For
You loads. System fonts avoid remote requests. These sizes did not justify new packages,
manual vendor splitting or a risky component rewrite during final QA.

Observed local production-preview flows: **109 ms** navigation-to-catalog products,
**563 ms** navigation-to-Insights segments, and **10,352 ms** for the deliberately slow
search timeout, including debounce. Polling granularity is about 70ms; these are single
run observations, not percentiles or backend inference latency. The end-of-quality-phase
JS heap snapshot was about **16.67 MiB**, not peak/total browser or backend memory.

## Files and screenshots

Modified frontend files:

- `src/components/layout/AppShell.jsx`
- `src/features/recommendations/ExplanationDialog.jsx` and `ForYouPage.jsx`
- `src/features/catalog/ProductDetailsPage.jsx`
- `src/styles/catalog.css`
- `src/app/App.test.jsx` and `src/features/recommendations/ForYouPage.test.jsx`

Created this report and `docs/local_setup.md`; updated `docs/frontend_architecture.md`
and `docs/project_plan.md`. Package manifests/locks, backend code and Python tests are
unchanged. All generated output is ignored under `data/local/` or `frontend/dist/`.

Final screenshots are in `data/local/frontend-stage5-20261113/`:

| Page | Desktop | Mobile |
|---|---|---|
| Discover | `desktop-discover.png` | `mobile-discover.png`, `mobile-catalog.png` |
| Product Details | `desktop-details.png` | `mobile-details.png` |
| For You | `desktop-for-you.png` | `mobile-for-you.png`, `mobile-for-you-picks.png` |
| AI Insights | `desktop-insights.png`, `desktop-insights-charts.png` | `mobile-insights.png`, `mobile-insights-charts.png` |
| Explanation | `desktop-explanation.png` | `mobile-explanation.png` |

The same directory holds `run-final-audit.py`, five bounded audit scripts, JSON network/
layout/privacy receipts, test logs, baseline and `delivery-validation.json`. Verification
processes were stopped; ports 8000/5173/9222 are free on loopback afterward.

## Remaining limitations

No blocking issue remains in the exercised local flows. Safari, Firefox, screen-reader
sessions and physical devices were not tested. The text-contrast scanner does not
certify all visual/nontext contrast states. Native dialog/ResizeObserver require a
modern browser. The prepared private data/toolchain/artifacts are needed for a fresh
checkout; a source clone alone is not a ready installation.

This remains an unauthenticated local historical demo. New users do not learn new
preferences; explanations expire or are evicted; profile selections are browser-local.
The frozen catalog, cold-product reachability, retrospective five-core/metadata timing,
and reused-validation limitations remain. Metrics endpoints still omit fusion weights,
dates, uncertainty intervals and usage-cohort counts. The existing TestClient deprecation
notice is nonblocking; no dependency update was made. Publishing, metadata redistribution,
GitHub actions and deployment await separate review and approval.
