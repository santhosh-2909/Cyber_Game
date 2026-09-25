/* MYSTERY TRACE · engines.js
 * Engine registry keyed by game_type — one entry per mini-game (48 total).
 * Every engine decides how the server-issued `evidence` + public `config`
 * are presented.  Evidence is fully safe to ship: answers / flags / accept
 * lists stay server-side and are never sent to this file.
 */
(function () {
  'use strict';

  // -------------------------------------------------------------------- utils

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function hx(html) { return html; }

  // Evidence shapes are defence-tolerant: some challenges ship their fields as a
  // single value (a form name, a dict of servers, a flat category list) instead
  // of an array. Never crash on a non-array — coerce it into a renderable list.
  function toList(x) {
    if (Array.isArray(x)) return x;
    if (x == null || x === '') return [];
    if (typeof x === 'object') return Object.keys(x).map(function (k) {
      return { key: k, value: x[k] };
    });
    return [x];
  }

  function kv(label, value, mono) {
    return '<div class="mt-row"><span class="mt-row-label">' + esc(label) + '</span>' +
      '<span class="mt-row-value' + (mono ? ' font-mono' : '') + '">' + esc(value) + '</span></div>';
  }

  function table(rows) {
    if (!rows) return '';
    var dict = !Array.isArray(rows) && typeof rows === 'object';
    if (dict) {
      rows = Object.keys(rows).map(function (k) {
        var v = rows[k];
        return { name: k, value: Array.isArray(v) ? v.join(', ') : v };
      });
    }
    if (!rows.length) return '';
    var keys = Object.keys(rows[0]);
    var head = keys.map(function (k) { return '<th>' + esc(k) + '</th>'; }).join('');
    var body = rows.map(function (r) {
      return '<tr>' + keys.map(function (k) {
        var v = r[k];
        return '<td class="font-mono">' + esc(Array.isArray(v) ? v.join(', ') : v) + '</td>';
      }).join('') + '</tr>';
    }).join('');
    return '<div class="table-wrapper"><table class="table mt-table"><thead><tr>' + head +
      '</tr></thead><tbody>' + body + '</tbody></table></div>';
  }

  function terminal(text, label) {
    return '<div class="card-terminal" style="font-size:0.9rem;padding:20px;">' +
      (label ? '<div style="opacity:0.5;font-size:0.72rem;margin-bottom:10px;">' + esc(label) + '</div>' : '') +
      '<div style="color:var(--cyan);word-break:break-all;white-space:pre-wrap;">' + esc(text) + '</div></div>';
  }

  function section(title) {
    return '<div class="font-overline text-muted mb-sm" style="margin-top:14px;">' + esc(title) + '</div>';
  }

  function block(html, cls) {
    return '<div class="' + (cls || '') + '" style="margin-top:16px;">' + html + '</div>';
  }

  function chips(list, cls) {
    return toList(list).map(function (v) {
      if (v && typeof v === 'object') v = v.key != null ? v.key : (v.name || v.label || '');
      return '<span class="font-mono" style="display:inline-block;background:var(--accent-signal-dim);' +
        'border:1px solid var(--accent-signal-border);color:var(--accent-signal);border-radius:6px;' +
        'padding:4px 10px;margin:0 8px 8px 0;font-size:0.8rem;">' + esc(v) + '</span>';
    }).join('');
  }

  function keyedRows(list, keyLabel, elLabel) {
    list = toList(list);
    if (!list.length) return '';
    return list.map(function (o) {
      if (typeof o === 'string') return '<div class="card-section">' + esc(o) + '</div>';
      var k = String(o[keyLabel] != null ? o[keyLabel] : Object.keys(o)[0] || '');
      var others = Object.keys(o).filter(function (x) { return x !== keyLabel; });
      var body = others.map(function (x) { return kv(x, o[x]); }).join('');
      return '<div class="mt-group"><div class="mt-group-title font-mono">' + esc(k) + '</div>' + body + '</div>';
    }).join('');
  }

  // Live helpers used by interactive engines
  var liveTools = function () {
    if (window.MTLiveTools) return window.MTLiveTools;
    var api = {};
    api.caesarInput = function (id) {
      return '<div class="card" style="background:var(--bg-base);padding:16px;margin-top:16px;">' +
        '<div class="flex items-center" style="gap:12px;flex-wrap:wrap;">' +
        '<label class="font-mono text-muted" style="font-size:0.78rem;">SHIFT</label>' +
        '<input id="' + id + '-shift" type="range" min="1" max="25" value="0" style="flex:1;">' +
        '<span class="font-mono" id="' + id + '-shiftval" style="width:60px;text-align:right;color:var(--hud-green);">0</span>' +
        '</div></div>';
    };
    return api;
  };

  // -------------------------------------------------------------------- rooms

  // Each engine is: { label, kind, render(evidence, cfg, host) }.
  // `kind` drives a shared visual language (terminal / table / cards / code).

  function strEngine(label) {
    return {
      label: label,
      render: function (ev, cfg) {
        return terminal(typeof ev === 'string' ? ev : JSON.stringify(ev, null, 2), 'sandbox_data');
      }
    };
  }

  function cardsEngine(label) {
    return {
      label: label,
      render: function (ev, cfg) {
        if (!ev || !ev.cards) return terminal(JSON.stringify(ev, null, 2));
        return '<div class="mt-grid">' + toList(ev.cards).map(function (c) {
          var ttl = c.name || c.title || c.card || (typeof c === 'string' ? c : '');
          var body = '';
          Object.keys(c).forEach(function (k) {
            if (k === 'name' || k === 'title' || k === 'card') return;
            body += kv(k, c[k]);
          });
          return '<div class="hud-panel mt-card"><div class="font-mono" style="color:var(--hud-amber);' +
            'font-weight:800;margin-bottom:8px;">' + esc(ttl) + '</div>' + (body || '') + '</div>';
        }).join('') + '</div>';
      }
    };
  }

  function queryEngine(label) {
    return {
      label: label,
      render: function (ev, cfg) {
        var out = '';
        if (ev.query_template) out += section('QUERY TEMPLATE') + terminal(ev.query_template, 'server_route');
        if (ev.form) {
          // `form` is the login form name (string) for most challenges; some ship
          // a list of {label, placeholder} fields. Render either without crashing.
          out += section('LOGIN FORM') + block(
            '<div style="max-width:360px;">' + toList(ev.form).map(function (f) {
              var label = typeof f === 'string' ? f : (f.label || 'Field');
              var placeholder = (f && f.placeholder) || '';
              return '<div class="form-group" style="margin-bottom:10px;"><label class="form-label">' +
                esc(label) + '</label><input class="form-input form-input-mono" type="text" disabled ' +
                'value="" placeholder="' + esc(placeholder) + '"></div>';
            }).join('') + '</div>');
        }
        if (ev.target_user) out += block(chips([ev.target_user], null));
        if (ev.fragments) out += section('QUERY FRAGMENTS') + block(chips(ev.fragments));
        if (ev.debug) out += section('DEBUG OUTPUT') + terminal(ev.debug, 'dbg');
        return out;
      }
    };
  }

  function portEngine(label) {
    return {
      label: label,
      render: function (ev, cfg) {
        var out = '';
        if (ev.host) out += block(kv('Target', ev.host, true) + kv('Role', ev.role || ''));
        if (ev.ports) out += section('PORT SCAN') + block(
          '<div class="mt-grid mt-grid-ports">' + toList(ev.ports).map(function (p) {
            if (typeof p === 'string') return terminal(p);
            var open = String(p.state || p.status || '').toLowerCase();
            return '<div class="hud-panel mt-card" style="text-align:center;">' +
              '<div class="font-mono" style="font-size:1.3rem;color:var(--hud-amber);font-weight:800;">' + esc(p.port) + '</div>' +
              '<div class="hud-stat-label" style="margin-top:4px;">' + esc(p.service || p.name || '') + '</div>' +
              '<div class="hud-badge ' + (open === 'open' ? 'hud-badge-green' : 'hud-badge-muted') + '" style="display:inline-block;margin-top:8px;">' +
              esc(p.state || p.status || '') + '</div></div>';
          }).join('') + '</div>');
        if (ev.services) out += section('SERVICE MAP') + block(table(ev.services));
        if (ev.servers) out += section('SERVER COMPARISON') + block(table(ev.servers));
        return out;
      }
    };
  }

  function listEngine(label) {
    return {
      label: label,
      render: function (ev, cfg) {
        var out = '';
        if (ev.clues) out += section('PUBLIC CLUES') + block(toList(ev.clues).map(function (c) {
          return '<div class="card-section">' + esc(c) + '</div>';
        }).join(''));
        if (ev.people) out += section('PEOPLE') + block(keyedRows(ev.people, 'name'));
        if (ev.usernames) out += section('USERNAMES') + block(chips(ev.usernames));
        if (ev.projects) out += section('PROJECTS') + block(chips(ev.projects));
        if (ev.org) out += section('ORGANISATION') + block(keyedRows(ev.org, 'name'));
        if (ev.references) out += section('REFERENCES') + block(toList(ev.references).map(function (r) {
          return '<div class="card-section font-mono" style="font-size:0.85rem;">' + esc(r) + '</div>';
        }).join(''));
        if (ev.nodes) out += section('CONNECTIONS') + block('<div class="mt-grid mt-grid-nodes">' + toList(ev.nodes).map(function (n) {
          var ttl = typeof n === 'string' ? n : (n.name || n.id || '');
          return '<div class="hud-panel mt-card" style="text-align:center;"><div class="font-mono" style="font-weight:800;color:var(--hud-green);">' +
            esc(ttl) + '</div>' + (n && n.role ? '<div class="hud-stat-label" style="margin-top:4px;">' + esc(n.role) + '</div>' : '') + '</div>';
        }).join('') + '</div>');
        if (ev.edges) out += block(toList(ev.edges).map(function (e) {
          return '<div class="card-section font-mono" style="font-size:0.85rem;">' + esc(e.from || e.a || e[0]) +
            ' &rarr; ' + esc(e.to || e.b || e[1]) + '</div>';
        }).join(''));
        if (ev.events) out += section('EVENT LOG') + block(toList(ev.events).map(function (e) {
          var t = e.ts || e.time || e.date || '';
          var m = e.msg || e.description || e.desc || '';
          return '<div class="mt-row"><span class="mt-row-label font-mono">' + esc(t) + '</span>' +
            '<span class="mt-row-value">' + esc(m) + '</span></div>';
        }).join(''));
        return out;
      }
    };
  }

  function accountsEngine(label) {
    return {
      label: label,
      render: function (ev, cfg) {
        var out = '';
        if (ev.accounts) out += section('ACCOUNT RECORDS') + block(table(ev.accounts));
        if (ev.candidates) out += section('CANDIDATES') + block(chips(ev.candidates));
        if (ev.policy) out += section('POLICY') + block('<div class="card-section">' + esc(ev.policy) + '</div>');
        if (ev.categories) {
          out += section('CATEGORIES');
          // Flat list (["COMMON","REUSED",...]) or a map of category -> values.
          if (Array.isArray(ev.categories)) {
            out += block(chips(ev.categories));
          } else {
            Object.keys(ev.categories).forEach(function (cat) {
              out += block('<div class="mt-group"><div class="mt-group-title font-mono">' + esc(cat) + '</div>' +
                chips(ev.categories[cat]) + '</div>');
            });
          }
        }
        return out;
      }
    };
  }

  function emailEngine(label) {
    return {
      label: label,
      render: function (ev, cfg) {
        var out = '';
        if (ev.email) {
          var e = ev.email;
          out += block('<div class="card" style="background:var(--bg-base);padding:18px;">' +
            kv('From', e.from || e.sender || '') + kv('To', e.to || '') + kv('Subject', e.subject || '') +
            (e.date ? kv('Date', e.date) : '') +
            '<div style="margin-top:12px;border-top:1px solid var(--border);padding-top:12px;line-height:1.7;">' +
            esc(e.body || e.message || e.content || '') + '</div></div>');
        }
        if (ev.headers) out += section('MESSAGE HEADERS') + block(Object.keys(ev.headers).map(function (k) {
          return kv(k, ev.headers[k], true);
        }).join(''));
        if (ev.links) out += section('LINKS') + block(toList(ev.links).map(function (L) {
          return '<div class="mt-row"><span class="mt-row-value font-mono" style="color:var(--cyan);">' +
            esc(L.url || L.href || L) + '</span>' + (L.host ? '<span class="mt-row-label">HOST ' + esc(L.host) + '</span>' : '') +
            '</div>';
        }).join(''));
        return out;
      }
    };
  }

  function metaEngine(label) {
    return {
      label: label,
      render: function (ev, cfg) {
        var out = '';
        if (ev.fields) out += section('FILE FIELDS') + block(Object.keys(ev.fields).map(function (k) {
          return kv(k, ev.fields[k], true);
        }).join(''));
        if (ev.exif) out += section('EXIF DATA') + block(Object.keys(ev.exif).map(function (k) {
          return kv(k, ev.exif[k], true);
        }).join(''));
        if (ev.date) out += block(kv('Captured', ev.date, true));
        if (ev.gps) out += section('GPS POSITION') + block('<div class="card-terminal font-mono" style="font-size:0.85rem;">lat: ' +
          esc(ev.gps.lat) + '  lon: ' + esc(ev.gps.lon) + '</div>');
        if (ev.pins) out += section('LOCATION PINS') + block(toList(ev.pins).map(function (p) {
          return '<div class="card-section font-mono" style="font-size:0.85rem;">' + esc(p.name || p) +
            ' <span class="text-muted">' + (p.coords ? esc(p.coords) : '') + '</span></div>';
        }).join(''));
        if (ev.events) out += section('EVENT LOG') + block(toList(ev.events).map(function (e) {
          return '<div class="mt-row"><span class="mt-row-label font-mono">' + esc(e.time || e.ts || e.date || '') +
            '</span><span class="mt-row-value">' + esc(e.msg || e.event || e.description || '') + '</span></div>';
        }).join(''));
        return out;
      }
    };
  }

  function webEngine(label) {
    return {
      label: label,
      render: function (ev, cfg) {
        var out = '';
        if (ev.pages) out += section('SITE MAP') + block(chips(typeof ev.pages === 'object' ? Object.keys(ev.pages) : ev.pages));
        if (ev.html) out += section('HTML SNIPPET') + terminal(ev.html, 'html');
        if (ev.source) out += section('SOURCE') + terminal(ev.source, 'server.js');
        if (ev.robots) out += section('ROBOTS.TXT') + block('<div class="card-terminal" style="white-space:pre-wrap;font-size:0.85rem;">' +
          esc(typeof ev.robots === 'string' ? ev.robots : JSON.stringify(ev.robots, null, 2)) + '</div>');
        return out;
      }
    };
  }

  function hexEngine(label) {
    return {
      label: label,
      render: function (ev, cfg) {
        var out = '';
        var hex = typeof ev === 'string' ? { hex: ev } : ev;
        if (hex.hex) {
          var txt = typeof hex.hex === 'string' ? hex.hex : hex.hex.join(' ');
          out += section('HEX DUMP') + terminal(txt, 'file.bin');
        }
        if (cfg && Array.isArray(cfg.options)) out += section('SIGNATURES') + block(chips(cfg.options));
        return out;
      }
    };
  }

  function hashEngine(label) {
    return {
      label: label,
      render: function (ev, cfg) {
        var out = terminal(typeof ev === 'string' ? ev : JSON.stringify(ev, null, 2), 'hash_target');
        if (cfg && Array.isArray(cfg.options)) out += section('ALGORITHMS') + block(chips(cfg.options));
        return out;
      }
    };
  }

  // Caesar wheel with a live shift slider (ROT engines)
  function caesarEngine(label, cfgExtra) {
    return {
      label: label,
      render: function (ev, cfg) {
        var text = typeof ev === 'string' ? ev : '';
        var html = terminal(text, 'encoded_message');
        html += liveTools().caesarInput('mt-caesar');
        html += '<div class="card-terminal" id="mt-caesar-out" style="font-size:0.85rem;margin-top:12px;display:none;color:var(--hud-green);"></div>';
        if (cfgExtra && cfgExtra.length) html += section('TOOLS') + block(chips(cfgExtra));
        // wire the slider after injection
        setTimeout(function () {
          var s = document.getElementById('mt-caesar-shift');
          var v = document.getElementById('mt-caesar-shiftval');
          var o = document.getElementById('mt-caesar-out');
          if (!s) return;
          s.value = 0;
          function shift(text, n) {
            return text.replace(/[A-Za-z]/g, function (ch) {
              var base = ch <= 'Z' ? 65 : 97;
              return String.fromCharCode(((ch.charCodeAt(0) - base + n) % 26 + 26) % 26 + base);
            });
          }
          function tick() {
            var n = parseInt(s.value, 10) || 0;
            v.textContent = n;
            o.style.display = 'block';
            o.textContent = 'decoded[' + n + ']: ' + shift(text, n);
            if (n === 0) o.style.display = 'none';
          }
          s.addEventListener('input', tick);
          tick();
        }, 0);
        return html;
      }
    };
  }

  // Binary / octal / hex tile board -> live recogniser
  function binEngine(label, base) {
    return {
      label: label,
      render: function (ev, cfg) {
        var text = typeof ev === 'string' ? ev : '';
        var radix = base === 'octal' ? 8 : base === 'hex' ? 16 : 2;
        var html = '';
        if (base === 'octal') {
          html += section('OCTAL STREAM');
        } else if (base === 'hex') {
          html += section('HEX STREAM');
        } else {
          html += section('BINARY STREAM');
        }
        html += terminal(text, 'encoded_word');
        html += '<div class="card-terminal" id="mt-bin-out" style="font-size:0.85rem;margin-top:12px;display:none;color:var(--hud-green);"></div>';
        setTimeout(function () {
          var o = document.getElementById('mt-bin-out');
          if (!o) return;
          var raw = text.trim().split(/\s+/);
          var decoded = '';
          raw.forEach(function (tok) {
            if (!tok) return;
            if (/^[01]{7,8}$/.test(tok)) decoded += String.fromCharCode(parseInt(tok, 2));
            else if (/^[0-7]{3}$/.test(tok)) decoded += String.fromCharCode(parseInt(tok, 8));
            else if (/^[0-9a-fA-F]{2}$/.test(tok)) decoded += String.fromCharCode(parseInt(tok, 16));
            else decoded += tok + ' ';
          });
          o.style.display = 'block';
          o.textContent = 'decoded: ' + decoded;
        }, 0);
        return html;
      }
    };
  }

  function codeEngine(label) {
    return {
      label: label,
      render: function (ev, cfg) {
        var out = terminal(typeof ev === 'string' ? ev : JSON.stringify(ev, null, 2), 'pipeline_input');
        if (cfg && Array.isArray(cfg.tools)) out += section('TOOLKIT') + block(chips(cfg.tools));
        return out;
      }
    };
  }

  /* Shadow Hunt: preformatted evidence block. Every challenge ships its
   * evidence as text (a cipher, headers, logs, a sentence...). Optionally the
   * C04 challenge config carries the staff-portal link, and a solved
   * challenge carries the team's OWN flag for revisit display. */
  function shadowEngine(label) {
    return {
      label: label,
      render: function (ev, cfg) {
        var out = terminal(typeof ev === 'string' ? ev : JSON.stringify(ev, null, 2), 'evidence');
        if (cfg && cfg.artifact_url) {
          out += '<div style="margin-top:16px;">' +
            '<a class="hud-btn hud-btn-green btn-sm" style="text-decoration:none;" href="' +
            esc(cfg.artifact_url) + '" target="_blank" rel="noopener noreferrer">' +
            'OPEN STAFF PORTAL &#8599;</a></div>';
        }
        if (cfg && cfg.solved_flag) {
          out += '<div class="card" style="background:var(--success-bg);border-color:var(--success);' +
            'padding:16px 18px;margin-top:16px;">' +
            '<div class="font-overline text-success">FLAG RECORDED — SOLVED</div>' +
            '<div style="margin-top:8px;font-size:.95rem;color:var(--success);' +
            'word-break:break-all;" class="font-mono">' + esc(cfg.solved_flag) + '</div>' +
            '<div style="margin-top:6px;font-size:.78rem;color:var(--text-secondary);">' +
            'This challenge is complete. The flag above is your team\'s own ' +
            'variant — it is recorded on the server.</div></div>';
        }
        return out;
      }
    };
  }

  // ----------------------------------------------------------------- registry

  // Full 48-entry registry (12 domains x 4 variants).
  // NOTE: the two HTML-dense entries below use `var api` closure so each
  // engine's evidence + config is captured when rendered.

  var ENGINES = {
    // ---- Shadow Hunt (Round 1 rework): one flag question per challenge
    shadow_text: shadowEngine('Shadow Hunt'),
    // ---- binary, base-N decoding
    digital_lock: binEngine('Digital Lock', 'binary'),
    combination_safe: binEngine('Combination Safe', 'octal'),
    binary_tiles: binEngine('Binary Tiles', 'binary'),
    forensic_terminal: binEngine('Forensic Terminal', 'binary'),
    // ---- cipher chains / hex
    decode_machine: codeEngine('Decode Machine'),
    layer_breaker: codeEngine('Layer Breaker'),
    hex_lab: binEngine('Hex Lab', 'hex'),
    pipeline_builder: codeEngine('Pipeline Builder'),
    // ---- hashing
    hash_microscope: hashEngine('Hash Microscope'),
    hash_match_cards: hashEngine('Hash Match Cards'),
    evidence_terminal: hashEngine('Evidence Terminal'),
    verification_grid: hashEngine('Verification Grid'),
    // ---- file magic
    hex_microscope: hexEngine('Hex Microscope'),
    signature_match: hexEngine('Signature Match'),
    file_detective: hexEngine('File Detective'),
    signature_challenge: hexEngine('Signature Challenge'),
    // ---- metadata & osint
    document_scanner: metaEngine('Document Scanner'),
    timeline_scrubber: metaEngine('Timeline Scrubber'),
    camera_forensics: metaEngine('Camera Forensics'),
    location_pin_hunt: metaEngine('Location Pin Hunt'),
    evidence_board: cardsEngine('Evidence Board'),
    identity_matcher: listEngine('Identity Matcher'),
    domain_hunter: listEngine('Domain Hunter'),
    connection_web: listEngine('Connection Web'),
    // ---- password security
    risk_card_hunt: cardsEngine('Risk Card Hunt'),
    match_pair: accountsEngine('Match Pair'),
    drag_classify: accountsEngine('Drag & Classify'),
    security_audit: accountsEngine('Security Audit'),
    // ---- phishing
    inbox_investigation: emailEngine('Inbox Investigation'),
    header_detective: emailEngine('Header Detective'),
    link_inspector: emailEngine('Link Inspector'),
    intent_detective: cardsEngine('Intent Detective'),
    // ---- port scanning
    radar_scan: portEngine('Radar Scan'),
    service_match: portEngine('Service Match'),
    server_compare: portEngine('Server Compare'),
    service_radar: portEngine('Service Radar'),
    // ---- SQL injection
    login_escape: queryEngine('Login Escape'),
    query_puzzle: queryEngine('Query Puzzle'),
    live_query_builder: queryEngine('Live Query Builder'),
    debug_console: queryEngine('Debug Console'),
    // ---- web source recon
    source_treasure_hunt: webEngine('Source Treasure Hunt'),
    html_detective: webEngine('HTML Detective'),
    robots_puzzle: webEngine('Robots Puzzle'),
    source_search: webEngine('Source Search'),
    // ---- Caesar / ROT
    alphabet_wheel: caesarEngine('Alphabet Wheel'),
    caesar_slider: caesarEngine('Caesar Slider'),
    shift_lock: caesarEngine('Shift Lock'),
    shift_guess: caesarEngine('Shift Guess')
  };

  window.MTEngines = {
    get: function (key) {
      return ENGINES[key] || {
        label: key || 'Challenge',
        render: function (ev) {
          return terminal(typeof ev === 'string' ? ev : JSON.stringify(ev, null, 2), 'evidence');
        }
      };
    },
    registry: ENGINES
  };
})();