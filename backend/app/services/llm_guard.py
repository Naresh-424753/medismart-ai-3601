"""PII redaction for everything that leaves the server towards an external LLM (Gemini / Anthropic).

Before a prompt is sent, identifiers are replaced by placeholders such as [PHONE_1] or [NAME_1]. The model only ever sees placeholders;
when the answer comes back, placeholders are swapped back locally so the user still reads a natural reply.

What is masked: e-mail, UPI id, Indian phone numbers, Aadhaar-like 12-digit numbers, PAN, card-like numbers, "DOB: ..." values, PIN codes,
"address: ..." text, "my name is ..." phrases, and the logged-in user's own name / e-mail / phone wherever they appear (current_user feeds these in).
Honest limit: free-text names and addresses cannot be detected perfectly by rules. This is a strong first filter, not a guarantee; keep the
"don't paste identifying details" notice in the UI and use an LLM provider under a data-processing agreement for real patient data.
"""
import re
from contextvars import ContextVar

_known: ContextVar[tuple] = ContextVar("pii_known", default=())
stats = {"prompts": 0, "redactions": 0}

# (label, regex) applied in this order; names/known identifiers are handled separately
_RULES = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("UPI", re.compile(r"(?<![\w@])[\w.\-]{2,}@[a-z]{2,15}\b", re.I)),
    ("CARD", re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")),
    ("AADHAAR", re.compile(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)")),
    ("PHONE", re.compile(r"(?<![\d])(?:\+?91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("DOB", re.compile(r"(?i)\b(?:dob|d\.o\.b|date of birth|born on|janm tithi)\b\W{0,3}(?:\d{1,2}[/\-. ]\d{1,2}[/\-. ]\d{2,4}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\.?,?\s+\d{2,4}|[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4}|\d{4})")),
    ("PIN", re.compile(r"(?i)\b(?:pin(?:code)?|zip(?:code)?)\W{0,3}\d{6}\b")),
    ("ADDRESS", re.compile(r"(?i)\b(?:address|resident of|residing at|lives at|living at|mera pata|ghar ka pata)\b\s*(?:is|hai|:|-)?\s*[^\n.]{5,140}")),
    ("NAME", re.compile(r"(?i:\b(?:my name is|mera naam|my name's|name\s*:)\s*(?:is\s+)?)[A-Za-z][a-z'-]{1,20}(?:\s+[A-Z][a-z'-]{1,20}){0,2}")),
]


def set_known(user: dict | None):
    """Called once per request after authentication: the user's own identifiers are always masked."""
    vals = []
    if user:
        name = (user.get("name") or "").strip()
        if len(name) >= 3:
            vals.append(("NAME", name))
            vals += [("NAME", p) for p in re.split(r"\s+", name) if len(p) >= 3]
        for k, lab in (("email", "EMAIL"), ("phone", "PHONE")):
            if user.get(k):
                vals.append((lab, str(user[k])))
    vals.sort(key=lambda x: -len(x[1]))  # longest first so "Naresh Kumar" is replaced before "Naresh"
    _known.set(tuple(vals))


def scrub(text: str, mapping: dict) -> str:
    if not text:
        return text
    counts: dict[str, int] = {}

    def ph(label: str, original: str) -> str:
        for k, v in mapping.items():  # same value -> same placeholder, so the model can still follow the conversation
            if v == original and k.startswith(f"[{label}_"):
                return k
        counts[label] = sum(1 for k in mapping if k.startswith(f"[{label}_")) + 1
        key = f"[{label}_{counts[label]}]"
        mapping[key] = original
        stats["redactions"] += 1
        return key

    for label, rx in _RULES:
        text = rx.sub(lambda m, l=label: ph(l, m.group(0)), text)
    for label, val in _known.get():
        text = re.sub(rf"(?<!\w){re.escape(val)}(?!\w)", lambda m, l=label: ph(l, m.group(0)), text, flags=re.I)
    return text


def protect(system: str, messages: list[dict]):
    """-> (system, messages, restore). Send the first two to the LLM, pass its answer through restore()."""
    mapping: dict[str, str] = {}
    stats["prompts"] += 1
    s = scrub(system, mapping)
    msgs = [{**m, "content": scrub(m.get("content", ""), mapping)} for m in messages]

    def restore(answer):
        if not answer or not mapping:
            return answer
        for k, v in mapping.items():
            answer = answer.replace(k, v)
        return answer
    return s, msgs, restore


def protect_text(text: str):
    mapping: dict[str, str] = {}
    stats["prompts"] += 1
    return scrub(text, mapping), mapping
