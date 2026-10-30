# Grocery Price Finder

Compare grocery prices across supermarkets, save shopping drafts, and search many items at once.
Built from `Documentation.docx`.

| Part | Technology | Hosted on |
| --- | --- | --- |
| `backend/` API, ranking, sync, admin | Python FastAPI | Render |
| Database | MongoDB | MongoDB Atlas |
| `web/` introduction, dashboard, shopper app | React + Vite | Firebase Hosting |
| `web/android/` APK (same code as the shopper app) | Capacitor | Direct download |

All data shown is fictional sample data until a real retailer is connected.

## Run locally

Without `MONGODB_URI` the backend uses an in-memory database, so no install is needed, but data resets on restart.

```powershell
cd web; npm install; npm run build; cd ..
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

- Website: http://127.0.0.1:8000
- Shopper app: http://127.0.0.1:8000/#/shop
- Dashboard: http://127.0.0.1:8000/#/dashboard (`admin@demo.local` or `supervisor@demo.local`, password `demo-password`, local only)
- API docs: http://127.0.0.1:8000/api/docs
- Tests: `cd backend; .venv\Scripts\python -m pytest`

## Deploy

**1. MongoDB Atlas.** Create a free cluster and a database user, and copy the `mongodb+srv://` connection string.
Allow network access from `0.0.0.0/0`, because Render's free tier has no fixed outbound IP.

**2. Render.** Push this project to GitHub, then choose New > Blueprint and select the repo; it reads `render.yaml`. When prompted, set:

- `MONGODB_URI`: the Atlas connection string
- `CORS_ORIGINS`: `https://YOUR-PROJECT.web.app,https://YOUR-PROJECT.firebaseapp.com,https://localhost`
  (`https://localhost` is what lets the APK connect)

`SECRET_KEY` and `DEMO_PASSWORD` are generated for you. Find `DEMO_PASSWORD` under the service's Environment tab; that is the dashboard password online.

**3. Firebase Hosting.** Copy `web/.env.production.example` to `web/.env.production` and enter your Render URL. Then:

```powershell
cd web; npm run build; cd ..
npx firebase-tools login
npx firebase-tools use --add
npx firebase-tools deploy --only hosting
```

**4. APK.** With `web/.env.production` in place:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-android-toolchain.ps1   # once; about 2.5 GB in C:\dev
powershell -ExecutionPolicy Bypass -File scripts\build-apk.ps1
```

The APK lands in `web/public/downloads/`. Redeploy Firebase and the website's download button turns on.
It is debug-signed, which suits testing. Create a release keystore before distributing it widely.

## Where this differs from the documentation

| Documentation | Built | Why |
| --- | --- | --- |
| PostgreSQL + PostGIS | MongoDB | Project decision. Distance is calculated in Python for now; stores already hold GeoJSON points for a `2dsphere` index once catalogs grow. |
| Flutter | Capacitor + React | Far smaller Android toolchain, and one codebase for the web and the APK. |
| Celery + Redis | Background loop in the API process | The documentation marks these optional for an MVP. The loop only runs the simulated feeds. |
| Database constraints | Validation in the single import path | MongoDB has no `CHECK` constraints. Only the unique indexes are enforced by the database. |

Added beyond the documentation's first release: drafts, multi-item search and basket totals.

Not built yet: real retailer API or POS connectors (only CSV import and simulated feeds), promotions, barcode scanning, and a screen for managing users. Rate limiting is per-process.

On Render's free plan the API sleeps when idle, so the first request after a quiet spell can take about a minute, and simulated feeds pause while it sleeps.
