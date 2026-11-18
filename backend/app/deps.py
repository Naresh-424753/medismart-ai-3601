from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt

from .db import get_db
from .config import settings
from .security import decode_token
from .services import llm_guard

bearer = HTTPBearer(auto_error=False)


# Per-user request budget per minute, by role. A stolen token or a runaway script cannot hammer the API; normal screens use far less.
ROLE_LIMITS = {"patient": 240, "doctor": 400, "nurse": 400, "hospital": 400, "lab": 400, "pharmacist": 400, "blood_bank": 400, "ambulance": 600,
               "admin": 600, "super_admin": 600}
_user_hits: dict = {}


def user_rate_ok(user: dict, now_s: float | None = None) -> bool:
    t = now_s if now_s is not None else __import__("time").time()
    q = _user_hits.setdefault(user["id"], __import__("collections").deque())
    while q and q[0] < t - 60:
        q.popleft()
    if len(q) >= ROLE_LIMITS.get(user["role"], 200):
        return False
    q.append(t)
    return True


async def current_user(request: Request, cred: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    if not cred:
        raise HTTPException(401, "Not authenticated")
    user = await user_from_token(cred.credentials)
    allow = settings.ADMIN_IP_ALLOWLIST
    if allow and user["role"] in ("admin", "super_admin") and client_ip(request) not in allow:
        raise HTTPException(403, "Admin access is not allowed from this network")
    if not user_rate_ok(user):
        raise HTTPException(429, "Too many requests from this account. Please slow down for a minute.")
    llm_guard.set_known(user)  # this user's own name/email/phone are masked in any AI prompt of this request
    return user


async def user_from_token(token: str) -> dict:
    db = get_db()
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    if await db.revoked_tokens.find_one({"jti": payload["jti"]}):
        raise HTTPException(401, "Session ended - please log in again")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
    if not user or user.get("status") == "suspended":
        raise HTTPException(401, "Account unavailable")
    # "log out from all devices": every token issued before this moment is dead
    if payload.get("iat", 0) < user.get("sessions_valid_after", 0):
        raise HTTPException(401, "Session ended - please log in again")
    user["_jti"] = payload["jti"]
    return user


def require_roles(*roles: str):
    async def dep(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles and user["role"] != "super_admin":
            raise HTTPException(403, "You do not have access to this resource")
        return user
    return dep


def client_ip(request: Request) -> str:
    """Real client IP. X-Forwarded-For is read from the right, skipping only the proxies we trust, so it cannot be spoofed by the caller."""
    hops = settings.TRUSTED_PROXY_HOPS
    fwd = request.headers.get("x-forwarded-for")
    if hops > 0 and fwd:
        parts = [p.strip() for p in fwd.split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    return request.client.host if request.client else ""
