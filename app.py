import os
import re
import datetime
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for,
                   session, jsonify, abort, send_from_directory, Response)

import access
import unify
import admin_ops
import round1.db as db

app = Flask(__name__)
app.secret_key = "forencis-csae-secret-key-2026"
app.config["TEMPLATES_AUTO_RELOAD"] = True


def _wants_json():
    """API-ish JSON endpoints return machine-readable errors so participant
    UIs (Round 1 MT, Round 2 MCQ) can show a friendly retry instead of
    failing to parse an HTML error page into a dead 'NETWORK ERROR' box."""
    return (request.path.startswith("/api/")
            or request.path.startswith("/evidence")
            or request.path.startswith("/r2")
            or (request.accept_mimetypes
                and request.accept_mimetypes.best == "application/json"))


@app.errorhandler(404)
def _handle_404(e):
    if _wants_json():
        return jsonify({"ok": False, "error": "not_found", "status": 404}), 404
    return e


@app.errorhandler(503)
def _handle_503(e):
    if _wants_json():
        return jsonify({"ok": False, "error": "temporarily_unavailable",
                        "retry": True, "status": 503}), 503
    return e


@app.errorhandler(500)
def _handle_500(e):
    app.logger.error("Unhandled 500 on %s: %s",
                     request.path, e, exc_info=type(e))
    if _wants_json():
        return jsonify({"ok": False, "error": "server_error",
                        "retry": True, "status": 500}), 500
    return e


@app.errorhandler(db.OperationalErrorBusy)
def _handle_busy(e):
    """SQLite writer contention is transient — surface a RETRYABLE JSON
    error instead of an unhandled 500, and never let it corrupt state."""
    return jsonify({"ok": False, "error": "database_busy",
                    "retry": True, "status": 503}), 503


@app.template_filter("ts")
def _fmt_ts(ms):
    """Format a millisecond timestamp for admin panels."""
    if not ms:
        return "—"
    try:
        return datetime.datetime.fromtimestamp(int(ms) / 1000.0).strftime(
            "%b %d, %H:%M")
    except (TypeError, ValueError, OSError):
        return "—"

# Apply additive schema changes for admin-controlled team access. Safe to run
# on every boot; existing team progress is never touched.
access.init()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EVIDENCE_DIR = os.path.join(BASE_DIR, "evidence")

# ---------------------------------------------------------------------------
# DATA MODELS
# ---------------------------------------------------------------------------

# Each case has: id, title, short title, story fields, 5 stations, person IDs
CASES = {
    "case1": {
        "id": "case1",
        "code": "CASE-A",
        "title": "The Ransomware Hold-Up",
        "file": "case1_ransomware.md",
        "company": "Meridian Logistics Pvt. Ltd.",
        "incident": "A phishing lure and a midnight encryption brought the company to its knees.",
        "objective": "Reconstruct the full attack chain and identify every person involved.",
        "stations": [
            {
                "id": "S1",
                "name": "Email Evidence",
                "domain": "Email Forensics",
                "desc": "Analyze the phishing email headers and mail server logs.",
                "evidence": "phish.eml",
                "question": "What IP sent the phishing email and what was the malicious attachment?",
                "finding": "sender_ip",
                "flag": "203.0.113.42",
                "hint": "Check the Received and Return-Path headers; SPF is failing.",
            },
            {
                "id": "S2",
                "name": "Network PCAP",
                "domain": "Network Forensics",
                "desc": "Examine the network capture for C2 beaconing.",
                "evidence": "traffic.pcap",
                "question": "What is the Command-and-Control server IP address?",
                "finding": "c2_ip",
                "flag": "198.51.100.77",
                "hint": "Look for periodic outbound connections on a high port.",
            },
            {
                "id": "S3",
                "name": "Malware Artifact",
                "domain": "Malware Triage",
                "desc": "Identify the ransomware family and its persistence key.",
                "evidence": "malware.zip",
                "question": "What is the ransomware family name and the persistence registry key?",
                "finding": "family",
                "flag": "BloodRansom",
                "hint": "Run strings on the binary; check the startup registry subkey.",
            },
            {
                "id": "S4",
                "name": "Access Logs",
                "domain": "Log Correlation",
                "desc": "Find the suspicious late-night admin login.",
                "evidence": "access_logs.txt",
                "question": "Which user logged in at the suspicious time just before encryption?",
                "finding": "patient_zero_user",
                "flag": "akhanna",
                "hint": "Cross-reference the DC login against the firewall log timeline.",
            },
            {
                "id": "S5",
                "name": "Ransom Evidence",
                "domain": "Crypto Tracing",
                "desc": "Decode the ransom note and trace the wallet.",
                "evidence": "ransom_note.txt",
                "question": "What is the bitcoin wallet address in the ransom note?",
                "finding": "wallet",
                "flag": "1A2b3C4d5E6f7G8h9I0j",
                "hint": "The wallet string is hidden in an obfuscated part of the note.",
            },
        ],
        "persons": [
            {
                "role": "Victim / Primary Target",
                "key": "victim",
                "answer": ["Meridian Logistics", "meridian"],
                "clue": "The organization that held the data.",
            },
            {
                "role": "Attacker / Ransomware Operator",
                "key": "attacker",
                "answer": ["Elias Vortex", "elias", "vortex"],
                "clue": "The actor demanding the ransom.",
            },
            {
                "role": "Patient-Zero User (insider who clicked)",
                "key": "insider",
                "answer": ["akhanna", "arjun khanna", "khanna", "arjun"],
                "clue": "The employee who opened the malicious attachment.",
            },
            {
                "role": "Accomplice",
                "key": "accomplice",
                "answer": ["", "none"],
                "clue": "Optional - was there an inside helper?",
            },
        ],
    },

    "case2": {
        "id": "case2",
        "code": "CASE-B",
        "title": "The Silent Insider Leak",
        "file": "case2_insider.md",
        "company": "Apex Retail Group",
        "incident": "A confidential pricing document appeared at a rival firm with no external breach.",
        "objective": "Trace how data walked out the front door and identify who leaked it.",
        "stations": [
            {
                "id": "S1",
                "name": "Email Headers",
                "domain": "Email Forensics",
                "desc": "Trace the internal email that exfiltrated the document.",
                "evidence": "trade_email.eml",
                "question": "Who sent the confidential document out of the company?",
                "finding": "sender",
                "flag": "dmehta",
                "hint": "Check the From field and the actual sending account in logs.",
            },
            {
                "id": "S2",
                "name": "PCAP Exfiltration",
                "domain": "Network Forensics",
                "desc": "Find the upload session in the network capture.",
                "evidence": "exfil.pcap",
                "question": "What external IP received the uploaded data?",
                "finding": "dest_ip",
                "flag": "192.0.2.88",
                "hint": "Search for a large one-way upload to a non-standard port.",
            },
            {
                "id": "S3",
                "name": "Document Metadata",
                "domain": "Digital Forensics",
                "desc": "Extract the author and editing device info from the leaked file.",
                "evidence": "leaked_doc.docx",
                "question": "What is the document author's username in the metadata?",
                "finding": "author",
                "flag": "dmehta",
                "hint": "Use strings or exiftool on the docx.",
            },
            {
                "id": "S4",
                "name": "Access Logs",
                "domain": "Log Analysis",
                "desc": "Find unauthorized access to the shared drive.",
                "evidence": "share_logs.txt",
                "question": "Which employee accessed the confidential file outside normal hours?",
                "finding": "access_user",
                "flag": "dmehta",
                "hint": "Look for a 02:00 AM access on the shared drive.",
            },
            {
                "id": "S5",
                "name": "Employee Records",
                "domain": "User Forensics",
                "desc": "Correlate HR records to a specific employee.",
                "evidence": "employee_records.txt",
                "question": "Which full employee name maps to all the clues?",
                "finding": "employee",
                "flag": "david mehta",
                "hint": "The department head with access to pricing.",
            },
        ],
        "persons": [
            {
                "role": "Victim / Data Owner",
                "key": "victim",
                "answer": ["Apex Retail Group", "apex"],
                "clue": "The company whose data was stolen.",
            },
            {
                "role": "Leaker / Insider Suspect",
                "key": "leaker",
                "answer": ["dmehta", "david mehta", "mehta", "david"],
                "clue": "The employee who sent the data out.",
            },
            {
                "role": "Receiver / Rival Contact",
                "key": "receiver",
                "answer": ["Nova Retail", "nova", "jasmin cole", "cole"],
                "clue": "The external party that received the data.",
            },
            {
                "role": "Accomplice",
                "key": "accomplice",
                "answer": ["", "none"],
                "clue": "Optional - was there an inside helper?",
            },
        ],
    },

    "case3": {
        "id": "case3",
        "code": "CASE-C",
        "title": "The CEO Fraud Deception",
        "file": "case3_bec.md",
        "company": "StellarWorks Manufacturing",
        "incident": "A six-figure payment was wired based on an email the CEO never sent.",
        "objective": "Prove the impersonation, trace the fraudster, and name everyone involved.",
        "stations": [
            {
                "id": "S1",
                "name": "Email Headers",
                "domain": "Email Forensics",
                "desc": "Trace the spoofed CEO email.",
                "evidence": "spoofed_ceo.eml",
                "question": "What is the real sender IP (SPF/DKIM failing)?",
                "finding": "sender_ip",
                "flag": "203.0.113.200",
                "hint": "The Return-Path does not match the From; SPF fails.",
            },
            {
                "id": "S2",
                "name": "Reply-To Analysis",
                "domain": "Email Forensics",
                "desc": "Find the attacker-controlled Reply-To address.",
                "evidence": "spoofed_ceo.eml",
                "question": "What Reply-To address would receive the fraud reply?",
                "finding": "reply_to",
                "flag": "accounts.verify@fraudmail.net",
                "hint": "Look at the Reply-To header - it differs from the CEO's real address.",
            },
            {
                "id": "S3",
                "name": "Wire Request",
                "domain": "Social Engineering",
                "desc": "Inspect the forged bank details in the email.",
                "evidence": "wire_request.txt",
                "question": "What is the fraudulent bank account number?",
                "finding": "account",
                "flag": "0987654321",
                "hint": "Compare against the legitimate vendor account list.",
            },
            {
                "id": "S4",
                "name": "Email Timeline",
                "domain": "Log Analysis",
                "desc": "Reconstruct the phishing delivery timeline.",
                "evidence": "mail_logs.txt",
                "question": "At what time was the spoofed email actually delivered?",
                "finding": "delivery_time",
                "flag": "2026-08-27 09:14",
                "hint": "Cross-check the Received trace timestamps.",
            },
            {
                "id": "S5",
                "name": "Money Trail",
                "domain": "OSINT / Network",
                "desc": "Trace where the funds were routed.",
                "evidence": "bank_transfer.txt",
                "question": "What is the destination account holder's name?",
                "finding": "beneficiary",
                "flag": "Rajan Iyer",
                "hint": "The funds moved from the fake account to a named beneficiary.",
            },
        ],
        "persons": [
            {
                "role": "Victim / Spoofed Person (CEO)",
                "key": "victim",
                "answer": ["sonia kapoor", "kapoor", "sonia"],
                "clue": "The CEO whose identity was impersonated.",
            },
            {
                "role": "Attacker / Fraudster",
                "key": "attacker",
                "answer": ["masked hacker", "hacker", "operator"],
                "clue": "The actor behind the spoofed email.",
            },
            {
                "role": "Compromised Insider (moved funds)",
                "key": "insider",
                "answer": ["arvind nair", "nair", "arvind"],
                "clue": "The finance employee who wired the money.",
            },
            {
                "role": "Money-Receiver / Beneficiary",
                "key": "beneficiary",
                "answer": ["rajan iyer", "iyer", "rajan"],
                "clue": "The person who received the fraudulent payment.",
            },
        ],
    },
}


# ---------------------------------------------------------------------------
# ROUND 1 - CYBER PUZZLE CHALLENGES
# ---------------------------------------------------------------------------

CHALLENGES = [
    {"title": "SQL Injection Basics", "domain": "WEB", "difficulty": "MEDIUM",
     "task": "Craft a SQL injection payload to bypass the login query.",
     "description": "A login form is vulnerable to SQL injection. Bypass the authentication by injecting a payload into the username field that makes the WHERE clause always true.",
     "artifact": "login.php", "flag": "sqli_always_true", "points": 100,
     "hint": "Try a classic OR 1=1 payload with a comment terminator.",
     "published": True, "instructions": ["Navigate to the vulnerable login endpoint.", "Inject into the username field.", "Retrieve the flag after successful bypass."]},
    {"title": "Caesar Shift Decode", "domain": "CRYPTO", "difficulty": "EASY",
     "task": "Decode the Caesar ciphertext to reveal a hidden flag.",
     "description": "A message has been shifted by an unknown number of positions. Brute-force or analyze the frequency to decode it.",
     "artifact": "shift.txt", "flag": "caesar_breach", "points": 75,
     "hint": "Try all 25 shifts; look for a readable English message.",
     "published": True, "instructions": []},
    {"title": "PCAP Credential Hunt", "domain": "NETWORKING", "difficulty": "MEDIUM",
     "task": "Analyze the packet capture to recover credentials.",
     "description": "An unencrypted HTTP login occurred on the network. Inspect the PCAP to recover the submitted username and password.",
     "artifact": "capture.pcap", "flag": "http_basic_auth", "points": 100,
     "hint": "Filter for http and look at the POST data.",
     "published": True, "instructions": []},
    {"title": "Metadata Extraction", "domain": "FORENSICS", "difficulty": "EASY",
     "task": "Extract the author name hidden in the document metadata.",
     "description": "A leaked document contains identifying metadata. Extract the author field.",
     "artifact": "leak.docx", "flag": "meta_author", "points": 75,
     "hint": "Use strings or exiftool on the file.",
     "published": True, "instructions": []},
    {"title": "Port Scan Recon", "domain": "NETWORKING", "difficulty": "MEDIUM",
     "task": "Identify which service is running on the scan results.",
     "description": "A network scan revealed open ports. Identify the service running on the flagged port.",
     "artifact": "scan.txt", "flag": "open_port_3389", "points": 100,
     "hint": "Port 3389 = RDP, 22 = SSH, 80 = HTTP.",
     "published": True, "instructions": []},
    {"title": "Base64 Obfuscation", "domain": "CRYPTO", "difficulty": "EASY",
     "task": "Decode the base64-encoded token to reveal a secret.",
     "description": "A suspicious token was found. It's base64 encoded. Decode it and extract the flag.",
     "artifact": "token.b64", "flag": "decoded_token", "points": 75,
     "hint": "Decode from base64 once, then again if needed.",
     "published": True, "instructions": []},
    {"title": "OSINT Email Trace", "domain": "OSINT", "difficulty": "MEDIUM",
     "task": "Trace the origin domain behind the suspicious email.",
     "description": "An email claims to be from a trusted domain but the real sender domain can be discovered through headers.",
     "artifact": "header.eml", "flag": "spoof_domain", "points": 100,
     "hint": "Check the Return-Path and Received headers.",
     "published": True, "instructions": []},
    {"title": "Wireshark Stream", "domain": "FORENSICS", "difficulty": "HARD",
     "task": "Reassemble the HTTP stream to recover transmitted data.",
     "description": "A file was transferred over the network. Follow the TCP stream to reconstruct it and locate the flag.",
     "artifact": "stream.pcap", "flag": "stream_carved", "points": 125,
     "hint": "Right-click Follow TCP Stream in Wireshark.",
     "published": True, "instructions": []},
    {"title": "Hash Cracking", "domain": "SECURITY", "difficulty": "HARD",
     "task": "Crack the MD5 hash to reveal the plaintext password.",
     "description": "A password hash was recovered from the database. It's a weak MD5 hash. Try common wordlists.",
     "artifact": "hash.txt", "flag": "cracked_pass", "points": 125,
     "hint": "Try a small rockyou-style wordlist.",
     "published": False, "instructions": []},
    {"title": "Steganography", "domain": "FORENSICS", "difficulty": "HARD",
     "task": "Extract the hidden file embedded in the image.",
     "description": "An innocent-looking image contains a hidden message. Extract the embedded data.",
     "artifact": "hidden.png", "flag": "steg_hidden", "points": 125,
     "hint": "Check for appended data or LSB steganography.",
     "published": False, "instructions": []},
    {"title": "Binary Analysis", "domain": "REVERSING", "difficulty": "HARD",
     "task": "Reverse engineer the binary to recover the hardcoded flag.",
     "description": "A compiled binary contains a hardcoded credential. Use strings or a disassembler to find it.",
     "artifact": "binary", "flag": "hardcoded_key", "points": 150,
     "hint": "Run strings on the binary and grep for 'flag'.",
     "published": False, "instructions": []},
    {"title": "JWT Forgery", "domain": "WEB", "difficulty": "HARD",
     "task": "Forge a valid JWT to escalate privileges.",
     "description": "A JWT with 'alg:none' or weak signing can be forged. Modify the token to become admin.",
     "artifact": "token.jwt", "flag": "jwt_forged", "points": 150,
     "hint": "Try setting alg to none and removing the signature.",
     "published": False, "instructions": []},
]

challenge_domains = []
for _c in CHALLENGES:
    if _c["domain"] not in challenge_domains:
        challenge_domains.append(_c["domain"])

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def normalize(text):
    if not text:
        return ""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def normalize_flag(text):
    if not text:
        return ""
    return text.strip().lower()


# Representation of the attack / evidence chain per case for the evidence board
BOARDS = {
    "case1": [
        {"label": "EMAIL", "detail": "Phishing email received", "icon": "📧"},
        {"label": "MALWARE", "detail": "BloodRansom dropped via attachment", "icon": "🦠"},
        {"label": "NETWORK", "detail": "C2 beaconing to 198.51.100.77", "icon": "🌐"},
        {"label": "FILE SERVER", "detail": "FS01 encrypted 16:42 UTC", "icon": "🗄️"},
        {"label": "RANSOM", "detail": "Wallet 1A2b3C4d5E6f7G8h9I0j", "icon": "💰"},
    ],
    "case2": [
        {"label": "DOCUMENT", "detail": "Pricing file accessed 02:00", "icon": "📄"},
        {"label": "EMAIL", "detail": "Sent to external address", "icon": "📧"},
        {"label": "NETWORK", "detail": "Uploaded to 192.0.2.88", "icon": "🌐"},
        {"label": "RIVAL", "detail": "Nova Retail received it", "icon": "🏢"},
        {"label": "LEAK", "detail": "Insider: David Mehta", "icon": "🕵️"},
    ],
    "case3": [
        {"label": "SPOOFED EMAIL", "detail": "CEO impersonated", "icon": "📧"},
        {"label": "REPLY-TO", "detail": "fraudmail.net address", "icon": "✉️"},
        {"label": "WIRE REQUEST", "detail": "Forged bank details", "icon": "🏦"},
        {"label": "PAYMENT", "detail": "₹ routed to fake account", "icon": "💸"},
        {"label": "BENEFICIARY", "detail": "Rajan Iyer", "icon": "🕵️"},
    ],
}


# ---------------------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if access.is_logged_in("round2") is False:
            return redirect(url_for("r2_login"))
        return f(*args, **kwargs)
    return wrapper


R2_TIMER_MINUTES = 45  # fixed Round 2 limit; hits 0 -> COMPLETED


def r2_timer_minutes():
    """Round 2 limit in minutes (admin setting, falls back to 45)."""
    try:
        minutes = int((admin_ops.get_round_settings("round2") or {}).get(
            "timer_minutes") or R2_TIMER_MINUTES)
    except (TypeError, ValueError):
        minutes = R2_TIMER_MINUTES
    return minutes if minutes > 0 else R2_TIMER_MINUTES


def get_r2_timer():
    """Server-authoritative Round 2 countdown state.

    Lazily starts the timer for pre-existing sessions, then enforces expiry:
    when remaining hits 0 the round is marked COMPLETED exactly once.
    Returns dict(status, remaining_ms, ends_at, started_at).
    """
    now = db_now_ms()
    status = session.get("r2_status") or "ACTIVE"
    started_at = session.get("r2_started_at")
    ends_at = session.get("r2_ends_at")
    if not started_at or not ends_at:
        started_at = now
        ends_at = now + r2_timer_minutes() * 60 * 1000
        session["r2_started_at"] = started_at
        session["r2_ends_at"] = ends_at
        session["r2_status"] = "ACTIVE"
        session.pop("r2_completed_at", None)
        status = "ACTIVE"
    remaining_ms = int(ends_at) - now
    if remaining_ms <= 0:
        remaining_ms = 0
        if status != "COMPLETED":
            session["r2_status"] = "COMPLETED"
            session["r2_completed_at"] = now
            status = "COMPLETED"
    return {"status": status, "remaining_ms": remaining_ms,
            "ends_at": int(ends_at), "started_at": int(started_at)}


def r2_expired():
    """True when the Round 2 timer has hit 0 (round marked COMPLETED)."""
    return get_r2_timer()["status"] == "COMPLETED"


@app.context_processor
def _inject_r2_timer():
    try:
        if session.get("team"):
            return {"r2_timer": get_r2_timer()}
    except Exception:
        pass
    return {"r2_timer": {"status": "ACTIVE", "remaining_ms": R2_TIMER_MINUTES * 60 * 1000,
                         "ends_at": 0, "started_at": 0}}


def db_now_ms(conn=None):
    """Millisecond timestamp (matches round1.db convention)."""
    import time
    return int(time.time() * 1000)


def pick_case():
    """Rotating case assignment (delegated to the shared access module)."""
    return access.pick_case()


# ---------------------------------------------------------------------------
# ROUND 2 - CASE STATE HELPERS
# ---------------------------------------------------------------------------

MAX_ATTEMPTS = 5   # wrong submissions before a station is flagged/locked

# ---------------------------------------------------------------
# Round 2 QUIZ MODE — per-question multiple choice scoring
# +20 correct · −5 wrong · +5 speed bonus for ANY correct answer
# inside the bonus grace window (30s). After the window the question
# STAYS OPEN until answered: no timeout penalty and no auto-advance,
# but a correct answer then scores +20 with no +5 bonus.
# Per station: 3 questions × max 25 = 75 pts → case max = 15 × 25 = 375.
# ---------------------------------------------------------------
MCQ_PER_STATION = 3
MCQ_CORRECT = 20
MCQ_BONUS = 5
MCQ_WRONG = -5
MCQ_TIME_MS = 30000
MCQ_STATION_MAX = MCQ_PER_STATION * (MCQ_CORRECT + MCQ_BONUS)  # 75

# Per-station accent (drives the option-card colour per vault level).
STATION_ACCENTS = ("cyan", "amber", "purple", "green", "magenta")


def format_case_code(raw):
    """Display label for a case code: 'case3' -> 'CASE-03'."""
    m = re.search(r"(\d+)\s*$", str(raw or ""))
    if m:
        return "CASE-" + m.group(1).zfill(2)
    return str(raw or "").upper()


def load_case(case_code):
    """Load a Round 2 case from the admin-managed content DB.

    Returns a dict structurally identical to the legacy in-memory CASES
    entries (stations + persons) so the participant flow, scoring and
    templates keep working unchanged. Draft/archived content is excluded from
    the participant view. Stations carrying an ``mcq_json`` bank expose it as
    ``station['mcqs']`` — q + options only, answers are never sent to the
    participant browser, and are re-read from the DB at submit time.
    """
    case = admin_ops.get_round2_case_by_code(case_code)
    if case is None:
        return None
    stations = [dict(s) for s in admin_ops.list_r2_stations(case["id"])]
    persons = [dict(p) for p in admin_ops.list_r2_persons(case["id"])]
    published = [s for s in stations if s.get("status", "PUBLISHED") == "PUBLISHED"]
    if published:
        stations = published
    view = []
    for s in stations:
        mcq_bank = admin_ops.parse_mcq_json(s.get("mcq_json"))
        mcqs = [{"q": m["q"], "options": list(m["options"])} for m in mcq_bank["mcqs"]]
        view.append({
            "id": s.get("station_id", ""),
            "name": s.get("name", ""),
            "domain": s.get("domain", ""),
            "desc": s.get("description", ""),
            "evidence": s.get("evidence", ""),
            "question": s.get("question", ""),
            "finding": "f_" + str(s.get("station_id", "")),
            "flag": s.get("answer", ""),
            "hint": s.get("hint", ""),
            "points": s.get("points", 100),
            "max_attempts": s.get("max_attempts", 5),
            "validation_mode": s.get("validation_mode", "NORMALIZED"),
            "mcqs": mcqs,
            "db_id": s.get("id"),
        })
    view_persons = []
    for p in persons:
        view_persons.append({
            "role": p.get("role", ""),
            "key": p.get("person_key", ""),
            "answer": p.get("answers", []),
            "clue": p.get("clue", ""),
            "db_id": p.get("id"),
        })
    return {
        "id": case_code,
        "code": format_case_code(case.get("case_code", case_code)),
        "case_code_raw": case.get("case_code", case_code),
        "title": case.get("title", case_code),
        "file": "",
        "company": case.get("company", ""),
        "incident": case.get("case_brief", case.get("description", "")),
        "objective": case.get("objective", ""),
        "db_id": case.get("id"),
        "stations": view,
        "persons": view_persons,
    }


def _mcq_answers():
    """Session dict {station_id: [answer records]} for the current participant."""
    return dict(session.get("mcq") or {})


def _station_answered(answers, station):
    """Number of MCQs answered for a station (0 = untouched)."""
    return len(answers.get(station["id"], []) or [])


def station_answers(station):
    """Authoritative MCQ list for a station from the content DB (answers intact)."""
    row = admin_ops.get_r2_station(station.get("db_id")) or {}
    if not row.get("mcq_json"):
        return []
    return admin_ops.parse_mcq_json(row.get("mcq_json"))["mcqs"]


def current_case():
    """The participant's assigned Round 2 case (DB-backed with legacy fallback)."""
    code = session.get("team", {}).get("case")
    case = load_case(code)
    if case is not None:
        return case
    return CASES.get(code) or (list(CASES.values())[0] if CASES else None)


def next_case_code(current_code):
    """The next PUBLISHED case a team advances to after completing the current one.

    Follows display_order and wraps around. Returns None when the pool has no
    next case (empty or a single-case round), so callers hide the CTA.
    """
    cases = [c["case_code"] for c in admin_ops.list_r2_cases(include_archived=False)]
    if len(cases) < 2:
        return None
    if current_code in cases:
        idx = cases.index(current_code)
    else:
        return cases[0]
    if len(cases) > 1:
        return cases[(idx + 1) % len(cases)]
    return None


# Seed the admin-managed Round 2 content library from the legacy multi-case
# definitions (idempotent, never overwrites admin edits). Only used when the
# R2 library is completely empty — once the admin/seeder populates it (e.g. the
# 10-case MCQ quiz bank) the legacy text cases are never re-introduced.
if admin_ops.count_r2_cases() == 0:
    admin_ops.seed_r2_cases(CASES)


def station_states(case, answers, attempts=None):
    """Sequential vault states for each station of a case.

    Each station is a 3-question quiz module. A station is 'verified' once all
    three MCQs are answered; the first station still in progress is the active
    frontier ('opened' / 'analyzing'), everything after stays locked, and
    previously verified levels read as 'reviewed'.
    """
    states = []
    frontier_open = True
    for i, s in enumerate(case["stations"]):
        done = _station_answered(answers, s)
        if done >= MCQ_PER_STATION:
            states.append("verified")
            continue
        if frontier_open:
            states.append("analyzing" if done > 0 else "opened")
            frontier_open = False
        else:
            states.append("locked")
    for i, st in enumerate(states):
        if st == "verified" and any(
                later in ("verified", "analyzing", "opened")
                for later in states[i + 1:]):
            states[i] = "reviewed"
    return states


def case_stage(findings=None, persons=None):
    """Investigation workflow stage: opened|brief|evidence|report|complete."""
    if session.get("report"):
        return "complete"
    answers = _mcq_answers()
    case = current_case()
    if case and all(_station_answered(answers, s) >= MCQ_PER_STATION
                    for s in case["stations"]):
        return "complete"
    if persons:
        return "report"
    if answers and any(v for v in answers.values()):
        return "evidence"
    if session.get("brief_viewed"):
        return "brief"
    return "opened"


def verified_count(case, answers):
    """Stations whose full 3-question quiz has been answered."""
    return sum(1 for s in case["stations"]
               if _station_answered(answers, s) >= MCQ_PER_STATION)


def quiz_count(case, answers):
    """Total MCQs answered across every station (max = stations × 3)."""
    return sum(_station_answered(answers, s) for s in case["stations"])


# ---------------------------------------------------------------------------
# ROUTES
# ---------------------------------------------------------------------------

@app.route("/")
def landing():
    # Keep an authenticated participant inside the round they entered, or send
    # a both-rounds unified team straight to the Operations Center hub.
    if access.is_logged_in():
        unified_rounds = session.get("unified_rounds") or []
        if "round1" in unified_rounds and "round2" in unified_rounds:
            return redirect(url_for("home"))
        if session.get("active_round") == "round1":
            return redirect(url_for("r1.r1_dashboard"))
        return redirect(url_for("dashboard"))
    return render_template("landing.html", is_admin=access.is_admin())


@app.route("/r2/login", methods=["GET", "POST"])
def r2_login():
    """Round 2 direct login using its dedicated access ID."""
    if access.is_logged_in("round2"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        team_name = request.form.get("team_name", "").strip()
        team_id = request.form.get("team_id", "").strip()
        ok, error = access.participant_login(team_name, team_id, "round2")
        if not ok:
            return render_template("r2_login.html", error=error)
        return redirect(url_for("dashboard"))
    return render_template("r2_login.html", error=access.pop_login_notice())


@app.route("/home")
def home():
    """Return participants to the Operations Center (both rounds) or their
    active round's dashboard."""
    auth = access.validate_participant()
    if auth is None:
        return redirect(url_for("start"))
    unified_rounds = session.get("unified_rounds") or []
    is_both_rounds = "round1" in unified_rounds and "round2" in unified_rounds
    if session.get("active_round") == "round1" and not is_both_rounds:
        return redirect(url_for("r1.r1_dashboard"))
    if session.get("active_round") == "round2" and not is_both_rounds:
        return redirect(url_for("dashboard"))

    # Both-rounds unified session (or a legacy session without an active round):
    # render the ONE LOGIN · BOTH ROUNDS Operations Center hub.
    profile = unify.get_round1_profile()
    r1_session = unify.get_round1_session()
    r1_stage = unify.round1_stage()
    r1_stats = None
    if r1_session:
        r1_stats = {
            "score": r1_session["score"],
            "solved": r1_session["challenges_solved"],
            "total": 6,
            "remaining_ms": max(0, r1_session["ends_at"] - __import__("time").time() * 1000),
        }
    team = session.get("team")
    return render_template("home.html",
                           team=team,
                           auth=auth,
                           profile=profile,
                           r1_session=r1_session,
                           r1_stage=r1_stage,
                           r1_stats=r1_stats,
                           r2_ready=unify.round2_ready())


@app.route("/start", methods=["GET", "POST"])
def start():
    """Unified TEAM LOGIN (Team Name + Team ID only).

    Unauthenticated teams cannot self-register. A team can only sign in when
    it was first created/authorized by an administrator. One sign-in opens
    BOTH rounds (Round 1 + Round 2) for the team.
    """
    notice = access.pop_login_notice()
    if request.method == "POST":
        team_name = request.form.get("team_name", "").strip()
        team_id = request.form.get("team_id", "").strip()
        ok, error = access.participant_login_unified(team_name, team_id)
        if not ok:
            return render_template("start.html", error=error or notice)
        return redirect(url_for("home"))

    if access.is_logged_in():
        return redirect(url_for("home"))
    return render_template("start.html", error=notice)


@app.route("/login")
def index():
    if access.is_logged_in():
        return redirect(url_for("home"))
    return redirect(url_for("start"))


@app.route("/login", methods=["POST"])
def login():
    """Backward-compatible POST handler for the unified team login."""
    team_name = request.form.get("team_name", "").strip()
    team_id = request.form.get("team_id", "").strip()
    ok, error = access.participant_login_unified(team_name, team_id)
    if not ok:
        return render_template("start.html", error=error)
    return redirect(url_for("home"))


@app.route("/logout")
def logout():
    # Ends the participant's login session. An administrator's session is
    # untouched so clearing logins/admins all remain separate concerns.
    access.participant_logout()
    return redirect(url_for("landing"))


# Spec-aligned aliases: Round 2 lives at /dashboard (existing route). These
# URLs also require a valid participant session and reuse the existing route.
@app.route("/r2")
@login_required
def r2_home():
    return redirect(url_for("dashboard"))


@app.route("/r2/dashboard")
@login_required
def r2_dashboard_alias():
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
@login_required
def dashboard():
    case = current_case()
    answers = _mcq_answers()
    states = station_states(case, answers)
    report_done = bool(session.get("report"))
    return render_template("dashboard.html", team=session["team"], case=case,
                           answers=answers,
                           MCQ_PER_STATION=MCQ_PER_STATION,
                           vault=[{"station": s, "state": st, "cnt": _station_answered(answers, s)}
                                  for s, st in zip(case["stations"], states)],
                           verified=verified_count(case, answers),
                           answered=quiz_count(case, answers),
                           stage=case_stage(),
                           report_done=report_done,
                           next_case=next_case_code(case.get("case_code_raw")))


@app.route("/case")
@login_required
def case_study():
    case = current_case()
    session["brief_viewed"] = True
    answers = _mcq_answers()
    return render_template("case.html", team=session["team"], case=case,
                           answers=answers,
                           MCQ_PER_STATION=MCQ_PER_STATION,
                           verified=verified_count(case, answers),
                           stage=case_stage())


@app.route("/evidence/<station_id>")
@login_required
def evidence(station_id):
    case = current_case()
    station = next((s for s in case["stations"] if s["id"] == station_id), None)
    if not station:
        abort(404)
    answers = _mcq_answers()
    states = station_states(case, answers)
    idx = next(i for i, s in enumerate(case["stations"]) if s["id"] == station_id)
    state = states[idx]
    unlocked = state != "locked"
    station_done = _station_answered(answers, station)
    accent = STATION_ACCENTS[idx % len(STATION_ACCENTS)]
    next_open = next((s["id"] for s, st in zip(case["stations"], states)
                      if st in ("opened", "analyzing")), case["stations"][0]["id"])
    return render_template(
        "station.html", team=session["team"], case=case,
        station=station if unlocked else None,
        unlocked=unlocked, state=state,
        accent=accent,
        next_open=next_open,
        station_done=station_done,
        station_answers=answers.get(station_id, []) or [],
        mcq_answers=answers,
        mcq_total=MCQ_PER_STATION,
        mcq_time_ms=MCQ_TIME_MS,
        mcq_correct=MCQ_CORRECT, mcq_wrong=MCQ_WRONG, mcq_bonus=MCQ_BONUS,
        verified=verified_count(case, answers),
        answered=quiz_count(case, answers),
        report_done=bool(session.get("report")),
        note=session.get("notes", {}).get(station_id, ""),
        vault=[{"station": s, "state": st, "active": s["id"] == next_open}
               for s, st in zip(case["stations"], states)])


@app.route("/api/mcq/start", methods=["POST"])
@login_required
def mcq_start():
    """Mark the participant's question start time (server-authoritative).

    The 30s bonus-grace clock is judged server-side against this timestamp,
    so refreshing the page or replaying the request can never extend it.
    """
    if r2_expired():
        return jsonify({"ok": False, "error": "Round 2 time is up.",
                        "completed": True}), 403
    data = request.get_json(silent=True) or {}
    station_id = data.get("station_id")
    try:
        q_index = int(data.get("q_index") or 0)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid question index."}), 400
    case = current_case()
    station = next((s for s in case["stations"] if s["id"] == station_id), None)
    if not station:
        return jsonify({"ok": False, "error": "Invalid station."}), 400
    answers = _mcq_answers()
    states = station_states(case, answers)
    idx = case["stations"].index(station)
    if states[idx] == "locked":
        return jsonify({"ok": False,
                        "error": "Station locked — complete earlier stations first."}), 403
    if q_index < 0 or q_index >= max(1, len(station["mcqs"])):
        return jsonify({"ok": False, "error": "Invalid question index."}), 400
    if q_index < len(answers.get(station_id, []) or []):
        return jsonify({"ok": True, "already": True, "q_index": q_index})
    session["mcq_start"] = {"station_id": station_id, "q": q_index,
                            "at": db_now_ms()}
    return jsonify({"ok": True, "q_index": q_index})


@app.route("/api/mcq/submit", methods=["POST"])
@login_required
def mcq_submit():
    """Grade a single MCQ answer against the DB-stored key.

    Scoring per question (max +25):
      • correct answered within 30s  → +20 +5 bonus
      • correct answered after 30s   → +20 (question stays open, no penalty)
      • wrong answer                 → −5
    A question is never auto-advanced: submitting with no option is ignored
    and the question remains open until the participant answers it.
    Answers are recorded exactly once (idempotent on repeat submits).
    """
    if r2_expired():
        return jsonify({"ok": False, "error": "Round 2 time is up.",
                        "completed": True}), 403
    data = request.get_json(silent=True) or {}
    station_id = data.get("station_id")
    try:
        q_index = int(data.get("q_index") or 0)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid question index."}), 400
    option_raw = data.get("option")
    if option_raw is None or option_raw == "":
        chosen = None
    else:
        try:
            chosen = int(option_raw)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Invalid option."}), 400

    case = current_case()
    station = next((s for s in case["stations"] if s["id"] == station_id), None)
    if not station:
        return jsonify({"ok": False, "error": "Invalid station."}), 400
    answers = _mcq_answers()
    states = station_states(case, answers)
    idx = case["stations"].index(station)
    if states[idx] == "locked":
        return jsonify({"ok": False,
                        "error": "Station locked — complete earlier stations first."}), 403
    key = station_answers(station)
    if q_index < 0 or q_index >= len(key):
        return jsonify({"ok": False, "error": "No such question."}), 400
    mcq = key[q_index]

    recorded = list(answers.get(station_id, []) or [])
    if q_index < len(recorded):
        prior = recorded[q_index]
        return jsonify({
            "ok": True, "already": True, "q_index": q_index,
            "correct": prior["correct"], "pts": prior["pts"],
            "bonus": prior.get("bonus", False),
            "station_done": (len(recorded) >= MCQ_PER_STATION),
            "case_done": all(len((answers or {}).get(s["id"], []) or []) >= MCQ_PER_STATION
                             for s in case["stations"])})

    # No option selected: question stays open until answered. Never record
    # or advance, so a blank submit can never cost points.
    if chosen is None:
        start = session.get("mcq_start") or {}
        elapsed_raw = db_now_ms() - (start.get("at") or 0)
        if not (start.get("station_id") == station_id and start.get("q") == q_index):
            elapsed_raw = int(data.get("elapsed_ms") or MCQ_TIME_MS)
        return jsonify({
            "ok": True, "not_answered": True, "q_index": q_index,
            "bonus_ms_remaining": max(0, MCQ_TIME_MS - elapsed_raw)})

    start = session.get("mcq_start") or {}
    elapsed = db_now_ms() - (start.get("at") or 0)
    if not (start.get("station_id") == station_id and start.get("q") == q_index):
        elapsed = int(data.get("elapsed_ms") or MCQ_TIME_MS)
    within_bonus = elapsed <= MCQ_TIME_MS
    correct = chosen == mcq["answer"]
    if correct:
        pts = MCQ_CORRECT + (MCQ_BONUS if within_bonus else 0)
    else:
        pts = MCQ_WRONG
    recorded.append({
        "chosen": chosen,
        "correct": bool(correct),
        "pts": pts,
        "ms": max(0, int(elapsed)),
        "bonus": bool(correct and within_bonus),
        "at": db_now_ms(),
    })
    answers[station_id] = recorded
    session["mcq"] = answers
    session["mcq_start"] = {}
    station_done = len(recorded) >= MCQ_PER_STATION
    case_done = all(len((answers.get(s["id"], []) or [])) >= MCQ_PER_STATION
                    for s in case["stations"])
    return jsonify({
        "ok": True, "q_index": q_index, "correct": bool(correct),
        "bonus": bool(correct and within_bonus), "pts": recorded[-1]["pts"],
        "answer_index": mcq["answer"],
        "steps": recorded[-1]["pts"],
        "station_done": station_done, "case_done": case_done,
        "answer_count": len(recorded),
    })


@app.route("/evidence/download/<path:filename>")
@login_required
def download_evidence(filename):
    case = current_case()
    answers = _mcq_answers()
    states = station_states(case, answers)
    for i, s in enumerate(case["stations"]):
        if s["evidence"] == filename and states[i] == "locked":
            abort(403)
    return send_from_directory(EVIDENCE_DIR, filename)


@app.route("/api/notes", methods=["POST"])
@login_required
def save_note():
    if r2_expired():
        return jsonify({"ok": False, "error": "Round 2 time is up.",
                        "completed": True}), 403
    data = request.get_json() or {}
    station_id = data.get("station_id")
    text = (data.get("text") or "").strip()
    case = current_case()
    if not any(s["id"] == station_id for s in case["stations"]):
        return jsonify({"error": "Invalid station"}), 400
    notes = dict(session.get("notes", {}))
    notes[station_id] = text
    session["notes"] = notes
    return jsonify({"ok": True, "station_id": station_id})


@app.route("/api/submit", methods=["POST"])
@login_required
def submit_finding():
    if r2_expired():
        return jsonify({"error": "Round 2 time is up.", "completed": True,
                        "attempts_left": 0}), 403
    data = request.get_json() or {}
    station_id = data.get("station_id")
    value = data.get("value", "").strip()
    case = current_case()
    station = next((s for s in case["stations"] if s["id"] == station_id), None)
    if not station:
        return jsonify({"error": "Invalid station"}), 400
    max_attempts = int(station.get("max_attempts") or MAX_ATTEMPTS)
    attempts = dict(session.get("attempts", {}))
    used = int(attempts.get(station_id, 0) or 0)
    findings = dict(session.get("findings", {}))
    if findings.get(station_id, {}).get("status") == "verified":
        return jsonify({"correct": True, "value": value, "already": True,
                        "attempts_left": max_attempts - used})
    if used >= max_attempts:
        return jsonify({"error": "Max attempts reached", "locked": True,
                        "attempts_left": 0, "max_attempts": max_attempts}), 400
    attempts[station_id] = used + 1
    session["attempts"] = attempts
    correct = normalize_flag(value) == normalize_flag(station["flag"]) or \
              normalize_flag(station["flag"]) in normalize_flag(value)
    findings[station_id] = {
        "value": value,
        "status": "verified" if correct else "incorrect"
    }
    session["findings"] = findings
    return jsonify({"correct": correct, "value": value,
                    "attempts_left": max(0, max_attempts - (used + 1)),
                    "max_attempts": max_attempts})


@app.route("/evidence-board")
@login_required
def evidence_board():
    case_id = session["team"]["case"]
    case = current_case()
    board = BOARDS.get(case_id, [])
    # Quiz-mode cases (admin-managed) have no pre-canned attack-chain board.
    if not board:
        return redirect(url_for("dashboard"))
    answers = _mcq_answers()
    states = station_states(case, answers)
    return render_template("evidence_board.html", team=session["team"],
                           case=case, board=board, answers=answers,
                           vault=[{"station": s, "state": st}
                                  for s, st in zip(case["stations"], states)],
                           verified=verified_count(case, answers),
                           stage=case_stage(),
                           report_done=bool(session.get("report")))


@app.route("/report", methods=["GET", "POST"])
@login_required
def report():
    case = current_case()
    # Quiz-mode cases have no person-identification sheet; the deliverable is
    # the MCQ score card.
    if not case["persons"]:
        return redirect(url_for("score"))
    if request.method == "POST":
        if r2_expired():
            return redirect(url_for("score"))
        for person in case["persons"]:
            key = person["key"]
            value = request.form.get(f"person_{key}", "").strip()
            evidence = request.form.get(f"evidence_{key}", "").strip()
            accepted = []
            for a in person["answer"]:
                if normalize(a):
                    accepted.append(normalize(a))
            if not accepted:
                status = "skip"
            elif any(normalize(value) and normalize(a) in normalize(value) or
                     (normalize(value) and normalize(value) in normalize(a))
                     for a in accepted):
                status = "verified"
            else:
                status = "incorrect"
            persons = dict(session.get("persons", {}))
            persons[key] = {"value": value, "evidence": evidence,
                            "status": status}
            session["persons"] = persons
        entry = request.form.get("entry_point", "").strip()
        timeline = request.form.get("timeline", "").strip()
        conclusion = request.form.get("conclusion", "").strip()
        session["report"] = {
            "entry_point": entry, "timeline": timeline, "conclusion": conclusion
        }
        return redirect(url_for("score"))
    return render_template("report.html", team=session["team"], case=case,
                           persons=session.get("persons", {}),
                           findings=session.get("findings", {}),
                           verified=verified_count(case, session.get("findings", {})))


def mcq_score_card(case, answers):
    """Per-station MCQ breakdown: points, per-question rows, cumulative stats."""
    stations = []
    station_points = 0
    correct = 0
    answered_total = 0
    for s in case["stations"]:
        recs = list(answers.get(s["id"], []) or [])
        rows = []
        pts = 0
        for qi in range(MCQ_PER_STATION):
            r = recs[qi] if qi < len(recs) else None
            rows.append(r)
            if r:
                pts += int(r.get("pts") or 0)
                answered_total += 1
                if r["correct"]:
                    correct += 1
        stations.append({"station": s, "rows": rows, "pts": pts,
                         "max": MCQ_STATION_MAX})
        station_points += pts
    station_max = len(case["stations"]) * MCQ_STATION_MAX
    total_questions = len(case["stations"]) * MCQ_PER_STATION
    return {
        "stations": stations, "station_points": station_points,
        "station_max": station_max, "correct": correct,
        "answered_total": answered_total, "total_questions": total_questions,
        "total": station_points, "grand_max": station_max,
    }


@app.route("/score")
@login_required
def score():
    case = current_case()
    answers = _mcq_answers()
    card = mcq_score_card(case, answers)

    try:
        team_db_id = session.get("r1_team")
        if team_db_id:
            admin_ops.save_r2_progress(
                team_db_id, case.get("case_code_raw") or case.get("id") or "",
                {"station_points": card["station_points"],
                 "person_points": 0, "report_points": 0,
                 "total": card["total"],
                 "verified_stations": verified_count(case, answers),
                 "verified_persons": 0,
                 "report_done": bool(session.get("report")),
                 "completed_at": db.now_ms()})
    except Exception as exc:
        __import__("sys").stderr.write("score-persist-error: %r\n" % (exc,))

    return render_template("score.html", team=session["team"], case=case,
                           card=card, answers=answers,
                           next_case=next_case_code(case.get("case_code_raw")))


@app.route("/api/rotate", methods=["POST"])
@login_required
def rotate_case():
    """Advance the participant to the next PUBLISHED case after completing one.

    Server-authoritative: refuses to rotate until every station of the current
    case is answered. Only the per-case state is reset — the 45-minute round
    clock keeps running.
    """
    case = current_case()
    if not case:
        return jsonify({"ok": False, "error": "No case is currently assigned."}), 400
    answers = _mcq_answers()
    complete = all(_station_answered(answers, s) >= MCQ_PER_STATION
                   for s in case["stations"])
    if not complete:
        return jsonify({"ok": False,
                        "error": "Complete the current case before advancing."}), 403
    nxt = next_case_code(case.get("case_code_raw") or case.get("id"))
    if not nxt:
        return jsonify({"ok": False,
                        "error": "No further cases to assign."}), 400
    session["team"]["case"] = nxt
    session["mcq"] = {}
    session["mcq_start"] = {}
    session["findings"] = {}
    session["persons"] = {}
    session["notes"] = {}
    session["attempts"] = {}
    session.pop("report", None)
    return jsonify({"ok": True, "case": nxt,
                    "redirect": url_for("case_study")})


@app.route("/reset")
@login_required
def reset():
    session["findings"] = {}
    session["persons"] = {}
    session.pop("report", None)
    session["notes"] = {}
    session["attempts"] = {}
    session["mcq"] = {}
    session["mcq_start"] = {}
    session.pop("brief_viewed", None)
    # Fresh investigation restarts the 45-minute countdown.
    now = db_now_ms()
    session["r2_started_at"] = now
    session["r2_ends_at"] = now + r2_timer_minutes() * 60 * 1000
    session["r2_status"] = "ACTIVE"
    session.pop("r2_completed_at", None)
    return redirect(url_for("dashboard"))


@app.route("/r2/timeup", methods=["POST"])
@login_required
def r2_timeup():
    """Finalize Round 2 when the 45-minute countdown hits 0.

    Server-authoritative: only marks COMPLETED if the deadline has passed,
    so an early POST can never close the round early. Mirrors r1_timeup.
    """
    timer = get_r2_timer()
    if timer["status"] != "COMPLETED":
        return jsonify({"ok": False, "error": "Session still active.",
                        "remaining_ms": timer["remaining_ms"]})
    return jsonify({"ok": True, "completed": True,
                    "redirect": url_for("score")})


# ---------------------------------------------------------------------------
# ROUND 1 - CYBER PUZZLE
# ---------------------------------------------------------------------------

def challenge_status(cid):
    """Track which challenges the team has solved in the session."""
    solved = session.get("challenges_solved", [])
    return str(cid) in solved


@app.route("/puzzle-lab")
@login_required
def puzzle_lab():
    challenges = []
    for i, ch in enumerate(CHALLENGES):
        item = dict(ch)
        item["solved"] = challenge_status(i)
        challenges.append(item)
    solved_count = sum(1 for c in challenges if c["solved"])
    return render_template("puzzle_lab.html", team=session["team"],
                           challenges=challenges, domains=challenge_domains,
                           solved_count=solved_count)


@app.route("/challenge/<int:cid>")
@login_required
def challenge(cid):
    if cid < 0 or cid >= len(CHALLENGES):
        abort(404)
    ch = dict(CHALLENGES[cid])
    ch["solved"] = challenge_status(cid)
    return render_template("challenge_detail.html", team=session["team"],
                           challenge=ch, cid=cid)


# ---------------------------------------------------------------------------
# ROUND 2 - CASE SELECTOR
# ---------------------------------------------------------------------------

@app.route("/cases")
@login_required
def case_selector():
    current = session["team"]["case"]
    cases_for_view = []
    db_cases = admin_ops.list_r2_cases()
    if db_cases:
        for c in db_cases:
            item = dict(c)
            item["id"] = c["case_code"]
            item["narrative"] = c.get("case_brief") or ""
            stations_view = [{"id": s["station_id"], "name": s["name"]}
                             for s in admin_ops.list_r2_stations(c["id"])
                             if s.get("status") == "PUBLISHED"]
            item["stations"] = stations_view
            item["questions"] = len(stations_view) * MCQ_PER_STATION
            item["persons"] = list(range(admin_ops.r2_person_count(c["id"])))
            cases_for_view.append(item)
    else:
        for cid, c in CASES.items():
            item = dict(c)
            item["id"] = cid
            cases_for_view.append(item)
    return render_template("cases.html", team=session["team"],
                           cases=cases_for_view, current_case=current)


# ---------------------------------------------------------------------------
# ADMIN
# ---------------------------------------------------------------------------

@app.before_request
def _admin_gate_reset():
    """Clear the one-time admin-dashboard entry flag outside the console.

    Any request outside /admin* or /r1/admin* (static files included) resets
    the flag, so every fresh arrival at /admin must enter the password again
    while movement inside the console keeps working once unlocked.
    """
    try:
        path = request.path or ""
        if not (path == "/admin" or path.startswith("/admin/") or
                path.startswith("/r1/admin")):
            session.pop("admin_gate_ok", None)
    except Exception:
        pass


def admin_required(f):
    @wraps(f)
    def admin_wrapper(*args, **kwargs):
        # Only an authenticated administrator (round1 admins table) may access
        # the admin console. Participant sessions can never reach these routes.
        if not access.is_admin():
            return redirect(url_for("r1.r1_admin_login"))
        return f(*args, **kwargs)
    return admin_wrapper


def admin_required_api(f):
    @wraps(f)
    def admin_api_wrapper(*args, **kwargs):
        # JSON/admin APIs return a clean error instead of a redirect so callers
        # (or attackers probing the endpoints) never get pages/session leaks.
        if not access.is_admin():
            return jsonify({"ok": False,
                            "error": "Administrator access required."}), 403
        return f(*args, **kwargs)
    return admin_api_wrapper


@app.route("/admin", methods=["GET", "POST"])
def admin_dashboard():
    # Every fresh visit to the admin dashboard must enter the password first,
    # even with an active admin session. Inner admin pages keep working once
    # unlocked (see _admin_gate_reset).
    if not access.is_admin():
        return redirect(url_for("r1.r1_admin_login"))
    if not session.get("admin_gate_ok"):
        error = None
        if request.method == "POST":
            username = session.get(access.SESSION_ADMIN_KEY)
            if username and access.verify_admin_password(
                    username, request.form.get("password") or ""):
                session["admin_gate_ok"] = True
                return redirect(url_for("admin_dashboard"))
            error = "Incorrect password."
        return render_template("admin_gate.html", error=error,
                               username=session.get(access.SESSION_ADMIN_KEY))
    stats = admin_ops.dashboard_stats()
    activity = admin_ops.recent_activity()
    due = admin_ops.get_round_settings("round1")
    due2 = admin_ops.get_round_settings("round2")
    return render_template("admin/overview.html",
                           status=stats,
                           activity=activity,
                           r1=due, r2=due2,
                           teams=access.list_teams(),
                           rounds_settings={"round1": due, "round2": due2})


@app.route("/admin/teams")
@admin_required
def admin_teams():
    return redirect(url_for("admin_round1_teams"))


@app.route("/admin/team-logins/<round_name>")
@admin_required
def admin_team_logins(round_name):
    """Legacy URL for the credential desk. Kept so old bookmarks still work:
    each round now has its own modern team-management page."""
    if round_name == "round1":
        return redirect(url_for("admin_round1_teams"))
    if round_name == "round2":
        return redirect(url_for("admin_round2_teams"))
    abort(404)


@app.route("/admin/teams/add", methods=["POST"])
@admin_required_api
def admin_team_add():
    data = request.get_json(silent=True) or request.form
    team_name = (data.get("team_name") or "").strip()
    team_id = (data.get("team_id") or "").strip()
    ok, error = access.add_team(team_name, team_id)
    if not ok:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True, "team": access.team_detail(team_id)})


@app.route("/admin/teams/round2-access", methods=["POST"])
@admin_required_api
def admin_team_round2_access():
    data = request.get_json(silent=True) or request.form
    ok, error = access.set_round2_access(data.get("team_name"),
                                         data.get("round2_access_id"))
    if not ok:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True})


@app.route("/admin/teams/<int:team_db_id>/toggle", methods=["POST"])
@admin_required_api
def admin_team_toggle(team_db_id):
    current = access.team_detail(team_db_id)
    if not current:
        return jsonify({"ok": False, "error": "Team not found."}), 404
    ok, error = access.set_team_active(team_db_id, not bool(current.get("is_active")))
    if not ok:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True, "active": access.team_detail(team_db_id)["is_active"]})


@app.route("/admin/teams/<int:team_db_id>/edit", methods=["POST"])
@admin_required_api
def admin_team_edit(team_db_id):
    data = request.get_json(silent=True) or request.form
    is_active = data.get("is_active")
    if isinstance(is_active, str):
        is_active = is_active.lower() in ("1", "true", "on", "yes")
    ok, error = access.update_team(
        team_db_id,
        team_name=data.get("team_name") or None,
        team_id=data.get("team_id") or None,
        participant_names=data.get("participant_names") or None,
        is_active=is_active)
    if not ok:
        code = 404 if error == "Team not found." else 400
        return jsonify({"ok": False, "error": error}), code
    return jsonify({"ok": True, "team": access.team_detail(team_db_id)})


@app.route("/admin/teams/<int:team_db_id>/delete", methods=["POST"])
@admin_required_api
def admin_team_delete(team_db_id):
    row = access.team_detail(team_db_id)
    if not row:
        return jsonify({"ok": False, "error": "Team not found."}), 404
    team_name = row["team_name"]
    ok, err = access.delete_team(team_db_id)
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    admin_ops.audit("admin", "Deleted team", target=team_name)
    return jsonify({"ok": True})


@app.route("/admin/rounds")
@admin_required
def admin_round1():
    return redirect(url_for("admin_round1_overview"))


@app.route("/admin/round2")
@admin_required
def admin_round2():
    return redirect(url_for("admin_round2_overview"))


# ---------------------------------------------------------------------------
# Admin: Round 1 pages
# ---------------------------------------------------------------------------

def _settings_bool(value):
    return 1 if value in (1, True, "1", "true", "True", "on", "yes") else 0


def _save_round_settings(round_name, data):
    """Shared round-settings saver for Round 1 / Round 2."""
    data = dict(data or {})
    for key in ("timer_minutes", "max_attempts"):
        if key in data and data.get(key):
            try:
                data[key] = int(data[key])
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "Invalid %s." % key}), 400
    if "access_enabled" in data:
        data["access_enabled"] = _settings_bool(data["access_enabled"])
    ok, err = admin_ops.update_round_settings(round_name, data)
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    admin_ops.audit("admin", "Updated %s settings" % round_name,
                    target=round_name, detail=", ".join(k for k in data))
    return jsonify({"ok": True})


@app.route("/admin/round1/overview")
@admin_required
def admin_round1_overview():
    settings = admin_ops.get_round_settings("round1")
    stats = admin_ops.dashboard_stats()
    return render_template("admin/round1/overview.html",
                           settings=settings, stats=stats, r1=settings)


@app.route("/admin/round1/settings")
@admin_required
def admin_r1_settings():
    settings = admin_ops.get_round_settings("round1")
    return render_template("admin/round1/settings.html", r1=settings,
                           statuses=admin_ops.ROUND_STATUSES)


@app.route("/admin/round1/status", methods=["POST"])
@admin_required_api
def admin_r1_round_status():
    data = request.get_json(silent=True) or request.form
    ok, err = admin_ops.update_round_settings("round1",
                                              {"status": data.get("status") or ""})
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    admin_ops.audit("admin", "Round 1 status", target="round1",
                    detail="status = %s" % data.get("status"))
    return jsonify({"ok": True, "status": data.get("status")})


@app.route("/admin/round1/settings/save", methods=["POST"])
@admin_required_api
def admin_r1_settings_save():
    return _save_round_settings("round1",
                                request.get_json(silent=True) or request.form)


@app.route("/admin/round1/challenges")
@admin_required
def admin_r1_challenges():
    challenges = admin_ops.list_r1_challenges()
    settings = admin_ops.get_round_settings("round1")
    domains = sorted({c.get("domain") for c in challenges} | {"WEB", "CRYPTO",
                                                               "FORENSICS",
                                                               "NETWORK", "OSINT"})
    return render_template("admin/round1/challenges.html",
                           challenges=challenges, settings=settings,
                           domains=domains)


@app.route("/admin/round1/api/challenge/<int:cid>")
@admin_required_api
def admin_r1_api_challenge(cid):
    challenge = admin_ops.get_r1_challenge(cid)
    if challenge is None:
        return jsonify({"ok": False, "error": "Challenge not found."}), 404
    return jsonify({"ok": True, "item": challenge})


@app.route("/admin/round1/challenges/save", methods=["POST"])
@admin_required_api
def admin_r1_challenge_save():
    data = request.get_json(silent=True) or request.form
    cat_id = data.get("challenge_id")
    if cat_id:
        ok, err = admin_ops.update_r1_challenge(int(cat_id), data)
        label = "updated R1 challenge"
    else:
        ok, err = admin_ops.create_r1_challenge(data)
        label = "created R1 challenge"
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    admin_ops.audit("admin", label, target=data.get("title") or "")
    return jsonify({"ok": True})


@app.route("/admin/round1/challenges/<int:cid>/status", methods=["POST"])
@admin_required_api
def admin_r1_challenge_status(cid):
    data = request.get_json(silent=True) or request.form
    active = _settings_bool(data.get("active"))
    admin_ops.set_r1_challenge_status(cid, active)
    admin_ops.audit("admin", "R1 challenge %s" % ("published" if active else "hidden"),
                    target="#%d" % cid)
    return jsonify({"ok": True, "active": active})


@app.route("/admin/round1/challenges/<int:cid>/delete", methods=["POST"])
@admin_required_api
def admin_r1_challenge_delete(cid):
    result = admin_ops.delete_or_archive_r1_challenge(cid)
    admin_ops.audit("admin", "R1 challenge %s" % result, target="#%d" % cid)
    return jsonify({"ok": True, "action": result})


@app.route("/admin/round1/challenges/<int:cid>/reorder/<direction>", methods=["POST"])
@admin_required_api
def admin_r1_challenge_reorder(cid, direction):
    if direction not in ("up", "down"):
        return jsonify({"ok": False, "error": "Invalid direction."}), 400
    admin_ops.reorder_r1_challenge(cid, direction)
    return jsonify({"ok": True})


@app.route("/admin/round1/questions")
@admin_required
def admin_r1_questions():
    challenges = admin_ops.list_r1_challenges()
    selected = request.args.get("challenge")
    variants = admin_ops.list_r1_variants(int(selected) if selected else None)
    VALIDATION_MODES = ["NORMALIZED", "EXACT", "CONTAINS", "CASE_SENSITIVE"]
    return render_template("admin/round1/questions.html",
                           challenges=challenges, variants=variants,
                           selected=selected, modes=VALIDATION_MODES)


@app.route("/admin/round1/questions/save", methods=["POST"])
@admin_required_api
def admin_r1_question_save():
    data = request.get_json(silent=True) or request.form
    variant_id = data.get("variant_id")
    if variant_id:
        ok, err = admin_ops.update_r1_variant(int(variant_id), data)
        label = "updated R1 question"
    else:
        cat_id = data.get("challenge_category_id")
        if not cat_id:
            return jsonify({"ok": False, "error": "Challenge is required."}), 400
        ok, err = admin_ops.create_r1_variant(int(cat_id), data)
        label = "created R1 question"
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    admin_ops.audit("admin", label, target=data.get("title") or "")
    return jsonify({"ok": True})


@app.route("/admin/round1/questions/<int:vid>")
@admin_required_api
def admin_r1_question_get(vid):
    row = next((v for v in admin_ops.list_r1_variants()
                if v["id"] == vid), None)
    if row is None:
        return jsonify({"ok": False, "error": "Question not found."}), 404
    return jsonify({"ok": True, "question": row})


@app.route("/admin/round1/questions/<int:vid>/delete", methods=["POST"])
@admin_required_api
def admin_r1_question_delete(vid):
    result = admin_ops.delete_r1_variant(vid)
    admin_ops.audit("admin", "R1 question %s" % result, target="#%d" % vid)
    return jsonify({"ok": True, "action": result})


@app.route("/admin/round1/questions/<int:vid>/status", methods=["POST"])
@admin_required_api
def admin_r1_question_status(vid):
    data = request.get_json(silent=True) or request.form
    status = data.get("status") or ""
    if status not in ("PUBLISHED", "ARCHIVED", "DRAFT"):
        return jsonify({"ok": False, "error": "Invalid status."}), 400
    admin_ops.set_r1_variant_status(vid, status)
    admin_ops.audit("admin", "R1 question status", target="#%d" % vid, detail=status)
    return jsonify({"ok": True, "status": status})


@app.route("/admin/round1/validation")
@admin_required
def admin_r1_validation():
    variants = admin_ops.list_r1_variants()
    settings = admin_ops.get_round_settings("round1")
    return render_template("admin/round1/validation.html",
                           variants=variants, r1=settings)


@app.route("/admin/round1/validation/save", methods=["POST"])
@admin_required_api
def admin_r1_validation_save():
    data = request.get_json(silent=True) or request.form
    modes = data.get("modes") or {}
    saved = 0
    for vid, mode in modes.items():
        if str(vid).isdigit() and mode:
            admin_ops.update_r1_variant(int(vid), {"validation_mode": str(mode)})
            saved += 1
    admin_ops.audit("admin", "R1 validation settings", target="round1",
                    detail="updated %d question(s)" % saved)
    return jsonify({"ok": True, "saved": saved})


@app.route("/admin/round1/scoring")
@admin_required
def admin_r1_scoring():
    challenges = admin_ops.list_r1_challenges()
    settings = admin_ops.get_round_settings("round1")
    return render_template("admin/round1/scoring.html",
                           challenges=challenges, r1=settings)


@app.route("/admin/round1/preview/<int:cid>")
@admin_required
def admin_r1_preview(cid):
    challenge = next((c for c in admin_ops.list_r1_challenges()
                      if c["id"] == cid), None)
    if challenge is None:
        abort(404)
    variants = admin_ops.list_r1_variants(cid)
    # Never render answer keys on a preview page (admin-only, but keep it clean).
    for v in variants:
        v.pop("expected_answer", None)
        v.pop("flag", None)
    return render_template("admin/round1/preview.html",
                           challenge=challenge, variants=variants)


# ---------------------------------------------------------------------------
# Admin: Round 2 pages
# ---------------------------------------------------------------------------

@app.route("/admin/round2/overview")
@admin_required
def admin_round2_overview():
    settings = admin_ops.get_round_settings("round2")
    stats = admin_ops.dashboard_stats()
    return render_template("admin/round2/overview.html",
                           settings=settings, stats=stats, r2=settings)


@app.route("/admin/round2/settings")
@admin_required
def admin_r2_settings():
    settings = admin_ops.get_round_settings("round2")
    return render_template("admin/round2/settings.html", r2=settings,
                           statuses=admin_ops.ROUND_STATUSES)


@app.route("/admin/round2/status", methods=["POST"])
@admin_required_api
def admin_r2_round_status():
    data = request.get_json(silent=True) or request.form
    ok, err = admin_ops.update_round_settings("round2",
                                              {"status": data.get("status") or ""})
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    admin_ops.audit("admin", "Round 2 status", target="round2",
                    detail="status = %s" % data.get("status"))
    return jsonify({"ok": True, "status": data.get("status")})


@app.route("/admin/round2/settings/save", methods=["POST"])
@admin_required_api
def admin_r2_settings_save():
    return _save_round_settings("round2",
                                request.get_json(silent=True) or request.form)


@app.route("/admin/round2/cases")
@admin_required
def admin_r2_cases():
    cases = admin_ops.list_r2_cases()
    settings = admin_ops.get_round_settings("round2")
    return render_template("admin/round2/cases.html",
                           cases=cases, r2=settings,
                           statuses=admin_ops.CASE_STATUSES)


@app.route("/admin/round2/cases/save", methods=["POST"])
@admin_required_api
def admin_r2_case_save():
    data = request.get_json(silent=True) or request.form
    case_id = data.get("case_id")
    if case_id:
        ok, err = admin_ops.update_round2_case(int(case_id), data)
        label = "updated R2 case"
    else:
        ok, err = admin_ops.create_round2_case(data)
        label = "created R2 case"
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    admin_ops.audit("admin", label, target=data.get("title") or "")
    return jsonify({"ok": True})


@app.route("/admin/round2/cases/<int:cid>/status", methods=["POST"])
@admin_required_api
def admin_r2_case_status(cid):
    data = request.get_json(silent=True) or request.form
    status = data.get("status") or ""
    if status not in admin_ops.CASE_STATUSES:
        return jsonify({"ok": False, "error": "Invalid status."}), 400
    ok, _ = admin_ops.update_round2_case(cid, {"status": status})
    admin_ops.audit("admin", "R2 case status", target="#%d" % cid, detail=status)
    return jsonify({"ok": True, "status": status})


@app.route("/admin/round2/cases/<int:cid>/delete", methods=["POST"])
@admin_required_api
def admin_r2_case_delete(cid):
    result = admin_ops.delete_round2_case(cid)
    admin_ops.audit("admin", "R2 case %s" % result, target="#%d" % cid)
    return jsonify({"ok": True, "action": result})


@app.route("/admin/round2/cases/<int:cid>/reorder/<direction>", methods=["POST"])
@admin_required_api
def admin_r2_case_reorder(cid, direction):
    if direction not in ("up", "down"):
        return jsonify({"ok": False, "error": "Invalid direction."}), 400
    admin_ops.reorder_item("r2_cases", cid, direction)
    return jsonify({"ok": True})


@app.route("/admin/round2/cases/<int:cid>")
@admin_required
def admin_r2_case_detail(cid):
    case = admin_ops.get_round2_case(cid)
    if case is None:
        abort(404)
    stations = admin_ops.list_r2_stations(cid)
    persons = admin_ops.list_r2_persons(cid)
    evidence = admin_ops.list_r2_evidence(cid)
    return render_template("admin/round2/case_detail.html",
                           case=case, stations=stations, persons=persons,
                           evidence=evidence,
                           statuses=admin_ops.CASE_STATUSES,
                           evidence_types=admin_ops.EVIDENCE_TYPES,
                           station_statuses=admin_ops.STATION_STATUSES)


@app.route("/admin/round2/tasks")
@admin_required
def admin_r2_tasks():
    cases = admin_ops.list_r2_cases()
    selected = request.args.get("case")
    stations = admin_ops.list_r2_stations(int(selected)) if selected else []
    for s in stations:
        bank = admin_ops.parse_mcq_json(s.get("mcq_json"))
        s["mcq_count"] = len(bank["mcqs"])
    return render_template("admin/round2/tasks.html",
                           cases=cases, selected=selected, stations=stations)


@app.route("/admin/round2/api/case/<int:case_id>")
@admin_required_api
def admin_r2_api_case(case_id):
    case = admin_ops.get_round2_case(case_id)
    if case is None:
        return jsonify({"ok": False, "error": "Case not found."}), 404
    return jsonify({"ok": True, "item": case})


@app.route("/admin/round2/api/station/<int:sid>")
@admin_required_api
def admin_r2_api_station(sid):
    for cid in [r["id"] for r in admin_ops.list_r2_cases()]:
        for s in admin_ops.list_r2_stations(cid):
            if s["id"] == sid:
                return jsonify({"ok": True, "item": s})
    return jsonify({"ok": False, "error": "Task not found."}), 404


@app.route("/admin/round2/api/person/<int:pid>")
@admin_required_api
def admin_r2_api_person(pid):
    for cid in [r["id"] for r in admin_ops.list_r2_cases()]:
        for p in admin_ops.list_r2_persons(cid):
            if p["id"] == pid:
                return jsonify({"ok": True, "item": p})
    return jsonify({"ok": False, "error": "Person not found."}), 404


@app.route("/admin/round2/api/evidence/<int:eid>")
@admin_required_api
def admin_r2_api_evidence(eid):
    item = next((e for e in admin_ops.list_r2_evidence()
                 if e["id"] == eid), None)
    if item is None:
        return jsonify({"ok": False, "error": "Evidence not found."}), 404
    return jsonify({"ok": True, "item": item})


@app.route("/admin/round2/tasks/save", methods=["POST"])
@admin_required_api
def admin_r2_task_save():
    data = request.get_json(silent=True) or request.form
    station_id = data.get("station_id_pk")
    if station_id:
        ok, err = admin_ops.update_r2_station(int(station_id), data)
        label = "updated R2 task"
    else:
        case_id = data.get("case_id")
        if not case_id:
            return jsonify({"ok": False, "error": "Case is required."}), 400
        ok, err = admin_ops.create_r2_station(int(case_id), data)
        label = "created R2 task"
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    admin_ops.audit("admin", label, target=data.get("name") or "")
    return jsonify({"ok": True})


@app.route("/admin/round2/tasks/<int:sid>/delete", methods=["POST"])
@admin_required_api
def admin_r2_task_delete(sid):
    admin_ops.delete_r2_station(sid)
    admin_ops.audit("admin", "deleted R2 task", target="#%d" % sid)
    return jsonify({"ok": True})


@app.route("/admin/round2/tasks/<int:sid>/status", methods=["POST"])
@admin_required_api
def admin_r2_task_status(sid):
    data = request.get_json(silent=True) or request.form
    status = data.get("status") or ""
    if status not in admin_ops.STATION_STATUSES:
        return jsonify({"ok": False, "error": "Invalid status."}), 400
    admin_ops.set_r2_station_status(sid, status)
    admin_ops.audit("admin", "R2 task status", target="#%d" % sid, detail=status)
    return jsonify({"ok": True, "status": status})


@app.route("/admin/round2/tasks/<int:sid>/reorder/<direction>", methods=["POST"])
@admin_required_api
def admin_r2_task_reorder(sid, direction):
    if direction not in ("up", "down"):
        return jsonify({"ok": False, "error": "Invalid direction."}), 400
    admin_ops.reorder_item("r2_stations", sid, direction)
    return jsonify({"ok": True})


@app.route("/admin/round2/questions")
@admin_required
def admin_r2_questions():
    cases = admin_ops.list_r2_cases()
    selected = request.args.get("case")
    persons = admin_ops.list_r2_persons(int(selected)) if selected else []
    return render_template("admin/round2/questions.html",
                           cases=cases, selected=selected, persons=persons)


@app.route("/admin/round2/persons/save", methods=["POST"])
@admin_required_api
def admin_r2_person_save():
    data = request.get_json(silent=True) or request.form
    person_id = data.get("person_id")
    answers = data.get("answers")
    if isinstance(answers, str):
        try:
            answers = [a.strip() for a in answers.replace("\n", ",").split(",")
                       if a.strip()]
        except Exception:
            answers = []
    if person_id:
        ok, err = admin_ops.update_r2_person(int(person_id), {
            "role": data.get("role"), "person_key": data.get("person_key"),
            "clue": data.get("clue"), "answers": answers})
        label = "updated R2 person"
    else:
        case_id = data.get("case_id")
        if not case_id:
            return jsonify({"ok": False, "error": "Case is required."}), 400
        ok, err = admin_ops.create_r2_person(int(case_id), {
            "role": data.get("role"), "person_key": data.get("person_key"),
            "clue": data.get("clue"), "answers": answers or []})
        label = "added R2 person"
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    admin_ops.audit("admin", label, target=data.get("role") or "")
    return jsonify({"ok": True})


@app.route("/admin/round2/persons/<int:pid>/delete", methods=["POST"])
@admin_required_api
def admin_r2_person_delete(pid):
    admin_ops.delete_r2_person(pid)
    admin_ops.audit("admin", "deleted R2 person", target="#%d" % pid)
    return jsonify({"ok": True})


@app.route("/admin/round2/validation")
@admin_required
def admin_r2_validation():
    cases = admin_ops.list_r2_cases()
    selected = request.args.get("case")
    stations = admin_ops.list_r2_stations(int(selected)) if selected else []
    settings = admin_ops.get_round_settings("round2")
    return render_template("admin/round2/validation.html",
                           cases=cases, selected=selected,
                           stations=stations, r2=settings)


@app.route("/admin/round2/validation/save", methods=["POST"])
@admin_required_api
def admin_r2_validation_save():
    data = request.get_json(silent=True) or request.form
    modes = data.get("modes") or {}
    saved = 0
    for sid, mode in modes.items():
        if str(sid).isdigit() and mode:
            admin_ops.update_r2_station(int(sid), {"validation_mode": str(mode)})
            saved += 1
    admin_ops.audit("admin", "R2 validation settings", target="round2",
                    detail="updated %d task(s)" % saved)
    return jsonify({"ok": True, "saved": saved})


@app.route("/admin/round2/scoring")
@admin_required
def admin_r2_scoring():
    cases = admin_ops.list_r2_cases()
    settings = admin_ops.get_round_settings("round2")
    return render_template("admin/round2/scoring.html",
                           cases=cases, r2=settings)


@app.route("/admin/round2/evidence")
@admin_required
def admin_r2_evidence():
    cases = admin_ops.list_r2_cases()
    selected = request.args.get("case")
    evidence = admin_ops.list_r2_evidence(int(selected)) if selected else []
    return render_template("admin/round2/evidence.html",
                           cases=cases, selected=selected, evidence=evidence,
                           evidence_types=admin_ops.EVIDENCE_TYPES)


@app.route("/admin/round2/evidence/save", methods=["POST"])
@admin_required_api
def admin_r2_evidence_save():
    data = request.get_json(silent=True) or request.form
    evidence_id = data.get("evidence_id")
    if evidence_id:
        ok, err = admin_ops.update_r2_evidence(int(evidence_id), data)
        label = "updated R2 evidence"
    else:
        case_id = data.get("case_id")
        if not case_id:
            return jsonify({"ok": False, "error": "Case is required."}), 400
        ok, err = admin_ops.create_r2_evidence(int(case_id), data)
        label = "added R2 evidence"
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    admin_ops.audit("admin", label, target=data.get("name") or "")
    return jsonify({"ok": True})


@app.route("/admin/round2/evidence/<int:eid>/delete", methods=["POST"])
@admin_required_api
def admin_r2_evidence_delete(eid):
    admin_ops.delete_r2_evidence(eid)
    admin_ops.audit("admin", "deleted R2 evidence", target="#%d" % eid)
    return jsonify({"ok": True})


@app.route("/admin/round2/evidence/upload", methods=["POST"])
@admin_required_api
def admin_r2_evidence_upload():
    case_id = request.form.get("case_id")
    if not case_id or not str(case_id).isdigit():
        return jsonify({"ok": False, "error": "Case is required."}), 400
    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify({"ok": False, "error": "Choose a file to upload."}), 400
    filename = os.path.basename(file.filename)
    if not os.path.isdir(EVIDENCE_DIR):
        os.makedirs(EVIDENCE_DIR, exist_ok=True)
    filepath = os.path.join(EVIDENCE_DIR, filename)
    file.save(filepath)
    with open(filepath, "rb") as fh:
        fh.read()
    ok, err = admin_ops.create_r2_evidence(int(case_id), {
        "name": request.form.get("name") or filename,
        "evidence_code": request.form.get("evidence_code") or "",
        "evidence_type": request.form.get("evidence_type") or "OTHER",
        "description": request.form.get("description") or "",
        "filename": filename,
        "file_size": os.path.getsize(filepath),
    })
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    admin_ops.audit("admin", "uploaded R2 evidence", target=filename)
    return jsonify({"ok": True, "filename": filename})


@app.route("/admin/round2/preview/<int:cid>")
@admin_required
def admin_r2_case_preview(cid):
    case = admin_ops.get_round2_case(cid)
    if case is None:
        abort(404)
    stations = admin_ops.list_r2_stations(cid)
    for s in stations:
        s["answer"] = ""
        bank = admin_ops.parse_mcq_json(s.get("mcq_json"))
        for m in bank["mcqs"]:
            m.pop("answer", None)
        s["mcqs"] = bank["mcqs"]
    persons = admin_ops.list_r2_persons(cid)
    return render_template("admin/round2/preview.html",
                           case=case, stations=stations, persons=persons)


# ---------------------------------------------------------------------------
# Admin: Team members (round-scoped)
# ---------------------------------------------------------------------------

@app.route("/admin/teams/round1")
@admin_required
def admin_round1_teams():
    teams = admin_ops.list_teams_for_round("round1")
    return render_template("admin/teams_round1.html", teams=teams,
                           round_name="round1", credential_field="round1_access_id")


@app.route("/admin/teams/round2")
@admin_required
def admin_round2_teams():
    teams = admin_ops.list_teams_for_round("round2")
    return render_template("admin/teams_round2.html", teams=teams,
                           round_name="round2", credential_field="round2_access_id")


@app.route("/admin/teams/round/add", methods=["POST"])
@admin_required_api
def admin_round_team_add():
    data = request.get_json(silent=True) or request.form
    round_name = data.get("round_name")
    team_name = (data.get("team_name") or "").strip()
    access_id = (data.get("access_id") or "").strip()
    if round_name not in ("round1", "round2"):
        return jsonify({"ok": False, "error": "Invalid round."}), 400
    if not team_name or not access_id:
        return jsonify({"ok": False, "error": "Team name and ID are required."}), 400
    if round_name == "round1":
        ok, error = access.add_team(team_name, access_id)
    else:
        ok, error = admin_ops.create_round2_team(team_name, access_id)
    if not ok:
        return jsonify({"ok": False, "error": error}), 400
    admin_ops.audit("admin", "Created %s team" % round_name, target=team_name)
    return jsonify({"ok": True, "team": access.team_detail(access_id)})


@app.route("/admin/teams/<int:team_db_id>/profile")
@admin_required
def admin_team_profile(team_db_id):
    profile = admin_ops.team_profile(team_db_id)
    if profile is None:
        abort(404)
    return render_template("admin/team_profile.html", profile=profile)


@app.route("/admin/teams/<int:team_db_id>/round/<round_name>/toggle", methods=["POST"])
@admin_required_api
def admin_team_round_toggle(team_db_id, round_name):
    if round_name not in ("round1", "round2"):
        return jsonify({"ok": False, "error": "Invalid round."}), 400
    row = access.team_detail(team_db_id)
    if not row:
        return jsonify({"ok": False, "error": "Team not found."}), 404
    enabled_key = "%s_enabled" % round_name
    target = not bool(row.get(enabled_key, 0))
    admin_ops.set_round_access(team_db_id, round_name, target)
    admin_ops.audit("admin", "%s team %s" % (
        "Enabled" if target else "Disabled", round_name), target=row["team_name"])
    return jsonify({"ok": True, "enabled": target})


@app.route("/admin/teams/<int:team_db_id>/round/<round_name>/access-id", methods=["POST"])
@admin_required_api
def admin_team_set_round_access_id(team_db_id, round_name):
    if round_name not in ("round1", "round2"):
        return jsonify({"ok": False, "error": "Invalid round."}), 400
    data = request.get_json(silent=True) or request.form
    new_id = (data.get("access_id") or "").strip()
    if not new_id:
        return jsonify({"ok": False, "error": "Access ID is required."}), 400
    ok, err = admin_ops.set_round_access_id(team_db_id, round_name, new_id)
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    admin_ops.audit("admin", "Rotated %s access ID" % round_name,
                    target="#%d" % team_db_id)
    return jsonify({"ok": True})


@app.route("/admin/teams/<int:team_db_id>/round/<round_name>/reset", methods=["POST"])
def admin_team_round_reset(team_db_id, round_name):
    if round_name not in ("round1", "round2"):
        return jsonify({"ok": False, "error": "Invalid round."}), 400
    ok = admin_ops.reset_team_round_progress(team_db_id, round_name)
    if not ok:
        return jsonify({"ok": False, "error": "Team not found."}), 404
    admin_ops.audit("admin", "Reset %s progress" % round_name,
                    target="#%d" % team_db_id)
    return jsonify({"ok": True})


@app.route("/admin/logins/clear", methods=["POST"])
@admin_required_api
def admin_login_clear():
    data = request.get_json(silent=True) or request.form
    team_db_id = data.get("team_db_id")
    if not team_db_id:
        return jsonify({"ok": False, "error": "Team required."}), 400
    round_name = data.get("round_name")
    if round_name in ("round1", "round2"):
        admin_ops.clear_round_logins(int(team_db_id), round_name)
    else:
        access.clear_login_by_team(int(team_db_id))
    return jsonify({"ok": True})


@app.route("/admin/logins/clear-selected", methods=["POST"])
@admin_required_api
def admin_login_clear_selected():
    data = request.get_json(silent=True) or request.form
    ids = data.get("team_db_ids") or []
    round_name = data.get("round_name")
    admin_ops.clear_selected_round_logins(ids, round_name)
    return jsonify({"ok": True})


@app.route("/admin/logins/clear-all", methods=["POST"])
@admin_required_api
def admin_login_clear_all():
    data = request.get_json(silent=True) or request.form
    round_name = data.get("round_name")
    cleared = admin_ops.delete_all_teams()
    admin_ops.audit("admin", "Cleared %s logins" % (round_name or "all"),
                    detail="deleted %d team(s) entirely" % cleared)
    return jsonify({"ok": True, "deleted": cleared})


@app.route("/admin/teams/import", methods=["POST"])
@admin_required_api
def admin_teams_import():
    data = request.get_json(silent=True) or request.form
    round_name = data.get("round_name") or "round1"
    result = admin_ops.import_teams(data.get("csv") or "", round_name)
    if result.get("errors"):
        return jsonify({"ok": False,
                        "error": "Some rows failed: %s" % "; ".join(result["errors"][:8]),
                        "result": result}), 400
    admin_ops.audit("admin", "Imported teams", target=round_name,
                    detail="%d imported" % result.get("imported", 0))
    return jsonify({"ok": True, "result": result})


@app.route("/admin/teams/export")
@admin_required
def admin_teams_export():
    round_name = request.args.get("round") or "round1"
    csv_text = admin_ops.export_teams(round_name)
    resp = Response(csv_text, mimetype="text/csv")
    resp.headers["Content-Disposition"] = \
        "attachment; filename=teams_%s.csv" % round_name
    return resp


# ---------------------------------------------------------------------------
# Admin: monitoring / audit / system
# ---------------------------------------------------------------------------

@app.route("/admin/monitoring")
@admin_required
def admin_monitoring():
    sessions = admin_ops.live_monitoring()
    stats = admin_ops.dashboard_stats()
    return render_template("admin/monitoring.html", sessions=sessions, stats=stats)


@app.route("/admin/audit-log")
@admin_required
def admin_audit_log():
    entries = admin_ops.list_audit(250)
    return render_template("admin/audit.html", entries=entries)


@app.route("/admin/audit")
@admin_required
def admin_audit():
    return redirect(url_for("admin_audit_log"))


@app.route("/admin/system")
@admin_required
def admin_system():
    stats = admin_ops.system_stats()
    db_size = 0
    dbpath = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "round1", "round1.db")
    try:
        db_size = os.path.getsize(dbpath)
    except OSError:
        db_size = 0
    return render_template("admin/system.html", stats=stats, db_size=db_size)


@app.route("/admin/submissions")
@admin_required
def admin_submissions():
    submissions = admin_ops.list_submissions(250)
    return render_template("admin/submissions.html", submissions=submissions)


@app.route("/admin/review")
@admin_required
def admin_review():
    reports = admin_ops.list_r2_reviews()
    return render_template("admin/review.html", reports=reports)


@app.route("/admin/leaderboard")
@admin_required
def admin_leaderboard():
    r1 = admin_ops.leaderboard()
    r2 = admin_ops.r2_leaderboard()
    return render_template("admin/leaderboard.html", leaderboard=r1, r2_leaderboard=r2)


@app.route("/admin/content/round1")
@admin_required
def admin_content_round1():
    return redirect(url_for("admin_r1_challenges"))


@app.route("/admin/content/round2")
@admin_required
def admin_content_round2():
    return redirect(url_for("admin_r2_cases"))


# Register Round 1 (Cyber Puzzle) blueprint
from round1.main import r1
app.register_blueprint(r1)

# Register MYSTERY TRACE R1 (Round 1 rebuild) blueprint
from round1.mt import mt as mt1
app.register_blueprint(mt1)


if __name__ == "__main__":
    _host = os.environ.get("HOST", "127.0.0.1")
    _port = int(os.environ.get("PORT", "5000"))
    print("==============================================")
    print(" CYBER INVESTIGATION - FORENSIC INVESTIGATION APP")
    print(f" Running at: http://{_host}:{_port}")
    print("==============================================")
    app.run(host=_host, port=_port, debug=False, threaded=True)
