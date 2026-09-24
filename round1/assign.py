"""Round 1 - Cyber Puzzle: assignment and randomization logic.

All randomization happens server-side and is persisted to the database.
Assignments are generated exactly once per round session and never reshuffled.
"""
import json
import random
import secrets

import admin_ops
import round1.db as db
import round1.lab as lab


# ---------------------------------------------------------------------------
# Difficulty balance helpers
# ---------------------------------------------------------------------------

def normalize_answer(text):
    """Normalize a submitted answer for case-insensitive comparison."""
    if not text:
        return ""
    return " ".join(text.strip().lower().split())


MAX_LAB_ATTEMPTS = 3


def select_balanced_categories(categories, n=6):
    """Select n categories with a preferred difficulty distribution.

    Preferred: 2 Easy, 2 Medium, 1 Medium-Hard, 1 Flexible.
    Falls back gracefully when the pool lacks enough of a given difficulty.
    """
    random.shuffle(categories)

    easy = [c for c in categories if c["difficulty"] == "Easy"]
    medium = [c for c in categories if c["difficulty"] == "Medium"]
    med_hard = [c for c in categories if c["difficulty"] == "Medium-Hard"]

    selected = []

    # Pick 2 easy
    take = min(2, len(easy))
    selected += easy[:take]
    # Pick 2 medium
    take = min(2, len(medium))
    selected += medium[:take]
    # Pick 1 medium-hard
    take = min(1, len(med_hard))
    selected += med_hard[:take]

    # Fill remaining with flexible (any leftover) to reach n
    remaining = []
    for c in categories:
        if c not in selected:
            remaining.append(c)
    needed = n - len(selected)
    selected += remaining[:needed]

    # Shuffle the final selection order
    random.shuffle(selected)
    return selected[:n]


def pick_variant(category_id, difficulty=None):
    """Randomly select one variant for the given category.

    If a specific difficulty is requested and available, prefer it.
    """
    conn = db.get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM challenge_variants WHERE challenge_category_id=?",
            (category_id,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        raise ValueError("No variants for category %s" % category_id)

    variants = [dict(r) for r in rows]
    if difficulty:
        matching = [v for v in variants if v["difficulty"] == difficulty]
        if matching:
            return random.choice(matching)
    return random.choice(variants)


def create_assignment(team_id, round_name="Round 1 - Cyber Puzzle: Mixed Fundamentals"):
    """Create a new round session for a team and assign challenges.

    Returns a dict describing the session. If a session already exists that
    is not COMPLETED/EXPIRED, it is resumed (no new assignment).
    """
    conn = db.get_connection()
    try:
        # 1. Check for an existing active session
        existing = conn.execute(
            "SELECT * FROM round_sessions WHERE team_id=? AND status NOT IN "
            "('COMPLETED','EXPIRED') ORDER BY id DESC LIMIT 1",
            (team_id,),
        ).fetchone()
        if existing:
            return _resume_session(existing)

        # 2. Check if team already completed (prevent duplicate rounds)
        finished = conn.execute(
            "SELECT * FROM round_sessions WHERE team_id=? AND status IN "
            "('COMPLETED','EXPIRED') ORDER BY id DESC LIMIT 1",
            (team_id,),
        ).fetchone()
        if finished:
            return _resume_session(finished, allow_resume=False)

        # 3. Fetch active categories
        cats = [dict(r) for r in conn.execute(
            "SELECT * FROM challenge_categories WHERE active=1"
        ).fetchall()]
        if len(cats) < 6:
            raise ValueError("Not enough active challenge categories")

        # 4. Select 6 balanced categories
        selected_cats = select_balanced_categories(cats, n=6)

        # 5. Pick 1 variant per selected category
        assignments = []
        for cat in selected_cats:
            variant = pick_variant(cat["id"], difficulty=cat["difficulty"])
            assignments.append({
                "cat": cat,
                "variant": variant,
            })

        # 6. Create the session (started/ends timestamps)
        start = db.now_ms()
        duration_ms = int(admin_ops.get_round_settings("round1").get("timer_minutes", 30)) * 60 * 1000
        end = start + duration_ms

        cur = conn.execute(
            "INSERT INTO round_sessions (team_id, round_name, started_at, ends_at, "
            "status, score, challenges_solved) VALUES (?,?,?,?,?,?,?)",
            (team_id, round_name, start, end, "ACTIVE", 0, 0),
        )
        session_id = cur.lastrowid

        # 7. Shuffle order and persist assignments
        random.shuffle(assignments)
        for idx, a in enumerate(assignments):
            conn.execute(
                "INSERT INTO team_challenge_assignments (session_id, "
                "challenge_category_id, variant_id, display_order, status, "
                "points_awarded) VALUES (?,?,?,?,?,?)",
                (session_id, a["cat"]["id"], a["variant"]["id"], idx + 1,
                 "IN_PROGRESS", 0),
            )
        conn.commit()

        return _resume_session(conn.execute(
            "SELECT * FROM round_sessions WHERE id=?", (session_id,)
        ).fetchone())

    finally:
        conn.close()


def _resume_session(row, allow_resume=True):
    """Build the public session view for an existing DB row."""
    row = dict(row)
    if row["status"] == "ACTIVE":
        # Re-evaluate expiry
        remaining = row["ends_at"] - db.now_ms()
        if remaining <= 0:
            row["status"] = "EXPIRED"
    return row


def get_session_by_team(team_id):
    """Return the current session row for a team (or None)."""
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM round_sessions WHERE team_id=? "
            "AND status NOT IN ('COMPLETED','EXPIRED') ORDER BY id DESC LIMIT 1",
            (team_id,),
        ).fetchone()
        return _resume_session(row) if row else None
    finally:
        conn.close()


def get_completed_count(session_id):
    """Number of challenges fully solved (flag submitted correctly) in a session."""
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM team_challenge_assignments "
            "WHERE session_id=? AND status='COMPLETED'", (session_id,)).fetchone()
        return row["n"] if row else 0
    finally:
        conn.close()


def get_current_unlocked_id(session_id):
    """Return the assignment id that is currently unlocked.

    The unlocked challenge is the lowest display_order that has not been fully
    completed (status != 'COMPLETED') AND has not had its lab attempts exhausted
    (locked after the max wrong attempts). A locked/solved challenge is treated
    as passed so the participant progresses to the next challenge. Returns None
    once every challenge in the session has been solved or locked.
    """
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM team_challenge_assignments WHERE session_id=? "
            "AND status != 'COMPLETED' "
            "AND (lab_attempts IS NULL OR lab_attempts < ?) "
            "ORDER BY display_order LIMIT 1",
            (session_id, MAX_LAB_ATTEMPTS)).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


def get_unlocked_assignment(session_id):
    """Return the currently unlocked assignment as a rich public view or None.

    Only the currently unlocked challenge is ever returned so future / completed
    challenge details (names, questions) are never exposed to the frontend.
    """
    unlocked_id = get_current_unlocked_id(session_id)
    if unlocked_id is None:
        return None
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT a.id AS assignment_id, a.display_order, a.status, "
            "a.started_at, a.completed_at, a.points_awarded, "
            "a.lab_status, a.lab_started_at, a.lab_completed_at, a.flag_revealed, "
            "a.lab_attempts, a.lab_submitted, "
            "c.id AS category_id, c.challenge_code, c.title, c.domain, "
            "c.description, c.points, "
            "v.id AS variant_id, v.variant_code, v.question, "
            "v.task_description, v.provided_data, v.difficulty, v.hint, "
            "v.lab_type, v.story, v.objective, v.lab_data "
            "FROM team_challenge_assignments a "
            "JOIN challenge_categories c ON a.challenge_category_id = c.id "
            "JOIN challenge_variants v ON a.variant_id = v.id "
            "WHERE a.id=?",
            (unlocked_id,),
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["lab_meta"] = lab.LAB_META.get(d.get("lab_type") or "", {})
        d["lab_payload"] = lab.sanitize_lab_data(
            lab.parse_lab_data(d.get("lab_data")))
        return d
    finally:
        conn.close()


def get_assignments(session_id):
    """Return assigned challenges joined with variant + category data.

    Never includes flags or expected answers.
    """
    conn = db.get_connection()
    try:
        rows = conn.execute(
            "SELECT a.id AS assignment_id, a.display_order, a.status, "
            "a.started_at, a.completed_at, a.points_awarded, "
            "a.lab_status, a.lab_started_at, a.lab_completed_at, a.flag_revealed, "
            "a.lab_attempts, a.lab_submitted, "
            "c.id AS category_id, c.challenge_code, c.title, c.domain, "
            "c.description, c.points, "
            "v.id AS variant_id, v.variant_code, v.question, "
            "v.task_description, v.provided_data, v.difficulty, v.hint, "
            "v.lab_type, v.story, v.objective, v.lab_data "
            "FROM team_challenge_assignments a "
            "JOIN challenge_categories c ON a.challenge_category_id = c.id "
            "JOIN challenge_variants v ON a.variant_id = v.id "
            "WHERE a.session_id=? ORDER BY a.display_order",
            (session_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["lab_meta"] = lab.LAB_META.get(d.get("lab_type") or "", {})
            d["lab_payload"] = lab.sanitize_lab_data(
                lab.parse_lab_data(d.get("lab_data")))
            result.append(d)
        return result
    finally:
        conn.close()


def get_assignment_detail(session_id, assignment_id, team_id):
    """Return a single assignment with lab metadata, safe for a given team.

    Returns None if the assignment does not belong to this team's session.
    """
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT a.*, "
            "c.title, c.challenge_code AS code, c.domain, c.points, "
            "v.variant_code, v.difficulty, v.story, v.objective, "
            "v.lab_type, v.lab_data, v.explanation, "
            "v.estimated_solve_time AS eta, v.hints "
            "FROM team_challenge_assignments a "
            "JOIN challenge_categories c ON a.challenge_category_id = c.id "
            "JOIN challenge_variants v ON a.variant_id = v.id "
            "WHERE a.id=? AND a.session_id=? AND a.session_id IN "
            "(SELECT id FROM round_sessions WHERE id=? AND team_id=?)",
            (assignment_id, session_id, session_id, team_id),
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["lab_meta"] = lab.LAB_META.get(d.get("lab_type") or "", {})
        d["lab_payload"] = lab.sanitize_lab_data(lab.parse_lab_data(d["lab_data"]))
        try:
            d["hints"] = json.loads(d["hints"])
        except Exception:
            pass
        return d
    finally:
        conn.close()


def get_lab_answer(assignment_id):
    """Return the stored expected lab answer for an assignment (server-only)."""
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT v.expected_answer FROM team_challenge_assignments a "
            "JOIN challenge_variants v ON a.variant_id = v.id "
            "WHERE a.id=?", (assignment_id,)).fetchone()
        return row["expected_answer"] if row else ""
    finally:
        conn.close()


def generate_secret_flag(index):
    """Generate a unique flag token like CPR1-XXXX-XXXX."""
    part1 = "CPR1"
    token = secrets.token_hex(2).upper()      # 4 hex chars
    token2 = secrets.token_hex(2).upper()     # 4 hex chars
    return f"{part1}-{token}-{token2}"


# ===========================================================================
# MYSTERY TRACE (Round 1 rebuild) assignment engine.
#
# Spec behaviors enforced here (server-side, persisted):
#   * Exactly `challenges_per_team` (default 6) challenges per team, drawn so
#     that NO two challenges share a domain.
#   * Selection is deterministic for a (team, secret) pair via
#     sha256("team_id:round1:SECRET")-seeded RNG, so a retry/refresh never
#     yields a different hand.
#   * Assignments are created once per MT round and persisted; the same
#     ACTIVE session is resumed on refresh.
#   * Sequential unlock: challenge N+1 is 404/locked until N is solved.
#   * Server-authoritative timer from round_settings (30 min default).
#   * First correct attempt only: base points_awarded (25) once, never twice,
#     PLUS a "time strike" bonus: +2 marks for every 5 seconds saved from the
#     STRIKE_WINDOW_SECONDS window (max +12 for an instant solve).
# ===========================================================================

import hashlib
import os

MT_DEFAULT_CHALLENGES = 6
MT_DEFAULT_POINTS = 25
MT_MAX_ATTEMPTS = 3        # max wrong tries per MYSTERY TRACE question
STRIKE_WINDOW_SECONDS = 30  # time-strike window: +2 marks per 5s saved

# Assignment-seed secret. Real events supply MT_ASSIGNMENT_SECRET; a stable
# dev fallback is used locally / in preview (never relied upon on Vercel,
# where the env is always set).
_ASSIGN_SECRET = os.environ.get(
    "MT_ASSIGNMENT_SECRET", "mt-dev-assignment-secret")


def _mt_rng(team_id, secret=None):
    secret = secret or _ASSIGN_SECRET
    seed_hex = hashlib.sha256(
        ("%s:round1:%s" % (team_id, secret)).encode("utf-8")).hexdigest()
    seed_int = int.from_bytes(bytes.fromhex(seed_hex[:16]), "big")
    return random.Random(seed_int)


def mt_time_strike(elapsed_ms, base_points):
    """Time-strike bonus for a solve.

    The challenge earns a bonus for every 5 seconds SAVED from the
    STRIKE_WINDOW_SECONDS window: each full 5-second bucket still remaining
    when the answer is submitted adds +2 marks.

      solved at 0s  -> 30s saved -> +12 marks
      solved at 20s -> 10s saved ->  +4 marks
      solved at 25s ->  5s saved ->  +2 marks
      solved at 30s+->  0s saved ->  +0 marks

    `base_points` is accepted for signature compatibility but the bonus is a
    flat per-bucket amount, independent of the challenge's base marks.
    Server-side so every client (and the leaderboard) sees identical numbers.
    """
    if elapsed_ms is None:
        return STRIKE_WINDOW_SECONDS // 5 * 2
    elapsed_s = max(0, elapsed_ms) // 1000
    saved_s = max(0, STRIKE_WINDOW_SECONDS - elapsed_s)
    return (saved_s // 5) * 2


def _mt_settings():
    """challenges_per_team / points_per_challenge from round_settings."""
    try:
        row = admin_ops.get_round_settings("round1")
    except Exception:
        row = {}
    return {
        "count": int(row.get("challenges_per_team") or MT_DEFAULT_CHALLENGES),
        "points": int(row.get("points_per_challenge") or MT_DEFAULT_POINTS),
        "timer_minutes": int(row.get("timer_minutes") or 30),
    }


def _is_mt_variant(variant_id, conn):
    """True when a variant belongs to the MT catalogue."""
    row = conn.execute(
        "SELECT flag, game_type FROM challenge_variants WHERE id=?",
        (variant_id,)).fetchone()
    return bool(row and (row["flag"] or "").startswith("MT{"))


_MT_SESSION_ROUND = ("s.round_name LIKE 'SHADOW HUNT%' "
                     "OR s.round_name LIKE 'MYSTERY TRACE%'")


def get_mt_session(team_id):
    """Return the ACTIVE MT round session for a team, or None.

    Only sessions dealt by the MT flows (SHADOW HUNT / MYSTERY TRACE) are
    considered; legacy Cyber-Puzzle sessions are excluded so a new round can
    start cleanly even if a legacy session's assignments happen to point at
    current catalogue variants.
    """
    conn = db.get_connection()
    try:
        rows = conn.execute(
            "SELECT s.id FROM round_sessions s "
            "JOIN team_challenge_assignments a ON a.session_id = s.id "
            "WHERE s.team_id=? AND s.status NOT IN ('COMPLETED','EXPIRED') "
            "AND (" + _MT_SESSION_ROUND + ") "
            "ORDER BY s.id DESC LIMIT 5",
            (team_id,)).fetchall()
        for r in rows:
            if r["id"] is None:
                continue
            ok = conn.execute(
                "SELECT COUNT(*) AS c FROM team_challenge_assignments a "
                "JOIN challenge_variants v ON a.variant_id = v.id "
                "WHERE a.session_id=? AND v.game_type != '' ",
                (r["id"],)).fetchone()["c"]
            if ok:
                return conn.execute(
                    "SELECT * FROM round_sessions WHERE id=?",
                    (r["id"],)).fetchone()
        return None
    finally:
        conn.close()


def _legacy_sessions_for_team(conn, team_id):
    """Active sessions that are NOT MT sessions (old Cyber-Puzzle flow)."""
    return conn.execute(
        "SELECT s.id FROM round_sessions s "
        "WHERE s.team_id=? AND s.status NOT IN ('COMPLETED','EXPIRED') "
        "AND NOT (" + _MT_SESSION_ROUND + ")",
        (team_id,)).fetchall()


def assign_mt(team_id, secret=None):
    """Create (or resume) the Round 1 round for a team.

    Returns a dict: {"session": {...}, "fresh": bool}. Idempotent: an existing
    ACTIVE Round 1 session is resumed; a finished one stays finished.

    Shadow Hunt (Round 1 rework): teams carry a round-robin variant letter
    (A/B/C). Their hand is ALL six challenges, each handed with the single
    variant matching their letter (one flag question per challenge), all
    unlocked together so any order is playable.
    """
    conn = db.get_connection()
    try:
        active = get_mt_session(team_id)
        if active is not None:
            active = dict(active)
            if active["ends_at"] <= db.now_ms():
                return _resume_session(active), False
            active["remaining_ms"] = active["ends_at"] - db.now_ms()
            active["finished"] = False
            return active, False

        finished = conn.execute(
            "SELECT * FROM round_sessions WHERE team_id=? "
            "AND status IN ('COMPLETED','EXPIRED') "
            "AND id IN (SELECT session_id FROM team_challenge_assignments a "
            "           JOIN challenge_variants v ON a.variant_id = v.id "
            "           WHERE v.game_type != '') "
            "ORDER BY id DESC LIMIT 1",
            (team_id,)).fetchone()
        if finished:
            finished = dict(finished)
            finished["finished"] = True
            return finished, False

        # Any leftover legacy ACTIVE sessions are retired so the team starts
        # a clean Round 1 round (the historical data stays in the DB).
        for old in _legacy_sessions_for_team(conn, team_id):
            conn.execute(
                "UPDATE round_sessions SET status='EXPIRED', completed_at=? "
                "WHERE id=?", (db.now_ms(), old["id"]))

        settings = _mt_settings()
        shadow_letter = _team_variant_letter(conn, team_id)
        round_name = ("SHADOW HUNT — Round 1" if shadow_letter
                      else "MYSTERY TRACE — Round 1")
        cats = [dict(r) for r in conn.execute(
            "SELECT * FROM challenge_categories WHERE active=1 "
            "ORDER BY challenge_code").fetchall()]
        if len(cats) < 2:
            raise ValueError("Not enough active challenge categories")

        # Seeded, cross-refresh-stable hand draw.
        rng = _mt_rng(team_id, secret)
        ordered = list(cats)
        rng.shuffle(ordered)
        if shadow_letter:
            # Shadow Hunt: every challenge is dealt to every team.
            chosen = ordered
        else:
            chosen = ordered[: settings["count"]]
        # Guarantee: no duplicate domain across the hand (categories ARE the
        # domains here, and the UNIQUE(session, category) constraint enforces
        # it structurally as well).
        if len({c["id"] for c in chosen}) != len(chosen):
            raise ValueError("duplicate domain selection")

        # Deterministically pick variants per chosen category:
        #  * Shadow Hunt — the ONE variant matching the team's letter and no
        #    second question (a single flag per challenge).
        #  * Classic MT — a primary plus a SECOND question from the SAME
        #    category, never the same variant.
        picks = []
        for cat in chosen:
            variants = [dict(r) for r in conn.execute(
                "SELECT * FROM challenge_variants WHERE challenge_category_id=? "
                "AND game_type != '' ORDER BY variant_code",
                (cat["id"],)).fetchall()]
            if shadow_letter:
                match = [v for v in variants
                         if v["variant_code"] == shadow_letter]
                if not match:
                    raise ValueError("No variant %s for category %s"
                                     % (shadow_letter, cat["id"]))
                primary, second = match[0], None
            else:
                if len(variants) < 2:
                    raise ValueError("Need >=2 MT variants for category %s"
                                     % cat["id"])
                primary = rng.choice(variants)
                second = rng.choice([v for v in variants
                                     if v["id"] != primary["id"]])
            picks.append((cat, primary, second))

        start = db.now_ms()
        end = start + settings["timer_minutes"] * 60 * 1000
        cur = conn.execute(
            "INSERT INTO round_sessions (team_id, round_name, started_at, "
            "ends_at, status, score, challenges_solved, challenges_per_team, "
            "challenges_total, points_per_challenge) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (team_id, round_name, start, end, "ACTIVE", 0, 0,
             len(picks), len(picks), settings["points"]))
        session_id = cur.lastrowid

        rng.shuffle(picks)
        for idx, (cat, variant, second) in enumerate(picks):
            conn.execute(
                "INSERT INTO team_challenge_assignments (session_id, "
                "challenge_category_id, variant_id, variant2_id, "
                "display_order, status, started_at, points_awarded) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (session_id, cat["id"], variant["id"],
                 second["id"] if second else None, idx + 1,
                 "IN_PROGRESS", start, 0))

        conn.commit()

        sess = dict(conn.execute(
            "SELECT * FROM round_sessions WHERE id=?",
            (session_id,)).fetchone())
        sess["remaining_ms"] = sess["ends_at"] - db.now_ms()
        sess["finished"] = False
        return sess, True
    finally:
        conn.close()


def team_variant_letter(team_id):
    """A team's Shadow Hunt variant letter ('' for classic MT teams)."""
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT variant_letter FROM teams WHERE id=?",
            (team_id,)).fetchone()
        return (row["variant_letter"] or "").strip() if row else ""
    finally:
        conn.close()


def _team_variant_letter(conn, team_id):
    """Connection-scoped variant letter (see team_variant_letter)."""
    row = conn.execute(
        "SELECT variant_letter FROM teams WHERE id=?",
        (team_id,)).fetchone()
    return (row["variant_letter"] or "").strip() if row else ""


def get_mt_assignments(session_id):
    """MT assignments for a session (public-safe: no flags/answers)."""
    conn = db.get_connection()
    try:
        rows = conn.execute(
            "SELECT a.id AS assignment_id, a.display_order, a.status, "
            "a.started_at, a.completed_at, a.points_awarded, a.q1_solved, "
            "c.id AS category_id, c.challenge_code, c.title, c.domain, "
            "c.points, v.id AS variant_id, v.variant_code, v.question, "
            "v.task_description, v.difficulty, v.hint, v.title, "
            "v.game_type, v.game_config, v.provided_data "
            "FROM team_challenge_assignments a "
            "JOIN challenge_categories c ON a.challenge_category_id = c.id "
            "JOIN challenge_variants v ON a.variant_id = v.id "
            "WHERE a.session_id=? ORDER BY a.display_order",
            (session_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["domain"] = _mt_domain(d)
            out.append(d)
        return out
    finally:
        conn.close()


def get_mt_unlocked_id(session_id):
    """First unresolved (IN_PROGRESS) assignment -> the open challenge.

    Once every challenge is settled (COMPLETED or FAILED) there is nothing
    left to attempt and None is returned (.e. the hand is finished).
    """
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM team_challenge_assignments "
            "WHERE session_id=? AND status='IN_PROGRESS' "
            "ORDER BY display_order LIMIT 1",
            (session_id,)).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


def get_mt_attempts_used(assignment_id):
    """Number of answers already submitted for an assignment."""
    conn = db.get_connection()
    try:
        return conn.execute(
            "SELECT COUNT(*) AS c FROM submissions WHERE assignment_id=?",
            (assignment_id,)).fetchone()["c"]
    finally:
        conn.close()


def get_mt_stage_attempts(assignment_id, stage):
    """Attempts consumed by a specific question stage (1 or 2)."""
    conn = db.get_connection()
    try:
        return conn.execute(
            "SELECT COUNT(*) AS c FROM submissions WHERE assignment_id=? "
            "AND stage=?", (assignment_id, stage)).fetchone()["c"]
    finally:
        conn.close()


def get_mt_phase(assignment_id):
    """Which question is currently open: 'q1' or 'q2'."""
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT q1_solved, status FROM team_challenge_assignments "
            "WHERE id=?", (assignment_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return "q1"
    if row["status"] in ("COMPLETED", "FAILED"):
        return "q2" if row["status"] == "COMPLETED" else "q1"
    return "q2" if row["q1_solved"] else "q1"


def is_mt_unlocked(session_id, assignment_id):
    """Open state of a challenge.

    Classic Mystery Trace: sequential unlock — only the current
    (lowest-order) open challenge is attemptable; completed or failed
    challenges stay viewable/re-verifiable but never expose future ones.

    Shadow Hunt: all challenges are unlocked at once (any order), so any
    still-open assignment of a Shadow Hunt session is attemptable until
    it is solved.
    """
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT status FROM team_challenge_assignments "
            "WHERE session_id=? AND id=?", (session_id, assignment_id)).fetchone()
        if row is None:
            return False
        if row["status"] in ("COMPLETED", "FAILED"):
            return True
        if _session_is_shadow(session_id):
            return True  # Shadow Hunt: every open challenge is attemptable.
        unlocked = get_mt_unlocked_id(session_id)
        return unlocked is not None and unlocked == assignment_id
    finally:
        conn.close()


def _default_variant2(conn, category_id, variant1_id):
    """Deterministic fallback second question for legacy assignments.

    Picks the MT variant with the smallest variant_code in the SAME category
    that is not the primary variant. Used whenever variant2_id is NULL so a
    challenge always carries TWO distinct questions (same domain, no repeat).
    """
    row = conn.execute(
        "SELECT id FROM challenge_variants WHERE challenge_category_id=? "
        "AND game_type != '' AND id != ? ORDER BY variant_code LIMIT 1",
        (category_id, variant1_id)).fetchone()
    return row["id"] if row else None


def get_mt_challenge(assignment_id):
    """Full challenge payload incl. evidence for an unlocked assignment.

    All flags / answers are excluded. The evidence is pre-computed from the
    server-side evidence_config and is safe to ship: without the answer the
    evidence alone reveals nothing.
    """
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT a.id AS assignment_id, a.display_order, a.status, "
            "a.started_at, a.completed_at, a.points_awarded, "
            "a.variant2_id, a.q1_solved, "
            "c.id AS category_id, c.challenge_code, c.title AS category_title, "
            "c.domain, c.description, c.points AS category_points, "
            "v.id AS variant_id, v.variant_code, v.question, v.task_description, "
            "v.difficulty, v.hint, v.title AS variant_title, "
            "v.game_type, v.game_config, v.evidence_config, v.provided_data, "
            "v2.id AS variant2_id_live, v2.variant_code AS variant2_code, "
            "v2.question AS question2, v2.task_description AS task_description2, "
            "v2.hint AS hint2, v2.title AS variant2_title, "
            "v2.game_type AS game_type2, v2.game_config AS game_config2, "
            "v2.evidence_config AS evidence_config2, v2.provided_data AS "
            "provided_data2 "
            "FROM team_challenge_assignments a "
            "JOIN challenge_categories c ON a.challenge_category_id = c.id "
            "JOIN challenge_variants v ON a.variant_id = v.id "
            "LEFT JOIN challenge_variants v2 ON a.variant2_id = v2.id "
            "WHERE a.id=?",
            (assignment_id,)).fetchone()
        # Legacy rows without a stored variant2_id: resolve the second
        # question deterministically on read (same rule graders use). Shadow
        # Hunt assignments carry a single flag question and variant2_id=NULL
        # by design, so the legacy two-question fallback never applies.
        raw = dict(row) if row is not None else None
        is_shadow = row is not None and _is_shadow_variant(conn, assignment_id)
        if raw is not None and raw.get("variant2_id") is None and not is_shadow:
            v2id = _default_variant2(conn, raw["category_id"],
                                     raw["variant_id"])
            if v2id is not None:
                v2row = conn.execute(
                    "SELECT id AS variant2_id_live, variant_code, question, "
                    "task_description, hint, title, game_type, game_config, "
                    "evidence_config, provided_data FROM challenge_variants "
                    "WHERE id=?", (v2id,)).fetchone()
                if v2row is not None:
                    row = dict(raw)
                    for k in ("variant2_code", "question2", "task_description2",
                              "hint2", "variant2_title", "game_type2",
                              "game_config2", "evidence_config2", "provided_data2"):
                        row[k] = v2row[k]
                    raw = row
        if raw is None:
            return None
        d = dict(raw)
        d["domain"] = _mt_domain(d)
        d["evidence_config"] = _load_json(d.get("evidence_config") or "{}")
        d["game_config"] = _load_json(d.get("game_config") or "{}")
        d["evidence_config2"] = _load_json(d.get("evidence_config2") or "{}")
        d["game_config2"] = _load_json(d.get("game_config2") or "{}")
        d["q1_solved"] = bool(d.get("q1_solved"))
        d["phase"] = "q2" if d["q1_solved"] else "q1"
        return d
    finally:
        conn.close()


def _mt_domain(assignment):
    """Resolve the MT domain key for a row exposing provided_data/game_config.

    The MT profile lives on the variant (sql/pass/bin/...); the legacy
    category.domain is only a display grouping and is NOT the MT domain.
    """
    try:
        data = json.loads(assignment.get("provided_data") or "{}")
        if isinstance(data, dict) and data.get("domain"):
            return data["domain"]
    except (TypeError, ValueError):
        pass
    try:
        gc = json.loads(assignment.get("game_config") or "{}")
        if isinstance(gc, dict) and gc.get("domain"):
            return gc["domain"]
    except (TypeError, ValueError):
        pass
    return assignment.get("domain") or ""


def _load_json(raw):
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return {}


def get_mt_flag(assignment_id):
    """Server-only: the MT flag for an assignment."""
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT v.flag FROM team_challenge_assignments a "
            "JOIN challenge_variants v ON a.variant_id = v.id "
            "WHERE a.id=?", (assignment_id,)).fetchone()
        return row["flag"] if row else ""
    finally:
        conn.close()


def get_mt_expected(assignment_id):
    """Server-only: canonical answer for grading (never shipped to client)."""
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT v.expected_answer FROM team_challenge_assignments a "
            "JOIN challenge_variants v ON a.variant_id = v.id "
            "WHERE a.id=?", (assignment_id,)).fetchone()
        return row["expected_answer"] if row else ""
    finally:
        conn.close()


def _variant2(conn, assignment_id):
    """Resolve the second variant for an assignment (stored or, for legacy
    rows, the deterministic same-category fallback). Returns a dict row."""
    aa = conn.execute(
        "SELECT a.variant2_id, a.challenge_category_id, a.variant_id "
        "FROM team_challenge_assignments a WHERE a.id=?",
        (assignment_id,)).fetchone()
    if aa is None:
        return None
    v2id = aa["variant2_id"]
    if v2id is None:
        v2id = _default_variant2(conn, aa["challenge_category_id"],
                                 aa["variant_id"])
    if v2id is None:
        return None
    return conn.execute(
        "SELECT * FROM challenge_variants WHERE id=?", (v2id,)).fetchone()


def get_mt_variant2(assignment_id):
    """Server-only: the second variant (never shipped to the client)."""
    conn = db.get_connection()
    try:
        row = _variant2(conn, assignment_id)
        return dict(row) if row else None
    finally:
        conn.close()


def get_mt_expected2(assignment_id):
    """Server-only: canonical answer for the SECOND question."""
    conn = db.get_connection()
    try:
        row = _variant2(conn, assignment_id)
        return row["expected_answer"] if row else ""
    finally:
        conn.close()


def get_mt_accept_list2(assignment_id):
    """Server-only: extra accepted answer forms for the SECOND question."""
    conn = db.get_connection()
    try:
        row = _variant2(conn, assignment_id)
        raw = row["lab_data"] if row else ""
        try:
            data = json.loads(raw or "{}")
            extras = data.get("accept") or []
            return list(extras) if isinstance(extras, list) else []
        except (TypeError, ValueError):
            return []
    finally:
        conn.close()


def get_mt_accept_list(assignment_id):
    """Server-only: extra accepted answer forms stored in the variant's
    lab_data JSON (never shipped to the participant)."""
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT v.lab_data FROM team_challenge_assignments a "
            "JOIN challenge_variants v ON a.variant_id = v.id "
            "WHERE a.id=?", (assignment_id,)).fetchone()
        raw = row["lab_data"] if row else ""
        try:
            data = json.loads(raw or "{}")
            extras = data.get("accept") or []
            return list(extras) if isinstance(extras, list) else []
        except (TypeError, ValueError):
            return []
    finally:
        conn.close()


def accept_mt_answer(submitted, canonical, extra=None):
    return submitted.strip() != "" and submitted.strip().lower() in {
        a for a in _accepted(canonical, extra)}


def _accepted(canonical, extra=None):
    from round1.evidence import accepted_answers as _aa
    return _aa(canonical, extra)


def record_mt_submission(session_id, assignment_id, submitted, stage,
                         is_correct, conn=None):
    """Insert a submission row (every attempt is logged).

    Stage 1 answers go into `submitted_answer`, stage 2 into
    `submitted_answer2`, so the audit trail always records which question.

    When `conn` is supplied the row is written on that connection (part of a
    larger transaction, committed by the caller); otherwise the row is
    committed on a fresh connection.
    """
    if conn is None:
        conn = db.get_connection()
        own = True
    else:
        own = False
    try:
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM submissions WHERE assignment_id=?",
            (assignment_id,)).fetchone()["c"]
        ans1 = submitted if stage == 1 else ""
        ans2 = submitted if stage == 2 else ""
        conn.execute(
            "INSERT INTO submissions (session_id, assignment_id, "
            "submitted_answer, submitted_answer2, stage, is_correct, "
            "submitted_at, attempt_number) VALUES (?,?,?,?,?,?,?,?)",
            (session_id, assignment_id, ans1, ans2, stage, int(is_correct),
             db.now_ms(), n + 1))
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()


# ===========================================================================
# SHADOW HUNT (Round 1 rework) grading.
#
# Shadow Hunt participants submit CIC{...} flags directly. The submitted
# value is evaluated against the flag SAVED in the database
# (challenge_variants.flag). Every wrong answer is recorded as a WRONG
# ATTEMPT (persisted in submissions, surfaced to the UI) and stays fully
# retryable — a wrong guess never costs points and never locks the
# challenge. A correct flag completes the challenge for its category points.
#
# Detection is by flag prefix, so the rework is inert until the Shadow Hunt
# catalogue (CIC{...} flags) is seeded; the existing MT / legacy flows are
# untouched.
# ===========================================================================

SHADOW_FLAG_PREFIX = "CIC{"


def _is_shadow_variant(conn, assignment_id):
    """True when an assignment's variant belongs to the Shadow Hunt catalogue."""
    row = conn.execute(
        "SELECT v.flag FROM team_challenge_assignments a "
        "JOIN challenge_variants v ON a.variant_id = v.id "
        "WHERE a.id=?", (assignment_id,)).fetchone()
    return bool(row and (row["flag"] or "").startswith(SHADOW_FLAG_PREFIX))


def _session_is_shadow(session_id):
    """True when a session's hand is built from Shadow Hunt challenges."""
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM team_challenge_assignments a "
            "JOIN challenge_variants v ON a.variant_id = v.id "
            "WHERE a.session_id=? AND v.flag LIKE 'CIC{%'",
            (session_id,)).fetchone()
        return bool(row and row["c"])
    finally:
        conn.close()


def _shadow_points(assignment_id):
    """Category points for an assignment (the Shadow Hunt per-challenge mark)."""
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT c.points FROM team_challenge_assignments a "
            "JOIN challenge_categories c ON a.challenge_category_id = c.id "
            "WHERE a.id=?", (assignment_id,)).fetchone()
        return int(row["points"]) if row else 100
    finally:
        conn.close()


def grade_shadow_flag(conn, session_id, assignment_id, team_id, submitted):
    """Grade a Shadow Hunt flag submission against the DB-saved flag.

    - Correct (matches challenge_variants.flag, case-insensitive):
      challenge COMPLETED, category points awarded once, flag returned.
    - Wrong: recorded as a wrong attempt (submissions is_correct=0), no
      points lost, challenge stays open for retry — never auto-FAILED.
    - Resubmit after completion: already_solved, no extra points.

    Returns the same dict shape as ``grade_and_award`` so the web layer
    treats both graders identically.
    """
    row = conn.execute(
        "SELECT status FROM team_challenge_assignments WHERE id=?",
        (assignment_id,)).fetchone()
    status = row["status"] if row else "IN_PROGRESS"
    already_solved = status == "COMPLETED"

    flag = get_mt_flag(assignment_id)
    correct = bool(flag) and submitted.strip().lower() == flag.strip().lower()

    def _attempt_count():
        return conn.execute(
            "SELECT COUNT(*) AS c FROM submissions WHERE assignment_id=?",
            (assignment_id,)).fetchone()["c"]

    stage_attempts = _attempt_count()
    record_mt_submission(session_id, assignment_id, submitted, 1, correct, conn)
    new_attempts = _attempt_count()

    if already_solved:
        if not correct:
            # Logged above; a late wrong answer never damages a solved card.
            conn.commit()
        return {"accepted": True, "q1_done": True, "phase": "q1",
                "already_solved": True, "exhausted": False,
                "stage_attempts": new_attempts,
                "attempts_used": new_attempts, "attempts_limit": 0,
                "flag": "", "points": 0, "strike": 0, "points_total": 0,
                "session_done": False}

    if not correct:
        conn.commit()
        return {"accepted": False, "q1_done": False, "phase": "q1",
                "already_solved": False, "exhausted": False,
                "stage_attempts": new_attempts,
                "attempts_used": new_attempts, "attempts_limit": 0,
                "flag": "", "points": 0, "strike": 0, "points_total": 0,
                "session_done": False}

    points = _shadow_points(assignment_id)
    now = db.now_ms()
    conn.execute(
        "UPDATE team_challenge_assignments SET status='COMPLETED', "
        "completed_at=?, points_awarded=? WHERE id=? AND status != 'COMPLETED'",
        (now, points, assignment_id))
    conn.execute(
        "UPDATE round_sessions SET challenges_solved = challenges_solved + 1, "
        "score = score + ? WHERE id=?", (points, session_id))

    total = conn.execute(
        "SELECT COUNT(*) AS c FROM team_challenge_assignments "
        "WHERE session_id=?", (session_id,)).fetchone()["c"]
    solved = conn.execute(
        "SELECT COUNT(*) AS c FROM team_challenge_assignments "
        "WHERE session_id=? AND status='COMPLETED'",
        (session_id,)).fetchone()["c"]
    session_done = solved >= total
    if session_done:
        conn.execute(
            "UPDATE round_sessions SET status='COMPLETED', completed_at=? "
            "WHERE id=? AND status='ACTIVE'", (now, session_id))
    conn.commit()
    return {"accepted": True, "q1_done": True, "phase": "q1",
            "already_solved": False, "exhausted": False,
            "stage_attempts": new_attempts,
            "attempts_used": new_attempts, "attempts_limit": 0,
            "flag": flag, "points": points, "strike": 0,
            "points_total": points, "session_done": session_done}


def grade_and_award(conn, session_id, assignment_id, team_id, submitted):
    """Grade ONE answer under the sequencing (1 question at a time).

    Question 1 must be solved before question 2 is presented; each question
    has its own 3-attempt budget.

    - Q1 correct    -> phase moves to Q2 (accepted, q1_done, no flag yet).
    - Q2 correct    -> challenge COMPLETED, 25 pts + time strike, flag.
    - Wrong answer  -> question stays open; on the 3rd wrong of a question
                       the challenge FAILED (0 pts, next challenge unlocks).
    - A resubmit after completion reports already_solved, no extra points.

    Returns dict:
    {accepted, q1_done, phase, already_solved, exhausted, stage_attempts,
     attempts_used, attempts_limit, flag, points, session_done}.
    Every attempt is logged to submissions.
    """
    limit = MT_MAX_ATTEMPTS
    row = conn.execute(
        "SELECT status, q1_solved FROM team_challenge_assignments WHERE id=?",
        (assignment_id,)).fetchone()
    status = row["status"] if row else "IN_PROGRESS"
    q1_solved = bool(row["q1_solved"]) if row else False
    stage = 2 if q1_solved else 1
    phase = "q2" if q1_solved else "q1"

    if stage == 1:
        expected = get_mt_expected(assignment_id)
        extra = get_mt_accept_list(assignment_id)
    else:
        expected = get_mt_expected2(assignment_id)
        extra = get_mt_accept_list2(assignment_id)
    correct = accept_mt_answer(submitted, expected, extra)

    already = conn.execute(
        "SELECT status FROM team_challenge_assignments WHERE id=?",
        (assignment_id,)).fetchone()
    already_solved = bool(already and already["status"] == "COMPLETED")

    stage_attempts = get_mt_stage_attempts(assignment_id, stage)
    record_mt_submission(session_id, assignment_id, submitted, stage,
                         correct, conn)
    new_stage_attempts = stage_attempts + 1
    new_attempts = get_mt_attempts_used(assignment_id)

    # Already solved / closed: no double-scoring, no extra attempts.
    if already_solved:
        conn.commit()
        return {"accepted": True, "q1_done": True, "phase": "q2",
                "already_solved": True, "exhausted": False,
                "stage_attempts": new_stage_attempts,
                "attempts_used": new_attempts, "attempts_limit": limit,
                "flag": "", "points": 0, "strike": 0, "points_total": 0,
                "session_done": False}

    if status == "FAILED" or (not correct and new_stage_attempts >= limit):
        now = db.now_ms()
        conn.execute(
            "UPDATE team_challenge_assignments SET status='FAILED', "
            "completed_at=? WHERE id=? AND status IN ('IN_PROGRESS','FAILED')",
            (now, assignment_id))
        session_done = _mt_hand_finished(conn, session_id)
        if session_done:
            conn.execute(
                "UPDATE round_sessions SET status='COMPLETED', completed_at=? "
                "WHERE id=? AND status='ACTIVE'", (now, session_id))
        conn.commit()
        return {"accepted": False, "q1_done": False, "phase": phase,
                "already_solved": False, "exhausted": True,
                "stage_attempts": new_stage_attempts,
                "attempts_used": new_attempts, "attempts_limit": limit,
                "flag": "", "points": 0, "strike": 0, "points_total": 0,
                "session_done": session_done}

    if not correct:
        conn.commit()
        return {"accepted": False, "q1_done": False, "phase": phase,
                "already_solved": False, "exhausted": False,
                "stage_attempts": new_stage_attempts,
                "attempts_used": new_attempts, "attempts_limit": limit,
                "flag": "", "points": 0, "strike": 0, "points_total": 0,
                "session_done": False}

    # Correct.
    if stage == 1:
        # Q1 solved -> reveal Q2. No points yet.
        conn.execute(
            "UPDATE team_challenge_assignments SET q1_solved=1 WHERE id=?",
            (assignment_id,))
        conn.commit()
        return {"accepted": True, "q1_done": True, "phase": "q2",
                "already_solved": False, "exhausted": False,
                "stage_attempts": new_stage_attempts,
                "attempts_used": new_attempts, "attempts_limit": limit,
                "flag": "", "points": 0, "strike": 0, "points_total": 0,
                "session_done": False}

    # Q2 correct -> challenge completed.
    row = conn.execute(
        "SELECT points_per_challenge FROM round_sessions WHERE id=?",
        (session_id,)).fetchone()
    points = int(row["points_per_challenge"] or MT_DEFAULT_POINTS) if row else MT_DEFAULT_POINTS

    flag = get_mt_flag(assignment_id)
    now = db.now_ms()
    started = conn.execute(
        "SELECT started_at FROM team_challenge_assignments WHERE id=?",
        (assignment_id,)).fetchone()
    elapsed_ms = now - (started["started_at"] if started else now)
    strike = mt_time_strike(elapsed_ms, points)
    points_total = points + strike
    conn.execute(
        "UPDATE team_challenge_assignments SET status='COMPLETED', "
        "completed_at=?, points_awarded=? WHERE id=? AND status != 'COMPLETED'",
        (now, points_total, assignment_id))
    conn.execute(
        "UPDATE round_sessions SET challenges_solved = challenges_solved + 1, "
        "score = score + ? WHERE id=?", (points_total, session_id))

    total = conn.execute(
        "SELECT COUNT(*) AS c FROM team_challenge_assignments "
        "WHERE session_id=?", (session_id,)).fetchone()["c"]
    solved = conn.execute(
        "SELECT COUNT(*) AS c FROM team_challenge_assignments "
        "WHERE session_id=? AND status='COMPLETED'",
        (session_id,)).fetchone()["c"]
    session_done = solved >= total
    if session_done:
        conn.execute(
            "UPDATE round_sessions SET status='COMPLETED', completed_at=? "
            "WHERE id=? AND status='ACTIVE'", (now, session_id))
    conn.commit()
    return {"accepted": True, "q1_done": True, "phase": "q2",
            "already_solved": False, "exhausted": False,
            "stage_attempts": new_stage_attempts,
            "attempts_used": new_attempts, "attempts_limit": limit,
            "flag": flag, "points": points, "strike": strike,
            "points_total": points_total, "session_done": session_done}


def _mt_hand_finished(conn, session_id):
    """True when every challenge in the hand is settled (solved or failed)."""
    return conn.execute(
        "SELECT COUNT(*) AS c FROM team_challenge_assignments "
        "WHERE session_id=? AND status='IN_PROGRESS'",
        (session_id,)).fetchone()["c"] == 0
