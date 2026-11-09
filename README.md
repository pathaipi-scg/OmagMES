# OmagMES Factory-Review Prototype

React + TypeScript + Vite frontend with a FastAPI REST backend. This is a factory-review prototype, not a production MES deployment.

## Safety boundary

- **Mock-only writes:** saves live in process memory and are lost when the backend restarts.
- **Gated read-only SQL:** live SQL access is disabled unless explicit configuration/approval gates pass. Do not enable it until the endpoint, instance, SELECT-only permissions, and source metadata are verified. No SQL migrations are run by the application.
- **No production data:** Product names, Lots, counters, reject reasons, and KPI values are explicitly illustrative.
- **No migrations executed:** legacy `dbo` remains untouched. See [schema implementation gate](docs/OmagMES_Schema_Implementation_Gate.md).
- Product standard values remain blank because the historical numeric conflicts are unresolved. Do not copy mock values to production.

## Run locally (Windows PowerShell)

Start the backend and frontend with the tracked launcher:

```powershell
\.\run_omagmes.bat
```

The root `.env` and `.env.example` set `APP_PORT=3001`. Vite reads the repository-root `.env` even when started from the `frontend` directory, and falls back to port 3001 if the setting is missing or invalid. The launcher loads `APP_PORT` from the root `.env` before starting either process. FastAPI reads/reports that application setting but remains bound to `127.0.0.1:8000`; Vite listens on `0.0.0.0:$APP_PORT` and proxies `/api` to FastAPI.

Alternatively, run the processes separately:

```powershell
\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

```powershell
Set-Location frontend
npm run dev
```

Open `http://localhost:<APP_PORT>` on the server computer. From another computer, open `http://<server-hostname-or-IP>:<APP_PORT>`; with the checked-in example value this is port 3001. The browser calls the API through the same origin, so no client-side API hostname or CORS setup is required. Vite's development and preview servers bind all interfaces; make sure Windows Firewall/network policy permits inbound TCP `<APP_PORT>`. FastAPI port 8000 is internal and should not be exposed to clients.

## Validate

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
Set-Location frontend
npm run build
```

## Prototype screens

- Production: load suggestion-only AutoCal, edit Drops/Pieces, explicitly save.
- Wet Reject: dynamic mock `cntR*` reason counters; `R*` button states are not accepted as quantities.
- Wet Run Log: manually classified events; AutoRun does not overwrite operator classifications.
- Wet OEE: visibly simulated demonstration only.
- Curing / Depallet: mock lifecycle records retain the original Lot ID; event grain/units remain unresolved.
- Settings: mock Run/Lot transitions, duplicate LotNames, audited mock rename, approval gates.

See the [FittingMES workflow mapping](docs/OmagMES_FittingMES_Workflow_Implementation_Mapping.md) and [development progress handoff](docs/OmagMES_Development_Progress.md) for verified source analysis and current work status.
