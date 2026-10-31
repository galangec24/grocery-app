"""Crowdsourced prices: accounts, proof photos, comparison, agreement and admin review."""
import io
from datetime import timedelta

import pytest

from app import market, proofs
from app.db import utcnow
from conftest import shopper
from test_market import SRP_PDF, SRP_URL, dti_srp

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 200
BODY = dict(name="Piatos Cheese 85g", store_name="SM Hypermarket Cebu", latitude=10.31, longitude=123.89, city="Cebu City", price=45)


def send(client, headers, photo=JPEG, **change):
    return client.post("/api/v1/market/proofs", data={**BODY, **change}, headers=headers,
                       files={"photo": ("proof.jpg", io.BytesIO(photo), "image/jpeg")})


@pytest.fixture()
def loaded(client, db):
    market.store_report(db, "dti_srp", SRP_URL, dti_srp.parse_bulletin(SRP_PDF))
    market.reset_caches()


def queue(client, admin):
    return client.get("/api/v1/admin/proofs", headers=admin).json()


def basket(client):
    body = {"items": [{"query": "piatos cheese 85g"}], "city": "Cebu City"}
    return client.post("/api/v1/market/basket", json=body).json()["lines"][0]


def test_sharing_requires_an_account(client):
    assert send(client, {}).status_code == 401
    body = dict(name="Piatos", store_name="SM", latitude=10.3, longitude=123.9, city="Cebu City", price=30)
    assert client.post("/api/v1/market/shelf-prices", json=body).status_code == 401


def test_shoppers_can_register_and_sign_in(client):
    assert client.get("/api/v1/users/me", headers=shopper(client)).json()["roles"][0]["role"] == "shopper"
    login = client.post("/api/v1/auth/login", json={"email": "shopper@example.com", "password": "a-long-password"})
    assert login.status_code == 200


def test_duplicate_and_weak_registrations_are_refused(client):
    shopper(client)
    url = "/api/v1/auth/register"
    assert client.post(url, json=dict(email="SHOPPER@example.com", full_name="Again", password="a-long-password")).status_code == 409
    assert client.post(url, json=dict(email="x@example.com", full_name="Weak", password="short")).status_code == 422


@pytest.mark.parametrize("path", ["/api/v1/admin/overview", "/api/v1/admin/proofs", "/api/v1/admin/sync-jobs", "/api/v1/admin/users"])
def test_shoppers_never_reach_administration(client, path):
    assert client.get(path, headers=shopper(client)).status_code == 403


def test_proof_waits_for_review_and_is_not_published(client, admin):
    response = send(client, shopper(client))
    assert response.status_code == 201 and response.json()["status"] == "pending"
    assert basket(client)["status"] == "estimated"
    assert len(queue(client, admin)) == 1


def test_comparison_flags_a_price_far_from_the_official_one(client, db, admin, loaded):
    send(client, shopper(client), name="Bear Brand", price=500)
    check = queue(client, admin)[0]["comparison"]
    assert check["verdict"] == "needs_checking" and check["checks"][0]["price"] == 50 and not check["checks"][0]["ok"]


def test_comparison_accepts_a_price_near_the_official_one(client, admin, loaded):
    send(client, shopper(client), name="Bear Brand", price=52)
    assert queue(client, admin)[0]["comparison"]["verdict"] == "consistent"


def test_comparison_says_when_there_is_nothing_to_compare(client, admin):
    send(client, shopper(client))
    assert queue(client, admin)[0]["comparison"]["verdict"] == "no_reference"


def test_two_shoppers_agreeing_verifies_the_price(client, admin):
    send(client, shopper(client, "a@example.com"))
    second = send(client, shopper(client, "b@example.com"), price=46).json()
    assert second["status"] == "approved" and queue(client, admin) == []
    line = basket(client)
    assert line["status"] == "reported" and line["report"]["origin"] == "Verified by 2 shoppers"


def test_one_shopper_cannot_verify_their_own_price(client, admin):
    headers = shopper(client)
    send(client, headers)
    assert send(client, headers).json()["status"] == "pending"
    assert basket(client)["status"] == "estimated"


def test_shoppers_who_disagree_stay_in_review(client, admin):
    send(client, shopper(client, "a@example.com"))
    assert send(client, shopper(client, "b@example.com"), price=80).json()["status"] == "pending"


def test_agreement_needs_the_same_store(client, admin):
    send(client, shopper(client, "a@example.com"))
    assert send(client, shopper(client, "b@example.com"), store_name="Robinsons Cebu").json()["status"] == "pending"


def test_admin_approves_and_can_correct_the_price(client, admin):
    send(client, shopper(client))
    proof = queue(client, admin)[0]
    assert client.post(f'/api/v1/admin/proofs/{proof["id"]}/approve', json={"price": 44.5}, headers=admin).status_code == 200
    line = basket(client)
    assert line["unit_price"] == 44.5 and line["report"]["origin"] == "Verified with proof"


def test_approved_price_reaches_open_apps(client, admin):
    send(client, shopper(client))
    before = client.get("/api/v1/market/live").json()["version"]
    client.post(f'/api/v1/admin/proofs/{queue(client, admin)[0]["id"]}/approve', json={}, headers=admin)
    assert client.get("/api/v1/market/live").json()["version"] == before + 1


def test_rejecting_needs_a_reason_and_removes_the_photo(client, db, admin):
    headers = shopper(client)
    send(client, headers)
    proof = queue(client, admin)[0]
    assert client.post(f'/api/v1/admin/proofs/{proof["id"]}/reject', json={}, headers=admin).status_code == 422
    assert client.post(f'/api/v1/admin/proofs/{proof["id"]}/reject', json={"reason": "Blurry"}, headers=admin).status_code == 200
    assert db.proofs.find_one({"_id": proof["id"]})["photo"] is None
    mine = client.get("/api/v1/market/proofs/mine", headers=headers).json()
    assert mine[0]["status"] == "rejected" and mine[0]["reason"] == "Blurry"


def test_a_proof_cannot_be_decided_twice(client, admin):
    send(client, shopper(client))
    url = f'/api/v1/admin/proofs/{queue(client, admin)[0]["id"]}/approve'
    client.post(url, json={}, headers=admin)
    assert client.post(url, json={}, headers=admin).status_code == 409


def test_photos_are_admin_only_and_never_listed(client, admin, supervisor):
    headers = shopper(client)
    send(client, headers)
    proof = queue(client, admin)[0]
    url = f'/api/v1/admin/proofs/{proof["id"]}/photo'
    assert client.get(url).status_code == 401
    assert client.get(url, headers=headers).status_code == 403
    assert client.get(url, headers=supervisor).status_code == 403
    response = client.get(url, headers=admin)
    assert response.content == JPEG and response.headers["content-type"] == "image/jpeg"
    assert response.headers["x-content-type-options"] == "nosniff" and "no-store" in response.headers["cache-control"]
    assert "photo" not in client.get("/api/v1/market/proofs/mine", headers=headers).json()[0]


def test_shoppers_only_see_their_own_submissions(client):
    send(client, shopper(client, "a@example.com"))
    assert client.get("/api/v1/market/proofs/mine", headers=shopper(client, "b@example.com")).json() == []


@pytest.mark.parametrize("fake", [b"<svg onload=alert(1)>", b"<html>", b"%PDF-1.7", b""])
def test_only_real_images_are_accepted(client, fake):
    assert send(client, shopper(client), photo=fake).status_code == 422


def test_oversized_photos_are_refused(client):
    assert send(client, shopper(client), photo=JPEG + b"0" * proofs.MAX_PHOTO_BYTES).status_code == 413


def test_old_decided_photos_are_deleted(client, db, admin):
    send(client, shopper(client))
    proof = queue(client, admin)[0]
    client.post(f'/api/v1/admin/proofs/{proof["id"]}/approve', json={}, headers=admin)
    assert proofs.purge_photos(db) == 0
    db.proofs.update_one({"_id": proof["id"]}, {"$set": {"decided_at": utcnow() - timedelta(days=proofs.PHOTO_RETENTION_DAYS + 1)}})
    assert proofs.purge_photos(db) == 1 and db.proofs.find_one({"_id": proof["id"]})["photo"] is None


def test_pending_photos_are_kept_for_review(client, db):
    send(client, shopper(client))
    db.proofs.update_many({}, {"$set": {"created_at": utcnow() - timedelta(days=90)}})
    assert proofs.purge_photos(db) == 0


def test_admin_can_enter_a_price_by_hand(client, admin, supervisor):
    body = dict(retailer="SM Markets", product="Piatos Cheese", size="85g", price=44)
    assert client.post("/api/v1/admin/prices", json=body, headers=supervisor).status_code == 403
    assert client.post("/api/v1/admin/prices", json=body, headers=admin).status_code == 201
    line = basket(client)
    assert line["unit_price"] == 44 and "branches may differ" in line["report"]["origin"]


def test_mall_prices_appear_in_search(client, admin):
    body = dict(retailer="SM Markets", branch="Cebu", latitude=10.31, longitude=123.89, city="Cebu City", product="Jack 'n Jill Piatos Cheese", size="85g", price=44)
    client.post("/api/v1/admin/prices", json=body, headers=admin)
    found = client.get("/api/v1/market/suggest", params={"q": "piatos cheese", "city": "Cebu City"}).json()
    hit = next(r for r in found if r["size"] == "85g")
    assert hit["price"] == 44 and hit["price_label"] == "SM Markets Cebu"


def test_mall_agent_needs_a_connector_and_permission(client, admin):
    assert client.post("/api/v1/admin/sources/sm-markets/run", headers=admin).status_code == 409
    client.put("/api/v1/admin/sources/sm-markets/connector", headers=admin, json={"url": "https://api.sm.example/prices"})
    assert client.post("/api/v1/admin/sources/sm-markets/run", headers=admin).status_code == 409


def test_sm_markets_is_blocked_with_the_reason_on_record(client, admin):
    sm = next(s for s in client.get("/api/v1/admin/sources", headers=admin).json() if s["id"] == "sm-markets")
    assert sm["can_run"] is False and "permission" in sm["notes"]


def approved_proofs(db, user_id, count, status="approved"):
    for number in range(count):
        db.proofs.insert_one({"_id": f"{status}{number}", "user_id": user_id, "item_key": f"item {number}", "store_name": "SM Cebu", "city": "Cebu City", "status": status, "price_centavos": 100, "created_at": utcnow()})


def me(client, headers):
    return client.get("/api/v1/users/me", headers=headers).json()["id"]


def test_trusted_shopper_skips_the_queue_when_the_price_looks_right(client, db, admin, loaded):
    headers = shopper(client)
    approved_proofs(db, me(client, headers), proofs.TRUSTED_AFTER)
    result = send(client, headers, name="Bear Brand", price=52).json()
    assert result["status"] == "approved" and queue(client, admin) == []
    assert db.shelf_reports.find_one()["origin"] == "Verified trusted shopper"


def test_trusted_shopper_still_goes_to_review_when_the_price_looks_wrong(client, db, admin, loaded):
    headers = shopper(client)
    approved_proofs(db, me(client, headers), proofs.TRUSTED_AFTER)
    assert send(client, headers, name="Bear Brand", price=500).json()["status"] == "pending"


def test_too_many_rejections_lose_trust(client, db):
    headers = shopper(client)
    approved_proofs(db, me(client, headers), proofs.TRUSTED_AFTER)
    approved_proofs(db, me(client, headers), 2, "rejected")
    assert client.get("/api/v1/market/proofs/impact", headers=headers).json()["trusted"] is False


def test_impact_counts_verified_work_and_needs_an_account(client, db):
    assert client.get("/api/v1/market/proofs/impact").status_code == 401
    headers = shopper(client)
    approved_proofs(db, me(client, headers), 2)
    result = client.get("/api/v1/market/proofs/impact", headers=headers).json()
    assert (result["verified"], result["items"], result["stores"], result["to_trusted"]) == (2, 2, 1, 3)
