"""Minimal, strict WebAuthn (passkey) verification: fingerprint / face / device-PIN login without any password.

The browser/OS does the biometric check and keeps the private key; the server stores only the public key.
Implemented here (no third-party webauthn package): CBOR decoding, authenticator-data parsing, ES256 + RS256 public keys,
signature verification, challenge/origin/RP-ID checks, mandatory user verification and sign-counter clone detection.
Attestation statements are NOT verified (we ask for attestation "none"): we do not care which device model it is, only that
this key belongs to this account and was created after a biometric/PIN check."""
from __future__ import annotations

import base64
import hashlib
import json
import struct

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

FLAG_UP, FLAG_UV, FLAG_AT = 0x01, 0x04, 0x40


class WebAuthnError(ValueError):
    pass


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def unb64u(s: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    except Exception:
        raise WebAuthnError("Malformed data")


# ----------------------------------------------------------------------------- CBOR (definite lengths only, as used by CTAP2)
def _cbor(data: bytes, i: int, depth: int = 0):
    if depth > 8 or i >= len(data):
        raise WebAuthnError("Bad CBOR")
    ib = data[i]; i += 1
    major, info = ib >> 5, ib & 31
    if info < 24:
        n = info
    elif info in (24, 25, 26, 27):
        size = {24: 1, 25: 2, 26: 4, 27: 8}[info]
        if i + size > len(data):
            raise WebAuthnError("Bad CBOR")
        n = int.from_bytes(data[i:i + size], "big"); i += size
    else:
        raise WebAuthnError("Unsupported CBOR")
    if major == 0:
        return n, i
    if major == 1:
        return -1 - n, i
    if major in (2, 3):
        if i + n > len(data):
            raise WebAuthnError("Bad CBOR")
        raw = data[i:i + n]
        return (raw if major == 2 else raw.decode("utf-8")), i + n
    if major == 4:
        out = []
        for _ in range(n):
            v, i = _cbor(data, i, depth + 1); out.append(v)
        return out, i
    if major == 5:
        out = {}
        for _ in range(n):
            k, i = _cbor(data, i, depth + 1); v, i = _cbor(data, i, depth + 1); out[k] = v
        return out, i
    if major == 7 and info in (20, 21, 22):
        return {20: False, 21: True, 22: None}[info], i
    raise WebAuthnError("Unsupported CBOR")


def cbor_decode(data: bytes):
    v, i = _cbor(data, 0)
    return v, i


# ----------------------------------------------------------------------------- authenticator data
def parse_auth_data(ad: bytes) -> dict:
    if len(ad) < 37:
        raise WebAuthnError("Authenticator data too short")
    out = {"rp_id_hash": ad[:32], "flags": ad[32], "sign_count": struct.unpack(">I", ad[33:37])[0], "cred_id": None, "cose": None}
    if out["flags"] & FLAG_AT:
        if len(ad) < 55:
            raise WebAuthnError("Authenticator data too short")
        n = struct.unpack(">H", ad[53:55])[0]
        if n == 0 or n > 1023 or len(ad) < 55 + n:
            raise WebAuthnError("Bad credential id")
        out["cred_id"] = ad[55:55 + n]
        key, _ = cbor_decode(ad[55 + n:])
        out["cose"] = key
    return out


def cose_to_pem(key: dict) -> tuple[str, int]:
    """COSE key -> (PEM public key, COSE alg). Supports ES256 (P-256) and RS256."""
    if not isinstance(key, dict):
        raise WebAuthnError("Bad public key")
    kty, alg = key.get(1), key.get(3)
    if kty == 2 and alg == -7 and key.get(-1) == 1:
        x, y = key.get(-2), key.get(-3)
        if not (isinstance(x, bytes) and isinstance(y, bytes) and len(x) == 32 and len(y) == 32):
            raise WebAuthnError("Bad EC key")
        try:
            pub = ec.EllipticCurvePublicNumbers(int.from_bytes(x, "big"), int.from_bytes(y, "big"), ec.SECP256R1()).public_key()
        except ValueError:
            raise WebAuthnError("Bad EC key")
    elif kty == 3 and alg == -257:
        n, e = key.get(-1), key.get(-2)
        if not (isinstance(n, bytes) and isinstance(e, bytes)) or len(n) < 256:
            raise WebAuthnError("Bad RSA key")
        pub = rsa.RSAPublicNumbers(int.from_bytes(e, "big"), int.from_bytes(n, "big")).public_key()
    else:
        raise WebAuthnError("Unsupported key type. This device must support ES256 or RS256.")
    return pub.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode(), alg


# ----------------------------------------------------------------------------- shared checks
def _client_data(raw_b64: str, expected_type: str, challenge: str, origin: str) -> bytes:
    raw = unb64u(raw_b64)
    try:
        cd = json.loads(raw)
    except Exception:
        raise WebAuthnError("Malformed client data")
    if cd.get("type") != expected_type:
        raise WebAuthnError("Wrong request type")
    if cd.get("challenge") != challenge:
        raise WebAuthnError("Challenge mismatch")
    if cd.get("origin") != origin:
        raise WebAuthnError("Origin mismatch")
    if cd.get("crossOrigin"):
        raise WebAuthnError("Cross-origin use is not allowed")
    return raw


def _check_auth_data(ad: dict, rp_id: str) -> None:
    if ad["rp_id_hash"] != hashlib.sha256(rp_id.encode()).digest():
        raise WebAuthnError("This passkey belongs to a different website")
    if not ad["flags"] & FLAG_UP:
        raise WebAuthnError("User presence missing")
    if not ad["flags"] & FLAG_UV:
        raise WebAuthnError("Fingerprint / face / PIN check was not performed on the device")


def verify_registration(credential: dict, challenge: str, origin: str, rp_id: str) -> dict:
    """Returns {credential_id, public_key_pem, alg, sign_count}. Raises WebAuthnError."""
    if not isinstance(credential, dict) or credential.get("type") != "public-key":
        raise WebAuthnError("Bad credential")
    resp = credential.get("response") or {}
    _client_data(resp.get("clientDataJSON", ""), "webauthn.create", challenge, origin)
    att, used = cbor_decode(unb64u(resp.get("attestationObject", "")))
    if not isinstance(att, dict) or not isinstance(att.get("authData"), bytes):
        raise WebAuthnError("Bad attestation")
    ad = parse_auth_data(att["authData"])
    _check_auth_data(ad, rp_id)
    if not ad["flags"] & FLAG_AT or not ad["cred_id"]:
        raise WebAuthnError("No credential in response")
    if ad["cred_id"] != unb64u(credential.get("rawId", "")):
        raise WebAuthnError("Credential id mismatch")
    pem, alg = cose_to_pem(ad["cose"])
    return {"credential_id": b64u(ad["cred_id"]), "public_key_pem": pem, "alg": alg, "sign_count": ad["sign_count"]}


def verify_assertion(credential: dict, challenge: str, origin: str, rp_id: str, stored: dict) -> int:
    """Verifies a login signature against the stored public key. Returns the new sign counter. Raises WebAuthnError."""
    if not isinstance(credential, dict) or credential.get("type") != "public-key":
        raise WebAuthnError("Bad credential")
    resp = credential.get("response") or {}
    cdj = _client_data(resp.get("clientDataJSON", ""), "webauthn.get", challenge, origin)
    ad_raw = unb64u(resp.get("authenticatorData", ""))
    ad = parse_auth_data(ad_raw)
    _check_auth_data(ad, rp_id)
    signed = ad_raw + hashlib.sha256(cdj).digest()
    pub = serialization.load_pem_public_key(stored["public_key_pem"].encode())
    sig = unb64u(resp.get("signature", ""))
    try:
        if stored["alg"] == -7:
            pub.verify(sig, signed, ec.ECDSA(hashes.SHA256()))
        elif stored["alg"] == -257:
            pub.verify(sig, signed, padding.PKCS1v15(), hashes.SHA256())
        else:
            raise WebAuthnError("Unsupported algorithm")
    except InvalidSignature:
        raise WebAuthnError("Signature check failed")
    old, new = stored.get("sign_count", 0), ad["sign_count"]
    if (old or new) and new <= old:
        raise WebAuthnError("This passkey looks cloned (counter went backwards). It was refused.")
    return new
