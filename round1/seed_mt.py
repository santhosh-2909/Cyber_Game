"""SHADOW HUNT Round 1 — content seeder (Shadow Hunt challenge catalogue).

Re-runnable (idempotent) upsert that loads the full 18-challenge catalogue
(6 challenges x variants A/B/C) from ``round1.mt_catalog`` into
``challenge_categories`` / ``challenge_variants`` plus optional DEV test
teams.

Usage:
    python -m round1.seed_mt                      # upsert catalogue only
    python -m round1.seed_mt --with-test-teams    # + 20 DEV-TEAM-xx teams
    python -m round1.seed_mt --reset-catalog      # PERMANENTLY purge old
                                                  # Round 1 content + progress,
                                                  # then reseed the 18
    python -m round1.seed_mt --remove-test-teams  # delete DEV-teams + their data

Answers / flags / accept forms live ONLY server-side (DB). The frontend is
only ever given generated evidence + public game_config.
"""
import argparse
import sys
from datetime import datetime

import round1.db as db
from round1.evidence import generate_evidence
from round1.mt_catalog import catalogue, DOMAIN_META


def _ts():
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def _json(obj):
    import json
    return json.dumps(obj, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Categories (the 6 Shadow Hunt challenges). Removes legacy content on reset.
# ---------------------------------------------------------------------------

def seed_categories(conn, reset=False, verbose=True):
    """Ensure the 6 Shadow Hunt challenge_categories exist (upsert by code).

    With reset=True the ENTIRE old Round 1 catalogue and all Round 1 progress
    (legacy categories, variants, sessions, assignments, submissions, hint
    usage and lab events) is deleted first so no legacy data survives.
    """
    if reset:
        _purge_round1_data(conn)
    cats = {r["challenge_code"].upper() for r in conn.execute(
        "SELECT challenge_code FROM challenge_categories").fetchall()}
    added = 0
    for idx, (domain, (cat_code, title, difficulty, points)) in enumerate(
            DOMAIN_META.items(), start=1):
        if cat_code in cats:
            conn.execute(
                "UPDATE challenge_categories SET title=?, domain=?, "
                "difficulty=?, points=?, active=1, display_order=? "
                "WHERE challenge_code=?",
                (title, title, difficulty, points, idx, cat_code))
        else:
            conn.execute(
                "INSERT INTO challenge_categories (challenge_code, title, "
                "domain, description, difficulty, points, active, display_order) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (cat_code, title, title,
                 "SHADOW HUNT Round 1 challenge: %s" % title,
                 difficulty, points, 1, idx))
            added += 1
        cats.add(cat_code)
    if verbose:
        sys.stdout.write("seed_categories: %d created, %d ensured\n"
                         % (added, len(DOMAIN_META)))
    return added


def _purge_round1_data(conn):
    """Permanently delete old Round 1 catalogue + progress (FK-safe order)."""
    conn.execute(
        "DELETE FROM hint_usage WHERE assignment_id IN "
        "(SELECT id FROM team_challenge_assignments)")
    conn.execute(
        "DELETE FROM lab_events WHERE session_id IN "
        "(SELECT id FROM round_sessions)")
    conn.execute(
        "DELETE FROM submissions WHERE session_id IN "
        "(SELECT id FROM round_sessions)")
    conn.execute("DELETE FROM team_challenge_assignments")
    conn.execute("DELETE FROM round_sessions")
    conn.execute("DELETE FROM challenge_variants")
    conn.execute("DELETE FROM challenge_categories")
    for tbl in ("round_sessions", "team_challenge_assignments", "submissions",
                "hint_usage", "lab_events", "challenge_variants",
                "challenge_categories"):
        conn.execute("DELETE FROM sqlite_sequence WHERE name=?", (tbl,))


def reset_round(conn=None, clear_participant_sessions=True):
    """Admin "reset round": wipe Round 1 play data + logins, then reseed the
    Shadow Hunt catalogue. Teams are KEPT so the same users can log in again.

    Clears only round_name='round1' participant sessions so Round 2 logins
    are untouched. Returns a counts dict for the admin banner.
    """
    own = conn is None
    if own:
        conn = db.get_connection()
    try:
        _purge_round1_data(conn)
        seed_categories(conn, reset=False, verbose=False)
        seed_variants(conn, verbose=False)
        cleared = 0
        if clear_participant_sessions:
            cur = conn.execute(
                "UPDATE participant_sessions SET status='CLEARED' "
                "WHERE round_name='round1' AND status='ACTIVE'")
            cleared = cur.rowcount
        conn.commit()
        return {"categories": len(DOMAIN_META),
                "variants": len(catalogue()),
                "cleared_logins": cleared}
    finally:
        if own:
            conn.close()


# ---------------------------------------------------------------------------
# Variants (the 18-challenge upsert)
# ---------------------------------------------------------------------------

def seed_variants(conn, verbose=True):
    cats = {r["challenge_code"].upper(): r for r in conn.execute(
        "SELECT * FROM challenge_categories").fetchall()}
    missing = [code for code in (m[0] for m in DOMAIN_META.values())
               if code not in cats]
    if missing:
        raise SystemExit("Aborting: missing categories %s. Run seed_categories "
                         "first (or `--reset-catalog`)." % sorted(missing))

    mt_codes = {ch["code"] for ch in catalogue()}
    # Converge: drop old variants that are not in the MT catalogue and are not
    # referenced by any historical assignment (kept rows are inert).
    legacy = conn.execute(
        "SELECT v.id, v.variant_code FROM challenge_variants v "
        "LEFT JOIN team_challenge_assignments a ON a.variant_id = v.id "
        "GROUP BY v.id HAVING COUNT(a.id) = 0").fetchall()
    gone = 0
    for row in legacy:
        if row["variant_code"] not in mt_codes:
            conn.execute("DELETE FROM challenge_variants WHERE id=?",
                         (row["id"],))
            gone += 1

    n_new, n_upd = 0, 0
    for ch in catalogue():
        payload, cfg = _evidence_for(ch)
        evidence_payload = _json({"evidence": payload, "config": cfg})
        public_cfg = {"domain": ch["domain"], "variant": ch["code"]}
        public_cfg.update(ch["cfg"])
        lab_data = _json({"accept": ch["accept"]}) if ch["accept"] else "{}"
        row = conn.execute(
            "SELECT id FROM challenge_variants WHERE challenge_category_id=? "
            "AND variant_code=?",
            (cats[ch["cat_code"]]["id"], ch["code"])).fetchone()
        common = {
            "title": ch["title"],
            "question": ch["q"],
            "task_description": ch["q"],
            "provided_data": _json({"domain": ch["domain"],
                                    "game_type": ch["game_type"]}),
            "expected_answer": ch["answer"],
            "flag": ch["flag"],
            "difficulty": ch.get("difficulty", "Medium"),
            "hint": ch["hint"],
            "explanation": ch["hint"],
            "estimated_solve_time": ch.get("solve_time", "15s"),
            "game_type": ch["game_type"],
            "evidence_config": evidence_payload,
            "game_config": _json(public_cfg),
            "lab_type": ch["game_type"],
            "lab_data": lab_data,
            "status": "PUBLISHED",
            "display_order": 1,
        }
        if row is None:
            conn.execute(
                "INSERT INTO challenge_variants (challenge_category_id, "
                "variant_code, title, question, task_description, "
                "provided_data, expected_answer, flag, difficulty, hint, "
                "explanation, estimated_solve_time, game_type, evidence_config, "
                "game_config, lab_type, lab_data, status, display_order) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cats[ch["cat_code"]]["id"], ch["code"], common["title"],
                 common["question"], common["task_description"],
                 common["provided_data"], common["expected_answer"],
                 common["flag"], common["difficulty"], common["hint"],
                 common["explanation"], common["estimated_solve_time"],
                 common["game_type"], common["evidence_config"],
                 common["game_config"], common["lab_type"],
                 common["lab_data"], common["status"], common["display_order"]))
            n_new += 1
        else:
            conn.execute(
                "UPDATE challenge_variants SET title=?, question=?, "
                "task_description=?, provided_data=?, expected_answer=?, "
                "flag=?, difficulty=?, hint=?, explanation=?, "
                "estimated_solve_time=?, game_type=?, evidence_config=?, "
                "game_config=?, lab_type=?, lab_data=?, status=?, display_order=? "
                "WHERE id=?",
                (common["title"], common["question"], common["task_description"],
                 common["provided_data"], common["expected_answer"],
                 common["flag"], common["difficulty"], common["hint"],
                 common["explanation"], common["estimated_solve_time"],
                 common["game_type"], common["evidence_config"],
                 common["game_config"], common["lab_type"], common["lab_data"],
                 common["status"], common["display_order"], row["id"]))
            n_upd += 1
    if verbose:
        sys.stdout.write("seed_variants: %d new, %d updated, %d legacy "
                         "removed\n" % (n_new, n_upd, gone))
    return n_new, n_upd, gone


def _evidence_for(ch):
    """Return (evidence_payload, generator_config) for a catalogue entry.

    Generator entries ({"type": ...} e.g. binary/octal/hex/caesar/hash/chain)
    have their evidence computed server-side from the canonical answer.
    Static entries ship their object as the evidence payload.
    """
    ev = ch["ev"]
    if isinstance(ev, dict) and ev.get("type"):
        cfg = dict(ev)
        payload = generate_evidence(ch["answer"], cfg)
        return payload, cfg
    return ev, None


# ---------------------------------------------------------------------------
# DEV teams
# ---------------------------------------------------------------------------

def seed_test_teams(conn, count=20, verbose=True):
    """Create DEV-TEAM-01..N test teams (is_dev_seed=1) with round-robin
    A/B/C shadow variant letters so every test team plays SHADOW HUNT."""
    now = db.now_ms()
    letters = ("A", "B", "C")
    n = 0
    for i in range(1, count + 1):
        tid = "DEV-TEAM-%02d" % i
        row = conn.execute(
            "SELECT id FROM teams WHERE team_id=? COLLATE NOCASE",
            (tid,)).fetchone()
        if row:
            rid = row["id"]
            conn.execute(
                "UPDATE teams SET team_name=?, is_active=1, updated_at=?, "
                "round1_enabled=1, round2_enabled=1, is_dev_seed=1 "
                "WHERE id=?",
                ("DEV TEAM %02d" % i, now, rid))
        else:
            cur = conn.execute(
                "INSERT INTO teams (team_id, team_name, participant_names, "
                "created_at, is_active, updated_at, round1_access_id, "
                "round2_access_id, round1_enabled, round2_enabled, is_dev_seed) "
                "VALUES (?,?,?,?,1,?,?,?,1,1,1)",
                (tid, "DEV TEAM %02d" % i, "", now, now, tid, tid))
            rid = cur.lastrowid
            n += 1
        conn.execute("UPDATE teams SET variant_letter=? WHERE id=?",
                     (letters[(rid - 1) % len(letters)], rid))
    if verbose:
        sys.stdout.write("seed_test_teams: %d new, %d ensured\n" % (n, count))
    return n


def remove_test_teams(conn, verbose=True):
    """Delete every DEV team (is_dev_seed=1) and all of its data."""
    conn.execute(
        "DELETE FROM hint_usage WHERE assignment_id IN "
        "(SELECT id FROM team_challenge_assignments a JOIN round_sessions s "
        " ON a.session_id=s.id JOIN teams t ON s.team_id=t.id "
        " WHERE t.is_dev_seed=1)")
    conn.execute(
        "DELETE FROM lab_events WHERE session_id IN "
        "(SELECT id FROM round_sessions s JOIN teams t ON s.team_id=t.id "
        " WHERE t.is_dev_seed=1)")
    conn.execute(
        "DELETE FROM submissions WHERE session_id IN "
        "(SELECT id FROM round_sessions s JOIN teams t ON s.team_id=t.id "
        " WHERE t.is_dev_seed=1)")
    conn.execute(
        "DELETE FROM team_challenge_assignments WHERE session_id IN "
        "(SELECT id FROM round_sessions s JOIN teams t ON s.team_id=t.id "
        " WHERE t.is_dev_seed=1)")
    conn.execute(
        "DELETE FROM round_sessions WHERE team_id IN "
        "(SELECT id FROM teams WHERE is_dev_seed=1)")
    conn.execute(
        "DELETE FROM participant_sessions WHERE team_id IN "
        "(SELECT id FROM teams WHERE is_dev_seed=1)")
    cur = conn.execute("DELETE FROM teams WHERE is_dev_seed=1")
    if verbose:
        sys.stdout.write("remove_test_teams: %d deleted\n" % cur.rowcount)
    return cur.rowcount


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="SHADOW HUNT R1 seeder")
    ap.add_argument("--reset-catalog", action="store_true",
                    help="Permanently purge old Round 1 content + progress, "
                         "then seed the Shadow Hunt catalogue")
    ap.add_argument("--with-test-teams", action="store_true",
                    help="create/ensure 20 DEV-TEAM-xx teams")
    ap.add_argument("--remove-test-teams", action="store_true",
                    help="delete DEV teams and all their data")
    args = ap.parse_args(argv)

    # Ensure every schema column exists before seeding.
    db.init_db()
    try:
        db.migrate()
    except Exception:
        pass
    conn = db.get_connection()
    try:
        with conn:
            seed_categories(conn, reset=args.reset_catalog)
            seed_variants(conn)
            if args.with_test_teams:
                seed_test_teams(conn)
            if args.remove_test_teams:
                remove_test_teams(conn)
    finally:
        conn.close()
    sys.stdout.write("Shadow Hunt seed OK — %s\n" % _ts())


if __name__ == "__main__":
    main()