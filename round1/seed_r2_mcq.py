"""Round 2 - MCQ Quiz: seed the MCQ question bank.

Populates the Round 2 library (cases + MCQ stations) from
``round1.mcq_questions``. Idempotent: existing cases/stations are left as-is,
missing ones are inserted.

Usage:
    python -m round1.seed_r2_mcq          # wipe old content, then seed
    python -m round1.seed_r2_mcq --no-wipe   # add/update new cases, keep progress
    python -m round1.seed_r2_mcq --stub      # dev-only placeholder content
"""
import json
import sys

import round1.db as db
import round1.mcq_questions as QUESTIONS

LETTER_TO_INDEX = {"A": 0, "B": 1, "C": 2, "D": 3}
DOMAINS = ["IDENTIFY", "COLLECT", "ANALYZE", "PRESERVE", "REPORT"]


def _letter(v):
    if isinstance(v, int):
        if v not in range(4):
            raise ValueError("answer index out of range: %r" % v)
        return v
    s = str(v).strip().upper()
    if s not in LETTER_TO_INDEX:
        raise ValueError("answer must be A-D or 0-3, got %r" % (v,))
    return LETTER_TO_INDEX[s]


def _validate(cases):
    """Return (ok, error). Enforces the 5 x 3 per-case contract with real text."""
    if not cases or len(cases) > 10:
        return False, "Expected between 1 and 10 cases, got %d." % len(cases)
    for i, case in enumerate(cases, start=1):
        code = "case%d" % i
        st = case.get("stations") or {}
        if not isinstance(st, dict) or len(st) != 5:
            return False, "%s must define exactly 5 stations." % code
        for j, sid in enumerate(("S1", "S2", "S3", "S4", "S5"), start=1):
            sn = st.get(sid)
            if not sn:
                return False, "%s is missing station %s." % (code, sid)
            if sn.get("domain", "").upper() != DOMAINS[j - 1]:
                return False, "%s/%s domain must be %s." % (code, sid, DOMAINS[j - 1])
            mcqs = sn.get("mcqs") or []
            if len(mcqs) != 3:
                return False, "%s/%s must carry exactly 3 MCQs." % (code, sid)
            for k, m in enumerate(mcqs, start=1):
                q = str(m.get("q") or "").strip()
                opts = [str(o or "").strip() for o in (m.get("options") or [])]
                if q.startswith("[Q]") or not q or q in ("(1) [Q]", "(2) [Q]", "(3) [Q]"):
                    return False, ("%s/%s MCQ%d text is still a placeholder — "
                                   "paste the real questions first." % (code, sid, k))
                if any("[" in o and o.startswith("[") for o in opts) or len(opts) != 4:
                    return False, "%s/%s MCQ%d needs exactly 4 real options." % (code, sid, k)
                _letter(m.get("answer"))
    return True, ""


def _build_mcq_bank(station):
    mcqs = []
    for m in station.get("mcqs") or []:
        mcqs.append({
            "q": str(m["q"]).strip(),
            "options": [str(o).strip() for o in (m["options"] or [])],
            "answer": _letter(m.get("answer")),
        })
    return mcqs


def seed(validate=True, wipe=True):
    """Seed the MCQ bank. Returns (ok, error).

    wipe=True drops Round 2 content (cases, stations, persons, evidence and
    progress) before seeding. wipe=False is additive: cases 5..10 can be
    pasted later and seeded without touching existing data.
    """
    cases = QUESTIONS.CASES
    if validate:
        ok, err = _validate(cases)
        if not ok:
            return False, err
    conn = db.get_connection()
    try:
        now = db.now_ms()
        if wipe:
            # Children first, then per-team progress, then the case library.
            conn.execute("DELETE FROM r2_progress")
            conn.execute("DELETE FROM r2_evidence")
            conn.execute("DELETE FROM r2_persons")
            conn.execute("DELETE FROM r2_stations")
            conn.execute("DELETE FROM r2_cases")
        for i, case in enumerate(cases, start=1):
            code = "case%d" % i
            row = conn.execute("SELECT id FROM r2_cases WHERE case_code=?",
                               (code,)).fetchone()
            if row is None:
                cur = conn.execute(
                    "INSERT INTO r2_cases (case_code, title, case_type, description, "
                    "objective, case_brief, company, difficulty, time_limit, points, "
                    "status, display_order, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (code, case.get("title", code), "SIMULATED CYBERCRIME", "",
                     case.get("objective", ""), case.get("case_brief", ""),
                     case.get("company", ""), "MEDIUM", 45, 375, "PUBLISHED",
                     i, now, now))
                case_id = cur.lastrowid
            else:
                case_id = row["id"]
            for j, sid in enumerate(("S1", "S2", "S3", "S4", "S5"), start=1):
                sn = case["stations"][sid]
                exists = conn.execute(
                    "SELECT 1 FROM r2_stations WHERE case_id=? AND station_id=?",
                    (case_id, sid)).fetchone()
                if exists:
                    continue
                conn.execute(
                    "INSERT INTO r2_stations (case_id, station_id, name, domain, "
                    "description, evidence, question, answer, hint, points, "
                    "max_attempts, validation_mode, mcq_json, display_order, status, "
                    "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (case_id, sid, sn.get("name", sid), sn.get("domain", DOMAINS[j - 1]),
                     "", "", sn.get("question", ""), "", "", 75, 1, "NORMALIZED",
                     json.dumps({"mcqs": _build_mcq_bank(sn)}), j, "PUBLISHED",
                     now, now))
        conn.commit()
        return True, "Seeded %d cases x 5 stations x 3 MCQs." % len(cases)
    except Exception as exc:  # pragma: no cover - defensive rollback
        conn.rollback()
        return False, "Seed failed: %r" % (exc,)
    finally:
        conn.close()


def stub():
    """Dev-only: seed placeholder content so the quiz engine can be smoke-tested."""
    QUESTIONS.CASES = QUESTIONS.blank_cases(10)
    ok, err = seed(validate=False)
    return ok, err


def main():
    if "--stub" in sys.argv:
        ok, err = stub()
    else:
        wipe = "--no-wipe" not in sys.argv
        ok, err = seed(wipe=wipe)
    if not ok:
        sys.stderr.write("ERROR: %s\n" % err)
        sys.exit(1)
    print(err)


if __name__ == "__main__":
    main()