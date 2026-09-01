/* ArtQuest Stage 1 front-end: quest → intent → draw → feedback → revise → done. */
(() => {
  const $ = (s) => document.querySelector(s);
  const api = async (path, opts = {}) => {
    const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json();
  };

  const state = { cfg: null, quests: [], quest: null, emotion: null, sessionId: null, phase: "before",
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
  const STAGES = [
    { key: "quest",  name: "出发", icon: "🎒" },
    { key: "intent", name: "心愿", icon: "💭" },
    { key: "draw",   name: "创作", icon: "🎨" },
    { key: "result", name: "支招", icon: "💡" },
    { key: "evolve", name: "进化", icon: "✨" },
    { key: "final",  name: "宝藏", icon: "🏆" },
  ];
  function renderTrail(currentKey) {
    const el = document.getElementById("trail"); if (!el) return;
    const order = STAGES.map(s => s.key), idx = order.indexOf(currentKey);
    const xs = STAGES.map((_, i) => 80 + i * 208);           // 80,288,…,1120
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

  function resetCanvas() { ctx.globalAlpha = 1; ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, canvas.width, canvas.height); undoStack.length = redoStack.length = 0; }
  function pos(e) {
    const r = canvas.getBoundingClientRect();
    return { x: (e.clientX - r.left) * canvas.width / r.width, y: (e.clientY - r.top) * canvas.height / r.height, p: e.pressure || 0.5 };
  }
  function pushUndo() { undoStack.push(ctx.getImageData(0, 0, canvas.width, canvas.height)); if (undoStack.length > MAX_UNDO) undoStack.shift(); redoStack.length = 0; }
  function strokeStyle(p) {
    const t = TOOLS[tool];
    const w = size * t.size * (t.pressure ? (1 - t.pressure + t.pressure * 2 * p) : 1);
    ctx.lineWidth = Math.max(0.5, w); ctx.lineCap = t.cap; ctx.lineJoin = "round";
    ctx.strokeStyle = t.color || color; ctx.globalAlpha = t.alpha;
  }
  // -- stroke recording: the core process datum. Raw points only —
  //    speed / length / hesitation / rhythm are derived offline, never here.
  const R = (v, n) => { const f = Math.pow(10, n); return Number.isFinite(v) ? Math.round(v * f) / f : 0; };
  function samplePoint(e, t0) {
    const q = pos(e);
    return [R(q.x, 1), R(q.y, 1), Math.round(elapsed() - t0), R(e.pressure || 0, 3), Math.round(e.tiltX || 0), Math.round(e.tiltY || 0)];
  }
  function beginStroke(e) {
    const t0 = elapsed();
    curStroke = { t0, tool, color: TOOLS[tool].color || color, size, opacity: TOOLS[tool].alpha,
      erase: tool === "eraser", pointer_type: e.pointerType || "", points: [samplePoint(e, t0)] };
  }
  function finishStroke() {
    if (!curStroke) return;
    const s = curStroke; curStroke = null;
    const id = "s" + String(++strokeCount).padStart(5, "0"), last_pt = s.points[s.points.length - 1];
    ArtLog.stroke({ stroke_id: id, phase: state.phase, t_start_ms: Math.round(s.t0), t_end_ms: Math.round(s.t0 + last_pt[2]),
      tool: s.tool, color: s.color, size: s.size, opacity: s.opacity, erase: s.erase,
      pointer_type: s.pointer_type, points: s.points });
    // the same stroke also lands in the unified event timeline, cross-referenced by id
    logEvent(s.erase ? "ERASE" : "STROKE", { stroke_id: id, tool: s.tool, color: s.color, size: s.size, n: s.points.length, dur_ms: last_pt[2] });
  }
  canvas.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 && e.pointerType === "mouse") return;
    if (state.timeUp) return;
    canvas.setPointerCapture(e.pointerId); pushUndo(); drawing = true; last = pos(e); beginStroke(e);
    strokeStyle(last.p); ctx.beginPath(); ctx.moveTo(last.x, last.y); ctx.lineTo(last.x + 0.01, last.y); ctx.stroke();
    markActive();
  });
  canvas.addEventListener("pointermove", (e) => {
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
  const endStroke = () => { if (drawing) { drawing = false; ctx.globalAlpha = 1; finishStroke(); } };
  canvas.addEventListener("pointerup", endStroke); canvas.addEventListener("pointercancel", endStroke); canvas.addEventListener("pointerleave", endStroke);

  function undo() { if (!undoStack.length) return; redoStack.push(ctx.getImageData(0, 0, canvas.width, canvas.height)); ctx.putImageData(undoStack.pop(), 0, 0); logEvent("UNDO"); state.dirtySinceSnapshot = true; }
  function redo() { if (!redoStack.length) return; undoStack.push(ctx.getImageData(0, 0, canvas.width, canvas.height)); ctx.putImageData(redoStack.pop(), 0, 0); logEvent("REDO"); state.dirtySinceSnapshot = true; }
  $("#btn-undo").onclick = undo; $("#btn-redo").onclick = redo;
  $("#btn-clear").onclick = () => { if (confirm("确定清空整张画布？")) { pushUndo(); ctx.globalAlpha = 1; ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, canvas.width, canvas.height); logEvent("CLEAR"); state.dirtySinceSnapshot = true; } };
  document.addEventListener("keydown", (e) => {
    if ($("#view-draw").classList.contains("hidden")) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? redo() : undo(); }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") { e.preventDefault(); redo(); }
  });
  document.querySelectorAll("#tools button").forEach(b => b.onclick = () => {
    if (b.disabled) return;
    tool = b.dataset.tool; document.querySelectorAll("#tools button").forEach(x => x.classList.toggle("active", x === b)); logEvent("BRUSH_CHANGE", { tool });
  });
  $("#size").oninput = (e) => { size = +e.target.value; $("#size-val").textContent = size; logEvent("SIZE_CHANGE", { size }); };
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
  function setColor(c, el) { color = c; $("#color-custom").value = c; pal.querySelectorAll("div").forEach(x => x.classList.toggle("active", x === el)); if (tool === "eraser") document.querySelector('[data-tool="pencil"]').click(); logEvent("COLOR_CHANGE", { color: c }); state.buddyTick++; updateBuddy(); }
  pal.firstChild.classList.add("active");
  $("#color-custom").oninput = (e) => setColor(e.target.value, null);
  $("#btn-download").onclick = () => { const a = document.createElement("a"); a.download = `artquest-${state.sessionId || "draft"}.png`; a.href = canvas.toDataURL("image/png"); a.click(); logEvent("DOWNLOAD"); };

  // ---------- process recording ----------
  const elapsed = () => state.startedAt ? Date.now() - state.startedAt : 0;
  const IDLE_MS = 3000;   // no input for this long counts as a pause worth logging
  /** One line of the append-only operation log; buffered locally, flushed in batches. */
  function logEvent(type, payload) { if (state.sessionId) ArtLog.event(type, elapsed(), payload || null); markActive(); }
  function markActive() {
    const t = elapsed();
    if (state.idle) { ArtLog.event("IDLE_END", t, { duration_ms: Math.round(t - state.lastActivity), phase: state.phase }); state.idle = false; }
    state.lastActivity = t;
  }
  function checkIdle() {
    if (!state.sessionId || state.idle) return;
    const t = elapsed();
    if (t - state.lastActivity >= IDLE_MS) { state.idle = true; ArtLog.event("IDLE_START", t, { since_ms: Math.round(state.lastActivity), phase: state.phase }); }
  }
  /** Push everything queued locally, then report what is still unsent. */
  async function flushLog() { try { await ArtLog.flush(); } catch (e) { /* keep the queue */ } return await ArtLog.pending(); }
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
  /** Apply the frozen condition to the UI (gamification level, undo, reference). */
  function applyCondition() {
    const c = state.condition;
    document.body.classList.toggle("quiet", c.ui === "quiet");
    ["#btn-undo", "#btn-redo"].forEach(sel => { const b = $(sel); if (b) { b.disabled = !c.undo_allowed; b.classList.toggle("hidden", !c.undo_allowed); } });
  }
  /** Per-task condition: reference image, time limit, allowed tools. */
  function applyTask(q) {
    const ref = q.reference, allowRef = state.condition.reference_allowed && !!ref;
    $("#refpanel").classList.toggle("hidden", !allowRef);
    $("#ref-wrap").classList.add("hidden");
    if (allowRef) { $("#ref-img").src = ref.file || `/static/refs/${ref.id}.png`; if (ref.mode === "always") toggleRef(true); }
    state.timeUp = false; $("#limit-info").textContent = ""; $("#limit-info").classList.remove("low");
    const allowed = q.allowed_tools;
    document.querySelectorAll("#tools button").forEach(b => {
      const ok = !allowed || allowed.indexOf(b.dataset.tool) >= 0;
      b.disabled = !ok; b.classList.toggle("off", !ok);
      if (!ok && b.classList.contains("active")) document.querySelector('[data-tool="pencil"]').click();
    });
  }
  function toggleRef(open) {
    const wrap = $("#ref-wrap"), willOpen = open !== undefined ? open : wrap.classList.contains("hidden");
    wrap.classList.toggle("hidden", !willOpen);
    $("#btn-ref-toggle").textContent = willOpen ? "🖼 收起参考图" : "🖼 看看参考图";
    logEvent(willOpen ? "REFERENCE_OPEN" : "REFERENCE_CLOSE", { task_id: state.quest && state.quest.id });
  }
  $("#btn-ref-toggle").onclick = () => toggleRef();

  // ---------- flow ----------
  function renderQuests() {
    const grid = $("#quest-grid"); grid.innerHTML = "";
    const seq = state.study && state.study.sequence ? state.study.sequence : null;
    const byId = Object.fromEntries(state.quests.map(q => [q.id, q]));
    const list = seq ? seq.map(id => byId[id]).filter(Boolean) : state.quests;
    list.forEach((q, i) => {
      const fb = QUEST_STYLE[q.id] || {};
      const icon = q.icon || fb.icon || "🎨", col = q.color || fb.c || "#e8632b";
      const locked = !!seq && i !== state.seqIdx;
      const c = document.createElement("div");
      c.className = "quest-card" + (locked ? " locked" : ""); c.style.setProperty("--qc", col);
      c.innerHTML = `<div class="qc-top"><span class="qc-icon">${icon}</span><span class="type">${q.type}</span></div>`
        + `<h3>${q.title}</h3><p>${q.prompt}</p>`
        + `<span class="qc-go">${locked ? "稍后解锁" : seq ? `第 ${i + 1} 关 · 开始 →` : "开始创作 →"}</span>`;
      if (!locked) c.onclick = () => chooseQuest(q);
      grid.appendChild(c);
    });
  }
  async function init() {
    state.cfg = await api("/api/config"); state.quests = await api("/api/quests");
    state.anonId = anonId();
    $("#backend-badge").textContent = `评分: ${state.cfg.scorer} · 反馈: ${state.cfg.feedback}` + (state.cfg.claude_available ? "" : " (离线模式)");
    await setupStudy();
    applyCondition();
    $("#participant").value = savedPid();
    renderQuests();
    const chips = $("#emotion-chips"); chips.innerHTML = "";
    state.cfg.emotions.forEach(em => { const b = document.createElement("button"); b.textContent = em; b.onclick = () => { state.emotion = em; chips.querySelectorAll("button").forEach(x => x.classList.toggle("active", x === b)); }; chips.appendChild(b); });
    await loadCollection();
    show("quest");
  }
  function chooseQuest(q) {
    state.quest = q; $("#intent-quest-title").textContent = q.title; $("#intent-quest-prompt").textContent = q.prompt; $("#intent-quest-hint").textContent = "提示：" + q.hint; show("intent");
  }
  $("#btn-back-quest").onclick = () => show("quest");
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
    state.condition = { ...state.condition, ...(r.session.condition || {}) };  // the server froze it; mirror it back
    resetCanvas(); state.startedAt = Date.now(); state.dirtySinceSnapshot = false;
    strokeCount = 0; state.lastActivity = 0; state.idle = false;
    await ArtLog.start(state.sessionId);
    applyTask(state.quest);
    $("#draw-quest-card").innerHTML = `<div class="type">${state.quest.type}</div><h3>${state.quest.title}</h3><p>${state.quest.prompt}</p>`;
    $("#draw-intent-card").innerHTML = `心情：<b>${intent.emotion}</b><br>我想表达：${intent.text || "（没写）"}`;
    $("#revision-banner").classList.add("hidden"); $("#btn-submit").classList.remove("hidden"); $("#snap-info").textContent = "";
    state.buddyTick = 0; updateBuddy();
    startTimers(); show("draw");
  };

  $("#btn-submit").onclick = async () => {
    if (!undoStack.length && !state.dirtySinceSnapshot) { if (!confirm("画布好像还是空的，确定提交吗？")) return; }
    overlay("正在观察你的画……"); stopTimers();
    const image = canvas.toDataURL("image/png");
    try {
      const pending = await flushLog();
      const r = await api(`/api/sessions/${state.sessionId}/submit`, { method: "POST", body: JSON.stringify({ image, elapsed_ms: elapsed(), phase: "before", pending }) });
      state.before = { image, scores: r.scores };
      $("#result-img").src = image; renderScores($("#scores"), r.scores, null); $("#score-summary").textContent = r.scores.summary || "";
      const fbSp = $("#fb-sprite"); if (fbSp) fbSp.innerHTML = spriteInner(buddyColor(), "happy");
      $("#feedback-text").textContent = r.feedback.text; show("result");
    } catch (e) { alert("提交失败：" + e.message); startTimers(); }
    overlay(null);
  };
  $("#btn-revise").onclick = () => {
    state.phase = "after"; logEvent("REVISION_START");
    $("#btn-submit").classList.add("hidden"); $("#revision-banner").classList.remove("hidden"); startTimers(); show("draw");
  };
  $("#btn-skip-revise").onclick = async () => {
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
    const body = skip ? {} : { ...answers, hardest_part: $("#survey-hardest").value.trim() };
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
    if (state.condition.questionnaire) { renderSurvey(); show("survey"); return; }
    showFinal(session, beforeImg, afterImg, comparison);
  }

  function showFinal(session, beforeImg, afterImg, comparison) {
    state.revised = session.revised;
    $("#final-before").src = beforeImg; $("#final-after").src = afterImg;
    const cmpSp = $("#cmp-sprite"); if (cmpSp) cmpSp.innerHTML = spriteInner(buddyColor(), session.revised ? "happy" : "normal");
    $("#comparison-text").textContent = comparison ? comparison.text : "这次没有走进化关～下次试试根据我的话改一小处，就能解锁 🔁 进化大师徽章！";
    renderBadges(session);
    renderScores($("#final-scores"), session.after.scores, session.before.scores);
    $("#final-meta").textContent = `Session ${session.id} · 过程截图 ${session.snapshots.length} 张 · 事件 ${session.events.length} 条 · 数据在 data/sessions/${session.id}/`;
    show("final");
  }

  // ===== 过程徽章（只奖励过程，不奖励分数）=====
  const dimScore = (s, k) => ((s.after || s.before || {}).scores?.dims?.[k]?.score) ?? 0;
  const drawMs = (s) => (s.after?.elapsed_ms || s.before?.elapsed_ms || 0);
  const distinctIn = (s, types, field) => new Set((s.events || [])
    .filter(e => types.indexOf(e.type) >= 0)
    .map(e => (e.payload || e.detail || {})[field]).filter(Boolean)).size;
  const BADGES = [
    { icon: "🌈", name: "冷暖对比", desc: "画面里冷色暖色都用上了", earned: s => dimScore(s, "color_contrast") >= 4 },
    { icon: "🎨", name: "缤纷调色", desc: "用了 5 种以上颜色", earned: s => distinctIn(s, ["COLOR_CHANGE", "STROKE"], "color") >= 5 },
    { icon: "🖌", name: "工具全能", desc: "用了 3 种以上工具", earned: s => distinctIn(s, ["BRUSH_CHANGE", "STROKE", "ERASE"], "tool") >= 3 },
    { icon: "⏱️", name: "专注之心", desc: "专注创作超过 5 分钟", earned: s => drawMs(s) >= 300000 },
    { icon: "🔁", name: "进化大师", desc: "走完进化关，改了自己的作品", earned: s => s.revised === true, evo: true },
  ];
  function renderBadges(session) {
    const el = $("#badges"); if (!el) return;
    el.innerHTML = BADGES.map(b => {
      const got = !!b.earned(session);
      const hint = (!got && b.evo) ? "走完 ✨进化关 解锁" : b.desc;
      return `<div class="badge${got ? " new" : " locked"}${b.evo ? " evo" : ""}">
        <div class="b-ico">${b.icon}</div><div class="b-name">${b.name}</div><div class="b-desc">${hint}</div></div>`;
    }).join("");
    const n = BADGES.filter(b => b.earned(session)).length;
    $("#badges-count").textContent = `点亮了 ${n}/${BADGES.length} 枚`;
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
  function stars(v) { const n = Math.round(Math.max(1, Math.min(state.cfg.scale_max, v))); return `${"★".repeat(n)}<u>${"☆".repeat(state.cfg.scale_max - n)}</u>`; }

  function renderScores(el, scores, baseline) {
    const focus = new Set(state.quest ? state.quest.focus_dims : []);
    const notes = state.cfg.dimensions.map(d => {
      const s = scores.dims[d.key]; if (!s) return "";
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
