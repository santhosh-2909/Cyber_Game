/* MYSTERY TRACE · dashboard.js
 * Single-page participant controller for /participant/round/1.
 * Everything is driven by the server: session, timer, unlock order, grading.
 */
(function () {
  'use strict';

  var state = null;
  var _focusQ2 = false;
  var _sessionRetried = false;
  var _transientTries = 0;

  function isShadow() {
    return !!(state && state.session && state.session.shadow);
  }

  /* Bounded reload budget: a missing/erroring Round 1 payload must never put
   * the participant in an infinite reload loop on a page that has no answer
   * bar. After a few quick reloads the page settles into a readable card
   * that routes back to Round 1 / re-login instead. */
  var _reloadBudget = (function () {
    var key = 'mt-r1-reload';
    var now = Date.now();
    var n = parseInt(sessionStorage.getItem(key) || '0', 10) || 0;
    var last = parseInt(sessionStorage.getItem(key + '-t') || '0', 10) || 0;
    if (now - last > 8000) n = 0; // cooled down -> fresh budget
    n += 1;
    sessionStorage.setItem(key, String(n));
    sessionStorage.setItem(key + '-t', String(now));
    return n <= 3;
  })();

  /* Dead-end fallback: rendered when Round 1 data cannot be loaded at all.
   * Always surfaces a path back to the round (never a bare page with no
   * answer UI, never an endless reload). */
  function renderMissedRound(d) {
    var wrap = $('mt-hand');
    var panel = $('mt-panel');
    var bar = $('mt-answerbar');
    if (panel) panel.style.display = 'none';
    if (bar) bar.style.display = 'none';
    var detail = (d && d.error)
      ? '<br><span class="font-mono" style="color:var(--hud-red);">' +
        esc(d.error) + '</span>' : '';
    if (wrap) {
      wrap.innerHTML =
        '<div class="hud-panel" style="padding:24px;max-width:560px;margin:40px auto;">' +
          '<div class="font-overline text-warning">ROUND 1 UNAVAILABLE</div>' +
          '<p style="margin:10px 0 18px;color:var(--text-secondary);font-size:0.9rem;line-height:1.7;">' +
            'Your game session data is missing or the round could not be loaded.' +
            detail + '</p>' +
          '<div style="display:flex;gap:10px;flex-wrap:wrap;">' +
            '<button type="button" class="hud-btn hud-btn-green btn-sm" ' +
            'onclick="location.href=\'/participant/round/1\'">RETRY ROUND 1</button>' +
            '<a class="hud-btn hud-btn-ghost btn-sm" href="/start">LOG IN AGAIN</a>' +
          '</div></div>';
    }
    if (window.RoundGuard) window.RoundGuard.setActive(false);
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  var $ = function (id) { return document.getElementById(id); };

  // ---------------------------------------------------------------- transport

  /* Resilient fetch: Accepts JSON, retries once on network failures / 5xx /
   * server-declared transient busy errors, and never throws on a bad
   * response so a transient hiccup surfaces a RETRY UI instead of a dead
   * "NETWORK ERROR" box. Resolves {status, ok, d} where d is the JSON body
   * (or null when the server replied without JSON).
   */
  function api(url, opts, attemptsLeft) {
    attemptsLeft = (attemptsLeft == null) ? 2 : attemptsLeft;
    return fetch(url, opts)
      .then(function (r) {
        return r.json()
          .then(function (d) { return { status: r.status, ok: !!d, d: d }; })
          .catch(function () { return { status: r.status, ok: false, d: null }; });
      })
      .catch(function () { return { status: 0, ok: false, d: null }; })
      .then(function (res) {
        var transient = res.status === 0 || res.status >= 500 ||
          (res.d && res.d.retry === true);
        if (transient && attemptsLeft > 1) {
          return new Promise(function (resolve) {
            setTimeout(function () { resolve(api(url, opts, attemptsLeft - 1)); }, 700);
          });
        }
        return res;
      });
  }

  // ---------------------------------------------------------------- rendering

  function renderHand() {
    var wrap = $('mt-hand');
    if (!wrap) return;
    if (!state || !state.assignments) { wrap.innerHTML = ''; return; }
    var unlockedId = (state.unlocked || {}).id;
    var shadow = isShadow();
    wrap.innerHTML = state.assignments.map(function (a) {
      var cls = 'mt-tile';
      if (a.solved) cls += ' mt-tile-solved';
      else if (a.failed) cls += ' mt-tile-failed';
      if (a.id === unlockedId) cls += ' mt-tile-active';
      if (shadow) cls += ' mt-tile-clickable';
      // Shadow Hunt: every challenge is open (click to open any of them).
      var icon = a.solved ? '&#10003;'
               : a.failed ? '&#10007;'
               : (shadow ? '&#9654;'
                         : (a.id === unlockedId ? '&#9654;' : '&#128274;'));
      var footer;
      if (a.solved) {
        footer = '<div class="hud-badge hud-badge-green mt-tile-pts">+' + (a.points_awarded || a.points || 25) + ' pts</div>';
      } else if (a.failed) {
        footer = '<div class="hud-badge hud-badge-red mt-tile-pts">CLOSED</div>';
      } else if (shadow) {
        footer = '<div class="hud-badge hud-badge-green mt-tile-pts font-mono" title="Points for this challenge">' +
          esc(a.points || 25) + ' pts</div>' +
          (a.id === unlockedId
            ? '<div class="hud-badge hud-badge-amber mt-tile-pts font-mono">' +
              esc(a.attempts_used || 0) + ' att</div>'
            : '<div class="hud-stat-label mt-tile-lock" style="color:var(--hud-green, #4ade80);">OPEN' +
              (a.attempts_used ? ' &middot; ' + (a.attempts_used || 0) + ' att' : '') + '</div>');
      } else if (a.id === unlockedId) {
        footer = '<div class="hud-badge hud-badge-amber mt-tile-pts font-mono">' +
          esc((a.attempts_used || 0) + '/' + (a.attempts_limit || 3)) + ' tries</div>' +
          '<div class="mt-tile-strike" id="mt-active-strike">STRIKE --:--</div>';
      } else {
        footer = '<div class="hud-badge hud-badge-green mt-tile-pts font-mono" title="Points awarded for this case">' +
          esc(a.points || 25) + ' pts</div>' +
          '<div class="hud-stat-label mt-tile-lock">LOCKED</div>';
      }
      return '<div class="' + cls + '" data-id="' + a.id + '"' +
        (shadow ? ' tabindex="0" role="button" aria-label="Open ' + esc(a.title) + '"' : '') + '>' +
        '<div class="mt-tile-top font-mono">' +
          '<span class="mt-tile-num">' + a.sequence_number + '</span>' +
          '<span class="mt-tile-icon">' + icon + '</span>' +
        '</div>' +
        '<div class="font-mono mt-tile-code">' + esc(a.code) + '</div>' +
        '<div class="mt-tile-title">' + esc(a.title) + '</div>' +
        '<div class="hud-stat-label mt-tile-domain">' + esc(a.domain) + '</div>' +
        footer +
        '</div>';
    }).join('');
  }

  function renderUnlocked() {
    var u = state.unlocked;
    var panel = $('mt-panel');
    var complete = $('mt-complete');
    var bar = $('mt-answerbar');
    if (!u) {
      panel.style.display = 'none';
      if (bar) bar.style.display = 'none';
      if (state.session.finished || state.session.solved >= state.session.challenges_per_team) {
        complete.style.display = 'block';
        $('mt-complete-count').textContent = state.session.solved;
        $('mt-complete-score').textContent = state.session.score;
      } else {
        // Round is live and unsolved but the open challenge payload is
        // missing — surface a recovery card instead of a dead page with no
        // answer bar.
        renderMissedRound();
      }
      return;
    }
    panel.style.display = 'block';
    complete.style.display = 'none';
    if (bar) bar.style.display = 'block';

    var q2 = u.phase === 'q2';
    var shadow = isShadow();
    // Solved Shadow Hunt cards are view-only: evidence + recorded flag.
    // Exhausted (3 wrong flags) cards are view-only too: the challenge is
    // CLOSED, the team moves on to the next open card.
    var closedView = shadow && (u.solved || u.failed);

    // One question at a time: Q1 first, Q2 only after Q1 is solved.
    var q1Block = $('mt-q1-block');
    var q2Block = $('mt-q2-block');
    if (q1Block) q1Block.style.display = q2 ? 'none' : '';
    if (q2Block) q2Block.style.display = q2 ? '' : 'none';
    var row1 = $('mt-answer-row-1');
    var row2 = $('mt-answer-row-2');
    var hintBtn = $('mt-hint-btn');
    var submitBtn = $('mt-submit');
    if (closedView) {
      if (row1) row1.style.display = 'none';
      if (row2) row2.style.display = 'none';
      if (hintBtn) hintBtn.style.display = 'none';
      if (submitBtn) submitBtn.style.display = 'none';
      $('mt-answer').disabled = true;
      $('mt-answer-2').disabled = true;
    } else {
      if (row1) row1.style.display = q2 ? 'none' : '';
      if (row2) row2.style.display = q2 ? '' : 'none';
      if (hintBtn) hintBtn.style.display = '';
      if (submitBtn) submitBtn.style.display = '';
      $('mt-answer').disabled = false;
      $('mt-answer-2').disabled = false;
    }

    $('mt-code').textContent = u.code;
    $('mt-domain').textContent = u.domain;
    var engine = window.MTEngines.get(u.game_type);
    var engine2 = window.MTEngines.get(u.game_type2);
    $('mt-engine').textContent = q2 ? engine2.label : engine.label;
    $('mt-title').textContent = u.title;
    $('mt-points').textContent = u.points + ' PTS';
    $('mt-question').textContent = u.question;

    var stage = $('mt-evidence');
    stage.innerHTML = '';
    if (!q2) stage.appendChild(renderEvidence(u, engine));

    $('mt-question-2').textContent = u.question2;
    var stage2 = $('mt-evidence-2');
    stage2.innerHTML = '';
    if (q2) stage2.appendChild(renderEvidence(u, engine2, true));

    $('mt-answer').value = '';
    $('mt-answer').disabled = false;
    $('mt-answer').classList.remove('mt-shake');
    $('mt-answer-2').value = '';
    $('mt-answer-2').disabled = false;
    $('mt-answer-2').classList.remove('mt-shake');

    renderQuizOptions(u);
    $('mt-answer').disabled = !shadow || (u.solved || u.failed);
    $('mt-answer').style.display = shadow && u.options && u.options.length ? 'none' : '';
    $('mt-submit').disabled = false;
    $('mt-hint').style.display = 'none';
    $('mt-result').innerHTML = '';
    $('mt-flag-chip').style.display = 'none';
    closePop();

    var ab = $('mt-attempts');
    if (ab) {
      if (shadow) {
        if (u.solved) {
          ab.textContent = 'SOLVED';
          ab.className = 'hud-badge hud-badge-green font-mono';
        } else if (u.failed) {
          ab.textContent = 'OUT OF TRIES (' + (u.attempts_used || 0) + '/' +
            (u.attempts_limit || 3) + ')';
          ab.className = 'hud-badge hud-badge-red font-mono';
        } else {
          ab.textContent = 'TRIES ' + (u.attempts_used || 0) + '/' +
            (u.attempts_limit || 3);
          ab.className = 'hud-badge hud-badge-amber font-mono';
        }
      } else {
        ab.textContent = 'TRIES ' + (u.attempts_used || 0) + '/' + (u.attempts_limit || 3);
        ab.className = 'hud-badge hud-badge-amber font-mono';
        if (u.failed) {
          ab.className = 'hud-badge hud-badge-red font-mono';
        }
      }
      ab.setAttribute('style', 'margin-left:10px;display:inline;');
    }

    // Shadow Hunt has no time strike: hide the bonus chip.
    var strikeChip = $('mt-strike');
    if (strikeChip) strikeChip.style.display = shadow ? 'none' : 'inline';

    // After a Q1 solve, hand focus straight to the Q2 input.
    if (q2 && _focusQ2) {
      _focusQ2 = false;
      setTimeout(function () {
        var a2 = $('mt-answer-2');
        if (a2 && !a2.disabled) a2.focus();
      }, 60);
    }
  }

  function renderEvidence(u, engine, second) {
    var wrap = document.createElement('div');
    try {
      wrap.innerHTML = engine.render(
        second ? u.evidence2 : u.evidence,
        second ? (u.config2 || {}) : (u.config || {}));
    } catch (e) {
      // An evidence renderer must never take the page down: show a readable
      // fallback (the answer bar stays usable) instead of crashing the controller.
      console.error('[MT render] ' + (engine && engine.label) + ' failed:', e);
      wrap.innerHTML = '<div class="hud-panel mt-card">' +
        '<div class="font-overline text-muted">EVIDENCE RENDER</div>' +
        '<div class="mt-row"><span class="mt-row-label">STATUS</span>' +
        '<span class="mt-row-value" style="color:var(--hud-red);">unavailable (renderer error)</span></div>' +
        '</div>';
    }
    return wrap;
  }

  /* Shadow Hunt quiz: the challenge ships a radio list of candidate recovery
   * results (bare inner tokens). Picking one writes the bare inner into the
   * hidden flag input, so the existing submit()/grader path is reused as-is. */
  function renderQuizOptions(u) {
    var box = $('mt-options');
    if (!box) return;
    box.innerHTML = '';
    var opts = (u && u.options) || [];
    var inp = $('mt-answer');
    if (!opts.length) {
      box.style.display = 'none';
      if (inp) inp.style.display = '';
      return;
    }
    box.style.display = '';
    if (inp) inp.style.display = 'none';
    opts.forEach(function (inner, i) {
      var label = document.createElement('label');
      label.className = 'mt-quiz-opt';
      var radio = document.createElement('input');
      radio.type = 'radio';
      radio.name = 'mt-options';
      radio.value = inner;
      radio.dataset.idx = i;
      radio.addEventListener('change', function () {
        if (inp) inp.value = inner哪有;
      });
      var span = document.createElement('span');
      span.className = 'mt-quiz-opt-inner font-mono';
      span.textContent = inner;
      label.appendChild(radio);
      label.appendChild(span);
      box.appendChild(label);
    });
  }

  function renderHud() {
    var s = state.session;
    var hs = $('hud-solved');
    if (hs) hs.textContent = s.solved + '/' + (s.challenges_per_team || 0);
    var hsc = $('hud-score');
    if (hsc) hsc.textContent = s.score || 0;
  }

  /* Screen watchdog: armed while the round is live (not finished, not fully
   * solved), disarmed the moment it ends so post-round navigation is free. */
  function updateGuard() {
    if (!window.RoundGuard) return;
    var s = state.session;
    var finished = !s || !!s.finished ||
      (s.solved || 0) >= (s.challenges_per_team || s.solved || 0);
    window.RoundGuard.setActive(!finished);
  }

  // ---------------------------------------------------------------- timer

  function startTimer() {
    var el = $('mt-timer');
    if (!el) return;
    var endMs = Date.now() + (state.session.remaining_ms || 0);
    var warned = false;
    function pad(n) { return String(n).padStart(2, '0'); }
    function tick() {
      var rem = endMs - Date.now();
      if (rem <= 0) {
        el.textContent = '00:00';
        el.style.color = 'var(--state-danger, #EF4444)';
        if (!warned) { warned = true; setTimeout(function () { load(); }, 800); }
        return;
      }
      var mins = Math.floor(rem / 60000), secs = Math.floor((rem % 60000) / 1000);
      el.textContent = pad(mins) + ':' + pad(secs);
      if (rem <= 5 * 60000) el.style.color = 'var(--state-warning, #F59E0B)';
      if (rem <= 60000) el.style.color = 'var(--state-danger, #EF4444)';
    }
    tick();
    setInterval(tick, 1000);
  }

  // ------------------------------------------------------------ time strike

  var strikeTimer = null;

  /* Live preview of the TIME STRIKE on the unlocked case: the bonus the team
   * would earn if it solved right now, plus the remaining strike window. The
   * server re-computes the authoritative number at grading time. Each full
   * 5 seconds saved from the 30s window earns +2 bonus marks. */
  function startStrike() {
    if (strikeTimer) { clearInterval(strikeTimer); strikeTimer = null; }
    var chip = $('mt-strike');
    var badge = $('mt-active-strike');
    if (!state || !state.unlocked || isShadow()) {
      if (chip) chip.style.display = 'none';
      if (badge) badge.style.display = 'none';
      return;
    }
    chip.style.display = 'inline';
    var windowMs = state.unlocked.strike_window_ms || 30000;
    var deadline = (state.unlocked.started_at || 0) + windowMs;
    function pad(n) { return String(n).padStart(2, '0'); }
    function paint() {
      var rem = deadline - Date.now();
      var remaining_s = Math.max(0, Math.ceil(rem / 1000));
      var bonus = Math.floor(remaining_s / 5) * 2;
      if (rem <= 0) {
        if (chip) chip.textContent = '+0 marks · expired';
        if (badge) { badge.textContent = 'STRIKE 00:00'; badge.className = 'mt-tile-strike done'; }
        return;
      }
      var mm = pad(Math.floor(rem / 60000)), ss = pad(Math.floor((rem % 60000) / 1000));
      if (chip) chip.textContent = '+ ' + bonus + ' marks @ ' + mm + ':' + ss;
      if (badge) {
        badge.textContent = 'STRIKE ' + mm + ':' + ss;
        badge.className = rem <= 60000 ? 'mt-tile-strike hot' : 'mt-tile-strike';
      }
    }
    paint();
    strikeTimer = setInterval(paint, 1000);
  }

  // ---------------------------------------------------------------- actions

  function flash(el, cls, html) {
    el.className = cls;
    el.textContent = '';
    el.innerHTML = html;
  }

  /* Pressed/kicked effect: the button visibly "fires" on every click. */
  function kick(el) {
    if (!el) return;
    el.classList.remove('mt-kick');
    void el.offsetWidth;
    el.classList.add('mt-kick');
  }

  /* TRY AGAIN / validation dialog. kind: '' (danger) | 'warn' (amber). */
  function pop(title, text, kind) {
    var backdrop = $('mt-pop-backdrop');
    if (!backdrop) return;
    backdrop.className = kind === 'warn' ? 'show warn' : 'show';
    backdrop.setAttribute('aria-hidden', 'false');
    $('mt-pop-title').textContent = title;
    $('mt-pop-text').textContent = text;
    // replay the pop-in animation on every open
    var card = backdrop.firstElementChild;
    card.style.animation = 'none';
    void card.offsetWidth;
    card.style.animation = '';
    var tryBtn = $('mt-pop-try');
    if (tryBtn) setTimeout(function () { tryBtn.focus(); }, 60);
  }

  function closePop() {
    var backdrop = $('mt-pop-backdrop');
    if (!backdrop) return;
    backdrop.className = '';
    backdrop.setAttribute('aria-hidden', 'true');
  }

  function shakeEmpty(input) {
    input.classList.remove('mt-shake');
    void input.offsetWidth;
    input.classList.add('mt-shake');
  }

  /* Shadow Hunt: click an open tile to open that challenge (any order). The
   * server still guards the session/timer; this only drives client view. */
  function openChallenge(id) {
    if (!isShadow()) return;
    if (state && state.unlocked && state.unlocked.id === id) return;
    api('/api/participant/challenges/' + id, {})
      .then(function (res) {
        var d = res.d;
        if (!d || d.ok === false) { load(); return; }
        state.unlocked = d;
        _focusQ2 = false;
        renderHand();
        renderUnlocked();
        startStrike();
      });
  }

  function load() {
    api('/api/participant/round/1', {})
      .then(function (res) {
        var d = res.d;
        if (res.status === 503 || (d && d.retry === true)) {
          // Transient (SQLite busy under multi-user load) — retried once by
          // api(); if still busy, wait a beat and load again rather than dead.
          // Bounded: after a few tries a readable fallback (leading back to
          // Round 1) replaces the retry loop so it can never spin forever.
          _transientTries += 1;
          if (_reloadBudget && _transientTries <= 3) {
            setTimeout(function () { load(); }, 1200);
          } else { renderMissedRound(d); }
          return;
        }
        if (!d || !d.ok) {
          // Missing/erroring session data: never loop forever on a page with
          // no answer bar — bounded reloads first, then a fallback that
          // routes back to Round 1 / re-login.
          if (_reloadBudget) { window.location.reload(); }
          else { renderMissedRound(d); }
          return;
        }
        state = d;
        _sessionRetried = false;
        _transientTries = 0;
        try {
          renderHand();
          renderUnlocked();
          renderHud();
          startStrike();
          updateGuard();
        } catch (e) {
          // Render errors must NEVER trigger an infinite reload loop. Surface the
          // problem and keep the page (and answer bar) alive for the participant.
          console.error('[MT render] controller error:', e);
        }
      })
      .catch(function (e) {
        // Network/render failure: surface the Round 1 fallback instead of an
        // unbounded reload that leaves the participant without an answer bar.
        console.error('[MT] load failed:', e);
        renderMissedRound();
      });
  }

  function submit() {
    if (!state || !state.unlocked) return;
    var q2 = state.unlocked.phase === 'q2';
    var input = q2 ? $('mt-answer-2') : $('mt-answer');
    var answer = (input.value || '').trim();
    var btn = $('mt-submit');
    var result = $('mt-result');
    if (!answer) {
      // Empty / null / whitespace answers are blocked before any request.
      input.focus();
      shakeEmpty(input);
      pop('ANSWER REQUIRED', 'Enter the value for the open question, then run the check.', 'warn');
      return;
    }

    btn.disabled = true;
    result.innerHTML = '<span class="text-muted font-mono">CHECKING...</span>';

    api('/api/participant/challenges/' + state.unlocked.id + '/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answer: answer })
    })
      .then(function (res) {
        var d = res.d || {};
        if (d.retry === true || res.status === 503) {
          // Writer contention under concurrent teams — give the participant a
          // one-tap RETRY instead of a dead error card.
          result.innerHTML =
            '<div class="card" style="background:var(--warning-bg);border-color:var(--warning);padding:14px 16px;">' +
              '<div class="font-overline text-warning">NETWORK BUSY</div>' +
              '<p style="margin:6px 0 0;color:var(--text-secondary);font-size:0.85rem;">' +
                'The grading server is momentarily overloaded. ' +
                '<button type="button" class="btn btn-warning btn-sm" onclick="MT.submit()">RETRY</button>' +
              '</p></div>';
          btn.disabled = false;
          return;
        }
        if (!d || d.ok === false) {
          if (d && d.error === 'session_not_found') {
            // Serverless instances keep per-instance SQLite: a submit can land
            // on an instance that never saw our session row. Re-run the
            // summary (it recreates a fresh Round 1 session if missing) once;
            // if that still fails, tell the participant to log in again.
            if (!_sessionRetried) {
              _sessionRetried = true;
              load();
              return;
            }
            result.innerHTML =
              '<div class="card" style="background:var(--warning-bg);border-color:var(--warning);padding:14px 16px;">' +
                '<div class="font-overline text-warning">SESSION NOT FOUND</div>' +
                '<p style="margin:6px 0 0;color:var(--text-secondary);font-size:0.85rem;">' +
                  'Your game session is not on this server node. ' +
                  '<a class="btn btn-warning btn-sm" href="/start">LOG IN AGAIN</a>' +
                '</p></div>';
          } else if (d && d.error === 'locked') { load(); return; }
          else if (d && d.error === 'session_ended') { load(); return; }
          else if (d && d.error === 'empty_answer') {
            pop('ANSWER REQUIRED', 'The answer field cannot be empty. Enter a value and try again.', 'warn');
          } else if (d && d.error === 'attempts_exhausted') {
            load(); return;
          } else {
            result.innerHTML = '<span class="text-muted font-mono">' + esc((d && d.error) || 'Request failed.') + '</span>';
          }
          btn.disabled = false;
          input.focus();
          return;
        }
        if (d.accepted && d.flag) {
          closePop();
          var winLine = isShadow()
            ? '+' + d.points + ' marks = <strong style="color:var(--success);">' +
              d.points_total + ' pts</strong>. Flag recorded — pick any challenge to continue.'
            : '+' + d.points +
              ' marks +<span style="color:var(--accent-signal);font-weight:700;">' + d.strike +
              ' time bonus</span> = <strong style="color:var(--success);">' + d.points_total +
              ' pts</strong>. Advances to the next challenge.';
          result.innerHTML =
            '<div class="card" style="background:var(--success-bg);border-color:var(--success);padding:18px 20px;">' +
              '<div class="font-overline text-success">CORRECT — FLAG CAPTURED</div>' +
              '<div style="margin-top:10px;display:flex;gap:10px;flex-wrap:wrap;align-items:center;">' +
                '<span class="font-mono" style="font-size:1rem;color:var(--success);word-break:break-all;" id="js-flag">' +
                  esc(d.flag) + '</span>' +
                '<button type="button" class="btn btn-success btn-sm" onclick="MT.copyFlag()">COPY FLAG</button>' +
              '</div>' +
              '<p style="margin:10px 0 0;font-size:0.85rem;color:var(--text-secondary);">' + winLine + '</p></div>';
          setTimeout(function () { load(); }, 900);
        } else if (d.accepted && d.q1_done && !d.flag) {
          // Question 1 correct -> reveal Question 2.
          closePop();
          _focusQ2 = true;
          result.innerHTML =
            '<div class="card" style="background:var(--success-bg);border-color:var(--success);padding:14px 16px;">' +
              '<div class="font-overline text-success">QUESTION 1 SOLVED</div>' +
              '<p style="margin:6px 0 0;color:var(--text-secondary);font-size:0.85rem;">' +
              esc(d.message) + '</p></div>';
          setTimeout(function () { load(); }, 900);
        } else if (d.exhausted) {
          closePop();
          result.innerHTML =
            '<div class="card" style="background:var(--danger-bg);border-color:var(--danger);padding:14px 16px;">' +
              '<div class="font-overline text-danger">ATTEMPTS EXHAUSTED (' + d.attempts_used + '/' + d.attempts_limit + ')</div>' +
              '<p style="margin:6px 0 0;color:var(--text-secondary);font-size:0.85rem;">' +
              esc(d.message) + '</p></div>';
          btn.disabled = true;
          input.disabled = true;
          setTimeout(function () { load(); }, 1300);
        } else if (d.already_solved) {
          closePop();
          result.innerHTML = '<div class="card" style="background:var(--accent-glow);border-color:var(--accent-border);padding:14px 16px;">' +
            '<div class="font-overline" style="color:var(--accent);">ALREADY SOLVED</div><p style="margin:6px 0 0;color:var(--text-secondary);font-size:0.85rem;">' +
            esc(d.message) + '</p></div>';
          setTimeout(function () { load(); }, 1200);
        } else {
          // Wrong answer -> pop a TRY AGAIN dialog (answers are compared
          // case-insensitively server-side).
          var wrongNote = isShadow()
            ? 'Wrong flag — ' + d.attempts_used + ' of ' +
              (d.attempts_limit || 3) + ' tries used, no points lost. '
            : 'Your answer did not unlock this case. ' +
              d.attempts_used + ' of ' + d.attempts_limit + ' attempts used — ';
          pop('INCORRECT', wrongNote + 're-verify the evidence and try again.', '');
          btn.disabled = false;
          var ab = $('mt-attempts');
          if (ab && typeof d.attempts_used === 'number') {
            ab.textContent = 'TRIES ' + d.attempts_used + '/' +
              (d.attempts_limit || 3);
            if (isShadow() && d.attempts_used >= (d.attempts_limit || 3)) {
              ab.className = 'hud-badge hud-badge-red font-mono';
            } else {
              ab.className = 'hud-badge hud-badge-amber font-mono';
            }
          }
        }
      })
      .catch(function () {
        result.innerHTML =
          '<div class="card" style="background:var(--warning-bg);border-color:var(--warning);padding:14px 16px;">' +
            '<div class="font-overline text-warning">NETWORK ERROR</div>' +
            '<p style="margin:6px 0 0;color:var(--text-secondary);font-size:0.85rem;">' +
              'Could not reach the grading server. ' +
              '<button type="button" class="btn btn-warning btn-sm" onclick="MT.submit()">RETRY</button>' +
            '</p></div>';
        btn.disabled = false;
      });
  }

  function hint() {
    if (!state || !state.unlocked) return;
    var box = $('mt-hint');
    var btn = $('mt-hint-btn');
    btn.disabled = true;
    api('/api/participant/challenges/' + state.unlocked.id + '/hint', {})
      .then(function (res) {
        var d = res.d || {};
        box.style.display = 'block';
        box.innerHTML = '<div class="card" style="background:var(--warning-bg);border-color:var(--warning);padding:14px 16px;">' +
          '<div class="font-overline text-warning">HINT</div><p style="margin:6px 0 0;font-size:0.9rem;color:var(--text-secondary);">' +
          esc((d && d.hint) || ((d && d.error) ? 'Hint service busy — try again.' : 'No hint available.')) +
          '</p></div>';
      })
      .catch(function () { box.style.display = 'block'; box.textContent = 'Hint unavailable.'; })
      .finally(function () { btn.disabled = false; });
  }

  // -------------------------------------------------------------------- boot

  /* Keep the answer bar above the on-screen keyboard. When a phone/tablet
   * keyboard opens, the visual viewport shrinks (innerHeight stays); this
   * re-pins bottom so the bar is never covered while entering an answer. */
  function pinBar() {
    var bar = $('mt-answerbar');
    if (!bar) return;
    var vv = window.visualViewport;
    if (!vv || typeof vv.height === 'undefined') return;
    var gap = window.innerHeight - (vv.height + vv.offsetTop);
    bar.style.bottom = (gap > 0 ? gap : 0) + 'px';
  }

  function boot() {
    var sub = $('mt-submit');
    var ans = $('mt-answer');
    var ans2 = $('mt-answer-2');
    if (sub) {
      sub.addEventListener('click', function () { kick(sub); submit(); });
      ans.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !sub.disabled) { kick(sub); submit(); } });
      if (ans2) ans2.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !sub.disabled) { kick(sub); submit(); } });
    }
    var hintBtn = $('mt-hint-btn');
    if (hintBtn) hintBtn.addEventListener('click', function () { kick(hintBtn); hint(); });

    // Shadow Hunt: click / keyboard-open any open tile.
    var hand = $('mt-hand');
    if (hand) {
      hand.addEventListener('click', function (e) {
        var t = e.target && e.target.closest ? e.target.closest('.mt-tile') : null;
        if (!t) return;
        var id = parseInt(t.getAttribute('data-id'), 10);
        if (id > 0) openChallenge(id);
      });
      hand.addEventListener('keydown', function (e) {
        var t = e.target && e.target.closest ? e.target.closest('.mt-tile') : null;
        if (!t) return;
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          var id = parseInt(t.getAttribute('data-id'), 10);
          if (id > 0) openChallenge(id);
        }
      });
    }

    var popTry = $('mt-pop-try');
    if (popTry) {
      popTry.addEventListener('click', function () {
        kick(popTry);
        closePop();
        var ans2 = $('mt-answer');
        if (ans2 && !ans2.disabled) ans2.focus();
      });
    }
    var backdrop = $('mt-pop-backdrop');
    if (backdrop) {
      backdrop.addEventListener('click', function (e) {
        if (e.target === backdrop) closePop();
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && backdrop.classList.contains('show')) closePop();
      });
    }

    load();
    if (window.RoundGuard) {
      var completeEl = $('mt-complete');
      var initialDone = !!(completeEl && completeEl.style.display === 'block');
      window.RoundGuard.setActive(!initialDone);
    }
    setTimeout(startTimer, 100);
    pinBar();
    var vv = window.visualViewport;
    if (vv && typeof vv.addEventListener === 'function') {
      vv.addEventListener('resize', pinBar);
      vv.addEventListener('scroll', pinBar);
    }
    window.addEventListener('scroll', pinBar, true);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();

/* Public helper used by the flag-copy button (engines.js + template share it). */
window.MT = window.MT || {};
window.MT.submit = function () { submit(); };
window.MT.hint = function () { hint(); };
window.MT.copyFlag = function () {
  var f = document.getElementById('js-flag');
  if (!f) return;
  var copy = function (txt) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(txt).then(function () { return true; });
    }
    var t = document.createElement('textarea');
    t.value = txt;
    document.body.appendChild(t); t.select();
    try { document.execCommand('copy'); } catch (e) {}
    document.body.removeChild(t);
    return Promise.resolve(true);
  };
  copy(f.textContent.trim()).then(function () {
    var msg = document.querySelector('.text-success.font-mono');
    if (!msg) return;
    msg.textContent = 'FLAG COPIED';
    setTimeout(function () { msg.textContent = ''; }, 1500);
  });
};