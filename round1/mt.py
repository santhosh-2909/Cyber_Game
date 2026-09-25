"""MYSTERY TRACE — Round 1 rebuild: web routes.

Blueprint mounted on the root prefix. Participant + admin JSON APIs plus the
server-rendered admin pages (monitor / team detail / answer key).

Security invariants enforced here:
  * Auth via the project's existing access layer (access.validate_participant)
    so admin-revoked / disabled teams are blocked server-side.
  * Every session / timer / scoring decision is made server-side.
  * Flags, canonical answers and "also accept" lists NEVER reach the client.
  * Sequential unlock: challenge N is 404/locked until N-1 is solved.
  * First correct attempt scores the base marks (25) PLUS a time-strike bonus:
    +2 marks for every 5 seconds saved from the 30s window; re-solves yield 0.
"""
import json
from functools import wraps

from flask import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for

import access
import admin_ops
import round1.db as db
import round1.assign as assign
import round1.seed_mt as seed_mt

MT_ADMIN_KEY = "r1_admin"

mt = Blueprint("mt", __name__, template_folder="templates", url_prefix="")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _json_load(raw, default=None):
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return default if default is not None else {}


def _team_or_api_401():
    team = access.validate_participant("round1")
    if team is None:
        return None, (jsonify({"ok": False, "error": "unauthorized"}), 401)
    # Server-side Round 1 disqualification gate for MT APIs. Round 2 remains
    # independently unaffected; enforced per request so direct API calls and
    # refreshed pages can never bypass the restriction.
    if team.get("round1_disqualified"):
        return None, access.render_round_blocked("round1", team)
    return team, None


def _admin_ok():
    """Shared admin gate: the project admin session (r1_admin key) or a
    configured MT_ADMIN_TOKEN bearer."""
    if session.get(MT_ADMIN_KEY):
        return True
    token = request.headers.get("Authorization", "")
    expected = __import__("os").environ.get("MT_ADMIN_TOKEN", "")
    if expected and token == "Bearer " + expected:
        return True
    return False


def _require_mt_admin_api():
    if not _admin_ok():
        return jsonify({"ok": False, "error": "admin required"}), 401
    return None


def login_required_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _admin_ok():
            return redirect(url_for("r1.r1_admin_login"))
        return view(*args, **kwargs)
    return wrapped


def _session_row(team_id):
    """MT session for the team, or None."""
    row = assign.get_mt_session(team_id)
    return dict(row) if row is not None else None


def _finalize_expired(sess):
    """Flip an expired ACTIVE session to EXPIRED/COMPLETED and return dict."""
    now = db.now_ms()
    if sess.get("status") == "ACTIVE" and sess["ends_at"] <= now:
        conn = db.get_connection()
        try:
            conn.execute(
                "UPDATE round_sessions SET status='COMPLETED', completed_at=? "
                "WHERE id=? AND status='ACTIVE'",
                (now, sess["id"]))
            conn.commit()
        finally:
            conn.close()
        sess["status"] = "COMPLETED"
        sess["completed_at"] = now
    return sess


def _overview_payload(sess):
    """Public {session, assignments overview, unlocked full payload}."""
    now = db.now_ms()
    finished = sess["status"] != "ACTIVE" or sess["ends_at"] <= now
    remaining_ms = max(0, sess["ends_at"] - now)
    assignments = assign.get_mt_assignments(sess["id"])
    points_ppc = sess.get("points_per_challenge") or 25
    shadow_session = assign._session_is_shadow(sess["id"])
    strike_ms = assign.STRIKE_WINDOW_SECONDS * 1000
    overview = [{
        "id": a["assignment_id"],
        "sequence_number": a["display_order"],
        "status": a["status"],
        "points_awarded": a["points_awarded"] or 0,
        "solved": a["status"] == "COMPLETED",
        "failed": a["status"] == "FAILED",
        "attempts_used": (assign.get_mt_attempts_used(a["assignment_id"])
                          if shadow_session else assign.get_mt_stage_attempts(
                              a["assignment_id"],
                              2 if a.get("q1_solved") else 1)),
        "attempts_limit": assign.MT_MAX_ATTEMPTS,
        "question_count": 1 if shadow_session else 2,
        "code": (a["challenge_code"] + "-" + a["variant_code"])
                if shadow_session else a["variant_code"],
        "domain": a.get("domain") or "",
        "title": a.get("title") or "",
        "points": (assign._shadow_points(a["assignment_id"])
                   if shadow_session else points_ppc),
        "started_at": a["started_at"],
        "strike_window_ms": strike_ms,
    } for a in assignments]

    unlocked = None
    unlocked_id = None if finished else assign.get_mt_unlocked_id(sess["id"])
    if unlocked_id is not None:
        unlocked = _challenge_payload(unlocked_id, sess)

    session_data = {
        "id": sess["id"],
        "round_name": sess["round_name"],
        "shadow": bool(shadow_session),
        "started_at": sess["started_at"],
        "ends_at": sess["ends_at"],
        "status": sess["status"],
        "score": sess["score"] or 0,
        "solved": sess["challenges_solved"] or 0,
        "challenges_per_team": sess["challenges_per_team"] or 0,
        "points_per_challenge": sess["points_per_challenge"] or 0,
        "strike_window_ms": assign.STRIKE_WINDOW_SECONDS * 1000,
        "finished": finished,
        "remaining_ms": remaining_ms,
    }
    return {
        "ok": True,
        "fresh": bool(sess.get("_fresh")),
        "session": session_data,
        "assignments": overview,
        "unlocked": unlocked,
    }


def _is_shadow_assignment(assignment_id):
    conn = db.get_connection()
    try:
        return assign._is_shadow_variant(conn, assignment_id)
    finally:
        conn.close()


def _challenge_payload(assignment_id, sess):
    """Public payload for one unlocked assignment (no answers/flags)."""
    d = assign.get_mt_challenge(assignment_id)
    if d is None:
        return None
    shadow = _is_shadow_assignment(assignment_id)
    ev = d.get("evidence_config") or {}
    evidence = ev.get("evidence") if isinstance(ev, dict) else None
    if evidence is None:
        evidence = ev
    cfg = d.get("game_config") or {}
    cfg.setdefault("title", d.get("variant_title") or "")
    cfg.setdefault("category", d.get("category_title") or "")
    cfg.setdefault("points",
                   assign._shadow_points(assignment_id) if shadow else
                   (sess.get("points_per_challenge") or 25))
    if shadow:
        # Shadow Hunt challenges carry ONE question (the flag).
        evidence2 = None
        cfg2 = {}
    else:
        # Second question of the same challenge (same domain, distinct variant).
        ev2 = d.get("evidence_config2") or {}
        evidence2 = ev2.get("evidence") if isinstance(ev2, dict) else None
        if evidence2 is None:
            evidence2 = ev2
        cfg2 = d.get("game_config2") or {}
        cfg2.setdefault("title", d.get("variant2_title") or "")
        cfg2.setdefault("category", d.get("category_title") or "")
        cfg2.setdefault("points", sess.get("points_per_challenge") or 25)
    payload = {
        "id": d["assignment_id"],
        "sequence_number": d["display_order"],
        "status": d["status"],
        "points_awarded": d["points_awarded"] or 0,
        "solved": d["status"] == "COMPLETED",
        "failed": d["status"] == "FAILED",
        "phase": d.get("phase") or "q1",
        "q1_solved": d.get("q1_solved") or False,
        "attempts_used": (assign.get_mt_attempts_used(d["assignment_id"])
                          if shadow else assign.get_mt_stage_attempts(
                              d["assignment_id"],
                              2 if d.get("q1_solved") else 1)),
        "attempts_limit": assign.MT_MAX_ATTEMPTS,
        "code": (d["challenge_code"] + "-" + d["variant_code"])
                if shadow else d["variant_code"],
        "domain": d.get("domain") or "",
        "title": d.get("variant_title") or d.get("category_title") or "",
        "game_type": d.get("game_type") or "",
        "question": d.get("question") or d.get("task_description") or "",
        "hint": d.get("hint") or "",
        "hint2": d.get("hint2") or "",
        "code2": d.get("variant2_code") or "",
        "game_type2": "" if shadow else (d.get("game_type2") or ""),
        "question2": "" if shadow else (d.get("question2")
                                        or d.get("task_description2") or ""),
        "points": (assign._shadow_points(assignment_id) if shadow else
                   sess.get("points_per_challenge") or 25),
        "started_at": d.get("started_at"),
        "strike_window_ms": assign.STRIKE_WINDOW_SECONDS * 1000,
        "evidence": evidence,
        "config": cfg,
        "evidence2": evidence2,
        "config2": cfg2,
        "flag": "",
        "artifact_url": "",
    }
    if shadow:
        # Solved Shadow Hunt cards carry the team's OWN flag so a solved
        # challenge can be revisited (and the flag re-displayed). A team can
        # never see another team's variant: the flag comes from their
        # assignment's variant row only.
        if d["status"] == "COMPLETED":
            payload["flag"] = assign.get_mt_flag(assignment_id)
            cfg.setdefault("solved_flag", payload["flag"])
        if d.get("challenge_code") == "C04":
            payload["artifact_url"] = "/challenge4/%s.html" % (
                d["variant_code"]).lower()
            cfg.setdefault("artifact_url", payload["artifact_url"])
    return payload


def _mt_points_per_challenge(session_id):
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT points_per_challenge FROM round_sessions WHERE id=?",
            (session_id,)).fetchone()
        return int(row["points_per_challenge"]) if row else 25
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Participant
# ---------------------------------------------------------------------------

@mt.route("/participant/round/1")
def mt_page():
    team = access.validate_participant("round1")
    if team is None:
        return redirect(url_for("r1.r1_landing"))
    # Disqualified participants see the full-screen restriction notice instead
    # of the round. The gate is server-side (DB flag), so it survives refresh
    # and re-login and cannot be altered from the browser.
    if team.get("round1_disqualified"):
        return access.render_round_blocked("round1", team)
    # Header timer (top-right, next to Logout) needs the live remaining time.
    sess = _session_row(team["id"])
    if sess is not None:
        now = db.now_ms()
        sess = dict(sess)
        sess["remaining_ms"] = max(0, sess.get("ends_at", now) - now)
    return render_template("mt_round.html", team=team, session_row=sess)


@mt.route("/api/participant/round/1")
def api_round_summary():
    team, err = _team_or_api_401()
    if err:
        return err
    sess, fresh = assign.assign_mt(team["id"])
    if sess.get("finished"):
        sess["status"] = "COMPLETED"
    sess = _finalize_expired(sess)
    sess["_fresh"] = fresh
    return jsonify(_overview_payload(sess))


@mt.route("/api/participant/challenges/<int:assignment_id>")
def api_challenge_detail(assignment_id):
    team, err = _team_or_api_401()
    if err:
        return err
    sess = _session_row(team["id"])
    if sess is None:
        return jsonify({"ok": False, "error": "session_not_found"}), 404
    sess = _finalize_expired(sess)
    if sess["status"] != "ACTIVE":
        return jsonify({"ok": False, "error": "session_ended",
                        "status": sess["status"]}), 410

    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT a.id FROM team_challenge_assignments a "
            "JOIN round_sessions s ON a.session_id = s.id "
            "WHERE a.id=? AND s.id=? AND s.team_id=?",
            (assignment_id, sess["id"], team["id"])).fetchone()
    finally:
        conn.close()
    if row is None:
        abort(404)

    if not assign.is_mt_unlocked(sess["id"], assignment_id):
        return jsonify({"ok": False, "error": "locked",
                        "id": assignment_id}), 403
    return jsonify(_challenge_payload(assignment_id, sess))


@mt.route("/api/participant/challenges/<int:assignment_id>/submit",
          methods=["POST"])
def api_challenge_submit(assignment_id):
    team, err = _team_or_api_401()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    raw = body.get("answer")
    submitted = (raw.strip() if isinstance(raw, str) else "").strip()
    if not submitted:
        # Empty / null / non-string values are rejected BEFORE grading so they
        # never register as an attempt.
        return jsonify({"ok": False, "error": "empty_answer"}), 400

    sess = _session_row(team["id"])
    if sess is None:
        return jsonify({"ok": False, "error": "session_not_found"}), 404
    sess = _finalize_expired(sess)
    if sess["status"] != "ACTIVE":
        return jsonify({"ok": False, "error": "session_ended",
                        "status": sess["status"]}), 410

    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT a.id FROM team_challenge_assignments a "
            "JOIN round_sessions s ON a.session_id = s.id "
            "WHERE a.id=? AND s.id=? AND s.team_id=?",
            (assignment_id, sess["id"], team["id"])).fetchone()
        if row is None:
            conn.close()
            abort(404)
        if not assign.is_mt_unlocked(sess["id"], assignment_id):
            conn.close()
            return jsonify({"ok": False, "error": "locked",
                            "id": assignment_id}), 403

        status = conn.execute(
            "SELECT status FROM team_challenge_assignments WHERE id=?",
            (assignment_id,)).fetchone()
        if status and status["status"] == "FAILED":
            conn.close()
            return jsonify({"ok": False, "error": "attempts_exhausted",
                            "id": assignment_id}), 403

        shadow = assign._is_shadow_variant(conn, assignment_id)
        if shadow:
            result = assign.grade_shadow_flag(conn, sess["id"], assignment_id,
                                              team["id"], submitted)
        else:
            result = assign.grade_and_award(conn, sess["id"], assignment_id,
                                            team["id"], submitted)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if result["exhausted"]:
        message = ("3 attempts used on this question — moving to the next "
                   "challenge.")
    elif result["already_solved"]:
        message = "Already solved earlier."
    elif result["accepted"] and result["flag"]:
        message = "Correct — flag awarded."
    elif result["q1_done"] and not result["flag"]:
        message = "Question 1 correct — question 2 unlocked!"
    else:
        message = "Incorrect — try again."
    return jsonify({
        "ok": True,
        "accepted": result["accepted"],
        "q1_done": result["q1_done"],
        "phase": result["phase"],
        "already_solved": result["already_solved"],
        "exhausted": result["exhausted"],
        "attempts_used": result["attempts_used"],
        "stage_attempts": result["stage_attempts"],
        "attempts_limit": result["attempts_limit"],
        "flag": result["flag"],
        "points": result["points"],
        "strike": result["strike"],
        "points_total": result["points_total"],
        "session_done": result["session_done"],
        "solved": _mt_solved_count(sess["id"]),
        "total": sess["challenges_per_team"] or 0,
        "message": message,
    })


@mt.route("/challenge4/<letter>")
def challenge4_page(letter):
    """Developer's Mistake (C04): per-variant static "staff portal" page.

    Each team can only ever reach the page for THEIR OWN variant letter
    (matched against their C04 assignment on the server). The portal hides
    a USERNAME in its page metadata/source (never the flag); recovering the
    USERNAME and wrapping it in SHADOW{...} yields the flag.
    """
    team = access.validate_participant("round1")
    if team is None:
        return redirect(url_for("r1.r1_landing"))
    target = (letter or "").lower()
    if target.endswith(".html"):
        target = target[:-5]
    if team.get("round1_disqualified"):
        return access.render_round_blocked("round1", team)
    if target not in ("a", "b", "c"):
        abort(404)
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT v.id FROM team_challenge_assignments a "
            "JOIN round_sessions s ON a.session_id = s.id "
            "JOIN challenge_categories c ON a.challenge_category_id = c.id "
            "JOIN challenge_variants v ON a.variant_id = v.id "
            "WHERE s.team_id=? AND s.status='ACTIVE' "
            "AND c.challenge_code='C04' AND LOWER(v.variant_code)=?",
            (team["id"], target)).fetchone()
        flag = ""
        if row is not None:
            frow = conn.execute(
                "SELECT flag FROM challenge_variants WHERE id=?",
                (row["id"],)).fetchone()
            flag = frow["flag"] if frow else ""
    finally:
        conn.close()
    if not flag:
        abort(404)
    # The staff portal is a "username recovery" lab: the page hides the
    # guest USERNAME (recovered from the flag's inner token) in its source
    # metadata, and the team must wrap it in SHADOW{...} themselves. Only
    # the recovered USERNAME is exposed to the template -- never the flag.
    inner = flag[len("SHADOW{"):-1]
    username = inner.lower()
    return render_template("challenge4.html", letter=target.upper(),
                           debug_username=username)


@mt.route("/api/participant/challenges/<int:assignment_id>/hint")
def api_challenge_hint(assignment_id):
    team, err = _team_or_api_401()
    if err:
        return err
    sess = _session_row(team["id"])
    if sess is None:
        return jsonify({"ok": False, "error": "session_not_found"}), 404
    sess = _finalize_expired(sess)
    if sess["status"] != "ACTIVE":
        return jsonify({"ok": False, "error": "session_ended",
                        "status": sess["status"]}), 410

    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT a.q1_solved, "
            "CASE WHEN a.q1_solved=1 THEN v2.hint ELSE v.hint END AS hint "
            "FROM team_challenge_assignments a "
            "JOIN round_sessions s ON a.session_id = s.id "
            "JOIN challenge_variants v ON a.variant_id = v.id "
            "LEFT JOIN challenge_variants v2 ON a.variant2_id = v2.id "
            "WHERE a.id=? AND s.id=? AND s.team_id=?",
            (assignment_id, sess["id"], team["id"])).fetchone()
        if row is None:
            conn.close()
            abort(404)
        if not assign.is_mt_unlocked(sess["id"], assignment_id):
            conn.close()
            return jsonify({"ok": False, "error": "locked",
                            "id": assignment_id}), 403
        conn.execute(
            "INSERT INTO hint_usage (assignment_id, used_at) VALUES (?, ?)",
            (assignment_id, db.now_ms()))
        conn.commit()
        hint = row["hint"]
    finally:
        conn.close()
    return jsonify({"ok": True, "hint": hint})


def _mt_solved_count(session_id):
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM team_challenge_assignments "
            "WHERE session_id=? AND status='COMPLETED'",
            (session_id,)).fetchone()
        return row["c"] if row else 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

@mt.route("/admin/round1")
def admin_round1():
    return redirect(url_for("mt.admin_monitor"))


@mt.route("/admin/round1/monitor")
@login_required_admin
def admin_monitor():
    data = _admin_monitor_data()
    return render_template("mt_admin_monitor.html", data=data)


@mt.route("/admin/round1/team/<int:team_id>")
@login_required_admin
def admin_team_detail(team_id):
    data = _admin_team_data(team_id)
    if data is None:
        abort(404)
    return render_template("mt_admin_team.html", data=data)


@mt.route("/admin/round1/answer-key")
@login_required_admin
def admin_answer_key():
    data = _admin_answer_key_data()
    return render_template("mt_admin_answer_key.html", data=data)


# Admin JSON APIs

@mt.route("/api/admin/team/<int:team_id>/toggle", methods=["POST"])
def api_admin_team_toggle(team_id):
    """Enable/disable a team's access (reflects immediately on the login page
    gate list and blocks/enables their round login)."""
    err = _require_mt_admin_api()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    active = bool(body.get("active", True))
    ok, message = access.set_team_active(team_id, active)
    if not ok:
        return jsonify({"ok": False, "error": message}), 404
    return jsonify({"ok": True, "team_id": team_id, "active": active,
                    "message": message})


@mt.route("/api/admin/round/1/reset", methods=["POST"])
def api_admin_round_reset():
    """Admin reset: wipe Round 1 play data/logins and reseed the catalogue.

    Teams are kept, so the login page reflects the same users as a fresh
    round. Requires {"confirm": true} to avoid accidental wipes.
    """
    err = _require_mt_admin_api()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    if not body.get("confirm"):
        return jsonify({"ok": False, "error": "confirm_required"}), 400
    counts = seed_mt.reset_round()
    return jsonify({"ok": True, "reset": counts,
                    "message": "Round 1 reset done — teams must log in again."})


@mt.route("/api/admin/round/1")
def api_admin_round():
    err = _require_mt_admin_api()
    if err:
        return err
    return jsonify({"ok": True, **(_admin_monitor_data())})


@mt.route("/api/admin/round/1/teams/bulk", methods=["POST"])
def api_admin_teams_bulk_add():
    """Add several teams at once for a live multi-user round.

    Body: {"teams": [{"name": "Team Name", "id": "TEAM01",
                      "access_id": "optional"}], ...}
    Each row goes through access.add_team() so unique/duplicate rules apply.
    """
    err = _require_mt_admin_api()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    entries = body.get("teams") or []
    if not isinstance(entries, list) or not entries:
        return jsonify({"ok": False, "error": "no_teams"}), 400

    results, added, failed = [], 0, 0
    for e in entries:
        name = (e.get("name") or "").strip()
        tid = (e.get("id") or "").strip()
        acc = str(e.get("access_id") or tid).strip()
        ok, message = access.add_team(name, tid,
                                      round1_access_id=acc,
                                      round2_access_id=acc)
        if ok:
            added += 1
        else:
            failed += 1
        results.append({"name": name, "id": tid, "ok": ok, "message": message})
    return jsonify({"ok": True, "added": added, "failed": failed,
                    "results": results})


@mt.route("/api/admin/team/<int:team_id>")
def api_admin_team(team_id):
    err = _require_mt_admin_api()
    if err:
        return err
    data = _admin_team_data(team_id)
    if data is None:
        return jsonify({"ok": False, "error": "team_not_found"}), 404
    return jsonify({"ok": True, **data})


@mt.route("/api/admin/answer-key")
def api_admin_answer_key():
    err = _require_mt_admin_api()
    if err:
        return err
    return jsonify({"ok": True, **(_admin_answer_key_data())})


@mt.route("/api/admin/challenges")
def api_admin_challenges():
    err = _require_mt_admin_api()
    if err:
        return err
    return jsonify({"ok": True, "catalog": _catalog_data()})


def _admin_monitor_data():
    conn = db.get_connection()
    try:
        teams = [dict(r) for r in conn.execute(
            "SELECT t.*, "
            "(SELECT COUNT(*) FROM round_sessions s WHERE s.team_id=t.id "
            " AND s.status NOT IN ('COMPLETED','EXPIRED')) AS active_rounds, "
            "(SELECT s.id FROM round_sessions s WHERE s.team_id=t.id AND "
            " s.status NOT IN ('COMPLETED','EXPIRED') ORDER BY s.id DESC LIMIT 1) "
            " AS session_id, "
            "(SELECT s.score FROM round_sessions s WHERE s.team_id=t.id AND "
            " s.status NOT IN ('COMPLETED','EXPIRED') ORDER BY s.id DESC LIMIT 1) "
            " AS session_score, "
            "(SELECT s.challenges_solved FROM round_sessions s WHERE "
            " s.team_id=t.id AND s.status NOT IN ('COMPLETED','EXPIRED') "
            " ORDER BY s.id DESC LIMIT 1) AS session_solved, "
            "(SELECT MAX(ps.last_seen) FROM participant_sessions ps WHERE "
            " ps.team_id=t.id AND ps.round_name='round1') AS last_seen "
            "FROM teams t WHERE t.is_active=1 ORDER BY t.team_id").fetchall()]

        cat_counts = {"categories": 0, "variants": 0, "active_sessions": 0,
                      "solved_total": 0}
        cat_counts["categories"] = conn.execute(
            "SELECT COUNT(*) AS c FROM challenge_categories").fetchone()["c"]
        cat_counts["variants"] = conn.execute(
            "SELECT COUNT(*) AS c FROM challenge_variants").fetchone()["c"]
        cat_counts["active_sessions"] = conn.execute(
            "SELECT COUNT(*) AS c FROM round_sessions WHERE status='ACTIVE'").fetchone()["c"]
        cat_counts["solved_total"] = conn.execute(
            "SELECT COUNT(*) AS c FROM submissions WHERE is_correct=1").fetchone()["c"]
        categories = [dict(r) for r in conn.execute(
            "SELECT id, challenge_code, title, active FROM challenge_categories "
            "ORDER BY display_order, challenge_code").fetchall()]
    finally:
        conn.close()

    now = db.now_ms()
    rows = []
    for t in teams:
        sess = None
        if t.get("session_id"):
            conn = db.get_connection()
            try:
                s = conn.execute(
                    "SELECT id, round_name, started_at, ends_at, status, score, "
                    "challenges_solved, challenges_per_team FROM round_sessions "
                    "WHERE id=?", (t["session_id"],)).fetchone()
                if s:
                    s = dict(s)
                    s["remaining_ms"] = max(0, s["ends_at"] - now)
                    s["finished"] = s["status"] != "ACTIVE"
                    sess = s
            finally:
                conn.close()
        rows.append({
            "id": t["id"],
            "team_id": t["team_id"],
            "team_name": t["team_name"],
            "variant_letter": (t.get("variant_letter") or "").strip(),
            "is_dev_seed": t.get("is_dev_seed") or 0,
            "last_seen": t.get("last_seen"),
            "session": sess,
        })
    return {
        "summary": cat_counts,
        "settings": admin_ops.get_round_settings("round1") or {},
        "teams": rows,
        "categories": categories,
    }


def _admin_team_data(team_id):
    conn = db.get_connection()
    try:
        team = conn.execute(
            "SELECT * FROM teams WHERE id=?", (team_id,)).fetchone()
        if team is None:
            return None
        team = dict(team)
        sess = conn.execute(
            "SELECT * FROM round_sessions WHERE team_id=? AND status NOT IN "
            "('COMPLETED','EXPIRED') ORDER BY id DESC LIMIT 1",
            (team_id,)).fetchone()
        assignments = []
        if sess:
            sess = dict(sess)
            sess["remaining_ms"] = max(0, sess["ends_at"] - db.now_ms())
            rows = conn.execute(
                "SELECT a.id, a.display_order, a.status, a.started_at, "
                "a.completed_at, a.points_awarded, v.variant_code, "
                "v.expected_answer, v.flag, v.hint, "
                "c.challenge_code, c.title AS category_title, "
                "v.title AS variant_title, v.game_type, v.lab_data "
                "FROM team_challenge_assignments a "
                "JOIN challenge_categories c ON a.challenge_category_id = c.id "
                "JOIN challenge_variants v ON a.variant_id = v.id "
                "WHERE a.session_id=? ORDER BY a.display_order",
                (sess["id"],)).fetchall()
            for r in rows:
                d = dict(r)
                d["accept"] = (_json_load(d.get("lab_data") or "{}")
                               .get("accept") or [])
                d["attempts_limit"] = assign.MT_MAX_ATTEMPTS
                d["submissions"] = [dict(x) for x in conn.execute(
                    "SELECT submitted_answer, is_correct, submitted_at, "
                    "attempt_number FROM submissions WHERE assignment_id=? "
                    "ORDER BY attempt_number", (d["id"],)).fetchall()]
                d["attempts_used"] = len(d["submissions"])
                assignments.append(d)
        sessions = [dict(x) for x in conn.execute(
            "SELECT id, round_name, started_at, ends_at, status, score, "
            "challenges_solved, challenges_per_team, completed_at "
            "FROM round_sessions WHERE team_id=? ORDER BY id DESC",
            (team_id,)).fetchall()]
    finally:
        conn.close()
    return {"team": team, "session": sess, "assignments": assignments,
            "sessions": sessions}


def _admin_answer_key_data():
    conn = db.get_connection()
    try:
        rows = conn.execute(
            "SELECT v.id, v.variant_code, v.title, v.question, v.expected_answer, "
            "v.flag, v.hint, v.game_type, v.lab_data, "
            "c.challenge_code AS category_code, c.title AS category_title "
            "FROM challenge_variants v "
            "JOIN challenge_categories c ON v.challenge_category_id = c.id "
            "ORDER BY c.display_order, v.variant_code").fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["accept"] = _json_load(d.get("lab_data") or "{}").get("accept") or []
        out.append(d)
    return {"challenges": out}


def _catalog_data():
    conn = db.get_connection()
    try:
        cats = [dict(r) for r in conn.execute(
            "SELECT id, challenge_code, title, description FROM "
            "challenge_categories ORDER BY display_order, challenge_code").fetchall()]
        variants = [dict(r) for r in conn.execute(
            "SELECT v.id, v.variant_code, v.title, v.game_type, "
            "c.challenge_code AS category_code FROM challenge_variants v "
            "JOIN challenge_categories c ON v.challenge_category_id = c.id "
            "ORDER BY c.display_order, v.variant_code").fetchall()]
    finally:
        conn.close()
    return {"categories": cats, "variants": variants}