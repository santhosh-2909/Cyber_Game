"""SHADOW HUNT Round 1 — acceptance tests.

Runs against a scratch SQLite DB (round1.db.DB_PATH is repointed at
/tmp/r1_test_mt.db) so the live database is never touched.

Run:   python -m round1.test_mt
"""
import json
import os
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
import admin_ops
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
                "SELECT id, variant_letter FROM teams WHERE team_id=?",
                (team_id,)).fetchone()
            assert row is not None, "missing team %s" % team_id
            tid, letter = row["id"], row["variant_letter"]
        else:
            row = conn.execute(
                "SELECT id, variant_letter FROM teams LIMIT 1").fetchone()
            assert row is not None, "no teams seeded"
            tid, letter = row["id"], row["variant_letter"]
        token = "tok-%s" % tid
        conn.execute(
            "DELETE FROM participant_sessions WHERE team_id=?", (tid,))
        conn.execute(
            "INSERT INTO participant_sessions (token, team_id, login_time, "
            "last_seen, status, round_name) VALUES (?,?,?,?,?,?)",
            (token, tid, db.now_ms(), db.now_ms(), "ACTIVE", "round1"))
        conn.commit()
        return tid, token, letter
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


class MTShadowBase(unittest.TestCase):
    def setUp(self):
        _seed()

    def summary(self, client):
        r = client.get("/api/participant/round/1")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        return r.get_json()

    def _server_flag(self, assignment_id):
        conn = db.get_connection()
        try:
            return conn.execute(
                "SELECT v.flag FROM team_challenge_assignments a "
                "JOIN challenge_variants v ON a.variant_id=v.id WHERE a.id=?",
                (assignment_id,)).fetchone()["flag"]
        finally:
            conn.close()

    def _submit(self, c, u, answer, check=True):
        r = c.post("/api/participant/challenges/%d/submit" % u["id"],
                   json={"answer": answer})
        g = r.get_json()
        if check:
            self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        return g

    def _solve(self, c, u):
        """Submit the correct flag for a challenge."""
        flag = self._server_flag(u["id"])
        return self._submit(c, u, flag)


LIMITS_SUM = 600


class TestShadowCatalog(MTShadowBase):
    def test_6_categories_18_variants_letters_abc_flags_cic(self):
        conn = db.get_connection()
        try:
            cats = conn.execute(
                "SELECT challenge_code FROM challenge_categories "
                "ORDER BY display_order").fetchall()
            variants = conn.execute(
                "SELECT COUNT(*) c FROM challenge_variants").fetchone()["c"]
            bad = conn.execute(
                "SELECT COUNT(*) c FROM challenge_variants WHERE flag='' OR "
                "flag NOT LIKE 'SHADOW{%' OR expected_answer != flag OR "
                "game_type != 'shadow_text'").fetchone()["c"]
            letters = [dict(r) for r in conn.execute(
                "SELECT challenge_category_id, variant_code FROM "
                "challenge_variants ORDER BY challenge_category_id, "
                "variant_code").fetchall()]
        finally:
            conn.close()
        self.assertEqual([r["challenge_code"] for r in cats],
                         ["C01", "C02", "C03", "C04", "C05", "C06"])
        self.assertEqual(variants, 18)
        self.assertEqual(bad, 0)
        per_cat = {}
        for r in letters:
            per_cat.setdefault(r["challenge_category_id"], []).append(
                r["variant_code"])
        for cat_id, codes in per_cat.items():
            self.assertEqual(sorted(codes), ["A", "B", "C"],
                             "each challenge needs variants A/B/C")

    def test_category_points_sum_to_600(self):
        conn = db.get_connection()
        try:
            pts = [r["points"] for r in conn.execute(
                "SELECT points FROM challenge_categories "
                "ORDER BY display_order").fetchall()]
        finally:
            conn.close()
        self.assertEqual(sorted(pts), [75, 100, 100, 100, 100, 125])
        self.assertEqual(sum(pts), 600)

    def test_catalogue_evidence_is_always_present(self):
        conn = db.get_connection()
        try:
            rows = conn.execute(
                "SELECT v.*, c.challenge_code cat FROM challenge_variants v "
                "JOIN challenge_categories c ON v.challenge_category_id=c.id "
                "ORDER BY c.display_order, v.variant_code").fetchall()
        finally:
            conn.close()
        self.assertEqual(len(rows), 18)
        for r in rows:
            self.assertRegex(r["flag"], r"^SHADOW\{[^}]+\}$")
            self.assertEqual(r["expected_answer"], r["flag"])
            self.assertTrue(r["hint"], r["variant_code"])
            ev = json.loads(r["evidence_config"])
            self.assertTrue(ev.get("evidence") if isinstance(ev["evidence"], str)
                            else bool(ev.get("evidence")))
            lab = json.loads(r["lab_data"] or "{}")
            self.assertNotIn("answer", lab)


class TestShadowRng(MTShadowBase):
    def test_deterministic_seeded_converge(self):
        r1a = assign._mt_rng("DEV-TEAM-01").choice(list(range(1000)))
        r1b = assign._mt_rng("DEV-TEAM-01").choice(list(range(1000)))
        r2 = assign._mt_rng("DEV-TEAM-02").choice(list(range(1000)))
        self.assertEqual(r1a, r1b)
        self.assertNotEqual(r1a, r2)


class TestShadowVariantLetters(MTShadowBase):
    def test_letters_round_robin_a_b_c(self):
        conn = db.get_connection()
        try:
            rows = conn.execute(
                "SELECT team_id, variant_letter FROM teams WHERE is_dev_seed=1 "
                "ORDER BY id LIMIT 6").fetchall()
        finally:
            conn.close()
        self.assertEqual([r["variant_letter"] for r in rows],
                         ["A", "B", "C", "A", "B", "C"])


class TestShadowHand(MTShadowBase):
    def test_hand_is_all_six_challenges_matching_team_letter(self):
        tid, token, letter = _active_participant(None, "DEV-TEAM-01")
        self.assertEqual(letter, "A")
        c = _team_client(tid, token)
        d = self.summary(c)
        s = d["session"]
        self.assertTrue(s["shadow"])
        self.assertEqual(s["challenges_per_team"], 6)
        self.assertEqual(s["status"], "ACTIVE")
        self.assertEqual(s["ends_at"] - s["started_at"], 30 * 60 * 1000)
        codes = sorted(a["code"] for a in d["assignments"])
        self.assertEqual(codes,
                         ["C01-A", "C02-A", "C03-A", "C04-A", "C05-A",
                          "C06-A"])
        for a in d["assignments"]:
            self.assertEqual(a["question_count"], 1)
            self.assertEqual(a["attempts_limit"], 3)
        # per-challenge value comes from the category points
        total = sum(a["points"] for a in d["assignments"])
        self.assertEqual(total, 600)

    def test_different_letters_get_different_variants(self):
        ta, toka, l_a = _active_participant(None, "DEV-TEAM-01")
        tb, tokb, l_b = _active_participant(None, "DEV-TEAM-02")
        self.assertEqual((l_a, l_b), ("A", "B"))
        ca = _team_client(ta, toka)
        cb = _team_client(tb, tokb)
        codes_a = sorted(a["code"] for a in self.summary(ca)["assignments"])
        codes_b = sorted(a["code"] for a in self.summary(cb)["assignments"])
        self.assertTrue(all(c.endswith("-A") for c in codes_a))
        self.assertTrue(all(c.endswith("-B") for c in codes_b))
        self.assertNotEqual(codes_a, codes_b)

    def test_unlocked_payload_exposes_single_question_and_evidence(self):
        tid, token, _ = _active_participant(None, "DEV-TEAM-05")
        c = _team_client(tid, token)
        d = self.summary(c)
        u = d["unlocked"]
        self.assertIsNotNone(u)
        self.assertEqual(u["attempts_limit"], 3)
        self.assertEqual(u["question2"], "")
        self.assertEqual(u["game_type2"], "")
        self.assertTrue(u["question"])
        self.assertTrue(u["evidence"])
        # no flag/answer leaks on an open challenge
        self.assertEqual(u["flag"], "")
        self.assertEqual(u["artifact_url"], "")
        self.assertNotIn('"flag": "SHADOW', json.dumps(d))


class TestShadowPlay(MTShadowBase):
    def test_wrong_flag_scored_zero_keeps_challenge_open(self):
        tid, token, _ = _active_participant(None, "DEV-TEAM-02")
        c = _team_client(tid, token)
        d = self.summary(c)
        u = d["unlocked"]
        g = self._submit(c, u, "SHADOW{WRONG}")
        self.assertFalse(g["accepted"])
        self.assertEqual(g["points"], 0)
        self.assertEqual(g["points_total"], 0)
        self.assertEqual(g["attempts_used"], 1)
        self.assertEqual(g["attempts_limit"], 3)
        self.assertFalse(g["exhausted"])
        self.assertEqual(g["phase"], "q1")
        # challenge still open, never failed by a single wrong attempt
        self.assertEqual(c.get("/api/participant/challenges/%d" % u["id"])
                         .get_json()["status"], "IN_PROGRESS")

    def test_three_wrong_attempts_fail_challenge_for_zero_points(self):
        tid, token, _ = _active_participant(None, "DEV-TEAM-08")
        c = _team_client(tid, token)
        d = self.summary(c)
        u = d["unlocked"]
        for i in (1, 2):
            g = self._submit(c, u, "SHADOW{WRONG_%d}" % i)
            self.assertFalse(g["accepted"])
            self.assertFalse(g["exhausted"])
            self.assertEqual(g["attempts_used"], i)
            self.assertEqual(g["points_total"], 0)
        g = self._submit(c, u, "SHADOW{WRONG_3}")
        self.assertFalse(g["accepted"])
        self.assertTrue(g["exhausted"])
        self.assertEqual(g["attempts_used"], 3)
        self.assertEqual(g["attempts_limit"], 3)
        self.assertEqual(g["points_total"], 0)
        # challenge is now FAILED and further submissions are rejected
        detail = c.get("/api/participant/challenges/%d" % u["id"]).get_json()
        self.assertEqual(detail["status"], "FAILED")
        self.assertTrue(detail["failed"])
        self.assertEqual(detail["attempts_limit"], 3)
        dup = c.post("/api/participant/challenges/%d/submit" % u["id"],
                     json={"answer": "SHADOW{WRONG_4}"})
        self.assertEqual(dup.status_code, 403)
        # overview shows CLOSED card, other challenges still open
        d2 = self.summary(c)
        mine = [a for a in d2["assignments"] if a["id"] == u["id"]]
        self.assertTrue(mine and mine[0]["failed"])
        self.assertEqual(self.summary(c)["session"]["status"], "ACTIVE")

    def test_correct_flag_on_third_attempt_still_scores(self):
        tid, token, _ = _active_participant(None, "DEV-TEAM-09")
        c = _team_client(tid, token)
        d = self.summary(c)
        u = d["unlocked"]
        expected = next(a["points"] for a in d["assignments"]
                        if a["id"] == u["id"])
        for i in (1, 2):
            self._submit(c, u, "SHADOW{WRONG_%d}" % i)
        g = self._solve(c, u)
        self.assertTrue(g["accepted"])
        self.assertEqual(g["attempts_used"], 3)
        self.assertEqual(g["attempts_limit"], 3)
        self.assertEqual(g["points"], expected)
        self.assertEqual(g["points_total"], expected)

    def test_session_completes_when_remaining_cards_resolve_or_fail(self):
        tid, token, _ = _active_participant(None, "DEV-TEAM-04")
        c = _team_client(tid, token)
        d = self.summary(c)
        u = d["unlocked"]
        failed_points = u["points"]
        # burn this card on 3 wrong flags
        for i in (1, 2, 3):
            self._submit(c, u, "SHADOW{WRONG_%d}" % i)
        # solve the other five
        d = self.summary(c)
        opens = [a for a in d["assignments"] if a["status"] != "FAILED"]
        self.assertEqual(len(opens), 5)
        solved_and_points = 0
        for a in opens:
            detail = c.get("/api/participant/challenges/%d" % a["id"])
            self.assertEqual(detail.status_code, 200, a["code"])
            g = self._solve(c, a)
            self.assertTrue(g["accepted"], a["code"])
            solved_and_points += g["points_total"]
        final = self.summary(c)
        self.assertEqual(final["session"]["status"], "COMPLETED")
        self.assertEqual(final["session"]["solved"], 5)
        self.assertEqual(final["session"]["score"], 600 - failed_points)
        self.assertIsNone(final["unlocked"])

    def test_correct_flag_scores_category_points_and_awards_flag(self):
        tid, token, _ = _active_participant(None, "DEV-TEAM-02")
        c = _team_client(tid, token)
        d = self.summary(c)
        u = d["unlocked"]
        expected = d["assignments"][0]["points"]
        g = self._solve(c, u)
        self.assertTrue(g["accepted"])
        self.assertTrue(g["q1_done"])
        self.assertEqual(g["stage_attempts"], 1)
        self.assertEqual(g["points"], expected)
        self.assertEqual(g["strike"], 0)
        self.assertEqual(g["points_total"], expected)
        self.assertRegex(g["flag"], r"^SHADOW\{[^}]+\}$")
        # solved challenge carries its OWN flag on revisit (view-only mode)
        detail = c.get("/api/participant/challenges/%d" % u["id"]).get_json()
        self.assertEqual(detail["flag"], self._server_flag(u["id"]))
        self.assertTrue(detail["solved"])

    def test_resubmit_after_solving_is_already_solved_no_points(self):
        tid, token, _ = _active_participant(None, "DEV-TEAM-02")
        c = _team_client(tid, token)
        d = self.summary(c)
        u = d["unlocked"]
        flag = self._server_flag(u["id"])
        self._solve(c, u)
        g = self._submit(c, u, flag)
        self.assertTrue(g["accepted"])
        self.assertTrue(g["already_solved"])
        self.assertEqual(g["points"], 0)
        self.assertEqual(g["points_total"], 0)

    def test_any_order_play_all_open(self):
        tid, token, _ = _active_participant(None, "DEV-TEAM-04")
        c = _team_client(tid, token)
        d = self.summary(c)
        ids = [a["id"] for a in d["assignments"]]
        # every challenge is unlocked from the start (no 403s)
        for aid in ids:
            r = c.get("/api/participant/challenges/%d" % aid)
            self.assertEqual(r.status_code, 200, aid)
        # solve the LAST assignment first, scoring lands regardless of order
        last = d["assignments"][-1]
        g = self._solve(c, last)
        self.assertTrue(g["accepted"])
        self.assertEqual(g["points"],
                         d["assignments"][-1]["points"])
        d2 = self.summary(c)
        self.assertEqual(d2["session"]["solved"], 1)
        self.assertEqual(d2["session"]["score"],
                         d["assignments"][-1]["points"])

    def test_all_six_flagged_sum_to_600_and_session_completes(self):
        tid, token, _ = _active_participant(None, "DEV-TEAM-06")
        c = _team_client(tid, token)
        d = self.summary(c)
        expected_total = sum(a["points"] for a in d["assignments"])
        self.assertEqual(expected_total, 600)
        flushed = []
        for i, a in enumerate(d["assignments"]):
            g = self._solve(c, a)
            self.assertTrue(g["accepted"], a["code"])
            flushed.append(a["id"])
            # a solved card stays revisit-able (with its OWN flag) while any
            # other challenge is still open
            if i < len(d["assignments"]) - 1:
                detail = c.get("/api/participant/challenges/%d" % a["id"])
                self.assertEqual(detail.status_code, 200, a["code"])
                self.assertEqual(detail.get_json()["flag"],
                                 self._server_flag(a["id"]), a["code"])
        final = self.summary(c)
        self.assertEqual(final["session"]["solved"], 6)
        self.assertEqual(final["session"]["score"], 600)
        self.assertEqual(final["session"]["status"], "COMPLETED")
        self.assertIsNone(final["unlocked"])
        for a in final["assignments"]:
            self.assertTrue(a["solved"])

    def test_expired_session_locks_submissions(self):
        tid, token, _ = _active_participant(None, "DEV-TEAM-07")
        c = _team_client(tid, token)
        d = self.summary(c)
        u = d["unlocked"]
        conn = db.get_connection()
        try:
            conn.execute(
                "UPDATE round_sessions SET ends_at=? WHERE id=?",
                (db.now_ms() - 1000, d["session"]["id"]))
            conn.commit()
        finally:
            conn.close()
        r = c.post("/api/participant/challenges/%d/submit" % u["id"],
                   json={"answer": "SHADOW{ANY}"})
        self.assertEqual(r.status_code, 410)
        self.assertEqual(r.get_json()["error"], "session_ended")

    def test_empty_answers_rejected_without_consuming_attempt(self):
        tid, token, _ = _active_participant(None, "DEV-TEAM-02")
        c = _team_client(tid, token)
        d = self.summary(c)
        aid = d["unlocked"]["id"]
        for payload in ({"answer": ""}, {"answer": "   \t "},
                        {"answer": None}, {}, {"answer": 123}):
            r = c.post("/api/participant/challenges/%d/submit" % aid,
                       json=payload)
            self.assertEqual(r.status_code, 400)
            self.assertEqual(r.get_json()["error"], "empty_answer")
        conn = db.get_connection()
        try:
            used = conn.execute(
                "SELECT COUNT(*) FROM submissions WHERE assignment_id=?",
                (aid,)).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(used, 0)

    def test_case_insensitive_flags_are_accepted(self):
        for casing in ("lower", "upper", "mixed"):
            tid, token, _ = _active_participant(None, "DEV-TEAM-10")
            c = _team_client(tid, token)
            d = self.summary(c)
            u = d["unlocked"]
            flag = self._server_flag(u["id"])
            if casing == "lower":
                answer = flag.lower()
            elif casing == "upper":
                answer = flag.upper()
            else:
                answer = "".join(ch.upper() if i % 2 else ch.lower()
                                 for i, ch in enumerate(flag))
            g = self._submit(c, u, answer)
            self.assertTrue(g["accepted"],
                            "%s-cased flag should grade correct" % casing)

    def test_bare_inner_token_without_cic_wrapper_is_accepted(self):
        for i, casing in enumerate(("inner", "lower", "upper")):
            tid, token, _ = _active_participant(
                None, "DEV-TEAM-%d" % (11 + i))
            c = _team_client(tid, token)
            d = self.summary(c)
            u = d["unlocked"]
            flag = self._server_flag(u["id"])
            self.assertRegex(flag, "^SHADOW\\{.+\\}$")
            inner = flag[7:-1]
            answer = {"inner": inner, "lower": inner.lower(),
                      "upper": inner.upper()}[casing]
            g = self._submit(c, u, answer)
            self.assertTrue(g["accepted"],
                            "bare token %r should grade correct" % answer)
            self.assertEqual(g["points"], d["assignments"][0]["points"])

    def test_hint_returns_and_logs_usage(self):
        tid, token, _ = _active_participant(None, "DEV-TEAM-02")
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

    def test_all_real_flags_never_leak_into_unsolved_payloads(self):
        seen_codes = set()
        conn = db.get_connection()
        try:
            real_flags = {r["flag"] for r in conn.execute(
                "SELECT flag FROM challenge_variants").fetchall()}
        finally:
            conn.close()
        for team_idx in ("DEV-TEAM-%02d" % i for i in range(1, 13)):
            tid, token, _ = _active_participant(None, team_idx)
            c = _team_client(tid, token)
            d = self.summary(c)
            for a in d["assignments"]:
                du = c.get("/api/participant/challenges/%d" % a["id"]).get_json()
                if du["status"] == "COMPLETED":
                    continue
                blob = json.dumps(du)
                self.assertEqual(du["flag"], "", a["code"])
                for f in real_flags:
                    self.assertNotIn(f, blob, "%s leaked in %s"
                                     % (f, a["code"]))
                seen_codes.add(du["code"])
            # solve the whole hand so next teams see fresh sessions
            for a in d["assignments"]:
                self._solve(c, a)
        self.assertGreaterEqual(len(seen_codes), 18,
                                "expected all 18 A/B/C variants seen")


class TestShadowC04Artifact(MTShadowBase):
    def test_artifact_route_granted_only_to_own_variant(self):
        tid, token, letter = _active_participant(None, "DEV-TEAM-02")
        self.assertEqual(letter, "B")
        c = _team_client(tid, token)
        d = self.summary(c)
        own = letter.lower()
        r = c.get("/challenge4/%s.html" % own)
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        conn = db.get_connection()
        try:
            c04 = conn.execute(
                "SELECT v.flag FROM team_challenge_assignments a "
                "JOIN challenge_categories c ON a.challenge_category_id=c.id "
                "JOIN challenge_variants v ON a.variant_id=v.id "
                "WHERE a.session_id=? AND c.challenge_code='C04'",
                (d["session"]["id"],)).fetchone()["flag"]
        finally:
            conn.close()
        # the redesign exposes only the recovered USERNAME (flag inner,
        # lowercased) as the page comment — never the SHADOW envelope itself
        username = c04[len("SHADOW{"):-1].lower()
        self.assertIn(username, body,
                      "their own recovered-USERNAME comment must be present")
        self.assertNotIn(c04, body,
                         "the solved SHADOW envelope must never be a comment")
        # other letters route nowhere
        for other in ("a", "c"):
            self.assertEqual(c.get("/challenge4/%s.html" % other).status_code,
                             404, other)
        self.assertEqual(c.get("/challenge4/z.html").status_code, 404)

    def test_artifact_requires_login(self):
        r = APP.test_client().get("/challenge4/a.html")
        self.assertEqual(r.status_code, 302)


class TestShadowAdmin(MTShadowBase):
    def test_bulk_add_teams_stamps_round_robin_letters(self):
        c = APP.test_client()
        _admin(c)
        r = c.post("/api/admin/round/1/teams/bulk", json={
            "teams": [
                {"name": "Bulk One", "id": "BULK01", "access_id": "bulk-a"},
                {"name": "Bulk Two", "id": "BULK02"},
                {"name": "Bulk Three", "id": "BULK03"},
            ]})
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertEqual(j["added"], 3)
        conn = db.get_connection()
        try:
            rows = conn.execute(
                "SELECT team_id, variant_letter FROM teams WHERE "
                "team_id IN ('BULK01','BULK02','BULK03') ORDER BY id").fetchall()
            for row in conn.execute(
                    "SELECT team_id FROM teams WHERE team_id LIKE 'BULK%' "
                    "ORDER BY id").fetchall():
                pass
            letters = dict((x["team_id"], x["variant_letter"]) for x in rows)
        finally:
            conn.close()
        # consecutive NEW teams get a rotating A/B/C — covers all three
        self.assertEqual(sorted(letters.values()), ["A", "B", "C"])
        self.assertEqual(len(set(letters.values())), 3)
        conn = db.get_connection()
        try:
            conn.execute("DELETE FROM teams WHERE team_id LIKE 'BULK%'")
            conn.commit()
        finally:
            conn.close()

    def test_admin_answer_key_and_apis(self):
        c = APP.test_client()
        _admin(c)
        r = c.get("/api/admin/answer-key")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(len(data["challenges"]), 18)
        for ch in data["challenges"]:
            self.assertRegex(ch["flag"], r"^SHADOW{")
            self.assertEqual(ch["expected_answer"], ch["flag"])
        self.assertEqual(c.get("/api/admin/round/1").status_code, 200)
        cat = c.get("/api/admin/challenges").get_json()
        self.assertEqual(len(cat["catalog"]["variants"]), 18)

    def test_monitor_data_includes_variant_letter(self):
        tid, token, letter = _active_participant(None, "DEV-TEAM-01")
        c = APP.test_client()
        _admin(c)
        data = c.get("/api/admin/round/1").get_json()
        row = [t for t in data["teams"] if t["id"] == tid][0]
        self.assertEqual(row["variant_letter"], letter)
        self.assertEqual(data["summary"]["categories"], 6)
        self.assertEqual(data["summary"]["variants"], 18)

    def test_team_detail_includes_submissions(self):
        tid, token, _ = _active_participant(None, "DEV-TEAM-02")
        c = _team_client(tid, token)
        d = self.summary(c)
        u = d["unlocked"]
        c.post("/api/participant/challenges/%d/submit" % u["id"],
               json={"answer": "SHADOW{WRONG}"})
        a = APP.test_client()
        _admin(a)
        r = a.get("/api/admin/team/%d" % tid)
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data["team"]["id"], tid)
        self.assertEqual(len(data["assignments"]), 6)
        any_sub = any(a["submissions"] for a in data["assignments"])
        self.assertTrue(any_sub)
        self.assertIn("variant_letter", data["team"])

    def test_admin_reset_keeps_teams_and_reseeds_catalogue(self):
        tid, token, _ = _active_participant(None, "DEV-TEAM-08")
        c = _team_client(tid, token)
        d = self.summary(c)
        self._solve(c, d["unlocked"])
        a = APP.test_client()
        _admin(a)
        r = a.post("/api/admin/round/1/reset", json={"confirm": True})
        self.assertEqual(r.status_code, 200)
        res = r.get_json()["reset"]
        self.assertEqual(res["categories"], 6)
        self.assertEqual(res["variants"], 18)
        conn = db.get_connection()
        try:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) c FROM challenge_categories").fetchone()["c"], 6)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) c FROM challenge_variants").fetchone()["c"], 18)
            # old token invalid -> must log in again
            self.assertEqual(c.get("/api/participant/round/1").status_code, 401)
        finally:
            conn.close()

    def test_admin_endpoints_require_auth(self):
        tid, token, _ = _active_participant(None)
        c = _team_client(tid, token)
        for path in ("/api/admin/round/1", "/api/admin/answer-key",
                     "/api/admin/challenges"):
            self.assertEqual(c.get(path).status_code, 401, path)

    def test_leaderboard_reflects_shadow_scores(self):
        tid, token, _ = _active_participant(None, "DEV-TEAM-02")
        c = _team_client(tid, token)
        d = self.summary(c)
        u = d["unlocked"]
        g = self._solve(c, u)
        rows = admin_ops.leaderboard(limit=50)
        mine = [r for r in rows if r["team_id"] == tid]
        self.assertTrue(mine, "team must appear on the leaderboard")
        self.assertEqual(mine[0]["r1_score"], g["points_total"])


if __name__ == "__main__":
    unittest.main(verbosity=2)