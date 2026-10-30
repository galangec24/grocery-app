import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import admin, api
from .config import BASE_DIR, CORS_ORIGINS, DEMO_MODE
from .db import USING_MOCK, database, ensure_indexes
from .seed import seed
from .sync import run_due_demo_syncs

log = logging.getLogger("grocery")
WEB_DIST: Path = BASE_DIR.parent / "web" / "dist"


async def demo_feed_loop():
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(run_due_demo_syncs, database)
        except Exception:
            log.exception("demo feed run failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if USING_MOCK:
        log.warning("Using the in-memory database; data is lost on restart. Set MONGODB_URI to keep it.")
    ensure_indexes(database)
    task = None
    if DEMO_MODE:
        seed(database)
        task = asyncio.create_task(demo_feed_loop())
    yield
    if task:
        task.cancel()


app = FastAPI(title="Grocery Price Finder API", version="1.0.0", lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
app.include_router(api.router)
app.include_router(admin.router)

# Local convenience only; in production Firebase Hosting serves the website.
if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
