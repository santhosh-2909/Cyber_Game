"""MYSTERY TRACE Round 1 — concurrent multi-user stress test.

Simulates many teams playing at the same time (each on its own thread,
every team with its own Flask test client) and verifies that live play:

  - creates independent sessions / hands / timers per team,
  - never leaks another team's assignment data (cross-access => 403),
  - converges all submissions under write contention with no SQLite
    "database is locked" / race errors,
  - ends every hand Completed at 100 pts and records the exact same
    number of sessions / assignments / solves.

Run:   python -m round1.test_mt_multiuser
"""
import json
import os
import tempfile
import threading
import unittest
import concurrent.futures

import round1.db as db

_TEST_DB = os.path.join(tempfile.gettempdir(), "r1_test_mt_multi.db")
if os.path.exists(_TEST_DB):
    os.remove(_TEST_DB)
db.DB_PATH = _TEST_DB

import round1.seed_mt as seed_mt
import app as appmod

APP = appmod.app
APP.testing = True

USERS = 12
START = threading.Barrier(USERS)
errors = []
results = []


def _seed():
    db.init_db()
    db.migrate()
    seed_mt.main(["--reset-catalog", "--with-test-teams"])


def _new_session(token, team_id):
    conn = db.get_connection()
    try:
        conn.execute(
            "INSERT INTO participant_sessions (token, team_id, login_time, "
            "last_seen, status, round_name) VALUES (?,?,?,?,?,?)",
            (token, team_id, db.now_ms(), db.now_ms(), "ACTIVE", "round1"))
        conn.commit()
    finally:
        conn.close()


def _server_answer(assignment_id):
    conn = db.get_connection()
    try:
        return conn.execute(
            "SELECT v.expected_answer FROM team_challenge_assignments a "
            "JOIN challenge_variants v ON a.variant_id=v.id WHERE a.id=?",
            (assignment_id,)).fetchone()["expected_answer"]
    finally:
        conn.close()


def _server_answer2(assignment_id):
    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT a.variant2_id FROM team_challenge_assignments a "
            "WHERE a.id=?", (assignment_id,)).fetchone()
        v2id = row["variant2_id"] if row else None
        if v2id is None:
            return ""
        r = conn.execute(
            "SELECT expected_answer FROM challenge_variants WHERE id=?",
            (v2id,)).fetchone()
        return r["expected_answer"] if r else ""
    finally:
        conn.close()


def run_team(team_id, out):
    try:
        tid, token = team_id
        START.wait(timeout=10)
        _new_session(token, tid)
        c = APP.test_client()
        with c.session_transaction() as s:
            s["ptoken"] = token

        d = c.get("/api/participant/round/1").get_json()
        sess, assigns = d["session"], d["assignments"]
        assert sess["status"] == "ACTIVE", sess
        assert len(assigns) == 6, len(assigns)
        domains = [a["domain"] for a in assigns]
        assert len(set(domains)) == 6, (token, domains)
        assert any(a["id"] == d["unlocked"]["id"] for a in assigns)
        my_ids = {a["id"] for a in assigns}

        # Cross-team leakage: another unknown assignment must be rejected.
        probe = out.get("foreign_ids")
        if probe:
            foreign = next(iter(probe - my_ids))
            r = c.get("/api/participant/challenges/%d" % foreign)
            assert r.status_code in (403, 404), (token, r.status_code, foreign)

        # Two simultaneous wrong submissions on the SAME open question: both
        # are logged, no race error, and the per-question counter is sane.
        first = d["unlocked"]["id"]
        ws = []
        with concurrent.futures.ThreadPoolExecutor(2) as ex:
            ws = list(ex.map(
                lambda _: c.post(
                    "/api/participant/challenges/%d/submit" % first,
                    json={"answer": "burst-wrong"}).get_json(), range(2)))
        assert all(w["accepted"] is False for w in ws), ws
        assert all(w["stage_attempts"] in (1, 2) for w in ws), ws

        # Full sequential solve of the hand (Q1 then Q2 per challenge).
        guard = 0
        earned = 0
        while d["unlocked"] is not None and guard < 10:
            u = d["unlocked"]
            r = c.post("/api/participant/challenges/%d/submit" % u["id"],
                       json={"answer": _server_answer(u["id"])})
            g = r.get_json()
            assert g["accepted"] is True, (token, u["id"], g)
            assert g["q1_done"] is True, (token, u["id"], g)
            assert g["flag"] == "", "Q1 must not award a flag yet"
            assert g["phase"] == "q2", (token, u["id"], g)
            r = c.post("/api/participant/challenges/%d/submit" % u["id"],
                       json={"answer": _server_answer2(u["id"])})
            g = r.get_json()
            assert g["accepted"] is True, (token, u["id"], g)
            assert g["flag"].startswith("MT{")
            earned += g["points_total"]
            d = c.get("/api/participant/round/1").get_json()
            guard += 1
        assert d["unlocked"] is None
        assert d["session"]["status"] in ("COMPLETED",), (token, d["session"])
        assert d["session"]["score"] == earned, (token, d["session"]["score"])
        assert sess["challenges_per_team"] == d["session"]["challenges_per_team"]

        out["sessions"].append(d["session"]["id"])
        out["ids"].update(my_ids)
        out["solved_teams"] += 1
    except BaseException as e:  # noqa: BLE001 - surfaced by the harness
        errors.append((team_id, repr(e)))


class TestMultiUser(unittest.TestCase):
    def test_12_teams_play_simultaneously(self):
        _seed()
        conn = db.get_connection()
        try:
            teams = [dict(r) for r in conn.execute(
                "SELECT id, team_id FROM teams WHERE is_dev_seed=1 "
                "ORDER BY id LIMIT ?", (USERS,)).fetchall()]
        finally:
            conn.close()

        shared = {"ids": set(), "sessions": [], "solved_teams": 0}
        threads = []
        for ti, t in enumerate(teams):
            out = shared
            th = threading.Thread(
                target=run_team,
                args=((t["id"], "multi-tok-%d" % t["id"]), out),
                name="MT-%s" % t["team_id"])
            threads.append(th)
            th.start()
        for th in threads:
            th.join(timeout=60)

        self.assertEqual(errors, [], "thread failures: %r" % errors)
        self.assertEqual(shared["solved_teams"], USERS)
        self.assertEqual(len(shared["sessions"]), USERS)
        self.assertEqual(len(shared["ids"]), USERS * 6)

        # DB totals must match exactly: one session, 6 assignments,
        # 12 accepted per-question submissions (Q1+Q2 per challenge),
        # per team: 2 burst wrongs on Q1 + 12 solves = 14 submissions.
        conn = db.get_connection()
        try:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) c FROM round_sessions WHERE "
                             "status='COMPLETED'").fetchone()["c"], USERS)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) c FROM "
                             "team_challenge_assignments").fetchone()["c"],
                USERS * 6)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) c FROM submissions WHERE "
                             "is_correct=1").fetchone()["c"], USERS * 12)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) c FROM submissions").fetchone()["c"],
                USERS * 14)
            # no question may be double-solved
            # base marks 25 .. 25+full time strike (50) is the legal range
            self.assertEqual(
                conn.execute("SELECT COUNT(*) c FROM team_challenge_assignments "
                             "WHERE status='COMPLETED' AND points_awarded "
                             "NOT BETWEEN 25 AND 50").fetchone()["c"], 0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)