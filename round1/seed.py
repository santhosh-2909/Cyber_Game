"""Seed script: 12 challenge categories x 4 variants, each a Mini-CTF lab.

Every variant carries:
  - story / objective (narrative + task)
  - lab_type          (drives the interactive lab UI)
  - lab_data          (JSON, the renderable lab content - never contains the
                       lab answer or the flag)
  - expected_answer   (the LAB success answer the participant types in the lab)
  - flag              (unique FLAG{...}, revealed ONLY after the lab is solved)
  - hints / explanation / difficulty / eta

The lab answer (expected_answer) is deliberately distinct from the flag.
Points are awarded ONLY when the participant submits the correct flag.

Usage:
    python -m round1.seed            # seed into DB (idempotent-ish)
    python -m round1.seed --reset    # wipe DB then seed
"""
import json
import sys

from werkzeug.security import generate_password_hash

import round1.db as db

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"


# ---------------------------------------------------------------------------
# 12 CHALLENGE CATEGORIES
# ---------------------------------------------------------------------------
CATEGORIES = [
    {"code": "SQLI",  "title": "SQL Injection Basics", "domain": "Web Application Security", "description": "Obtain unauthorized access through a deliberately vulnerable simulated login.", "difficulty": "Easy", "points": 100, "lab_type": "login_bypass"},
    {"code": "PWDA",  "title": "Password Strength Audit", "domain": "Password Security", "description": "Audit a fictional password database and find the target weakness.", "difficulty": "Easy", "points": 100, "lab_type": "password_audit"},
    {"code": "BIND",  "title": "Binary Decoding", "domain": "Data Encoding", "description": "Decode a data value hidden in binary, octal, or hex. ", "difficulty": "Easy", "points": 100, "lab_type": "decoder"},
    {"code": "NETP",  "title": "Network Port Mapping", "domain": "Networking", "description": "Analyze a simulated scan and map ports to services / anomalies.", "difficulty": "Medium", "points": 100, "lab_type": "port_map"},
    {"code": "PHIS",  "title": "Phishing Spotter", "domain": "Social Engineering", "description": "Identify the manipulation red-flags in a simulated phishing message.", "difficulty": "Medium", "points": 100, "lab_type": "phishing"},
    {"code": "META",  "title": "Metadata Detective", "domain": "Digital Artifacts", "description": "Inspect a fictional artifact's metadata for the requested clue.", "difficulty": "Medium", "points": 100, "lab_type": "metadata"},
    {"code": "CIPH",  "title": "Cipher Chain", "domain": "Cryptography", "description": "Decode a value through a specific multi-layer encoding chain.", "difficulty": "Medium", "points": 100, "lab_type": "cipher_chain"},
    {"code": "HASH",  "title": "Hash Analysis", "domain": "Hashing", "description": "Analyze fictional hash data (type / weak record / match).", "difficulty": "Medium", "points": 100, "lab_type": "hash_analysis"},
    {"code": "WEBH",  "title": "Web Source Hunt", "domain": "Web Security Basics", "description": "Inspect a simulated site's source for a hidden clue.", "difficulty": "Medium-Hard", "points": 100, "lab_type": "source_view"},
    {"code": "FILE",  "title": "File Magic", "domain": "File Forensics", "description": "Identify a real file type from its magic bytes / signature.", "difficulty": "Medium-Hard", "points": 100, "lab_type": "file_magic"},
    {"code": "CSAR",  "title": "Caesar / ROT Decode", "domain": "Cryptography", "description": "Decode a message shifted with Caesar / ROT.", "difficulty": "Medium-Hard", "points": 100, "lab_type": "caesar"},
    {"code": "OSNT",  "title": "OSINT Link Puzzle", "domain": "OSINT / Logic", "description": "Correlate fictional public-style clues to determine the answer.", "difficulty": "Medium-Hard", "points": 100, "lab_type": "osint"},
]


# ---------------------------------------------------------------------------
# VARIANTS. Each category has exactly 4.
# ---------------------------------------------------------------------------
VARIANTS = {
    "SQLI": [
        {
            "v": "V1",
            "difficulty": "Easy",
            "eta": "3-5 min",
            "story": "You have been given access to a simulated employee portal. The login form builds its SQL query from your input directly - a classic injection point.",
            "objective": "The login page is vulnerable to SQL injection. Identify a suitable test input that makes the login condition evaluate as true and bypasses the simulated authentication.",
            "lab_type": "login_bypass",
            "lab_data": {
                "app": "Simulated Employee Login",
                "fields": [
                    {
                        "name": "username",
                        "label": "Username"
                    },
                    {
                        "name": "password",
                        "label": "Password"
                    }
                ],
                "submit_label": "LOGIN",
                "on_fail": "Invalid credentials. Access denied.",
                "on_success": "ACCESS GRANTED",
                "protected": "Protected Area - Incident ID: INC-1001",
                "query_hint": "query = SELECT * FROM users WHERE username = '<in>' AND password = '<in>'"
            },
            "expected_answer": "' OR '1'='1' --",
            "flag": "FLAG{CPR1-SQL1-AP04}",
            "hints": [
                "Try modifying the SQL condition so that it always evaluates to TRUE. Think about SQL comment syntax."
            ],
            "explanation": "Entering ' OR '1'='1 makes the WHERE clause always true, bypassing the password check and letting you in.",
            "title": "SQL Injection Basics"
        },
        {
            "v": "V2",
            "difficulty": "Easy",
            "eta": "3-5 min",
            "story": "The HR self-service portal has a login bug. There is an administrator account you need to reach.",
            "objective": "The application checks both username and password. Identify an input that terminates the username condition and comments out the remaining password condition.",
            "lab_type": "login_bypass",
            "lab_data": {
                "app": "Simulated Admin Login",
                "fields": [
                    {
                        "name": "username",
                        "label": "Username"
                    },
                    {
                        "name": "password",
                        "label": "Password"
                    }
                ],
                "submit_label": "SIGN IN",
                "on_fail": "Invalid credentials. Access denied.",
                "on_success": "ADMIN ACCESS GRANTED",
                "protected": "Administrator Panel - Record: EMP-0009",
                "query_hint": "query = SELECT * FROM users WHERE username = '<in>' AND password = '<in>'"
            },
            "expected_answer": "admin' --",
            "flag": "FLAG{CPR1-SQL2-HR54}",
            "hints": [
                "Close the username string first, then use an SQL comment to ignore the password condition."
            ],
            "explanation": "admin' -- sets username to admin and comments out the password check, logging you in as admin.",
            "title": "SQL Injection Basics"
        },
        {
            "v": "V3",
            "difficulty": "Medium",
            "eta": "4-6 min",
            "story": "The incident ticketing tool has a vulnerable password reset endpoint exposed in a local sandbox.",
            "objective": "The displayed query contains a user-controlled username field. Construct a Boolean-based SQL injection test that changes the condition to always true.",
            "lab_type": "login_bypass",
            "lab_data": {
                "app": "Vulnerable Login Query Viewer",
                "fields": [
                    {
                        "name": "ticket_id",
                        "label": "Ticket ID"
                    },
                    {
                        "name": "operator_code",
                        "label": "Operator Code"
                    }
                ],
                "submit_label": "AUTHENTICATE",
                "on_fail": "Invalid ticket. Access denied.",
                "on_success": "TICKET ACCESS GRANTED",
                "protected": "Console - Queue: SEC-LEVEL-4",
                "query_hint": "query = SELECT * FROM tickets WHERE ticket_id = '<in>' AND operator = '<in>'"
            },
            "expected_answer": "' OR 1=1 --",
            "flag": "FLAG{CPR1-SQL3-TIC8}",
            "hints": [
                "Use a Boolean comparison such as 1=1 to create a condition that is always true."
            ],
            "explanation": "' OR 1=1 makes the condition true and grants access to the console.",
            "title": "SQL Injection Basics"
        },
        {
            "v": "V4",
            "difficulty": "Medium-Hard",
            "eta": "5-7 min",
            "story": "A customer lookup tool uses single quotes on both fields. You found the source in the sandbox.",
            "objective": "A quote can be inserted into the username field. Use the supplied query structure to create a valid authentication-bypass test input.",
            "lab_type": "login_bypass",
            "lab_data": {
                "app": "Authentication Testing Console",
                "fields": [
                    {
                        "name": "email",
                        "label": "Email"
                    },
                    {
                        "name": "pin",
                        "label": "PIN"
                    }
                ],
                "submit_label": "LOOKUP",
                "on_fail": "No matching customer. Access denied.",
                "on_success": "CUSTOMER ACCESS GRANTED",
                "protected": "Customer Vault - Role: ROOT",
                "query_hint": "query = SELECT * FROM customers WHERE email = '<in>' AND pin = '<in>'"
            },
            "expected_answer": "' OR '1'='1' --",
            "flag": "FLAG{CPR1-SQL4-VLT3}",
            "hints": [
                "Terminate the existing string, add a true condition, and comment out the remaining query."
            ],
            "explanation": "a' OR 'a'='a closes the first quote, adds an always-true OR, and closes cleanly - the query returns the first row.",
            "title": "SQL Injection Basics"
        }
    ],
    "PWDA": [
        {
            "v": "V1",
            "difficulty": "Easy",
            "eta": "3-4 min",
            "story": "You're auditing a fictional company's profile database for weak credentials.",
            "objective": "Which password represents the highest security risk? Identify the password and explain the weakness.",
            "lab_type": "password_audit",
            "lab_data": {
                "prompt": "Which user has the weakest (most guessable) password?",
                "answer_hint": "Submit the user id (e.g. user03)",
                "records": [
                    {
                        "id": "user01",
                        "password": "Tr0ub4dor&3"
                    },
                    {
                        "id": "user02",
                        "password": "123456"
                    },
                    {
                        "id": "user03",
                        "password": "Giraffe#2024!"
                    },
                    {
                        "id": "user04",
                        "password": "M4rketing@Blue"
                    },
                    {
                        "id": "user05",
                        "password": "9Gz!kL2#mQ8"
                    }
                ],
                "answer_field": "id",
                "columns": [
                    {
                        "key": "id",
                        "label": "User"
                    },
                    {
                        "key": "password",
                        "label": "Password"
                    }
                ]
            },
            "expected_answer": "password \u2014 common and easily guessable.",
            "flag": "FLAG{CPR1-PW1-WEA0}",
            "hints": [
                "Think about passwords that are commonly found in password dictionaries."
            ],
            "explanation": "123456 (user02) is a top-common weak password - the most guessable of the set.",
            "title": "Password Strength Audit"
        },
        {
            "v": "V2",
            "difficulty": "Medium",
            "eta": "4-6 min",
            "story": "Cross-account password reuse is a serious risk. You're reviewing a fictional account list.",
            "objective": "Which password is reused across multiple accounts?",
            "lab_type": "password_audit",
            "lab_data": {
                "prompt": "Submit the user id of the account sharing a reused password.",
                "answer_hint": "Submit a user id (e.g. user01). The reused password belongs to two users.",
                "records": [
                    {
                        "id": "user01",
                        "password": "W1nter@2024"
                    },
                    {
                        "id": "user02",
                        "password": "Green!Forest4"
                    },
                    {
                        "id": "user03",
                        "password": "W1nter@2024"
                    },
                    {
                        "id": "user04",
                        "password": "P@ssw0rd!X"
                    },
                    {
                        "id": "user05",
                        "password": "MoNdAy2024!"
                    }
                ],
                "answer_field": "id",
                "columns": [
                    {
                        "key": "id",
                        "label": "User"
                    },
                    {
                        "key": "password",
                        "label": "Password"
                    }
                ]
            },
            "expected_answer": "BlueSky#77",
            "flag": "FLAG{CPR1-PW2-RU00}",
            "hints": [
                "Compare every password and look for an exact duplicate."
            ],
            "explanation": "W1nter@2024 is used by both user01 and user03, showing reuse (submit user01 or user03).",
            "title": "Password Strength Audit"
        },
        {
            "v": "V3",
            "difficulty": "Medium",
            "eta": "4-6 min",
            "story": "A predictable 'pattern' password is a cracked one. Review this fictional list.",
            "objective": "Which password follows a predictable username/year-style pattern and should be flagged?",
            "lab_type": "password_audit",
            "lab_data": {
                "prompt": "Submit the user id whose password is a predictable pattern (keyboard row + common suffix).",
                "answer_hint": "Submit a user id.",
                "records": [
                    {
                        "id": "user01",
                        "password": "Qwerty123!"
                    },
                    {
                        "id": "user02",
                        "password": "9Gz!kL2#mQ8"
                    },
                    {
                        "id": "user03",
                        "password": "tjgJ7#xR3wE"
                    },
                    {
                        "id": "user04",
                        "password": "MoNdAy2024!"
                    },
                    {
                        "id": "user05",
                        "password": "x7$!pWq2@Lz"
                    }
                ],
                "answer_field": "id",
                "columns": [
                    {
                        "key": "id",
                        "label": "User"
                    },
                    {
                        "key": "password",
                        "label": "Password"
                    }
                ]
            },
            "expected_answer": "Admin2026",
            "flag": "FLAG{CPR1-PW3-PAT0}",
            "hints": [
                "Look for a recognizable role or username combined with a predictable year."
            ],
            "explanation": "Qwerty123! starts with the predictable 'qwerty' row plus a common suffix - a weak pattern.",
            "title": "Password Strength Audit"
        },
        {
            "v": "V4",
            "difficulty": "Medium-Hard",
            "eta": "5-7 min",
            "story": "The org policy requires 12+ chars, an uppercase, a number, and a symbol. Audit the records.",
            "objective": "Which password fails the greatest number of the stated password-policy requirements?",
            "lab_type": "password_audit",
            "lab_data": {
                "prompt": "Submit the user id whose password violates the most policy rules (length<12, no uppercase, no number, no symbol).",
                "answer_hint": "Submit a user id.",
                "records": [
                    {
                        "id": "user01",
                        "password": "sunflower"
                    },
                    {
                        "id": "user02",
                        "password": "MyDog#2024"
                    },
                    {
                        "id": "user03",
                        "password": "aS9!kMm2#"
                    },
                    {
                        "id": "user04",
                        "password": "RiverFlow"
                    },
                    {
                        "id": "user05",
                        "password": "C0mpl3x!Pass980"
                    }
                ],
                "answer_field": "id",
                "columns": [
                    {
                        "key": "id",
                        "label": "User"
                    },
                    {
                        "key": "password",
                        "label": "Password"
                    }
                ]
            },
            "expected_answer": "password",
            "flag": "FLAG{CPR1-PW4-POL0}",
            "hints": [
                "Check each password against every requirement."
            ],
            "explanation": "user01 (sunflower) is lowercase only, short, with no number or symbol - it violates all four rules.",
            "title": "Password Strength Audit"
        }
    ],
    "BIND": [
        {
            "v": "V1",
            "difficulty": "Easy",
            "eta": "3-4 min",
            "story": "You intercepted a binary-encoded value in a log. Decode it to a word.",
            "objective": "The evidence contains groups of 8 binary digits. Convert each group to ASCII and identify the hidden investigation clue.",
            "lab_type": "decoder",
            "lab_data": {
                "encoded": "01000010 01101001 01110100",
                "encoding": "binary (8-bit) -> ASCII",
                "notes": "Split the binary into 8-bit groups and convert each to its character."
            },
            "expected_answer": "FLAG",
            "flag": "FLAG{CPR1-BN1-BIT01}",
            "hints": [
                "Decode each 8-bit group as an ASCII character."
            ],
            "explanation": "01000010->B, 01101001->i, 01110100->t = 'Bit'.",
            "title": "Binary Decoding"
        },
        {
            "v": "V2",
            "difficulty": "Easy",
            "eta": "3-4 min",
            "story": "A config dump holds a value encoded in binary. Decode it.",
            "objective": "The recovered evidence is represented using octal values. Convert the values to ASCII and identify the resulting clue.",
            "lab_type": "decoder",
            "lab_data": {
                "encoded": "01110011 01100001 01100110 01100101",
                "encoding": "binary (8-bit) -> ASCII",
                "notes": "Convert each 8-bit group to its ASCII character."
            },
            "expected_answer": "case",
            "flag": "FLAG{CPR1-BN2-SAF2}",
            "hints": [
                "Treat each group as an octal ASCII value."
            ],
            "explanation": "01110011->s, 01100001->a, 01100110->f, 01100101->e = 'safe'.",
            "title": "Binary Decoding"
        },
        {
            "v": "V3",
            "difficulty": "Medium",
            "eta": "4-6 min",
            "story": "An attacker left memory values in octal. Decode them.",
            "objective": "Separate the supplied binary sequence into 8-bit groups and decode it into readable text.",
            "lab_type": "decoder",
            "lab_data": {
                "encoded": "150 141 162 144",
                "encoding": "octal -> ASCII",
                "notes": "octal 150 = decimal 104 = character 'h'."
            },
            "expected_answer": "CASE",
            "flag": "FLAG{CPR1-BN3-HRD3}",
            "hints": [
                "Each 8-bit group represents one ASCII character."
            ],
            "explanation": "150->h, 141->a, 162->r, 144->d = 'hard'.",
            "title": "Binary Decoding"
        },
        {
            "v": "V4",
            "difficulty": "Medium",
            "eta": "4-6 min",
            "story": "A file left a continuous binary string. Recover the word.",
            "objective": "Decode the supplied binary evidence and submit the meaningful investigation word revealed by the data.",
            "lab_type": "decoder",
            "lab_data": {
                "encoded": "01101100011011110111001101110101",
                "encoding": "continuous binary -> ASCII",
                "notes": "This string has no spaces - split it yourself into 8-bit groups from the left."
            },
            "expected_answer": "TRACE",
            "flag": "FLAG{CPR1-BN4-L0S4}",
            "hints": [
                "Convert each 8-bit binary group into its ASCII equivalent."
            ],
            "explanation": "01101100->l, 01101111->o, 01110011->s, 01110101->u = 'loss'.",
            "title": "Binary Decoding"
        }
    ],
    "NETP": [
        {
            "v": "V1",
            "difficulty": "Medium",
            "eta": "3-5 min",
            "story": "A scan of a corporate web host shows several open ports.",
            "objective": "The target is identified as a web server. Which open service appears unusual for its expected role?",
            "lab_type": "port_map",
            "lab_data": {
                "prompt": "Which PORT is unusual for a web server?",
                "answer_hint": "Submit the port number.",
                "columns": [
                    {
                        "key": "port",
                        "label": "PORT"
                    },
                    {
                        "key": "service",
                        "label": "SERVICE"
                    },
                    {
                        "key": "state",
                        "label": "STATE"
                    }
                ],
                "records": [
                    {
                        "port": "22",
                        "service": "ssh",
                        "state": "open"
                    },
                    {
                        "port": "80",
                        "service": "http",
                        "state": "open"
                    },
                    {
                        "port": "443",
                        "service": "https",
                        "state": "open"
                    },
                    {
                        "port": "5900",
                        "service": "vnc",
                        "state": "open"
                    }
                ]
            },
            "expected_answer": "21 / FTP",
            "flag": "FLAG{CPR1-NP1-UNU1}",
            "hints": [
                "HTTP and HTTPS are expected on a web server. Look at the remaining service."
            ],
            "explanation": "Port 5900 (VNC remote desktop) is unusual for a public web server and often signals an unauthorized service.",
            "title": "Network Port Mapping"
        },
        {
            "v": "V2",
            "difficulty": "Medium",
            "eta": "3-5 min",
            "story": "A host exposes a database port that should not be on the internet.",
            "objective": "Which exposed service indicates that a database service is directly accessible from the scanned host?",
            "lab_type": "port_map",
            "lab_data": {
                "prompt": "Which PORT is the exposed database?",
                "answer_hint": "Submit the port number.",
                "columns": [
                    {
                        "key": "port",
                        "label": "PORT"
                    },
                    {
                        "key": "service",
                        "label": "SERVICE"
                    },
                    {
                        "key": "state",
                        "label": "STATE"
                    }
                ],
                "records": [
                    {
                        "port": "80",
                        "service": "http",
                        "state": "open"
                    },
                    {
                        "port": "443",
                        "service": "https",
                        "state": "open"
                    },
                    {
                        "port": "3306",
                        "service": "mysql",
                        "state": "open"
                    },
                    {
                        "port": "22",
                        "service": "ssh",
                        "state": "open"
                    }
                ]
            },
            "expected_answer": "3306 / MySQL",
            "flag": "FLAG{CPR1-NP2-DB02}",
            "hints": [
                "Identify the port normally associated with MySQL."
            ],
            "explanation": "Port 3306 is MySQL - exposing it to the internet is a security concern.",
            "title": "Network Port Mapping"
        },
        {
            "v": "V3",
            "difficulty": "Medium",
            "eta": "4-6 min",
            "story": "Two servers scanned. One has an extra, suspicious service.",
            "objective": "Compare the two hosts. Which additional service is present only on SERVER-B?",
            "lab_type": "port_map",
            "lab_data": {
                "prompt": "Which SERVICE code appears on host B but NOT host A?",
                "answer_hint": "Submit the service name.",
                "columns": [
                    {
                        "key": "host",
                        "label": "HOST"
                    },
                    {
                        "key": "port",
                        "label": "PORT"
                    },
                    {
                        "key": "service",
                        "label": "SERVICE"
                    }
                ],
                "records": [
                    {
                        "host": "A",
                        "port": "22",
                        "service": "ssh"
                    },
                    {
                        "host": "A",
                        "port": "80",
                        "service": "http"
                    },
                    {
                        "host": "A",
                        "port": "443",
                        "service": "https"
                    },
                    {
                        "host": "B",
                        "port": "22",
                        "service": "ssh"
                    },
                    {
                        "host": "B",
                        "port": "80",
                        "service": "http"
                    },
                    {
                        "host": "B",
                        "port": "443",
                        "service": "https"
                    },
                    {
                        "host": "B",
                        "port": "137",
                        "service": "netbios-ssn"
                    }
                ]
            },
            "expected_answer": "445 / SMB",
            "flag": "FLAG{CPR1-NP3-SVC3}",
            "hints": [
                "Look for the port/service that does not appear on SERVER-A."
            ],
            "explanation": "netbios-ssn (port 137) is present on Host B but not Host A - an unusual file-sharing exposure.",
            "title": "Network Port Mapping"
        },
        {
            "v": "V4",
            "difficulty": "Medium-Hard",
            "eta": "5-7 min",
            "story": "You are mapping the services on a fictional lab server.",
            "objective": "Which open service provides remote desktop functionality and requires further investigation?",
            "lab_type": "port_map",
            "lab_data": {
                "prompt": "Which SERVICE does not belong in a production web environment?",
                "answer_hint": "Submit the service name.",
                "columns": [
                    {
                        "key": "port",
                        "label": "PORT"
                    },
                    {
                        "key": "service",
                        "label": "SERVICE"
                    },
                    {
                        "key": "state",
                        "label": "STATE"
                    }
                ],
                "records": [
                    {
                        "port": "443",
                        "service": "https",
                        "state": "open"
                    },
                    {
                        "port": "3306",
                        "service": "mysql",
                        "state": "open"
                    },
                    {
                        "port": "80",
                        "service": "http",
                        "state": "open"
                    },
                    {
                        "port": "1433",
                        "service": "mssql",
                        "state": "open"
                    }
                ]
            },
            "expected_answer": "3389 / RDP",
            "flag": "FLAG{CPR1-NP4-MSS4}",
            "hints": [
                "Identify the standard port used by Remote Desktop Protocol."
            ],
            "explanation": "Having both mysql (3306) and mssql (1433) databases on a web tier is anomalous; mssql is the outlier requested.",
            "title": "Network Port Mapping"
        }
    ],
    "PHIS": [
        {
            "v": "V1",
            "difficulty": "Medium",
            "eta": "3-5 min",
            "story": "You received an urgent-looking email. Analyze it for manipulation.",
            "objective": "Which social-engineering technique is being used to pressure the recipient?",
            "lab_type": "phishing",
            "lab_data": {
                "prompt": "Which social-engineering technique does this email use?",
                "answer_hint": "Submit the technique name (e.g. urgency).",
                "from": "no-reply@megamail.example",
                "reply_to": "reset@secure-login.example",
                "subject": "URGENT: Your account will be suspended in 24 HOURS",
                "body": "Click this link immediately and enter your password RIGHT NOW to avoid suspension.",
                "link_text": "Verify my account",
                "link_href": "https://secure-login.example/verify",
                "headers": "Return-Path: reset@secure-login.example"
            },
            "expected_answer": "Urgency / fear-based social engineering",
            "flag": "FLAG{CPR1-PH1-URG1}",
            "hints": [
                "Look at the time limit and urgent language."
            ],
            "explanation": "The email creates false urgency and time pressure to force a hasty, insecure action - the 'urgency' technique.",
            "title": "Phishing Spotter"
        },
        {
            "v": "V2",
            "difficulty": "Medium",
            "eta": "3-5 min",
            "story": "A bank-ish email landed in your simulated inbox. Check the addresses.",
            "objective": "What suspicious characteristic should investigators identify from the sender and Reply-To information?",
            "lab_type": "phishing",
            "lab_data": {
                "prompt": "Which suspicious domain does the Reply-To use?",
                "answer_hint": "Submit the domain only (no @).",
                "from": "Support @ SafeBank <support@safebank.example>",
                "reply_to": "reset@phish-site.example",
                "subject": "Verify your SafeBank account",
                "body": "Dear customer, confirm your identity to keep your account active.",
                "link_text": "Verify now",
                "link_href": "https://login.safebank.example/confirm",
                "headers": "Reply-To: reset@phish-site.example"
            },
            "expected_answer": "Suspicious/mismatched Reply-To address",
            "flag": "FLAG{CPR1-PH2-SND2}",
            "hints": [
                "Check whether the Reply-To destination matches the expected organization."
            ],
            "explanation": "The Reply-To points to phish-site.example, not the bank's domain - the attacker's address.",
            "title": "Phishing Spotter"
        },
        {
            "v": "V3",
            "difficulty": "Medium-Hard",
            "eta": "5-7 min",
            "story": "A link in an email LOOKS legitimate. Check where it actually goes.",
            "objective": "What phishing indicator is revealed by comparing the displayed URL with its actual destination?",
            "lab_type": "phishing",
            "lab_data": {
                "prompt": "What is the REAL destination domain of the link (the href)?",
                "answer_hint": "Submit the domain only (no protocol).",
                "from": "no-reply@safebank.example",
                "reply_to": "no-reply@safebank.example",
                "subject": "Security alert: sign in",
                "body": "Click to verify your identity.\nDisplay text: https://login-safebank.example/verify",
                "link_text": "https://login-safebank.example/verify",
                "link_href": "https://fake-login-abc.example/verify",
                "headers": "Return-Path: bounce@safebank.example"
            },
            "expected_answer": "Displayed URL and actual destination mismatch",
            "flag": "FLAG{CPR1-PH3-LNK3}",
            "hints": [
                "The link shown to the user is different from where the browser actually goes."
            ],
            "explanation": "The visible text says safebank but the href points to fake-login-abc.example - the attack destination.",
            "title": "Phishing Spotter"
        },
        {
            "v": "V4",
            "difficulty": "Medium-Hard",
            "eta": "5-7 min",
            "story": "An email claims to be from your company's CEO. Verify the sender.",
            "objective": "What type of phishing activity is the attacker attempting?",
            "lab_type": "phishing",
            "lab_data": {
                "prompt": "Which non-corporate domain shows this isn't really the CEO?",
                "answer_hint": "Submit the domain only (no @).",
                "from": "CEO Sarah <sarah.ceo@gmail.example>",
                "reply_to": "sarah.ceo@gmail.example",
                "subject": "Urgent: wire transfer needed",
                "body": "Sarah, our CEO, needs you to approve the payment immediately.",
                "link_text": "Approve",
                "link_href": "https://payments.finance.example/approve",
                "headers": "Sender: sarah.ceo@gmail.example"
            },
            "expected_answer": "Credential phishing / credential harvesting",
            "flag": "FLAG{CPR1-PH4-CEO4}",
            "hints": [
                "The attacker is trying to obtain authentication information from the victim."
            ],
            "explanation": "The CEO impersonator used a public mail domain (gmail.example) instead of the corporate domain - the deception.",
            "title": "Phishing Spotter"
        }
    ],
    "META": [
        {
            "v": "V1",
            "difficulty": "Medium",
            "eta": "3-4 min",
            "story": "You received a 'final' report doc. Its metadata may reveal who wrote it.",
            "objective": "Identify the author recorded in the document metadata.",
            "lab_type": "metadata",
            "lab_data": {
                "prompt": "Who is the author stored in the metadata?",
                "answer_hint": "Submit the author value.",
                "file": "report_final.docx",
                "columns": [
                    {
                        "key": "field",
                        "label": "FIELD"
                    },
                    {
                        "key": "value",
                        "label": "VALUE"
                    }
                ],
                "records": [
                    {
                        "field": "Author",
                        "value": "j.morales"
                    },
                    {
                        "field": "Last Modified By",
                        "value": "j.morales"
                    },
                    {
                        "field": "Created",
                        "value": "2025-11-12"
                    },
                    {
                        "field": "Software",
                        "value": "LibreOffice 7.4"
                    }
                ]
            },
            "expected_answer": "A.Raman",
            "flag": "FLAG{CPR1-MD1-AUT1}",
            "hints": [
                "Look specifically at the Author field."
            ],
            "explanation": "The Author metadata field shows j.morales.",
            "title": "Metadata Detective"
        },
        {
            "v": "V2",
            "difficulty": "Medium",
            "eta": "3-4 min",
            "story": "An invoice PDF's metadata reveals when it was last changed.",
            "objective": "What is the last modified timestamp recorded for the evidence file?",
            "lab_type": "metadata",
            "lab_data": {
                "prompt": "What is the Last Modified timestamp?",
                "answer_hint": "Submit the value exactly as shown.",
                "file": "invoice.pdf",
                "columns": [
                    {
                        "key": "field",
                        "label": "FIELD"
                    },
                    {
                        "key": "value",
                        "label": "VALUE"
                    }
                ],
                "records": [
                    {
                        "field": "Author",
                        "value": "finance-svc"
                    },
                    {
                        "field": "Creation",
                        "value": "2025-09-01 09:00"
                    },
                    {
                        "field": "Modified",
                        "value": "2025-09-01 11:32"
                    },
                    {
                        "field": "Producer",
                        "value": "PDFKit"
                    }
                ]
            },
            "expected_answer": "2026-08-21 18:42",
            "flag": "FLAG{CPR1-MD2-MOD2}",
            "hints": [
                "Do not use the creation timestamp. Look at Modified."
            ],
            "explanation": "The Modified field records 2025-09-01 11:32.",
            "title": "Metadata Detective"
        },
        {
            "v": "V3",
            "difficulty": "Medium",
            "eta": "4-5 min",
            "story": "An image's EXIF metadata reveals which editor was used on it.",
            "objective": "Which device is recorded in the image metadata?",
            "lab_type": "metadata",
            "lab_data": {
                "prompt": "Which software was used on this image (from EXIF)?",
                "answer_hint": "Submit the software name.",
                "file": "photo_001.jpg",
                "columns": [
                    {
                        "key": "field",
                        "label": "FIELD"
                    },
                    {
                        "key": "value",
                        "label": "VALUE"
                    }
                ],
                "records": [
                    {
                        "field": "Make",
                        "value": "SampleCam"
                    },
                    {
                        "field": "Model",
                        "value": "SN-500"
                    },
                    {
                        "field": "Software",
                        "value": "GIMP 2.10"
                    },
                    {
                        "field": "DateTime",
                        "value": "2025-06-15 14:22"
                    }
                ]
            },
            "expected_answer": "Canon EOS",
            "flag": "FLAG{CPR1-MD3-SFT3}",
            "hints": [
                "Look at the Device field."
            ],
            "explanation": "The EXIF Software field shows GIMP 2.10, indicating the image was edited with GIMP.",
            "title": "Metadata Detective"
        },
        {
            "v": "V4",
            "difficulty": "Medium-Hard",
            "eta": "5-6 min",
            "story": "A contract claims it was prepared on one date, but the metadata disagrees.",
            "objective": "What location is recorded in the supplied fictional metadata?",
            "lab_type": "metadata",
            "lab_data": {
                "prompt": "The document text says 'Prepared on 2025-08-20', but what does the METADATA say?",
                "answer_hint": "Submit the metadata modification date.",
                "file": "contract.pdf",
                "columns": [
                    {
                        "key": "field",
                        "label": "FIELD"
                    },
                    {
                        "key": "value",
                        "label": "VALUE"
                    }
                ],
                "records": [
                    {
                        "field": "Document text",
                        "value": "Prepared on 2025-08-20"
                    },
                    {
                        "field": "Author",
                        "value": "legal-dept"
                    },
                    {
                        "field": "Modified",
                        "value": "2025-08-27"
                    },
                    {
                        "field": "Created",
                        "value": "2025-08-19"
                    }
                ]
            },
            "expected_answer": "Chennai",
            "flag": "FLAG{CPR1-MD4-DTA4}",
            "hints": [
                "Use the location associated with the supplied GPS metadata."
            ],
            "explanation": "The metadata Modified field shows 2025-08-27, a week after the claimed date - revealing tampering.",
            "title": "Metadata Detective"
        }
    ],
    "CIPH": [
        {
            "v": "V1",
            "difficulty": "Easy",
            "eta": "5-7 min",
            "story": "A value was first Caesar-shifted by +1, then Base64-encoded.",
            "objective": "Reverse the supplied encoding sequence using the provided tools and recover the hidden investigation message.",
            "lab_type": "cipher_chain",
            "lab_data": {
                "encoded": "QnV1YmRs",
                "chain": [
                    "1) Caesar shift each letter back by 1",
                    "2) Base64-decode"
                ],
                "notes": "The encoding was: plaintext -> Caesar(+1) -> Base64."
            },
            "expected_answer": "Decoded investigation message from the supplied evidence.",
            "flag": "FLAG{CPR1-CP1-ATT1}",
            "hints": [
                "When decoding a chain, work from the last encoding layer backward."
            ],
            "explanation": "ROT-1 of 'QnV1YmRs' then Base64-decode yields 'Attack'.",
            "title": "Cipher Chain"
        },
        {
            "v": "V2",
            "difficulty": "Medium",
            "eta": "6-8 min",
            "story": "A plaintext was hex-encoded, then that hex text was Base64-encoded.",
            "objective": "Decode the Base64 layer, convert the resulting hexadecimal value to ASCII, and identify the final clue.",
            "lab_type": "cipher_chain",
            "lab_data": {
                "encoded": "NGU2OTc0NjU=",
                "chain": [
                    "1) Base64-decode (you get hex characters)",
                    "2) Convert hex to ASCII"
                ],
                "notes": "Encoding: plaintext -> hex (as text) -> Base64."
            },
            "expected_answer": "Final ASCII clue from the decoded evidence.",
            "flag": "FLAG{CPR1-CP2-NIT2}",
            "hints": [
                "Start with Base64, then interpret the resulting hexadecimal characters."
            ],
            "explanation": "Base64-decode gives hex 4e697465 which spells 'Nite'.",
            "title": "Cipher Chain"
        },
        {
            "v": "V3",
            "difficulty": "Medium",
            "eta": "6-8 min",
            "story": "A string was hex-encoded after a Caesar shift of +3.",
            "objective": "Convert the hexadecimal evidence to text and apply the supplied Caesar shift to reveal the plaintext.",
            "lab_type": "cipher_chain",
            "lab_data": {
                "encoded": "4e6868736875",
                "chain": [
                    "1) Hex-decode to ASCII letters",
                    "2) Caesar shift each letter back 3"
                ],
                "notes": "Encoding: plaintext -> Caesar(+3) -> hex."
            },
            "expected_answer": "Decoded plaintext after reversing the shift.",
            "flag": "FLAG{CPR1-CP3-KEE3}",
            "hints": [
                "Decode Hex first, then reverse the Caesar shift by 3."
            ],
            "explanation": "Hex gives 'Nhhshu'; Caesar back 3 gives 'Keeper'.",
            "title": "Cipher Chain"
        },
        {
            "v": "V4",
            "difficulty": "Medium-Hard",
            "eta": "8-10 min",
            "story": "Three layers: Caesar(+1) -> Base64 -> Hex.",
            "objective": "Reverse all the supplied encoding layers in the correct order and reveal the final investigation clue.",
            "lab_type": "cipher_chain",
            "lab_data": {
                "encoded": "556e5a716257303d",
                "chain": [
                    "1) Hex-decode (you get a Base64 string)",
                    "2) Base64-decode",
                    "3) Caesar shift each letter back 1"
                ],
                "notes": "Encoding: plaintext -> Caesar(+1) -> Base64 -> hex."
            },
            "expected_answer": "Final decoded investigation clue.",
            "flag": "FLAG{CPR1-CP4-QUI4}",
            "hints": [
                "Always decode the outermost layer first and work backward through the chain."
            ],
            "explanation": "Following the chain in reverse yields the word 'Quill'.",
            "title": "Cipher Chain"
        }
    ],
    "HASH": [
        {
            "v": "V1",
            "difficulty": "Medium",
            "eta": "3-5 min",
            "story": "An account stores a 32-char hash. Identify the algorithm.",
            "objective": "Based on the supplied hash format, identify the most likely hashing algorithm.",
            "lab_type": "hash_analysis",
            "lab_data": {
                "prompt": "What hash algorithm produced this 32-character hexadecimal value?",
                "encoded": "e10adc3949ba59abbe56e057f20f883e",
                "notes": "32 hex chars = 128 bits."
            },
            "expected_answer": "MD5",
            "flag": "FLAG{CPR1-HS1-MD51}",
            "hints": [
                "Count the hexadecimal characters. MD5, SHA-1, and SHA-256 have different digest lengths."
            ],
            "explanation": "A 32-character hexadecimal hash of 128 bits is MD5.",
            "title": "Hash Analysis"
        },
        {
            "v": "V2",
            "difficulty": "Medium",
            "eta": "5-7 min",
            "story": "You found a hash and a short wordlist. Match the password.",
            "objective": "Match the recovered hash against the supplied offline candidate list and identify the corresponding password.",
            "lab_type": "hash_analysis",
            "lab_data": {
                "prompt": "Which wordlist password matches this MD5 hash?",
                "encoded": "5f4dcc3b5aa765d61d8327deb882cf99",
                "notes": "Try MD5 of each word below.",
                "wordlist": [
                    "admin",
                    "password",
                    "temp123",
                    "secret"
                ]
            },
            "expected_answer": "secret",
            "flag": "FLAG{CPR1-HS2-MTH2}",
            "hints": [
                "Generate the MD5 hash of each candidate and compare it with the recovered hash."
            ],
            "explanation": "The MD5 5f4dcc3b5aa765d61d8327deb882cf99 is the hash of 'password'.",
            "title": "Hash Analysis"
        },
        {
            "v": "V3",
            "difficulty": "Medium-Hard",
            "eta": "5-7 min",
            "story": "A record stores this SHA256 hash. Find the matching wordlist entry.",
            "objective": "Which candidate matches the recovered SHA-1 evidence?",
            "lab_type": "hash_analysis",
            "lab_data": {
                "prompt": "Which wordlist password (SHA256) matches this hash?",
                "encoded": "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8",
                "notes": "Try SHA256 of each candidate.",
                "wordlist": [
                    "hello",
                    "qwerty",
                    "letmein",
                    "pass123"
                ]
            },
            "expected_answer": "admin123",
            "flag": "FLAG{CPR1-HS3-SH53}",
            "hints": [
                "Generate the SHA-1 hash of each candidate and compare."
            ],
            "explanation": "The SHA256 digest corresponds to the word 'qwerty'.",
            "title": "Hash Analysis"
        },
        {
            "v": "V4",
            "difficulty": "Medium-Hard",
            "eta": "5-7 min",
            "story": "An account uses an MD5 hash. Which stored word is the weakest match?",
            "objective": "Which candidate matches the supplied SHA-256 evidence?",
            "lab_type": "hash_analysis",
            "lab_data": {
                "prompt": "Which word mirrors this weak account hash?",
                "encoded": "5f4dcc3b5aa765d61d8327deb882cf99",
                "notes": "The hash matches one of these words.",
                "wordlist": [
                    "admin",
                    "password",
                    "cookie",
                    "winter"
                ]
            },
            "expected_answer": "password",
            "flag": "FLAG{CPR1-HS4-WK01}",
            "hints": [
                "Calculate the SHA-256 hash of each candidate and compare the results."
            ],
            "explanation": "The hash is MD5('password'); 'password' is the weak and most-guessable entry.",
            "title": "Hash Analysis"
        }
    ],
    "WEBH": [
        {
            "v": "V1",
            "difficulty": "Medium-Hard",
            "eta": "3-5 min",
            "story": "A simulated site's HTML contains a clue in a comment.",
            "objective": "Inspect the page source and identify the hidden investigation path.",
            "lab_type": "source_view",
            "lab_data": {
                "prompt": "What clue is in the HTML comment?",
                "answer_hint": "Submit the exact value.",
                "url": "https://dev.local/",
                "html_source": "<!-- hint: the admin panel is at /console -->\n<html>\n<body>\n  <h1>Welcome to the site</h1>\n</body>\n</html>"
            },
            "expected_answer": "/archive",
            "flag": "FLAG{CPR1-WB1-CMT1}",
            "hints": [
                "Look for HTML comments that are not visible on the rendered page."
            ],
            "explanation": "The comment reveals the hidden admin route /console.",
            "title": "Web Source Hunt"
        },
        {
            "v": "V2",
            "difficulty": "Medium-Hard",
            "eta": "3-5 min",
            "story": "A page element carries a hidden data attribute.",
            "objective": "Inspect the supplied HTML and identify the value stored in the data-key attribute.",
            "lab_type": "source_view",
            "lab_data": {
                "prompt": "What is the value of data-secret?",
                "answer_hint": "Submit the attribute value.",
                "url": "https://app.local/",
                "html_source": "<div id=\"app\" data-version=\"2.3\" data-secret=\"blueprint\">App</div>\n<html><body>Spare content...</body></html>"
            },
            "expected_answer": "blue-door",
            "flag": "FLAG{CPR1-WB2-DAT2}",
            "hints": [
                "Read the value between data-key=\"...\"."
            ],
            "explanation": "The data-secret attribute holds the value 'blueprint'.",
            "title": "Web Source Hunt"
        },
        {
            "v": "V3",
            "difficulty": "Medium-Hard",
            "eta": "4-6 min",
            "story": "A robots.txt file hints at a hidden path.",
            "objective": "Which path is restricted according to the supplied robots.txt file?",
            "lab_type": "source_view",
            "lab_data": {
                "prompt": "Which path is disallowed in robots.txt?",
                "answer_hint": "Submit the exact path.",
                "url": "https://site.local/robots.txt",
                "html_source": "User-agent: *\nDisallow: /private/\nDisallow: /admin"
            },
            "expected_answer": "/backup/",
            "flag": "FLAG{CPR1-WB3-RBT3}",
            "hints": [
                "Look at the value following the Disallow directive."
            ],
            "explanation": "robots.txt disallows /private/, which may hide unlinked content.",
            "title": "Web Source Hunt"
        },
        {
            "v": "V4",
            "difficulty": "Medium-Hard",
            "eta": "4-6 min",
            "story": "A page's meta tag reveals the author.",
            "objective": "Inspect the HTML metadata and identify the value stored in the author field.",
            "lab_type": "source_view",
            "lab_data": {
                "prompt": "What is the meta author content?",
                "answer_hint": "Submit the exact value.",
                "url": "https://blog.local/",
                "html_source": "<meta name=\"author\" content=\"t.owens\">\n<html><body>Welcome to the dev blog.</body></html>"
            },
            "expected_answer": "trace_admin",
            "flag": "FLAG{CPR1-WB4-MET4}",
            "hints": [
                "Find name=\"author\" and read its content value."
            ],
            "explanation": "The meta author tag reveals t.owens as the hidden detail.",
            "title": "Web Source Hunt"
        }
    ],
    "FILE": [
        {
            "v": "V1",
            "difficulty": "Medium-Hard",
            "eta": "3-5 min",
            "story": "A file is named report.png, but its magic bytes look like a PDF.",
            "objective": "The extension is `.dat`. Based on the magic bytes, what is the actual file type?",
            "lab_type": "file_magic",
            "lab_data": {
                "prompt": "What is the real file type?",
                "answer_hint": "Submit the type name (e.g. PDF).",
                "filename": "report.png",
                "magic": "25 50 44 46 2D",
                "notes": "25 50 44 46 2D is the hex for '%PDF-'."
            },
            "expected_answer": "PDF",
            "flag": "FLAG{CPR1-FM1-PDF1}",
            "hints": [
                "Do not trust the extension. Identify the file using its signature."
            ],
            "explanation": "The magic bytes '%PDF-1.' identify it as a PDF despite the .png extension.",
            "title": "File Magic"
        },
        {
            "v": "V2",
            "difficulty": "Medium-Hard",
            "eta": "3-4 min",
            "story": "Identify a file type from its signature bytes.",
            "objective": "Identify the actual file format from the supplied file signature.",
            "lab_type": "file_magic",
            "lab_data": {
                "prompt": "What file type has these magic bytes?",
                "answer_hint": "Submit the type name.",
                "filename": "image.bin",
                "magic": "89 50 4E 47 0D 0A 1A 0A",
                "notes": "89 50 4E 47 spells 'PNG'."
            },
            "expected_answer": "PNG",
            "flag": "FLAG{CPR1-FM2-PNG2}",
            "hints": [
                "The first four bytes are a well-known image signature."
            ],
            "explanation": "The signature 0x89 'PNG' identifies a PNG image.",
            "title": "File Magic"
        },
        {
            "v": "V3",
            "difficulty": "Medium-Hard",
            "eta": "4-5 min",
            "story": "A file called notes.txt actually has ZIP magic bytes.",
            "objective": "Determine the actual file format represented by these magic bytes.",
            "lab_type": "file_magic",
            "lab_data": {
                "prompt": "What is the real type of this file?",
                "answer_hint": "Submit the type name.",
                "filename": "notes.txt",
                "magic": "50 4B 03 04",
                "notes": "50 4B is 'PK', the ZIP signature."
            },
            "expected_answer": "ZIP",
            "flag": "FLAG{CPR1-FM3-ZIP3}",
            "hints": [
                "This signature is commonly associated with compressed archive files."
            ],
            "explanation": "The PK signature indicates a ZIP archive disguised with a .txt extension.",
            "title": "File Magic"
        },
        {
            "v": "V4",
            "difficulty": "Medium-Hard",
            "eta": "3-4 min",
            "story": "Match a file format from its leading bytes.",
            "objective": "The extension is misleading. Identify the actual image format from the signature.",
            "lab_type": "file_magic",
            "lab_data": {
                "prompt": "What file type begins with these bytes?",
                "answer_hint": "Submit the type name.",
                "filename": "anim.bin",
                "magic": "47 49 46 38 37 61",
                "notes": "This spells 'GIF87a'."
            },
            "expected_answer": "JPEG / JPG",
            "flag": "FLAG{CPR1-FM4-GIF4}",
            "hints": [
                "Look up the common JPEG file signature beginning with FF D8."
            ],
            "explanation": "The bytes spell 'GIF87a', the signature for GIF images.",
            "title": "File Magic"
        }
    ],
    "CSAR": [
        {
            "v": "V1",
            "difficulty": "Easy",
            "eta": "2-3 min",
            "story": "A message was rotated with ROT13.",
            "objective": "Decode the message using ROT13 and identify the plaintext investigation clue.",
            "lab_type": "caesar",
            "lab_data": {
                "encoded": "pbqr",
                "shift_label": "ROT13",
                "notes": "ROT13 shifts letters by 13."
            },
            "expected_answer": "THE CASE IS CLOSED",
            "flag": "FLAG{CPR1-CR1-COD1}",
            "hints": [
                "Move every alphabetic character 13 positions in the alphabet."
            ],
            "explanation": "ROT13 of 'pbqr' is 'code'.",
            "title": "Caesar / ROT Decode"
        },
        {
            "v": "V2",
            "difficulty": "Medium",
            "eta": "5-6 min",
            "story": "A word was Caesar-shifted by +3 (A->D).",
            "objective": "Apply the supplied Caesar shift and recover the plaintext.",
            "lab_type": "caesar",
            "lab_data": {
                "encoded": "Vshdulxqlqj",
                "shift_label": "Caesar shift +3",
                "notes": "Shift each letter back 3."
            },
            "expected_answer": "CASE",
            "flag": "FLAG{CPR1-CR2-SEC2}",
            "hints": [
                "For decryption, move each character 3 positions backward."
            ],
            "explanation": "Caesar -3 of 'Vshdulxqlqj' yields 'Securing'.",
            "title": "Caesar / ROT Decode"
        },
        {
            "v": "V3",
            "difficulty": "Medium-Hard",
            "eta": "6-8 min",
            "story": "A message was reversed, then Caesar-shifted by +3.",
            "objective": "Decode the ciphertext using the supplied shift and identify the hidden clue.",
            "lab_type": "caesar",
            "lab_data": {
                "encoded": "Grohq dsdg",
                "shift_label": "Reverse then Caesar +3",
                "notes": "Reverse 'Grohq dsdg', then unshift each letter by 3."
            },
            "expected_answer": "TRACE",
            "flag": "FLAG{CPR1-CR3-ALE3}",
            "hints": [
                "Move each character 5 positions backward."
            ],
            "explanation": "Reversing and Caesar -3 yields 'alert'.",
            "title": "Caesar / ROT Decode"
        },
        {
            "v": "V4",
            "difficulty": "Medium-Hard",
            "eta": "6-8 min",
            "story": "The shift amount is unknown. Brute-force all 25 shifts to find English.",
            "objective": "Determine the Caesar shift and decode the message to reveal the meaningful investigation-related word.",
            "lab_type": "caesar",
            "lab_data": {
                "encoded": "Lzdfq",
                "shift_label": "Unknown Caesar shift",
                "notes": "Try every shift (ROT1..ROT25); one gives a real word."
            },
            "expected_answer": "CASE \u2014 shift 3.",
            "flag": "FLAG{CPR1-CR4-CIP4}",
            "hints": [
                "Try different shifts until the result becomes a meaningful investigation word."
            ],
            "explanation": "Among all shifts, the readable result is 'Cipher'.",
            "title": "Caesar / ROT Decode"
        }
    ],
    "OSNT": [
        {
            "v": "V1",
            "difficulty": "Medium-Hard",
            "eta": "3-5 min",
            "story": "A fictional employee's public profile is the clue.",
            "objective": "Correlate the supplied fictional profile and project page. Identify the developer's username.",
            "lab_type": "osint",
            "lab_data": {
                "prompt": "What is Alice's public profile username?",
                "answer_hint": "Submit the handle.",
                "scenario": "Alice works at Acme. Her public Hubsight profile lists her handle as 'alice_dev' and location 'Bengaluru'.",
                "clues": [
                    "Name: Alice",
                    "Company: Acme",
                    "Profile handle: alice_dev",
                    "Location: Bengaluru"
                ]
            },
            "expected_answer": "dev_trace",
            "flag": "FLAG{CPR1-OS1-ALC1}",
            "hints": [
                "Look for the identifier that appears in both the profile and project information."
            ],
            "explanation": "The public profile clearly lists the handle alice_dev.",
            "title": "OSINT Link Puzzle"
        },
        {
            "v": "V2",
            "difficulty": "Medium-Hard",
            "eta": "3-5 min",
            "story": "A fictional company blog reveals the author of a project.",
            "objective": "Connect the project information with the profile and identify the person associated with the project.",
            "lab_type": "osint",
            "lab_data": {
                "prompt": "Which first name signed the blog post?",
                "answer_hint": "Submit the first name.",
                "scenario": "A blog post about Project Nova is signed by its author Rajesh.",
                "clues": [
                    "Post: 'Project Nova v2 launched today!'",
                    "Signed: '-- Rajesh'",
                    "Role: project author"
                ]
            },
            "expected_answer": "Arun \u2014 username: arun_builds",
            "flag": "FLAG{CPR1-OS2-RJ2}",
            "hints": [
                "Use the common project name to connect the two pieces of evidence."
            ],
            "explanation": "The post is signed by Rajesh.",
            "title": "OSINT Link Puzzle"
        },
        {
            "v": "V3",
            "difficulty": "Medium-Hard",
            "eta": "4-6 min",
            "story": "A fictional project README lists a maintainer email.",
            "objective": "Identify the organization/project domain from the supplied fictional evidence.",
            "lab_type": "osint",
            "lab_data": {
                "prompt": "What is the maintainer email domain (after the @)?",
                "answer_hint": "Submit the domain only.",
                "scenario": "The README lists a maintainer contact email.",
                "clues": [
                    "README: 'Maintainer: dev-team@openforge.example'"
                ]
            },
            "expected_answer": "mysterylab.example",
            "flag": "FLAG{CPR1-OS3-D3V3}",
            "hints": [
                "The same domain appears in both the email address and website."
            ],
            "explanation": "The domain after @ is openforge.example.",
            "title": "OSINT Link Puzzle"
        },
        {
            "v": "V4",
            "difficulty": "Medium-Hard",
            "eta": "4-6 min",
            "story": "Two fictional public clues point to the announcement author.",
            "objective": "Correlate all three evidence sources and identify the account responsible for the final project announcement.",
            "lab_type": "osint",
            "lab_data": {
                "prompt": "Who posted the announcement?",
                "answer_hint": "Submit the handle.",
                "scenario": "An announcement post and a docs repo share a maintainer.",
                "clues": [
                    "Announcement posted by: docs_mgr",
                    "Docs repo managed by: km_team"
                ]
            },
            "expected_answer": "case_admin",
            "flag": "FLAG{CPR1-OS4-DOC4}",
            "hints": [
                "Find the username repeated across all three evidence sources."
            ],
            "explanation": "The announcement is posted by docs_mgr.",
            "title": "OSINT Link Puzzle"
        }
    ]
}


def seed(reset=False):
    if reset:
        db.reset_db()
    else:
        db.init_db()

    conn = db.get_connection()
    try:
        cat_id_by_code = {}
        for cat in CATEGORIES:
            conn.execute(
                "INSERT OR IGNORE INTO challenge_categories "
                "(challenge_code, title, domain, description, difficulty, points, active) "
                "VALUES (?,?,?,?,?,?,1)",
                (cat["code"], cat["title"], cat["domain"], cat["description"],
                 cat["difficulty"], cat["points"]),
            )
            row = conn.execute(
                "SELECT id FROM challenge_categories WHERE challenge_code=?",
                (cat["code"],),
            ).fetchone()
            cat_id_by_code[cat["code"]] = row["id"]

        for code, variants in VARIANTS.items():
            clist = VARIANTS[code]
            assert len(clist) == 4, \
                f"Category {code} must have exactly 4 variants (got {len(clist)})"
            cat_id = cat_id_by_code[code]
            for i, v in enumerate(clist, start=1):
                title = v.get("title") or CATEGORIES[[c["code"] for c in CATEGORIES].index(code)]["title"]
                conn.execute(
                    "INSERT OR IGNORE INTO challenge_variants "
                    "(challenge_category_id, variant_code, title, question, task_description, "
                    "provided_data, expected_answer, flag, difficulty, hint, explanation, "
                    "estimated_solve_time, lab_type, story, objective, lab_data, hints) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        cat_id, v["v"], title, v["objective"], v["objective"],
                        json.dumps(v["lab_data"]),        # provided_data (renderable lab content)
                        v["expected_answer"], v["flag"], v["difficulty"],
                        v["hints"][0] if v["hints"] else "", v["explanation"],
                        v["eta"], v["lab_type"], v["story"], v["objective"],
                        json.dumps(v["lab_data"]), json.dumps(v["hints"]),
                    ),
                )
        conn.commit()
        num_variants = sum(len(v) for v in VARIANTS.values())
        print(f"Seeded {len(CATEGORIES)} categories and {num_variants} lab variants.")

        conn.execute(
            "INSERT OR IGNORE INTO admins (username, password_hash) VALUES (?,?)",
            (DEFAULT_ADMIN_USERNAME, generate_password_hash(DEFAULT_ADMIN_PASSWORD)),
        )
        conn.commit()
        print(f"Admin account ready: username='{DEFAULT_ADMIN_USERNAME}', "
              f"password='{DEFAULT_ADMIN_PASSWORD}'")
    finally:
        conn.close()


if __name__ == "__main__":
    reset_flag = "--reset" in sys.argv
    seed(reset=reset_flag)