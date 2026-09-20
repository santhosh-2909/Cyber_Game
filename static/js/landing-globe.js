/**
 * Tactical Orthographic 2D Canvas Globe Engine with Great-Circle Arc Telemetry
 * Cyber Detective 2026 — Phase 3b-L Production Implementation (Gate L2b)
 * Zero external libraries, zero WebGL, pure Canvas 2D, bit-packed binary coordinates.
 */
(function (global) {
  'use strict';

  // Seeded Mulberry32 PRNG for deterministic incident chains
  function mulberry32(seed) {
    return function () {
      seed |= 0;
      seed = (seed + 0x6D2B79F5) | 0;
      var t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // Spherical Math Helpers
  function latLonToCartesian(latDeg, lonDeg) {
    var latRad = latDeg * (Math.PI / 180);
    var lonRad = lonDeg * (Math.PI / 180);
    return {
      x: Math.cos(latRad) * Math.sin(lonRad),
      y: Math.sin(latRad),
      z: Math.cos(latRad) * Math.cos(lonRad)
    };
  }

  function dotProduct(v1, v2) {
    return v1.x * v2.x + v1.y * v2.y + v1.z * v2.z;
  }

  // Spherical Linear Interpolation (Slerp) on unit sphere
  function slerp(v1, v2, t) {
    var dot = dotProduct(v1, v2);
    dot = Math.max(-1, Math.min(1, dot));
    var theta = Math.acos(dot);
    if (Math.abs(theta) < 0.0001) return v1;
    var sinTheta = Math.sin(theta);
    var a = Math.sin((1 - t) * theta) / sinTheta;
    var b = Math.sin(t * theta) / sinTheta;
    return {
      x: a * v1.x + b * v2.x,
      y: a * v1.y + b * v2.y,
      z: a * v1.z + b * v2.z
    };
  }

  // Incident Arc Stages
  var ARC_STAGES = [
    { type: 'ENTRY', name: 'Recon & Entry', color: '#00F0FF', glyph: '▶' },
    { type: 'PIVOT', name: 'Lateral Pivot', color: '#BFA5FF', glyph: '⇄' },
    { type: 'C2',    name: 'C2 Beacon',     color: '#F59E0B', glyph: '⚡' },
    { type: 'EXFIL', name: 'Data Exfil',    color: '#F87171', glyph: '⇪' }
  ];

  function TacticalGlobe(options) {
    this.canvas = options.canvas;
    this.ctx = this.canvas.getContext('2d', { alpha: true });
    this.rawPoints = options.points || [];

    // HOME Node from data attributes or default New Delhi [28.6139, 77.2090]
    var homeLat = parseFloat(this.canvas.getAttribute('data-home-lat') || '28.6139');
    var homeLon = parseFloat(this.canvas.getAttribute('data-home-lon') || '77.2090');
    this.homeCoords = [homeLat, homeLon];
    this.homeVec = latLonToCartesian(homeLat, homeLon);

    // Rotation & Axis
    this.rotationSpeed = 0.003; // rad per frame
    this.tilt = 0.26; // ~15 deg axial tilt
    this.currentLon = 0;
    this.dragLon = 0;
    this.dragLat = 0;
    this.inertiaX = 0;
    this.inertiaY = 0;
    this.isDragging = false;

    // Quality Tiers: 0: 1732 dots / 6 arcs; 1: 866 dots / 3 arcs; 2: 433 dots / 1 arc; 3: poster
    var savedTier = sessionStorage.getItem('tactical_globe_tier');
    this.tier = savedTier !== null ? parseInt(savedTier, 10) : 0;
    this.drawTimes = [];
    this.droppedFrames = 0;
    this.longTasksCount = 0;
    this.lastFrameStamp = performance.now();
    this.isPaused = false;

    // PRNG & Incident Arcs
    this.rng = mulberry32(0xC7BE2026);
    this.arcs = [];
    this.arrivalRipples = [];

    // Precomputed Cartesian points
    this.unitPoints = [];
    this.stride = 1;
    this.applyTierSettings();

    // DOM Elements
    this.elLon = document.getElementById('globe-telemetry-lon');
    this.elFps = document.getElementById('globe-telemetry-fps');
    this.elNodes = document.getElementById('globe-telemetry-nodes');
    this.perfOverlay = document.getElementById('globe-perf-overlay');
    this.pauseBtn = document.getElementById('globe-pause-btn');
    this.attractBtn = document.getElementById('attract-toggle');

    this.isPerfMode = window.location.search.indexOf('perf=1') !== -1;
    if (this.isPerfMode && this.perfOverlay) {
      this.perfOverlay.style.display = 'block';
    }

    this.initSize();
    this.setupInteractions();
    this.setupLongTaskObserver();
    this.seedInitialArcs();
  }

  TacticalGlobe.prototype.applyTierSettings = function () {
    // Quality Tiers (Monotonic):
    // Tier 0: 1732 dots, max 6 arcs, native DPR (up to 2)
    // Tier 1: 866 dots, max 3 arcs, DPR 1
    // Tier 2: 433 dots, max 1 arc, DPR 1
    // Tier 3: static poster + paused
    if (this.tier === 0) {
      this.stride = 1;
      this.maxArcs = 6;
      this.maxDpr = 2;
    } else if (this.tier === 1) {
      this.stride = 2;
      this.maxArcs = 3;
      this.maxDpr = 1;
    } else if (this.tier === 2) {
      this.stride = 4;
      this.maxArcs = 1;
      this.maxDpr = 1;
    } else {
      this.stride = 4;
      this.maxArcs = 0;
      this.maxDpr = 1;
      this.triggerTier3Poster();
      return;
    }

    // Adaptive mobile viewport override: width <= 480px caps stride at >= 2
    if (window.innerWidth <= 480 && this.stride < 2) {
      this.stride = 3; // ~578 dots
      this.maxArcs = Math.min(this.maxArcs, 3);
    }

    // Bug Fix (R2.c): Clamp arcs immediately so arcCount never stays at 6 upon tier downgrade
    if (this.arcs.length > this.maxArcs) {
      this.arcs = this.arcs.slice(0, this.maxArcs);
    }

    this.rebuildPoints();
    this.initSize();
    sessionStorage.setItem('tactical_globe_tier', this.tier);
  };

  TacticalGlobe.prototype.triggerTier3Poster = function () {
    this.isPaused = true;
    var poster = document.getElementById('globe-poster');
    var canvas = this.canvas;
    var banner = document.getElementById('globe-reduced-banner');
    var resumeBtn = document.getElementById('globe-resume-btn');
    var self = this;

    if (poster) poster.style.display = 'block';
    if (canvas) canvas.style.display = 'none';
    if (banner) banner.style.display = 'flex';

    if (resumeBtn && !resumeBtn._bound) {
      resumeBtn._bound = true;
      resumeBtn.addEventListener('click', function () {
        resumeBtn.setAttribute('aria-pressed', 'true');
        if (banner) banner.style.display = 'none';
        if (poster) poster.style.display = 'none';
        if (canvas) canvas.style.display = 'block';
        self.tier = 2; // resume at Tier 2
        self.applyTierSettings();
        self.isPaused = false;
        self.lastFrameStamp = performance.now();
      });
    }
  };

  TacticalGlobe.prototype.rebuildPoints = function () {
    var raw = this.rawPoints;
    var len = raw.length;
    var pts = [];
    var stride = this.stride || 1;

    for (var i = 0; i < len; i += stride) {
      var pt = raw[i];
      pts.push(latLonToCartesian(pt[0], pt[1]));
    }
    this.unitPoints = pts;
    if (this.elNodes) {
      this.elNodes.textContent = pts.length.toLocaleString() + ' NODES';
    }
  };

  TacticalGlobe.prototype.initSize = function () {
    var rect = this.canvas.getBoundingClientRect();
    var width = Math.round(rect.width) || 360;
    var height = Math.round(rect.height) || 360;
    var dpr = Math.min(window.devicePixelRatio || 1, this.maxDpr || 2);

    this.width = width;
    this.height = height;
    this.canvas.width = Math.round(width * dpr);
    this.canvas.height = Math.round(height * dpr);
    this.ctx.setTransform(1, 0, 0, 1, 0, 0);
    this.ctx.scale(dpr, dpr);

    this.centerX = width / 2;
    this.centerY = height / 2;
    this.radius = Math.min(width, height) * 0.40;

    // Cache atmospheric radial gradient (R2.e hotspot elimination)
    this.cachedAtmosphereGrad = this.ctx.createRadialGradient(
      this.centerX, this.centerY, this.radius * 0.78,
      this.centerX, this.centerY, this.radius * 1.12
    );
    this.cachedAtmosphereGrad.addColorStop(0, 'rgba(0, 240, 255, 0.0)');
    this.cachedAtmosphereGrad.addColorStop(0.85, 'rgba(0, 240, 255, 0.14)');
    this.cachedAtmosphereGrad.addColorStop(1, 'rgba(0, 240, 255, 0.0)');
  };

  TacticalGlobe.prototype.seedInitialArcs = function () {
    this.arcs = [];
    var count = this.maxArcs;
    for (var i = 0; i < count; i++) {
      this.spawnArc(i / Math.max(1, count));
    }
  };

  TacticalGlobe.prototype.spawnArc = function (initialProgress) {
    if (this.unitPoints.length < 10 || this.arcs.length >= this.maxArcs) return;

    var stageIdx = Math.floor(this.rng() * ARC_STAGES.length);
    var stage = ARC_STAGES[stageIdx];

    // Pick start node and end node from real tactical land points
    var startIdx = Math.floor(this.rng() * this.unitPoints.length);
    var endIdx = Math.floor(this.rng() * this.unitPoints.length);
    if (startIdx === endIdx) endIdx = (startIdx + 50) % this.unitPoints.length;

    // 50% of arcs connect to or from HOME node (Delhi)
    var startVec = (this.rng() < 0.5) ? this.homeVec : this.unitPoints[startIdx];
    var endVec = (startVec === this.homeVec) ? this.unitPoints[endIdx] : this.homeVec;

    // Precalculate 20 geodesic waypoints (R2.e hotspot elimination: zero runtime slerp in draw loop)
    var waypoints = [];
    var STEPS = 20;
    for (var s = 0; s <= STEPS; s++) {
      var st = s / STEPS;
      var sv = slerp(startVec, endVec, st);
      var sh = 1.0 + Math.sin(Math.PI * st) * 0.12;
      waypoints.push({
        x: sv.x * sh,
        y: sv.y * sh,
        z: sv.z * sh
      });
    }

    this.arcs.push({
      startVec: startVec,
      endVec: endVec,
      stage: stage,
      progress: initialProgress || 0,
      speed: 0.005 + this.rng() * 0.005,
      trailLength: 0.22,
      waypoints: waypoints,
      isExfil: stage.type === 'EXFIL'
    });
  };

  TacticalGlobe.prototype.setupInteractions = function () {
    var self = this;
    var canvas = this.canvas;
    var startX = 0, startY = 0;

    canvas.addEventListener('pointerdown', function (e) {
      self.isDragging = true;
      startX = e.clientX;
      startY = e.clientY;
      self.inertiaX = 0;
      self.inertiaY = 0;
      canvas.setPointerCapture(e.pointerId);
    });

    canvas.addEventListener('pointermove', function (e) {
      if (!self.isDragging) return;
      var dx = e.clientX - startX;
      var dy = e.clientY - startY;
      startX = e.clientX;
      startY = e.clientY;

      self.dragLon += dx * 0.005;
      self.dragLat = Math.max(-0.5, Math.min(0.5, self.dragLat + dy * 0.005));
      self.inertiaX = dx * 0.005;
      self.inertiaY = dy * 0.005;
    });

    function endDrag(e) {
      if (self.isDragging) {
        self.isDragging = false;
        try { canvas.releasePointerCapture(e.pointerId); } catch (_) {}
      }
    }
    canvas.addEventListener('pointerup', endDrag);
    canvas.addEventListener('pointercancel', endDrag);

    // Pause button toggle (Condition 8)
    if (this.pauseBtn) {
      this.pauseBtn.addEventListener('click', function () {
        self.togglePause();
      });
    }

    // Attract button toggle (Condition 6)
    if (this.attractBtn) {
      this.attractBtn.addEventListener('click', function () {
        self.toggleAttract();
      });
    }
  };

  TacticalGlobe.prototype.togglePause = function () {
    this.isPaused = !this.isPaused;
    if (this.pauseBtn) {
      this.pauseBtn.setAttribute('aria-pressed', this.isPaused ? 'true' : 'false');
      this.pauseBtn.textContent = this.isPaused ? 'RESUME ORBIT' : 'PAUSE ORBIT';
    }
    if (!this.isPaused) {
      this.lastFrameStamp = performance.now();
    }
  };

  TacticalGlobe.prototype.toggleAttract = function () {
    var isAttract = document.body.classList.toggle('attract-mode');
    if (this.attractBtn) {
      this.attractBtn.setAttribute('aria-pressed', isAttract ? 'true' : 'false');
      this.attractBtn.textContent = isAttract ? 'EXIT KIOSK' : 'KIOSK VIEW';
    }
    this.initSize();
  };

  TacticalGlobe.prototype.setupLongTaskObserver = function () {
    var self = this;
    if (typeof PerformanceObserver !== 'undefined') {
      try {
        var observer = new PerformanceObserver(function (list) {
          list.getEntries().forEach(function (entry) {
            if (entry.entryType === 'longtask') {
              self.longTasksCount++;
            }
          });
        });
        observer.observe({ entryTypes: ['longtask'] });
      } catch (_) {}
    }
  };

  // Automated Tier Degrader based on rolling draw p95 (Condition 2 / R2.a, R2.b, R2.c)
  TacticalGlobe.prototype.checkPerformanceConvergence = function () {
    if (this.tier >= 3) return;

    var now = performance.now();
    if (!this.initTime) this.initTime = now;
    // Condition R2.b: Exclude initial 5s warm-up from degrader decisions
    if (now - this.initTime < 5000) return;

    // Check every 30 draw samples
    if (this.drawTimes.length < 30) return;

    var sorted = this.drawTimes.slice().sort(function (a, b) { return a - b; });
    var p95 = sorted[Math.floor(sorted.length * 0.95)];

    // Target budget:
    // A healthy 1x machine stays at Tier 0 (draw p95 is ~3-8ms, well below 16ms).
    // If p95 > 35ms (fps < 28) or p95 > 18ms consistently with hysteresis:
    if (p95 > 35) {
      // Immediate degradation for severe bottleneck (<28 fps)
      this.tier++;
      this.consecutiveSlowChecks = 0;
      this.applyTierSettings();
      this.drawTimes = [];
    } else if (p95 > 18) {
      // Hysteresis: requires 2 consecutive slow checks before degrading
      this.consecutiveSlowChecks = (this.consecutiveSlowChecks || 0) + 1;
      if (this.consecutiveSlowChecks >= 2) {
        this.tier++;
        this.consecutiveSlowChecks = 0;
        this.applyTierSettings();
        this.drawTimes = [];
      }
    } else {
      this.consecutiveSlowChecks = 0;
    }
  };

  // Pure draw() execution routine instrumented with performance.now() (Condition 1)
  TacticalGlobe.prototype.draw = function (now) {
    var ctx = this.ctx;
    var cx = this.centerX;
    var cy = this.centerY;
    var r = this.radius;

    ctx.clearRect(0, 0, this.width, this.height);

    // Apply drag inertia decay
    if (!this.isDragging) {
      this.dragLon += this.inertiaX;
      this.dragLat = Math.max(-0.5, Math.min(0.5, this.dragLat + this.inertiaY));
      this.inertiaX *= 0.94;
      this.inertiaY *= 0.94;
    }

    // 1. Direction B Atmospheric Rim Glow Ring (Cached radial gradient, zero blur)
    if (this.cachedAtmosphereGrad) {
      ctx.fillStyle = this.cachedAtmosphereGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, r * 1.12, 0, Math.PI * 2);
      ctx.fill();
    }

    // 2. Horizon Wireframe Ring & Latitude Reticles
    ctx.save();
    ctx.strokeStyle = 'rgba(98, 125, 159, 0.35)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.stroke();

    ctx.strokeStyle = 'rgba(98, 125, 159, 0.14)';
    ctx.setLineDash([2, 4]);
    ctx.beginPath();
    ctx.ellipse(cx, cy, r, r * 0.35, this.tilt + this.dragLat, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.ellipse(cx, cy, r, r * 0.70, this.tilt + this.dragLat, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();

    // Longitude and Latitude rotation angles
    this.currentLon += this.rotationSpeed;
    var rot = this.currentLon + this.dragLon;
    var cosRot = Math.cos(rot);
    var sinRot = Math.sin(rot);
    var effTilt = this.tilt + this.dragLat;
    var cosTilt = Math.cos(effTilt);
    var sinTilt = Math.sin(effTilt);

    // 3. Project Land Nodes via Coordinate Batching into 4 Discrete Alpha Buckets (R2.e)
    var points = this.unitPoints;
    var len = points.length;
    var backBatch = [];
    var bucket0 = []; // alpha ~0.40, depth < 0.25
    var bucket1 = []; // alpha ~0.60, depth 0.25 - 0.50
    var bucket2 = []; // alpha ~0.80, depth 0.50 - 0.75
    var bucket3 = []; // alpha ~1.00, depth >= 0.75

    for (var i = 0; i < len; i++) {
      var pt = points[i];
      var rx = pt.x * cosRot + pt.z * sinRot;
      var ry = pt.y;
      var rz = -pt.x * sinRot + pt.z * cosRot;

      var ryT = ry * cosTilt - rz * sinTilt;
      var rzT = ry * sinTilt + rz * cosTilt;

      var sx = (cx + rx * r) | 0;
      var sy = (cy - ryT * r) | 0;

      if (rzT >= 0) {
        if (rzT < 0.25) {
          bucket0.push(sx, sy);
        } else if (rzT < 0.50) {
          bucket1.push(sx, sy);
        } else if (rzT < 0.75) {
          bucket2.push(sx, sy);
        } else {
          bucket3.push(sx, sy);
        }
      } else {
        backBatch.push(sx, sy);
      }
    }

    // Draw Dim Back Hemisphere Points (1 fillStyle assignment)
    ctx.fillStyle = 'rgba(98, 125, 159, 0.20)';
    for (var j = 0, blen = backBatch.length; j < blen; j += 2) {
      ctx.fillRect(backBatch[j], backBatch[j + 1], 1, 1);
    }

    // Draw 4 Discrete Front Alpha Buckets (Only 4 fillStyle assignments per frame!)
    ctx.fillStyle = 'rgba(0, 240, 255, 0.40)';
    for (var b0 = 0, l0 = bucket0.length; b0 < l0; b0 += 2) {
      ctx.fillRect(bucket0[b0], bucket0[b0 + 1], 1, 1);
    }

    ctx.fillStyle = 'rgba(0, 240, 255, 0.60)';
    for (var b1 = 0, l1 = bucket1.length; b1 < l1; b1 += 2) {
      ctx.fillRect(bucket1[b1], bucket1[b1 + 1], 1, 1);
    }

    ctx.fillStyle = 'rgba(0, 240, 255, 0.80)';
    for (var b2 = 0, l2 = bucket2.length; b2 < l2; b2 += 2) {
      ctx.fillRect(bucket2[b2], bucket2[b2 + 1], 2, 2);
    }

    ctx.fillStyle = 'rgba(0, 240, 255, 1.00)';
    for (var b3 = 0, l3 = bucket3.length; b3 < l3; b3 += 2) {
      ctx.fillRect(bucket3[b3] - 1, bucket3[b3 + 1] - 1, 2, 2);
    }

    // 4. Render Incident Great-Circle Arcs (Condition 3: entry -> pivot -> C2 -> exfil)
    this.renderIncidentArcs(ctx, cx, cy, r, cosRot, sinRot, cosTilt, sinTilt);

    // 5. Render Arrival Ripples
    this.renderArrivalRipples(ctx, cx, cy, r, cosRot, sinRot, cosTilt, sinTilt);

    // 6. Home Node Tactical Marker (New Delhi / LAN Coordinator)
    this.renderHomeMarker(ctx, cx, cy, r, cosRot, sinRot, cosTilt, sinTilt, now);
  };

  TacticalGlobe.prototype.renderIncidentArcs = function (ctx, cx, cy, r, cosRot, sinRot, cosTilt, sinTilt) {
    for (var i = this.arcs.length - 1; i >= 0; i--) {
      var arc = this.arcs[i];
      arc.progress += arc.speed;

      if (arc.progress >= 1.0) {
        this.arrivalRipples.push({
          vec: arc.endVec,
          color: arc.stage.color,
          radius: 1,
          maxRadius: 18,
          alpha: 1.0
        });

        this.arcs.splice(i, 1);
        this.spawnArc(0);
        continue;
      }

      var waypoints = arc.waypoints;
      if (!waypoints || waypoints.length === 0) continue;

      var totalSteps = waypoints.length - 1;
      var headT = arc.progress;
      var tailT = Math.max(0, headT - arc.trailLength);

      var startIdx = Math.floor(tailT * totalSteps);
      var endIdx = Math.min(totalSteps, Math.ceil(headT * totalSteps));

      ctx.save();
      ctx.strokeStyle = arc.stage.color;
      ctx.lineWidth = 1.6;
      ctx.lineCap = 'round';
      ctx.globalAlpha = 0.85;

      // Single continuous path stroke per arc (R2.e hotspot elimination)
      ctx.beginPath();
      var pathStarted = false;
      var headScreenX = 0, headScreenY = 0, headVisible = false;

      for (var s = startIdx; s <= endIdx; s++) {
        var wp = waypoints[s];
        var rx = wp.x * cosRot + wp.z * sinRot;
        var ry = wp.y;
        var rz = -wp.x * sinRot + wp.z * cosRot;
        var ryT = ry * cosTilt - rz * sinTilt;
        var rzT = ry * sinTilt + rz * cosTilt;

        if (rzT > -0.1) {
          var px = (cx + rx * r) | 0;
          var py = (cy - ryT * r) | 0;
          if (!pathStarted) {
            ctx.moveTo(px, py);
            pathStarted = true;
          } else {
            ctx.lineTo(px, py);
          }
          if (s === endIdx) {
            headScreenX = px;
            headScreenY = py;
            headVisible = (rzT > -0.05);
          }
        }
      }
      if (pathStarted) {
        ctx.stroke();
      }

      // Leading Pulse Head
      if (headVisible && pathStarted) {
        ctx.globalAlpha = 1.0;
        ctx.fillStyle = '#FFFFFF';
        ctx.beginPath();
        ctx.arc(headScreenX, headScreenY, 2.2, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = arc.stage.color;
        ctx.beginPath();
        ctx.arc(headScreenX, headScreenY, 3.8, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.restore();
    }
  };

  TacticalGlobe.prototype.renderArrivalRipples = function (ctx, cx, cy, r, cosRot, sinRot, cosTilt, sinTilt) {
    for (var i = this.arrivalRipples.length - 1; i >= 0; i--) {
      var rip = this.arrivalRipples[i];
      rip.radius += 0.8;
      rip.alpha -= 0.04;

      if (rip.alpha <= 0) {
        this.arrivalRipples.splice(i, 1);
        continue;
      }

      var v = rip.vec;
      var rx = v.x * cosRot + v.z * sinRot;
      var ry = v.y;
      var rz = -v.x * sinRot + v.z * cosRot;
      var ryT = ry * cosTilt - rz * sinTilt;
      var rzT = ry * sinTilt + rz * cosTilt;

      if (rzT > 0) {
        ctx.save();
        ctx.strokeStyle = rip.color;
        ctx.globalAlpha = rip.alpha;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(cx + rx * r, cy - ryT * r, rip.radius, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      }
    }
  };

  TacticalGlobe.prototype.renderHomeMarker = function (ctx, cx, cy, r, cosRot, sinRot, cosTilt, sinTilt, now) {
    var v = this.homeVec;
    var rx = v.x * cosRot + v.z * sinRot;
    var ry = v.y;
    var rz = -v.x * sinRot + v.z * cosRot;
    var ryT = ry * cosTilt - rz * sinTilt;
    var rzT = ry * sinTilt + rz * cosTilt;

    if (rzT > 0) {
      var hScreenX = cx + rx * r;
      var hScreenY = cy - ryT * r;
      var pulse = (Math.sin(now * 0.005) + 1) / 2;

      ctx.save();
      ctx.strokeStyle = '#F59E0B'; // accent amber
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(hScreenX, hScreenY, 5 + pulse * 6, 0, Math.PI * 2);
      ctx.stroke();

      ctx.fillStyle = '#F59E0B';
      ctx.beginPath();
      ctx.arc(hScreenX, hScreenY, 2.5, 0, Math.PI * 2);
      ctx.fill();

      ctx.font = '10px "JetBrains Mono", monospace';
      ctx.fillStyle = '#F59E0B';
      ctx.fillText('NODE 01 [LOCAL]', hScreenX + 10, hScreenY - 4);
      ctx.restore();
    }
  };

  TacticalGlobe.prototype.renderFrame = function (now) {
    // 1. Detect dropped frames (> 1.5x interval: > 25ms)
    var dt = now - this.lastFrameStamp;
    this.lastFrameStamp = now;
    if (dt > 25) {
      this.droppedFrames++;
    }

    // 2. Instrument draw() execution cost specifically with performance.now()
    var t0 = performance.now();
    this.draw(now);
    var drawMs = performance.now() - t0;

    // Record draw metrics
    this.drawTimes.push(drawMs);
    if (this.drawTimes.length > 60) this.drawTimes.shift();

    if (this.benchmarkActive) {
      this.benchmarkFrames.push({
        drawMs: drawMs,
        dt: dt,
        tier: this.tier,
        dots: this.unitPoints.length,
        arcs: this.arcs.length
      });
    }

    // Check tier convergence
    this.checkPerformanceConvergence();

    // Update Telemetry & Dev Perf Overlay (?perf=1)
    if (this.elFps && Math.random() < 0.05) {
      var avgDt = this.drawTimes.reduce(function (a, b) { return a + b; }, 0) / this.drawTimes.length;
      var fps = Math.min(60, Math.round(1000 / Math.max(16.6, dt)));
      this.elFps.textContent = fps + ' FPS';
    }

    if (this.elLon && Math.random() < 0.1) {
      var deg = (((this.currentLon + this.dragLon) * (180 / Math.PI)) % 360).toFixed(1);
      this.elLon.textContent = deg + '°E';
    }

    if (this.isPerfMode && this.perfOverlay) {
      var sorted = this.drawTimes.slice().sort(function (a, b) { return a - b; });
      var p95 = sorted[Math.floor(sorted.length * 0.95)] || 0;
      var max = sorted[sorted.length - 1] || 0;
      var avg = (this.drawTimes.reduce(function (a, b) { return a + b; }, 0) / this.drawTimes.length) || 0;

      this.perfOverlay.innerHTML =
        'DRAW: ' + avg.toFixed(2) + 'ms | P95: ' + p95.toFixed(2) + 'ms | MAX: ' + max.toFixed(1) + 'ms<br>' +
        'TIER: ' + this.tier + ' (' + this.unitPoints.length + ' pts, ' + this.arcs.length + ' arcs)<br>' +
        'DROPPED: ' + this.droppedFrames + ' | LONG TASKS: ' + this.longTasksCount;
    }
  };

  TacticalGlobe.prototype.setTier = function (t) {
    this.tier = Math.max(0, Math.min(3, t));
    this.applyTierSettings();
    this.drawTimes = [];
  };

  TacticalGlobe.prototype.startBenchmark = function (targetTier) {
    if (typeof targetTier === 'number') {
      this.setTier(targetTier);
    }
    this.benchmarkActive = true;
    this.benchmarkFrames = [];
    this.droppedFrames = 0;
    this.longTasksCount = 0;
    // ensure max concurrency of arcs
    while (this.arcs.length < this.maxArcs) {
      this.spawnArc(this.arcs.length / Math.max(1, this.maxArcs));
    }
  };

  TacticalGlobe.prototype.stopBenchmark = function () {
    this.benchmarkActive = false;
    return {
      frames: this.benchmarkFrames,
      droppedFrames: this.droppedFrames,
      longTasks: this.longTasksCount,
      tier: this.tier,
      dots: this.unitPoints.length,
      arcs: this.arcs.length
    };
  };

  TacticalGlobe.prototype.start = function () {
    var self = this;
    function loop(now) {
      self.renderFrame(now);
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

    // Reduced Motion Safeguard: Render single frame, zero rAF loop
    var prefersReducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // Load Bit-Packed Binary Coordinate Deltas (6,928 bytes raw, 1,819 bytes gz)
    var binUrl = canvas.getAttribute('data-bin-url') || '/static/data/land_mask.bin';

    fetch(binUrl)
      .then(function (res) {
        if (!res.ok) throw new Error('Binary mask fetch error ' + res.status);
        return res.arrayBuffer();
      })
      .then(function (buffer) {
        // Delta unpack: 1732 coordinates
        var rawDeltas = new Int16Array(buffer);
        var len = rawDeltas.length;
        var points = [];
        var curLat = 0, curLon = 0;
        for (var i = 0; i < len; i += 2) {
          curLat += rawDeltas[i];
          curLon += rawDeltas[i + 1];
          points.push([curLat / 100, curLon / 100]);
        }

        var globe = new TacticalGlobe({
          canvas: canvas,
          points: points
        });

        // Store instance for testing & benchmarks
        window.__tacticalGlobe = globe;

        if (prefersReducedMotion) {
          globe.draw(performance.now());
          return;
        }

        // Default Kiosk Mode Layout & Continuous Spin
        document.body.classList.add('attract-mode');
        globe.initSize();
        globe.isPaused = false;
        globe.start();

        // Responsive Resize Handling via ResizeObserver
        if (typeof ResizeObserver !== 'undefined' && container) {
          var ro = new ResizeObserver(function () {
            globe.initSize();
          });
          ro.observe(container);
        } else {
          window.addEventListener('resize', function () {
            globe.initSize();
          });
        }
      })
      .catch(function (err) {
        console.warn('Globe canvas binary fallback:', err);
        if (poster) {
          poster.style.display = 'block';
          canvas.style.display = 'none';
        }
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initLandingGlobe);
  } else {
    initLandingGlobe();
  }

  global.TacticalGlobe = TacticalGlobe;
})(typeof window !== 'undefined' ? window : this);
