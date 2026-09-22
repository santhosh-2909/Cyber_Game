"""MYSTERY TRACE evidence engine (Round 1).

Evidence strings are generated server-side from a canonical plaintext value
the *combined* generator: a variant stores `evidence_config` (JSON) describing
which generator to run and with which parameters. The front-end only ever sees
the final encoded evidence string; the plaintext / answer / flag never leave
the server.

The canonical values and their expected evidence strings are taken verbatim
from the Round 1 "MYSTERY TRACE" challenge spec.
"""
import base64
import hashlib
import json

# ---------------------------------------------------------------------------
# Normalization (answer acceptance)
# ---------------------------------------------------------------------------


def normalize_answer(text):
    """Normalize a submitted answer for case-insensitive comparison.

    Case-insensitive, whitespace-collapsed. This keeps multi-word answers
    (e.g. "Ionic Morphix", "Chroma Brake") acceptably loose without being
    overly fuzzy (characters and punctuation still matter).
    """
    if not text:
        return ""
    return " ".join(str(text).strip().lower().split())


def accepted_answers(canonical, extra=None):
    """Return the set of accepted normalized answers for a canonical value.

    The canonical answer itself plus a couple of humanization variants
    (spaces removed for token-like answers). `extra` is an optional list of
    additional accepted forms ("Also accept" from the spec); each one is
    normalized and compacts to a no-space variant as well.
    """
    out = set()
    for form in [canonical] + list(extra or []):
        if not form:
            continue
        base = normalize_answer(form)
        if base:
            out.add(base)
            compact = "".join(base.split())
            if compact and compact != base:
                out.add(compact)
    return sorted(out)


def answer_is_correct(submitted, canonical, extra=None):
    """Check whether a submitted answer matches a canonical answer."""
    if not submitted:
        return False
    return normalize_answer(submitted) in accepted_answers(canonical, extra)


# ---------------------------------------------------------------------------
# Evidence generators
# ---------------------------------------------------------------------------

TRIGGER_FALLBACK = "[EVIDENCE-LOCKED]"


def _b64(x: bytes) -> str:
    return base64.b64encode(x).decode("ascii")


def _caesar(s: str, shift: int, wrap_text: bool = True) -> str:
    """Classic Caesar shift on [A-Za-z], preserving case and spaces."""
    out = []
    for ch in s:
        if ch.isalpha():
            base = ord("a") if ch.islower() else ord("A")
            out.append(chr((ord(ch) - base + shift) % 26 + base))
        else:
            out.append(ch)
    return "".join(out)


def generate_evidence(canonical, evidence_config):
    """Produce the evidence string for a variant.

    evidence_config is a dict of the form:

        {"type": "static"}                         -> canonical itself
        {"type": "binary"}                         -> space-separated ASCII
        {"type": "octal"}                          -> octal codes (%s)
        {"type": "hex"}                            -> hex of canonical
        {"type": "caesar", "shift": n}             -> caesar-shifted text
        {"type": "hash", "algo": "md5"|"sha256"}   -> digest of canonical
        {"type": "chain", "steps": [...]}          -> sequential transforms

    Chain steps run in order over the running value (a string). Each step is
    either a string step name ("caesar4", "base64", "hex") or a dict for
    parameterized steps.
    """
    if not canonical:
        return TRIGGER_FALLBACK
    cfg = evidence_config or {}
    kind = cfg.get("type", "static")
    value = canonical

    if kind == "static":
        return value

    if kind == "binary":
        return "".join(format(ord(ch), "08b") + " " for ch in value).strip()

    if kind == "octal":
        return " ".join("%o" % ord(ch) for ch in value)

    if kind == "hex":
        return value.encode("utf-8").hex()

    if kind == "caesar":
        return _caesar(value, int(cfg.get("shift", 0)))

    if kind == "hash":
        algo = cfg.get("algo", "sha256").lower()
        # Optional distinct-input support: two hash challenges may share the
        # same answer word but must not share the same displayed digest. A
        # "plain" override hashes an arbitrary string instead of the answer.
        raw = cfg.get("plain") or value
        if algo == "md5":
            return hashlib.md5(raw.encode("utf-8")).hexdigest()
        if algo == "sha1":
            return hashlib.sha1(raw.encode("utf-8")).hexdigest()
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    if kind == "chain":
        out = value
        for step in cfg.get("steps", []):
            out = _run_step(out, step)
        return out

    return TRIGGER_FALLBACK


def _run_step(out, step):
    """Apply a single chain step to the running value."""
    if isinstance(step, dict):
        name = step.get("op", "")
    else:
        name = str(step)

    if name == "caesar4":
        return _caesar(out, 4)
    if name == "caesar3":
        return _caesar(out, 3)
    if name == "caesar13":
        return _caesar(out, 13)
    if name == "rot13":
        return _caesar(out, 13)
    if name == "reverse":
        return out[::-1]
    if name == "base64":
        return _b64(out.encode("utf-8"))
    if name == "hex":
        return out.encode("utf-8").hex()
    if name == "binary":
        return " ".join(format(ord(ch), "08b") for ch in out)
    if name == "octal":
        return " ".join("%o" % ord(ch) for ch in out)
    raise ValueError("Unknown evidence chain step: %r" % (name,))


# ---------------------------------------------------------------------------
# Config loading helpers
# ---------------------------------------------------------------------------


def parse_config(raw, default=None):
    """Parse a JSON config string stored on a variant row."""
    if not raw:
        return default if default is not None else {}
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default if default is not None else {}