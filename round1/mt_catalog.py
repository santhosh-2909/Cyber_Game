"""SHADOW HUNT (Round 1) — authoritative 18-challenge catalogue.

Six challenges x three variants (A/B/C), transcribed from the Shadow Hunt
Master Specification. Participants receive ONE global variant letter
determined when their team is created (round-robin: teams 1,4,7,10 -> A;
2,5,8 -> B; 3,6,9 -> C) and submit SHADOW{...} flags directly. Grading
evaluates the submission against the flag SAVED here (challenge_variants.flag);
wrong flags are recorded as wrong attempts but never lock the challenge.

This file is the single source of truth that `seed_mt.py` upserts into
`challenge_categories` / `challenge_variants`.

Per-variant entries carry:
    code        variant code        ("A" / "B" / "C")
    domain      domain key          (crypto / email / logs / source / encode / words)
    game_type   engine key          ("shadow_text")
    title       challenge title     (same for all three variants)
    answer      canonical flag      (server-side only, same as flag)
    flag        SHADOW{...} flag       (server-side only)
    q / hint    participant question + hint
    ev          evidence: static text/object shipped as-is
    cfg         public game_config extra (e.g. the challenge-4 staff-portal URL)
"""

# Domain key -> (category challenge_code, display name, difficulty, points)
# Points: 75 + 100 + 100 + 100 + 125 + 100 = 600 maximum.
DOMAIN_META = {
    "crypto": ("C01", "Shifted Message", "Easy", 75),
    "email":  ("C02", "Email Trail", "Easy-Medium", 100),
    "logs":   ("C03", "Midnight Log", "Easy-Medium", 100),
    "source": ("C04", "Developer's Mistake", "Easy-Medium", 100),
    "encode": ("C05", "Encoded Ransom", "Easy-Medium", 125),
    "words":  ("C06", "Final Connection", "Medium", 100),
}

CHALLENGES = [
    # ------------------------------------------------------------------ C01
    {
        "code": "A", "domain": "crypto", "game_type": "shadow_text",
        "title": "Shifted Message",
        "answer": "SHADOW{CAESAR_IS_EASY}",
        "flag": "SHADOW{CAESAR_IS_EASY}",
        "accept": [],
        "points": 75, "difficulty": "Easy",
        "solve_time": "3m",
        "q": "The ciphertext below has been shifted with one fixed Caesar "
            "rotation. Decode the message and submit the recovered SHADOW{...} flag.",
        "hint": "A Caesar shift moves every letter by the same amount. Here "
                "VKDGRZ{...} decodes to SHADOW{...}, so the rotation is easy to find.",
        "ev": "VKDGRZ{FDHVDU_LV_HDVB}",
        "cfg": {},
    },
    {
        "code": "B", "domain": "crypto", "game_type": "shadow_text",
        "title": "Shifted Message",
        "answer": "SHADOW{SIMPLE_SHIFT_WINS}",
        "flag": "SHADOW{SIMPLE_SHIFT_WINS}",
        "accept": [],
        "points": 75, "difficulty": "Easy",
        "solve_time": "3m",
        "q": "The ciphertext below has been shifted with one fixed Caesar "
            "rotation. Decode the message and submit the recovered SHADOW{...} flag.",
        "hint": "A Caesar shift moves every letter by the same amount. Here "
                "VKDGRZ{...} decodes to SHADOW{...}, so the rotation is easy to find.",
        "ev": "VKDGRZ{VLPSOH_VKLIW_ZLQV}",
        "cfg": {},
    },
    {
        "code": "C", "domain": "crypto", "game_type": "shadow_text",
        "title": "Shifted Message",
        "answer": "SHADOW{ROT_THREE_BASICS}",
        "flag": "SHADOW{ROT_THREE_BASICS}",
        "accept": [],
        "points": 75, "difficulty": "Easy",
        "solve_time": "3m",
        "q": "The ciphertext below has been shifted with one fixed Caesar "
            "rotation. Decode the message and submit the recovered SHADOW{...} flag.",
        "hint": "A Caesar shift moves every letter by the same amount. Here "
                "VKDGRZ{...} decodes to SHADOW{...}, so the rotation is easy to find.",
        "ev": "VKDGRZ{URW_WKUHH_EDVLFV}",
        "cfg": {},
    },

    # ------------------------------------------------------------------ C02
    {
        "code": "A", "domain": "email", "game_type": "shadow_text",
        "title": "Email Trail",
        "answer": "SHADOW{203_0_113_42}",
        "flag": "SHADOW{203_0_113_42}",
        "accept": [],
        "points": 100, "difficulty": "Easy-Medium",
        "solve_time": "5m",
        "q": "Examine the full message headers. The relay that delivered this "
            "email claims a legitimate-looking name, but its REAL IP address is "
            "visible in the Received lines. Submit that IP wrapped in the "
            "SHADOW{...} flag format, using underscores instead of dots.",
        "hint": "Received lines list every hop the message crossed. The "
                "suspicious relay's true address sits in the square brackets "
                "[...] of its Received line.",
        "ev": ("Return-Path: <anonymous@unknown-mail.test>\n"
               "Received: from suspicious-node.test (suspicious-node.test [203.0.113.42])\n"
               "        by mail-server.test with ESMTP id 9F2A; Wed, 23 Sep 2026 21:14:08 +0000\n"
               "From: anonymous@unknown-mail.test\n"
               "To: investigation@cic.test\n"
               "Subject: You should stop looking.\n"
               "Date: Wed, 23 Sep 2026 21:14:08 +0000\n"
               "X-Mailer: ShadowMail 0.9.3\n"
               "User-Agent: Mozilla/5.0 (X11; Linux x86_64)"),
        "cfg": {},
    },
    {
        "code": "B", "domain": "email", "game_type": "shadow_text",
        "title": "Email Trail",
        "answer": "SHADOW{198_51_100_77}",
        "flag": "SHADOW{198_51_100_77}",
        "accept": [],
        "points": 100, "difficulty": "Easy-Medium",
        "solve_time": "5m",
        "q": "Examine the full message headers. The relay that delivered this "
            "email claims a legitimate-looking name, but its REAL IP address is "
            "visible in the Received lines. Submit that IP wrapped in the "
            "SHADOW{...} flag format, using underscores instead of dots.",
        "hint": "Received lines list every hop the message crossed. The "
                "suspicious relay's true address sits in the square brackets "
                "[...] of its Received line.",
        "ev": ("Return-Path: <anonymous@unknown-mail.test>\n"
               "Received: from ghost-relay.test (ghost-relay.test [198.51.100.77])\n"
               "        by mail-server.test with ESMTP id 4C1D; Wed, 23 Sep 2026 22:03:41 +0000\n"
               "From: anonymous@unknown-mail.test\n"
               "To: investigation@cic.test\n"
               "Subject: Nobody will find me.\n"
               "Date: Wed, 23 Sep 2026 22:03:41 +0000\n"
               "X-Mailer: ShadowMail 0.9.3\n"
               "User-Agent: Mozilla/5.0 (X11; Linux x86_64)"),
        "cfg": {},
    },
    {
        "code": "C", "domain": "email", "game_type": "shadow_text",
        "title": "Email Trail",
        "answer": "SHADOW{192_0_2_10}",
        "flag": "SHADOW{192_0_2_10}",
        "accept": [],
        "points": 100, "difficulty": "Easy-Medium",
        "solve_time": "5m",
        "q": "Examine the full message headers. The relay that delivered this "
            "email claims a legitimate-looking name, but its REAL IP address is "
            "visible in the Received lines. Submit that IP wrapped in the "
            "SHADOW{...} flag format, using underscores instead of dots.",
        "hint": "Received lines list every hop the message crossed. The "
                "suspicious relay's true address sits in the square brackets "
                "[...] of its Received line.",
        "ev": ("Return-Path: <anonymous@unknown-mail.test>\n"
               "Received: from hidden-node.test (hidden-node.test [192.0.2.10])\n"
               "        by mail-server.test with ESMTP id 8E2A; Wed, 23 Sep 2026 23:27:19 +0000\n"
               "From: anonymous@unknown-mail.test\n"
               "To: investigation@cic.test\n"
               "Subject: This trail ends here.\n"
               "Date: Wed, 23 Sep 2026 23:27:19 +0000\n"
               "X-Mailer: ShadowMail 0.9.3\n"
               "User-Agent: Mozilla/5.0 (X11; Linux x86_64)"),
        "cfg": {},
    },

    # ------------------------------------------------------------------ C03
    {
        "code": "A", "domain": "logs", "game_type": "shadow_text",
        "title": "Midnight Log",
        "answer": "SHADOW{MIDNIGHT_ARCHIVE}",
        "flag": "SHADOW{MIDNIGHT_ARCHIVE}",
        "accept": [],
        "points": 100, "difficulty": "Easy-Medium",
        "solve_time": "5m",
        "q": "One archived file was downloaded from the server moments after the "
            "breach session started. Identify which archive left the machine and "
            "submit its NAME wrapped in the SHADOW{...} flag format.",
        "hint": "Follow the suspicious session from LOGIN SUCCESS to DOWNLOAD — "
                "only one archive reaches the wire.",
        "ev": ("2026-09-23 22:37:51 INFO  173.203.12.9    LOGIN FAILED   admin\n"
               "2026-09-23 22:41:08 INFO  10.10.10.24     LOGIN SUCCESS  service_backup\n"
               "2026-09-23 22:41:12 INFO  10.10.10.24     VIEW          /srv/archive/\n"
               "2026-09-23 22:41:19 INFO  10.10.10.24     ACCESS        /srv/archive/midnight_archive.zip\n"
               "2026-09-23 22:41:23 INFO  10.10.10.24     DOWNLOAD      midnight_archive.zip  (481 MB)\n"
               "2026-09-23 22:41:40 INFO  10.10.10.24     LOGOUT        established session dropped"),
        "cfg": {},
    },
    {
        "code": "B", "domain": "logs", "game_type": "shadow_text",
        "title": "Midnight Log",
        "answer": "SHADOW{PROJECT_SECRETS}",
        "flag": "SHADOW{PROJECT_SECRETS}",
        "accept": [],
        "points": 100, "difficulty": "Easy-Medium",
        "solve_time": "5m",
        "q": "One archived file was downloaded from the server moments after the "
            "breach session started. Identify which archive left the machine and "
            "submit its NAME wrapped in the SHADOW{...} flag format.",
        "hint": "Follow the suspicious session from LOGIN SUCCESS to DOWNLOAD — "
                "only one archive reaches the wire.",
        "ev": ("2026-09-23 22:58:30 INFO  54.32.10.7      LOGIN FAILED   operator\n"
               "2026-09-23 23:02:10 INFO  10.10.10.55     LOGIN SUCCESS  nightly_scan\n"
               "2026-09-23 23:02:15 INFO  10.10.10.55     VIEW          /srv/buckets/\n"
               "2026-09-23 23:02:22 INFO  10.10.10.55     ACCESS        /srv/buckets/project_secrets.zip\n"
               "2026-09-23 23:02:27 INFO  10.10.10.55     DOWNLOAD      project_secrets.zip  (1024 MB)\n"
               "2026-09-23 23:02:44 INFO  10.10.10.55     LOGOUT        established session dropped"),
        "cfg": {},
    },
    {
        "code": "C", "domain": "logs", "game_type": "shadow_text",
        "title": "Midnight Log",
        "answer": "SHADOW{BACKUP_VAULT}",
        "flag": "SHADOW{BACKUP_VAULT}",
        "accept": [],
        "points": 100, "difficulty": "Easy-Medium",
        "solve_time": "5m",
        "q": "One archived file was downloaded from the server moments after the "
            "breach session started. Identify which archive left the machine and "
            "submit its NAME wrapped in the SHADOW{...} flag format.",
        "hint": "Follow the suspicious session from LOGIN SUCCESS to DOWNLOAD — "
                "only one archive reaches the wire.",
        "ev": ("2026-09-24 00:10:03 INFO  8.8.201.66      LOGIN FAILED   root\n"
               "2026-09-24 00:14:17 INFO  10.10.10.77     LOGIN SUCCESS  vault_sync\n"
               "2026-09-24 00:14:22 INFO  10.10.10.77     VIEW          /srv/vault/\n"
               "2026-09-24 00:14:29 INFO  10.10.10.77     ACCESS        /srv/vault/backup_vault.zip\n"
               "2026-09-24 00:14:34 INFO  10.10.10.77     DOWNLOAD      backup_vault.zip  (756 MB)\n"
               "2026-09-24 00:14:50 INFO  10.10.10.77     LOGOUT        established session dropped"),
        "cfg": {},
    },

    # ------------------------------------------------------------------ C04
    {
        "code": "A", "domain": "source", "game_type": "shadow_text",
        "title": "The Hidden Login Trail",
        "answer": "SHADOW{SHADOW_ADMIN}",
        "flag": "SHADOW{SHADOW_ADMIN}",
        "accept": [],
        "points": 100, "difficulty": "Easy-Medium",
        "solve_time": "4m",
        "q": "A staff-only portal is still live and someone left a hidden login "
            "trail on it. Open the portal and inspect its RAW HTML SOURCE to "
            "find the hidden USERNAME, then wrap it in SHADOW{...}. The flag is "
            "the recovered USERNAME wrapped in UPPERCASE (recover a lowercase "
            "username, submit it UPPERCASED inside SHADOW{...}).",
        "hint": "The portal hides the USERNAME in its page metadata -- an HTML "
                "comment or meta tag that appears only in the page source, "
                "never in the rendered page. Read the RAW SOURCE to find it.",
        "ev": "A staff-only login trail is still live. Open the portal and read "
              "its SOURCE to recover the hidden USERNAME.",
        "cfg": {"artifact_url": "/challenge4/A.html"},
    },
    {
        "code": "B", "domain": "source", "game_type": "shadow_text",
        "title": "The Hidden Login Trail",
        "answer": "SHADOW{NIGHT_OPERATOR}",
        "flag": "SHADOW{NIGHT_OPERATOR}",
        "accept": [],
        "points": 100, "difficulty": "Easy-Medium",
        "solve_time": "4m",
        "q": "An undocumented operator account is still live in the staff portal. "
            "Open the portal and inspect its RAW HTML SOURCE to find the hidden "
            "USERNAME, then wrap it in SHADOW{...}. The flag is the recovered "
            "USERNAME in UPPERCASE (e.g. recovering a word like ``operator_login`` "
            "gives SHADOW{OPERATOR_LOGIN}).",
        "hint": "Look for the username in the page source -- a debug meta tag "
                "or comment left by the developer. It is lowercase like "
                "``night_operator``; the flag is that word in UPPERCASE inside "
                "SHADOW{...}.",
        "ev": "An undocumented operator trail is still live in the staff portal. "
              "Inspect its SOURCE to recover the hidden USERNAME.",
        "cfg": {"artifact_url": "/challenge4/B.html"},
    },
    {
        "code": "C", "domain": "source", "game_type": "shadow_text",
        "title": "The Hidden Login Trail",
        "answer": "SHADOW{GHOST_USER}",
        "flag": "SHADOW{GHOST_USER}",
        "accept": [],
        "points": 100, "difficulty": "Easy-Medium",
        "solve_time": "4m",
        "q": "There is one more hidden user in the portal's login trail. Inspect "
            "the RAW HTML SOURCE of the staff portal, recover the hidden "
            "USERNAME, and wrap it in SHADOW{...}. The flag is the recovered "
            "USERNAME in UPPERCASE (e.g. recovering a placeholder word like "
            "``temporary_account`` would give SHADOW{TEMPORARY_ACCOUNT}; "
            "recover the real USERNAME from the source instead).",
        "hint": "The username is stashed in the page metadata -- check every "
                "comment and meta tag in the source. It is lowercase like "
                "``ghost_user``; the flag is that word in UPPERCASE inside "
                "SHADOW{...}.",
        "ev": "A final hidden user is in the portal trail. Open the portal and "
              "read its SOURCE to recover the hidden USERNAME.",
        "cfg": {"artifact_url": "/challenge4/C.html"},
    },
    # ------------------------------------------------------------------ C05
    {
        "code": "A", "domain": "encode", "game_type": "shadow_text",
        "title": "Encoded Ransom",
        "answer": "SHADOW{BASE64_IS_NOT_ENCRYPTION}",
        "flag": "SHADOW{BASE64_IS_NOT_ENCRYPTION}",
        "accept": [],
        "points": 125, "difficulty": "Easy-Medium",
        "solve_time": "4m",
        "q": "The ransom note hides one encoded token. Decode it to reveal the "
            "SHADOW{...} flag and submit it.",
        "hint": "The token is a binary-to-text encoding whose output often ends "
                "in '=' padding — decode it to plain text.",
        "ev": "U0hBRE9Xe0JBU0U2NF9JU19OT1RfRU5DUllQVElPTn0=",
        "cfg": {},
    },
    {
        "code": "B", "domain": "encode", "game_type": "shadow_text",
        "title": "Encoded Ransom",
        "answer": "SHADOW{ENCODING_IS_NOT_ENCRYPTION}",
        "flag": "SHADOW{ENCODING_IS_NOT_ENCRYPTION}",
        "accept": [],
        "points": 125, "difficulty": "Easy-Medium",
        "solve_time": "4m",
        "q": "The ransom note hides one encoded token. Decode it to reveal the "
            "SHADOW{...} flag and submit it.",
        "hint": "The token is a binary-to-text encoding whose output often ends "
                "in '=' padding — decode it to plain text.",
        "ev": "U0hBRE9Xe0VOQ09ESU5HX0lTX05PVF9FTkNSWVBUSU9OfQ==",
        "cfg": {},
    },
    {
        "code": "C", "domain": "encode", "game_type": "shadow_text",
        "title": "Encoded Ransom",
        "answer": "SHADOW{DECODE_ME_IF_YOU_CAN}",
        "flag": "SHADOW{DECODE_ME_IF_YOU_CAN}",
        "accept": [],
        "points": 125, "difficulty": "Easy-Medium",
        "solve_time": "4m",
        "q": "The ransom note hides one encoded token. Decode it to reveal the "
            "SHADOW{...} flag and submit it.",
        "hint": "The token is a binary-to-text encoding whose output often ends "
                "in '=' padding — decode it to plain text.",
        "ev": "U0hBRE9Xe0RFQ09ERV9NRV9JRl9ZT1VfQ0FOfQ==",
        "cfg": {},
    },

    # ------------------------------------------------------------------ C06
    {
        "code": "A", "domain": "words", "game_type": "shadow_text",
        "title": "Final Connection",
        "answer": "SHADOW{CLESST}",
        "flag": "SHADOW{CLESST}",
        "accept": [],
        "points": 100, "difficulty": "Medium",
        "solve_time": "2m",
        "q": "Every word in the sentence is a clue. Take the FIRST LETTER of each "
            "word, in order, to reveal the SHADOW{...} flag and submit it.",
        "hint": "Read only the first letters — ignoring commas and spaces — "
                "and join them into one uppercase word.",
        "ev": "Case Locked, Evidence Secured, Suspect Traced",
        "cfg": {},
    },
    {
        "code": "B", "domain": "words", "game_type": "shadow_text",
        "title": "Final Connection",
        "answer": "SHADOW{DENTECD}",
        "flag": "SHADOW{DENTECD}",
        "accept": [],
        "points": 100, "difficulty": "Medium",
        "solve_time": "2m",
        "q": "Every word in the sentence is a clue. Take the FIRST LETTER of each "
            "word, in order, to reveal the SHADOW{...} flag and submit it.",
        "hint": "Read only the first letters — ignoring commas and spaces — "
                "and join them into one uppercase word.",
        "ev": "Danger Every Night, Trust Every Clue, Decide",
        "cfg": {},
    },
    {
        "code": "C", "domain": "words", "game_type": "shadow_text",
        "title": "Final Connection",
        "answer": "SHADOW{SHADOWS}",
        "flag": "SHADOW{SHADOWS}",
        "accept": [],
        "points": 100, "difficulty": "Medium",
        "solve_time": "2m",
        "q": "Every word in the sentence is a clue. Take the FIRST LETTER of each "
            "word, in order, to reveal the SHADOW{...} flag and submit it.",
        "hint": "Read only the first letters — ignoring commas and spaces — "
                "and join them into one uppercase word.",
        "ev": "Shadow Hides, Answers Dawn, Only Walk Slowly",
        "cfg": {},
    },
]


def catalogue():
    """Return the catalogue with a normalized 'category' entry per variant."""
    out = []
    for ch in CHALLENGES:
        item = dict(ch)
        cat_code, cat_title = DOMAIN_META[item["domain"]][:2]
        item["category"] = cat_title
        item["cat_code"] = cat_code
        item["difficulty"] = DOMAIN_META[item["domain"]][2]
        item.setdefault("points", 25)
        item["cfg"] = dict(item.get("cfg") or {})
        item["accept"] = list(item.get("accept") or [])
        out.append(item)
    return out


def by_code(code):
    for ch in catalogue():
        if ch["code"] == code:
            return ch
    return None