#!/usr/bin/env python3
"""Scan the project for hard-coded secrets before you push to GitHub:  python scripts/check_secrets.py
Exits 1 if it finds anything. Real secrets belong only in backend/.env (git-ignored) or in Render/Vercel environment variables."""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATTERNS = {
    "Google/Gemini API key": r"AIza[0-9A-Za-z_\-]{35}",
    "Anthropic key": r"sk-ant-[0-9A-Za-z_\-]{20,}",
    "OpenAI-style key": r"sk-[0-9A-Za-z]{32,}",
    "Brevo key": r"xkeysib-[0-9a-f]{20,}",
    "Twilio account SID": r"\bAC[0-9a-f]{32}\b",
    "Mongo URL with password": r"mongodb(?:\+srv)?://[^/\s:@<>\"']+:[^@\s<>\"']{3,}@",
    "Private key block": r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----",
    "GitHub token": r"gh[pousr]_[0-9A-Za-z]{30,}",
    "Slack/other bearer": r"xox[baprs]-[0-9A-Za-z\-]{10,}",
}
SKIP_DIRS = {"node_modules", "dist", ".git", "__pycache__", "data", "uploads", ".pytest_cache"}
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".ico", ".woff", ".woff2", ".onnx", ".pkl", ".joblib"}
bad = []
for d, dirs, files in os.walk(ROOT):
    dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
    for f in files:
        if f == ".env" or os.path.splitext(f)[1].lower() in SKIP_EXT or f == "check_secrets.py":
            continue
        path = os.path.join(d, f)
        try:
            text = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for name, pat in PATTERNS.items():
            for m in re.finditer(pat, text):
                if name.startswith("Mongo") and re.search(r"USER|PASSWORD|YOUR|<|\$\{|xxxx", m.group(0), re.I):
                    continue  # documentation placeholder
                bad.append((os.path.relpath(path, ROOT), name, m.group(0)[:6] + "…"))
if bad:
    print("POSSIBLE SECRETS IN CODE:")
    for p, n, v in bad:
        print(f"  {p}: {n} ({v})")
    print("Move them to backend/.env or your host's environment variables and rotate the key.")
gi = open(os.path.join(ROOT, ".gitignore")).read() if os.path.exists(os.path.join(ROOT, ".gitignore")) else ""
if not re.search(r"^\.env$", gi, re.M):
    print("WARNING: .gitignore does not ignore .env")
    bad.append(("", ".gitignore", ""))
try:
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "backend/.env"], cwd=ROOT, capture_output=True, text=True)
    if tracked.returncode == 0:
        print("WARNING: backend/.env is tracked by git. Run: git rm --cached backend/.env  (and rotate every key in it)")
        bad.append(("backend/.env", "tracked", ""))
except FileNotFoundError:
    pass
print("OK: no hard-coded secrets found." if not bad else "FAILED")
sys.exit(1 if bad else 0)
