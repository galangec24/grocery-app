# Grocery Price Finder

Official Philippine grocery prices, multi-item search and shopping drafts.

- **Website:** https://grocery-app-71cfd.web.app
- **Android:** [latest APK](https://github.com/galangec24/grocery-app/releases/latest/download/grocery-price-finder.apk)

| Part | Technology | Hosted on |
| --- | --- | --- |
| `backend/` API, price collection, admin | Python FastAPI | Render |
| Database | MongoDB | MongoDB Atlas |
| `web/` price board, shopper app, dashboard | React + Vite | Firebase Hosting |
| `mobile/` phone and tablet app | Flutter, with Kotlin (Android) and Swift (iOS) hosts | GitHub Releases |

## Where the prices come from

No sample data ships with the app. Every price keeps its source link and report date.

| Source | What it is | Coverage | Updated |
| --- | --- | --- | --- |
| [DTI SRP bulletin](https://www.dti.gov.ph/konsyumer/latest-srps-basic-necessities-prime-commoditie) | Official standard price of branded goods | Nationwide, supermarkets and wet markets, unless the item says otherwise | When the DTI issues a bulletin |
| [DA Daily Price Index](https://www.da.gov.ph/price-monitoring/) | Average price seen in covered wet markets | Metro Manila | Daily |

Prices are as live as these publications, not minute by minute. **No public source gives prices per mall.**
Location therefore finds the shopper's real city, lists its malls and supermarkets from OpenStreetMap, and
applies the SRPs for that island group. Store-specific prices arrive when retailers connect through the dashboard.

Products come from the [Open Food Facts](https://world.openfoodfacts.org) family of open databases (ODbL), about 9,800 items sold in the Philippines, copied into MongoDB in small batches. Administrators can add more from the dashboard, for example when a mall partners with the app.

Store prices come from [Open Prices](https://prices.openfoodfacts.org) and shoppers who share what they see. Coverage is thin for now, because no free source has complete Philippine shelf prices. Every price shows where it came from, and nothing is estimated.

### Data integration layer

`backend/app/ingestion.py` registers every price source with its type and permission status. Nothing is imported until permission is on record, and administrators manage this from the dashboard under **Price data sources**. Retailer CSV feeds import there too.

Each price records its retailer, size and last verified date, plus its scope. A price with no named branch is a chain price: it is labelled as one and never pinned to a store on the map, because an online WalterMart price doesn't prove what every branch charges. Prices older than 30 days drop out.

Budolista is registered but blocked: its terms allow personal, non-commercial use only and its `robots.txt` disallows `/api/`. Connecting it needs written permission from Baptiste Group.

Drafts, the budget and saved purchases stay on the device, so they need no account but don't move between devices.

## Price Agent

`backend/app/agent.py` checks every permitted source, saves the best supported price on each product, and tells open apps when prices change. It runs every 15 minutes while the server is awake and as soon as the server starts. An hourly GitHub workflow wakes the free Render service so it keeps running.

Run it by hand with `python -m app.agent` (set `MONGODB_URI` first), or use **Run the agent now** on the dashboard. It prints how many products have a price and how many have no evidence yet. It never invents a price.

To connect a retailer API: record permission under **Price data sources**, then add the https address. The API returns JSON using the same names as the CSV columns. A token goes in the Render variable `SOURCE_<ID>_TOKEN`, for example `SOURCE_WALTERMART_TOKEN`.

## Automation

| Trigger | What happens |
| --- | --- |
| Push to `main` | Tests run on all parts, the Android and iOS apps compile, the website publishes to Firebase, and Render redeploys the backend |
| Push a `v*.*.*` tag | The APK is built, signed and published as a GitHub Release |
| Every hour | Live checks run against production, which wakes Render so the Price Agent runs |

Reports are collected in batches: each run stores up to 14 new daily reports, and a report that fails validation is skipped so the last good prices stay live.

## Releasing an app update

```powershell
.\scripts\release.ps1 1.1.0 "Added price alerts`nFaster search"
```

The notes become the "What's new" text. The app checks GitHub on launch, shows **Update available** with those notes, and shows **What's new** once after updating. Android asks the shopper to confirm the install, and "Install unknown apps" must be allowed for their browser.

Keep `C:\Users\Emmanuel Christian\grocery-app-signing\` backed up somewhere safe and private. If the signing key is lost, phones can't update and every user has to reinstall.

## One-time setup

**GitHub secrets** (Settings > Secrets and variables > Actions):

| Secret | Value |
| --- | --- |
| `ANDROID_KEYSTORE_BASE64` | Contents of `ANDROID_KEYSTORE_BASE64.txt` in the signing folder |
| `ANDROID_KEYSTORE_PASSWORD` | Contents of `ANDROID_KEYSTORE_PASSWORD.txt` in the signing folder |
| `FIREBASE_SERVICE_ACCOUNT` | The JSON from Firebase console > Project settings > Service accounts > Generate new private key |

**Render:** set `MONGODB_URI` once. Everything else comes from `render.yaml`. The dashboard login is `admin@grocery-app.ph` with `ADMIN_PASSWORD` from the Environment tab.

**iPhone:** the app compiles for iOS on every push. Publishing needs an Apple Developer account and a signing setup.

## Run locally

Without `MONGODB_URI` the backend uses an in-memory database that resets on restart.

```powershell
cd web; npm install; npm run build; cd ..\backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Open http://127.0.0.1:8000. Tests: `.venv\Scripts\python -m pytest tests`. Live checks: `pytest live_tests`.

## Where this differs from the documentation

| Documentation | Built | Why |
| --- | --- | --- |
| PostgreSQL + PostGIS | MongoDB | Project decision |
| Store-level price comparison | Official price board, with store comparison kept in the backend | No store-level data exists until retailers join |
| Celery + Redis | Background loop in the API process | Optional for an MVP in the documentation |
| Database constraints | Validation in the import paths | MongoDB has no `CHECK` constraints; unique indexes are enforced |

Not built yet: real retailer API or POS connectors (CSV import works), barcode scanning, price alerts, and shopper accounts for syncing between devices.

On Render's free plan the API sleeps when idle, so the first request after a quiet spell can take about a minute.
