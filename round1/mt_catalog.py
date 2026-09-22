"""MYSTERY TRACE Round 1 — authoritative 48-challenge catalogue.

Twelve domains x four variants, transcribed verbatim from the Round 1
Master Specification. This is the single source of truth that `seed_mt.py`
upserts into `challenge_categories` / `challenge_variants`.

Each variant carries:
    code        variant code        (e.g. "SQL-V1")
    domain      MT domain key       (e.g. "sql")
    game_type   engine key          (e.g. "login_escape")
    title       variant title
    answer      canonical answer (server-side only)
    accept      extra accepted answer forms ("Also accept" from the spec)
    flag        MT{...} flag (server-side only)
    q / hint    mission briefing + hint
    ev          evidence: a generator config {"type": ...} OR a static
                object (cards, emails, ports, HTML ...) shipped as-is
    cfg         public game_config extra the engine needs (options,
                candidates, tools, ...) -- never answers/flags
"""

# Domain key -> (category challenge_code, display name)
DOMAIN_META = {
    "sql":    ("SQLI", "SQL Injection Basics"),
    "pass":   ("PWDA", "Password Strength Audit"),
    "bin":    ("BIND", "Binary Decoding"),
    "port":   ("NETP", "Simulated Network Port Mapping"),
    "phish":  ("PHIS", "Phishing Spotter"),
    "meta":   ("META", "Metadata Detective"),
    "cipher": ("CIPH", "Cipher Chain"),
    "hash":   ("HASH", "Hash Analysis"),
    "web":    ("WEBH", "Simulated Web Source Hunt"),
    "magic":  ("FILE", "File Magic / Signature"),
    "rot":    ("CSAR", "Caesar / ROT Decoding"),
    "osint":  ("OSNT", "Fictional OSINT Link Puzzle"),
}

SQL_TMPL = ("SELECT * FROM employees WHERE username='{u}' AND password='{p}'")


def _fill(ev, **cfg):
    ev = dict(ev) if isinstance(ev, dict) else ev
    return {"ev": ev, "cfg": cfg}


CHALLENGES = [
    # ------------------------------------------------------------------ SQL
    {
        "code": "SQL-V1", "domain": "sql", "game_type": "login_escape",
        "title": "Login Escape", "answer": "' OR '1'='1' --",
        "accept": ["' OR '1'='1'--"],
        "flag": "MT{EMPLOYEE_GATE_BROKEN}",
        "q": "The login page is vulnerable to SQL injection. Identify a suitable "
             "test input that makes the login condition evaluate as true and "
             "bypasses the simulated authentication.",
        "hint": "Modify the SQL condition to always be true; use comment syntax.",
        **_fill({"query_template": SQL_TMPL, "form": "employee_login"}),
    },
    {
        "code": "SQL-V2", "domain": "sql", "game_type": "query_puzzle",
        "title": "Query Puzzle", "answer": "admin' --",
        "accept": ["admin'--"],
        "flag": "MT{ADMIN_CONSOLE_UNLOCKED}",
        "q": "The application checks both username and password. Identify an "
             "input that terminates the username condition and comments out the "
             "remaining password condition.",
        "hint": "Close the username string, then comment the remaining condition.",
        **_fill({"query_template": SQL_TMPL, "target_user": "admin"}),
    },
    {
        "code": "SQL-V3", "domain": "sql", "game_type": "live_query_builder",
        "title": "Live Query Builder", "answer": "' OR 1=1 --",
        "accept": ["' OR 1=1--"],
        "flag": "MT{BOOLEAN_QUERY_TRUE}",
        "q": "The displayed query contains a user-controlled username field. "
             "Construct a Boolean-based SQL injection test that changes the "
             "condition to always true.",
        "hint": "Use Boolean 1=1 and comment syntax.",
        **_fill({"query_template": SQL_TMPL,
                 "fragments": ["'", "OR", "1=1", "--", "admin", "AND", "'1'='2'"]}),
    },
    {
        "code": "SQL-V4", "domain": "sql", "game_type": "debug_console",
        "title": "Debug Console", "answer": "' OR '1'='1' --",
        "accept": ["' OR '1'='1'--"],
        "flag": "MT{AUTH_QUERY_REBUILT}",
        "q": "A quote can be inserted into the username field. Use the supplied "
             "query structure to create a valid authentication-bypass test input.",
        "hint": "Terminate the string, add a true condition, then comment the rest.",
        **_fill({"query_template": SQL_TMPL, "debug": True}),
    },

    # ------------------------------------------------------------------ PASS
    {
        "code": "PASS-V1", "domain": "pass", "game_type": "risk_card_hunt",
        "title": "Risk Card Hunt", "answer": "password", "accept": [],
        "flag": "MT{COMMON_PASSWORD_FOUND}",
        "q": "Which password represents the highest security risk?",
        "hint": "Look for a common dictionary password.",
        **_fill({"cards": ["Xy7#kLm2!q", "password", "Winter!Rain42", "T9$vBn4@wE"]}),
    },
    {
        "code": "PASS-V2", "domain": "pass", "game_type": "match_pair",
        "title": "Match the Pair", "answer": "BlueSky#77", "accept": [],
        "flag": "MT{CREDENTIAL_REUSE}",
        "q": "Which password is reused across multiple accounts?",
        "hint": "Find an exact duplicate across the supplied accounts.",
        **_fill({"accounts": [
            {"user": "alice", "password": "BlueSky#77"},
            {"user": "bob", "password": "Green$Tree9"},
            {"user": "carol", "password": "BlueSky#77"},
            {"user": "dave", "password": "Orange!55x"},
        ]}),
    },
    {
        "code": "PASS-V3", "domain": "pass", "game_type": "drag_classify",
        "title": "Drag & Classify", "answer": "Admin2026", "accept": [],
        "flag": "MT{PREDICTABLE_PATTERN}",
        "q": "Which password follows a predictable username/year-style pattern and "
             "should be flagged?",
        "hint": "Look for a role/username combined with a year.",
        **_fill({"cards": ["Admin2026", "k3Y!vP9zQm", "Blue$Whale88", "Rn7@Lp2#dX"],
                 "categories": ["COMMON", "REUSED", "PREDICTABLE", "STRONGER"]}),
    },
    {
        "code": "PASS-V4", "domain": "pass", "game_type": "security_audit",
        "title": "Security Audit", "answer": "password", "accept": [],
        "flag": "MT{POLICY_FAILURE}",
        "q": "Which password fails the greatest number of the stated password-"
             "policy requirements?",
        "hint": "Compare each supplied requirement.",
        **_fill({"policy": ["min 8 characters", "an uppercase letter", "a digit", "a symbol"],
                 "candidates": ["password", "Passw0rd", "Summer2024", "Xy7#kLm2!q"]}),
    },

    # ------------------------------------------------------------------ BIN
    {
        "code": "BIN-V1", "domain": "bin", "game_type": "digital_lock",
        "title": "Digital Lock", "answer": "FLAG", "accept": [],
        "flag": "MT{BINARY_LOCK_OPEN}",
        "q": "The evidence contains groups of 8 binary digits. Convert each group "
             "to ASCII and identify the hidden investigation clue.",
        "hint": "Each group of 8 bits is one ASCII character.",
        "ev": {"type": "binary"},
    },
    {
        "code": "BIN-V2", "domain": "bin", "game_type": "combination_safe",
        "title": "Combination Safe", "answer": "case", "accept": [],
        "flag": "MT{OCTAL_SAFE_OPEN}",
        "q": "The recovered evidence is represented using octal values. Convert "
             "the values to ASCII and identify the resulting clue.",
        "hint": "Octal 141 is the letter 'a'.",
        "ev": {"type": "octal"},
    },
    {
        "code": "BIN-V3", "domain": "bin", "game_type": "binary_tiles",
        "title": "Binary Tile Puzzle", "answer": "CASE", "accept": [],
        "flag": "MT{BINARY_CASE_FOUND}",
        "q": "Separate the supplied binary sequence into 8-bit groups and decode it "
             "into readable text.",
        "hint": "Split every 8 bits, then decode.",
        "ev": {"type": "binary"}, "cfg": {"joined": True},
    },
    {
        "code": "BIN-V4", "domain": "bin", "game_type": "forensic_terminal",
        "title": "Forensic Terminal", "answer": "TRACE", "accept": [],
        "flag": "MT{DIGITAL_TRACE_FOUND}",
        "q": "Decode the supplied binary evidence and submit the meaningful "
             "investigation word revealed by the data.",
        "hint": "Use the terminal command: decode.",
        "ev": {"type": "binary"},
    },

    # ------------------------------------------------------------------ PORT
    {
        "code": "PORT-V1", "domain": "port", "game_type": "radar_scan",
        "title": "Radar Scan", "answer": "21 / FTP",
        "accept": ["21/ftp", "21", "ftp"],
        "flag": "MT{UNEXPECTED_FTP}",
        "q": "The target is identified as a web server. Which open service appears "
             "unusual for its expected role?",
        "hint": "Web servers normally expose HTTP/HTTPS.",
        **_fill({"host": "web-01.sim.example", "role": "web server",
                 "ports": [{"port": 80, "service": "HTTP"},
                           {"port": 443, "service": "HTTPS"},
                           {"port": 21, "service": "FTP"}]}),
    },
    {
        "code": "PORT-V2", "domain": "port", "game_type": "service_match",
        "title": "Service Match", "answer": "3306 / MySQL",
        "accept": ["3306/mysql", "3306", "mysql"],
        "flag": "MT{MYSQL_PORT_FOUND}",
        "q": "Identify the open port associated with the database service shown in "
             "the evidence.",
        "hint": "Match each service to its default port.",
        **_fill({"host": "db-01.sim.example",
                 "ports": [80, 3306, 22, 8080],
                 "services": ["MySQL", "HTTP", "SSH", "HTTP-ALT"]}),
    },
    {
        "code": "PORT-V3", "domain": "port", "game_type": "server_compare",
        "title": "Server Compare", "answer": "445 / SMB",
        "accept": ["445/smb", "445", "smb"],
        "flag": "MT{SERVER_B_SMB}",
        "q": "Two simulated servers are shown. Identify the port associated with the "
             "SMB service on the relevant server.",
        "hint": "Only one server exposes file sharing.",
        **_fill({"servers": {"A": [80, 443, 22], "B": [80, 445, 139]}}),
    },
    {
        "code": "PORT-V4", "domain": "port", "game_type": "service_radar",
        "title": "Service Radar", "answer": "3389 / RDP",
        "accept": ["3389/rdp", "3389", "rdp"],
        "flag": "MT{REMOTE_DESKTOP_FOUND}",
        "q": "The simulated host contains several services. Identify the port "
             "associated with the remote desktop service.",
        "hint": "Windows remote desktop default port.",
        **_fill({"host": "ws-07.sim.example",
                 "ports": [{"port": 80, "service": "HTTP"},
                           {"port": 3389, "service": "RDP"},
                           {"port": 5432, "service": "PostgreSQL"},
                           {"port": 8080, "service": "HTTP-ALT"}]}),
    },

    # ------------------------------------------------------------------ PHISH
    {
        "code": "PHISH-V1", "domain": "phish", "game_type": "inbox_investigation",
        "title": "Inbox Investigation",
        "answer": "Urgency / fear-based social engineering",
        "accept": ["urgency"],
        "flag": "MT{PHISH_URGENCY_DETECTED}",
        "q": "An email contains several suspicious characteristics. Identify the "
             "strongest social-engineering indicator.",
        "hint": "What emotion is the sender trying to trigger?",
        **_fill({"email": {
            "from": "it-support@northwind-corp.example",
            "subject": "URGENT: Account will be closed in 2 hours",
            "body": "Your mailbox will be permanently deleted unless you verify immediately."}},
            options=["Urgency / fear-based social engineering",
                     "Correct spelling and grammar",
                     "Sent to a single recipient",
                     "Includes a company signature"]),
    },
    {
        "code": "PHISH-V2", "domain": "phish", "game_type": "header_detective",
        "title": "Header Detective", "answer": "Suspicious/mismatched Reply-To address",
        "accept": ["reply-to mismatch"],
        "flag": "MT{REPLY_TO_MISMATCH}",
        "q": "Which header characteristic indicates that the email may not be what "
             "it claims to be?",
        "hint": "Compare From and Reply-To.",
        **_fill({"headers": {
            "From": "hr@northwind-corp.example", "To": "staff@northwind-corp.example",
            "Subject": "Payroll update", "Reply-To": "payroll@n0rthwind-support.example",
            "Date": "Mon, 21 Sep 2026 09:14:00 +0530"}},
            options=["Suspicious/mismatched Reply-To address",
                     "Long subject line", "Unusual date format",
                     "Recipient address present"]),
    },
    {
        "code": "PHISH-V3", "domain": "phish", "game_type": "link_inspector",
        "title": "Link Inspector",
        "answer": "Displayed URL and actual destination mismatch",
        "accept": ["url mismatch"],
        "flag": "MT{URL_DESTINATION_TRAP}",
        "q": "What suspicious characteristic is revealed when the displayed link is "
             "compared with its actual destination?",
        "hint": "Hover the link and read both URLs.",
        **_fill({"links": [{
            "displayed": "https://portal.northwind-corp.example/login",
            "actual": "http://northwind-login.verify-now.example/collect"}]},
            options=["Displayed URL and actual destination mismatch",
                     "Link uses HTTPS", "Link is too short", "Link has no path"]),
    },
    {
        "code": "PHISH-V4", "domain": "phish", "game_type": "intent_detective",
        "title": "Intent Detective",
        "answer": "Credential phishing / credential harvesting",
        "accept": ["credential phishing", "credential harvesting"],
        "flag": "MT{CREDENTIAL_HARVEST}",
        "q": "What type of phishing activity is the email attempting to perform?",
        "hint": "What does the email ask you to enter?",
        **_fill({"cards": [
            "Please re-enter your username and password to keep access",
            "Meeting notes attached", "Your invoice is due"]},
            options=["Credential phishing / credential harvesting",
                     "Malware attachment delivery", "Invoice fraud",
                     "Harmless newsletter"]),
    },

    # ------------------------------------------------------------------ META
    {
        "code": "META-V1", "domain": "meta", "game_type": "document_scanner",
        "title": "Document Scanner", "answer": "A.Raman", "accept": ["a raman"],
        "flag": "MT{AUTHOR_AR_MAN}",
        "q": "A document contains embedded metadata. Identify the author recorded in "
             "the document metadata.",
        "hint": "Author is not the same as Last Modified By.",
        **_fill({"fields": {
            "Author": "A.Raman", "Creator": "WordProc 12",
            "LastModifiedBy": "S.Kumar", "Created": "2026-08-21 17:30",
            "Modified": "2026-08-21 18:42"}}),
    },
    {
        "code": "META-V2", "domain": "meta", "game_type": "timeline_scrubber",
        "title": "Timeline Scrubber", "answer": "2026-08-21 18:42",
        "accept": ["18:42"],
        "flag": "MT{TIMELINE_MODIFIED}",
        "q": "The evidence contains several timestamps. Identify the timestamp "
             "associated with the relevant modification event.",
        "hint": "Find the event labelled content modified.",
        **_fill({"events": [["18:10", "created"], ["18:20", "opened"],
                            ["18:30", "printed"], ["18:42", "content modified"],
                            ["18:55", "copy saved"], ["19:05", "emailed"]],
                 "date": "2026-08-21"}),
    },
    {
        "code": "META-V3", "domain": "meta", "game_type": "camera_forensics",
        "title": "Camera Forensics", "answer": "Canon EOS", "accept": ["canon eos 80d"],
        "flag": "MT{CANON_EOS_FOUND}",
        "q": "An image file contains camera metadata. Identify the camera information "
             "recorded in the evidence.",
        "hint": "Look at Make and Model.",
        **_fill({"exif": {"Make": "Canon", "Model": "Canon EOS 80D",
                          "Exposure": "1/125", "ISO": 400}}),
    },
    {
        "code": "META-V4", "domain": "meta", "game_type": "location_pin_hunt",
        "title": "Location Pin Hunt", "answer": "Chennai", "accept": [],
        "flag": "MT{GPS_CHENNAI}",
        "q": "The image/document metadata contains location information. Identify the "
             "location recorded in the evidence.",
        "hint": "Match the coordinates to a pin.",
        **_fill({"gps": {"lat": 13.0827, "lon": 80.2707},
                 "pins": ["Chennai", "Mumbai", "Delhi", "Kolkata"]}),
    },

    # ------------------------------------------------------------------ CIPHER
    {
        "code": "CIPHER-V1", "domain": "cipher", "game_type": "decode_machine",
        "title": "Decode Machine", "answer": "CASE CLOSED", "accept": [],
        "flag": "MT{CIPHER_CHAIN_ONE}",
        "q": "Decode the evidence through the supplied steps and recover the "
             "plaintext.",
        "hint": "Undo the steps in reverse order.",
        "ev": {"type": "chain", "steps": ["base64", "rot13"]},
        "cfg": {"tools": ["rot13", "base64", "hex", "reverse"]},
    },
    {
        "code": "CIPHER-V2", "domain": "cipher", "game_type": "layer_breaker",
        "title": "Layer Breaker", "answer": "TRACE FOUND", "accept": [],
        "flag": "MT{CIPHER_CHAIN_TWO}",
        "q": "Remove the encoding layers one by one and recover the plaintext.",
        "hint": "The outer layer is hexadecimal.",
        "ev": {"type": "chain", "steps": ["reverse", "base64", "hex"]},
        "cfg": {"tools": ["hex", "base64", "reverse", "rot13"]},
    },
    {
        "code": "CIPHER-V3", "domain": "cipher", "game_type": "hex_lab",
        "title": "Hex Lab", "answer": "CASE", "accept": [],
        "flag": "MT{CIPHER_CHAIN_THREE}",
        "q": "Decode the hexadecimal bytes and recover the plaintext.",
        "hint": "Each byte is one ASCII character.",
        "ev": {"type": "hex"},
    },
    {
        "code": "CIPHER-V4", "domain": "cipher", "game_type": "pipeline_builder",
        "title": "Pipeline Builder", "answer": "TRACE COMPLETE", "accept": [],
        "flag": "MT{CIPHER_CHAIN_FOUR}",
        "q": "Arrange the decoding operations in the correct order and recover the "
             "plaintext.",
        "hint": "Hex, then Base64, then a Caesar shift of 4.",
        "ev": {"type": "chain", "steps": ["caesar4", "base64", "hex"]},
        "cfg": {"tools": ["hex", "base64", "caesar-4", "reverse"]},
    },

    # ------------------------------------------------------------------ HASH
    {
        "code": "HASH-V1", "domain": "hash", "game_type": "hash_microscope",
        "title": "Hash Microscope", "answer": "MD5", "accept": [],
        "flag": "MT{HASH_ALGORITHM_MD5}",
        "q": "Identify the hashing algorithm used to generate the supplied value.",
        "hint": "Count the hex characters: 32 / 40 / 64.",
        "ev": {"type": "hash", "algo": "md5", "plain": "trace2026"},
        "cfg": {"options": ["MD5", "SHA-1", "SHA-256", "bcrypt"]},
    },
    {
        "code": "HASH-V2", "domain": "hash", "game_type": "hash_match_cards",
        "title": "Hash Match Cards", "answer": "secret", "accept": [],
        "flag": "MT{HASH_MATCH_SECRET}",
        "q": "Identify the candidate password that matches the supplied hash.",
        "hint": "Match the hash against the candidate cards.",
        "ev": {"type": "hash", "algo": "md5"},
        "cfg": {"candidates": ["letmein", "secret", "qwerty", "welcome1"],
                "algo_label": "MD5"},
    },
    {
        "code": "HASH-V3", "domain": "hash", "game_type": "evidence_terminal",
        "title": "Evidence Terminal", "answer": "admin123", "accept": [],
        "flag": "MT{SHA1_MATCH_FOUND}",
        "q": "Identify the candidate password that produces the supplied SHA-1 hash "
             "in the simulated evidence set.",
        "hint": "Use the terminal: hash <word> and compare.",
        "ev": {"type": "hash", "algo": "sha1"},
        "cfg": {"candidates": ["123456", "qwerty", "admin123", "letmein"],
                "algo_label": "SHA-1"},
    },
    {
        "code": "HASH-V4", "domain": "hash", "game_type": "verification_grid",
        "title": "Verification Grid", "answer": "password", "accept": [],
        "flag": "MT{SHA256_MATCH_FOUND}",
        "q": "Identify the candidate password that matches the supplied SHA-256 hash.",
        "hint": "Only one row can match.",
        "ev": {"type": "hash", "algo": "sha256"},
        "cfg": {"candidates": ["letmein", "password", "dragon", "sunshine"],
                "algo_label": "SHA-256"},
    },

    # ------------------------------------------------------------------ WEB
    {
        "code": "WEB-V1", "domain": "web", "game_type": "source_treasure_hunt",
        "title": "Source Treasure Hunt", "answer": "/archive", "accept": ["archive"],
        "flag": "MT{HIDDEN_ARCHIVE}",
        "q": "The simulated website contains a hidden archive location. Identify the "
             "path where the archive is located.",
        "hint": "Check comments in the page source.",
        **_fill({"pages": {
            "/": "<h1>Northwind</h1><!-- old files moved to /archive -->",
            "/about": "<p>About us</p>",
            "/contact": "<p>Contact</p>"}}),
    },
    {
        "code": "WEB-V2", "domain": "web", "game_type": "html_detective",
        "title": "HTML Detective", "answer": "blue-door", "accept": [],
        "flag": "MT{BLUE_DOOR_FOUND}",
        "q": "Inspect the supplied HTML evidence. Identify the hidden value "
             "associated with the relevant HTML element.",
        "hint": "Look for type=hidden.",
        **_fill({"html": "<form><input type=\"text\" name=\"q\"><input "
                         "type=\"hidden\" name=\"token\" value=\"blue-door\"></form>"}),
    },
    {
        "code": "WEB-V3", "domain": "web", "game_type": "robots_puzzle",
        "title": "Robots Puzzle", "answer": "/backup/", "accept": ["/backup"],
        "flag": "MT{RESTRICTED_BACKUP}",
        "q": "The simulated site contains a robots configuration. Identify the "
             "restricted path revealed by the evidence.",
        "hint": "Which path is Disallowed?",
        **_fill({"robots": "User-agent: *\nAllow: /public/\nDisallow: /backup/"}),
    },
    {
        "code": "WEB-V4", "domain": "web", "game_type": "source_search",
        "title": "Source Search", "answer": "trace_admin", "accept": [],
        "flag": "MT{TRACE_ADMIN_FOUND}",
        "q": "The simulated page contains hidden metadata. Identify the username/"
             "value associated with the relevant metadata.",
        "hint": "Search the source for a meta tag.",
        **_fill({"source": "<html><head><title>Portal</title><meta "
                           "name=\"author\" content=\"trace_admin\"></head>"
                           "<body>Welcome</body></html>"}),
    },

    # ------------------------------------------------------------------ MAGIC
    {
        "code": "MAGIC-V1", "domain": "magic", "game_type": "hex_microscope",
        "title": "Hex Microscope", "answer": "PDF", "accept": [],
        "flag": "MT{MAGIC_BYTES_PDF}",
        "q": "Identify the file format represented by the supplied magic bytes.",
        "hint": "Bytes 25 50 44 46 spell ASCII text.",
        **_fill({"hex": "25 50 44 46 2D 31 2E 34"},
            options=["PDF", "PNG", "ZIP", "GIF"]),
    },
    {
        "code": "MAGIC-V2", "domain": "magic", "game_type": "signature_match",
        "title": "Signature Match", "answer": "PNG", "accept": [],
        "flag": "MT{MAGIC_BYTES_PNG}",
        "q": "Inspect the supplied hexadecimal file signature. Identify the file "
             "format.",
        "hint": "Second to fourth bytes spell a word.",
        **_fill({"hex": "89 50 4E 47 0D 0A 1A 0A"},
            options=["PNG", "PDF", "ZIP", "JPEG"]),
    },
    {
        "code": "MAGIC-V3", "domain": "magic", "game_type": "file_detective",
        "title": "File Detective", "answer": "ZIP", "accept": [],
        "flag": "MT{MAGIC_BYTES_ZIP}",
        "q": "The evidence contains a file signature. Identify the file type.",
        "hint": "First two bytes are the initials of its creator.",
        **_fill({"hex": "50 4B 03 04 14 00"},
            options=["ZIP", "PDF", "PNG", "GIF"]),
    },
    {
        "code": "MAGIC-V4", "domain": "magic", "game_type": "signature_challenge",
        "title": "Signature Challenge", "answer": "JPEG / JPG",
        "accept": ["jpeg", "jpg", "jpeg/jpg"],
        "flag": "MT{MAGIC_BYTES_JPEG}",
        "q": "A hexadecimal signature is displayed. Identify the file format.",
        "hint": "Starts with FF D8 FF.",
        **_fill({"hex": "FF D8 FF E0 00 10 4A 46"},
            options=["JPEG / JPG", "PNG", "ZIP", "PDF"]),
    },

    # ------------------------------------------------------------------ ROT
    {
        "code": "ROT-V1", "domain": "rot", "game_type": "alphabet_wheel",
        "title": "Alphabet Wheel", "answer": "THE CASE IS CLOSED", "accept": [],
        "flag": "MT{CASE_IS_CLOSED}",
        "q": "Decode the supplied message and submit the resulting sentence.",
        "hint": "Rotate the wheel until it reads English.",
        "ev": {"type": "caesar", "shift": 7},
    },
    {
        "code": "ROT-V2", "domain": "rot", "game_type": "caesar_slider",
        "title": "Caesar Slider", "answer": "CASE", "accept": [],
        "flag": "MT{CAESAR_CASE}",
        "q": "Decode the supplied Caesar-shifted evidence. What word is revealed?",
        "hint": "Try every shift from 0 to 25.",
        "ev": {"type": "caesar", "shift": 5},
    },
    {
        "code": "ROT-V3", "domain": "rot", "game_type": "shift_lock",
        "title": "Shift Lock", "answer": "TRACE", "accept": [],
        "flag": "MT{CAESAR_TRACE}",
        "q": "Decode the message and identify the investigation word.",
        "hint": "The shift is between 1 and 25.",
        "ev": {"type": "caesar", "shift": 11},
    },
    {
        "code": "ROT-V4", "domain": "rot", "game_type": "shift_guess",
        "title": "Shift Guess Game", "answer": "CASE — shift 3",
        "accept": ["CASE - shift 3", "CASE shift 3", "CASE", "3", "CASE 3"],
        "flag": "MT{SHIFT_THREE_CASE}",
        "q": "Identify the decoded word and the shift value used.",
        "hint": "Answer format: WORD - shift N",
        "ev": {"type": "caesar", "shift": 3},
    },

    # ------------------------------------------------------------------ OSINT
    {
        "code": "OSINT-V1", "domain": "osint", "game_type": "evidence_board",
        "title": "Evidence Board", "answer": "dev_trace", "accept": [],
        "flag": "MT{DEV_TRACE_LINKED}",
        "q": "Several fictional online profiles are supplied. Identify the username "
             "that connects the supplied pieces of evidence.",
        "hint": "Which handle appears on every card?",
        **_fill({"cards": [{"site": "CodeNest.example", "handle": "dev_trace"},
                           {"site": "PhotoWall.example", "handle": "dev_trace"},
                           {"site": "ChatHub.example", "handle": "dev_trace"},
                           {"site": "Blogly.example", "handle": "trace_dev99"}]}),
    },
    {
        "code": "OSINT-V2", "domain": "osint", "game_type": "identity_matcher",
        "title": "Identity Matcher", "answer": "Arun — username: arun_builds",
        "accept": ["Arun - username: arun_builds", "arun arun_builds", "arun_builds"],
        "flag": "MT{ARUN_BUILDS_LINKED}",
        "q": "Identify the person and corresponding username connected to the "
             "supplied evidence.",
        "hint": "Match person to project to username.",
        **_fill({"people": ["Arun", "Meera", "Kiran"],
                 "usernames": ["arun_builds", "meera_codes", "kiran_dev"],
                 "projects": ["TraceBoard", "NightOwl", "CaseLog"],
                 "clues": ["TraceBoard was pushed by arun_builds",
                           "Meera works on NightOwl"]}),
    },
    {
        "code": "OSINT-V3", "domain": "osint", "game_type": "domain_hunter",
        "title": "Domain Hunter", "answer": "mysterylab.example", "accept": [],
        "flag": "MT{MYSTERYLAB_DOMAIN}",
        "q": "Identify the domain associated with the organization in the evidence.",
        "hint": "Only .example domains exist here.",
        **_fill({"org": "MysteryLab",
                 "references": ["mail from ops@mysterylab.example",
                                "MysteryLab careers page",
                                "unrelated: mysterylabs-fake.example"]}),
    },
    {
        "code": "OSINT-V4", "domain": "osint", "game_type": "connection_web",
        "title": "Connection Web", "answer": "case_admin", "accept": [],
        "flag": "MT{CASE_ADMIN_LINKED}",
        "q": "Correlate the three pieces of evidence and identify the "
             "account/username connected to the case.",
        "hint": "Find the node connected to all three.",
        **_fill({"nodes": ["Person: R. Nair", "Username: case_admin",
                           "Project: CaseLog", "Domain: caselog.example"],
                 "edges": [["Person: R. Nair", "Username: case_admin"],
                           ["Username: case_admin", "Project: CaseLog"],
                           ["Project: CaseLog", "Domain: caselog.example"]]}),
    },
]


def catalogue():
    """Return the catalogue with a normalized 'category' entry per variant."""
    out = []
    for ch in CHALLENGES:
        item = dict(ch)
        cat_code, cat_title = DOMAIN_META[item["domain"]]
        item["category"] = cat_title
        item["cat_code"] = cat_code
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