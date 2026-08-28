/* ArtQuest Stage 1 front-end: quest → intent → draw → feedback → revise → done. */
(() => {
  const $ = (s) => document.querySelector(s);
  const api = async (path, opts = {}) => {
    const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json();
  };

  const state = { cfg: null, quests: [], quest: null, emotion: null, sessionId: null, phase: "before",
    startedAt: null, events: [], dirtySinceSnapshot: false, timers: [], before: null };

  // ---------- views ----------
  const VIEWS = ["quest", "intent", "draw", "result", "final", "sessions"];
  function show(name) {
    VIEWS.forEach(v => $(`#view-${v}`).classList.toggle("hidden", v !== name));
    const order = ["quest", "intent", "draw", "result", "final"];
    document.querySelectorAll("#steps span").forEach(s => {
      const i = order.indexOf(s.dataset.step), j = order.indexOf(name);
      s.classList.toggle("active", i === j); s.classList.toggle("done", i < j);
    });
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
  let tool = "pencil", color = "#222222", size = 4, drawing = false, last = null;
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
  canvas.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 && e.pointerType === "mouse") return;
    canvas.setPointerCapture(e.pointerId); pushUndo(); drawing = true; last = pos(e);
    strokeStyle(last.p); ctx.beginPath(); ctx.moveTo(last.x, last.y); ctx.lineTo(last.x + 0.01, last.y); ctx.stroke();
    logEvent("stroke_start", { tool, color, size, pointer: e.pointerType });
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!drawing) return;
    const p = pos(e); strokeStyle(p);
    ctx.beginPath(); ctx.moveTo(last.x, last.y); ctx.lineTo(p.x, p.y); ctx.stroke(); last = p; state.dirtySinceSnapshot = true;
  });
  const endStroke = () => { if (drawing) { drawing = false; ctx.globalAlpha = 1; } };
  canvas.addEventListener("pointerup", endStroke); canvas.addEventListener("pointercancel", endStroke); canvas.addEventListener("pointerleave", endStroke);

  function undo() { if (!undoStack.length) return; redoStack.push(ctx.getImageData(0, 0, canvas.width, canvas.height)); ctx.putImageData(undoStack.pop(), 0, 0); logEvent("undo"); state.dirtySinceSnapshot = true; }
  function redo() { if (!redoStack.length) return; undoStack.push(ctx.getImageData(0, 0, canvas.width, canvas.height)); ctx.putImageData(redoStack.pop(), 0, 0); logEvent("redo"); state.dirtySinceSnapshot = true; }
  $("#btn-undo").onclick = undo; $("#btn-redo").onclick = redo;
  $("#btn-clear").onclick = () => { if (confirm("确定清空整张画布？")) { pushUndo(); ctx.globalAlpha = 1; ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, canvas.width, canvas.height); logEvent("clear"); state.dirtySinceSnapshot = true; } };
  document.addEventListener("keydown", (e) => {
    if ($("#view-draw").classList.contains("hidden")) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? redo() : undo(); }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") { e.preventDefault(); redo(); }
  });
  document.querySelectorAll("#tools button").forEach(b => b.onclick = () => {
    tool = b.dataset.tool; document.querySelectorAll("#tools button").forEach(x => x.classList.toggle("active", x === b)); logEvent("tool", { tool });
  });
  $("#size").oninput = (e) => { size = +e.target.value; $("#size-val").textContent = size; };
  const PALETTE = ["#222222", "#7a7a7a", "#ffffff", "#e63946", "#f4a261", "#ffd166", "#2a9d8f", "#4caf50", "#1d6fe0", "#7b4fd6", "#f28cb1", "#8d5524"];
  const pal = $("#palette");
  PALETTE.forEach(c => { const d = document.createElement("div"); d.style.background = c; d.title = c; d.onclick = () => setColor(c, d); pal.appendChild(d); });
  function setColor(c, el) { color = c; $("#color-custom").value = c; pal.querySelectorAll("div").forEach(x => x.classList.toggle("active", x === el)); if (tool === "eraser") document.querySelector('[data-tool="pencil"]').click(); logEvent("color", { color: c }); }
  pal.firstChild.classList.add("active");
  $("#color-custom").oninput = (e) => setColor(e.target.value, null);
  $("#btn-download").onclick = () => { const a = document.createElement("a"); a.download = `artquest-${state.sessionId || "draft"}.png`; a.href = canvas.toDataURL("image/png"); a.click(); logEvent("download"); };

  // ---------- process recording ----------
  const elapsed = () => state.startedAt ? Date.now() - state.startedAt : 0;
  function logEvent(type, detail) { if (state.startedAt) state.events.push({ t_ms: elapsed(), type, detail: detail || null }); }
  function takeEvents() { const ev = state.events; state.events = []; return ev; }
  async function snapshot() {
    if (!state.sessionId || !state.dirtySinceSnapshot) return;
    state.dirtySinceSnapshot = false;
    try {
      await api(`/api/sessions/${state.sessionId}/snapshot`, { method: "POST", body: JSON.stringify({ image: canvas.toDataURL("image/png"), elapsed_ms: elapsed(), events: takeEvents() }) });
      $("#snap-info").textContent = `已记录 ${new Date().toLocaleTimeString()}`;
    } catch (e) { console.warn("snapshot failed", e); }
  }
  function startTimers() {
    stopTimers();
    state.timers.push(setInterval(() => { const s = Math.floor(elapsed() / 1000); $("#timer").textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; }, 500));
    state.timers.push(setInterval(snapshot, state.cfg.snapshot_interval_sec * 1000));
  }
  function stopTimers() { state.timers.forEach(clearInterval); state.timers = []; }

  // ---------- flow ----------
  async function init() {
    state.cfg = await api("/api/config"); state.quests = await api("/api/quests");
    $("#backend-badge").textContent = `评分: ${state.cfg.scorer} · 反馈: ${state.cfg.feedback}` + (state.cfg.claude_available ? "" : " (离线模式)");
    const grid = $("#quest-grid"); grid.innerHTML = "";
    state.quests.forEach(q => {
      const c = document.createElement("div"); c.className = "quest-card";
      c.innerHTML = `<div class="type">${q.type}</div><h3>${q.title}</h3><p>${q.prompt}</p>`;
      c.onclick = () => chooseQuest(q); grid.appendChild(c);
    });
    const chips = $("#emotion-chips"); chips.innerHTML = "";
    state.cfg.emotions.forEach(em => { const b = document.createElement("button"); b.textContent = em; b.onclick = () => { state.emotion = em; chips.querySelectorAll("button").forEach(x => x.classList.toggle("active", x === b)); }; chips.appendChild(b); });
    show("quest");
  }
  function chooseQuest(q) {
    state.quest = q; $("#intent-quest-title").textContent = q.title; $("#intent-quest-prompt").textContent = q.prompt; $("#intent-quest-hint").textContent = "提示：" + q.hint; show("intent");
  }
  $("#btn-back-quest").onclick = () => show("quest");
  $("#btn-start-draw").onclick = async () => {
    if (!state.emotion) { alert("先选一个现在的心情吧"); return; }
    const intent = { emotion: state.emotion, text: $("#intent-text").value.trim() };
    const r = await api("/api/sessions", { method: "POST", body: JSON.stringify({ quest_id: state.quest.id, intent, participant: $("#participant").value.trim() }) });
    state.sessionId = r.session_id; state.phase = "before"; state.events = []; state.before = null;
    resetCanvas(); state.startedAt = Date.now(); state.dirtySinceSnapshot = false;
    $("#draw-quest-card").innerHTML = `<div class="type">${state.quest.type}</div><h3>${state.quest.title}</h3><p>${state.quest.prompt}</p>`;
    $("#draw-intent-card").innerHTML = `心情：<b>${intent.emotion}</b><br>我想表达：${intent.text || "（没写）"}`;
    $("#revision-banner").classList.add("hidden"); $("#btn-submit").classList.remove("hidden"); $("#snap-info").textContent = "";
    startTimers(); show("draw");
  };

  $("#btn-submit").onclick = async () => {
    if (!undoStack.length && !state.dirtySinceSnapshot) { if (!confirm("画布好像还是空的，确定提交吗？")) return; }
    overlay("正在观察你的画……"); stopTimers();
    const image = canvas.toDataURL("image/png");
    try {
      const r = await api(`/api/sessions/${state.sessionId}/submit`, { method: "POST", body: JSON.stringify({ image, elapsed_ms: elapsed(), phase: "before", events: takeEvents() }) });
      state.before = { image, scores: r.scores };
      $("#result-img").src = image; renderScores($("#scores"), r.scores, null); $("#score-summary").textContent = r.scores.summary || "";
      $("#feedback-text").textContent = r.feedback.text; show("result");
    } catch (e) { alert("提交失败：" + e.message); startTimers(); }
    overlay(null);
  };
  $("#btn-revise").onclick = () => {
    state.phase = "after"; logEvent("revision_start");
    $("#btn-submit").classList.add("hidden"); $("#revision-banner").classList.remove("hidden"); startTimers(); show("draw");
  };
  $("#btn-skip-revise").onclick = async () => {
    overlay("正在保存……");
    const r = await api(`/api/sessions/${state.sessionId}/finalize`, { method: "POST", body: JSON.stringify({ elapsed_ms: elapsed(), events: takeEvents() }) });
    showFinal(r.session, state.before.image, state.before.image, null); overlay(null);
  };
  $("#btn-submit-after").onclick = async () => {
    overlay("正在比较修改前后……"); stopTimers();
    const image = canvas.toDataURL("image/png");
    try {
      const r = await api(`/api/sessions/${state.sessionId}/submit`, { method: "POST", body: JSON.stringify({ image, elapsed_ms: elapsed(), phase: "after", events: takeEvents() }) });
      showFinal(r.session, state.before.image, image, r.comparison);
    } catch (e) { alert("提交失败：" + e.message); startTimers(); }
    overlay(null);
  };
  function showFinal(session, beforeImg, afterImg, comparison) {
    $("#final-before").src = beforeImg; $("#final-after").src = afterImg;
    $("#comparison-text").textContent = comparison ? comparison.text : "这次没有修改。下次可以试试根据反馈改一小处，看看感觉有什么不同。";
    renderScores($("#final-scores"), session.after.scores, session.before.scores);
    $("#final-meta").textContent = `Session ${session.id} · 过程截图 ${session.snapshots.length} 张 · 事件 ${session.events.length} 条 · 数据在 data/sessions/${session.id}/`;
    show("final");
  }
  $("#btn-again").onclick = () => { state.sessionId = null; state.startedAt = null; $("#intent-text").value = ""; show("quest"); };

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
      const r = rOf(sc.score), isFocus = focus.has(key);
      const b = baseline && baseline.dims[key], delta = b ? sc.score - b.score : null;
      sectors += `<path d="${sectorPath(cx, cy, r, a0, a1)}" fill="${fam.color}" fill-opacity="${isFocus ? 0.95 : 0.72}"`
        + ` stroke="#fff" stroke-width="2"${isFocus ? ' class="rose-focus"' : ''}>`
        + `<title>${d.zh}：${sc.score}/${max}${delta !== null ? `（${delta >= 0 ? "+" : ""}${delta.toFixed(1)}）` : ""}</title></path>`;
      if (b) {  // 修改前的水平：一条虚线弧
        const rb = rOf(b.score);
        marks += `<path d="${arcPath(cx, cy, rb, a0, a1)}" class="rose-before" stroke="${fam.color}"/>`;
      }
      const [lx, ly] = polar(cx, cy, LABEL_R, mid);
      const anchor = Math.cos(mid * Math.PI / 180) > 0.25 ? "start" : Math.cos(mid * Math.PI / 180) < -0.25 ? "end" : "middle";
      labels += `<text x="${fmt(lx)}" y="${fmt(ly)}" text-anchor="${anchor}" class="rose-label${isFocus ? " focus" : ""}">`
        + `<tspan>${d.zh}</tspan><tspan dx="4" class="rose-num">${sc.score}${delta !== null ? ` ${delta >= 0 ? "▲" : "▼"}` : ""}</tspan></text>`;
    });
    const shown = CHART_ORDER.map(k => scores.dims[k]).filter(Boolean);
    const avg = shown.length ? shown.reduce((a, s) => a + s.score, 0) / shown.length : 0;
    const legend = Object.values(FAMILIES).map(f =>
      `<span class="rose-leg"><i style="background:${f.color}"></i>${f.label}</span>`).join("");
    return `<div class="rose-wrap">
      <svg viewBox="0 0 400 400" class="rose" role="img" aria-label="九维扇形评分图">
        ${grid}${sectors}${marks}
        <circle cx="${cx}" cy="${cy}" r="30" class="rose-hub"/>
        <text x="${cx}" y="${cy - 2}" text-anchor="middle" class="rose-avg">${avg.toFixed(1)}</text>
        <text x="${cx}" y="${cy + 14}" text-anchor="middle" class="rose-avg-sub">平均 /${max}</text>
        ${labels}
      </svg>
      <div class="rose-legend">${legend}${baseline ? '<span class="rose-leg dash"><i></i>修改前</span>' : ""}</div>
    </div>`;
  }

  function renderScores(el, scores, baseline) {
    const focus = new Set(state.quest ? state.quest.focus_dims : []);
    const notes = state.cfg.dimensions.map(d => {
      const s = scores.dims[d.key]; if (!s) return "";
      const b = baseline && baseline.dims[d.key], delta = b ? s.score - b.score : null;
      const fam = FAMILIES[DIM_FAMILY[d.key]];
      return `<div class="dim${focus.has(d.key) ? " focus" : ""}">
        <div class="name"><span><i class="dot" style="background:${fam.color}"></i>${d.zh}</span>
          <span class="sval">${s.score}${delta !== null ? ` <span class="delta ${delta < 0 ? "neg" : ""}">${delta >= 0 ? "+" : ""}${delta.toFixed(1)}</span>` : ""}</span></div>
        <div class="note">${s.note || ""}</div></div>`;
    }).join("");
    el.innerHTML = roseChart(scores, baseline) + `<div class="dim-notes">${notes}</div>`;
  }

  // ---------- sessions list ----------
  $("#link-sessions").onclick = async (e) => {
    e.preventDefault(); const rows = await api("/api/sessions"); const tb = $("#sessions-table tbody"); tb.innerHTML = "";
    rows.forEach(s => { const tr = document.createElement("tr"); tr.innerHTML = `<td>${s.created_at}</td><td>${s.quest_id}</td><td>${s.participant || ""}</td><td>${s.status}</td><td>${s.revised === null ? "—" : s.revised ? "是" : "否"}</td><td><a href="/files/${s.id}/before.png" target="_blank">before</a> · <a href="/files/${s.id}/after.png" target="_blank">after</a> · <a href="/api/sessions/${s.id}" target="_blank">json</a></td>`; tb.appendChild(tr); });
    show("sessions");
  };
  $("#btn-sessions-back").onclick = () => show("quest");
  window.addEventListener("beforeunload", (e) => { if (state.sessionId && !$("#view-draw").classList.contains("hidden")) { e.preventDefault(); e.returnValue = ""; } });

  init().catch(e => alert("初始化失败：" + e.message));
})();
