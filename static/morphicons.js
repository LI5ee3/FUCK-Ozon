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

  // --- Canonical Official Icon Path Definitions (Lucide & Tabler) ---
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

    // Navigation & App Icons
    dashboard: [
      "M5 4h4a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z",
      "M5 16h4a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-2a1 1 0 0 1 1-1Z",
      "M15 12h4a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1h-4a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1Z",
      "M15 4h4a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1h-4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z"
    ],
    orders: [
      "M6.33 8h11.34a2 2 0 0 1 1.98 2.3l-1.26 8.16A3 3 0 0 1 15.43 21H8.57a3 3 0 0 1-2.96-2.54L4.35 10.3A2 2 0 0 1 6.33 8Z",
      "M9 11V6a3 3 0 0 1 6 0v5"
    ],
    risk: [
      "M10.36 3.59L2.26 17.13a1.91 1.91 0 0 0 1.64 2.87h16.2a1.91 1.91 0 0 0 1.64-2.87L13.64 3.59a1.91 1.91 0 0 0-3.28 0Z",
      "M12 9v4",
      "M12 16.5v.5"
    ],
    delivery: [
      "M5 17a2 2 0 1 0 4 0 2 2 0 1 0-4 0",
      "M15 17a2 2 0 1 0 4 0 2 2 0 1 0-4 0",
      "M5 17H3v-4M2 5h11v12M9 17h6M19 17h2v-6h-8M13 6h5l3 5M3 9h4"
    ],
    returns: [
      "M9 14l-4-4 4-4",
      "M5 10h11a4 4 0 1 1 0 8h-1"
    ],
    stock: [
      "M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3Z",
      "M12 12l8-4.5",
      "M12 12v9",
      "M12 12L4 7.5"
    ],
    transfer: [
      "M7 10h14l-4-4",
      "M17 14H3l4 4"
    ],
    sync: [
      "M20 11A8.1 8.1 0 0 0 4.5 9M4 5v4h4",
      "M4 13a8.1 8.1 0 0 0 15.5 2m.5 4v-4h-4"
    ],
    rules: [
      "M4 6h8M16 6h4",
      "M12 6a2 2 0 1 0 4 0 2 2 0 1 0-4 0",
      "M4 12h2M10 12h10",
      "M6 12a2 2 0 1 0 4 0 2 2 0 1 0-4 0",
      "M4 18h11M19 18h1",
      "M15 18a2 2 0 1 0 4 0 2 2 0 1 0-4 0"
    ],
    dingtalk: [
      "M9 7h6a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2Z",
      "M12 7V4",
      "M9 4h6",
      "M10 12v.01",
      "M14 12v.01",
      "M10 16h4"
    ],
    robot: [
      "M9 7h6a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2Z",
      "M12 7V4",
      "M9 4h6",
      "M10 12v.01",
      "M14 12v.01",
      "M10 16h4"
    ],
    settings: [
      "M10.33 4.32c.42-1.76 2.92-1.76 3.34 0a1.72 1.72 0 0 0 2.57 1.07c1.55-.94 3.32.83 2.38 2.37a1.72 1.72 0 0 0 1.06 2.57c1.76.43 1.76 2.93 0 3.35a1.72 1.72 0 0 0-1.06 2.58c.94 1.54-.83 3.3-2.38 2.37a1.72 1.72 0 0 0-2.57 1.06c-.42 1.76-2.92 1.76-3.34 0a1.72 1.72 0 0 0-2.58-1.06c-1.54.93-3.3-.83-2.37-2.37a1.72 1.72 0 0 0-1.06-2.58c-1.76-.42-1.76-2.92 0-3.35a1.72 1.72 0 0 0 1.06-2.57c-.93-1.54.83-3.31 2.37-2.37 1 .6 2.3.07 2.58-1.07Z",
      "M9 12a3 3 0 1 0 6 0 3 3 0 0 0-6 0"
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
      "M7 15l5 5 5-5",
      "M7 9l5-5 5 5"
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
      "M8 4h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z",
      "M4 8v10a2 2 0 0 0 2 2h10"
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
