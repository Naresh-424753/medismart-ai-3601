"""AI doctor agents (text + browser voice). Sessions and reports belong to the logged-in user."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..common import new_id, now
from ..db import get_db
from ..deps import current_user
from ..services import assistant, languages

router = APIRouter(prefix="/assistant", tags=["ai-doctors"])
MAX_USER_MESSAGES = 30


class SuggestIn(BaseModel):
    notes: str = Field(min_length=3, max_length=1000)


class StartIn(BaseModel):
    agent_id: str
    notes: str = Field(default="", max_length=1000)
    lang: str | None = None


class MsgIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


def _public(s: dict, full: bool = True) -> dict:
    out = {k: s.get(k) for k in ("id", "agent_id", "agent", "notes", "created", "updated", "ended", "emergency", "lang")}
    out["icon"] = (assistant.BY_ID.get(s.get("agent_id")) or {}).get("icon", "heart")
    out["messages_count"] = len(s.get("messages", []))
    out["has_report"] = bool(s.get("report"))
    if full:
        out["messages"] = s.get("messages", [])
        out["report"] = s.get("report")
    return out


async def _own(sid: str, user: dict) -> dict:
    s = await get_db().assistant_sessions.find_one({"id": sid, "user_id": user["id"]}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Session not found")
    return s


@router.get("/agents")
async def agents(user: dict = Depends(current_user)):
    return assistant.agents_public()


@router.post("/suggest")
async def suggest(body: SuggestIn, user: dict = Depends(current_user)):
    rf = assistant.red_flag(body.notes)
    return {"suggestions": assistant.suggest(body.notes), "emergency": rf["reply"] if rf else None}


@router.post("/sessions", status_code=201)
async def start(body: StartIn, user: dict = Depends(current_user)):
    agent = assistant.BY_ID.get(body.agent_id)
    if not agent:
        raise HTTPException(404, "Unknown AI doctor")
    lc = languages.code(body.lang)
    rf = assistant.red_flag(body.notes, lc) if body.notes.strip() else None
    first = rf["reply"] if rf else assistant.greeting(agent, body.notes)
    s = {"id": new_id(), "user_id": user["id"], "agent_id": agent["id"], "agent": agent["specialist"], "notes": body.notes.strip(), "lang": lc,
         "messages": [{"role": "assistant", "content": first, "ts": now()}], "emergency": bool(rf), "report": None, "ended": False, "created": now(), "updated": now()}
    await get_db().assistant_sessions.insert_one(dict(s))
    return _public(s)


@router.post("/sessions/{sid}/message")
async def message(sid: str, body: MsgIn, user: dict = Depends(current_user)):
    db = get_db()
    s = await _own(sid, user)
    if s.get("ended"):
        raise HTTPException(400, "This consultation has ended. Start a new one.")
    text = body.message.strip()
    msgs = s["messages"] + [{"role": "user", "content": text, "ts": now()}]
    if sum(1 for m in msgs if m["role"] == "user") > MAX_USER_MESSAGES:
        raise HTTPException(400, "Message limit reached for this consultation. Please end it and get your report.")
    agent = assistant.BY_ID[s["agent_id"]]
    rf = assistant.red_flag(text, s.get("lang"))
    if rf:  # fixed safe answer, never sent to the LLM
        reply, source, emergency = rf["reply"], "safety", True
    else:
        reply, source = await assistant.reply(agent, msgs, text, languages.LANGS[languages.code(s.get("lang"))]["name"])
        emergency = bool(s.get("emergency"))
    msgs.append({"role": "assistant", "content": reply, "ts": now(), "source": source})
    await db.assistant_sessions.update_one({"id": sid}, {"$set": {"messages": msgs, "updated": now(), "emergency": emergency}})
    return {"reply": reply, "source": source, "emergency": bool(rf), "remaining": MAX_USER_MESSAGES - sum(1 for m in msgs if m["role"] == "user")}


@router.post("/sessions/{sid}/report")
async def report(sid: str, user: dict = Depends(current_user)):
    db = get_db()
    s = await _own(sid, user)
    if not any(m["role"] == "user" for m in s["messages"]):
        raise HTTPException(400, "Talk to the AI doctor first, then generate the report.")
    rep = await assistant.make_report(assistant.BY_ID[s["agent_id"]], s["messages"], bool(s.get("emergency")), languages.LANGS[languages.code(s.get("lang"))]["name"], s.get("notes", ""))
    rep["generated"] = now()
    rep["patient"] = user.get("name") or "Patient"
    rep["consulted_on"] = s["created"]
    rep["agent"] = s["agent"]
    await db.assistant_sessions.update_one({"id": sid}, {"$set": {"report": rep, "ended": True, "updated": now()}})
    return rep


@router.get("/sessions")
async def history(user: dict = Depends(current_user)):
    docs = await get_db().assistant_sessions.find({"user_id": user["id"]}, {"_id": 0}).sort("updated", -1).limit(50).to_list(50)
    return [_public(d, full=False) for d in docs]


@router.get("/sessions/{sid}")
async def get_session(sid: str, user: dict = Depends(current_user)):
    return _public(await _own(sid, user))


@router.delete("/sessions/{sid}")
async def delete_session(sid: str, user: dict = Depends(current_user)):
    await _own(sid, user)
    await get_db().assistant_sessions.delete_one({"id": sid, "user_id": user["id"]})
    return {"deleted": sid}
