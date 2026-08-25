/**
 * Morphicons - Universal SVG Path Morphing with Apple Spring Physics
 * Canonical Tabler Icons SVG subpaths with DOM geometric sampling.
 */

(function () {
  'use strict';

  // --- Spring Physics Config ---
  const SPRING_PRESETS = {
    snappy: { stiffness: 150, damping: 18 }
  };

  // --- Canonical Official Icon Path Definitions (Tabler Icons System 24x24) ---
  const OFFICIAL_ICONS = {
    // Theme
    sun: [
      "M12 12m-4 0a4 4 0 1 0 8 0a4 4 0 1 0 -8 0",
      "M3 12h1", "M12 3v1", "M20 12h1", "M12 20v1",
      "M5.6 5.6l.7 .7", "M17.7 5.6l-.7 .7", "M17.7 17.7l.7 .7", "M5.6 17.7l-.7 .7"
    ],
    moon: [
      "M12 3c.132 0 .263 0 .393 0a7.5 7.5 0 0 0 7.92 12.446a9 9 0 1 1 -8.313 -12.454z"
    ],

    // Navigation & Main Modules
    dashboard: [
      "M4 4h6v8h-6z",
      "M4 16h6v4h-6z",
      "M14 12h6v8h-6z",
      "M14 4h6v4h-6z"
    ],
    orders: [
      "M6.33 8h11.34a2 2 0 0 1 1.98 2.3l-1.26 8.15a3 3 0 0 1 -2.97 2.55h-6.85a3 3 0 0 1 -2.97 -2.55l-1.25 -8.15a2 2 0 0 1 1.98 -2.3z",
      "M9 11v-5a3 3 0 0 1 6 0v5"
    ],
    risk: [
      "M12 3a12 12 0 0 0 8.5 3a12 12 0 0 1 -8.5 15a12 12 0 0 1 -8.5 -15a12 12 0 0 0 8.5 -3",
      "M12 8v4",
      "M12 16h.01"
    ],
    delivery: [
      "M7 17m-2 0a2 2 0 1 0 4 0a2 2 0 1 0 -4 0",
      "M17 17m-2 0a2 2 0 1 0 4 0a2 2 0 1 0 -4 0",
      "M5 17h-2v-4m-1 -8h11v12m-4 0h6m4 0h2v-6h-8m0 -5h5l3 5",
      "M3 9h4"
    ],
    returns: [
      "M9 14l-4 -4l4 -4",
      "M5 10h11a4 4 0 1 1 0 8h-1"
    ],
    messageSquareAlert: [
      "M18 4a3 3 0 0 1 3 3v8a3 3 0 0 1 -3 3h-5l-5 3v-3h-2a3 3 0 0 1 -3 -3v-8a3 3 0 0 1 3 -3h12z",
      "M12 8v3",
      "M12 14v.01"
    ],
    stock: [
      "M7 16.5l-5 -3l5 -3l5 3v5.5l-5 3z",
      "M2 13.5v5.5l5 3",
      "M7 10.5v5.5",
      "M17 16.5l-5 -3l5 -3l5 3v5.5l-5 3z",
      "M12 13.5v5.5l5 3",
      "M17 10.5v5.5",
      "M12 7.5l-5 -3l5 -3l5 3v5.5l-5 3z",
      "M7 4.5v5.5l5 3",
      "M12 1.5v5.5"
    ],
    transfer: [
      "M7 10h14l-4 -4",
      "M17 14h-14l4 4"
    ],
    sync: [
      "M20 11a8.1 8.1 0 0 0 -15.5 -2m-.5 -4v5h5",
      "M4 13a8.1 8.1 0 0 0 15.5 2m.5 4v-5h-5"
    ],
    rules: [
      "M14 6m-2 0a2 2 0 1 0 4 0a2 2 0 1 0 -4 0",
      "M4 6h8", "M16 6h4",
      "M8 12m-2 0a2 2 0 1 0 4 0a2 2 0 1 0 -4 0",
      "M4 12h2", "M10 12h10",
      "M17 18m-2 0a2 2 0 1 0 4 0a2 2 0 1 0 -4 0",
      "M4 18h11", "M19 18h1"
    ],
    dingtalk: [
      "M7 7h10a2 2 0 0 1 2 2v1l1 1v3l-1 1v3a2 2 0 0 1 -2 2h-10a2 2 0 0 1 -2 -2v-3l-1 -1v-3l1 -1v-1a2 2 0 0 1 2 -2z",
      "M10 16h4",
      "M9 11v.01",
      "M15 11v.01",
      "M12 4v3"
    ],
    settings: [
      "M10.325 4.317c.426 -1.756 2.924 -1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543 -.94 3.31 .826 2.37 2.37a1.724 1.724 0 0 0 1.065 2.572c1.756 .426 1.756 2.924 0 3.35a1.724 1.724 0 0 0 -1.066 2.573c.94 1.543 -.826 3.31 -2.37 2.37a1.724 1.724 0 0 0 -2.572 1.065c-.426 1.756 -2.924 1.756 -3.35 0a1.724 1.724 0 0 0 -2.573 -1.066c-1.543 .94 -3.31 -.826 -2.37 -2.37a1.724 1.724 0 0 0 -1.065 -2.572c-1.756 -.426 -1.756 -2.924 0 -3.35a1.724 1.724 0 0 0 1.066 -2.573c-.94 -1.543 .826 -3.31 2.37 -2.37c1 .608 2.296 .07 2.572 -1.065z",
      "M9 12a3 3 0 1 0 6 0a3 3 0 0 0 -6 0"
    ],
    store: [
      "M3 21l18 0",
      "M3 7v1a3 3 0 0 0 6 0v-1m0 1a3 3 0 0 0 6 0v-1m0 1a3 3 0 0 0 6 0v-1h-18l2 -4h14l2 4",
      "M5 21v-10.15",
      "M19 21v-10.15",
      "M9 21v-4a2 2 0 0 1 2 -2h2a2 2 0 0 1 2 2v4"
    ],

    // UI Controls & Navigation
    chevronDown: ["M6 9l6 6l6 -6"],
    chevronUp: ["M6 15l6 -6l6 6"],
    chevronLeft: ["M15 6l-6 6l6 6"],
    chevronRight: ["M9 6l6 6l-6 6"],
    calendar: [
      "M4 7a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2v-12z",
      "M16 3v4",
      "M8 3v4",
      "M4 11h16"
    ],
    sortUpDown: [
      "M3 9l4 -4l4 4m-4 -4v14",
      "M21 15l-4 4l-4 -4m4 4v-14"
    ],
    arrowUp: [
      "M12 5v14",
      "M18 11l-6 -6",
      "M6 11l6 -6"
    ],
    arrowDown: [
      "M12 5v14",
      "M18 13l-6 6",
      "M6 13l6 6"
    ],

    // Actions & Feedback
    check: ["M5 12l5 5l10 -10"],
    x: [
      "M18 6l-12 12",
      "M6 6l12 12"
    ],
    plus: [
      "M12 5v14",
      "M5 12h14"
    ],
    copy: [
      "M7 7m0 2.67a2.67 2.67 0 0 1 2.67 -2.67h8.66a2.67 2.67 0 0 1 2.67 2.67v8.66a2.67 2.67 0 0 1 -2.67 2.67h-8.66a2.67 2.67 0 0 1 -2.67 -2.67z",
      "M4.01 16.74a2 2 0 0 1 -1.01 -1.74v-10c0 -1.1 .9 -2 2 -2h10c.75 0 1.16 .39 1.5 1"
    ],
    alertCircle: [
      "M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0",
      "M12 8v4",
      "M12 16h.01"
    ],
    alertTriangle: [
      "M12 9v4",
      "M12 16h.01",
      "M10.24 3.96l-8.43 14.37a1.08 1.08 0 0 0 .93 1.67h18.52a1.08 1.08 0 0 0 .93 -1.67l-8.43 -14.37a1.08 1.08 0 0 0 -1.86 0z"
    ],
    alertOctagon: [
      "M12 8v4",
      "M12 16h.01",
      "M8.7 3h6.6c.3 0 .5 .1 .7 .3l4.7 4.7c.2 .2 .3 .4 .3 .7v6.6c0 .3 -.1 .5 -.3 .7l-4.7 4.7c-.2 .2 -.4 .3 -.7 .3h-6.6c-.3 0 -.5 -.1 -.7 -.3l-4.7 -4.7c-.2 -.2 -.3 -.4 -.3 -.7v-6.6c0 -.3 .1 -.5 .3 -.7l4.7 -4.7c.2 -.2 .4 -.3 .7 -.3z"
    ],
    clock: [
      "M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0",
      "M12 7v5l3 3"
    ],
    tag: [
      "M7.5 7.5m-1 0a1 1 0 1 0 2 0a1 1 0 1 0 -2 0",
      "M3 6v5.17a2 2 0 0 0 .59 1.41l7.71 7.71a2.41 2.41 0 0 0 3.41 0l5.59 -5.59a2.41 2.41 0 0 0 0 -3.41l-7.71 -7.71a2 2 0 0 0 -1.41 -.59h-5.17a3 3 0 0 0 -3 3z"
    ],
    gitMerge: [
      "M7 18m-2 0a2 2 0 1 0 4 0a2 2 0 1 0 -4 0",
      "M7 6m-2 0a2 2 0 1 0 4 0a2 2 0 1 0 -4 0",
      "M17 12m-2 0a2 2 0 1 0 4 0a2 2 0 1 0 -4 0",
      "M7 8v8",
      "M7 14a5 5 0 0 0 5 5h1a2 2 0 0 0 2 -2v-3"
    ],
    search: [
      "M10 10m-7 0a7 7 0 1 0 14 0a7 7 0 1 0 -14 0",
      "M21 21l-6 -6"
    ],
    trash: [
      "M4 7h16",
      "M10 11v6",
      "M14 11v6",
      "M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2 -2l1 -12",
      "M9 7v-3a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v3"
    ],
    edit: [
      "M4 20h4l10.5 -10.5a2.83 2.83 0 1 0 -4 -4l-10.5 10.5v4",
      "M13.5 6.5l4 4"
    ],
    trendingUp: [
      "M3 17l6 -6l4 4l8 -8",
      "M14 7h7v7"
    ],
    barChart: [
      "M3 12m0 1a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v6a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1z",
      "M9 8m0 1a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v10a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1z",
      "M15 4m0 1a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v14a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1z",
      "M4 20h14"
    ],
    package: [
      "M12 3l8 4.5v9l-8 4.5l-8 -4.5v-9l8 -4.5",
      "M12 12l8 -4.5",
      "M12 12v9",
      "M12 12l-8 -4.5",
      "M16 5.25l-8 4.5"
    ],
    percent: [
      "M17 17m-1 0a1 1 0 1 0 2 0a1 1 0 1 0 -2 0",
      "M7 7m-1 0a1 1 0 1 0 2 0a1 1 0 1 0 -2 0",
      "M6 18l12 -12"
    ],
    flame: [
      "M12 12c2 -2.96 0 -7 -1 -8c0 3.04 -1.77 4.74 -3 6c-1.23 1.26 -2 3.24 -2 5a6 6 0 1 0 12 0c0 -1.53 -.77 -2.74 -2 -4c-1 2.5 -2 3.5 -4 1z"
    ],
    messageSquare: [
      "M18 4a3 3 0 0 1 3 3v8a3 3 0 0 1 -3 3h-5l-5 3v-3h-2a3 3 0 0 1 -3 -3v-8a3 3 0 0 1 3 -3h12z",
      "M8 9h8",
      "M8 13h6"
    ],
    rotateCcw: [
      "M4.05 11a8 8 0 1 1 .5 4m-.5 5v-5h5"
    ],
    layers: [
      "M12 4l-8 4l8 4l8 -4l-8 -4",
      "M4 12l8 4l8 -4",
      "M4 16l8 4l8 -4"
    ],
    checkCircle: [
      "M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0",
      "M9 12l2 2l4 -4"
    ],
    box: [
      "M12 3l8 4.5v9l-8 4.5l-8 -4.5v-9l8 -4.5",
      "M12 12l8 -4.5",
      "M12 12v9",
      "M12 12l-8 -4.5"
    ],
    truck: [
      "M7 17m-2 0a2 2 0 1 0 4 0a2 2 0 1 0 -4 0",
      "M17 17m-2 0a2 2 0 1 0 4 0a2 2 0 1 0 -4 0",
      "M5 17h-2v-11a1 1 0 0 1 1 -1h9v12m-4 0h6m4 0h2v-6h-8m0 -5h5l3 5"
    ],
    shoppingBag: [
      "M6.33 8h11.34a2 2 0 0 1 1.98 2.3l-1.26 8.15a3 3 0 0 1 -2.97 2.55h-6.85a3 3 0 0 1 -2.97 -2.55l-1.25 -8.15a2 2 0 0 1 1.98 -2.3z",
      "M9 11v-5a3 3 0 0 1 6 0v5"
    ],
    userX: [
      "M8 7a4 4 0 1 0 8 0a4 4 0 0 0 -8 0",
      "M6 21v-2a4 4 0 0 1 4 -4h3.5",
      "M22 22l-5 -5",
      "M17 22l5 -5"
    ],
    shieldAlert: [
      "M12 3a12 12 0 0 0 8.5 3a12 12 0 0 1 -8.5 15a12 12 0 0 1 -8.5 -15a12 12 0 0 0 8.5 -3",
      "M12 8v4",
      "M12 16h.01"
    ],
    zap: [
      "M13 3v7h6l-8 11v-7h-6l8 -11"
    ],
    award: [
      "M12 9m-6 0a6 6 0 1 0 12 0a6 6 0 1 0 -12 0",
      "M12 15l3.4 5.89l1.598 -3.233l3.598 .232l-3.4 -5.889",
      "M6.802 12l-3.4 5.89l3.598 -.233l1.598 3.232l3.4 -5.889"
    ],
    bolt: [
      "M13 3l0 7l6 0l-8 11l0 -7l-6 0z"
    ],
    shieldCheck: [
      "M12 3a12 12 0 0 0 8.5 3a12 12 0 0 1 -8.5 15a12 12 0 0 1 -8.5 -15a12 12 0 0 0 8.5 -3",
      "M9 12l2 2l4 -4"
    ],
    xCircle: [
      "M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0",
      "M10 10l4 4m0 -4l-4 4"
    ]
  };

  const pointCache = new Map();
  let helperPathEl = null;

  function getHelperPath() {
    if (typeof document === 'undefined') return null;
    if (!helperPathEl) {
      let svg = document.getElementById('__morphicons_helper_svg__');
      if (!svg) {
        svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.id = '__morphicons_helper_svg__';
        svg.setAttribute('style', 'position:fixed;top:-9999px;left:-9999px;width:100px;height:100px;opacity:0;pointer-events:none;');
        (document.body || document.documentElement).appendChild(svg);
      }
      helperPathEl = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      svg.appendChild(helperPathEl);
    }
    return helperPathEl;
  }

  function cloneStrokes(strokes) {
    return strokes.map(stroke => stroke.map(pt => [pt[0], pt[1]]));
  }

  // Parse official SVG subpaths into geometrically resampled point strokes
  function parseAndSample(input, samplePointsPerStroke = 28) {
    const key = input.join('|');
    const cacheKey = `${key}_${samplePointsPerStroke}`;
    if (pointCache.has(cacheKey)) {
      return pointCache.get(cacheKey);
    }

    const helper = getHelperPath();
    if (!helper) return [];

    const strokes = [];
    for (const sub of input) {
      helper.setAttribute('d', sub.trim());
      const totalLen = helper.getTotalLength();
      const pts = [];

      if (totalLen <= 0.05) {
        const nums = sub.match(/-?[\d.]+/g);
        const x = nums ? parseFloat(nums[0]) : 12;
        const y = nums && nums[1] ? parseFloat(nums[1]) : 12;
        for (let i = 0; i < samplePointsPerStroke; i++) {
          pts.push([x, y]);
        }
      } else {
        for (let i = 0; i < samplePointsPerStroke; i++) {
          const dist = (i / (samplePointsPerStroke - 1)) * totalLen;
          const p = helper.getPointAtLength(dist);
          pts.push([Number(p.x.toFixed(2)), Number(p.y.toFixed(2))]);
        }
      }
      strokes.push(pts);
    }

    pointCache.set(cacheKey, strokes);
    return strokes;
  }

  function resolveIcon(name) {
    return parseAndSample(OFFICIAL_ICONS[name] || OFFICIAL_ICONS.sun);
  }

  function serializePath(strokes) {
    return strokes
      .map(pts => {
        if (!pts || pts.length === 0) return '';
        const d = [`M ${pts[0][0].toFixed(2)} ${pts[0][1].toFixed(2)}`];
        for (let i = 1; i < pts.length; i++) {
          d.push(`L ${pts[i][0].toFixed(2)} ${pts[i][1].toFixed(2)}`);
        }
        return d.join(' ');
      })
      .filter(Boolean)
      .join(' ');
  }

  // --- Morph Controller (Spring Physics Driver) ---
  class MorphController {
    constructor(svgElement, initialIcon = 'sun', options = {}) {
      this.svg = svgElement;
      this.options = Object.assign({ spring: 'snappy', size: 20, strokeWidth: 1.5, color: 'currentColor' }, options);
      this.springConfig = SPRING_PRESETS[this.options.spring] || SPRING_PRESETS.snappy;
      
      this.currentStrokes = cloneStrokes(resolveIcon(initialIcon));
      this.targetStrokes = cloneStrokes(this.currentStrokes);
      this.velocities = this.currentStrokes.map(stroke => stroke.map(() => [0, 0]));
      this.animating = false;
      this.lastTimestamp = 0;

      this.pathEl = this.svg.querySelector('path');
      if (!this.pathEl) {
        this.pathEl = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        this.svg.appendChild(this.pathEl);
      }

      this.svg.setAttribute('viewBox', '0 0 24 24');
      this.svg.setAttribute('width', this.options.size);
      this.svg.setAttribute('height', this.options.size);
      this.svg.setAttribute('fill', 'none');
      this.svg.setAttribute('stroke', this.options.color);
      this.svg.setAttribute('stroke-width', this.options.strokeWidth);
      this.svg.setAttribute('stroke-linecap', 'round');
      this.svg.setAttribute('stroke-linejoin', 'round');

      this.render();
    }

    morphTo(targetIcon, springPreset) {
      if (springPreset && SPRING_PRESETS[springPreset]) {
        this.springConfig = SPRING_PRESETS[springPreset];
      }
      const rawTarget = resolveIcon(targetIcon);
      const newTarget = cloneStrokes(rawTarget);
      
      // Equalize stroke counts between current and target
      const maxStrokes = Math.max(this.currentStrokes.length, newTarget.length);
      while (this.currentStrokes.length < maxStrokes) {
        const last = this.currentStrokes[this.currentStrokes.length - 1] || [[12, 12]];
        const collapsed = last.map(p => [p[0], p[1]]);
        this.currentStrokes.push(collapsed);
        this.velocities.push(collapsed.map(() => [0, 0]));
      }
      while (newTarget.length < maxStrokes) {
        const last = newTarget[newTarget.length - 1] || [[12, 12]];
        newTarget.push(last.map(p => [p[0], p[1]]));
      }

      this.targetStrokes = newTarget;

      if (!this.animating) {
        this.animating = true;
        this.lastTimestamp = performance.now();
        requestAnimationFrame(this.step.bind(this));
      }
    }

    step(timestamp) {
      if (!this.animating) return;

      const dt = Math.min((timestamp - this.lastTimestamp) / 1000, 0.032);
      this.lastTimestamp = timestamp;

      const { stiffness, damping } = this.springConfig;
      let totalDisplacement = 0;
      let totalVelocity = 0;

      for (let s = 0; s < this.currentStrokes.length; s++) {
        const curStroke = this.currentStrokes[s];
        const tgtStroke = this.targetStrokes[s];
        const velStroke = this.velocities[s];

        for (let p = 0; p < curStroke.length; p++) {
          const cur = curStroke[p];
          const tgt = tgtStroke[p];
          const vel = velStroke[p];

          // 2D Spring physics
          const fx = -stiffness * (cur[0] - tgt[0]) - damping * vel[0];
          const fy = -stiffness * (cur[1] - tgt[1]) - damping * vel[1];

          vel[0] += fx * dt;
          vel[1] += fy * dt;
          cur[0] += vel[0] * dt;
          cur[1] += vel[1] * dt;

          totalDisplacement += Math.hypot(cur[0] - tgt[0], cur[1] - tgt[1]);
          totalVelocity += Math.hypot(vel[0], vel[1]);
        }
      }

      this.render();

      if (totalDisplacement < 0.04 && totalVelocity < 0.04) {
        this.currentStrokes = cloneStrokes(this.targetStrokes);
        this.animating = false;
        this.render();
      } else {
        requestAnimationFrame(this.step.bind(this));
      }
    }

    render() {
      if (this.pathEl) {
        this.pathEl.setAttribute('d', serializePath(this.currentStrokes));
      }
    }
  }

  // --- Web Component <morph-icon> ---
  class MorphIconElement extends HTMLElement {
    static get observedAttributes() {
      return ['icon', 'spring', 'size', 'color', 'stroke-width'];
    }

    connectedCallback() {
      if (!this.shadowRoot) {
        this.attachShadow({ mode: 'open' });
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.style.display = 'block';
        svg.style.overflow = 'visible';
        this.shadowRoot.appendChild(svg);

        const initialIcon = this.getAttribute('icon') || 'sun';
        const size = this.getAttribute('size') || '20';
        const spring = this.getAttribute('spring') || 'snappy';
        const color = this.getAttribute('color') || 'currentColor';
        const strokeWidth = this.getAttribute('stroke-width') || '1.5';

        this._controller = new MorphController(svg, initialIcon, {
          size,
          spring,
          color,
          strokeWidth
        });
      }
    }

    attributeChangedCallback(name, oldValue, newValue) {
      if (!this._controller || oldValue === newValue) return;
      if (name === 'icon') {
        this._controller.morphTo(newValue);
      }
    }

    morphTo(icon, spring) {
      if (this._controller) {
        this._controller.morphTo(icon, spring);
      } else {
        this.setAttribute('icon', icon);
      }
    }

  }

  if (typeof customElements !== 'undefined' && !customElements.get('morph-icon')) {
    customElements.define('morph-icon', MorphIconElement);
  }
})();
