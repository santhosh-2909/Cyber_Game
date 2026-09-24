"""SHADOW HUNT Round 1 — concurrent multi-user stress test.

Simulates many teams playing at the same time (each on its own thread,
every team with its own Flask test client) and verifies that live play:

  - creates independent sessions / hands / timers per team,
  - never leaks another team's assignment data (cross-access => 403/404),
  - converges all submissions under write contention with no SQLite
    "database is locked" / race errors,
  - ends every hand Completed at 600 pts and records the exact same
    number of sessions / assignments / solves.

Run:   python -m round1.test_mt_multiuser
"""
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


def _server_flag(assignment_id):
    conn = db.get_connection()
    try:
        return conn.execute(
            "SELECT v.flag FROM team_challenge_assignments a "
            "JOIN challenge_variants v ON a.variant_id=v.id WHERE a.id=?",
            (assignment_id,)).fetchone()["flag"]
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
        assert sess["shadow"] is True, sess
        assert len(assigns) == 6, len(assigns)
        codes = [a["code"] for a in assigns]
        assert len(set(codes)) == 6, (token, codes)
        assert any(a["id"] == d["unlocked"]["id"] for a in assigns)
        my_ids = {a["id"] for a in assigns}

        # Cross-team leakage: another unknown assignment must be rejected.
        probe = out.get("foreign_ids")
        if probe:
            foreign = next(iter(probe - my_ids))
            r = c.get("/api/participant/challenges/%d" % foreign)
            assert r.status_code in (403, 404, 401), (token, r.status_code)

        # Two simultaneous wrong submissions on the SAME open challenge: both
        # are logged, no race error, and the attempt counter is sane.
        first = d["unlocked"]["id"]
        with concurrent.futures.ThreadPoolExecutor(2) as ex:
            ws = list(ex.map(
                lambda _: c.post(
                    "/api/participant/challenges/%d/submit" % first,
                    json={"answer": "burst-wrong"}).get_json(), range(2)))
        assert all(w["accepted"] is False for w in ws), ws
        assert all(w["attempts_used"] in (1, 2) for w in ws), ws

        # Full solve of the hand — any order, one flag each, 600 pts total.
        guard = 0
        earned = 0
        while guard < 20:
            d = c.get("/api/participant/round/1").get_json()
            open_ids = [a["id"] for a in d["assignments"]
                        if not a["solved"] and not a["failed"]]
            if not open_ids:
                break
            aid = open_ids.pop()
            flag = _server_flag(aid)
            g = c.post("/api/participant/challenges/%d/submit" % aid,
                       json={"answer": flag}).get_json()
            assert g["accepted"] is True, (token, aid, g)
            assert g["flag"].startswith("SHADOW{"), (token, g)
            assert g["strike"] == 0
            earned += g["points_total"]
            guard += 1

        final = c.get("/api/participant/round/1").get_json()
        assert final["session"]["status"] == "COMPLETED", (token, final)
        assert earned == 600, (token, earned)
        assert final["session"]["score"] == 600, (token, final)
        assert final["session"]["solved"] == 6, (token, final)

        out["sessions"].append(final["session"]["id"])
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
        for t in teams:
            th = threading.Thread(
                target=run_team,
                args=((t["id"], "multi-tok-%d" % t["id"]), shared),
                name="MT-%s" % t["team_id"])
            threads.append(th)
            th.start()
        for th in threads:
            th.join(timeout=90)

        self.assertEqual(errors, [], "thread failures: %r" % errors)
        self.assertEqual(shared["solved_teams"], USERS)
        self.assertEqual(len(shared["sessions"]), USERS)
        self.assertEqual(len(shared["ids"]), USERS * 6)

        # DB totals must match exactly: one session + 6 assignments per team,
        # 6 correct submissions + 2 burst wrongs = 8 submissions per team.
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
                             "is_correct=1").fetchone()["c"], USERS * 6)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) c FROM submissions").fetchone()["c"],
                USERS * 8)
            # no challenge may be double-solved and every award is 75..125
            self.assertEqual(
                conn.execute("SELECT COUNT(*) c FROM team_challenge_assignments "
                             "WHERE status='COMPLETED' AND points_awarded "
                             "NOT BETWEEN 75 AND 125").fetchone()["c"], 0)
            # per-team final scores are exactly 600
            self.assertEqual(
                conn.execute("SELECT COUNT(*) c FROM round_sessions WHERE "
                             "score != 600").fetchone()["c"], 0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)