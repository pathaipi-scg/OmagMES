# OmagMES Factory-Review Prototype

React + TypeScript + Vite frontend with a FastAPI REST backend. This is a factory-review prototype, not a production MES deployment.

## Safety boundary

- **Mock-only API:** all changes live in process memory and are lost when the backend restarts.
- **No SQL connection:** the backend does not read `.env`, connect to SQL Server, or write to any database.
- **No production data:** Product names, Lots, counters, reject reasons, and KPI values are explicitly illustrative.
- **No migrations executed:** legacy `dbo` remains untouched. See [schema implementation gate](docs/OmagMES_Schema_Implementation_Gate.md).
- Product standard values remain blank because the historical numeric conflicts are unresolved. Do not copy mock values to production.

## Run locally (Windows PowerShell)

Backend (from repository root):

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Frontend (in a second terminal):

```powershell
Set-Location frontend
npm run dev
```

Open `http://127.0.0.1:5173`. The frontend can be configured to use another local API origin with `VITE_API_URL`; the default is `http://127.0.0.1:8000`.

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
