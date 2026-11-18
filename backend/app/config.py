import os
import re
import secrets
from pathlib import Path


def _load_env_file() -> None:
    """Reads backend/.env into the environment (real environment variables win). Without this, .env would be silently ignored."""
    f = Path(__file__).resolve().parents[1] / ".env"
    if not f.is_file():
        return
    for line in f.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if v[:1] in "\"'" and v[-1:] == v[:1] and len(v) >= 2:
            v = v[1:-1]
        elif " #" in v:  # inline comment (values with # must be quoted)
            v = v.split(" #", 1)[0].strip()
        os.environ.setdefault(k.strip(), v)


_load_env_file()


def _b(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes"}


def _dev_secret() -> str:
    if not _b("DEV_MODE", "1"):
        return ""
    f = os.path.join(os.getenv("DEV_SECRET_DIR", "data"), ".dev_secret")
    try:
        return open(f).read().strip() or (_ for _ in ()).throw(OSError)
    except OSError:
        v = secrets.token_urlsafe(48)
        try:
            os.makedirs(os.path.dirname(f), exist_ok=True)
            with open(f, "w") as fh:
                fh.write(v)
            os.chmod(f, 0o600)
        except OSError:
            pass
        return v


class Settings:
    APP_NAME = "MediSmart AI 360"
    # "mock" -> in-memory database (demo/tests, data is lost on restart)
    MONGO_URL = os.getenv("MONGO_URL", "mock")
    DB_NAME = os.getenv("DB_NAME", "medismart")
    # If MongoDB cannot be reached at start, run on the in-memory database instead of refusing to start (data is lost on restart). Dev only.
    MONGO_FALLBACK = _b("MONGO_FALLBACK", "0")
    # No secret is stored in code. If JWT_SECRET is unset, DEV_MODE generates one and keeps it in data/.dev_secret (git-ignored);
    # DEV_MODE=0 refuses to start without it.
    JWT_SECRET = os.getenv("JWT_SECRET") or _dev_secret()
    JWT_EXPIRE_MIN = int(os.getenv("JWT_EXPIRE_MIN", "120"))
    # DEV_MODE returns OTPs in API responses so you can demo without SMS/email. NEVER enable in production.
    DEV_MODE = _b("DEV_MODE", "1")
    CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
    UPLOAD_DIR = os.getenv("UPLOAD_DIR", "data/uploads")
    # Set to a Google Cloud Storage bucket name to keep (encrypted) uploads there instead of on local disk.
    GCS_BUCKET = os.getenv("GCS_BUCKET", "")
    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))
    # Fernet key (base64 urlsafe 32 bytes) for encrypting uploaded documents at rest
    DATA_KEY = os.getenv("DATA_KEY", "")
    # How many reverse proxies sit in front of the API (Render = 1; Cloudflare + Render = 2). The client IP is taken from X-Forwarded-For
    # counting from the RIGHT, so a caller cannot fake it by sending their own header. 0 = ignore the header (local dev without a proxy).
    TRUSTED_PROXY_HOPS = int(os.getenv("TRUSTED_PROXY_HOPS", "1"))
    # REAL_PATIENT_DATA=1 makes the API refuse to start unless the configuration is production-safe (see production_problems()).
    REAL_PATIENT_DATA = _b("REAL_PATIENT_DATA", "0")
    # Optional: comma-separated IPs allowed to use admin / super_admin accounts (empty = no restriction). Example: 203.0.113.5,198.51.100.7
    ADMIN_IP_ALLOWLIST = [i.strip() for i in os.getenv("ADMIN_IP_ALLOWLIST", "").split(",") if i.strip()]
    # Idle time (minutes) after which the web app logs the user out automatically
    IDLE_LOGOUT_MIN = int(os.getenv("IDLE_LOGOUT_MIN", "15"))
    # Credentials are never hard-coded: set them in backend/.env, or create the admin with `python create_admin.py`.
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")  # empty -> a random one-time password is generated and printed once
    DEMO_EMAIL_DOMAIN = os.getenv("DEMO_EMAIL_DOMAIN", "")  # needed only when SEED_DEMO=1
    DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "")  # empty -> random, printed once
    SEED_DEMO = _b("SEED_DEMO", "1")
    APP_TZ = os.getenv("APP_TZ", "Asia/Kolkata")
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASS = os.getenv("SMTP_PASS", "")
    SMTP_FROM = os.getenv("SMTP_FROM", "")
    # HTTPS email API (Brevo). Use this on hosts that block SMTP ports, such as Render's free plan. SMTP_FROM must be a sender verified in Brevo.
    BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
    # Shown on the public Contact page (optional)
    SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "")
    SUPPORT_PHONE = os.getenv("SUPPORT_PHONE", "")
    # WhatsApp number with country code, digits only (e.g. 919876543210). Shows a "Chat on WhatsApp" button.
    SUPPORT_WHATSAPP = re.sub(r"\D", "", os.getenv("SUPPORT_WHATSAPP", ""))
    TWILIO_SID = os.getenv("TWILIO_SID", "")
    TWILIO_TOKEN = os.getenv("TWILIO_TOKEN", "")
    TWILIO_SMS_FROM = os.getenv("TWILIO_SMS_FROM", "")
    TWILIO_WA_FROM = os.getenv("TWILIO_WA_FROM", "")  # e.g. whatsapp:+14155238886
    DEFAULT_COUNTRY_CODE = os.getenv("DEFAULT_COUNTRY_CODE", "91")
    CLINIC_NAME = os.getenv("CLINIC_NAME", "MediSmart AI 360 Clinic")
    CLINIC_ADDRESS = os.getenv("CLINIC_ADDRESS", "")
    CLINIC_PHONE = os.getenv("CLINIC_PHONE", "")
    CLINIC_REG_NO = os.getenv("CLINIC_REG_NO", "")
    PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "")  # used for the verification link/QR on prescription PDFs
    # Telemedicine (WebRTC). Calls work peer-to-peer with STUN; add a TURN server for users behind strict NAT/firewalls.
    STUN_URLS = [u.strip() for u in os.getenv("STUN_URLS", "stun:stun.l.google.com:19302").split(",") if u.strip()]
    TURN_URL = os.getenv("TURN_URL", "")
    TURN_USERNAME = os.getenv("TURN_USERNAME", "")
    TURN_CREDENTIAL = os.getenv("TURN_CREDENTIAL", "")
    TELE_ANYTIME = _b("TELE_ANYTIME", "1")  # 1 = allow joining at any time (demo); 0 = only from 15 min before to 90 min after the slot
    # Server-side speech-to-text for regional languages (all optional; without them the browser's own speech recognition is used)
    STT_PROVIDER = os.getenv("STT_PROVIDER", "auto")  # auto | whisper | bhashini
    WHISPER_API_KEY = os.getenv("WHISPER_API_KEY", "")
    WHISPER_BASE_URL = os.getenv("WHISPER_BASE_URL", "https://api.openai.com/v1")
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
    BHASHINI_USER_ID = os.getenv("BHASHINI_USER_ID", "")
    BHASHINI_API_KEY = os.getenv("BHASHINI_API_KEY", "")
    BHASHINI_PIPELINE_ID = os.getenv("BHASHINI_PIPELINE_ID", "64392f96daac500b55c543cd")


settings = Settings()


def production_problems() -> list[str]:
    """Everything that makes the current configuration unsafe for real patient data. Empty list = OK."""
    st, out = settings, []
    if st.DEV_MODE:
        out.append("DEV_MODE must be 0")
    if st.MONGO_URL == "mock" or st.MONGO_FALLBACK:
        out.append("a real MongoDB is required (MONGO_URL not 'mock', MONGO_FALLBACK=0)")
    if len(st.JWT_SECRET) < 32:
        out.append("JWT_SECRET must be at least 32 random characters")
    if len(st.DATA_KEY) < 32:
        out.append("DATA_KEY must be set to at least 32 random characters (and backed up)")
    if st.SEED_DEMO:
        out.append("SEED_DEMO must be 0 (no demo accounts)")
    if not st.CORS_ORIGINS or any(o == "*" or "localhost" in o or "127.0.0.1" in o for o in st.CORS_ORIGINS):
        out.append("CORS_ORIGINS must list only your real https frontend URL")
    elif any(not o.startswith("https://") for o in st.CORS_ORIGINS):
        out.append("CORS_ORIGINS must use https")
    if not (os.getenv("BREVO_API_KEY") or os.getenv("SMTP_HOST")):
        out.append("e-mail (BREVO_API_KEY or SMTP_*) must be configured so OTP codes can reach users")
    if st.TRUSTED_PROXY_HOPS < 1:
        out.append("TRUSTED_PROXY_HOPS must be >= 1 behind Render/Cloudflare (else the client IP is the proxy's)")
    try:
        import argon2  # noqa: F401
    except ImportError:
        out.append("argon2-cffi must be installed (Argon2id password hashing)")
    return out
