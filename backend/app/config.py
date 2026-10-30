import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# mongomock:// is an in-memory database for local trials and tests; data is lost on
# restart. Deployed instances must set MONGODB_URI to a real cluster.
MONGODB_URI = os.getenv("MONGODB_URI") or "mongomock://localhost"
MONGODB_DB = os.getenv("MONGODB_DB", "grocery")
if os.getenv("RENDER") and MONGODB_URI.startswith("mongomock"):
    raise RuntimeError("MONGODB_URI must be set on deployed instances")

# Without SECRET_KEY, tokens are signed with a per-process key and die on restart.
SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_urlsafe(48)
ACCESS_TOKEN_MINUTES = 30
REFRESH_TOKEN_DAYS = 14

# The dashboard's first account. Created once; changing these later has no effect.
ADMIN_EMAIL = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD") or ""

# Turned off in tests so they never call government or map services.
FETCH_MARKET_DATA = os.getenv("FETCH_MARKET_DATA", "true").lower() == "true"
MARKET_CHECK_SECONDS = 3 * 60 * 60

CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000",
).split(",")

DEFAULT_FRESH_MINUTES = 60
DEFAULT_STALE_MINUTES = 1440
NEARBY_RADIUS_KM = 3.0
MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_MULTI_SEARCH_ITEMS = 30
SEARCH_RATE_PER_MINUTE = 120
LOGIN_RATE_PER_MINUTE = 10
