"""MYSTERY TRACE Round 1 — acceptance tests.

Runs against a scratch SQLite DB (round1.db.DB_PATH is repointed at
/tmp/r1_test.db) so the live database is never touched.

Run:   python -m round1.test_mt
"""
import json
import os
import shutil
import tempfile
import unittest

import round1.db as db

# Isolate everything on a scratch DB BEFORE importing the app + blueprints.
_TEST_DB = os.path.join(tempfile.gettempdir(), "r1_test_mt.db")
if os.path.exists(_TEST_DB):
    os.remove(_TEST_DB)
db.DB_PATH = _TEST_DB

import round1.seed_mt as seed_mt
import round1.assign as assign
import round1.mt as mtmod
import app as appmod

APP = appmod.app
APP.testing = True


def _seed():
    db.init_db()
    db.migrate()
    seed_mt.main(["--reset-catalog", "--with-test-teams"])


def _active_participant(client, team_id=None):
    conn = db.get_connection()
    try:
        if team_id:
            row = conn.execute(
                "SELECT id FROM teams WHERE team_id=?", (team_id,)).fetchone()
            assert row is not None, "missing team %s" % team_id
            tid = row["id"]
        else:
            tid = conn.execute("SELECT id FROM teams LIMIT 1").fetchone()["id"]
        token = "tok-%s" % tid
        conn.execute(
            "DELETE FROM participant_sessions WHERE team_id=?", (tid,))
        conn.execute(
            "INSERT INTO participant_sessions (token, team_id, login_time, "
            "last_seen, status, round_name) VALUES (?,?,?,?,?,?)",
            (token, tid, db.now_ms(), db.now_ms(), "ACTIVE", "round1"))
        conn.commit()
        return tid, token
    finally:
        conn.close()


def _admin(client):
    with client.session_transaction() as s:
        s["r1_admin"] = "admin-test"


def _team_client(tid, token):
    c = APP.test_client()
    with c.session_transaction() as s:
        s["ptoken"] = token
    return c


class MTBase(unittest.TestCase):
    def setUp(self):
        _seed()

    def summary(self, client):
        r = client.get("/api/participant/round/1")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        return r.get_json()

    def _server_answer(self, assignment_id):
        conn = db.get_connection()
        try:
            return conn.execute(
                "SELECT v.expected_answer FROM team_challenge_assignments a "
                "JOIN challenge_variants v ON a.variant_id=v.id WHERE a.id=?",
                (assignment_id,)).fetchone()["expected_answer"]
        finally:
            conn.close()

    def _server_answer2(self, assignment_id):
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

    def _submit_q1(self, c, u, answer=None, check=True):
        r = c.post("/api/participant/challenges/%d/submit" % u["id"],
                   json={"answer": answer if answer is not None
                         else self._server_answer(u["id"])})
        g = r.get_json()
        if check:
            self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
            self.assertTrue(g["accepted"])
            self.assertTrue(g["q1_done"])
            self.assertFalse(g["flag"], "Q1 alone must not award a flag")
            self.assertEqual(g["phase"], "q2")
        return g

    def _submit_q2(self, c, u, answer=None, check=True):
        r = c.post("/api/participant/challenges/%d/submit" % u["id"],
                   json={"answer": answer if answer is not None
                         else self._server_answer2(u["id"])})
        g = r.get_json()
        if check:
            self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
            self.assertTrue(g["accepted"])
            self.assertRegex(g["flag"], r"^MT\{")
        return g

    def _solve(self, c, u, answer1=None, answer2=None):
        """Answer Q1 then Q2 correctly; returns the Q2 result dict."""
        self._submit_q1(c, u, answer1)
        return self._submit_q2(c, u, answer2)


class TestCatalog(MTBase):
    def test_12_categories_48_variants_all_engines(self):
        conn = db.get_connection()
        try:
            cats = conn.execute(
                "SELECT COUNT(*) c FROM challenge_categories").fetchone()["c"]
            variants = conn.execute(
                "SELECT COUNT(*) c FROM challenge_variants").fetchone()["c"]
            engines = conn.execute(
                "SELECT COUNT(DISTINCT game_type) c FROM challenge_variants "
                "WHERE game_type != ''").fetchone()["c"]
            bad = conn.execute(
                "SELECT COUNT(*) c FROM challenge_variants WHERE flag='' OR "
                "flag NOT LIKE 'MT{%' OR expected_answer='' OR "
                "evidence_config=''").fetchone()["c"]
        finally:
            conn.close()
        self.assertEqual(cats, 12)
        self.assertEqual(variants, 48)
        self.assertEqual(engines, 48)
        self.assertEqual(bad, 0)

    def test_catalog_is_complete_and_safe(self):
        conn = db.get_connection()
        try:
            rows = conn.execute(
                "SELECT v.*, c.challenge_code cat FROM challenge_variants v "
                "JOIN challenge_categories c ON v.challenge_category_id=c.id "
                "ORDER BY v.variant_code").fetchall()
        finally:
            conn.close()
        self.assertEqual(len(rows), 48)
        accepted_forms = []
        for r in rows:
            self.assertRegex(r["flag"], r"^MT\{[^}]+\}$")
            self.assertTrue(r["expected_answer"])
            ev = json.loads(r["evidence_config"])
            self.assertIn("evidence", ev)
            lab = json.loads(r["lab_data"] or "{}")
            extra = lab.get("accept") or []
            if extra:
                self.assertTrue(all(str(x).strip() for x in extra))
                self.assertNotIn(r["flag"], extra)
                self.assertNotIn(r["expected_answer"], extra)
                accepted_forms.append(r["variant_code"])
        # several domains provide accepted alternate answers (regression guard)
        self.assertGreaterEqual(len(accepted_forms), 10)


class TestRng(MTBase):
    def test_deterministic_seeded_converge(self):
        r1a = assign._mt_rng("DEV-TEAM-01").choice(list(range(1000)))
        r1b = assign._mt_rng("DEV-TEAM-01").choice(list(range(1000)))
        r2 = assign._mt_rng("DEV-TEAM-02").choice(list(range(1000)))
        self.assertEqual(r1a, r1b)
        self.assertNotEqual(r1a, r2)


class TestParticipantFlow(MTBase):
    def test_session_returns_six_unique_domains_and_30min_timer(self):
        tid, token = _active_participant(None)
        c = _team_client(tid, token)
        d = self.summary(c)
        s = d["session"]
        self.assertEqual(s["challenges_per_team"], 6)
        self.assertEqual(s["points_per_challenge"], 25)
        self.assertEqual(s["status"], "ACTIVE")
        self.assertEqual(s["ends_at"] - s["started_at"], 30 * 60 * 1000)
        domains = [a["domain"] for a in d["assignments"]]
        self.assertEqual(len(domains), 6)
        self.assertEqual(len(set(domains)), 6)
        codes = [a["code"] for a in d["assignments"]]
        self.assertEqual(len(set(codes)), 6)
        self.assertIsNotNone(d["unlocked"])

    def test_every_challenge_carries_two_distinct_questions(self):
        """Each challenge ships TWO questions from the SAME domain and the
        pair is never repeated for the team across the whole hand."""
        tid, token = _active_participant(None)
        c = _team_client(tid, token)
        d = self.summary(c)
        u = d["unlocked"]
        self.assertTrue(u["question"])
        self.assertTrue(u["question2"])
        self.assertNotEqual(u["code"], u["code2"],
                            "question 2 must be a distinct variant")
        self.assertEqual(u["domain"], u["domain"])
        self.assertTrue(u["evidence2"])
        self.assertTrue(u["config2"])
        self.assertEqual(u["attempts_limit"], 3)
        self.assertEqual(d["assignments"][0]["question_count"], 2)
        # DB: every assignment holds two distinct variants, same category,
        # unique across the hand (no question repeats for this team).
        conn = db.get_connection()
        try:
            rows = conn.execute(
                "SELECT a.variant_id, a.variant2_id, v.challenge_category_id, "
                "v2.challenge_category_id AS cid2 FROM "
                "team_challenge_assignments a "
                "JOIN challenge_variants v ON a.variant_id=v.id "
                "JOIN challenge_variants v2 ON a.variant2_id=v2.id "
                "WHERE a.session_id=? ORDER BY a.display_order",
                (d["session"]["id"],)).fetchall()
        finally:
            conn.close()
        self.assertEqual(len(rows), 6)
        ids = []
        for r in rows:
            self.assertIsNotNone(r["variant2_id"])
            self.assertNotEqual(r["variant_id"], r["variant2_id"])
            self.assertEqual(r["challenge_category_id"], r["cid2"],
                             "second question must live in the same domain")
            ids += [r["variant_id"], r["variant2_id"]]
        self.assertEqual(len(ids), len(set(ids)),
                         "a question must never repeat for the same team")

    def test_questions_are_sequenced_one_at_a_time(self):
        """Q2 must not be answerable at the same time as Q1: only the open
        question consumes the attempt, Q1 alone awards no flag/points, and a
        wrong Q2 never scores."""
        tid, token = _active_participant(None)
        c = _team_client(tid, token)
        d = self.summary(c)
        u = d["unlocked"]
        self.assertEqual(u["phase"], "q1")
        self.assertFalse(u["q1_solved"])

        # Wrong Q1: rejected, no phase move, attempt counted on Q1 only.
        g = c.post("/api/participant/challenges/%d/submit" % u["id"],
                   json={"answer": "definitely-wrong"}).get_json()
        self.assertFalse(g["accepted"])
        self.assertFalse(g["q1_done"])
        self.assertEqual(g["phase"], "q1")
        self.assertEqual(g["stage_attempts"], 1)
        self.assertEqual(g["points"], 0)

        # Correct Q1: unlocked Q2, still no flag/points.
        g = c.post("/api/participant/challenges/%d/submit" % u["id"],
                   json={"answer": self._server_answer(u["id"])}).get_json()
        self.assertTrue(g["accepted"])
        self.assertTrue(g["q1_done"])
        self.assertEqual(g["phase"], "q2")
        self.assertEqual(g["flag"], "")
        self.assertEqual(g["points"], 0)

        # A Q1-stage payload can no longer grade (the open question is Q2).
        g = c.post("/api/participant/challenges/%d/submit" % u["id"],
                   json={"answer": "Q1-again-ignored"}).get_json()
        self.assertFalse(g["accepted"])
        self.assertEqual(g["phase"], "q2")
        self.assertEqual(g["stage_attempts"], 1)

        # Wrong Q2: rejected, no points.
        g = c.post("/api/participant/challenges/%d/submit" % u["id"],
                   json={"answer": "not-the-second"}).get_json()
        self.assertFalse(g["accepted"])
        self.assertEqual(g["phase"], "q2")
        self.assertEqual(g["stage_attempts"], 2)
        self.assertEqual(g["points"], 0)

        # Correct Q2: solved + flag + points (Q2 attempt 3).
        g = c.post("/api/participant/challenges/%d/submit" % u["id"],
                   json={"answer": self._server_answer2(u["id"])}).get_json()
        self.assertTrue(g["accepted"])
        self.assertRegex(g["flag"], r"^MT\{")
        self.assertEqual(g["stage_attempts"], 3)
        self.assertEqual(g["solved"], 1)

    def test_sequential_unlock_and_scoring(self):
        tid, token = _active_participant(None)
        c = _team_client(tid, token)
        d = self.summary(c)
        first = d["unlocked"]

        # second challenge is LOCKED (403) until first is solved
        second_id = d["assignments"][1]["id"]
        r = c.get("/api/participant/challenges/%d" % second_id)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json()["error"], "locked")

        # wrong answer on Q1: no points, still locked
        r = c.post("/api/participant/challenges/%d/submit" % first["id"],
                   json={"answer": "wroooooong"})
        g = r.get_json()
        self.assertFalse(g["accepted"])
        self.assertEqual(g["points"], 0)
        self.assertEqual(g["solved"], 0)
        self.assertEqual(g["stage_attempts"], 1)
        self.assertEqual(g["attempts_limit"], 3)
        self.assertFalse(g["exhausted"])

        # correct answers: 25 base marks + time-strike bonus, flag
        ans = self._server_answer(first["id"])
        ans2 = self._server_answer2(first["id"])
        self._submit_q1(c, first, ans)
        r = c.post("/api/participant/challenges/%d/submit" % first["id"],
                   json={"answer": ans2})
        g = r.get_json()
        self.assertTrue(g["accepted"])
        self.assertEqual(g["points"], 25)
        self.assertGreaterEqual(g["strike"], 0)
        self.assertEqual(g["points_total"], g["points"] + g["strike"])
        first_total = g["points_total"]
        self.assertRegex(g["flag"], r"^MT\{")
        self.assertEqual(g["solved"], 1)

        # resubmit correct Q2: already_solved, no extra points
        r = c.post("/api/participant/challenges/%d/submit" % first["id"],
                   json={"answer": ans2})
        g = r.get_json()
        self.assertTrue(g["accepted"])
        self.assertTrue(g["already_solved"])
        self.assertEqual(g["points"], 0)

        # second challenge now unlocked
        r = c.get("/api/participant/challenges/%d" % second_id)
        self.assertEqual(r.status_code, 200)

        d2 = self.summary(c)
        self.assertEqual(d2["session"]["score"], first_total)
        self.assertEqual(d2["session"]["solved"], 1)

    def test_three_wrong_attempts_fail_and_advance(self):
        """3 wrongs on the OPEN question close the challenge (FAILED) and
        unlock the next one — a question never stays locked forever."""
        tid, token = _active_participant(None)
        c = _team_client(tid, token)
        d = self.summary(c)
        first, second = d["unlocked"], d["assignments"][1]
        self.assertEqual(
            c.get("/api/participant/challenges/%d" % second["id"]).status_code, 403)

        for i in range(3):
            r = c.post("/api/participant/challenges/%d/submit" % first["id"],
                       json={"answer": "WRONG-%d" % i})
            g = r.get_json()
            self.assertFalse(g["accepted"])
            self.assertEqual(g["stage_attempts"], i + 1)
            self.assertEqual(g["attempts_limit"], 3)
            self.assertEqual(g["exhausted"], i == 2)

        # closed question stays viewable but no more submissions allowed
        r = c.get("/api/participant/challenges/%d" % first["id"])
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["failed"])
        r = c.post("/api/participant/challenges/%d/submit" % first["id"],
                   json={"answer": "late"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json()["error"], "attempts_exhausted")

        # next question is unlocked despite the failure
        r = c.get("/api/participant/challenges/%d" % second["id"])
        self.assertEqual(r.status_code, 200)
        d2 = self.summary(c)
        self.assertEqual(d2["session"]["score"], 0)
        self.assertEqual(d2["assignments"][0]["status"], "FAILED")
        self.assertTrue(d2["assignments"][0]["failed"])
        self.assertIsNotNone(d2["unlocked"])
        self.assertEqual(d2["unlocked"]["id"], second["id"])

    def test_q2_answers_never_score_before_q1(self):
        """Submitting only a correct Q2 while Q1 is open grades against Q1
        (the phrase stays closed to guarding the sequence)."""
        tid, token = _active_participant(None)
        c = _team_client(tid, token)
        d = self.summary(c)
        u = d["unlocked"]
        q2_ans = self._server_answer2(u["id"])
        g = c.post("/api/participant/challenges/%d/submit" % u["id"],
                   json={"answer": q2_ans}).get_json()
        self.assertFalse(g["accepted"])
        self.assertFalse(g["q1_done"])
        self.assertEqual(g["phase"], "q1")
        self.assertEqual(g["stage_attempts"], 1)
        self.assertEqual(g["points"], 0)
        # the challenge is still fully open for Q1
        self.assertEqual(
            c.get("/api/participant/challenges/%d" % u["id"]).get_json()["phase"],
            "q1")

    def test_session_completes_when_all_questions_failed(self):
        tid, token = _active_participant(None)
        c = _team_client(tid, token)
        d = self.summary(c)
        for _ in range(6):
            u = d["unlocked"]
            self.assertIsNotNone(u)
            self.assertEqual(u["phase"], "q1")
            for i in range(3):
                r = c.post("/api/participant/challenges/%d/submit" % u["id"],
                           json={"answer": "WRONG-%d" % i})
                g = r.get_json()
                self.assertEqual(g["accepted"], False)
                self.assertEqual(g["exhausted"], i == 2)
            d = self.summary(c)
        self.assertIsNone(d["unlocked"])
        self.assertIn(d["session"]["status"], ("COMPLETED",))
        self.assertEqual(d["session"]["solved"], 0)
        self.assertEqual(d["session"]["score"], 0)

    def test_case_insensitive_answers_are_accepted(self):
        """Uppercase / mixed / lowercase variants of the same answer all pass
        for both sequences (Q1 then Q2)."""
        for casing, expr in (("lower", lambda a: a.lower()),
                             ("upper", lambda a: a.upper()),
                             ("mixed", lambda a: "".join(
                                  ch.upper() if i % 2 else ch.lower()
                                  for i, ch in enumerate(a)))):
            tid, token = _active_participant(None)
            c = _team_client(tid, token)
            d = self.summary(c)
            u = d["unlocked"]
            ans1 = expr(self._server_answer(u["id"]))
            ans2 = expr(self._server_answer2(u["id"]))
            g = self._solve(c, u, ans1, ans2)
            self.assertTrue(g["accepted"],
                            "%s-cased answer should grade correct" % casing)

    def test_empty_null_answers_rejected_without_consuming_attempt(self):
        """Empty / null / non-string / whitespace answers are 400s and never
        register as an attempt, so the 3-attempt budget is preserved."""
        tid, token = _active_participant(None)
        c = _team_client(tid, token)
        d = self.summary(c)
        aid = d["unlocked"]["id"]
        variants = [{"answer": ""}, {"answer": "   \t "}, {"answer": None},
                    {}, {"answer": 123}, {"answer": ["x"]}]
        for payload in variants:
            r = c.post("/api/participant/challenges/%d/submit" % aid,
                       json=payload)
            g = r.get_json()
            self.assertEqual(r.status_code, 400)
            self.assertEqual(g["error"], "empty_answer")
        # no attempt consumed and the question is still open
        conn = db.get_connection()
        try:
            used = conn.execute(
                "SELECT COUNT(*) FROM submissions WHERE assignment_id=?",
                (aid,)).fetchone()[0]
            status = conn.execute(
                "SELECT status FROM team_challenge_assignments WHERE id=?",
                (aid,)).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(used, 0)
        self.assertEqual(status, "IN_PROGRESS")

    def test_accept_list_forms_grade_correctly(self):
        """Alternative ('Also accept') answers must be accepted server-side."""
        tid, token = _active_participant(None)
        c = _team_client(tid, token)
        d = self.summary(c)
        conn = db.get_connection()
        try:
            row = conn.execute(
                "SELECT a.id, v.expected_answer, v.lab_data FROM "
                "team_challenge_assignments a JOIN challenge_variants v "
                "ON a.variant_id=v.id WHERE a.session_id=? AND "
                "v.lab_data != '{}' ORDER BY a.display_order LIMIT 1",
                (d["session"]["id"],)).fetchone()
        finally:
            conn.close()
        if row is None:
            self.skipTest("no accept-list variant in this hand")
        extra = json.loads(row["lab_data"]).get("accept")
        self.assertTrue(extra)
        self.assertNotEqual(extra[0].strip(), row["expected_answer"].strip())
        ans2 = self._server_answer2(row["id"])
        g = self._solve(c, {"id": row["id"]}, extra[0], ans2)
        self.assertRegex(g["flag"], r"^MT\{")
        self.assertEqual(g["points"], 25)

    def test_no_secrets_in_any_participant_payload(self):
        """Across many teams/hands no flag / answer ever reaches the client."""
        seen_codes = set()
        teams = ["DEV-TEAM-%02d" % i for i in range(1, 17)]
        for team_idx in teams:
            tid, token = _active_participant(None, team_idx)
            c = _team_client(tid, token)
            d = self.summary(c)
            for _ in range(4):
                u = d["unlocked"]
                if u is None:
                    break
                seen_codes.add(u["code"])
                blob = json.dumps(d)
                blob_detail = json.dumps(u)
                for bad in ('"flag":', '"expected_answer":', '"accept":',
                            '"evidence_config":'):
                    self.assertNotIn(bad, blob_detail,
                                     "leaked %s in %s" % (bad, u["code"]))
                # every challenge carries TWO distinct questions
                self.assertNotEqual(u["code2"], u["code"])
                self.assertTrue(u["question2"])
                self.assertTrue(u["evidence2"])
                conn = db.get_connection()
                try:
                    fa = conn.execute(
                        "SELECT v.flag AS f1, v2.flag AS f2 FROM "
                        "team_challenge_assignments a "
                        "JOIN challenge_variants v ON a.variant_id=v.id "
                        "LEFT JOIN challenge_variants v2 ON "
                        "a.variant2_id=v2.id "
                        "WHERE a.id=?", (u["id"],)).fetchone()
                finally:
                    conn.close()
                for secret in (fa["f1"], fa["f2"]):
                    if not secret:
                        continue
                    self.assertNotIn(secret, blob_detail)
                # unlock next
                ans = self._server_answer(u["id"])
                ans2 = self._server_answer2(u["id"])
                g = self._solve(c, u, ans, ans2)
                self.assertTrue(g["accepted"])
                d = self.summary(c)
        self.assertGreaterEqual(len(seen_codes), 36,
                                "expected broad coverage, saw %d" % len(seen_codes))

    def test_completion_marks_session_done(self):
        tid, token = _active_participant(None)
        c = _team_client(tid, token)
        d = self.summary(c)
        guard = 0
        earned = 0
        while d["unlocked"] is not None and guard < 10:
            u = d["unlocked"]
            g = self._solve(c, u)
            earned += g["points_total"]
            d = self.summary(c)
            guard += 1
        self.assertIsNone(d["unlocked"])
        self.assertEqual(d["session"]["solved"], 6)
        self.assertEqual(d["session"]["score"], earned)
        self.assertIn(d["session"]["status"], ("COMPLETED",))

    def test_hint_returns_and_logs_usage(self):
        tid, token = _active_participant(None)
        c = _team_client(tid, token)
        d = self.summary(c)
        u = d["unlocked"]
        r = c.get("/api/participant/challenges/%d/hint" % u["id"])
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["hint"])
        conn = db.get_connection()
        try:
            n = conn.execute(
                "SELECT COUNT(*) c FROM hint_usage WHERE assignment_id=?",
                (u["id"],)).fetchone()["c"]
        finally:
            conn.close()
        self.assertGreaterEqual(n, 1)


class TestTimeStrike(MTBase):
    def test_grants_2_marks_per_5_seconds_saved(self):
        """Bonus = +2 marks for every full 5s saved from the 30s window."""
        self.assertEqual(assign.STRIKE_WINDOW_SECONDS, 30)
        self.assertEqual(assign.mt_time_strike(0, 25), 12)      # instant
        self.assertEqual(assign.mt_time_strike(999, 25), 12)     # < 1s used
        self.assertEqual(assign.mt_time_strike(1000, 25), 10)    # 29s saved
        self.assertEqual(assign.mt_time_strike(5000, 25), 10)    # 25s saved
        self.assertEqual(assign.mt_time_strike(10000, 25), 8)    # 20s saved
        self.assertEqual(assign.mt_time_strike(15000, 25), 6)    # 15s saved
        self.assertEqual(assign.mt_time_strike(20000, 25), 4)    # 10s saved
        self.assertEqual(assign.mt_time_strike(25000, 25), 2)    #  5s saved
        self.assertEqual(assign.mt_time_strike(26000, 25), 0)    # < 5s left
        self.assertEqual(assign.mt_time_strike(30000, 25), 0)    # window gone
        self.assertEqual(assign.mt_time_strike(360000, 25), 0)   # long past
        self.assertEqual(assign.mt_time_strike(None, 25), 12)    # unknown

    def test_bonus_is_independent_of_base_points(self):
        for base in (10, 25, 50):
            self.assertEqual(assign.mt_time_strike(10000, base), 8)


class TestAdmin(MTBase):
    def test_bulk_add_teams(self):
        c = APP.test_client()
        _admin(c)
        r = c.post("/api/admin/round/1/teams/bulk", json={
            "teams": [
                {"name": "Bulk One", "id": "BULK01", "access_id": "bulk-a"},
                {"name": "Bulk Two", "id": "BULK02"},
                {"name": "Bulk One", "id": "BULK01", "access_id": "bulk-a"},
            ]})
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertEqual(j["added"], 2)
        self.assertEqual(j["failed"], 1)
        conn = db.get_connection()
        try:
            names = [x["team_id"] for x in conn.execute(
                "SELECT team_id FROM teams WHERE team_id LIKE 'BULK%' "
                "ORDER BY team_id").fetchall()]
        finally:
            conn.close()
        self.assertEqual(names, ["BULK01", "BULK02"])
        # require admin auth
        c2 = APP.test_client()
        self.assertEqual(c2.post("/api/admin/round/1/teams/bulk", json={
            "teams": [{"name": "X", "id": "Y"}]}).status_code, 401)
        # clean up so reruns stay idempotent
        conn = db.get_connection()
        try:
            conn.execute("DELETE FROM teams WHERE team_id LIKE 'BULK%'")
            conn.commit()
        finally:
            conn.close()

    def test_team_toggle_controls_login_and_login_page(self):
        c = APP.test_client()
        _admin(c)
        r = c.post("/api/admin/round/1/teams/bulk", json={
            "teams": [{"name": "Gate A", "id": "GATEA",
                       "access_id": "gate-access-a"}]})
        self.assertEqual(r.get_json()["added"], 1)
        tid = db.get_connection().execute(
            "SELECT id FROM teams WHERE team_id='GATEA'").fetchone()["id"]

        # login page reflects the newly added team as ENABLED
        pub = APP.test_client()
        html = pub.get("/r1/login").get_data(as_text=True)
        self.assertIn("Gate A", html)
        self.assertIn("ENABLED", html)

        # the team can actually log in
        r = pub.post("/r1/login", data={"team_name": "Gate A",
                                        "team_id": "gate-access-a"})
        self.assertEqual(r.status_code, 302)

        # admin disables the gate -> reflects on the login page + login blocked
        r = c.post("/api/admin/team/%d/toggle" % tid,
                   json={"active": False})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["active"])
        pub2 = APP.test_client()
        html = pub2.get("/r1/login").get_data(as_text=True)
        self.assertIn("Gate A", html)
        self.assertIn("DISABLED", html)
        r = pub2.post("/r1/login", data={"team_name": "Gate A",
                                         "team_id": "gate-access-a"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("currently unavailable", r.get_data(as_text=True))

        # re-enable -> login allowed again
        r = c.post("/api/admin/team/%d/toggle" % tid,
                   json={"active": True})
        self.assertTrue(r.get_json()["active"])
        pub3 = APP.test_client()
        r = pub3.post("/r1/login", data={"team_name": "Gate A",
                                         "team_id": "gate-access-a"})
        self.assertEqual(r.status_code, 302)

        # cleanup (login rows FK-reference the team)
        conn = db.get_connection()
        try:
            conn.execute("DELETE FROM participant_sessions WHERE team_id=?",
                         (tid,))
            conn.execute("DELETE FROM teams WHERE team_id='GATEA'")
            conn.commit()
        finally:
            conn.close()

    def test_admin_reset_wipes_play_data_but_keeps_teams(self):
        # create live play data for a dev team (session + solve)
        tid, token = _active_participant(None)
        c = _team_client(tid, token)
        d = self.summary(c)
        u = d["unlocked"]
        self.assertTrue(c.post("/api/participant/challenges/%d/submit" % u["id"],
                               json={"answer": self._server_answer(u["id"])})
                        .get_json()["accepted"])
        self.assertTrue(c.post("/api/participant/challenges/%d/submit" % u["id"],
                               json={"answer": self._server_answer2(u["id"])})
                        .get_json()["accepted"])
        conn = db.get_connection()
        try:
            sessions_before = conn.execute(
                "SELECT COUNT(*) c FROM round_sessions").fetchone()["c"]
            subs_before = conn.execute(
                "SELECT COUNT(*) c FROM submissions").fetchone()["c"]
            logins_before = conn.execute(
                "SELECT COUNT(*) c FROM participant_sessions WHERE "
                "round_name='round1' AND status='ACTIVE'").fetchone()["c"]
            teams_before = conn.execute(
                "SELECT COUNT(*) c FROM teams").fetchone()["c"]
        finally:
            conn.close()
        self.assertGreaterEqual(sessions_before, 1)
        self.assertGreaterEqual(subs_before, 1)
        self.assertGreaterEqual(logins_before, 1)

        a = APP.test_client()
        _admin(a)
        # requires confirm + admin auth
        self.assertEqual(a.post("/api/admin/round/1/reset",
                                json={}).status_code, 400)
        bare = APP.test_client()
        self.assertEqual(bare.post("/api/admin/round/1/reset",
                                   json={"confirm": True}).status_code, 401)

        r = a.post("/api/admin/round/1/reset", json={"confirm": True})
        self.assertEqual(r.status_code, 200)
        res = r.get_json()["reset"]
        self.assertEqual(res["categories"], 12)
        self.assertEqual(res["variants"], 48)
        self.assertGreaterEqual(res["cleared_logins"], 1)

        conn = db.get_connection()
        try:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) c FROM round_sessions").fetchone()["c"], 0)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) c FROM team_challenge_assignments")
                .fetchone()["c"], 0)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) c FROM submissions").fetchone()["c"], 0)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) c FROM participant_sessions WHERE "
                "round_name='round1' AND status='ACTIVE'").fetchone()["c"], 0)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) c FROM challenge_categories").fetchone()["c"], 12)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) c FROM challenge_variants").fetchone()["c"], 48)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) c FROM teams").fetchone()["c"], teams_before)
        finally:
            conn.close()

        # old token is now invalid -> must log in again
        self.assertEqual(c.get("/api/participant/round/1").status_code, 401)

    def test_reset_then_relogin_does_not_resurrect_completed_state(self):
        """Regression: an admin reset must give a completed team a FRESH round.

        A previous login's progress is mirrored into the signed cookie
        (round1.state). If the reset wipes the DB but leaves that mirror, the
        post-reset dashboard rehydrates the old completed/expired session from
        the cookie and bounces the team straight to the "Round Complete" page
        instead of a fresh round. Login must drop the stale mirror.
        """
        c = APP.test_client()
        creds = {"team_name": "DEV TEAM 01", "team_id": "DEV-TEAM-01"}
        self.assertEqual(c.post("/r1/login", data=creds).status_code, 302)

        # start the MT session and mirror it into the cookie (as a dashboard
        # visit mid-round does) BEFORE completing, so a stale mirror exists.
        d = self.summary(c)
        html = c.get("/r1/dashboard").get_data(as_text=True)
        self.assertNotIn("OPERATION DEBRIEF", html)
        for _ in range(6):
            d = self.summary(c)
            u = d["unlocked"]
            self.assertTrue(c.post(
                "/api/participant/challenges/%d/submit" % u["id"],
                json={"answer": self._server_answer(u["id"])})
                .get_json()["accepted"])
            self.assertTrue(c.post(
                "/api/participant/challenges/%d/submit" % u["id"],
                json={"answer": self._server_answer2(u["id"])})
                .get_json()["accepted"])
        # completed in DB + stale cookie mirror present
        conn = db.get_connection()
        try:
            self.assertEqual(conn.execute(
                "SELECT status FROM round_sessions WHERE team_id="
                "(SELECT id FROM teams WHERE team_id='DEV-TEAM-01')"
                " ORDER BY id DESC LIMIT 1").fetchone()["status"], "COMPLETED")
        finally:
            conn.close()

        a = APP.test_client()
        _admin(a)
        r = a.post("/api/admin/round/1/reset", json={"confirm": True})
        self.assertEqual(r.status_code, 200)

        # same browser: cookie invalidated -> re-login must start FRESH
        c.post("/r1/login", data=creds)
        final = c.get("/r1/dashboard")
        body = final.get_data(as_text=True)
        self.assertEqual(final.status_code, 200)
        self.assertNotIn("OPERATION DEBRIEF", body)
        self.assertNotIn("ROUND 1 COMPLETED", body)
        self.assertNotIn("ENGAGEMENT CONCLUDED", body)
        # and the new live session really is a fresh in-progress one
        d = self.summary(c)
        self.assertEqual(d["session"]["score"], 0)
        self.assertFalse(d["session"]["finished"])

    def test_admin_endpoints_require_auth(self):
        tid, token = _active_participant(None)
        c = _team_client(tid, token)
        for path in ("/api/admin/round/1", "/api/admin/answer-key",
                     "/api/admin/challenges"):
            self.assertEqual(c.get(path).status_code, 401, path)

    def test_admin_apis_show_answers(self):
        c = APP.test_client()
        _admin(c)
        r = c.get("/api/admin/answer-key")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(len(data["challenges"]), 48)
        sample = data["challenges"][0]
        self.assertTrue(sample["expected_answer"])
        self.assertRegex(sample["flag"], r"^MT\{")
        r = c.get("/api/admin/round/1")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        r = c.get("/api/admin/challenges")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.get_json()["catalog"]["variants"]), 48)

    def test_team_detail_includes_submissions(self):
        tid, token = _active_participant(None)
        c = _team_client(tid, token)
        d = self.summary(c)
        u = d["unlocked"]
        c.post("/api/participant/challenges/%d/submit" % u["id"],
               json={"answer": "nope"})
        a = APP.test_client()
        _admin(a)
        r = a.get("/api/admin/team/%d" % tid)
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data["team"]["id"], tid)
        self.assertEqual(len(data["assignments"]), 6)
        any_sub = any(a["submissions"] for a in data["assignments"])
        self.assertTrue(any_sub)


if __name__ == "__main__":
    unittest.main(verbosity=2)