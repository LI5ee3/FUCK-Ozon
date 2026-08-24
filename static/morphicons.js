/**
 * Morphicons - Universal SVG Path Morphing with Apple Spring Physics
 * Uses official Lucide & Tabler canonical SVG subpaths with DOM geometric sampling.
 */

(function () {
  'use strict';

  // --- Spring Physics Config ---
  const SPRING_PRESETS = {
    snappy: { stiffness: 150, damping: 18 },
    bouncy: { stiffness: 130, damping: 11 },
    smooth: { stiffness: 100, damping: 16 }
  };

  // --- Canonical Official Icon Path Definitions (Lucide Icons System) ---
  const OFFICIAL_ICONS = {
    // Sun & Moon (Official Lucide definitions with independent absolute subpaths)
    sun: [
      "M12 2v2",
      "M12 20v2",
      "M2 12h2",
      "M20 12h2",
      "M4.93 4.93l1.41 1.41",
      "M17.66 17.66l1.41 1.41",
      "M4.93 19.07l1.41-1.41",
      "M17.66 6.34l1.41-1.41",
      "M12 8a4 4 0 1 0 0 8a4 4 0 0 0 0-8"
    ],
    moon: [
      "M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"
    ],

    // Navigation & App Icons (Lucide System Standard 24x24)
    dashboard: [
      "M4 4h7a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z",
      "M4 14h7a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-5a1 1 0 0 1 1-1Z",
      "M13 11h7a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1h-7a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1Z",
      "M13 4h7a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-7a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z"
    ],
    orders: [
      "M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z",
      "M3 6h18",
      "M16 10a4 4 0 0 1-8 0"
    ],
    risk: [
      "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z",
      "M12 8v4",
      "M12 16h.01"
    ],
    delivery: [
      "M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2",
      "M14 8h4.5a1 1 0 0 1 .8.4l3.2 4.3a1 1 0 0 1 .2.6V17a1 1 0 0 1-1 1h-1.5",
      "M7 18a2.5 2.5 0 1 0 0 .01",
      "M17 18a2.5 2.5 0 1 0 0 .01"
    ],
    returns: [
      "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8",
      "M3 3v5h5"
    ],
    stock: [
      "M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z",
      "M3.29 7L12 12l8.71-5",
      "M12 22V12",
      "M7.5 4.27l9 5.15"
    ],
    transfer: [
      "M17 3v18",
      "M21 7l-4-4-4 4",
      "M7 21V3",
      "M3 17l4 4 4-4"
    ],
    sync: [
      "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8",
      "M21 3v5h-5",
      "M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16",
      "M3 21v-5h5"
    ],
    rules: [
      "M21 4H14",
      "M10 4H3",
      "M14 2v4",
      "M21 12H12",
      "M8 12H3",
      "M8 10v4",
      "M21 20H8",
      "M4 20H3",
      "M8 18v4"
    ],
    dingtalk: [
      "M12 8V4H8",
      "M4 14a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z",
      "M2 14h2",
      "M20 14h2",
      "M9 16v.01",
      "M15 16v.01"
    ],
    robot: [
      "M12 8V4H8",
      "M4 14a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z",
      "M2 14h2",
      "M20 14h2",
      "M9 16v.01",
      "M15 16v.01"
    ],
    settings: [
      "M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2Z",
      "M12 9a3 3 0 1 0 0 6a3 3 0 0 0 0-6"
    ],

    chevronDown: [
      "M6 9l6 6 6-6"
    ],
    chevronUp: [
      "M6 15l6-6 6 6"
    ],
    chevronLeft: [
      "M15 18l-6-6 6-6"
    ],
    chevronRight: [
      "M9 18l6-6-6-6"
    ],
    calendar: [
      "M8 2v4",
      "M16 2v4",
      "M3 10h18",
      "M21 8.5V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8.5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z"
    ],
    sortUpDown: [
      "M17 4v16",
      "M21 16l-4 4-4-4",
      "M7 20V4",
      "M3 8l4-4 4 4"
    ],
    arrowUp: [
      "M12 19V5",
      "M5 12l7-7 7 7"
    ],
    arrowDown: [
      "M12 5v14",
      "M19 12l-7 7-7-7"
    ],
    check: [
      "M4 12l5 5L20 6"
    ],
    x: [
      "M6 6l12 12",
      "M6 18l12-12"
    ],
    plus: [
      "M12 5v14",
      "M5 12h14"
    ],
    minus: [
      "M5 12h14"
    ],
    copy: [
      "M8 4h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z",
      "M4 8v10a2 2 0 0 0 2 2h10"
    ],
    alertCircle: [
      "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z",
      "M12 8v4",
      "M12 16h.01"
    ],
    clock: [
      "M12 6v6l4 2",
      "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z"
    ],
    theme: [
      "M12 2v2",
      "M12 20v2",
      "M2 12h2",
      "M20 12h2",
      "M4.93 4.93l1.41 1.41",
      "M17.66 17.66l1.41 1.41",
      "M4.93 19.07l1.41-1.41",
      "M17.66 6.34l1.41-1.41",
      "M12 8a4 4 0 1 0 0 8a4 4 0 0 0 0-8"
    ],
    tag: [
      "M12 2H2v10l9.29 9.29a2.41 2.41 0 0 0 3.42 0l6.58-6.58a2.41 2.41 0 0 0 0-3.42L12 2Z",
      "M7 7h.01"
    ],
    gitMerge: [
      "M18 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
      "M6 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
      "M6 21V9",
      "M6 12a9 9 0 0 1 9 9"
    ],
    search: [
      "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16Z",
      "M21 21l-4.35-4.35"
    ],
    trash: [
      "M3 6h18",
      "M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6",
      "M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"
    ],
    edit: [
      "M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3Z"
    ],
    trendingUp: [
      "M22 7 13.5 15.5 8.5 10.5 2 17",
      "M16 7h6v6"
    ],
    barChart: [
      "M3 3v18h18",
      "M18 17V9",
      "M13 17V5",
      "M8 17v-3"
    ],
    package: [
      "M16.5 9.4 7.55 4.24",
      "M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z",
      "M3.29 7 12 12l8.71-5",
      "M12 22V12"
    ],
    alertTriangle: [
      "M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z",
      "M12 9v4",
      "M12 17h.01"
    ],
    percent: [
      "M19 5 5 19",
      "M6.5 9a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z",
      "M17.5 20a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z"
    ],
    flame: [
      "M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 3Z"
    ],
    messageSquare: [
      "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z"
    ],
    rotateCcw: [
      "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8",
      "M3 3v5h5"
    ],
    layers: [
      "M12 2 2 7l10 5 10-5-10-5Z",
      "M2 17l10 5 10-5",
      "M2 12l10 5 10-5"
    ],
    checkCircle: [
      "M22 11.08V12a10 10 0 1 1-5.93-9.14",
      "M22 4 12 14.01l-3-3"
    ],
    store: [
      "m2 7 4.41-4.41A2 2 0 0 1 7.83 2h8.34a2 2 0 0 1 1.42.59L22 7",
      "M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8",
      "M15 22v-4a2 2 0 0 0-2-2h-2a2 2 0 0 0-2 2v4",
      "M2 7h20"
    ],
    box: [
      "M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z",
      "m3.3 7 8.7 5 8.7-5",
      "M12 22V12"
    ],
    truck: [
      "M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2",
      "M14 8h4.5a1 1 0 0 1 .8.4l3.2 4.3a1 1 0 0 1 .2.6V17a1 1 0 0 1-1 1h-1.5",
      "M7 18a2.5 2.5 0 1 0 0 .01",
      "M17 18a2.5 2.5 0 1 0 0 .01"
    ],
    shoppingBag: [
      "M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z",
      "M3 6h18",
      "M16 10a4 4 0 0 1-8 0"
    ],
    alertOctagon: [
      "M7.86 2h8.28L22 7.86v8.28L16.14 22H7.86L2 16.14V7.86L7.86 2z",
      "M12 8v4",
      "M12 16h.01"
    ],
    fileWarning: [
      "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z",
      "M14 2v4a2 2 0 0 0 2 2h4",
      "M12 11v4",
      "M12 18h.01"
    ],
    userX: [
      "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2",
      "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z",
      "m17 8 5 5",
      "m22 8-5 5"
    ],
    shieldAlert: [
      "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z",
      "M12 8v4",
      "M12 16h.01"
    ],
    zap: [
      "M13 2 3 14h9l-1 8 10-12h-9l1-8Z"
    ],
    filter: [
      "M22 3H2l8 9.46V19l4 2v-8.54L22 3Z"
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

  // Parse official SVG subpaths array or string into geometrically resampled point strokes
  function parseAndSample(input, samplePointsPerStroke = 28) {
    const key = Array.isArray(input) ? input.join('|') : String(input);
    const cacheKey = `${key}_${samplePointsPerStroke}`;
    if (pointCache.has(cacheKey)) {
      return pointCache.get(cacheKey);
    }

    const helper = getHelperPath();
    if (!helper) return [];

    let subpaths = [];
    if (Array.isArray(input)) {
      subpaths = input;
    } else if (typeof input === 'string') {
      subpaths = input.match(/[Mm][^Mm]*/g) || [input];
    }

    const strokes = [];
    for (const sub of subpaths) {
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

  function resolveIcon(input) {
    if (typeof input === 'string') {
      if (OFFICIAL_ICONS[input]) {
        return parseAndSample(OFFICIAL_ICONS[input]);
      }
      if (input.includes('M') || input.includes('m')) {
        return parseAndSample(input);
      }
    } else if (Array.isArray(input)) {
      return parseAndSample(input);
    }
    return parseAndSample(OFFICIAL_ICONS.sun || OFFICIAL_ICONS.dashboard);
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

    set(icon) {
      this.currentStrokes = cloneStrokes(resolveIcon(icon));
      this.targetStrokes = cloneStrokes(this.currentStrokes);
      this.velocities = this.currentStrokes.map(stroke => stroke.map(() => [0, 0]));
      this.animating = false;
      this.render();
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

    set(icon) {
      if (this._controller) {
        this._controller.set(icon);
      } else {
        this.setAttribute('icon', icon);
      }
    }
  }

  function defineMorphIcon(tagName = 'morph-icon') {
    if (typeof customElements !== 'undefined' && !customElements.get(tagName)) {
      customElements.define(tagName, MorphIconElement);
    }
  }

  defineMorphIcon();

  window.Morphicons = {
    createMorph: (svgEl, initialIcon, options) => new MorphController(svgEl, initialIcon, options),
    icons: OFFICIAL_ICONS,
    defineMorphIcon,
    MorphController
  };
})();
