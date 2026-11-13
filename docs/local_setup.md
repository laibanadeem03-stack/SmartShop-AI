# SmartShop-AI: local setup and use

This guide starts the **existing prepared Windows workspace**, without installing
packages, preparing data or training models. The app uses frozen local artifacts, pinned by `data/local/serving-artifacts.json`.
Cloning source alone does not provide the ignored datasets, database or models.
For a fresh environment, use [fresh_clone_setup.md](fresh_clone_setup.md); the existing
workspace already has its operator-owned artifact registration.

## Start the application

Open two PowerShell terminals in the project:

```powershell
Set-Location -LiteralPath '<PROJECT_ROOT>'
```

Terminal 1 — FastAPI, localhost, one worker:

```powershell
.\.venv\Scripts\python.exe -B -m backend
```

Terminal 2 — React development server:

```powershell
.\.venv\Scripts\python.exe -B scripts/frontend.py dev
```

Open **http://localhost:5173**. The API base is
**http://127.0.0.1:8000/api/v1**; interactive API documentation is at
**http://127.0.0.1:8000/docs**. Stop each process with **Ctrl+C** in its own terminal.

The frontend helper uses project-local Node **26.13.1** / npm **11.20.0**, not PATH.
The existing `.venv`, Node toolchain, frontend dependencies, application pointer,
SQLite catalog, verified metadata and frozen model directories must be present.
No system Node installation, execution-policy change or global configuration is needed.
If something is missing, review its earlier preparation stage; normal startup does
not download data, install packages, rebuild the database or regenerate models.

## Production build preview

Keep the API running. Stop the frontend dev server first, then use:

```powershell
.\.venv\Scripts\python.exe -B scripts/frontend.py build
.\.venv\Scripts\python.exe -B scripts/frontend.py preview
```

Open the same **http://localhost:5173**. Preview serves the production assets locally;
it is not a deployment. Dev and preview both use strict port 5173 and cannot run on
that port together. Both remain localhost-only. Final QA used this production preview.

## Explore the demo

- **Discover:** search titles/categories, use verified featured filters, and paginate.
  Filters are a featured selection, not a complete taxonomy. Opening a title shows
  original metadata, training-only statistics and eligible-product similarity.
- **For You:** choose an anonymous historical profile. Hybrid is the default; compare
  content, CF and count rankings. Open an explanation for actual computed evidence.
  Creating a new demo profile requires the explicit button and starts with popularity.
  Browsing does not train or learn preferences. Only the selected public alias/type
  is saved in this browser; clearing browser storage loses that selection.
- **AI Insights:** switch validation/test, inspect model segments and tables, or enable
  full API precision. These are saved historical aggregates, not live accuracy.

There are no current prices, stock, product photos, purchases, rating submissions,
authentication or real-time preference learning. Illustrations are category icons.
Product metadata attribution remains Amazon Reviews 2023 / McAuley Lab, UC San Diego.

## Verify locally

From the project root:

```powershell
.\.venv\Scripts\python.exe -B scripts/frontend.py test
.\.venv\Scripts\python.exe -B scripts/frontend.py build
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -B scripts/frontend.py dependencies
```

Historical Stage 5 results: **97 frontend tests, 181 Python tests, successful build**.
Python tests include synthetic model/data fixtures and read-only real-artifact API
integration; they do not retrain the prepared recommendation models. No package or
browser installation is part of these commands.

## Troubleshooting

| Symptom | Action |
|---|---|
| Backend connection error | Start terminal 1; check `Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/health/ready'`. Expect `status: ready`. Use the page's retry action afterward. |
| Health live but readiness 503 | Frozen-file/database integrity validation did not succeed. Check the sanitized backend console; review the prepared files and earlier reports. Do not overwrite checksums or regenerate artifacts as a workaround. |
| Port 5173 or 8000 occupied | Stop your own earlier server in its terminal. Do not terminate unrelated processes or let Vite silently switch ports. |
| CORS failure | Use `http://localhost:5173` for the frontend and the approved API base. A different host such as `127.0.0.1:5173` is outside the current CORS allowlist. |
| Search returns no results | Clear search/category filters. Search is a contiguous substring match, not fuzzy search; no replacement products are fabricated. |
| No similar products | Outside-catalog products are browse-only; eligible products can also have zero positive text matches. |
| Explanation expired | Choose Refresh recommendations. Evidence is requested only if the item remains in the new batch. Restart/eviction can invalidate a batch before five minutes. |
| Stored profile unavailable | Use Choose another profile. Local new-user identities depend on this machine's runtime database. |
| Slow request | Requests time out after ten seconds. Check the API, then retry. A timed-out creation POST may already have created an identity; another click creates a separate profile. |
| Missing toolchain/dependencies | The helper deliberately does not fall back to global Node or install packages. Review the pinned setup before requesting a restore. |

`frontend/.env.example` documents the public API URL override. Any approved local
override belongs in ignored `.env.local`; restart dev afterward, or rebuild preview.
Vite environment values are public browser configuration—never put secrets there.

Raw data, metadata, model files, runtime identities, screenshots and browser caches
remain under ignored local directories. Do not copy them into `frontend/public/`,
source files or shared logs. API identities are public aliases, not dataset user IDs.
This remains a local demo without production authentication. Publishing, artifact
redistribution and deployment require separate review and approval.
