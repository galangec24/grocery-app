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

# Seeds clearly labelled sample data and runs the simulated retailer feeds.
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
# Deployments set this to a generated value so the well-known password never goes public.
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD") or "demo-password"
DEMO_PASSWORD_IS_PUBLIC = not os.getenv("DEMO_PASSWORD")

CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost,https://localhost,capacitor://localhost,"
    "http://localhost:5173,http://127.0.0.1:5173",
).split(",")

DEFAULT_FRESH_MINUTES = 60
DEFAULT_STALE_MINUTES = 1440
NEARBY_RADIUS_KM = 3.0
MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_MULTI_SEARCH_ITEMS = 30
SEARCH_RATE_PER_MINUTE = 120
LOGIN_RATE_PER_MINUTE = 10
