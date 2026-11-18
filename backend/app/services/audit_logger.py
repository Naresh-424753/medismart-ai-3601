"""Tamper-proof PHI access trail (who touched which patient's data, when).

Rows go into the same SHA-256 hash chain as every other audit entry (common.audit), so editing or deleting a past row breaks all later hashes
(verify with GET /admin/audit-logs/verify). The patient id is written into the hashed `detail` as `subject=<id>|...`, so it cannot be
changed afterwards without breaking the chain. Patients read their own trail at GET /privacy/access-log; admins review at GET /admin/phi-access.
"""
import re

from ..common import audit


async def phi_event(db, actor: dict, patient_id: str, action: str, resource: str = "", ip: str = ""):
    await audit(db, actor["id"], action, f"subject={patient_id}|{resource}", ip, actor.get("role", ""))


async def trail_for(db, patient_id: str, limit: int = 200) -> list[dict]:
    rows = await db.audit_logs.find({"detail": {"$regex": "^subject=" + re.escape(patient_id) + r"\|"}}, {"_id": 0}).sort("seq", -1).limit(limit).to_list(limit)
    return rows
