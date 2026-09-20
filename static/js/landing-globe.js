/**
 * Tactical Orthographic 2D Canvas Globe Engine
 * Cyber Detective 2026 — Phase 3b-L Production Implementation
 * Zero external libraries, zero WebGL, pure Canvas 2D.
 */
(function (global) {
  'use strict';

  function TacticalGlobe(options) {
    this.canvas = options.canvas;
    this.ctx = this.canvas.getContext('2d', { alpha: true });
    this.points = options.points || [];
    this.rotationSpeed = options.rotationSpeed || 0.003; // rad per frame (~0.17 deg/frame)
    this.tilt = options.tilt !== undefined ? options.tilt : 0.26; // ~15 deg axial tilt
    this.homeCoords = options.homeCoords || [28.6139, 77.2090]; // Delhi [lat, lon]
    this.colorSignal = options.colorSignal || '#00F0FF';
    this.colorDim = options.colorDim || '#627D9F';
    this.colorAmber = options.colorAmber || '#F59E0B';

    this.currentLon = 0;
    this.rafId = null;
    this.lastTime = performance.now();
    this.frameTimes = [];
    this.isPaused = false;
    this.fps = 60;
    this.stride = 1;

    // Unit sphere Cartesian coordinates cache
    this.unitPoints = [];
    this.rebuildPoints();

    // Sizing & DPR setup
    this.initSize();

    // DOM telemetry elements
    this.elLon = document.getElementById('globe-telemetry-lon');
    this.elFps = document.getElementById('globe-telemetry-fps');
    this.elNodes = document.getElementById('globe-telemetry-nodes');
  }

  TacticalGlobe.prototype.rebuildPoints = function () {
    var raw = this.points;
    var len = raw.length;
    var pts = [];
    var stride = this.stride || 1;

    for (var i = 0; i < len; i += stride) {
      var pt = raw[i];
      var latRad = pt[0] * (Math.PI / 180);
      var lonRad = pt[1] * (Math.PI / 180);
      pts.push({
        x: Math.cos(latRad) * Math.sin(lonRad),
        y: Math.sin(latRad),
        z: Math.cos(latRad) * Math.cos(lonRad)
      });
    }
    this.unitPoints = pts;
  };

  TacticalGlobe.prototype.initSize = function () {
    var rect = this.canvas.getBoundingClientRect();
    var width = Math.round(rect.width) || 360;
    var height = Math.round(rect.height) || 360;
    var dpr = Math.min(window.devicePixelRatio || 1, 2); // Cap at 2 for perf

    // Mobile stride adaptation: <= 480px viewport width uses stride 3 (~577 dots)
    var isMobile = window.innerWidth <= 480 || width <= 320;
    var targetStride = isMobile ? 3 : 1;
    if (this.stride !== targetStride) {
      this.stride = targetStride;
      this.rebuildPoints();
    }

    this.width = width;
    this.height = height;
    this.canvas.width = Math.round(width * dpr);
    this.canvas.height = Math.round(height * dpr);
    this.ctx.setTransform(1, 0, 0, 1, 0, 0); // reset transform
    this.ctx.scale(dpr, dpr);

    this.centerX = width / 2;
    this.centerY = height / 2;
    // Radius clamped proportionally to canvas viewport
    this.radius = Math.min(width, height) * 0.40;
  };

  TacticalGlobe.prototype.renderFrame = function (now) {
    var dt = (now - this.lastTime);
    this.lastTime = now;
    if (dt > 0 && dt < 1000) {
      this.frameTimes.push(dt);
      if (this.frameTimes.length > 30) this.frameTimes.shift();
      var avgDt = this.frameTimes.reduce(function (a, b) { return a + b; }, 0) / this.frameTimes.length;
      this.fps = Math.round(1000 / avgDt);
    }

    var ctx = this.ctx;
    var cx = this.centerX;
    var cy = this.centerY;
    var r = this.radius;

    ctx.clearRect(0, 0, this.width, this.height);

    // 1. Atmosphere Radial Rim Glow (Direction B visual cue)
    var grad = ctx.createRadialGradient(cx, cy, r * 0.78, cx, cy, r * 1.12);
    grad.addColorStop(0, 'rgba(0, 240, 255, 0.0)');
    grad.addColorStop(0.85, 'rgba(0, 240, 255, 0.14)');
    grad.addColorStop(1, 'rgba(0, 240, 255, 0.0)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, cy, r * 1.12, 0, Math.PI * 2);
    ctx.fill();

    // 2. Horizon Wireframe Ring & Tactical Grid
    ctx.save();
    ctx.strokeStyle = 'rgba(98, 125, 159, 0.35)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.stroke();

    // Subtle latitude rings
    ctx.strokeStyle = 'rgba(98, 125, 159, 0.14)';
    ctx.setLineDash([2, 4]);
    ctx.beginPath();
    ctx.ellipse(cx, cy, r, r * 0.35, this.tilt, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.ellipse(cx, cy, r, r * 0.70, this.tilt, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();

    // Rotate longitude
    this.currentLon += this.rotationSpeed;
    var rot = this.currentLon;
    var cosRot = Math.cos(rot);
    var sinRot = Math.sin(rot);
    var cosTilt = Math.cos(this.tilt);
    var sinTilt = Math.sin(this.tilt);

    // 3. Render Land Nodes via Batching
    var points = this.unitPoints;
    var len = points.length;

    var backBatch = [];
    var frontBatch = [];

    for (var i = 0; i < len; i++) {
      var pt = points[i];
      // Rotate around Y axis
      var rx = pt.x * cosRot + pt.z * sinRot;
      var ry = pt.y;
      var rz = -pt.x * sinRot + pt.z * cosRot;

      // Axial tilt
      var ryT = ry * cosTilt - rz * sinTilt;
      var rzT = ry * sinTilt + rz * cosTilt;

      var sx = cx + rx * r;
      var sy = cy - ryT * r;

      if (rzT >= 0) {
        frontBatch.push(sx, sy, rzT);
      } else {
        backBatch.push(sx, sy);
      }
    }

    // Draw Dim Back Hemisphere Points
    ctx.fillStyle = 'rgba(98, 125, 159, 0.20)';
    var blen = backBatch.length;
    for (var j = 0; j < blen; j += 2) {
      ctx.fillRect(backBatch[j], backBatch[j + 1], 1.2, 1.2);
    }

    // Draw Front Hemisphere Points with depth-scaled size and opacity (Direction B depth cues)
    var flen = frontBatch.length;
    for (var k = 0; k < flen; k += 3) {
      var depth = frontBatch[k + 2];
      var pSize = 1.0 + depth * 1.0;
      var pAlpha = 0.35 + depth * 0.65;
      ctx.fillStyle = 'rgba(0, 240, 255, ' + pAlpha.toFixed(2) + ')';
      ctx.fillRect(frontBatch[k] - pSize / 2, frontBatch[k + 1] - pSize / 2, pSize, pSize);
    }

    // 4. Home Node Tactical Marker (Delhi/LAN Coordinate)
    var hLat = this.homeCoords[0] * (Math.PI / 180);
    var hLon = this.homeCoords[1] * (Math.PI / 180) + rot;
    var hx = Math.cos(hLat) * Math.sin(hLon);
    var hy = Math.sin(hLat);
    var hz = Math.cos(hLat) * Math.cos(hLon);
    var hyT = hy * cosTilt - hz * sinTilt;
    var hzT = hy * sinTilt + hz * cosTilt;

    if (hzT > 0) {
      var hScreenX = cx + hx * r;
      var hScreenY = cy - hyT * r;
      var pulse = (Math.sin(now * 0.005) + 1) / 2;

      ctx.save();
      // Target Reticle
      ctx.strokeStyle = this.colorAmber;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(hScreenX, hScreenY, 5 + pulse * 6, 0, Math.PI * 2);
      ctx.stroke();

      // Core Solid Center
      ctx.fillStyle = this.colorAmber;
      ctx.beginPath();
      ctx.arc(hScreenX, hScreenY, 2.5, 0, Math.PI * 2);
      ctx.fill();

      // Tactical Label
      ctx.font = '10px "JetBrains Mono", monospace';
      ctx.fillStyle = this.colorAmber;
      ctx.fillText('NODE 01 [LOCAL]', hScreenX + 10, hScreenY - 4);
      ctx.restore();
    }

    // 5. Update DOM Telemetry readouts periodically
    if (this.elFps && Math.random() < 0.05) {
      this.elFps.textContent = this.fps + ' FPS';
    }
    if (this.elLon && Math.random() < 0.1) {
      var deg = ((this.currentLon * (180 / Math.PI)) % 360).toFixed(1);
      this.elLon.textContent = deg + '°E';
    }
    if (this.elNodes && this.lastNodeCount !== this.unitPoints.length) {
      this.elNodes.textContent = this.unitPoints.length.toLocaleString() + ' NODES';
      this.lastNodeCount = this.unitPoints.length;
    }
  };

  TacticalGlobe.prototype.start = function () {
    var self = this;
    function loop(now) {
      if (!self.isPaused) {
        self.renderFrame(now);
      }
      self.rafId = requestAnimationFrame(loop);
    }
    this.rafId = requestAnimationFrame(loop);
  };

  TacticalGlobe.prototype.stop = function () {
    if (this.rafId) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
  };

  // Controller Initializer
  function initLandingGlobe() {
    var canvas = document.getElementById('tactical-globe-canvas');
    if (!canvas) return;

    var container = document.getElementById('globe-viewport');
    var poster = document.getElementById('globe-poster');

    // 1. Reduced Motion Safeguard
    var prefersReducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // 2. Fetch Land Mask Coordinates
    var dataUrl = canvas.getAttribute('data-mask-url') || '/static/data/land_mask.json';

    fetch(dataUrl)
      .then(function (res) {
        if (!res.ok) throw new Error('Land mask fetch error ' + res.status);
        return res.json();
      })
      .then(function (points) {
        var globe = new TacticalGlobe({
          canvas: canvas,
          points: points,
          rotationSpeed: 0.003,
          tilt: 0.26,
          homeCoords: [28.6139, 77.2090] // Delhi
        });

        // If prefers-reduced-motion, render a single static frame and exit
        if (prefersReducedMotion) {
          globe.renderFrame(performance.now());
          return;
        }

        globe.start();

        // 3. Responsive Resize Handling via ResizeObserver
        if (typeof ResizeObserver !== 'undefined' && container) {
          var ro = new ResizeObserver(function () {
            globe.initSize();
            if (globe.isPaused) {
              globe.renderFrame(performance.now());
            }
          });
          ro.observe(container);
        } else {
          window.addEventListener('resize', function () {
            globe.initSize();
          });
        }

        // 4. IntersectionObserver Pause when Scrolled Offscreen
        if (typeof IntersectionObserver !== 'undefined') {
          var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
              globe.isPaused = !entry.isIntersecting;
            });
          }, { threshold: 0.05 });
          io.observe(canvas);
        }

        // 5. Visibility Change Pause
        document.addEventListener('visibilitychange', function () {
          globe.isPaused = document.hidden;
        });

        // 6. Attract Mode Toggle (?attract=1 or 90s idle)
        var isUrlAttract = window.location.search.indexOf('attract=1') !== -1;
        if (isUrlAttract) {
          document.body.classList.add('attract-mode');
          globe.initSize();
        } else {
          var idleTimer = null;
          function resetIdle() {
            if (document.body.classList.contains('attract-mode')) {
              document.body.classList.remove('attract-mode');
              globe.initSize();
            }
            clearTimeout(idleTimer);
            idleTimer = setTimeout(function () {
              document.body.classList.add('attract-mode');
              globe.initSize();
            }, 90000); // 90s idle timeout
          }
          window.addEventListener('mousemove', resetIdle, { passive: true });
          window.addEventListener('keydown', resetIdle, { passive: true });
          window.addEventListener('touchstart', resetIdle, { passive: true });
          resetIdle();
        }
      })
      .catch(function (err) {
        console.warn('Globe canvas fallback triggered:', err);
        if (poster) {
          poster.style.display = 'block';
          canvas.style.display = 'none';
        }
      });
  }

  // Auto-init on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initLandingGlobe);
  } else {
    initLandingGlobe();
  }

  global.TacticalGlobe = TacticalGlobe;
})(typeof window !== 'undefined' ? window : this);
