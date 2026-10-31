import base64
import hashlib
import hmac
import os
import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pymongo.database import Database

from .config import ACCESS_TOKEN_MINUTES, REFRESH_TOKEN_DAYS, SECRET_KEY
from .db import get_db, new_id, utcnow

ALGORITHM = "HS256"
SCRYPT = {"n": 2**14, "r": 8, "p": 1}
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    salt, digest = (base64.b64decode(part) for part in stored.split("$"))
    return hmac.compare_digest(hashlib.scrypt(password.encode(), salt=salt, **SCRYPT), digest)


def issue_token(user_id: str, kind: str) -> str:
    life = timedelta(minutes=ACCESS_TOKEN_MINUTES) if kind == "access" else timedelta(days=REFRESH_TOKEN_DAYS)
    return jwt.encode({"sub": user_id, "typ": kind, "exp": datetime.now(UTC) + life}, SECRET_KEY, ALGORITHM)


def read_token(token: str, kind: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    if payload.get("typ") != kind:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return payload["sub"]


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Database = Depends(get_db),
) -> dict:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    user = db.users.find_one({"_id": read_token(credentials.credentials, "access")})
    if user is None or user["status"] != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return user


def is_system_admin(user: dict) -> bool:
    return any(r["role"] == "system_admin" for r in user["roles"])


def org_scope(user: dict) -> list[str] | None:
    """Organizations the user may touch; None means every organization."""
    if is_system_admin(user):
        return None
    return [r["organization_id"] for r in user["roles"] if r.get("organization_id")]


def scope_filter(user: dict, field: str = "organization_id") -> dict:
    scope = org_scope(user)
    return {} if scope is None else {field: {"$in": scope}}


def require_org(user: dict, organization_id: str, roles: set[str] | None = None) -> None:
    """Authorize against the resource's organization, never one the client claims."""
    if is_system_admin(user):
        return
    allowed = any(
        r.get("organization_id") == organization_id and (roles is None or r["role"] in roles)
        for r in user["roles"]
    )
    if not allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized for this organization")


def staff_only(user: dict = Depends(current_user)) -> dict:
    """Shopper accounts share prices, but never reach administration."""
    if all(r["role"] == "shopper" for r in user["roles"]):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access required")
    return user


def require_system_admin(user: dict = Depends(current_user)) -> dict:
    if not is_system_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "System administrator role required")
    return user


def audit(db: Database, actor: dict | None, action: str, organization_id=None, detail=None) -> None:
    db.audit_logs.insert_one({
        "_id": new_id(),
        "actor_id": actor["_id"] if actor else None,
        "actor_email": actor["email"] if actor else None,
        "action": action,
        "organization_id": organization_id,
        "detail": detail,
        "created_at": utcnow(),
    })


class RateLimiter:
    """Sliding-window limiter per client IP. In-process only; use Redis once scaled out."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def __call__(self, request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with self.lock:
            window = self.hits[key]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= self.per_minute:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests")
            window.append(now)
