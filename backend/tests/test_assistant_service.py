import asyncio

from app.services import assistant


def test_suggest_ranks_specialist():
    assert assistant.suggest("knee and back pain for two weeks")[0]["id"] == "ortho"
    assert assistant.suggest("something strange")[0]["id"] == "general"
    ids = [s["id"] for s in assistant.suggest("my child has a rash")]
    assert "pediatric" in ids and "derm" in ids


def test_red_flags_get_fixed_safe_answers():
    assert "112" in assistant.red_flag("I have severe chest pain")["reply"]
    sh = assistant.red_flag("I want to end my life")
    assert "14416" in sh["reply"] and sh["emergency"]
    assert assistant.red_flag("mild headache since morning") is None


def test_rules_conversation_and_report(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    agent = assistant.BY_ID["general"]
    msgs = [{"role": "assistant", "content": assistant.greeting(agent, "fever")}]
    for t in ["since 3 days", "about 7/10", "no other symptoms, taking paracetamol", "nothing else"]:
        msgs.append({"role": "user", "content": t})
        reply, src = asyncio.run(assistant.reply(agent, msgs, t))
        assert src == "rules" and reply
        msgs.append({"role": "assistant", "content": reply})
    rep = asyncio.run(assistant.make_report(agent, msgs, False, notes="fever and cough"))
    assert rep["chief_complaint"] == "fever and cough" and rep["duration"] == "3 days"
    assert "paracetamol" in [m.lower() for m in rep["medicines_mentioned"]] and rep["severity"] in ("moderate", "severe")
    assert "not a diagnosis" in rep["disclaimer"]
