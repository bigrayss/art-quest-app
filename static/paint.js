/* ArtQuest 专业版画笔引擎  paint/1
 *
 * 一份代码，两处跑：浏览器里画，Node 里按日志重放（tools/replay_paint.js）。
 * 重放要和当时画出来的**逐像素一致**，所以这个文件守三条规矩：
 *
 *   1. 像素全是自己算的，放在 typed array 里。不调 Canvas2D 画任何东西——
 *      各家浏览器的抗锯齿不一样，调了就对不上。
 *   2. 不用 Math.sin / cos / atan2 / pow / exp / log：规范不保证它们在不同引擎里
 *      逐位相同。只用 + - * / 和 Math.sqrt（IEEE 754 规定了精确结果）。
 *   3. 不看时钟、不看帧率、不用 Math.random。随机数全部来自每一笔记进日志的 seed。
 *
 * 改了任何会影响像素的东西（画笔参数也算）→ 升 ENGINE 版本号，旧日志按旧版本重放。
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.Paint = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";
  const ENGINE = "paint/1";
  const TILE = 64;                       // 撤销按 64×64 的小块存，只存动过的
  const GRAIN = 256;                     // 纸纹是一张 256×256 可平铺的高度图
  const HISTORY_BYTES = 160 * 1024 * 1024;
  const HISTORY_STEPS = 60;

  const clamp = (v, a, b) => v < a ? a : (v > b ? b : v);
  const lerp = (a, b, t) => a + (b - a) * t;

  // ---- 确定性的随机：整数哈希，不同引擎结果一样 ----
  function hash2(x, y, seed) {
    let h = (Math.imul(x | 0, 0x27d4eb2d) ^ Math.imul(y | 0, 0x165667b1) ^ Math.imul(seed | 0, 0x9e3779b1)) | 0;
    h = Math.imul(h ^ (h >>> 15), 0x85ebca6b); h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35);
    return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
  }
  function rng(seed) {
    let s = (seed | 0) || 1;
    return () => { s ^= s << 13; s ^= s >>> 17; s ^= s << 5; return (s >>> 0) / 4294967296; };
  }
  /** 平铺的值噪声：period 个格点一循环 */
  function vnoise(x, y, period, seed) {
    const xi = Math.floor(x), yi = Math.floor(y), fx = x - xi, fy = y - yi;
    const u = fx * fx * (3 - 2 * fx), v = fy * fy * (3 - 2 * fy);
    const m = (n) => ((n % period) + period) % period;
    const a = hash2(m(xi), m(yi), seed), b = hash2(m(xi + 1), m(yi), seed);
    const c = hash2(m(xi), m(yi + 1), seed), d = hash2(m(xi + 1), m(yi + 1), seed);
    return lerp(lerp(a, b, u), lerp(c, d, u), v);
  }
  /** 三张纸：细纹（素描纸）、粗纹（炭笔纸）、宣纸纤维。值域 0..1，1 = 纸面的凸起。 */
  const _grains = {};
  function grain(kind) {
    if (_grains[kind]) return _grains[kind];
    const g = new Float32Array(GRAIN * GRAIN);
    for (let y = 0; y < GRAIN; y++) for (let x = 0; x < GRAIN; x++) {
      let v;
      if (kind === "fine") {
        v = 0.5 * hash2(x, y, 11) + 0.3 * vnoise(x / 2, y / 2, 128, 12) + 0.2 * vnoise(x / 5, y / 5, 51.2 | 0 || 51, 13);
      } else if (kind === "rough") {
        v = 0.3 * hash2(x, y, 21) + 0.4 * vnoise(x / 2.5, y / 2.5, 102, 22) + 0.3 * vnoise(x / 8, y / 8, 32, 23);
      } else {                        // "fiber"：横向拉长的纤维
        v = 0.25 * hash2(x, y, 31) + 0.45 * vnoise(x / 8, y / 1.6, 32, 32) + 0.3 * vnoise(x / 3, y / 6, 85, 33);
      }
      g[y * GRAIN + x] = v;
    }
    // 拉满到 0..1：不同噪声叠出来的范围不一样，画笔参数不该跟着变
    let lo = 1, hi = 0;
    for (let i = 0; i < g.length; i++) { if (g[i] < lo) lo = g[i]; if (g[i] > hi) hi = g[i]; }
    for (let i = 0; i < g.length; i++) g[i] = (g[i] - lo) / (hi - lo);
    return (_grains[kind] = g);
  }

  /* ---------- 画笔 ----------
   * size      画笔直径（画布像素）乘的倍数
   * spacing   两个印之间隔多远（半径的倍数）
   * hard      0 = 从中心就开始变淡，1 = 硬边
   * flow      一个印放下多少
   * pSize / pFlow   压力对粗细 / 浓淡的影响（0 = 不管，1 = 全靠压力）
   * tilt      笔放倒时变粗变淡的程度（侧锋铺调子）
   * grain / grainAmt / grainK   用哪张纸、纸纹多明显、多脆
   * bristle   笔毛：干的时候拉出飞白
   * wet       收笔时往外洇多远（像素，按笔的大小缩放）
   * mode      "mask" 一笔之内浓度统一、收笔才落到图层；"paint" 直接落、会带起底下的颜色
   */
  const BRUSHES = {
    pencil:   { name: "素描铅笔", mode: "mask", size: 0.5, spacing: 0.12, hard: 0.35, flow: 0.42, pSize: 0.25, pFlow: 0.9,
                tilt: 2.4, grain: "fine", grainAmt: 0.95, grainK: 2.4, smooth: 0.65, sim: 0.6, maxA: 0.92 },
    charcoal: { name: "炭笔", mode: "mask", size: 2.2, spacing: 0.1, hard: 0.55, flow: 0.5, pSize: 0.35, pFlow: 0.85,
                tilt: 1.6, grain: "rough", grainAmt: 1, grainK: 2.2, smooth: 0.6, sim: 0.6, maxA: 0.97 },
    ink:      { name: "毛笔", mode: "mask", size: 2.6, spacing: 0.06, hard: 0.72, flow: 1, pSize: 0.92, pFlow: 0.1,
                grain: "fiber", grainAmt: 0.18, grainK: 2, bristle: 0.85, load: 1400, wet: 0.05, edge: 0.12,
                smooth: 0.45, sim: "speed", taper: 1, maxA: 1 },
    wash:     { name: "淡墨", mode: "mask", size: 5, spacing: 0.07, hard: 0.5, flow: 0.55, pSize: 0.7, pFlow: 0.3,
                grain: "fiber", grainAmt: 0.25, grainK: 1.4, bristle: 0.35, load: 2600, wet: 0.12, edge: 0.45,
                smooth: 0.45, sim: "speed", taper: 1, maxA: 0.62 },
    oil:      { name: "油画笔", mode: "paint", size: 4, spacing: 0.07, hard: 0.93, flow: 0.9, pSize: 0.35, pFlow: 0.35,
                bristle: 0.5, load: 1800, pickup: 0.5, relief: 0.11, smooth: 0.55, sim: 0.7, maxA: 1 },
    eraser:   { name: "橡皮", mode: "mask", erase: true, size: 3, spacing: 0.1, hard: 0.6, flow: 1, pSize: 0.4, pFlow: 0.3,
                smooth: 0.8, sim: 0.7, maxA: 1 },
  };

  function parseColor(hex) {
    let h = String(hex || "#000").replace("#", "");
    if (h.length === 3) h = h.split("").map(c => c + c).join("");
    return [parseInt(h.slice(0, 2), 16) || 0, parseInt(h.slice(2, 4), 16) || 0, parseInt(h.slice(4, 6), 16) || 0];
  }

  // =====================================================================
  function Doc(spec) {
    this.engine = ENGINE;
    this.w = spec.width | 0; this.h = spec.height | 0;
    this.bg = parseColor(spec.background || "#ffffff");
    this.layers = [];                  // 从下到上
    this.mask = new Float32Array(this.w * this.h);   // 当前这一笔
    this.stroke = null;
    this.undoStack = []; this.redoStack = []; this._bytes = 0;
    this._act = null;                  // 正在记的这一步撤销
  }
  const D = Doc.prototype;

  D.layer = function (id) { return this.layers.find(l => l.id === id) || null; };
  D.maxLayers = function () {
    // 图层是整张画布的像素：画布越大能开的越少（预算 320 MB，最少 2 层，最多 12 层）
    return clamp(Math.floor(320 * 1024 * 1024 / (this.w * this.h * 4)), 2, 12);
  };
  function newLayer(doc, id, name) {
    return { id, name: name || id, visible: true, opacity: 1, blend: "normal", locked: false,
             px: new Uint8ClampedArray(doc.w * doc.h * 4) };
  }
  const full = (doc) => ({ x: 0, y: 0, w: doc.w, h: doc.h });

  // ---- 撤销：一步 = 一个 op。像素改动按小块存「改之前」，撤销时和现状对调，所以它自己就是重做。 ----
  D._begin = function (opId, kind) { this._act = { op: opId, kind, tiles: new Map(), struct: null, rect: null }; };
  D._touch = function (layer, x0, y0, x1, y1) {
    const a = this._act; if (!a || this.noHistory) return;
    const tw = Math.ceil(this.w / TILE);
    for (let ty = (y0 / TILE) | 0; ty <= ((y1 / TILE) | 0); ty++) for (let tx = (x0 / TILE) | 0; tx <= ((x1 / TILE) | 0); tx++) {
      const key = layer.id + ":" + (ty * tw + tx);
      if (a.tiles.has(key)) continue;
      a.tiles.set(key, { layer: layer.id, tx, ty, px: copyTile(this, layer, tx, ty) });
    }
  };
  function copyTile(doc, layer, tx, ty) {
    const x0 = tx * TILE, y0 = ty * TILE, w = Math.min(TILE, doc.w - x0), h = Math.min(TILE, doc.h - y0);
    const out = new Uint8ClampedArray(w * h * 4);
    for (let y = 0; y < h; y++) {
      const s = ((y0 + y) * doc.w + x0) * 4;
      out.set(layer.px.subarray(s, s + w * 4), y * w * 4);
    }
    return out;
  }
  function swapTile(doc, t) {
    const layer = doc.layer(t.layer); if (!layer) return;
    const x0 = t.tx * TILE, y0 = t.ty * TILE, w = Math.min(TILE, doc.w - x0), h = Math.min(TILE, doc.h - y0);
    const now = copyTile(doc, layer, t.tx, t.ty);
    for (let y = 0; y < h; y++) layer.px.set(t.px.subarray(y * w * 4, (y + 1) * w * 4), ((y0 + y) * doc.w + x0) * 4);
    t.px = now;
  }
  D._commit = function (rect) {
    const a = this._act; this._act = null; if (!a) return null;
    a.rect = rect || full(this);
    // 重放不需要撤销：不存「改之前」的像素，内存只剩图层本身（不影响画出来的像素）
    if (this.noHistory) return a;
    a.bytes = 0; a.tiles.forEach(t => { a.bytes += t.px.length; });
    if (a.struct && a.struct.px) a.bytes += a.struct.px.length;
    this.undoStack.push(a); this._bytes += a.bytes;
    this.redoStack.length = 0;
    while (this.undoStack.length > HISTORY_STEPS || (this._bytes > HISTORY_BYTES && this.undoStack.length > 1))
      this._bytes -= this.undoStack.shift().bytes;
    return a;
  };
  function flip(doc, a, undo) {
    a.tiles.forEach(t => swapTile(doc, t));
    const s = a.struct;
    if (s) {
      if (s.type === "add") {
        if (undo) { const i = doc.layers.findIndex(l => l.id === s.layer.id); doc.layers.splice(i, 1); }
        else doc.layers.splice(s.index, 0, s.layer);
      } else if (s.type === "remove") {
        if (undo) doc.layers.splice(s.index, 0, s.layer);
        else doc.layers.splice(doc.layers.findIndex(l => l.id === s.layer.id), 1);
      } else if (s.type === "move") {
        const l = doc.layers.splice(undo ? s.to : s.from, 1)[0]; doc.layers.splice(undo ? s.from : s.to, 0, l);
      } else if (s.type === "props") {
        const l = doc.layer(s.id); Object.assign(l, undo ? s.before : s.after);
      }
    }
    return a.rect;
  }
  /** → { op, rect } 或 null。op 是被撤掉的那一步的 id，日志靠它重放。 */
  D.undo = function () {
    const a = this.undoStack.pop(); if (!a) return null;
    this._bytes -= a.bytes; const rect = flip(this, a, true); this.redoStack.push(a);
    return { op: a.op, kind: a.kind, rect };
  };
  D.redo = function () {
    const a = this.redoStack.pop(); if (!a) return null;
    const rect = flip(this, a, false); this.undoStack.push(a); this._bytes += a.bytes;
    return { op: a.op, kind: a.kind, rect };
  };

  // ---- 图层操作：每个都是一步 op，可撤销，可重放 ----
  D.addLayer = function (opId, id, index, name) {
    const l = newLayer(this, id, name);
    index = index == null ? this.layers.length : clamp(index, 0, this.layers.length);
    this._begin(opId, "layer_add"); this._act.struct = { type: "add", layer: l, index };
    this.layers.splice(index, 0, l); this._commit(); return l;
  };
  D.removeLayer = function (opId, id) {
    const index = this.layers.findIndex(l => l.id === id); if (index < 0 || this.layers.length < 2) return false;
    this._begin(opId, "layer_remove"); this._act.struct = { type: "remove", layer: this.layers[index], index, px: this.layers[index].px };
    this.layers.splice(index, 1); this._commit(); return true;
  };
  D.moveLayer = function (opId, id, to) {
    const from = this.layers.findIndex(l => l.id === id); to = clamp(to, 0, this.layers.length - 1);
    if (from < 0 || from === to) return false;
    this._begin(opId, "layer_move"); this._act.struct = { type: "move", from, to };
    const l = this.layers.splice(from, 1)[0]; this.layers.splice(to, 0, l); this._commit(); return true;
  };
  D.setLayer = function (opId, id, props) {
    const l = this.layer(id); if (!l) return false;
    const before = {}, after = {};
    ["name", "visible", "opacity", "blend", "locked"].forEach(k => { if (k in props && props[k] !== l[k]) { before[k] = l[k]; after[k] = props[k]; } });
    if (!Object.keys(after).length) return false;
    this._begin(opId, "layer_props"); this._act.struct = { type: "props", id, before, after };
    Object.assign(l, after); this._commit(); return true;
  };
  D.clearLayer = function (opId, id) {
    const l = this.layer(id); if (!l) return false;
    this._begin(opId, "layer_clear"); this._touch(l, 0, 0, this.w - 1, this.h - 1); l.px.fill(0); this._commit(); return true;
  };
  /** 把这一层压到下面那层上，然后自己消失。 */
  D.mergeDown = function (opId, id) {
    const i = this.layers.findIndex(l => l.id === id); if (i < 1) return false;
    const top = this.layers[i], below = this.layers[i - 1];
    this._begin(opId, "layer_merge"); this._touch(below, 0, 0, this.w - 1, this.h - 1);
    const n = this.w * this.h, s = top.px, d = below.px, mul = top.blend === "multiply";
    if (top.visible) for (let p = 0; p < n; p++) over(d, p * 4, s[p * 4], s[p * 4 + 1], s[p * 4 + 2], s[p * 4 + 3] / 255 * top.opacity, mul);
    this._act.struct = { type: "remove", layer: top, index: i, px: top.px };
    this.layers.splice(i, 1); this._commit(); return true;
  };

  /** 把一个颜色盖到 d[o..o+3] 上（直通 alpha，不预乘）。a 是 0..1。 */
  function over(d, o, r, g, b, a, mul) {
    if (a <= 0) return;
    const da = d[o + 3] / 255;
    if (mul && da > 0) {   // 正片叠底：只和底下已有的颜色相乘，底下是空的就照常盖
      r = lerp(r, r * d[o] / 255, da); g = lerp(g, g * d[o + 1] / 255, da); b = lerp(b, b * d[o + 2] / 255, da);
    }
    const oa = a + da * (1 - a);
    d[o]     = Math.round((r * a + d[o] * da * (1 - a)) / oa);
    d[o + 1] = Math.round((g * a + d[o + 1] * da * (1 - a)) / oa);
    d[o + 2] = Math.round((b * a + d[o + 2] * da * (1 - a)) / oa);
    d[o + 3] = Math.round(oa * 255);
  }

  // =====================================================================
  //  一笔
  // =====================================================================
  /** opts: { op, brush, layer, color, size, opacity, seed } */
  D.beginStroke = function (o) {
    const b = BRUSHES[o.brush] || BRUSHES.pencil, layer = this.layer(o.layer) || this.layers[this.layers.length - 1];
    const r = rng(o.seed);
    const st = this.stroke = {
      op: o.op, b, layer, rgb: parseColor(o.color), size: +o.size || 8, opacity: clamp(+o.opacity || 1, 0, 1),
      seed: o.seed | 0, n: 0, dist: 0, carry: 0, sx: 0, sy: 0, lx: 0, ly: 0, lp: 0, lt: 0, ltilt: 0,
      dx: 1, dy: 0, speed: 0, simP: 0.5, bbox: null,
      g: b.grain ? grain(b.grain) : null,
      gox: (r() * GRAIN) | 0, goy: (r() * GRAIN) | 0,   // 每一笔从纸纹的不同位置起，不出现重复花纹
      bristles: null, bcol: null,
    };
    if (b.bristle) {
      const nb = st.nb = 48;
      st.bristles = new Float32Array(nb);
      for (let i = 0; i < nb; i++) st.bristles[i] = r();
      if (b.mode === "paint") {        // 每根笔毛带着自己的颜色，会被底下的颜料染
        st.bcol = new Float32Array(nb * 3);
        for (let i = 0; i < nb; i++) { st.bcol[i * 3] = st.rgb[0]; st.bcol[i * 3 + 1] = st.rgb[1]; st.bcol[i * 3 + 2] = st.rgb[2]; }
      }
    }
    this._begin(o.op, "stroke");
    return st;
  };

  /** 加一个采样点。pressure / tilt 可以是 null（鼠标、手指）。→ 这次动到的矩形 */
  D.strokeTo = function (x, y, pressure, tiltX, tiltY, tMs) {
    const st = this.stroke; if (!st) return null;
    const b = st.b; let dirty = null;
    const tilt = (tiltX == null) ? 0 : clamp(Math.sqrt(tiltX * tiltX + tiltY * tiltY) / 60, 0, 1);
    if (st.n === 0) {
      st.sx = st.lx = x; st.sy = st.ly = y; st.lt = tMs || 0; st.ltilt = tilt;
      st.simP = b.sim === "speed" ? 0.55 : (b.sim || 0.6);
      st.lp = pressure == null ? st.simP : pressure;
      st.n = 1;
      return this._stamp(st, x, y, st.lp, tilt);
    }
    // 轻微的防抖：手和鼠标的小抖动不该变成线上的毛刺
    const k = b.smooth || 1;
    const nx = st.sx + (x - st.sx) * k, ny = st.sy + (y - st.sy) * k;
    st.sx = nx; st.sy = ny;
    const ddx = nx - st.lx, ddy = ny - st.ly, len = Math.sqrt(ddx * ddx + ddy * ddy);
    if (len < 0.01) return null;
    const dt = Math.max(1, (tMs || 0) - st.lt);
    st.speed = lerp(st.speed, len / dt, 0.4);            // 像素/毫秒
    // 方向也平滑一下，笔毛的条纹才不会在拐弯处乱跳
    let ux = lerp(st.dx, ddx / len, 0.5), uy = lerp(st.dy, ddy / len, 0.5);
    const ul = Math.sqrt(ux * ux + uy * uy) || 1; st.dx = ux / ul; st.dy = uy / ul;
    let p;
    if (pressure == null) {
      // 没有压感的设备：毛笔按速度算（走得快就细），别的笔给一个固定力度
      const target = b.sim === "speed" ? clamp(1.05 - st.speed * 0.42, 0.18, 1) : (b.sim || 0.6);
      st.simP = lerp(st.simP, target, 0.25); p = st.simP;
    } else p = pressure;
    const p0 = st.lp, t0 = st.ltilt;
    let d = st.carry;
    for (;;) {
      const f0 = d / len, pp0 = lerp(p0, p, clamp(f0, 0, 1));
      const step = Math.max(0.6, this._radius(st, pp0, lerp(t0, tilt, clamp(f0, 0, 1))) * b.spacing);
      if (d > len) break;
      const f = d / len;
      const r = this._stamp(st, st.lx + ddx * f, st.ly + ddy * f, lerp(p0, p, f), lerp(t0, tilt, f));
      dirty = union(dirty, r);
      d += step;
    }
    st.carry = d - len; st.dist += len;
    st.lx = nx; st.ly = ny; st.lp = p; st.lt = tMs || 0; st.ltilt = tilt; st.n++;
    return dirty;
  };
  D._radius = function (st, p, tilt) {
    const b = st.b;
    let r = st.size * b.size * 0.5 * (1 - b.pSize + b.pSize * p * (b.pSize > 0.6 ? 1.25 : 2 * 0.75));
    if (b.tilt) r *= 1 + tilt * b.tilt;
    // 没压感时的起笔：从尖到圆，免得每一笔开头都是个圆头
    if (b.taper && st.dist < st.size * 2) r *= 0.35 + 0.65 * st.dist / (st.size * 2);
    return Math.max(0.5, r);
  };
  function union(a, r) {
    if (!r) return a; if (!a) return { x: r.x, y: r.y, w: r.w, h: r.h };
    const x0 = Math.min(a.x, r.x), y0 = Math.min(a.y, r.y);
    const x1 = Math.max(a.x + a.w, r.x + r.w), y1 = Math.max(a.y + a.h, r.y + r.h);
    a.x = x0; a.y = y0; a.w = x1 - x0; a.h = y1 - y0; return a;
  }

  D._stamp = function (st, cx, cy, p, tilt) {
    const b = st.b, W = this.w, H = this.h;
    const r = this._radius(st, p, tilt);
    const x0 = Math.max(0, Math.floor(cx - r)), y0 = Math.max(0, Math.floor(cy - r));
    const x1 = Math.min(W - 1, Math.ceil(cx + r)), y1 = Math.min(H - 1, Math.ceil(cy + r));
    if (x1 < x0 || y1 < y0) return null;
    // 浓淡：压力 × 笔放倒了变淡
    let flow = b.flow * (1 - b.pFlow + b.pFlow * p);
    if (b.tilt) flow *= 1 - tilt * 0.55;
    // 很细的笔（半径不到一个像素）按面积折算，不然细线会比粗线还黑
    const thin = r < 1 ? r : 1;
    const hard = b.hard, soft = 1 - hard, r2 = r * r;
    // 笔里的墨/颜料越画越少；走得快也带不下墨 → 飞白
    let dry = 0;
    if (b.bristle) dry = clamp((st.dist / (b.load * (0.4 + st.size / 24))) * 0.75 + (b.mode === "mask" ? st.speed * 0.16 : 0) - 0.12 + (1 - p) * 0.18, 0, 0.95) * b.bristle;
    const nb = st.nb, br = st.bristles, px = -st.dy, py = st.dx;   // 垂直于运笔方向
    const g = st.g, gAmt = b.grainAmt || 0, gK = b.grainK || 1;
    const pe = clamp(p * (1 - tilt * 0.35), 0, 1);
    const mask = this.mask;

    if (b.mode === "paint") {
      const L = st.layer.px, bc = st.bcol;
      this._touch(st.layer, x0, y0, x1, y1);
      // 先让每根笔毛沾一点它底下的颜色（这就是油画颜料在画布上互相带色）
      const reload = 0.018, pick = b.pickup;
      for (let i = 0; i < nb; i++) {
        const q = (i + 0.5) / nb * 2 - 1;
        // 在笔的**前缘**取色：笔心底下早就是自己刚涂的颜料了，取它等于什么都没带起来
        const lead = Math.sqrt(1 - q * q * 0.81) * r + 1.5;
        const sx = Math.round(cx + px * q * r * 0.9 + st.dx * lead), sy = Math.round(cy + py * q * r * 0.9 + st.dy * lead);
        if (sx < 0 || sy < 0 || sx >= W || sy >= H) continue;
        const o = (sy * W + sx) * 4, a = L[o + 3] / 255 * pick * 0.22;
        for (let c = 0; c < 3; c++) {
          let v = bc[i * 3 + c];
          v += (L[o + c] - v) * a;              // 沾上画布的
          v += (st.rgb[c] - v) * reload * (1 - dry);   // 笔里还有颜料就慢慢回到本色
          bc[i * 3 + c] = v;
        }
      }
      const relief = b.relief || 0, along = st.dist / Math.max(2, r * 1.5);
      for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) {
        const dx = x + 0.5 - cx, dy = y + 0.5 - cy, d2 = dx * dx + dy * dy;
        if (d2 >= r2) continue;
        const t = Math.sqrt(d2) / r;
        let s = t <= hard ? 1 : (1 - ((t - hard) / soft) * ((t - hard) / soft));
        const q = clamp((dx * px + dy * py) / r, -0.999, 0.999);
        const fi = (q * 0.5 + 0.5) * nb, i = fi | 0, i2 = Math.min(nb - 1, i + 1), ft = fi - i;
        const hgt = lerp(br[i], br[i2], ft);
        // 干笔：矮的笔毛先够不着画布；沿着笔的方向再断一断，才不像梳子
        let cov = 1;
        if (dry > 0) cov = clamp((hgt * 0.7 + 0.3 * vnoise(i * 0.9, along, 64, st.seed) - dry) * 6 + 0.5, 0, 1);
        const a = s * flow * cov * st.opacity;
        if (a <= 0.003) continue;
        // 笔毛之间的沟：一边亮一边暗，看起来颜料是有厚度的
        const shade = 1 + (br[i2] - br[i]) * relief * 2.2 + (hgt - 0.5) * relief * 0.5;
        over(L, (y * W + x) * 4,
          clamp(lerp(bc[i * 3], bc[i2 * 3], ft) * shade, 0, 255),
          clamp(lerp(bc[i * 3 + 1], bc[i2 * 3 + 1], ft) * shade, 0, 255),
          clamp(lerp(bc[i * 3 + 2], bc[i2 * 3 + 2], ft) * shade, 0, 255), clamp(a, 0, 1), false);
      }
    } else {
      const along = st.dist / Math.max(2, r * 2);
      for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) {
        const dx = x + 0.5 - cx, dy = y + 0.5 - cy, d2 = dx * dx + dy * dy;
        if (d2 >= r2) continue;
        const t = Math.sqrt(d2) / r;
        let a = (t <= hard ? 1 : (1 - ((t - hard) / soft) * ((t - hard) / soft))) * flow * thin;
        if (g && gAmt) {
          // 纸的凸起先沾上；用力了才压进凹处
          const gv = g[(((y + st.goy) & 255) << 8) | ((x + st.gox) & 255)];
          const v = clamp((pe * 1.15 + gv - 1) * gK + 0.5, 0, 1);
          a *= 1 - gAmt + gAmt * v;
        }
        if (dry > 0) {
          const q = clamp((dx * px + dy * py) / r, -0.999, 0.999);
          const fi = (q * 0.5 + 0.5) * nb, i = fi | 0, i2 = Math.min(nb - 1, i + 1);
          const hgt = lerp(br[i], br[i2], fi - i);
          a *= clamp((hgt * 0.65 + 0.35 * vnoise(i * 0.8, along, 64, st.seed) - dry) * 5 + 0.5, 0, 1);
        }
        if (a <= 0.002) continue;
        const o = y * W + x, m = mask[o];
        // 同一笔里重叠的印慢慢叠上去，到 maxA 封顶：来回涂不会无限变黑
        mask[o] = m + (b.maxA - m) * a * (b.flow >= 1 ? 1 : 0.5);
      }
    }
    const rect = { x: x0, y: y0, w: x1 - x0 + 1, h: y1 - y0 + 1 };
    st.bbox = union(st.bbox, rect);
    return rect;
  };

  /** 收笔：把这一笔落到图层上。→ { op, rect } */
  D.endStroke = function () {
    const st = this.stroke; if (!st) return null;
    this.stroke = null;
    let rect = st.bbox;
    if (!rect) { this._act = null; return null; }
    const b = st.b, W = this.w, H = this.h, mask = this.mask;
    if (b.mode === "mask") {
      if (b.wet) rect = this._soak(st, rect);
      const L = st.layer.px, x1 = rect.x + rect.w - 1, y1 = rect.y + rect.h - 1;
      this._touch(st.layer, rect.x, rect.y, x1, y1);
      for (let y = rect.y; y <= y1; y++) for (let x = rect.x; x <= x1; x++) {
        const o = y * W + x, m = mask[o]; if (m <= 0) continue;
        mask[o] = 0;
        if (b.erase) L[o * 4 + 3] = Math.round(L[o * 4 + 3] * (1 - m * st.opacity));
        else over(L, o * 4, st.rgb[0], st.rgb[1], st.rgb[2], m * st.opacity, false);
      }
    }
    const a = this._commit(rect);
    return { op: a.op, rect };
  };
  /** 放弃这一笔（两根手指落下来、手掌误触）。 */
  D.cancelStroke = function () {
    const st = this.stroke; if (!st) return null;
    this.stroke = null; const a = this._act; this._act = null;
    if (st.bbox) {
      const r = st.bbox;
      for (let y = r.y; y < r.y + r.h; y++) this.mask.fill(0, y * this.w + r.x, y * this.w + r.x + r.w);
    }
    if (a) a.tiles.forEach(t => swapTile(this, t));
    return st.bbox;
  };

  /** 墨往纸里洇：把这一笔的浓度图抹开一点，边缘按纸的纤维参差，再把边缘加深一圈（水走到边上停住，墨积在那儿）。 */
  D._soak = function (st, rect) {
    const b = st.b, W = this.w, H = this.h, mask = this.mask;
    const rad = Math.max(1, Math.round(st.size * b.size * 0.5 * b.wet));
    const x0 = Math.max(0, rect.x - rad * 2), y0 = Math.max(0, rect.y - rad * 2);
    const x1 = Math.min(W - 1, rect.x + rect.w - 1 + rad * 2), y1 = Math.min(H - 1, rect.y + rect.h - 1 + rad * 2);
    const w = x1 - x0 + 1, h = y1 - y0 + 1;
    let src = new Float32Array(w * h), tmp = new Float32Array(w * h);
    for (let y = 0; y < h; y++) src.set(mask.subarray((y0 + y) * W + x0, (y0 + y) * W + x0 + w), y * w);
    const orig = src.slice();
    const win = rad * 2 + 1;
    for (let pass = 0; pass < 2; pass++) {       // 两遍方框模糊 ≈ 一个柔和的晕
      for (let y = 0; y < h; y++) {
        let acc = 0;
        for (let x = -rad; x < w + rad; x++) {
          if (x + rad < w) acc += src[y * w + x + rad];
          if (x - rad - 1 >= 0) acc -= src[y * w + x - rad - 1];
          if (x >= 0 && x < w) tmp[y * w + x] = acc / win;
        }
      }
      for (let x = 0; x < w; x++) {
        let acc = 0;
        for (let y = -rad; y < h + rad; y++) {
          if (y + rad < h) acc += tmp[(y + rad) * w + x];
          if (y - rad - 1 >= 0) acc -= tmp[(y - rad - 1) * w + x];
          if (y >= 0 && y < h) src[y * w + x] = acc / win;
        }
      }
    }
    const g = st.g, edge = b.edge || 0, top = b.maxA;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const i = y * w + x, bl = src[i], o = orig[i];
      if (bl <= 0.004 && o <= 0) { mask[(y0 + y) * W + x0 + x] = 0; continue; }
      const gv = g ? g[(((y0 + y + st.goy) & 255) << 8) | ((x0 + x + st.gox) & 255)] : 0.5;
      // 纤维粗的地方吸得远：用纸纹去推晕开的边界
      let m = clamp((bl / top - 0.5 + (gv - 0.5) * 0.5) * (1.6 + 2.4 * (1 - b.wet * 3 > 0 ? 1 - b.wet * 3 : 0)) + 0.5, 0, 1) * top;
      m = Math.max(m, o * 0.85);                  // 笔真正走过的地方不会变淡，飞白也留着
      const rim = 4 * (bl / top) * (1 - bl / top);   // 在晕的半腰上最大 = 边缘
      m = clamp(m * (1 - edge * 0.35) + rim * edge * top * 0.6, 0, 1);
      mask[(y0 + y) * W + x0 + x] = m;
    }
    return { x: x0, y: y0, w, h };
  };

  // =====================================================================
  //  合成：把所有图层压成看得见的画面
  // =====================================================================
  /** 把 rect 这一块合成进 out（Uint8ClampedArray，rect.w × rect.h × 4，不透明）。 */
  D.composite = function (rect, out) {
    const W = this.w, st = this.stroke, mask = this.mask, bg = this.bg;
    const live = st && st.b.mode === "mask" ? st.layer : null;
    const px = [0, 0, 0, 0];
    let i = 0;
    for (let y = rect.y; y < rect.y + rect.h; y++) for (let x = rect.x; x < rect.x + rect.w; x++, i += 4) {
      const o = y * W + x;
      let r = bg[0], g = bg[1], b = bg[2];
      for (let k = 0; k < this.layers.length; k++) {
        const l = this.layers[k]; if (!l.visible) continue;
        let sr, sg, sb, sa;
        if (l === live && mask[o] > 0) {
          // 正在画的这一笔还没落到图层上：边合成边算，结果和收笔后一样
          px[0] = l.px[o * 4]; px[1] = l.px[o * 4 + 1]; px[2] = l.px[o * 4 + 2]; px[3] = l.px[o * 4 + 3];
          if (st.b.erase) px[3] = Math.round(px[3] * (1 - mask[o] * st.opacity));
          else over(px, 0, st.rgb[0], st.rgb[1], st.rgb[2], mask[o] * st.opacity, false);
          sr = px[0]; sg = px[1]; sb = px[2]; sa = px[3];
        } else { sa = l.px[o * 4 + 3]; if (!sa) continue; sr = l.px[o * 4]; sg = l.px[o * 4 + 1]; sb = l.px[o * 4 + 2]; }
        const a = sa / 255 * l.opacity; if (a <= 0) continue;
        if (l.blend === "multiply") { sr = sr * r / 255; sg = sg * g / 255; sb = sb * b / 255; }
        r += (sr - r) * a; g += (sg - g) * a; b += (sb - b) * a;
      }
      out[i] = Math.round(r); out[i + 1] = Math.round(g); out[i + 2] = Math.round(b); out[i + 3] = 255;
    }
    return out;
  };
  D.flatten = function () { return this.composite(full(this), new Uint8ClampedArray(this.w * this.h * 4)); };
  /** 某一层的缩略图（图层面板用）：最近邻，够看 */
  D.thumb = function (id, tw, th) {
    const l = this.layer(id), out = new Uint8ClampedArray(tw * th * 4); if (!l) return out;
    for (let y = 0; y < th; y++) for (let x = 0; x < tw; x++) {
      const o = (((y + 0.5) * this.h / th) | 0) * this.w + (((x + 0.5) * this.w / tw) | 0);
      const a = l.px[o * 4 + 3] / 255, i = (y * tw + x) * 4;
      out[i] = Math.round(lerp(255, l.px[o * 4], a)); out[i + 1] = Math.round(lerp(255, l.px[o * 4 + 1], a));
      out[i + 2] = Math.round(lerp(255, l.px[o * 4 + 2], a)); out[i + 3] = 255;
    }
    return out;
  };

  // =====================================================================
  //  重放：日志 → 画面。和当时画的走的是同一批函数。
  // =====================================================================
  /** 按一步 op 的记录再做一遍。op 是服务器从日志拼出来的（artquest/reconstruct.py 的 paint_ops）。 */
  D.apply = function (op) {
    switch (op.kind) {
      case "stroke": {
        this.beginStroke({ op: op.id, brush: op.brush, layer: op.layer, color: op.color, size: op.size, opacity: op.opacity, seed: op.seed });
        (op.points || []).forEach(p => this.strokeTo(p[0], p[1], p[3] == null ? null : p[3], p[4] == null ? null : p[4], p[5] == null ? null : p[5], p[2]));
        return this.endStroke();
      }
      case "layer_add": return this.addLayer(op.id, op.layer, op.index, op.name);
      case "layer_remove": return this.removeLayer(op.id, op.layer);
      case "layer_move": return this.moveLayer(op.id, op.layer, op.to);
      case "layer_props": return this.setLayer(op.id, op.layer, op.props || {});
      case "layer_clear": return this.clearLayer(op.id, op.layer);
      case "layer_merge": return this.mergeDown(op.id, op.layer);
    }
    return null;
  };
  /** spec: { width, height, background, layers:[{id,name}] }；ops 是最终还留在画面上的那些步，按顺序。 */
  function replay(spec, ops) {
    const doc = create(spec);
    (ops || []).forEach(op => doc.apply(op));
    return doc;
  }
  function create(spec) {
    const doc = new Doc(spec);
    (spec.layers && spec.layers.length ? spec.layers : [{ id: "L1", name: "图层 1" }])
      .forEach(l => doc.layers.push(newLayer(doc, l.id, l.name)));
    return doc;
  }
  /** 画面的指纹（FNV-1a）：浏览器和重放各算一次，对得上就说明日志能把画重建出来。 */
  function checksum(px) {
    let h = 0x811c9dc5;
    for (let i = 0; i < px.length; i++) { h ^= px[i]; h = Math.imul(h, 0x01000193); }
    return (h >>> 0).toString(16).padStart(8, "0");
  }

  return { ENGINE, BRUSHES, create, replay, checksum, grain, TILE };
});
