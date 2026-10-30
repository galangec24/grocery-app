import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import admin, api, market
from .bootstrap import ensure_admin, purge_sample_data
from .config import BASE_DIR, CORS_ORIGINS, FETCH_MARKET_DATA, MARKET_CHECK_SECONDS
from .db import USING_MOCK, database, ensure_indexes

log = logging.getLogger("grocery")
WEB_DIST: Path = BASE_DIR.parent / "web" / "dist"


async def market_loop():
    while True:
        try:
            await asyncio.to_thread(market.ingest, database)
        except Exception:
            log.exception("market data check failed")
        await asyncio.sleep(MARKET_CHECK_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if USING_MOCK:
        log.warning("Using the in-memory database; data is lost on restart. Set MONGODB_URI to keep it.")
    ensure_indexes(database)
    purge_sample_data(database)
    ensure_admin(database)
    task = asyncio.create_task(market_loop()) if FETCH_MARKET_DATA else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="Grocery Price Finder API", version="2.0.0", lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
app.include_router(api.router)
app.include_router(admin.router)

# Local convenience only; in production Firebase Hosting serves the website.
if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
