import base64
import hashlib
import hmac
import os
import re
import secrets
import time
import uuid

import jwt

from .config import settings


try:  # Argon2id is used when argon2-cffi is installed (it is in requirements.txt); otherwise scrypt is the fallback
    from argon2 import PasswordHasher
    from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
    _argon = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)  # 64 MiB, OWASP-grade
except ImportError:  # pragma: no cover - depends on the environment
    _argon = None


def _scrypt(pw: str, salt: bytes) -> bytes:
    return hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)


def hash_password(pw: str) -> str:
    if _argon:
        return _argon.hash(pw)
    salt = os.urandom(16)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(_scrypt(pw, salt)).decode()


def verify_password(pw: str, stored: str) -> bool:
    try:
        if stored.startswith("$argon2"):
            return bool(_argon) and _argon.verify(stored, pw)
        _, s, h = stored.split("$")
        return hmac.compare_digest(_scrypt(pw, base64.b64decode(s)), base64.b64decode(h))
    except Exception:
        return False


def needs_rehash(stored: str) -> bool:
    """True when a stored hash should be upgraded after a successful login (scrypt -> Argon2id, or weaker Argon2 params)."""
    if not _argon:
        return False
    return not stored.startswith("$argon2id") or _argon.check_needs_rehash(stored)


_COMMON = {"password", "password1", "password123", "passw0rd", "qwerty123", "qwertyuiop", "letmein123", "welcome123", "admin123", "iloveyou1",
           "abc12345", "abcd1234", "12345678", "123456789", "1234567890", "medismart", "medismart123", "india123", "test1234", "changeme"}


def password_problem(pw: str) -> str | None:
    if len(pw) < 10:
        return "Password must be at least 10 characters"
    if len(pw) > 128:
        return "Password is too long (max 128 characters)"
    if not (re.search(r"[a-z]", pw) and re.search(r"[A-Z]", pw) and re.search(r"\d", pw) and re.search(r"[^A-Za-z0-9]", pw)):
        return "Password needs an uppercase letter, a lowercase letter, a digit and a symbol"
    low = re.sub(r"[^a-z0-9]", "", pw.lower())
    if any(c in low for c in _COMMON) or re.search(r"(.)\1{3,}", pw):
        return "Password is too common or repetitive - choose something less guessable"
    return None


def create_token(user_id: str, role: str) -> tuple[str, str]:
    jti = uuid.uuid4().hex
    payload = {"sub": user_id, "role": role, "jti": jti, "iat": int(time.time()), "exp": int(time.time()) + settings.JWT_EXPIRE_MIN * 60}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256"), jti


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])


def new_otp() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def hash_otp(email: str, purpose: str, otp: str) -> str:
    return hmac.new(settings.JWT_SECRET.encode(), f"{email}|{purpose}|{otp}".encode(), hashlib.sha256).hexdigest()


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def sign(value: str) -> str:
    return hmac.new(settings.JWT_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()[:16]
