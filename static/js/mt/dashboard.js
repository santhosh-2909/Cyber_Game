/* MYSTERY TRACE · dashboard.js
 * Single-page participant controller for /participant/round/1.
 * Everything is driven by the server: session, timer, unlock order, grading.
 */
(function () {
  'use strict';

  var state = null;
  var _focusQ2 = false;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  var $ = function (id) { return document.getElementById(id); };

  // ---------------------------------------------------------------- rendering

  function renderHand() {
    var wrap = $('mt-hand');
    if (!wrap) return;
    if (!state || !state.assignments) { wrap.innerHTML = ''; return; }
    var unlockedId = (state.unlocked || {}).id;
    wrap.innerHTML = state.assignments.map(function (a) {
      var cls = 'mt-tile';
      if (a.solved) cls += ' mt-tile-solved';
      else if (a.failed) cls += ' mt-tile-failed';
      if (a.id === unlockedId) cls += ' mt-tile-active';
      var icon = a.solved ? '&#10003;'
               : a.failed ? '&#10007;'
               : (a.id === unlockedId ? '&#9654;' : '&#128274;');
      var footer;
      if (a.solved) {
        footer = '<div class="hud-badge hud-badge-green mt-tile-pts">+' + (a.points_awarded || 25) + ' pts</div>';
      } else if (a.failed) {
        footer = '<div class="hud-badge hud-badge-red mt-tile-pts">CLOSED</div>';
      } else if (a.id === unlockedId) {
        footer = '<div class="hud-badge hud-badge-amber mt-tile-pts font-mono">' +
          esc((a.attempts_used || 0) + '/' + (a.attempts_limit || 3)) + ' tries</div>' +
          '<div class="mt-tile-strike" id="mt-active-strike">STRIKE --:--</div>';
      } else {
        footer = '<div class="hud-badge hud-badge-green mt-tile-pts font-mono" title="Points awarded for this case">' +
          esc(a.points || 25) + ' pts</div>' +
          '<div class="hud-stat-label mt-tile-lock">LOCKED</div>';
      }
      return '<div class="' + cls + '" data-id="' + a.id + '">' +
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
      }
      return;
    }
    panel.style.display = 'block';
    complete.style.display = 'none';
    if (bar) bar.style.display = 'block';

    var q2 = u.phase === 'q2';

    // One question at a time: Q1 first, Q2 only after Q1 is solved.
    var q1Block = $('mt-q1-block');
    var q2Block = $('mt-q2-block');
    if (q1Block) q1Block.style.display = q2 ? 'none' : '';
    if (q2Block) q2Block.style.display = q2 ? '' : 'none';
    var row1 = $('mt-answer-row-1');
    var row2 = $('mt-answer-row-2');
    if (row1) row1.style.display = q2 ? 'none' : '';
    if (row2) row2.style.display = q2 ? '' : 'none';

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
    $('mt-submit').disabled = false;
    $('mt-hint').style.display = 'none';
    $('mt-result').innerHTML = '';
    $('mt-flag-chip').style.display = 'none';
    closePop();

    var ab = $('mt-attempts');
    if (ab) {
      ab.style.display = 'inline';
      ab.textContent = 'TRIES ' + (u.attempts_used || 0) + '/' + (u.attempts_limit || 3);
      ab.className = 'hud-badge hud-badge-amber font-mono';
      ab.setAttribute('style', 'margin-left:10px;display:inline;');
      if (u.failed) {
        ab.className = 'hud-badge hud-badge-red font-mono';
        ab.setAttribute('style', 'margin-left:10px;display:inline;');
      }
    }

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

  function renderHud() {
    var s = state.session;
    var hs = $('hud-solved');
    if (hs) hs.textContent = s.solved + '/' + (s.challenges_per_team || 0);
    var hsc = $('hud-score');
    if (hsc) hsc.textContent = s.score || 0;
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
    if (!state || !state.unlocked) {
      if (chip) chip.style.display = 'none';
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

  function load() {
    fetch('/api/participant/round/1', { headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.ok) { window.location.reload(); return; }
        state = d;
        try {
          renderHand();
          renderUnlocked();
          renderHud();
          startStrike();
        } catch (e) {
          // Render errors must NEVER trigger an infinite reload loop. Surface the
          // problem and keep the page (and answer bar) alive for the participant.
          console.error('[MT render] controller error:', e);
        }
      })
      .catch(function (e) {
        if (window.MT_RELOAD_GUARD) { console.error('[MT] reload guard: not reloading after', e); return; }
        window.location.reload();
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

    fetch('/api/participant/challenges/' + state.unlocked.id + '/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answer: answer })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || d.ok === false) {
          if (d && d.error === 'locked') { load(); return; }
          if (d && d.error === 'session_ended') { load(); return; }
          if (d && d.error === 'empty_answer') {
            pop('ANSWER REQUIRED', 'The answer field cannot be empty. Enter a value and try again.', 'warn');
          } else {
            result.innerHTML = '<span class="text-muted font-mono">' + esc((d && d.error) || 'Request failed.') + '</span>';
          }
          btn.disabled = false;
          input.focus();
          return;
        }
        if (d.accepted && d.flag) {
          closePop();
          result.innerHTML =
            '<div class="card" style="background:var(--success-bg);border-color:var(--success);padding:18px 20px;">' +
              '<div class="font-overline text-success">CORRECT — FLAG CAPTURED</div>' +
              '<div style="margin-top:10px;display:flex;gap:10px;flex-wrap:wrap;align-items:center;">' +
                '<span class="font-mono" style="font-size:1rem;color:var(--success);word-break:break-all;" id="js-flag">' +
                  esc(d.flag) + '</span>' +
                '<button type="button" class="btn btn-success btn-sm" onclick="MT.copyFlag()">COPY FLAG</button>' +
              '</div>' +
              '<p style="margin:10px 0 0;font-size:0.85rem;color:var(--text-secondary);">+' + d.points +
              ' marks +<span style="color:var(--accent-signal);font-weight:700;">' + d.strike +
              ' time bonus</span> = <strong style="color:var(--success);">' + d.points_total +
              ' pts</strong>. Advances to the next challenge.</p></div>';
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
          pop('INCORRECT',
              'Your answer did not unlock this case. ' +
              d.attempts_used + ' of ' + d.attempts_limit + ' attempts used — ' +
              're-verify the evidence and try again.',
              '');
          btn.disabled = false;
          var ab = $('mt-attempts');
          if (ab && typeof d.attempts_used === 'number') {
            ab.textContent = 'TRIES ' + d.attempts_used + '/' + d.attempts_limit;
          }
        }
      })
      .catch(function () {
        result.innerHTML = '<span class="text-danger font-mono">NETWORK ERROR</span>';
        btn.disabled = false;
      });
  }

  function hint() {
    if (!state || !state.unlocked) return;
    var box = $('mt-hint');
    var btn = $('mt-hint-btn');
    btn.disabled = true;
    fetch('/api/participant/challenges/' + state.unlocked.id + '/hint')
      .then(function (r) { return r.json(); })
      .then(function (d) {
        box.style.display = 'block';
        box.innerHTML = '<div class="card" style="background:var(--warning-bg);border-color:var(--warning);padding:14px 16px;">' +
          '<div class="font-overline text-warning">HINT</div><p style="margin:6px 0 0;font-size:0.9rem;color:var(--text-secondary);">' +
          esc((d && d.hint) || 'No hint available.') + '</p></div>';
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