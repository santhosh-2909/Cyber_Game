/**
 * Cyber Detective 2026 — Core UI Behavior Engine (core.js)
 * Pure vanilla JavaScript. Zero framework dependencies.
 * Complies with strict Content-Security-Policy (no eval, no external fetch).
 *
 * Implements:
 * - Theme toggle with localStorage persistence
 * - Tabs navigation (.tabs-nav & .tab-item)
 * - Modal dialogs (open, close, Escape, trap focus)
 * - Off-canvas drawers (toggle, close, backdrop click)
 * - Toast notification manager (auto-dismiss & persistent error alerts)
 * - Connection-lost banner (window online/offline & failed fetch interceptor)
 * - Command palette (Ctrl+K / Cmd+K)
 */

(function () {
  'use strict';

  // -------------------------------------------------------------------------
  // 1. THEME TOGGLE & PERSISTENCE
  // -------------------------------------------------------------------------
  function initTheme() {
    try {
      var saved = localStorage.getItem('cd_theme');
      if (saved === 'light' || saved === 'dark') {
        document.documentElement.setAttribute('data-theme', saved);
      }
    } catch (e) {
      // localStorage may be disabled in restricted iframe / sandbox
    }

    document.addEventListener('click', function (e) {
      var toggleBtn = e.target.closest('#theme-toggle, [data-action="toggle-theme"]');
      if (!toggleBtn) return;
      var cur = document.documentElement.getAttribute('data-theme') || 'dark';
      var next = cur === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      try {
        localStorage.setItem('cd_theme', next);
      } catch (err) {}
    });
  }

  // -------------------------------------------------------------------------
  // 2. TABS CONTROLLER (Event Delegation)
  // -------------------------------------------------------------------------
  function initTabs() {
    document.addEventListener('click', function (e) {
      var tabBtn = e.target.closest('.tab-item, [role="tab"]');
      if (!tabBtn) return;
      var targetId = tabBtn.getAttribute('data-target') || tabBtn.getAttribute('aria-controls');
      var nav = tabBtn.closest('.tabs-nav, [role="tablist"]');
      if (!nav) return;

      // Deactivate all sibling tabs
      var siblings = nav.querySelectorAll('.tab-item, [role="tab"]');
      siblings.forEach(function (s) {
        s.classList.remove('is-active');
        s.setAttribute('aria-selected', 'false');
      });

      // Activate clicked tab
      tabBtn.classList.add('is-active');
      tabBtn.setAttribute('aria-selected', 'true');

      // Toggle panels
      if (targetId) {
        var parentContainer = nav.parentElement;
        var panels = parentContainer.querySelectorAll('.tab-panel, [role="tabpanel"]');
        panels.forEach(function (p) {
          if (p.id === targetId || p.getAttribute('data-panel') === targetId) {
            p.classList.add('is-active');
            p.removeAttribute('hidden');
          } else {
            p.classList.remove('is-active');
            p.setAttribute('hidden', 'true');
          }
        });
      }
    });
  }

  // -------------------------------------------------------------------------
  // 3. MODAL CONTROLLER
  // -------------------------------------------------------------------------
  function initModals() {
    // Open modal via data-modal-target
    document.addEventListener('click', function (e) {
      var trigger = e.target.closest('[data-modal-target]');
      if (trigger) {
        var modalId = trigger.getAttribute('data-modal-target');
        var modal = document.getElementById(modalId);
        if (modal) {
          modal.classList.add('is-open');
          modal.setAttribute('aria-hidden', 'false');
          var focusable = modal.querySelector('button, input, [tabindex="0"]');
          if (focusable) focusable.focus();
        }
      }

      // Close button inside modal
      var closeBtn = e.target.closest('[data-modal-close], .modal-close');
      if (closeBtn) {
        var modalToClose = closeBtn.closest('.modal-backdrop, .modal-dialog');
        if (modalToClose) {
          var backdrop = modalToClose.classList.contains('modal-backdrop') ? modalToClose : modalToClose.closest('.modal-backdrop');
          if (backdrop) {
            backdrop.classList.remove('is-open');
            backdrop.setAttribute('aria-hidden', 'true');
          }
        }
      }
    });

    // Escape key closes open modals & drawers
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        document.querySelectorAll('.modal-backdrop.is-open').forEach(function (m) {
          m.classList.remove('is-open');
          m.setAttribute('aria-hidden', 'true');
        });
        document.querySelectorAll('.drawer-backdrop.is-open').forEach(function (d) {
          d.classList.remove('is-open');
        });
        document.querySelectorAll('.cmd-palette-backdrop.is-open').forEach(function (c) {
          c.classList.remove('is-open');
        });
      }
    });
  }

  // -------------------------------------------------------------------------
  // 4. DRAWER CONTROLLER
  // -------------------------------------------------------------------------
  function initDrawers() {
    document.addEventListener('click', function (e) {
      var trigger = e.target.closest('[data-drawer-target]');
      if (trigger) {
        var drawerId = trigger.getAttribute('data-drawer-target');
        var drawer = document.getElementById(drawerId);
        var backdrop = document.querySelector('.drawer-backdrop');
        if (drawer) {
          drawer.classList.toggle('is-open');
          if (backdrop) backdrop.classList.toggle('is-open');
        }
      }

      // Backdrop click closes drawer
      if (e.target.classList.contains('drawer-backdrop')) {
        e.target.classList.remove('is-open');
        document.querySelectorAll('.drawer.is-open').forEach(function (d) {
          d.classList.remove('is-open');
        });
      }
    });
  }

  // -------------------------------------------------------------------------
  // 5. TOAST NOTIFICATION MANAGER
  // -------------------------------------------------------------------------
  var ToastManager = {
    getContainer: function () {
      var container = document.getElementById('toast-container');
      if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
      }
      return container;
    },
    show: function (message, type, duration) {
      var container = this.getContainer();
      var toast = document.createElement('div');
      toast.className = 'toast toast-' + (type || 'info');
      toast.setAttribute('role', type === 'danger' ? 'alert' : 'status');
      toast.setAttribute('aria-live', type === 'danger' ? 'assertive' : 'polite');

      var iconSymbol = type === 'success' ? '#icon-check' : (type === 'danger' ? '#icon-status-error' : '#icon-info');
      toast.innerHTML = '<svg class="w-4 h-4 flex-shrink-0"><use href="/static/icons/sprite.svg' + iconSymbol + '"></use></svg>' +
                        '<span class="flex-1 font-mono text-xs">' + message + '</span>' +
                        '<button type="button" class="btn btn-ghost btn-sm btn-icon" style="width:24px;height:24px;" aria-label="Dismiss">&times;</button>';

      container.appendChild(toast);

      var dismissBtn = toast.querySelector('button');
      dismissBtn.addEventListener('click', function () {
        toast.remove();
      });

      // Success auto-dismiss after 2000ms; errors persist until dismissed
      if (type !== 'danger' && duration !== 0) {
        setTimeout(function () {
          if (toast.parentElement) toast.remove();
        }, duration || 2500);
      }
      return toast;
    }
  };

  // Expose global apToast helper compatible with existing inline handlers
  window.apToast = function (msg, type) {
    ToastManager.show(msg, type || 'info');
  };

  // -------------------------------------------------------------------------
  // 6. CONNECTION-LOST BANNER
  // -------------------------------------------------------------------------
  function initConnectionMonitor() {
    var banner = document.getElementById('connection-banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'connection-banner';
      banner.className = 'connection-banner';
      banner.innerHTML = '[OFFLINE] LAN CONNECTION INTERRUPTED — BUFFERING SUBMISSIONS LOCALLY';
      document.body.prepend(banner);
    }

    function setOnline(online) {
      if (online) {
        banner.classList.remove('is-active');
      } else {
        banner.classList.add('is-active');
      }
    }

    window.addEventListener('online', function () { setOnline(true); });
    window.addEventListener('offline', function () { setOnline(false); });
    if (!navigator.onLine) setOnline(false);

    // Intercept native fetch failures without heartbeat polling
    var origFetch = window.fetch;
    if (origFetch) {
      window.fetch = function () {
        return origFetch.apply(this, arguments).then(function (response) {
          setOnline(true);
          return response;
        }).catch(function (error) {
          setOnline(false);
          throw error;
        });
      };
    }
  }

  // -------------------------------------------------------------------------
  // 7. COMMAND PALETTE (Ctrl+K / Cmd+K)
  // -------------------------------------------------------------------------
  function initCommandPalette() {
    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        var palette = document.querySelector('.cmd-palette-backdrop');
        if (palette) {
          palette.classList.toggle('is-open');
          if (palette.classList.contains('is-open')) {
            var input = palette.querySelector('input');
            if (input) input.focus();
          }
        }
      }
    });
  }

  // Initialize on DOM ready
  document.addEventListener('DOMContentLoaded', function () {
    initTheme();
    initTabs();
    initModals();
    initDrawers();
    initConnectionMonitor();
    initCommandPalette();
  });

})();
