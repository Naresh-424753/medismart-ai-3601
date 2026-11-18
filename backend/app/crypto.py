"""Encryption at rest for uploaded medical documents and sensitive fields.

New data: AES-256-GCM (authenticated). Old Fernet blobs are still readable, so nothing already stored breaks.
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import settings

_V2 = b"v2:"


def _key_bytes() -> bytes:
    key = settings.DATA_KEY
    if not key:
        # Dev fallback: derive a key from the JWT secret. Set DATA_KEY in production.
        return hashlib.sha256(settings.JWT_SECRET.encode()).digest()
    return hashlib.sha256(key.encode()).digest()  # always 32 bytes -> AES-256


def _fernet() -> Fernet:
    key = settings.DATA_KEY
    if not key:
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.JWT_SECRET.encode()).digest()).decode()
    return Fernet(key.encode())


def encrypt(data: bytes) -> bytes:
    nonce = os.urandom(12)
    return _V2 + base64.urlsafe_b64encode(nonce + AESGCM(_key_bytes()).encrypt(nonce, data, None))


def decrypt(data: bytes) -> bytes:
    if data.startswith(_V2):
        raw = base64.urlsafe_b64decode(data[len(_V2):])
        return AESGCM(_key_bytes()).decrypt(raw[:12], raw[12:], None)
    try:
        return _fernet().decrypt(data)  # legacy blobs
    except InvalidToken:
        raise
