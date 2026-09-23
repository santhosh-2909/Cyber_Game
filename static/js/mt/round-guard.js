/* MYSTERY TRACE · round-guard.js
 * Screen watchdog for the ACTIVE Round 1 game (mt_round).
 *
 * While armed it:
 *   1. Flags tab switches / app switches / window minimize
 *      (visibilitychange -> document.hidden) with a blocking overlay and a
 *      running violation counter.
 *   2. Warns before the participant leaves the round screen — Home, Dashboard,
 *      Rules, Leaderboard, Logout, or any other in-app link — via a confirm
 *      overlay (return inside the window is the default).
 *   3. Blocks closing / refreshing the tab with the native beforeunload
 *      dialog while the round is live.
 *
 * The guard is disarmed by dashboard.js as soon as the session is finished
 * (all challenges solved or time expired), so post-round navigation is free.
 */
(function () {
  'use strict';

  var armed = false;
  var allowLeave = false;
  var violations = 0;
  var shield = null;
  var shieldTitle = null;
  var shieldText = null;
  var shieldVio = null;
  var stayBtn = null;
  var leaveBtn = null;
  var pendingHref = null;
  var roundFocusTarget = null;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function build() {
    if (shield) return;
    shield = document.createElement('div');
    shield.id = 'mt-shield';
    shield.setAttribute('role', 'alertdialog');
    shield.setAttribute('aria-modal', 'true');
    shield.setAttribute('aria-labelledby', 'mt-shield-title');
    shield.style.cssText =
      'position:fixed;inset:0;z-index:100000;display:none;align-items:center;justify-content:center;' +
      'background:rgba(4,8,16,0.88);backdrop-filter:blur(7px);-webkit-backdrop-filter:blur(7px);';
    shield.innerHTML =
      '<div style="max-width:540px;width:calc(100% - 48px);background:var(--bg-surface-1,#0B111B);' +
        'border:1px solid var(--state-danger,#EF4444);border-radius:16px;padding:32px 30px 26px;' +
        'box-shadow:0 0 0 1px rgba(239,68,68,.25),0 24px 90px rgba(0,0,0,.65);text-align:left;">' +
        '<div style="display:flex;align-items:center;gap:12px;margin-bottom:18px;">' +
          '<span style="width:12px;height:12px;border-radius:50%;background:var(--state-danger,#EF4444);' +
                 'box-shadow:0 0 16px var(--state-danger,#EF4444);flex:none;"></span>' +
          '<span class="font-mono" style="font-size:12px;letter-spacing:.20em;color:var(--state-danger,#EF4444);font-weight:700;">' +
            'SCREEN WATCHDOG</span>' +
          '<span id="mt-shield-vio" class="font-mono" style="margin-left:auto;font-size:11px;letter-spacing:.14em;' +
                 'color:var(--text-tertiary,#8494A5);">VIOLATION 0</span>' +
        '</div>' +
        '<div class="font-overline" id="mt-shield-title" style="margin-bottom:8px;color:var(--text-primary,#E7EDF5);">' +
          'ACTIVE ROUND MONITOR</div>' +
        '<p id="mt-shield-text" style="margin:0 0 10px;font-size:.95rem;line-height:1.75;color:var(--text-primary,#E7EDF5);"></p>' +
        '<p style="margin:0 0 26px;font-size:.8rem;line-height:1.6;color:var(--text-tertiary,#8494A5);">' +
          'During the live round this screen is monitored. Tab switching, minimizing the window, or leaving to ' +
          'another page is recorded as a screen-activity violation. Return to the round screen to continue.</p>' +
        '<div style="display:flex;gap:12px;justify-content:flex-end;flex-wrap:wrap;">' +
          '<button id="mt-shield-stay" type="button" class="hud-btn hud-btn-green" style="font-size:13px;">' +
            'RETURN TO ROUND</button>' +
          '<button id="mt-shield-leave" type="button" class="hud-btn hud-btn-ghost" style="font-size:13px;display:none;">' +
            'LEAVE ROUND</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(shield);
    shieldTitle = document.getElementById('mt-shield-title');
    shieldText = document.getElementById('mt-shield-text');
    shieldVio = document.getElementById('mt-shield-vio');
    stayBtn = document.getElementById('mt-shield-stay');
    leaveBtn = document.getElementById('mt-shield-leave');
    stayBtn.addEventListener('click', function () { dismiss(); });
    leaveBtn.addEventListener('click', function () {
      allowLeave = true;
      var href = pendingHref;
      dismiss();
      if (href) window.location.assign(href);
    });
  }

  function show(mode, title, text) {
    build();
    shieldTitle.textContent = title;
    shieldText.textContent = text;
    shieldVio.textContent = 'VIOLATION ' + violations;
    if (mode === 'leave') {
      stayBtn.textContent = 'STAY IN ROUND';
      leaveBtn.style.display = '';
    } else {
      stayBtn.textContent = 'RETURN TO ROUND';
      leaveBtn.style.display = 'none';
    }
    if (document.activeElement && document.activeElement.id &&
        document.activeElement.id.indexOf('mt-answer') === 0) {
      roundFocusTarget = document.activeElement;
    }
    shield.style.display = 'flex';
    stayBtn.focus();
  }

  function dismiss() {
    if (!shield) return;
    shield.style.display = 'none';
    pendingHref = null;
    if (roundFocusTarget) {
      var el = roundFocusTarget;
      roundFocusTarget = null;
      if (!el.disabled) { try { el.focus(); } catch (e) {} }
    }
  }

  // --------------------------------------------------------------- detectors

  function onVisibility() {
    if (!armed) return;
    if (document.hidden) {
      violations += 1;
      var n = violations;
      var text = n === 1
        ? 'The round screen was left once. Return now and stay on this screen — a second occurrence is treated as a repeated violation during the live round.'
        : 'The round screen has been left ' + n + ' times. This is a repeated violation — keep the round screen focused for the remainder of the game.';
      show('leaving', 'TAB SWITCH / SCREEN LEFT', text);
    }
  }

  function onUnload(e) {
    if (!armed || allowLeave) return;
    e.preventDefault();
    e.returnValue = 'You are inside an ACTIVE Round 1 screen. Leaving will be recorded as a screen-activity violation.';
    return e.returnValue;
  }

  function isOutsideLink(href) {
    if (!href || href.charAt(0) === '#' || href === 'javascript:void(0)') return false;
    if (href.indexOf('mailto:') === 0 || href.indexOf('tel:') === 0) return false;
    var a = document.createElement('a');
    a.href = href;
    if (a.origin !== window.location.origin) return false;
    if (a.pathname === window.location.pathname &&
        (a.search || '') === (window.location.search || '')) return false;
    return true;
  }

  function onClick(e) {
    if (!armed) return;
    var target = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (!target || !isOutsideLink(target.getAttribute('href'))) return;
    // Recovery / retry links injected by the controller (session restore, hint
    // refresh) are not treated as leaving the round.
    var host = target.closest('#mt-result, #mt-hint, #mt-complete');
    if (host) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    pendingHref = target.href;
    var label = (target.textContent || 'another page').trim().replace(/\s+/g, ' ').toUpperCase();
    show('leave',
         'LEAVE ROUND SCREEN?',
         'You are about to switch to "' + esc(label) + '" while the round is still live. ' +
         'Leaving the round screen is monitored and counted as a screen-activity violation. Stay in the round to continue.');
  }

  // ------------------------------------------------------------------ public

  function setActive(on) {
    armed = !!on;
    allowLeave = false;
    if (!armed && shield) {
      violations = 0;
      shield.style.display = 'none';
      pendingHref = null;
    }
  }

  var boot = function () {
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('beforeunload', onUnload);
    document.addEventListener('click', onClick, true);
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  window.RoundGuard = { setActive: setActive };
})();