/* ArtQuest Stage 1 front-end: quest → intent → draw → feedback → revise → done. */
(() => {
  const $ = (s) => document.querySelector(s);
  const api = async (path, opts = {}) => {
    const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json();
  };

  const state = { cfg: null, quests: [], families: [], allSessions: [], rarity: null, quest: null, emotion: null, sessionId: null, phase: "before", feedback: null,
    startedAt: null, dirtySinceSnapshot: false, timers: [], before: null, color: "#e8632b", buddyTick: 0,
    anonId: "", condition: {}, study: null, seqIdx: 0, lastActivity: 0, idle: false, timeUp: false, pendingFinal: null };

  // ---------- research identity & environment ----------
  // Two anonymous ids: one the device keeps by itself (so free play still lines
  // up across tasks) and one a researcher hands out. Neither is a real name.
  const params = new URLSearchParams(location.search);
  function anonId() {
    let id = localStorage.getItem("artquest.anon_id");
    if (!id) {
      id = "anon-" + (crypto.randomUUID ? crypto.randomUUID().slice(0, 12) : Math.random().toString(16).slice(2, 14));
      localStorage.setItem("artquest.anon_id", id);
    }
    return id;
  }
  const savedPid = () => localStorage.getItem("artquest.participant_id") || "";
  const setPid = (pid) => pid ? localStorage.setItem("artquest.participant_id", pid) : localStorage.removeItem("artquest.participant_id");
  const deviceInfo = () => ({
    ua: navigator.userAgent, platform: navigator.platform || "",
    screen: [screen.width, screen.height], viewport: [innerWidth, innerHeight], dpr: devicePixelRatio || 1,
    pointer_types: [matchMedia("(pointer:fine)").matches ? "fine" : "", matchMedia("(any-pointer:coarse)").matches ? "coarse" : ""].filter(Boolean),
    timezone: (Intl.DateTimeFormat().resolvedOptions() || {}).timeZone || "", language: navigator.language || "",
  });
  const canvasGeom = () => { const r = canvas.getBoundingClientRect();
    return { width: canvas.width, height: canvas.height, css_width: Math.round(r.width), css_height: Math.round(r.height) }; };

  // 每个任务的图标 + 主题色（首页卡片用）
  const QUEST_STYLE = {
    emotion_alone:        { icon: "🌗", c: "#e8632b" },
    imagine_animal:       { icon: "🦄", c: "#7b4fd6" },
    transform_chair:      { icon: "🪑", c: "#2b7de8" },
    color_rain_city:      { icon: "🌧️", c: "#2e9e5b" },
    story_character_home: { icon: "🏠", c: "#d9455f" },
  };

  // ===== 创作伙伴「彩点」：一坨会变色的颜料精灵 =====
  function spriteInner(color, expr) {
    const dark = "#3a2f2a";
    const mouth = expr === "happy" ? `<path d="M84,120 Q100,138 116,120" fill="none" stroke="${dark}" stroke-width="4" stroke-linecap="round"/>`
      : expr === "wow" ? `<ellipse cx="100" cy="126" rx="8" ry="11" fill="${dark}"/>`
      : `<path d="M88,122 Q100,132 112,122" fill="none" stroke="${dark}" stroke-width="4" stroke-linecap="round"/>`;
    const p = expr === "wow" ? 6 : 7;
    const blob = "M100,26 C138,24 172,52 176,94 C179,128 160,150 150,166 C120,190 80,190 52,168 C40,150 21,128 24,94 C28,52 62,28 100,26 Z";
    return `<ellipse cx="100" cy="184" rx="44" ry="8" fill="rgba(0,0,0,.07)"/>`
      + `<path d="${blob}" fill="${color}" stroke="rgba(0,0,0,.12)" stroke-width="2"/>`
      + `<ellipse cx="84" cy="92" rx="15" ry="17" fill="#fff"/><ellipse cx="116" cy="92" rx="15" ry="17" fill="#fff"/>`
      + `<circle cx="86" cy="95" r="${p}" fill="${dark}"/><circle cx="114" cy="95" r="${p}" fill="${dark}"/>`
      + `<circle cx="84" cy="86" r="3" fill="#fff"/><circle cx="115" cy="86" r="3" fill="#fff"/>${mouth}`
      + `<path d="M150,150 q14,10 8,26 q-12,4 -14,-10" fill="${color}"/>`;
  }
  const buddyColor = () => state.color || "#e8632b";

  // ===== 顶部探险路线（藏宝图闯关） =====
  const ALL_STAGES = [
    { key: "quest",  name: "出发", icon: "🎒" },
    { key: "intent", name: "心愿", icon: "💭" },
    { key: "draw",   name: "创作", icon: "🎨" },
    { key: "result", name: "支招", icon: "💡" },
    { key: "evolve", name: "进化", icon: "✨" },
    { key: "final",  name: "宝藏", icon: "🏆" },
  ];
  function renderTrail(currentKey) {
    const el = document.getElementById("trail"); if (!el) return;
    // The map must not promise stations this condition never visits: with no
    // feedback there is no 支招 and no 进化, and a child staring at two locked
    // stops they can never reach is being told they failed at something.
    const quiet = state.condition && state.condition.feedback_source !== "ai";
    const STAGES = ALL_STAGES.filter(s => !(quiet && (s.key === "result" || s.key === "evolve")));
    const order = STAGES.map(s => s.key), idx = order.indexOf(currentKey);
    const span = STAGES.length > 1 ? 1040 / (STAGES.length - 1) : 0;
    const xs = STAGES.map((_, i) => 80 + i * span);
    const ys = STAGES.map((_, i) => (i % 2 === 0 ? 58 : 78)); // gentle zigzag
    const status = STAGES.map((s, i) => {
      if (currentKey === "final") {
        if (s.key === "evolve") return state.revised ? "done" : "skip";
        return i <= idx ? "done" : "locked";
      }
      return i < idx ? "done" : i === idx ? "current" : "locked";
    });
    let doneSeg = "", restSeg = "";
    for (let i = 0; i < STAGES.length - 1; i++) {
      const seg = `M${xs[i]},${ys[i]} L${xs[i + 1]},${ys[i + 1]}`;
      (i < idx ? (doneSeg += seg) : (restSeg += seg));
    }
    let nodes = "";
    STAGES.forEach((s, i) => {
      const st = status[i], x = xs[i], y = ys[i], cur = st === "current";
      const fill = st === "skip" ? "#f6f0f2" : (st === "done" || cur) ? "#fff" : "#f2efe9";
      const stroke = (st === "done" || cur) ? "#e8632b" : st === "skip" ? "#e6a6b2" : "#d8d0c4";
      const op = (st === "locked" || st === "skip") ? 0.5 : 1;
      const dash = (s.key === "evolve" && st !== "done") ? ' stroke-dasharray="4 3"' : "";
      nodes += `<circle cx="${x}" cy="${y}" r="24" fill="${fill}" stroke="${stroke}" stroke-width="${cur ? 4 : 3}"${dash}/>`;
      nodes += `<text x="${x}" y="${y + 8}" text-anchor="middle" font-size="23" opacity="${op}">${s.icon}</text>`;
      if (st === "done") nodes += `<circle cx="${x + 19}" cy="${y - 18}" r="10" fill="#e8632b"/><text x="${x + 19}" y="${y - 14}" text-anchor="middle" font-size="12">⭐</text>`;
      if (st === "skip") nodes += `<text x="${x + 17}" y="${y - 12}" text-anchor="middle" font-size="15" fill="#d9455f">↷</text>`;
      const lc = cur ? "#e8632b" : st === "done" ? "#7a766f" : "#b8b2a8";
      nodes += `<text x="${x}" y="${y + 40}" text-anchor="middle" font-size="14" font-weight="${cur ? 700 : 600}" fill="${lc}">${s.name}</text>`;
      if (cur) nodes += `<g transform="translate(${x - 19},${y - 50})"><svg width="38" height="38" viewBox="0 0 200 200">${spriteInner(buddyColor(), "normal")}</svg></g>`;
    });
    el.innerHTML =
      `<path d="${restSeg}" fill="none" stroke="#cfc8bc" stroke-width="4" stroke-linecap="round" stroke-dasharray="2 10"/>`
      + `<path d="${doneSeg}" fill="none" stroke="#e8632b" stroke-width="4" stroke-linecap="round" stroke-dasharray="2 10"/>`
      + nodes;
  }

  // ---------- views ----------
  const VIEWS = ["quest", "intent", "draw", "result", "survey", "final", "sessions"];
  function show(name) {
    VIEWS.forEach(v => $(`#view-${v}`).classList.toggle("hidden", v !== name));
    const trailbar = document.querySelector(".trailbar");
    if (trailbar) trailbar.classList.toggle("hidden", name === "sessions");
    if (name !== "sessions") {
      const stage = name === "draw" ? (state.phase === "after" ? "evolve" : "draw") : name === "survey" ? "final" : name;
      renderTrail(stage);
    }
    window.scrollTo(0, 0);
  }
  const overlay = (text) => { $("#overlay").classList.toggle("hidden", !text); if (text) $("#overlay-text").textContent = text; };

  // ---------- event vocabulary ----------
  // Mirrors artquest/events.py. One timeline, one clock: `t_ms` is milliseconds
  // since the session started drawing, and nothing here keeps its own time.
  const EV = {
    STROKE_START: "STROKE_START", STROKE_END: "STROKE_END", ERASE: "ERASE",
    UNDO: "UNDO", REDO: "REDO", CLEAR: "CLEAR",
    BRUSH_CHANGE: "BRUSH_CHANGE", COLOR_CHANGE: "COLOR_CHANGE", SIZE_CHANGE: "SIZE_CHANGE",
    ZOOM: "ZOOM", PAN: "PAN",
    REFERENCE_SHOW: "REFERENCE_SHOW", REFERENCE_OPEN: "REFERENCE_OPEN",
    REFERENCE_CLOSE: "REFERENCE_CLOSE", REFERENCE_ZOOM: "REFERENCE_ZOOM",
    REFERENCE_PAN: "REFERENCE_PAN", REFERENCE_FOCUS: "REFERENCE_FOCUS",
    CANVAS_FOCUS: "CANVAS_FOCUS",
    PAUSE_START: "PAUSE_START", PAUSE_END: "PAUSE_END",
    TIME_LIMIT_REACHED: "TIME_LIMIT_REACHED", CANVAS_GEOMETRY: "CANVAS_GEOMETRY",
    FEEDBACK_DISMISS: "FEEDBACK_DISMISS", REVISION_START: "REVISION_START",
    TASK_SUBMIT: "TASK_SUBMIT", DOWNLOAD: "DOWNLOAD",
  };

  // ---------- canvas ----------
  const canvas = $("#canvas"), ctx = canvas.getContext("2d", { willReadFrequently: true });
  const TOOLS = {
    pencil: { size: 1, alpha: 1, cap: "round", pressure: 0.4 },
    brush:  { size: 3, alpha: 0.9, cap: "round", pressure: 1 },
    marker: { size: 6, alpha: 0.35, cap: "square", pressure: 0 },
    eraser: { size: 6, alpha: 1, cap: "round", pressure: 0, color: "#ffffff" },
  };
  let tool = "pencil", color = "#222222", size = 4, drawing = false, last = null, strokeCount = 0, curStroke = null;
  const undoStack = [], redoStack = [], MAX_UNDO = 40;
  // The document behind the pixels: which strokes are currently on the canvas.
  // `undoDoc` / `redoDoc` stay index-aligned with the pixel stacks, so every
  // undo/redo/clear can say *which strokes* it took off and put back — without
  // that, a log with an undo in it cannot be replayed.
  let visible = [];
  const undoDoc = [], redoDoc = [];
  /** What changed between two document states, in painting order. */
  function docDiff(prev, next) {
    const before = new Set(prev), after = new Set(next);
    return { removed: prev.filter(id => !after.has(id)), restored: next.filter(id => !before.has(id)), visible_n: next.length };
  }

  function resetCanvas() { ctx.globalAlpha = 1; ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, canvas.width, canvas.height); undoStack.length = redoStack.length = 0; visible = []; undoDoc.length = redoDoc.length = 0; }
  /** The task's starting canvas. Mirrors artquest/reconstruct.draw_stimulus()
   *  exactly — replay is `initial canvas + strokes + events`, so if these two
   *  drew different fragments every such session would fail its QC replay check.
   *  Drawn before the undo stack exists, so it can never be undone away. */
  // The task's printed figures live here too, so the eraser can lift the
  // child's own marks off them without taking them away: in the paradigm M3
  // borrows, the fragments are printed on the sheet and cannot be rubbed out.
  // Erasing them would quietly void the manipulation for that session.
  let stimulusCanvas = null, eraserPattern = null;
  function buildStimulusLayer(stim) {
    stimulusCanvas = document.createElement("canvas");
    stimulusCanvas.width = canvas.width; stimulusCanvas.height = canvas.height;
    const sctx = stimulusCanvas.getContext("2d");
    sctx.fillStyle = "#fff"; sctx.fillRect(0, 0, canvas.width, canvas.height);
    if (stim && stim.kind === "fragments") paintFragments(sctx, stim);
    eraserPattern = ctx.createPattern(stimulusCanvas, "no-repeat");
  }
  function drawStimulus(stim) {
    buildStimulusLayer(stim);
    if (!stim || stim.kind !== "fragments") return;
    paintFragments(ctx, stim);
  }
  function paintFragments(ctx, stim) {
    ctx.save();
    ctx.globalAlpha = 1; ctx.strokeStyle = stim.stroke || "#3a3a3a";
    ctx.fillStyle = stim.stroke || "#3a3a3a"; ctx.lineWidth = stim.width || 3;
    ctx.lineCap = "round"; ctx.lineJoin = "round";
    const R = Math.PI / 180;
    (stim.items || []).forEach(it => {
      ctx.beginPath();
      if (it.type === "dot") { ctx.arc(it.x, it.y, it.r, 0, Math.PI * 2); ctx.fill(); return; }
      if (it.type === "line") { ctx.moveTo(it.x1, it.y1); ctx.lineTo(it.x2, it.y2); }
      else if (it.type === "arc") { ctx.arc(it.cx, it.cy, it.r, it.a0 * R, it.a1 * R); }
      else if (it.type === "corner") { ctx.moveTo(it.x, it.y); ctx.lineTo(it.x, it.y + it.h); ctx.lineTo(it.x + it.w, it.y + it.h); }
      else if (it.type === "curve") { ctx.moveTo(it.x1, it.y1); ctx.quadraticCurveTo(it.cx, it.cy, it.x2, it.y2); }
      else if (it.type === "rect_open") {
        const g = it.gap || "top", x = it.x, y = it.y, w = it.w, h = it.h;
        const side = { top: [x, y, x + w, y], right: [x + w, y, x + w, y + h],
                       bottom: [x, y + h, x + w, y + h], left: [x, y, x, y + h] };
        Object.keys(side).forEach(k => { if (k !== g) { const p = side[k]; ctx.moveTo(p[0], p[1]); ctx.lineTo(p[2], p[3]); } });
      }
      ctx.stroke();
    });
    ctx.restore();
  }
  function pos(e) {
    const r = canvas.getBoundingClientRect();
    return { x: (e.clientX - r.left) * canvas.width / r.width, y: (e.clientY - r.top) * canvas.height / r.height, p: e.pressure || 0.5 };
  }
  function pushUndo() {
    undoStack.push(ctx.getImageData(0, 0, canvas.width, canvas.height)); undoDoc.push(visible.slice());
    if (undoStack.length > MAX_UNDO) { undoStack.shift(); undoDoc.shift(); }
    redoStack.length = redoDoc.length = 0;
  }
  function strokeStyle(p) {
    const t = TOOLS[tool];
    const w = size * t.size * (t.pressure ? (1 - t.pressure + t.pressure * 2 * p) : 1);
    ctx.lineWidth = Math.max(0.5, w); ctx.lineCap = t.cap; ctx.lineJoin = "round";
    // the eraser paints back the starting canvas, so it removes the child's
    // marks and never the task's printed stimulus
    ctx.strokeStyle = (tool === "eraser" && eraserPattern) ? eraserPattern : (t.color || color);
    ctx.globalAlpha = t.alpha;
  }
  // -- stroke recording: the core process datum. Raw points only —
  //    speed / length / hesitation / rhythm are derived offline, never here.
  const R = (v, n) => { const f = Math.pow(10, n); return Number.isFinite(v) ? Math.round(v * f) / f : 0; };
  /** Does this pointer actually measure pressure and tilt?
   *  A mouse reports a constant pressure of 0.5 and no tilt. Logging that as a
   *  reading would put a fabricated number in every point of every mouse-drawn
   *  stroke, and offline analysis could not tell it from a real one — so an
   *  unsupported channel is recorded as null, never as a plausible value. */
  const hasPen = (e) => e.pointerType === "pen";
  function samplePoint(e, t0) {
    const q = pos(e), pen = hasPen(e);
    return [R(q.x, 1), R(q.y, 1), Math.round(elapsed() - t0),
            pen ? R(e.pressure, 3) : null,
            pen ? Math.round(e.tiltX || 0) : null,
            pen ? Math.round(e.tiltY || 0) : null];
  }
  function beginStroke(e) {
    const t0 = elapsed();
    const id = "s" + String(++strokeCount).padStart(5, "0");
    curStroke = { id, t0, tool, color: TOOLS[tool].color || color, size, opacity: TOOLS[tool].alpha,
      erase: tool === "eraser", pointer_type: e.pointerType || "",
      // the stroke says whether these channels were measured at all
      pressure_supported: hasPen(e), tilt_supported: hasPen(e),
      zoom: view.z, points: [samplePoint(e, t0)] };
    // logged at pen-down, not at pen-up: planning latency and first-stroke
    // region are about when the child *started*, not when they let go
    logEvent(EV.STROKE_START, { stroke_id: id, tool: curStroke.tool, color: curStroke.color,
      size, erase: curStroke.erase, pointer_type: curStroke.pointer_type, zoom: R(view.z, 3) });
  }
  function finishStroke() {
    if (!curStroke) return;
    const s = curStroke; curStroke = null;
    const id = s.id, last_pt = s.points[s.points.length - 1];
    ArtLog.stroke({ stroke_id: id, phase: state.phase, t_start_ms: Math.round(s.t0), t_end_ms: Math.round(s.t0 + last_pt[2]),
      tool: s.tool, color: s.color, size: s.size, opacity: s.opacity, erase: s.erase,
      pointer_type: s.pointer_type, pressure_supported: s.pressure_supported,
      tilt_supported: s.tilt_supported, zoom: R(s.zoom, 3), points: s.points });
    visible.push(id);
    // the same stroke also lands in the unified event timeline, cross-referenced by id
    logEvent(s.erase ? EV.ERASE : EV.STROKE_END, { stroke_id: id, tool: s.tool, color: s.color,
      size: s.size, n: s.points.length, dur_ms: last_pt[2] });
  }
  canvas.addEventListener("pointerdown", (e) => {
    if (wantsPan(e)) { e.preventDefault(); panStart(e); return; }
    if (e.button !== 0 && e.pointerType === "mouse") return;
    if (state.timeUp) return;
    flushZoom();   // a zoom gesture closes before the stroke it was made for
    canvas.setPointerCapture(e.pointerId); pushUndo(); drawing = true; last = pos(e); beginStroke(e);
    strokeStyle(last.p); ctx.beginPath(); ctx.moveTo(last.x, last.y); ctx.lineTo(last.x + 0.01, last.y); ctx.stroke();
    markActive();
  });
  canvas.addEventListener("pointermove", (e) => {
    if (panning) return panMove(e);
    if (!drawing) return;
    // coalesced events keep the full input rate of a pen (up to ~240 Hz)
    const evs = (e.getCoalescedEvents && e.getCoalescedEvents()) || [];
    (evs.length ? evs : [e]).forEach(ev => {
      const p = pos(ev); strokeStyle(p.p);
      ctx.beginPath(); ctx.moveTo(last.x, last.y); ctx.lineTo(p.x, p.y); ctx.stroke(); last = p;
      if (curStroke) curStroke.points.push(samplePoint(ev, curStroke.t0));
    });
    state.dirtySinceSnapshot = true; markActive();
  });
  const endStroke = () => { if (panning) return panEnd(); if (drawing) { drawing = false; ctx.globalAlpha = 1; finishStroke(); } };
  canvas.addEventListener("pointerup", endStroke); canvas.addEventListener("pointercancel", endStroke); canvas.addEventListener("pointerleave", endStroke);

  // ---------- view: zoom / pan ----------
  // A *view* transform, never a drawing transform. The canvas element is scaled
  // and translated with CSS; the drawing context never learns about it. Pointer
  // coordinates go through getBoundingClientRect(), which already reports the
  // transformed box, so `pos()` keeps returning canvas pixels at every zoom
  // level — stroke data, undo, snapshots and replay are all untouched by zoom.
  // What zoom *does* change is what the child could see, so each stroke records
  // the zoom it was drawn at and each gesture lands in the event log.
  const viewport = $("#viewport");
  const MIN_ZOOM = 1, MAX_ZOOM = 8, ZOOM_STEP = 1.25;
  const ZOOM_SETTLE_MS = 300;   // a burst of wheel ticks is one gesture
  const MAX_GESTURE_STEPS = 80;
  const view = { z: 1, tx: 0, ty: 0 };
  let handMode = false, spaceDown = false, panning = null, zoomGesture = null, zoomTimer = null;

  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const zoomAllowed = () => state.condition.zoom_allowed !== false;
  const drawViewOpen = () => !$("#view-draw").classList.contains("hidden");
  const wantsPan = (e) => zoomAllowed() && (handMode || spaceDown || e.button === 1);

  function applyView() {
    const w = viewport.clientWidth, h = viewport.clientHeight;
    // the artwork always covers the viewport — no drifting off into empty space
    view.tx = clamp(view.tx, w - w * view.z, 0);
    view.ty = clamp(view.ty, h - h * view.z, 0);
    canvas.style.transform = `translate(${view.tx}px, ${view.ty}px) scale(${view.z})`;
    $("#zoom-level").textContent = Math.round(view.z * 100) + "%";
    viewport.classList.toggle("grab", !panning && (handMode || spaceDown) && zoomAllowed());
  }

  /** Zoom about a point in viewport coordinates, keeping that point still. */
  function zoomAt(z, cx, cy, source) {
    const prev = view.z;
    z = clamp(z, MIN_ZOOM, MAX_ZOOM);
    if (Math.abs(z - prev) < 1e-4) return;
    const lx = (cx - view.tx) / prev, ly = (cy - view.ty) / prev;
    view.z = z; view.tx = cx - lx * z; view.ty = cy - ly * z;
    applyView(); noteZoom(prev, source);
  }

  function resetView(source) {
    const prev = view.z, moved = view.z !== 1 || view.tx || view.ty;
    view.z = 1; view.tx = view.ty = 0; applyView();
    if (moved && source) noteZoom(prev, source);
  }

  // A gesture is logged as one record with its raw steps inside — the same
  // shape as a stroke, so the log keeps the trace without a flood of rows.
  function noteZoom(from, source) {
    const t = elapsed();
    if (!zoomGesture) zoomGesture = { t0: t, from, source, steps: [] };
    if (zoomGesture.steps.length < MAX_GESTURE_STEPS)
      zoomGesture.steps.push([Math.round(t - zoomGesture.t0), R(view.z, 3)]);
    clearTimeout(zoomTimer); zoomTimer = setTimeout(flushZoom, ZOOM_SETTLE_MS);
    markActive();
  }
  function flushZoom() {
    clearTimeout(zoomTimer); zoomTimer = null;
    const g = zoomGesture; zoomGesture = null;
    if (!g) return;
    logEvent(EV.ZOOM, { from: R(g.from, 3), to: R(view.z, 3), source: g.source,
      at: [Math.round(view.tx), Math.round(view.ty)],
      dur_ms: Math.round(elapsed() - g.t0), steps: g.steps });
  }

  function panStart(e) {
    canvas.setPointerCapture(e.pointerId);
    panning = { id: e.pointerId, x: e.clientX, y: e.clientY, t0: elapsed(),
                from: [Math.round(view.tx), Math.round(view.ty)], points: [] };
    viewport.classList.add("panning"); viewport.classList.remove("grab");
  }
  function panMove(e) {
    if (e.pointerId !== panning.id) return;
    view.tx += e.clientX - panning.x; view.ty += e.clientY - panning.y;
    panning.x = e.clientX; panning.y = e.clientY;
    applyView();
    if (panning.points.length < MAX_GESTURE_STEPS)
      panning.points.push([Math.round(elapsed() - panning.t0), Math.round(view.tx), Math.round(view.ty)]);
    markActive();
  }
  function panEnd() {
    const g = panning; panning = null;
    viewport.classList.remove("panning"); applyView();
    if (!g || !g.points.length) return;     // a click that never moved is not a pan
    logEvent(EV.PAN, { from: g.from, to: [Math.round(view.tx), Math.round(view.ty)],
      zoom: R(view.z, 3), dur_ms: Math.round(elapsed() - g.t0), points: g.points });
  }

  viewport.addEventListener("wheel", (e) => {
    if (!zoomAllowed()) return;
    e.preventDefault();
    const r = viewport.getBoundingClientRect();
    zoomAt(view.z * Math.pow(1.0015, -e.deltaY), e.clientX - r.left, e.clientY - r.top, "wheel");
  }, { passive: false });

  const stepZoom = (f, source) => {
    const r = viewport.getBoundingClientRect();
    zoomAt(view.z * f, r.width / 2, r.height / 2, source);
  };
  $("#btn-zoom-in").onclick = () => stepZoom(ZOOM_STEP, "button");
  $("#btn-zoom-out").onclick = () => stepZoom(1 / ZOOM_STEP, "button");
  $("#btn-zoom-reset").onclick = () => resetView("button");
  $("#btn-hand").onclick = () => {
    handMode = !handMode;
    $("#btn-hand").classList.toggle("active", handMode); applyView();
  };

  function undo() {
    if (!undoStack.length) return;
    redoStack.push(ctx.getImageData(0, 0, canvas.width, canvas.height)); redoDoc.push(visible.slice());
    ctx.putImageData(undoStack.pop(), 0, 0);
    const prev = visible; visible = undoDoc.pop() || [];
    logEvent(EV.UNDO, docDiff(prev, visible)); state.dirtySinceSnapshot = true;
  }
  function redo() {
    if (!redoStack.length) return;
    undoStack.push(ctx.getImageData(0, 0, canvas.width, canvas.height)); undoDoc.push(visible.slice());
    ctx.putImageData(redoStack.pop(), 0, 0);
    const prev = visible; visible = redoDoc.pop() || [];
    logEvent(EV.REDO, docDiff(prev, visible)); state.dirtySinceSnapshot = true;
  }
  $("#btn-undo").onclick = undo; $("#btn-redo").onclick = redo;
  $("#btn-clear").onclick = () => {
    if (!confirm("确定清空整张画布？")) return;
    pushUndo(); ctx.globalAlpha = 1; ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, canvas.width, canvas.height);
    const prev = visible; visible = [];
    logEvent(EV.CLEAR, docDiff(prev, visible)); state.dirtySinceSnapshot = true;
  };
  document.addEventListener("keydown", (e) => {
    if (!drawViewOpen()) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? redo() : undo(); }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") { e.preventDefault(); redo(); }
    if (!zoomAllowed()) return;
    if (e.code === "Space" && !spaceDown) { spaceDown = true; e.preventDefault(); applyView(); }
    if (e.key === "+" || e.key === "=") { e.preventDefault(); stepZoom(ZOOM_STEP, "key"); }
    if (e.key === "-" || e.key === "_") { e.preventDefault(); stepZoom(1 / ZOOM_STEP, "key"); }
    if (e.key === "0") { e.preventDefault(); resetView("key"); }
  });
  document.addEventListener("keyup", (e) => {
    if (e.code === "Space" && spaceDown) { spaceDown = false; applyView(); }
  });
  window.addEventListener("blur", () => { spaceDown = false; applyView(); });
  document.querySelectorAll("#tools button").forEach(b => b.onclick = () => {
    if (b.disabled) return;
    tool = b.dataset.tool; document.querySelectorAll("#tools button").forEach(x => x.classList.toggle("active", x === b)); logEvent(EV.BRUSH_CHANGE, { tool });
  });
  $("#size").oninput = (e) => { size = +e.target.value; $("#size-val").textContent = size; logEvent(EV.SIZE_CHANGE, { size }); };
  const PALETTE = ["#222222", "#7a7a7a", "#ffffff", "#e63946", "#f4a261", "#ffd166", "#2a9d8f", "#4caf50", "#1d6fe0", "#7b4fd6", "#f28cb1", "#8d5524"];
  const pal = $("#palette");
  PALETTE.forEach(c => { const d = document.createElement("div"); d.style.background = c; d.title = c; d.onclick = () => setColor(c, d); pal.appendChild(d); });
  const BUDDY_LINES = ["选个颜色，我就变成它！", "这个颜色真好看～", "大胆画，画错也没关系！", "多试几种颜色，我陪你！", "你画什么，我就变什么～"];
  function updateBuddy() {
    state.color = color;
    const sp = $("#draw-sprite"); if (sp) sp.innerHTML = spriteInner(color, "normal");
    const say = $("#draw-buddy-say"); if (say) say.textContent = BUDDY_LINES[state.buddyTick % BUDDY_LINES.length];
    if (!$("#view-draw").classList.contains("hidden")) renderTrail(state.phase === "after" ? "evolve" : "draw");
  }
  function setColor(c, el) { color = c; $("#color-custom").value = c; pal.querySelectorAll("div").forEach(x => x.classList.toggle("active", x === el)); if (tool === "eraser") document.querySelector('[data-tool="pencil"]').click(); logEvent(EV.COLOR_CHANGE, { color: c }); state.buddyTick++; updateBuddy(); }
  pal.firstChild.classList.add("active");
  $("#color-custom").oninput = (e) => setColor(e.target.value, null);
  $("#btn-download").onclick = () => { const a = document.createElement("a"); a.download = `artquest-${state.sessionId || "draft"}.png`; a.href = canvas.toDataURL("image/png"); a.click(); logEvent(EV.DOWNLOAD); };

  // ---------- process recording ----------
  const elapsed = () => state.startedAt ? Date.now() - state.startedAt : 0;
  const IDLE_MS = 3000;   // no input for this long counts as a pause worth logging
  /** One line of the append-only operation log; buffered locally, flushed in batches. */
  function logEvent(type, payload) { if (state.sessionId) ArtLog.event(type, elapsed(), payload || null); markActive(); }
  function markActive() {
    const t = elapsed();
    if (state.idle) { ArtLog.event(EV.PAUSE_END, t, { duration_ms: Math.round(t - state.lastActivity), phase: state.phase }); state.idle = false; }
    state.lastActivity = t;
  }
  function checkIdle() {
    if (!state.sessionId || state.idle) return;
    const t = elapsed();
    if (t - state.lastActivity >= IDLE_MS) { state.idle = true; ArtLog.event(EV.PAUSE_START, t, { since_ms: Math.round(state.lastActivity), phase: state.phase }); }
  }
  /** Push everything queued locally, then report what is still unsent. */
  async function flushLog() {
    flushZoom();   // close any open gesture before anything leaves the client
    try { await ArtLog.flush(); } catch (e) { /* keep the queue */ }
    return await ArtLog.pending();
  }
  async function snapshot() {
    if (!state.sessionId || !state.dirtySinceSnapshot) return;
    state.dirtySinceSnapshot = false;
    try {
      await api(`/api/sessions/${state.sessionId}/snapshot`, { method: "POST", body: JSON.stringify({ image: canvas.toDataURL("image/png"), elapsed_ms: elapsed() }) });
      $("#snap-info").textContent = `已记录 ${new Date().toLocaleTimeString()}`;
    } catch (e) { console.warn("snapshot failed", e); }
  }
  function startTimers() {
    stopTimers();
    state.timers.push(setInterval(() => { const s = Math.floor(elapsed() / 1000); $("#timer").textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; }, 500));
    state.timers.push(setInterval(snapshot, state.cfg.snapshot_interval_sec * 1000));
    state.timers.push(setInterval(checkIdle, 1000));
    state.timers.push(setInterval(tickTimeLimit, 1000));
  }
  function tickTimeLimit() {
    const limit = state.condition.time_limit_sec;
    if (!limit || state.timeUp) return;
    const left = Math.max(0, limit - Math.floor(elapsed() / 1000));
    $("#limit-info").textContent = `· 剩 ${String(Math.floor(left / 60)).padStart(2, "0")}:${String(left % 60).padStart(2, "0")}`;
    $("#limit-info").classList.toggle("low", left <= 30);
    if (left === 0) {
      state.timeUp = true; logEvent("TIME_LIMIT_REACHED", { limit_sec: limit });
      const btn = state.phase === "after" ? $("#btn-submit-after") : $("#btn-submit");
      if (btn) btn.click();
    }
  }
  function stopTimers() { state.timers.forEach(clearInterval); state.timers = []; }

  // ===== 首页：创作图鉴（收藏 + 集齐进度）=====
  async function loadCollection() {
    let rows = []; try { rows = await api("/api/sessions"); } catch (e) { return; }
    state.allSessions = rows;          // cross-artwork badges and the growth view read this
    const done = rows.filter(r => r.status === "done");
    const wrap = $("#collection-wrap"), grid = $("#collection");
    if (!done.length) { wrap.classList.add("hidden"); return; }
    wrap.classList.remove("hidden");
    const titleOf = (qid) => (state.quests.find(q => q.id === qid) || {}).title || qid;
    const styleOf = (qid) => QUEST_STYLE[qid] || { icon: "🎨", c: "#e8632b" };
    grid.innerHTML = done.slice(0, 12).map(r => {
      const st = styleOf(r.quest_id);
      return `<a class="dex-card" href="/api/sessions/${r.id}" target="_blank" style="--qc:${st.c}">
        <div class="dex-thumb"><img src="/files/${r.id}/after.png" alt="" loading="lazy"></div>
        <div class="dex-cap"><b>${st.icon} ${titleOf(r.quest_id)}</b><span>${(r.created_at || "").slice(0, 10)}</span></div></a>`;
    }).join("");
    const types = new Set(done.map(r => r.quest_id)), total = state.quests.length;
    $("#dex-progress").innerHTML = `已解锁 ${types.size}/${total} 种任务`
      + (types.size >= total ? ' · <b style="color:#e8632b">🏅 创作者勋章达成！</b>' : "");
  }

  /** 彩点's nine attributes, grown from what the child actually practised.
   *
   *  Practice comes from the task library's rubric contract: doing a task built
   *  to exercise a dimension grows it. That is real today and needs no model,
   *  and it rewards breadth — the way to grow an attribute is to go and do the
   *  missions that train it.
   *
   *  The evaluation layer stays dark until a backend can genuinely judge that
   *  dimension. Four of the nine are placeholders offline; drawing a bar over
   *  those would be a progress meter over numbers nobody produced. */
  async function renderGrowth() {
    const wrap = $("#growth-wrap");
    if ((state.condition.growth_display || "full") === "none") { wrap.classList.add("hidden"); return; }
    let g;
    try { g = await api(`/api/participants/${encodeURIComponent(savedPid() || " ")}/growth`
      + `?anon_id=${encodeURIComponent(state.anonId)}`); } catch (e) { return; }
    if (!g || !g.n_tasks) { wrap.classList.add("hidden"); return; }
    wrap.classList.remove("hidden");

    const byKey = Object.fromEntries(state.cfg.dimensions.map(d => [d.key, d]));
    const best = Object.entries(g.dims).sort((a, b) => b[1].practice - a[1].practice)[0];
    const col = FAMILIES[DIM_FAMILY[best[0]]].color;
    $("#growth-sprite").innerHTML = spriteInner(col, g.total_level >= 9 ? "happy" : "normal");
    // one ring per three levels: a visible shape change, not a number
    const rings = Math.min(5, Math.floor(g.total_level / 3));
    $("#growth-rings").textContent = rings ? "✦".repeat(rings) : "·";
    $("#growth-total").textContent = `${g.n_tasks} 幅作品 · 总成长 ${g.total_level}/${g.max_total}`;
    $("#growth-say").textContent = best[1].practice
      ? `我在「${byKey[best[0]].zh}」上长得最快！`
      : "再画几幅，我就开始长啦～";

    $("#growth-dims").innerHTML = CHART_ORDER.map(key => {
      const d = byKey[key], v = g.dims[key];
      if (!d || !v) return "";
      const fam = FAMILIES[DIM_FAMILY[key]];
      const pips = Array.from({ length: v.max_level }, (_, i) =>
        `<i class="${i < v.level ? "on" : ""}"></i>`).join("");
      const next = v.next_at !== null
        ? `再练 ${Math.max(0, v.next_at - v.practice)} 次升级`
        : "已满级";
      const layer = v.awake
        ? `<div class="gawake">评价层已唤醒 · ${v.score_n} 次评分</div>`
        : `<div class="gsleep">评价层待唤醒（需要评分模型）</div>`;
      return `<div class="gdim" style="--gc:${fam.color}">
        <div class="gtop"><span class="gname">${d.zh}</span><span class="gnext">${next}</span></div>
        <div class="gpips">${pips}</div>${layer}</div>`;
    }).join("");
  }

  // ---------- Study Mode ----------
  // The game is never stripped away; Study Mode only *fixes and records* what
  // would otherwise vary silently — task order, UI condition, reference, undo,
  // time limit, self-report. The condition is frozen per session, never mid-way.
  async function setupStudy() {
    const urlPid = (params.get("pid") || "").trim();
    if (urlPid) setPid(urlPid);
    state.condition = { ...state.cfg.default_condition };
    if (!(params.get("study") === "1" || state.cfg.study.active)) return;
    try {
      state.study = await api("/api/study/assign", { method: "POST",
        body: JSON.stringify({ participant_id: savedPid(), anon_id: state.anonId, group: params.get("group") || "" }) });
      state.condition = { ...state.condition, ...state.study.condition };
      state.seqIdx = 0;
    } catch (e) { console.warn("study assign failed", e); }
    renderStudyBar();
  }
  function renderStudyBar() {
    if (!state.study) return;
    const bar = $("#studybar"); bar.classList.remove("hidden");
    const pid = savedPid() || "（未分配代号）";
    $("#study-info").textContent = `${state.study.study_id || "study"} · 被试 ${pid} · 条件 ${state.condition.ui}`;
    $("#study-seq").textContent = (state.study.sequence || [])
      .map((t, i) => `${i < state.seqIdx ? "✓" : i === state.seqIdx ? "▶" : "·"}${i + 1}`).join(" ");
  }
  $("#btn-study-exit").onclick = () => { setPid(""); location.href = location.pathname; };
  /** What the personalisation arm chose to tell this child about their own past.
   *  The control arm (history_mode "none") returns nothing and nothing renders,
   *  so the three arms differ in what the child actually sees — which is the
   *  point of comparing them. What was shown is frozen server-side in
   *  personalization.json, alongside the representation it was derived from. */
  function renderHistory(p) {
    const card = $("#history-card"), lines = (p && p.shown) || [];
    card.classList.toggle("hidden", !lines.length);
    if (!lines.length) return;
    card.innerHTML = "<h4>🧭 你的创作轨迹</h4>"
      + lines.map(l => `<p>${escapeHtml(l.text || "")}</p>`).join("");
  }
  const escapeHtml = (t) => String(t).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  /** Apply the frozen condition to the UI (gamification level, undo, reference). */
  function applyCondition() {
    const c = state.condition;
    document.body.classList.toggle("quiet", c.ui === "quiet");
    ["#btn-undo", "#btn-redo"].forEach(sel => { const b = $(sel); if (b) { b.disabled = !c.undo_allowed; b.classList.toggle("hidden", !c.undo_allowed); } });
    $("#zoombar").classList.toggle("hidden", !zoomAllowed());
    if (!zoomAllowed()) { handMode = false; $("#btn-hand").classList.remove("active"); resetView(null); }
  }
  /** Per-task condition: reference image, time limit, allowed tools. */
  function applyTask(q) {
    drawStimulus(q.stimulus);
    const ref = q.reference, allowRef = state.condition.reference_allowed && !!ref;
    $("#refpanel").classList.toggle("hidden", !allowRef);
    $("#ref-wrap").classList.add("hidden");
    refView.z = 1; refView.tx = refView.ty = 0; refViewedMs = 0; refOpenedAt = null; attention = "canvas";
    if (allowRef) {
      $("#ref-img").src = ref.file || `/static/refs/${ref.id}.png`;
      applyRefView();
      // presented by the task, as distinct from the child choosing to open it
      logEvent(EV.REFERENCE_SHOW, { reference_id: ref.id, mode: ref.mode,
        placeholder: !!(q.stimulus && q.stimulus.placeholder), task_id: q.id });
      if (ref.mode === "always") toggleRef(true);
    }
    state.timeUp = false; $("#limit-info").textContent = ""; $("#limit-info").classList.remove("low");
    const allowed = q.allowed_tools;
    document.querySelectorAll("#tools button").forEach(b => {
      const ok = !allowed || allowed.indexOf(b.dataset.tool) >= 0;
      b.disabled = !ok; b.classList.toggle("off", !ok);
      if (!ok && b.classList.contains("active")) document.querySelector('[data-tool="pencil"]').click();
    });
  }
  // ---------- reference interaction ----------
  // Look → draw → check → correct only becomes visible if the reference records
  // more than "it was open": how long, how far in, and when attention moved.
  const refView = { z: 1, tx: 0, ty: 0 };
  let refOpenedAt = null, refViewedMs = 0, refDrag = null, attention = "canvas";

  function applyRefView() {
    const vp = $("#ref-viewport"), img = $("#ref-img");
    if (!vp || !img) return;
    const w = vp.clientWidth, h = vp.clientHeight;
    refView.tx = clamp(refView.tx, w - w * refView.z, 0);
    refView.ty = clamp(refView.ty, h - h * refView.z, 0);
    img.style.transform = `translate(${refView.tx}px, ${refView.ty}px) scale(${refView.z})`;
    $("#ref-zoom").textContent = Math.round(refView.z * 100) + "%";
  }
  function refZoomAt(z, cx, cy, source) {
    const prev = refView.z;
    z = clamp(z, 1, 8);
    if (Math.abs(z - prev) < 1e-4) return;
    const lx = (cx - refView.tx) / prev, ly = (cy - refView.ty) / prev;
    refView.z = z; refView.tx = cx - lx * z; refView.ty = cy - ly * z;
    applyRefView();
    logEvent(EV.REFERENCE_ZOOM, { reference_id: refId(), from: R(prev, 3), to: R(refView.z, 3),
      source, at: [Math.round(refView.tx), Math.round(refView.ty)] });
  }
  const refId = () => ((state.quest && state.quest.reference) || {}).id || "";
  function noteAttention(where) {
    if (attention === where || !state.sessionId) return;
    attention = where;
    logEvent(where === "reference" ? EV.REFERENCE_FOCUS : EV.CANVAS_FOCUS,
      { reference_id: refId(), zoom: R(refView.z, 3) });
  }

  function toggleRef(open) {
    const wrap = $("#ref-wrap"), willOpen = open !== undefined ? open : wrap.classList.contains("hidden");
    wrap.classList.toggle("hidden", !willOpen);
    $("#btn-ref-toggle").textContent = willOpen ? "🖼 收起参考图" : "🖼 看看参考图";
    const now = elapsed();
    if (willOpen) {
      refOpenedAt = now;
      logEvent(EV.REFERENCE_OPEN, { reference_id: refId(), task_id: state.quest && state.quest.id });
      applyRefView();
    } else {
      const dur = refOpenedAt != null ? Math.round(now - refOpenedAt) : null;
      if (dur != null) refViewedMs += dur;
      refOpenedAt = null;
      noteAttention("canvas");
      logEvent(EV.REFERENCE_CLOSE, { reference_id: refId(), task_id: state.quest && state.quest.id,
        view_duration_ms: dur, viewed_total_ms: refViewedMs, zoom: R(refView.z, 3) });
    }
  }
  $("#btn-ref-toggle").onclick = () => toggleRef();

  (function wireReference() {
    const vp = $("#ref-viewport");
    if (!vp) return;
    vp.addEventListener("wheel", (e) => {
      e.preventDefault();
      const r = vp.getBoundingClientRect();
      refZoomAt(refView.z * Math.pow(1.0015, -e.deltaY), e.clientX - r.left, e.clientY - r.top, "wheel");
    }, { passive: false });
    vp.addEventListener("pointerdown", (e) => {
      vp.setPointerCapture(e.pointerId);
      refDrag = { id: e.pointerId, x: e.clientX, y: e.clientY, t0: elapsed(),
                  from: [Math.round(refView.tx), Math.round(refView.ty)], moved: false };
      vp.classList.add("dragging");
    });
    vp.addEventListener("pointermove", (e) => {
      if (!refDrag || e.pointerId !== refDrag.id) return;
      refView.tx += e.clientX - refDrag.x; refView.ty += e.clientY - refDrag.y;
      refDrag.x = e.clientX; refDrag.y = e.clientY; refDrag.moved = true;
      applyRefView();
    });
    const endRefDrag = () => {
      if (!refDrag) return;
      const g = refDrag; refDrag = null; vp.classList.remove("dragging");
      if (!g.moved) return;
      logEvent(EV.REFERENCE_PAN, { reference_id: refId(), from: g.from,
        to: [Math.round(refView.tx), Math.round(refView.ty)], zoom: R(refView.z, 3),
        dur_ms: Math.round(elapsed() - g.t0) });
    };
    vp.addEventListener("pointerup", endRefDrag);
    vp.addEventListener("pointercancel", endRefDrag);
    vp.addEventListener("pointerenter", () => noteAttention("reference"));
    canvas.addEventListener("pointerenter", () => noteAttention("canvas"));
    const stepRef = (f, src) => { const r = vp.getBoundingClientRect(); refZoomAt(refView.z * f, r.width / 2, r.height / 2, src); };
    $("#btn-ref-in").onclick = () => stepRef(1.25, "button");
    $("#btn-ref-out").onclick = () => stepRef(1 / 1.25, "button");
    $("#btn-ref-reset").onclick = () => {
      const prev = refView.z;
      refView.z = 1; refView.tx = refView.ty = 0; applyRefView();
      if (prev !== 1) logEvent(EV.REFERENCE_ZOOM, { reference_id: refId(), from: R(prev, 3), to: 1, source: "button", at: [0, 0] });
    };
  })();

  // ---------- flow ----------
  /** Pick which parallel form of a family this child gets in free play.
   *  In Study Mode the protocol has already chosen; here it is just variety. */
  function randomForm(familyId) {
    const forms = state.quests.filter(q => q.family === familyId);
    return forms.length ? forms[Math.floor(Math.random() * forms.length)] : null;
  }

  function renderQuests() {
    const grid = $("#quest-grid"); grid.innerHTML = "";
    const seq = state.study && state.study.sequence ? state.study.sequence : null;
    const byId = Object.fromEntries(state.quests.map(q => [q.id, q]));

    // Study Mode: the protocol names exact forms, in order. Free play: the child
    // picks a *mission family* — 75 forms is a task library, not a treasure map,
    // and which parallel form they get is not a choice the child should make.
    const cards = seq
      ? seq.map(id => byId[id]).filter(Boolean).map((q, i) => ({
          key: q.id, icon: q.icon, color: q.color, kind: q.type, title: q.title,
          body: q.prompt, locked: i !== state.seqIdx,
          go: i !== state.seqIdx ? "稍后解锁" : `第 ${i + 1} 关 · 开始 →`, task: q }))
      : (state.families || []).filter(f => f.n_forms).map(f => ({
          key: f.id, icon: f.icon, color: f.color, kind: f.name,
          title: f.name, body: familyBlurb(f), locked: false,
          go: "开始创作 →", family: f.id }));

    cards.forEach(c => {
      const el = document.createElement("div");
      el.className = "quest-card" + (c.locked ? " locked" : "");
      el.style.setProperty("--qc", c.color || "#e8632b");
      el.innerHTML = `<div class="qc-top"><span class="qc-icon">${c.icon || "🎨"}</span><span class="type">${c.kind}</span></div>`
        + `<h3>${c.title}</h3><p>${c.body}</p><span class="qc-go">${c.go}</span>`;
      if (!c.locked) el.onclick = () => {
        const q = c.task || randomForm(c.family);
        if (q) chooseQuest(q);
      };
      grid.appendChild(el);
    });
  }
  /** One child-facing line per family — never the research goal. */
  const FAMILY_BLURB = {
    M0: "自己决定画什么，没有标准答案。",
    M1: "一幅画损坏了，把重要的东西重新画回来。",
    M2: "把看到的场景准确记录下来，让别人也能看懂。",
    M3: "画布上只剩几个碎片，把它们变成一整幅画。",
    M4: "把一个普通的东西改造成完全不同的用途。",
    M5: "把两个毫不相干的东西融合成一个新东西。",
    M6: "用颜色让整个地方换一种感觉。",
    M7: "先只用线条，再让线条长成一幅作品。",
    M8: "这个世界的规则和我们不一样，画出这里的生活。",
    M9: "一个故事的开头，接下来由你来画。",
  };
  const familyBlurb = (f) => FAMILY_BLURB[f.id] || "";
  async function init() {
    state.cfg = await api("/api/config"); state.quests = await api("/api/quests");
    state.families = await api("/api/families");
    state.anonId = anonId();
    $("#backend-badge").textContent = `评分: ${state.cfg.scorer} · 反馈: ${state.cfg.feedback}` + (state.cfg.claude_available ? "" : " (离线模式)");
    await setupStudy();
    applyCondition();
    $("#participant").value = savedPid();
    renderQuests();
    const chips = $("#emotion-chips"); chips.innerHTML = "";
    state.cfg.emotions.forEach(em => { const b = document.createElement("button"); b.textContent = em; b.onclick = () => { state.emotion = em; chips.querySelectorAll("button").forEach(x => x.classList.toggle("active", x === b)); }; chips.appendChild(b); });
    await loadCollection();
    await renderGrowth();
    await renderWall();
    show("quest");
  }
  function chooseQuest(q) {
    state.quest = q; $("#intent-quest-title").textContent = q.title; $("#intent-quest-prompt").textContent = q.prompt; $("#intent-quest-hint").textContent = "提示：" + q.hint; show("intent");
  }
  $("#btn-back-quest").onclick = () => show("quest");

  // ---------- leaving a task partway ----------
  // Picking the wrong mission used to be a trap: no way back, and the session
  // stayed open on the server for ever as a zombie "drawing" row.
  const leaveModal = $("#leave-modal");
  function askToLeave() {
    if (state.phase === "after") return;            // mid-revision: finish it
    const n = visible.length;
    $("#leave-body").textContent = n
      ? `这张画上已经有 ${n} 笔了。要先把它保存下来吗？`
      : "画布还是空的，可以直接换一个任务。";
    $("#btn-leave-save").classList.toggle("hidden", !n);
    leaveModal.classList.remove("hidden");
  }
  async function leaveTask(save) {
    leaveModal.classList.add("hidden");
    overlay(save ? "正在保存……" : "正在收尾……");
    stopTimers();
    try {
      const pending = await flushLog();
      if (save) {
        // a real submission: it goes through the normal scoring + QC path
        logEvent(EV.TASK_SUBMIT, { phase: "before", strokes: visible.length, via: "leave" });
        await api(`/api/sessions/${state.sessionId}/submit`, { method: "POST",
          body: JSON.stringify({ image: canvas.toDataURL("image/png"), elapsed_ms: elapsed(),
                                 phase: "before", pending }) });
        await api(`/api/sessions/${state.sessionId}/finalize`, { method: "POST",
          body: JSON.stringify({ elapsed_ms: elapsed(), pending }) });
      } else {
        // the strokes are kept, the session is marked — changing your mind is
        // process data, and a silently deleted session makes a task_id lie
        await api(`/api/sessions/${state.sessionId}/abandon`, { method: "POST",
          body: JSON.stringify({ elapsed_ms: elapsed(), reason: "wrong_task", pending }) });
      }
    } catch (e) { console.warn("leave failed", e); }
    state.sessionId = null; state.feedback = null; state.phase = "before";
    overlay(null);
    await loadCollection();
    await renderGrowth();
    await renderWall();
    show("quest");
  }
  $("#btn-back-draw").onclick = askToLeave;
  $("#btn-leave-keep").onclick = () => leaveModal.classList.add("hidden");
  $("#btn-leave-save").onclick = () => leaveTask(true);
  $("#btn-leave-drop").onclick = () => leaveTask(false);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !leaveModal.classList.contains("hidden")) leaveModal.classList.add("hidden");
  });
  $("#btn-start-draw").onclick = async () => {
    if (!state.emotion) { alert("先选一个现在的心情吧"); return; }
    const intent = { emotion: state.emotion, text: $("#intent-text").value.trim() };
    const pid = $("#participant").value.trim();
    if (pid && pid !== savedPid()) setPid(pid);
    const r = await api("/api/sessions", { method: "POST", body: JSON.stringify({
      quest_id: state.quest.id, intent,
      participant: { anon_id: state.anonId, participant_id: savedPid(), label: "" },
      condition: state.condition, device: deviceInfo(), canvas: canvasGeom(),
      study: state.study ? { active: !!state.study.active, study_id: state.study.study_id, group: state.study.group || "",
        order_index: state.seqIdx, sequence_id: (state.study.sequence || []).join(">") } : {},
    }) });
    state.sessionId = r.session_id; state.phase = "before"; state.before = null; state.revised = null;
    state.feedback = null;
    renderHistory(r.personalization);
    state.condition = { ...state.condition, ...(r.session.condition || {}) };  // the server froze it; mirror it back
    resetCanvas(); state.startedAt = Date.now(); state.dirtySinceSnapshot = false;
    strokeCount = 0; state.lastActivity = 0; state.idle = false;
    handMode = false; $("#btn-hand").classList.remove("active");
    resetView(null); applyCondition();   // a fresh canvas starts at 100 %, pen in hand
    await ArtLog.start(state.sessionId);
    applyTask(state.quest);
    $("#draw-quest-card").innerHTML = `<div class="type">${state.quest.type}</div><h3>${state.quest.title}</h3><p>${state.quest.prompt}</p>`;
    $("#draw-intent-card").innerHTML = `心情：<b>${intent.emotion}</b><br>我想表达：${intent.text || "（没写）"}`;
    $("#revision-banner").classList.add("hidden"); $("#btn-submit").classList.remove("hidden"); $("#snap-info").textContent = "";
    state.buddyTick = 0; updateBuddy();
    startTimers(); show("draw");
    // the canvas has a real size only once the view is visible
    logEvent(EV.CANVAS_GEOMETRY, canvasGeom());
  };

  $("#btn-submit").onclick = async () => {
    if (!undoStack.length && !state.dirtySinceSnapshot) { if (!confirm("画布好像还是空的，确定提交吗？")) return; }
    overlay("正在观察你的画……"); stopTimers();
    logEvent(EV.TASK_SUBMIT, { phase: state.phase, strokes: visible.length });
    const image = canvas.toDataURL("image/png");
    try {
      const pending = await flushLog();
      const r = await api(`/api/sessions/${state.sessionId}/submit`, { method: "POST", body: JSON.stringify({ image, elapsed_ms: elapsed(), phase: "before", pending }) });
      state.before = { image, scores: r.scores };
      if (!r.feedback) {
        // the frozen condition says this session carries no feedback, so there
        // is nothing to read and nothing to revise in response to
        const done = await api(`/api/sessions/${state.sessionId}/finalize`,
          { method: "POST", body: JSON.stringify({ elapsed_ms: elapsed(), pending }) });
        overlay(null);
        return endSession(done.session, image, image, null);
      }
      $("#result-img").src = image; renderScores($("#scores"), r.scores, null); $("#score-summary").textContent = r.scores.summary || "";
      const fbSp = $("#fb-sprite"); if (fbSp) fbSp.innerHTML = spriteInner(buddyColor(), "happy");
      // remember which feedback this is, so the revision can be attributed to it
      state.feedback = { id: r.feedback.feedback_id || "", shown_ms: elapsed() };
      $("#feedback-text").textContent = r.feedback.text; show("result");
    } catch (e) { alert("提交失败：" + e.message); startTimers(); }
    overlay(null);
  };
  /** Leaving the feedback screen — how long it was read is a process signal. */
  function dismissFeedback(action) {
    const fb = state.feedback || {};
    if (!fb.id) return;
    logEvent(EV.FEEDBACK_DISMISS, { feedback_id: fb.id, action,
      read_ms: fb.shown_ms != null ? Math.round(elapsed() - fb.shown_ms) : null });
  }
  $("#btn-revise").onclick = () => {
    const fb = state.feedback || {};
    dismissFeedback("revise");
    state.phase = "after";
    // the link the feedback experiments need: this revision answers *that*
    // feedback, and the child sat with it this long before acting
    logEvent("REVISION_START", { feedback_id: fb.id || null,
      latency_ms: fb.shown_ms != null ? Math.round(elapsed() - fb.shown_ms) : null });
    $("#btn-submit").classList.add("hidden"); $("#revision-banner").classList.remove("hidden"); startTimers(); show("draw");
  };
  $("#btn-skip-revise").onclick = async () => {
    dismissFeedback("skip");
    overlay("正在保存……");
    const pending = await flushLog();
    const r = await api(`/api/sessions/${state.sessionId}/finalize`, { method: "POST", body: JSON.stringify({ elapsed_ms: elapsed(), pending }) });
    endSession(r.session, state.before.image, state.before.image, null); overlay(null);
  };
  $("#btn-submit-after").onclick = async () => {
    overlay("正在比较修改前后……"); stopTimers();
    const image = canvas.toDataURL("image/png");
    try {
      const pending = await flushLog();
      const r = await api(`/api/sessions/${state.sessionId}/submit`, { method: "POST", body: JSON.stringify({ image, elapsed_ms: elapsed(), phase: "after", pending }) });
      endSession(r.session, state.before.image, image, r.comparison);
    } catch (e) { alert("提交失败：" + e.message); startTimers(); }
    overlay(null);
  };
  // ---------- self-report ----------
  const SURVEY = [
    { key: "difficulty", q: "这次画起来难不难？", lo: "很简单", hi: "很难" },
    { key: "confidence", q: "你觉得自己画得怎么样？", lo: "还差点", hi: "挺满意" },
    { key: "enjoyment", q: "画的过程开心吗？", lo: "一般", hi: "很开心" },
  ];
  const answers = {};
  function renderSurvey() {
    SURVEY.forEach(i => delete answers[i.key]);
    $("#survey-hardest").value = "";
    // a closed set makes the answer comparable across tasks and children; the
    // text box stays beside it, because a list that fits nobody is worse
    state.hardestChoice = null;
    const chips = $("#survey-hardest-choices"); chips.innerHTML = "";
    (state.cfg.hardest_parts || []).forEach(opt => {
      const b = document.createElement("button");
      b.textContent = opt.label;
      b.onclick = () => {
        state.hardestChoice = state.hardestChoice === opt.key ? null : opt.key;
        chips.querySelectorAll("button").forEach(x => x.classList.toggle("active", x === b && state.hardestChoice));
      };
      chips.appendChild(b);
    });
    $("#survey").innerHTML = SURVEY.map(item => `<div class="sq" data-key="${item.key}">
      <div class="sq-q">${item.q}</div>
      <div class="sq-scale"><span class="muted small">${item.lo}</span>
        ${[1, 2, 3, 4, 5].map(v => `<button data-v="${v}">${v}</button>`).join("")}
        <span class="muted small">${item.hi}</span></div></div>`).join("");
    $("#survey").querySelectorAll(".sq").forEach(row => row.querySelectorAll("button").forEach(b => b.onclick = () => {
      answers[row.dataset.key] = +b.dataset.v;
      row.querySelectorAll("button").forEach(x => x.classList.toggle("active", x === b));
    }));
  }
  async function sendSurvey(skip) {
    const body = skip ? { t_ms: elapsed() } : { ...answers,
      hardest_part_choice: state.hardestChoice || null,
      hardest_part: $("#survey-hardest").value.trim(), t_ms: elapsed() };
    try { await api(`/api/sessions/${state.sessionId}/questionnaire`, { method: "POST", body: JSON.stringify(body) }); }
    catch (e) { console.warn("questionnaire failed", e); }
    const f = state.pendingFinal; if (f) showFinal(f.session, f.beforeImg, f.afterImg, f.comparison);
  }
  $("#btn-survey-submit").onclick = () => sendSurvey(false);
  $("#btn-survey-skip").onclick = () => sendSurvey(true);

  /** Close out a session: push the local queue, then self-report (if the
   *  condition asks for it) before the final screen. */
  async function endSession(session, beforeImg, afterImg, comparison) {
    stopTimers();
    const pending = await flushLog();
    if (pending) console.warn(`${pending} 条记录尚未上传，已保留在本地队列`);
    state.pendingFinal = { session, beforeImg, afterImg, comparison };
    state.revised = session.revised;   // the trail must show ✨进化关 correctly on the survey too
    if (state.condition.questionnaire) { renderSurvey(); show("survey"); return; }
    showFinal(session, beforeImg, afterImg, comparison);
  }

  function showFinal(session, beforeImg, afterImg, comparison) {
    state.revised = session.revised;
    $("#final-before").src = beforeImg; $("#final-after").src = afterImg;
    // no revision happened, so "before / after" would be the same image twice
    const noRevision = state.condition && state.condition.feedback_source !== "ai";
    $("#final-before").closest("figure").classList.toggle("hidden", noRevision);
    document.querySelector("#view-final .compare")?.classList.toggle("single", noRevision);
    const cap = $("#final-after").nextElementSibling;
    if (cap) cap.textContent = noRevision ? "你的作品" : "修改后";
    const cmpSp = $("#cmp-sprite"); if (cmpSp) cmpSp.innerHTML = spriteInner(buddyColor(), session.revised ? "happy" : "normal");
    // In a no-feedback condition the child is shown their work and their
    // badges, but no evaluation: assessment keeps running server-side, it just
    // stops being an intervention this session.
    const quiet = state.condition.feedback_source !== "ai";
    $("#comparison-text").textContent = quiet
      ? "画完啦！你的创作已经保存下来了。"
      : (comparison ? comparison.text : "这次没有走进化关～下次试试根据我的话改一小处，就能解锁 🔁 进化大师徽章！");
    renderTrained(session);
    renderBadges(session);
    reportBadges(session).then(() => renderBadges(session));   // rarity needs this session counted
    renderPeers(session);
    // What the child is shown of their own growth is its own condition, separate
    // from whether this artwork got feedback: a no-intervention arm can still
    // let a child see their cumulative practice without being told about *this*
    // drawing.
    const showScores = (state.condition.growth_display || "full") === "full";
    const scores = $("#final-scores");
    scores.classList.toggle("hidden", !showScores);
    if (showScores) renderScores(scores, session.after.scores, session.before.scores);
    $("#final-meta").textContent = `Session ${session.id} · 过程截图 ${session.snapshots.length} 张 · 事件 ${session.events.length} 条 · 数据在 data/sessions/${session.id}/`;
    show("final");
  }

  // ===== 过程徽章（只奖励过程，不奖励分数）=====
  const dimScore = (s, k) => ((s.after || s.before || {}).scores?.dims?.[k]?.score) ?? 0;
  const drawMs = (s) => (s.after?.elapsed_ms || s.before?.elapsed_ms || 0);
  // Mirrors artquest/events.canonical(): a session recorded under the old
  // vocabulary must still light the same badges.
  const EV_ALIAS = { STROKE: "STROKE_END", IDLE_START: "PAUSE_START",
                     IDLE_END: "PAUSE_END", FEEDBACK_SHOWN: "FEEDBACK_SHOW" };
  const evType = (e) => EV_ALIAS[e.type] || e.type;
  const distinctIn = (s, types, field) => new Set((s.events || [])
    .filter(e => types.indexOf(evType(e)) >= 0)
    .map(e => (e.payload || e.detail || {})[field]).filter(Boolean)).size;
  // Badges read the process log, never the artwork's quality. "You zoomed in to
  // work on a detail" is something the child did; "your drawing is good" is a
  // verdict, and this app does not hand children verdicts.
  const WARM = ["#e63946", "#f4a261", "#ffd166", "#f28cb1", "#8d5524"];
  const COOL = ["#2a9d8f", "#4caf50", "#1d6fe0", "#7b4fd6"];
  const evOf = (s, types) => (s.events || []).filter(e => types.indexOf(evType(e)) >= 0);
  const payloads = (s, types, field) => evOf(s, types)
    .map(e => (e.payload || e.detail || {})[field]).filter(v => v !== undefined && v !== null);
  const colorsUsed = (s) => new Set(payloads(s, ["COLOR_CHANGE", "STROKE_START", "STROKE_END"], "color"));
  const toolsUsed = (s) => new Set(payloads(s, ["BRUSH_CHANGE", "STROKE_START", "STROKE_END", "ERASE"], "tool"));
  const nStrokes = (s) => (s.counts || {}).strokes || 0;   // `strokeCount` is the live counter
  const pauses = (s) => payloads(s, ["PAUSE_END"], "duration_ms").map(Number);
  const longestPause = (s) => Math.max(0, ...pauses(s));
  const zoomMax = (s) => Math.max(1, ...payloads(s, ["ZOOM"], "to").map(Number));
  const refMs = (s) => payloads(s, ["REFERENCE_CLOSE"], "view_duration_ms")
    .map(Number).reduce((a, b) => a + b, 0);
  const hasWarmAndCool = (s) => {
    const c = colorsUsed(s);
    return WARM.some(x => c.has(x)) && COOL.some(x => c.has(x));
  };
  const doneRows = () => (state.allSessions || []).filter(r => r.status === "done");
  const familyOf = (taskId) => (state.quests.find(q => q.id === taskId) || {}).family || "";

  const ALL_BADGES = [
    // -- 颜色与工具 --
    { g: "色彩与工具", icon: "🎨", name: "缤纷调色", desc: "用了 5 种以上颜色",
      earned: s => colorsUsed(s).size >= 5 },
    { g: "色彩与工具", icon: "🌗", name: "冷暖并用", desc: "暖色和冷色都用上了",
      earned: s => hasWarmAndCool(s) },
    { g: "色彩与工具", icon: "🖌", name: "工具全能", desc: "用了 3 种以上工具",
      earned: s => toolsUsed(s).size >= 3 },
    { g: "色彩与工具", icon: "✏️", name: "一支到底", desc: "只用一种工具画完 30 笔以上",
      earned: s => toolsUsed(s).size === 1 && nStrokes(s) >= 30 },
    // -- 过程与节奏 --
    { g: "过程与节奏", icon: "⏱️", name: "专注之心", desc: "专注创作超过 5 分钟",
      earned: s => drawMs(s) >= 300000 },
    { g: "过程与节奏", icon: "💭", name: "深思熟虑", desc: "停下来想了 30 秒以上，然后继续",
      earned: s => longestPause(s) >= 30000 && nStrokes(s) >= 5 },
    { g: "过程与节奏", icon: "⚡", name: "一气呵成", desc: "20 笔以上，中间几乎没停",
      earned: s => nStrokes(s) >= 20 && longestPause(s) < 10000 },
    { g: "过程与节奏", icon: "🔁", name: "反复打磨", desc: "撤销 5 次以上，还在继续画",
      earned: s => evOf(s, ["UNDO"]).length >= 5 && nStrokes(s) >= 10 },
    { g: "过程与节奏", icon: "🧹", name: "推倒重来", desc: "清空过画布，然后重新画完",
      earned: s => evOf(s, ["CLEAR"]).length >= 1 && nStrokes(s) >= 10 },
    // -- 观察与细节 --
    { g: "观察与细节", icon: "🔍", name: "细节猎人", desc: "放大到 3 倍以上作画",
      earned: s => zoomMax(s) >= 3 },
    { g: "观察与细节", icon: "🗺", name: "大局观", desc: "在整体和局部之间来回看了 5 次以上",
      earned: s => evOf(s, ["ZOOM", "PAN"]).length >= 5 },
    { g: "观察与细节", icon: "👀", name: "对照高手", desc: "参考图看了 3 次以上",
      earned: s => evOf(s, ["REFERENCE_OPEN"]).length >= 3, needs: "reference" },
    { g: "观察与细节", icon: "⏳", name: "看得仔细", desc: "参考图累计看了 30 秒以上",
      earned: s => refMs(s) >= 30000, needs: "reference" },
    // -- 探索与坚持（跨作品）--
    { g: "探索与坚持", icon: "🧭", name: "探险家", desc: "玩过 3 个不同的任务家族",
      earned: () => new Set(doneRows().map(r => familyOf(r.task_id)).filter(Boolean)).size >= 3 },
    { g: "探索与坚持", icon: "📚", name: "小有收藏", desc: "完成 5 幅作品",
      earned: () => doneRows().length >= 5 },
    { g: "探索与坚持", icon: "🏅", name: "走遍全图", desc: "每个任务家族都完成过一次",
      earned: () => {
        const fams = new Set((state.families || []).map(f => f.id));
        const done = new Set(doneRows().map(r => familyOf(r.task_id)).filter(Boolean));
        return fams.size > 0 && [...fams].every(f => done.has(f));
      } },
    { g: "探索与坚持", icon: "✨", name: "进化大师", desc: "走完进化关，改了自己的作品",
      earned: s => s.revised === true, evo: true },
  ];
  const BADGE_RULES_VERSION = "badges/1";

  /** Tell the server what this session lit, so rarity can be counted.
   *  Stored with the rule-set version: tightening a rule later must not take a
   *  badge off a child who already had it. */
  async function reportBadges(session) {
    const pool = badgePool(session);
    const earned = pool.filter(b => { try { return !!b.earned(session); } catch (e) { return false; } });
    try {
      await api(`/api/sessions/${session.id}/badges`, { method: "POST", body: JSON.stringify({
        earned: earned.map(b => b.name), offered: pool.map(b => b.name),
        version: BADGE_RULES_VERSION }) });
      state.rarity = await api("/api/achievements");
    } catch (e) { /* a badge is not worth failing a session over */ }
  }

  /** The server-wide wall: work a teacher chose to show, across every task.
   *  Curation is the only form of "best" this app has, because it is a human
   *  decision with a name attached — a classroom wall, not a ranking function.
   *  Still consent-gated, and only on the home screen when the condition says
   *  `always`; under `after_submit` seeing other work before drawing would
   *  steer what the child draws and void the task condition. */
  async function renderWall() {
    const el = $("#wall-wrap");
    if ((state.condition.gallery_display || "none") !== "always") { el.classList.add("hidden"); return; }
    let data;
    try { data = await api("/api/gallery/featured?k=8"); } catch (e) { el.classList.add("hidden"); return; }
    const cards = (data && data.examples) || [];
    if (!cards.length) { el.classList.add("hidden"); return; }
    el.classList.remove("hidden");
    $("#wall-grid").innerHTML = cards.map(c => {
      const a = c.approach || {};
      const title = (state.quests.find(q => q.id === c.task_id) || {}).title || c.task_id;
      return `<div class="peer">
        <img src="${c.image}" alt="精选作品" loading="lazy">
        <div class="p-why">${escapeHtml(title)}</div>
        <div class="p-how">${a.strokes} 笔 · ${a.colors || 1} 种颜色 · ${a.minutes} 分钟</div>
        ${c.why ? `<div class="p-how">「${escapeHtml(c.why)}」</div>` : ""}
        <div class="p-pin">📌 老师选的</div></div>`;
    }).join("");
  }

  /** Other people's *approaches* to the same task — chosen for how much they
   *  differ from this child's, never for being better. Only after they have
   *  submitted their own, so it cannot steer what they drew, and only where
   *  the frozen condition allows it. */
  async function renderPeers(session) {
    const el = $("#peers");
    if ((state.condition.gallery_display || "none") !== "after_submit") { el.classList.add("hidden"); return; }
    let data;
    try {
      data = await api(`/api/gallery/task/${encodeURIComponent(session.quest_id)}?exclude=${session.id}&k=3`);
    } catch (e) { el.classList.add("hidden"); return; }
    let cards = (data && data.examples) || [];
    try {
      const pinned = await api(`/api/gallery/featured?task_id=${encodeURIComponent(session.quest_id)}&k=2`);
      // a pinned drawing may also be one of the diverse picks — show it once,
      // with the teacher's note rather than the process contrast
      const seen = new Set((pinned.examples || []).map(c => c.session_id));
      cards = (pinned.examples || []).concat(cards.filter(c => !seen.has(c.session_id))).slice(0, 4);
    } catch (e) { /* featured is optional */ }
    if (!cards.length) { el.classList.add("hidden"); return; }
    el.classList.remove("hidden");
    $("#peers-note").textContent = "看看就好，没有哪一张是标准答案";
    $("#peer-grid").innerHTML = cards.map(c => {
      const a = c.approach || {};
      const how = [`${a.strokes} 笔`, `${a.colors || 1} 种颜色`, `${a.minutes} 分钟`,
                   a.zoomed ? "放大过" : null].filter(Boolean).join(" · ");
      return `<div class="peer">
        <img src="${c.image}" alt="别人的作品" loading="lazy">
        <div class="p-why">${escapeHtml(c.why || "另一种做法")}</div>
        <div class="p-how">${how}</div>
        ${c.featured_by ? `<div class="p-pin">📌 老师选的</div>` : ""}</div>`;
    }).join("");
  }

  /** The mission's own rubric, said back as practice rather than as a verdict.
   *  "This one trained imagination, transformation and composition" is a fact
   *  about the task; "you scored 3 on imagination" is a judgement of the child,
   *  and the second one is what we are trying not to put in front of them. */
  function renderTrained(session) {
    const el = $("#trained"); if (!el) return;
    if ((state.condition.growth_display || "full") === "none") { el.classList.add("hidden"); return; }
    const rubric = (session.task || {}).rubric || {};
    const primary = rubric.primary_dimensions || [];
    const na = rubric.not_applicable_dimensions || [];
    if (!primary.length) { el.classList.add("hidden"); return; }
    el.classList.remove("hidden");
    const byKey = Object.fromEntries(state.cfg.dimensions.map(d => [d.key, d]));
    const chip = (k) => {
      const fam = FAMILIES[DIM_FAMILY[k]];
      return `<span class="tchip" style="--tc:${fam.color}"><i></i>${(byKey[k] || {}).zh || k}</span>`;
    };
    el.innerHTML = `<h4>🌱 这一关练的是</h4><div class="tchips">${primary.map(chip).join("")}</div>`
      + `<div class="tnote">彩点在这几项上又长了一点。`
      + (na.length ? `这一关用不上「${na.map(k => (byKey[k] || {}).zh || k).join("、")}」，所以不算在内。` : "")
      + `</div>`;
  }

  /** Badges this condition can actually offer. One definition, used by both the
   *  display and the rarity report, so the two can never disagree. */
  function badgePool() {
    const quiet = state.condition && state.condition.feedback_source !== "ai";
    const hasRef = !!(state.quest && state.quest.reference) && state.condition.reference_allowed;
    return ALL_BADGES.filter(b => !(quiet && b.evo) && !(b.needs === "reference" && !hasRef));
  }

  function renderBadges(session) {
    const el = $("#badges"); if (!el) return;
    // A badge the condition makes unreachable is not shown as "not earned":
    // greying it out tells the child they missed something never on offer.
    const pool = badgePool();

    const got = pool.filter(b => { try { return !!b.earned(session); } catch (e) { return false; } });
    const gotSet = new Set(got);
    const groups = [];
    pool.forEach(b => {
      let g = groups.find(x => x.name === b.g);
      if (!g) groups.push(g = { name: b.g, items: [] });
      g.items.push(b);
    });
    el.innerHTML = groups.map(g => {
      // earned first inside each group, so the child sees what they got
      const items = [...g.items].sort((a, b) => (gotSet.has(b) ? 1 : 0) - (gotSet.has(a) ? 1 : 0));
      return `<div class="badge-group"><h4>${g.name}</h4><div class="badge-row">` + items.map(b => {
        const on = gotSet.has(b);
        // Rarity is about the badge, not about you: "8 % of people have lit this"
        // gives the collecting feeling without comparing anyone's drawing.
        const st = ((state.rarity || {}).badges || {})[b.name];
        const pct = st && st.rarity !== null ? Math.round(st.rarity * 100) : null;
        const rare = on && pct !== null && pct <= 15;
        const line = pct === null ? ""
          : `<div class="rarity">${pct <= 0 ? "还没有人点亮过" : `${pct}% 的人点亮过`}</div>`;
        return `<div class="badge${on ? " new" : " locked"}${b.evo ? " evo" : ""}${rare ? " rare" : ""}" title="${b.desc}">
          <div class="b-ico">${b.icon}</div><div class="b-name">${b.name}</div>
          <div class="b-desc">${b.desc}</div>${on ? line : ""}</div>`;
      }).join("") + "</div></div>";
    }).join("");
    $("#badges-count").textContent = `点亮了 ${got.length}/${pool.length} 枚`;
  }
  $("#btn-again").onclick = async () => {
    await flushLog();
    state.sessionId = null; state.startedAt = null; state.phase = "before"; state.pendingFinal = null;
    $("#intent-text").value = "";
    if (state.study && state.study.sequence) {   // advance to the next task in the assigned order
      state.seqIdx = Math.min(state.seqIdx + 1, state.study.sequence.length - 1);
      renderStudyBar();
    }
    renderQuests();
    await loadCollection(); show("quest");
  };

  // 9 维分为 4 个家族，扇形图按家族上色（配色经 dataviz 校验：CVD 全部通过）
  const FAMILIES = {
    color: { label: "色彩", color: "#e8632b" },
    line:  { label: "线条", color: "#2b7de8" },
    comp:  { label: "画面", color: "#2e9e5b" },
    sem:   { label: "表达", color: "#7b4fd6" },
  };
  const DIM_FAMILY = {
    color_richness: "color", color_contrast: "color",
    line_combination: "line", line_texture: "line",
    picture_organization: "comp",
    realism: "sem", deformation: "sem", imagination: "sem", transformation: "sem",
  };
  // 扇区顺序：同家族相邻，读起来成组
  const CHART_ORDER = ["color_richness", "color_contrast", "line_combination", "line_texture",
    "picture_organization", "realism", "deformation", "imagination", "transformation"];

  const polar = (cx, cy, r, deg) => { const t = deg * Math.PI / 180; return [cx + r * Math.cos(t), cy + r * Math.sin(t)]; };
  const fmt = (n) => n.toFixed(2);
  function sectorPath(cx, cy, r, a0, a1) {
    const [x0, y0] = polar(cx, cy, r, a0), [x1, y1] = polar(cx, cy, r, a1);
    return `M${cx},${cy} L${fmt(x0)},${fmt(y0)} A${r},${r} 0 0 1 ${fmt(x1)},${fmt(y1)} Z`;
  }
  function arcPath(cx, cy, r, a0, a1) {
    const [x0, y0] = polar(cx, cy, r, a0), [x1, y1] = polar(cx, cy, r, a1);
    return `M${fmt(x0)},${fmt(y0)} A${r},${r} 0 0 1 ${fmt(x1)},${fmt(y1)}`;
  }

  // 南丁格尔玫瑰扇形图：每个维度一个扇区，半径 = 分数；baseline 存在时用虚线弧标出修改前的分数
  function roseChart(scores, baseline) {
    const max = state.cfg.scale_max, N = CHART_ORDER.length, SLOT = 360 / N, PAD = 2;
    const cx = 200, cy = 200, R = 118, LABEL_R = R + 20;
    const dimsByKey = Object.fromEntries(state.cfg.dimensions.map(d => [d.key, d]));
    const focus = new Set(state.quest ? state.quest.focus_dims : []);
    const rOf = (s) => (Math.max(1, Math.min(max, s)) / max) * R;

    let grid = "";
    for (let s = 1; s <= max; s++) grid += `<circle cx="${cx}" cy="${cy}" r="${fmt((s / max) * R)}" class="rose-grid"/>`;
    let sectors = "", marks = "", labels = "";
    CHART_ORDER.forEach((key, i) => {
      const d = dimsByKey[key], sc = scores.dims[key]; if (!d || !sc) return;
      // N/A gets a hollow slot, never a short petal: a small sector would read
      // as a low score for something this task never tested
      if (isNA(sc)) {
        const a0n = -90 + i * SLOT + PAD, a1n = -90 + (i + 1) * SLOT - PAD, midn = (a0n + a1n) / 2;
        const [nx, ny] = polar(cx, cy, LABEL_R, midn);
        const anch = Math.cos(midn * Math.PI / 180) > 0.25 ? "start" : Math.cos(midn * Math.PI / 180) < -0.25 ? "end" : "middle";
        sectors += `<path d="${sectorPath(cx, cy, R, a0n, a1n)}" fill="none" stroke="#e6e0d6" stroke-width="1" stroke-dasharray="3 3"><title>${d.zh}：这个任务不考察</title></path>`;
        labels += `<text x="${fmt(nx)}" y="${fmt(ny)}" text-anchor="${anch}" class="rose-label na">${d.zh}</text>`;
        return;
      }
      const fam = FAMILIES[DIM_FAMILY[key]];
      const a0 = -90 + i * SLOT + PAD, a1 = -90 + (i + 1) * SLOT - PAD, mid = (a0 + a1) / 2;
      const r = rOf(sc.score), isFocus = focus.has(key), ph = isPlaceholder(sc);
      const b = baseline && baseline.dims[key], delta = b ? sc.score - b.score : null;
      sectors += `<path d="${sectorPath(cx, cy, r, a0, a1)}" fill="${fam.color}" fill-opacity="${ph ? 0.26 : isFocus ? 0.95 : 0.72}"`
        + ` stroke="#fff" stroke-width="2"${isFocus && !ph ? ' class="rose-focus"' : ''}>`
        + `<title>${d.zh}${ph ? "（待模型评）" : ""}</title></path>`;
      if (b && !ph) {  // 修改前的水平：一条虚线弧
        const rb = rOf(b.score);
        marks += `<path d="${arcPath(cx, cy, rb, a0, a1)}" class="rose-before" stroke="${fam.color}"/>`;
      }
      const [lx, ly] = polar(cx, cy, LABEL_R, mid);
      const anchor = Math.cos(mid * Math.PI / 180) > 0.25 ? "start" : Math.cos(mid * Math.PI / 180) < -0.25 ? "end" : "middle";
      const arrow = delta !== null && Math.abs(delta) >= 0.05 ? (delta > 0 ? " ▲" : " ▼") : "";
      labels += `<text x="${fmt(lx)}" y="${fmt(ly)}" text-anchor="${anchor}" class="rose-label${isFocus ? " focus" : ""}">`
        + `<tspan>${d.zh}</tspan>${arrow ? `<tspan dx="3" class="rose-arw ${delta < 0 ? "dn" : "up"}">${arrow}</tspan>` : ""}</text>`;
    });
    const legend = Object.values(FAMILIES).map(f =>
      `<span class="rose-leg"><i style="background:${f.color}"></i>${f.label}</span>`).join("");
    return `<div class="rose-wrap">
      <svg viewBox="0 0 400 400" class="rose" role="img" aria-label="九维能力值扇形图">
        ${grid}${sectors}${marks}
        <circle cx="${cx}" cy="${cy}" r="26" class="rose-hub"/>
        <text x="${cx}" y="${cy + 9}" text-anchor="middle" font-size="26">🎨</text>
        ${labels}
      </svg>
      <div class="rose-legend">${legend}${baseline ? '<span class="rose-leg dash"><i></i>修改前</span>' : ""}</div>
    </div>`;
  }

  const isPlaceholder = (s) => /需模型评分/.test(s.note || "");
  /** N/A is not a low score — the task could not elicit this dimension at all. */
  const isNA = (s) => !!(s && (s.na || s.score === null || s.score === undefined));
  function stars(v) { const n = Math.round(Math.max(1, Math.min(state.cfg.scale_max, v))); return `${"★".repeat(n)}<u>${"☆".repeat(state.cfg.scale_max - n)}</u>`; }

  function renderScores(el, scores, baseline) {
    const focus = new Set(state.quest ? state.quest.focus_dims : []);
    const notes = state.cfg.dimensions.map(d => {
      const s = scores.dims[d.key]; if (!s) return "";
      if (isNA(s)) {
        const fam0 = FAMILIES[DIM_FAMILY[d.key]];
        return `<div class="dim na"><div class="name"><span><i class="dot" style="background:#d8d2c8"></i>${d.zh}</span>`
          + `<span class="sval"><span class="wait">这个任务不考察</span></span></div></div>`;
      }
      const ph = isPlaceholder(s);
      const b = baseline && baseline.dims[d.key], delta = b ? s.score - b.score : null;
      const arrow = (!ph && delta !== null && Math.abs(delta) >= 0.05)
        ? ` <span class="delta ${delta < 0 ? "neg" : ""}">${delta > 0 ? "▲ 进步了" : "▼"}</span>` : "";
      const fam = FAMILIES[DIM_FAMILY[d.key]];
      return `<div class="dim${focus.has(d.key) ? " focus" : ""}${ph ? " ph" : ""}">
        <div class="name"><span><i class="dot" style="background:${fam.color}"></i>${d.zh}</span>
          <span class="sval">${ph ? '<span class="wait">待模型评</span>' : `<span class="st">${stars(s.score)}</span>${arrow}`}</span></div></div>`;
    }).join("");
    el.innerHTML = `<div class="ability-head">🎨 能力值 · 你这次在这些地方使了劲<span class="muted small">（我们不打分，只看能力往哪长）</span></div>`
      + roseChart(scores, baseline) + `<div class="dim-notes">${notes}</div>`;
  }

  // ---------- sessions list ----------
  $("#link-sessions").onclick = async (e) => {
    e.preventDefault(); const rows = await api("/api/sessions"); const tb = $("#sessions-table tbody"); tb.innerHTML = "";
    rows.forEach(s => { const tr = document.createElement("tr"); tr.innerHTML = `<td>${s.created_at}</td><td>${s.quest_id}</td><td>${s.participant || ""}</td><td>${s.status}</td><td>${s.revised === null ? "—" : s.revised ? "是" : "否"}</td><td><a href="/files/${s.id}/before.png" target="_blank">before</a> · <a href="/files/${s.id}/after.png" target="_blank">after</a> · <a href="/api/sessions/${s.id}" target="_blank">json</a></td>`; tb.appendChild(tr); });
    show("sessions");
  };
  $("#btn-sessions-back").onclick = () => show("quest");
  // recording indicator: what is still only on this device
  ArtLog.onstatus(({ pending, online }) => {
    const el = $("#recstat"); if (!el) return;
    el.classList.toggle("warn", !online || pending > 0);
    $("#recstat-text").textContent = !online ? `离线 · ${pending} 条待上传`
      : pending ? `同步中 ${pending}` : state.sessionId ? "记录中" : "就绪";
  });
  window.addEventListener("beforeunload", (e) => { if (state.sessionId && !$("#view-draw").classList.contains("hidden")) { e.preventDefault(); e.returnValue = ""; } });

  init().catch(e => alert("初始化失败：" + e.message));
})();
