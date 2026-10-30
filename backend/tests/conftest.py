import pytest
from fastapi.testclient import TestClient

from app.api import limit_login, limit_search
from app.config import DEMO_PASSWORD
from app.db import database, ensure_indexes
from app.main import app
from app.seed import seed


@pytest.fixture()
def db():
    return database


@pytest.fixture()
def client(db):
    for name in db.list_collection_names():
        db.drop_collection(name)
    ensure_indexes(db)
    seed(db)
    limit_search.hits.clear()
    limit_login.hits.clear()
    with TestClient(app) as test_client:
        yield test_client


def auth(client, email):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def admin(client):
    return auth(client, "admin@demo.local")


@pytest.fixture()
def supervisor(client):
    return auth(client, "supervisor@demo.local")
