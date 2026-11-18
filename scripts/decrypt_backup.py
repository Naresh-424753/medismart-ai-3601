"""Decrypt a backup file written by POST /admin/backup.   Usage (from backend/):  python ../scripts/decrypt_backup.py data/backups/<time>/users.json.enc > users.json
Needs the same DATA_KEY (or JWT_SECRET if DATA_KEY was empty) in the environment / backend/.env. Keep the output private."""
import sys

sys.path.insert(0, ".")
from app.crypto import decrypt  # noqa: E402

sys.stdout.buffer.write(decrypt(open(sys.argv[1], "rb").read()))
