/* ArtQuest Stage 1 front-end: quest → intent → draw → feedback → revise → done. */
(() => {
  const $ = (s) => document.querySelector(s);
  const api = async (path, opts = {}) => {
    const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json();
  };

  const state = { cfg: null, quests: [], families: [], allSessions: [], rarity: null, quest: null, emotion: null, sessionId: null, phase: "before", feedback: null,
    startedAt: null, dirtySinceSnapshot: false, timers: [], before: null, color: "#f79433", buddyTick: 0,
    anonId: "", condition: {}, study: null, seqIdx: 0, lastActivity: 0, idle: false, timeUp: false, pendingFinal: null,
    entered: false, worldColor: "", buddyName: "" };

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

  // ---------- 图标 ----------
  // 一套自己的线性图标：粗描边、圆端点、24×24 网格，全部用 currentColor 上色，
  // 所以放进彩色圆章里也好、放进灰色未解锁态里也好，都是同一套形状。
  // 不用 emoji —— emoji 在每个系统上长得都不一样，还带着别人的视觉语言。
  const ICONS = {
    // 品牌 / 任务
    palette: '<path d="M12 2.8C6.4 2.8 2.4 6.8 2.4 12.2c0 5 3.8 8.8 8.8 8.8 1.6 0 2.6-.9 2.6-2.2 0-.6-.2-1-.6-1.5-.3-.4-.5-.8-.5-1.3 0-1 .8-1.8 1.9-1.8h1.6c3.2 0 5.4-2.2 5.4-5.4 0-3.9-3.7-6-9.6-6Z"/><circle cx="7.2" cy="11.8" r="1.2" fill="currentColor" stroke="none"/><circle cx="10.4" cy="7.8" r="1.2" fill="currentColor" stroke="none"/><circle cx="15" cy="8.8" r="1.2" fill="currentColor" stroke="none"/>',
    backpack: '<path d="M4.2 11.4a5.2 5.2 0 0 1 5.2-5.2h5.2a5.2 5.2 0 0 1 5.2 5.2v6.2a3 3 0 0 1-3 3H7.2a3 3 0 0 1-3-3Z"/><path d="M9 6.2V5a3 3 0 0 1 6 0v1.2"/><path d="M9.2 20.6v-5.4h5.6v5.4"/>',
    think: '<path d="M6.4 4.2h11.2a3.4 3.4 0 0 1 3.4 3.4v4.8a3.4 3.4 0 0 1-3.4 3.4h-5.4l-4.8 3.6v-3.6h-1a3.4 3.4 0 0 1-3.4-3.4V7.6a3.4 3.4 0 0 1 3.4-3.4Z"/><circle cx="8.6" cy="10" r="1.15" fill="currentColor" stroke="none"/><circle cx="12" cy="10" r="1.15" fill="currentColor" stroke="none"/><circle cx="15.4" cy="10" r="1.15" fill="currentColor" stroke="none"/>',
    bulb: '<path d="M12 2.8a6.6 6.6 0 0 0-3.8 12v2.6h7.6v-2.6A6.6 6.6 0 0 0 12 2.8Z"/><path d="M9.6 19.6h4.8"/><path d="M10.6 21.8h2.8"/>',
    sparkle: '<path d="M11.4 2.6c.6 4.4 1.8 6.2 6.2 6.9-4.4.7-5.6 2.5-6.2 6.9-.6-4.4-1.8-6.2-6.2-6.9 4.4-.7 5.6-2.5 6.2-6.9Z" fill="currentColor"/><path d="M18.4 14.6c.3 2.2.9 3.1 3.1 3.5-2.2.4-2.8 1.3-3.1 3.5-.3-2.2-.9-3.1-3.1-3.5 2.2-.4 2.8-1.3 3.1-3.5Z" fill="currentColor"/>',
    trophy: '<path d="M7.4 3.4h9.2v5.8a4.6 4.6 0 0 1-9.2 0Z"/><path d="M7.4 5.2H4.4v1.6a3.8 3.8 0 0 0 3.6 3.8"/><path d="M16.6 5.2h3v1.6a3.8 3.8 0 0 1-3.6 3.8"/><path d="M12 13.8v4"/><rect x="7.8" y="17.8" width="8.4" height="3" rx="1.5"/>',
    // 画画工具（同一支笔转 45°，只有笔尖不一样）
    pencil: '<g transform="rotate(-45 12 12)"><path d="M8.6 6.8a3.4 3.4 0 0 1 6.8 0v5.8H8.6Z"/><path d="M8.6 12.6h6.8L12 20.4Z"/><path d="M8.6 10h6.8"/></g>',
    brush: '<g transform="rotate(-45 12 12)"><rect x="9.4" y="3.4" width="5.2" height="8" rx="2.4"/><path d="M8 11.4h8v2.4a4 4 0 0 1-.6 2.1l-2.2 3.5a1.4 1.4 0 0 1-2.4 0l-2.2-3.5a4 4 0 0 1-.6-2.1Z"/></g>',
    marker: '<g transform="rotate(-45 12 12)"><rect x="7.6" y="3.4" width="8.8" height="8.6" rx="2.6"/><path d="M9.2 12h5.6l-.8 6.4a1.3 1.3 0 0 1-1.3 1.1h-1.4a1.3 1.3 0 0 1-1.3-1.1Z"/></g>',
    eraser: '<g transform="rotate(-30 12 12)"><rect x="3.6" y="8.6" width="16.8" height="7.4" rx="1.6"/><path d="M11.4 8.6V16"/></g>',
    undo: '<path d="M4.2 8.8h9.6a5.4 5.4 0 0 1 0 10.8H9.2"/><path d="M8 4.4 3.4 8.8 8 13.2"/>',
    redo: '<path d="M19.8 8.8h-9.6a5.4 5.4 0 0 0 0 10.8h4.6"/><path d="M16 4.4l4.6 4.4L16 13.2"/>',
    trash: '<path d="M3.6 6.4h16.8"/><path d="M9.4 6.4V4.8a1.4 1.4 0 0 1 1.4-1.4h2.4a1.4 1.4 0 0 1 1.4 1.4v1.6"/><path d="m5.9 6.4.9 12.6a2 2 0 0 0 2 1.9h6.4a2 2 0 0 0 2-1.9l.9-12.6"/><path d="M10 10.6v6M14 10.6v6"/>',
    download: '<path d="M12 3.4v11.2"/><path d="m7.4 10.2 4.6 4.6 4.6-4.6"/><path d="M4.4 17.6v1.4a1.8 1.8 0 0 0 1.8 1.8h11.6a1.8 1.8 0 0 0 1.8-1.8v-1.4"/>',
    zoomIn: '<circle cx="10.6" cy="10.6" r="6.8"/><path d="m15.6 15.6 5.2 5.2"/><path d="M10.6 7.9v5.4M7.9 10.6h5.4"/>',
    zoomOut: '<circle cx="10.6" cy="10.6" r="6.8"/><path d="m15.6 15.6 5.2 5.2"/><path d="M7.9 10.6h5.4"/>',
    search: '<circle cx="10.6" cy="10.6" r="6.8"/><path d="m15.6 15.6 5.2 5.2"/>',
    hand: '<path d="M8.4 12.2V5.8a1.7 1.7 0 0 1 3.4 0v4.4"/><path d="M11.8 10.2V4.8a1.7 1.7 0 0 1 3.4 0v5.4"/><path d="M15.2 10.6V6.9a1.7 1.7 0 0 1 3.4 0V14a6.8 6.8 0 0 1-6.8 6.8h-.5a5 5 0 0 1-4-2l-2.7-3.6a1.8 1.8 0 0 1 2.8-2.2l1.8 1.9"/>',
    image: '<rect x="3" y="4.6" width="18" height="14.8" rx="3.2"/><path d="m5.6 16.6 4.4-4.8 3 3.2 2.4-2.6 3.4 4"/><circle cx="15.4" cy="9.2" r="1.5"/>',
    star: '<path d="M12 4 14.06 9.17 19.61 9.53 15.33 13.08 16.7 18.47 12 15.5 7.3 18.47 8.67 13.08 4.39 9.53 9.94 9.17Z" fill="currentColor"/>',
    check: '<path d="m4.8 12.6 4.8 4.8L19.4 6.6"/>',
    lock: '<rect x="4.4" y="10" width="15.2" height="10.6" rx="3.2"/><path d="M8 10V7.6a4 4 0 0 1 8 0V10"/>',
    clock: '<circle cx="12" cy="13.4" r="7.8"/><path d="M12 9v4.4l3 1.8"/><path d="M9.4 2.6h5.2"/><path d="M12 2.6v3"/>',
    bolt: '<path d="M13.4 2.8 5.8 13h5l-1.2 8.2L18.2 11h-5.4Z" fill="currentColor"/>',
    loop: '<path d="M20.4 12a8.4 8.4 0 1 1-2.5-6"/><path d="M20.8 3.4v5.2h-5.2"/>',
    map: '<path d="M9 4.4 3.4 6.8v12.8L9 17.2l6 2.4 5.6-2.4V4.4L15 6.8Z"/><path d="M9 4.4v12.8M15 6.8v12.8"/>',
    eye: '<path d="M2.6 12S6.2 5.6 12 5.6 21.4 12 21.4 12 17.8 18.4 12 18.4 2.6 12 2.6 12Z"/><circle cx="12" cy="12" r="2.9"/>',
    hourglass: '<path d="M6.6 3.4h10.8M6.6 20.6h10.8"/><path d="M7.8 3.4v3c0 2.2 4.2 3.9 4.2 5.6s-4.2 3.4-4.2 5.6v3"/><path d="M16.2 3.4v3c0 2.2-4.2 3.9-4.2 5.6s4.2 3.4 4.2 5.6v3"/>',
    compass: '<circle cx="12" cy="12" r="8.6"/><path d="m15.4 8.6-2 4.8-4.8 2 2-4.8Z" fill="currentColor"/>',
    books: '<path d="M12 6.6S9.8 4.4 4.2 4.4v13.2c5.6 0 7.8 2.2 7.8 2.2s2.2-2.2 7.8-2.2V4.4C14.2 4.4 12 6.6 12 6.6Z"/><path d="M12 6.6v13.2"/>',
    medal: '<path d="M8.6 9.4 5.4 3.4M15.4 9.4l3.2-6"/><circle cx="12" cy="15" r="6.2"/><path d="m12 11.5 1.2 2.4 2.6.4-1.9 1.8.5 2.6-2.4-1.3-2.4 1.3.5-2.6-1.9-1.8 2.6-.4Z" fill="currentColor" stroke="none"/>',
    sprout: '<path d="M12 20.8v-7.2"/><path d="M12 14.6C8.2 14.6 5.6 12 5.6 8.2c3.8 0 6.4 2.6 6.4 6.4Z"/><path d="M12 13c0-3.6 2.6-6.2 6.4-6.2 0 3.6-2.6 6.2-6.4 6.2Z"/>',
    pin: '<path d="M9.4 3.4h5.2l-.8 5.4 3.4 3.4H6.8l3.4-3.4Z"/><path d="M12 12.2v8.4"/>',
    grid: '<rect x="3.4" y="3.4" width="7.4" height="7.4" rx="2.2"/><rect x="13.2" y="3.4" width="7.4" height="7.4" rx="2.2"/><rect x="3.4" y="13.2" width="7.4" height="7.4" rx="2.2"/><rect x="13.2" y="13.2" width="7.4" height="7.4" rx="2.2"/>',
    people: '<circle cx="9" cy="8" r="3.6"/><path d="M2.6 20.4c0-3.6 2.9-6.2 6.4-6.2s6.4 2.6 6.4 6.2"/><path d="M16.2 4.9a3.6 3.6 0 0 1 0 6.2"/><path d="M17.6 14.7c2.5.7 3.8 3 3.8 5.7"/>',
    contrast: '<circle cx="12" cy="12" r="8.4"/><path d="M12 3.6a8.4 8.4 0 0 1 0 16.8Z" fill="currentColor"/>',
    arrowRight: '<path d="M4.4 12h13.8"/><path d="m12.8 6.4 5.6 5.6-5.6 5.6"/>',
    arrowLeft: '<path d="M19.6 12H5.8"/><path d="M11.2 6.4 5.6 12l5.6 5.6"/>',
    // 徽章用的一批
    drops: '<path d="M8.4 3.6c2.6 3 3.8 5 3.8 6.6a3.8 3.8 0 0 1-7.6 0c0-1.6 1.2-3.6 3.8-6.6Z"/><path d="M16.8 10.4c1.8 2.1 2.6 3.5 2.6 4.6a2.6 2.6 0 0 1-5.2 0c0-1.1.8-2.5 2.6-4.6Z"/>',
    sliders: '<path d="M3.6 8.6h16.8M3.6 15.4h16.8"/><circle cx="9" cy="8.6" r="2.7"/><circle cx="15.4" cy="15.4" r="2.7"/>',
    route: '<path d="M5.6 19.4c4.2-.6 3-6.6 6.8-7.4s3-6 7-6.6"/><circle cx="5.6" cy="19.4" r="2.1" fill="currentColor" stroke="none"/><circle cx="18.6" cy="5.4" r="2.1" fill="currentColor" stroke="none"/>',
    calendar: '<rect x="3.6" y="5.4" width="16.8" height="15" rx="3.2"/><path d="M3.6 10.4h16.8M8.4 3v4.6M15.6 3v4.6"/>',
    layers: '<path d="m12 3.4 8.4 4.6L12 12.6 3.6 8Z"/><path d="m4.8 12.4 7.2 3.9 7.2-3.9"/><path d="m4.8 16.6 7.2 3.9 7.2-3.9"/>',
    wave: '<path d="M2.6 13.6c2.4-6.2 4.3-6.2 6.7 0s4.3 6.2 6.7 0 4.3-6.2 5.4-2.6"/>',
    dense: '<circle cx="6.4" cy="6.4" r="1.9" fill="currentColor" stroke="none"/><circle cx="12" cy="6.4" r="1.9" fill="currentColor" stroke="none"/><circle cx="17.6" cy="6.4" r="1.9" fill="currentColor" stroke="none"/><circle cx="6.4" cy="12" r="1.9" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.9" fill="currentColor" stroke="none"/><circle cx="17.6" cy="12" r="1.9" fill="currentColor" stroke="none"/><circle cx="6.4" cy="17.6" r="1.9" fill="currentColor" stroke="none"/><circle cx="12" cy="17.6" r="1.9" fill="currentColor" stroke="none"/><circle cx="17.6" cy="17.6" r="1.9" fill="currentColor" stroke="none"/>',
    swap: '<path d="M4.4 8.6h13.4"/><path d="m14.2 5 3.6 3.6-3.6 3.6"/><path d="M19.6 15.4H6.2"/><path d="M9.8 11.8 6.2 15.4 9.8 19"/>',
    pause: '<rect x="6.4" y="4.4" width="4" height="15.2" rx="1.8"/><rect x="13.6" y="4.4" width="4" height="15.2" rx="1.8"/>',
  };
  /** 一枚图标，size px，颜色跟随 currentColor（或显式给 color）。 */
  function icon(name, size = 20, color = "") {
    const d = ICONS[name];
    if (!d) return "";
    return `<svg class="ico" viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" `
      + `stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"`
      + (color ? ` style="color:${color}"` : "") + ` aria-hidden="true">${d}</svg>`;
  }
  /** index.html 里写 <i data-icon="pin"></i>，这里把它换成真的图标。 */
  function hydrateIcons(root = document) {
    root.querySelectorAll("[data-icon]").forEach(el => {
      el.outerHTML = icon(el.dataset.icon, +el.dataset.size || 20);
    });
  }
  hydrateIcons();   // 脚本在 </body> 前，静态标记此刻已经在了

  // 每个任务的图标 + 主题色（首页卡片用）
  const QUEST_STYLE = {
    emotion_alone:        { icon: "contrast", c: "#f79433" },
    imagine_animal:       { icon: "sparkle",  c: "#b98cf0" },
    transform_chair:      { icon: "loop",     c: "#4db8ef" },
    color_rain_city:      { icon: "palette",  c: "#6cc24a" },
    story_character_home: { icon: "books",    c: "#f2706e" },
  };

  // ===== 创作伙伴「彩点」：一坨会变色的颜料精灵 =====
  function spriteInner(color, expr) {
    const dark = "#3a2f2a";
    const mouth = expr === "happy" ? `<path d="M84,120 Q100,138 116,120" fill="none" stroke="${dark}" stroke-width="4" stroke-linecap="round"/>`
      : expr === "wow" ? `<ellipse cx="100" cy="126" rx="8" ry="11" fill="${dark}"/>`
      : `<path d="M88,122 Q100,132 112,122" fill="none" stroke="${dark}" stroke-width="4" stroke-linecap="round"/>`;
    const p = expr === "wow" ? 6 : 7;
    const blob = "M100,26 C138,24 172,52 176,94 C179,128 160,150 150,166 C120,190 80,190 52,168 C40,150 21,128 24,94 C28,52 62,28 100,26 Z";
    // Parts are grouped and classed so CSS can move them: the body breathes,
    // the shadow answers it, and the eyes blink on their own offset. All of it
    // is switched off under prefers-reduced-motion.
    return `<ellipse class="cd-shadow" cx="100" cy="184" rx="44" ry="8" fill="rgba(0,0,0,.07)"/>`
      + `<g class="cd-body">`
      + `<path d="${blob}" fill="${color}" stroke="rgba(0,0,0,.12)" stroke-width="2"/>`
      + `<path d="M150,150 q14,10 8,26 q-12,4 -14,-10" fill="${color}"/>`
      + `<g class="cd-eyes">`
      + `<ellipse cx="84" cy="92" rx="15" ry="17" fill="#fff"/><ellipse cx="116" cy="92" rx="15" ry="17" fill="#fff"/>`
      + `<circle cx="86" cy="95" r="${p}" fill="${dark}"/><circle cx="114" cy="95" r="${p}" fill="${dark}"/>`
      + `<circle cx="84" cy="86" r="3" fill="#fff"/><circle cx="115" cy="86" r="3" fill="#fff"/>`
      + `</g>${mouth}</g>`;
  }
  const buddyColor = () => state.color || "#f79433";

  // ===== 伙伴的名字 =====
  // 「彩点」只是个占位的默认名。它是孩子的伙伴，名字该由孩子起——
  // 起了名字的东西才会被惦记着回来看。名字存在本机，并冻进 session，
  // 这样研究上也看得到每个孩子给它起了什么。
  const DEFAULT_BUDDY = "彩点";
  const buddyName = () => state.buddyName || DEFAULT_BUDDY;
  function loadBuddyName() {
    try { state.buddyName = localStorage.getItem("artquest.buddy_name") || ""; } catch (e) { /* 无所谓 */ }
  }
  function setBuddyName(name) {
    state.buddyName = (name || "").trim().slice(0, 8);
    try {
      if (state.buddyName) localStorage.setItem("artquest.buddy_name", state.buddyName);
      else localStorage.removeItem("artquest.buddy_name");
    } catch (e) { /* 无所谓 */ }
    paintBuddyName();
  }
  /** 界面上所有出现名字的地方，一处改全处改。 */
  function paintBuddyName() {
    const n = buddyName();
    document.querySelectorAll(".buddy-word").forEach(el => { el.textContent = n; });
    const w = $("#world-name"); if (w) w.textContent = n;
    TITLES.world = `${n}的世界`;
    TITLES.buddy = n;
    const av = $("#btn-world"); if (av) av.title = `看看${n}`;
  }
  function askBuddyName() {
    const m = $("#name-modal"), input = $("#buddy-name-input");
    input.value = state.buddyName || "";
    m.classList.remove("hidden");
    setTimeout(() => input.focus(), 50);
  }

  // ===== 做一幅画的六步：顶栏上一条细进度条 =====
  // 闯关地图搬到首页去了——那儿才该热闹。一次创作的过程条只需要回答一件事：还剩几步。
  const ALL_STAGES = [
    { key: "quest",  name: "出发" },
    { key: "intent", name: "心愿" },
    { key: "draw",   name: "创作" },
    { key: "result", name: "支招" },
    { key: "evolve", name: "进化" },
    { key: "final",  name: "宝藏" },
  ];
  /** The stations this condition actually visits: with no feedback there is no
   *  支招 and no 进化, and a bar that promises steps the child can never reach
   *  is telling them they failed at something. */
  function flowStages() {
    const quiet = state.condition && state.condition.feedback_source !== "ai";
    return ALL_STAGES.filter(s => !(quiet && (s.key === "result" || s.key === "evolve")));
  }
  function renderFlow(currentKey) {
    const bar = $("#flow"); if (!bar) return;
    const STAGES = flowStages();
    const idx = STAGES.findIndex(s => s.key === currentKey);
    bar.classList.toggle("hidden", idx < 0);
    if (idx < 0) return;
    $("#flow-fill").style.width = `${((idx + 1) / STAGES.length) * 100}%`;
    $("#flow-step").textContent = `${STAGES[idx].name} · ${idx + 1}/${STAGES.length}`;
    const sp = $("#flow-sprite");
    if (sp) sp.innerHTML = spriteInner(buddyColor(), currentKey === "final" ? "happy" : "normal");
  }

  // ---------- views ----------
  // 四个 tab 是四块独立的界面；做任务时导航整个收起来，只剩画画。
  const VIEWS = ["world", "quest", "dex", "buddy", "sessions", "intent", "draw", "result", "survey", "final"];
  const TAB_VIEW = { map: "quest", dex: "dex", buddy: "buddy", me: "sessions" };
  const VIEW_TAB = { world: "map", quest: "map", dex: "dex", buddy: "buddy", sessions: "me" };
  const TITLES = { world: "彩点的世界", quest: "创作冒险", dex: "创作图鉴", buddy: "彩点", sessions: "我的" };
  function show(name) {
    VIEWS.forEach(v => $(`#view-${v}`).classList.toggle("hidden", v !== name));
    const tab = VIEW_TAB[name];
    document.body.classList.toggle("inflow", !tab);
    document.querySelectorAll(".tab").forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
    $("#appbar-title").classList.toggle("hidden", !tab);
    if (tab) $("#appbar-title").textContent = TITLES[name];
    // 顶栏的彩点头像：在地图上才出现，点它回到世界
    const av = $("#btn-world");
    if (av) {
      av.classList.toggle("hidden", name !== "quest");
      if (name === "quest") $("#avatar-sprite").innerHTML = spriteInner(buddyColor(), "normal");
    }
    // 返回键归顶栏管：哪个流程界面，用哪个已有的返回逻辑
    $("#btn-back-quest").classList.toggle("hidden", name !== "intent");
    $("#btn-back-draw").classList.toggle("hidden", name !== "draw");
    const stage = tab ? "" : name === "draw" ? (state.phase === "after" ? "evolve" : "draw")
      : name === "survey" ? "final" : name;
    renderFlow(stage);
    window.scrollTo(0, 0);
  }
  async function openTab(tab) {
    let view = TAB_VIEW[tab] || "quest";
    // 第一次进来先见彩点：它带着自己的属性，然后才是世界和任务
    if (view === "quest" && !state.entered && state.condition.ui !== "quiet") {
      await renderWorld(); view = "world";
    }
    show(view);
    // 每块界面自己去取自己的数据，进哪块取哪块
    if (view === "dex") { await loadCollection(); await renderWall(); }
    else if (view === "buddy") { await renderGrowth(); await renderBadgeWall(); }
    else if (view === "sessions") await loadSessions();
  }
  document.querySelectorAll(".tab").forEach(b => { b.onclick = () => openTab(b.dataset.tab); });
  const overlay = (text) => { $("#overlay").classList.toggle("hidden", !text); if (text) $("#overlay-text").textContent = text; };

  // ---------- 被选为优秀作品：先问本人 ----------
  // `share_consent` 回答的是「我的画可不可以被人看见」，画之前就冻结了。
  // 被单独挑出来当优秀作品是另一个问题、针对另一个东西——**这一张**，挂在大家面前。
  // 所以老师的挑选只是一个提议，答应了才展出，而且随时能收回来。
  let featuredQueue = [];
  async function checkFeatured() {
    if (state.condition.ui === "quiet") return;
    try {
      const r = await api(`/api/participants/${encodeURIComponent(savedPid() || " ")}/featured`
        + `?anon_id=${encodeURIComponent(state.anonId)}`);
      featuredQueue = r.pending || [];
    } catch (e) { return; }
    showNextFeatured();
  }
  function showNextFeatured() {
    const m = $("#featured-modal");
    const item = featuredQueue[0];
    if (!item) { m.classList.add("hidden"); return; }
    $("#featured-note").textContent = item.note
      ? `老师说：「${item.note}」` : `你画的《${item.title}》被老师挑出来了。`;
    $("#featured-img").src = item.image;
    m.classList.remove("hidden");
  }
  async function answerFeatured(accept) {
    const item = featuredQueue.shift();
    $("#featured-modal").classList.add("hidden");
    if (!item) return;
    try {
      await api(`/api/sessions/${item.session_id}/featured`,
        { method: "POST", body: JSON.stringify({ accept: !!accept }) });
    } catch (e) { /* 下次再问 */ }
    showNextFeatured();
  }
  $("#btn-featured-yes").onclick = () => answerFeatured(true);
  $("#btn-featured-no").onclick = () => answerFeatured(false);

  // ---------- 世界入口 ----------
  // 游戏的开场：先看见这只精灵和它身上的九个属性，再进世界，再挑任务。
  // 属性不是分数——它长在「练过什么」上：做一个训练某维度的任务，那一格就涨。
  // 没画过画的时候它是灰的，这是设定的一部分：孩子用的颜色把它点亮。
  async function renderWorld() {
    const sp = $("#world-sprite"); if (!sp) return;
    let g = null;
    try {
      g = await api(`/api/participants/${encodeURIComponent(savedPid() || " ")}/growth`
        + `?anon_id=${encodeURIComponent(state.anonId)}`);
    } catch (e) { /* 离线就当还没点亮 */ }
    const lit = !!(g && g.n_tasks);
    const byKey = Object.fromEntries((state.cfg.dimensions || []).map(d => [d.key, d]));
    const best = lit ? Object.entries(g.dims).sort((a, b) => b[1].practice - a[1].practice)[0] : null;
    const col = lit && best && best[1].practice ? FAMILIES[DIM_FAMILY[best[0]]].color : "#cfcbc4";
    state.worldColor = col;
    sp.innerHTML = spriteInner(col, lit && g.total_level >= 9 ? "happy" : "normal");
    sp.classList.toggle("grey", !lit);

    const lv = lit ? 1 + Math.floor(g.total_level / 3) : 1;
    $("#world-level").textContent = `Lv.${lv}`;
    $("#world-say").textContent = !lit
      ? (state.buddyName
          ? "我现在还是灰的。你画画用什么颜色，我就变成什么颜色。"
          : "我还没有名字呢。点一下旁边那支笔，给我起一个吧。")
      : best && best[1].practice
        ? `我在「${(byKey[best[0]] || {}).zh || best[0]}」上长得最快！`
        : "再画几幅，我就开始长啦～";
    const pct = lit ? Math.round(100 * g.total_level / Math.max(1, g.max_total)) : 0;
    $("#world-bar-fill").style.width = pct + "%";
    $("#world-total").textContent = lit
      ? `${g.n_tasks} 幅作品 · 成长 ${g.total_level}/${g.max_total}`
      : "还没有作品";

    $("#world-attrs").innerHTML = CHART_ORDER.map(key => {
      const d = byKey[key]; if (!d) return "";
      const v = (lit && g.dims[key]) || { level: 0, max_level: 5 };
      const fam = FAMILIES[DIM_FAMILY[key]];
      const pips = Array.from({ length: v.max_level || 5 },
        (_, i) => `<i class="${i < (v.level || 0) ? "on" : ""}"></i>`).join("");
      return `<div class="attr${v.level ? "" : " dim"}" style="--ac:${fam.color}">
        <div class="attr-name">${d.zh}</div><div class="attr-pips">${pips}</div></div>`;
    }).join("");
  }
  function enterWorld() {
    state.entered = true;
    try { sessionStorage.setItem("artquest.entered", "1"); } catch (e) { /* 无所谓 */ }
    show("quest");
  }
  $("#btn-enter-world").onclick = enterWorld;
  $("#btn-rename").onclick = askBuddyName;
  $("#btn-name-cancel").onclick = () => $("#name-modal").classList.add("hidden");
  $("#btn-name-save").onclick = () => {
    setBuddyName($("#buddy-name-input").value);
    $("#name-modal").classList.add("hidden");
    renderWorld();
  };
  $("#buddy-name-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("#btn-name-save").click();
  });
  $("#btn-world").onclick = async () => { await renderWorld(); show("world"); };

  // ---------- mission glyphs ----------
  // Line glyphs instead of emoji: emoji render differently on every platform,
  // carry someone else's visual language, and several of the families had no
  // emoji that meant the right thing. These are drawn in the family's own
  // colour via currentColor, so the map reads as one set.
  const GLYPHS = {
    // palette: choose anything
    M0: ICONS.palette,
    // a framed picture with a crack through it
    M1: '<rect x="3.6" y="4.6" width="16.8" height="14.8" rx="1.6"/><path d="M9.2 19.4 11 13.2 8.6 11.4 12.6 4.6"/>',
    // a field pad: horizon, peaks, sun
    M2: '<rect x="4" y="4.6" width="16" height="14.8" rx="1.6"/><path d="M6.4 15.6 10 11.2l2.4 2.9 2-2.4 3.2 4.4"/><circle cx="15.4" cy="8.2" r="1.5"/>',
    // pieces that do not yet join up
    M3: '<path d="M4.4 11.2V5.1a.8.8 0 0 1 .8-.8h6.1"/><path d="M19.6 12.8v6.1a.8.8 0 0 1-.8.8h-6.1"/><path d="M15.4 5.6 19.3 9.5"/><circle cx="8.6" cy="15.4" r="1.25" fill="currentColor" stroke="none"/>',
    // a flask: something being changed into something else
    M4: '<path d="M10 3.6v5.6L5.6 17.8A2 2 0 0 0 7.4 20.8h9.2a2 2 0 0 0 1.8-3L14 9.2V3.6"/><path d="M8.6 3.6h6.8"/><circle cx="12" cy="16.4" r="1.15" fill="currentColor" stroke="none"/>',
    // two things becoming one
    M5: '<circle cx="9.4" cy="12" r="5.6"/><circle cx="14.6" cy="12" r="5.6"/>',
    // one place, two moods
    M6: '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16Z" fill="currentColor" stroke="none"/>',
    // a line going somewhere
    M7: '<path d="M3.4 15.8c3.2-6.4 5.2 4 8.2-1.2s4.2 2.2 9-5.2"/>',
    // a world with different rules
    M8: '<path d="M12 20.2a8.2 8.2 0 1 0-8.2-8.2 6 6 0 0 0 6 6 4 4 0 0 0 4-4 2.4 2.4 0 0 0-2.4-2.4"/>',
    // a door you have not opened
    M9: '<path d="M5.2 20.4V4.6l8.6-2v20.4l-8.6-2.6Z"/><path d="M13.8 5.2h5v13.6h-5"/><circle cx="11.4" cy="12.2" r=".9" fill="currentColor" stroke="none"/>',
  };
  /** A family glyph at `size` px, in that family's colour. */
  function glyph(familyId, color, size) {
    const g = GLYPHS[familyId];
    if (!g) return "";
    return `<svg class="glyph" viewBox="0 0 24 24" width="${size}" height="${size}" `
      + `fill="none" stroke="${color || "currentColor"}" stroke-width="2.2" `
      + `stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${g}</svg>`;
  }

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
    STROKE_CANCELLED: "STROKE_CANCELLED",
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
  /** 把两个颜色按比例混一下，自己算。
   *  CSS 的 color-mix() 要 Chrome 111+；低版本会把**整条**声明丢掉，
   *  于是立体下沿、柔光圈这些直接消失且不报错。算好再塞进去就没这问题。 */
  function mixHex(hex, pct, other) {
    const rgb = (h) => {
      h = String(h).replace("#", "");
      if (h.length === 3) h = h.split("").map(c => c + c).join("");
      return [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16));
    };
    const a = rgb(hex), b = rgb(other), p = pct / 100;
    return "#" + a.map((v, i) => Math.round(v * p + b[i] * (1 - p))
      .toString(16).padStart(2, "0")).join("");
  }
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
    // 一笔 = 几何 + 时间 + 工具状态，别的都不存。
    // t_end 是 t0_ms + 最后一个点的 dt，能算出来就不写进去；
    // zoom 和两个 *_supported 留着是因为它们算不出来：前者是画这一笔时孩子看到的画面，
    // 后者说明 null 是「没有这个传感器」而不是「传感器读到了空」。
    ArtLog.stroke({ stroke_id: id, phase: state.phase, op: s.erase ? "erase" : "draw",
      tool: s.tool, color: s.color, size: s.size, opacity: s.opacity,
      pointer: s.pointer_type, pressure_supported: s.pressure_supported,
      tilt_supported: s.tilt_supported, zoom: R(s.zoom, 3),
      t0_ms: Math.round(s.t0), points: s.points });
    visible.push(id);
    // the same stroke also lands in the unified event timeline, cross-referenced by id
    logEvent(s.erase ? EV.ERASE : EV.STROKE_END, { stroke_id: id, tool: s.tool, color: s.color,
      size: s.size, n: s.points.length, dur_ms: last_pt[2] });
  }
  // ===== iPad：一根手指画，两根手指看 =====
  // 捏合缩放、双指拖动平移、双指轻点撤销、三指轻点重做（Procreate 的那套手势）。
  // 它们走的是和滚轮/按钮同一个 zoomAt / PAN 通道，所以日志里是同一种记录，
  // 只有 source 不一样——分析时「他什么时候放大去抠细节」不会因为换了设备就断掉。
  const touches = new Map();          // pointerId -> {x, y}
  let gesture = null;
  let penSeen = false;                // 见过手写笔之后，手指就只当手势用（防手掌误触）
  const _mid = (a, b) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
  const _dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

  /** 第二根手指落下时，第一根手指刚蹭出来的那道印子不算数。
   *  不是偷偷删掉：画面回退，日志里记一条 STROKE_CANCELLED，
   *  所以「这一笔没被留下」本身也是可读的过程信息。 */
  function cancelStroke(reason) {
    if (!drawing || !curStroke) return;
    drawing = false; ctx.globalAlpha = 1;
    const s = curStroke; curStroke = null;
    if (undoStack.length) { ctx.putImageData(undoStack.pop(), 0, 0); undoDoc.pop(); }
    logEvent(EV.STROKE_CANCELLED, { stroke_id: s.id, reason, n: s.points.length });
  }

  function startGesture() {
    const pts = [...touches.values()];
    if (pts.length < 2) return;
    const m = _mid(pts[0], pts[1]);
    gesture = { n: touches.size, t0: elapsed(), moved: 0,
                d0: _dist(pts[0], pts[1]), z0: view.z, mx0: m.x, my0: m.y,
                tx0: view.tx, ty0: view.ty,
                panFrom: [Math.round(view.tx), Math.round(view.ty)], points: [] };
  }
  function moveGesture() {
    const pts = [...touches.values()];
    if (!gesture || pts.length < 2) return;
    gesture.n = Math.max(gesture.n, touches.size);
    const m = _mid(pts[0], pts[1]), d = _dist(pts[0], pts[1]);
    gesture.moved = Math.max(gesture.moved, Math.hypot(m.x - gesture.mx0, m.y - gesture.my0),
                             Math.abs(d - gesture.d0));
    const prev = view.z;
    // 一步算完：让「手指落下时那个中点下面的画布位置」始终待在当前中点下面
    const z = clamp(gesture.d0 > 0 ? gesture.z0 * (d / gesture.d0) : view.z, MIN_ZOOM, MAX_ZOOM);
    const lx = (gesture.mx0 - gesture.tx0) / gesture.z0, ly = (gesture.my0 - gesture.ty0) / gesture.z0;
    const r = viewport.getBoundingClientRect();
    view.z = z;
    view.tx = (m.x - r.left) - lx * z;
    view.ty = (m.y - r.top) - ly * z;
    applyView();
    if (Math.abs(z - prev) > 1e-4) noteZoom(prev, "pinch");
    if (gesture.points.length < MAX_GESTURE_STEPS)
      gesture.points.push([Math.round(elapsed() - gesture.t0), Math.round(view.tx), Math.round(view.ty)]);
    markActive();
  }
  function endGesture() {
    const g = gesture; gesture = null;
    if (!g) return;
    // 轻点：两根手指点一下撤销，三根手指点一下重做
    if (g.moved < 12 && elapsed() - g.t0 < 300) {
      if (g.n >= 3) redo(); else undo();
      return;
    }
    const to = [Math.round(view.tx), Math.round(view.ty)];
    if (g.points.length && (to[0] !== g.panFrom[0] || to[1] !== g.panFrom[1]))
      logEvent(EV.PAN, { from: g.panFrom, to, zoom: R(view.z, 3),
        dur_ms: Math.round(elapsed() - g.t0), points: g.points, source: "touch" });
    flushZoom();
  }

  canvas.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "pen") penSeen = true;
    if (e.pointerType === "touch") {
      touches.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (touches.size >= 2) {
        e.preventDefault();
        cancelStroke("multitouch");
        if (zoomAllowed()) startGesture();
        return;
      }
      // 手里拿着笔的时候，落在屏幕上的手指是手掌，不是画笔
      if (penSeen) { e.preventDefault(); return; }
    }
    if (wantsPan(e)) { e.preventDefault(); panStart(e); return; }
    if (e.button !== 0 && e.pointerType === "mouse") return;
    if (state.timeUp) return;
    flushZoom();   // a zoom gesture closes before the stroke it was made for
    canvas.setPointerCapture(e.pointerId); pushUndo(); drawing = true; last = pos(e); beginStroke(e);
    strokeStyle(last.p); ctx.beginPath(); ctx.moveTo(last.x, last.y); ctx.lineTo(last.x + 0.01, last.y); ctx.stroke();
    markActive();
  });
  canvas.addEventListener("pointermove", (e) => {
    if (e.pointerType === "touch" && touches.has(e.pointerId)) {
      touches.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (gesture) { e.preventDefault(); return moveGesture(); }
    }
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
  const endStroke = (e) => {
    if (e && e.pointerType === "touch") {
      touches.delete(e.pointerId);
      if (gesture && touches.size < 2) { endGesture(); return; }
      if (gesture) return;
    }
    if (panning) return panEnd();
    if (drawing) { drawing = false; ctx.globalAlpha = 1; finishStroke(); }
  };
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
    if (!$("#view-draw").classList.contains("hidden")) renderFlow(state.phase === "after" ? "evolve" : "draw");
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
    // 0 = 不拍：任何时刻的画面都能从 stroke/event 日志重建，定时截图只是它的副本
    if (state.cfg.snapshot_interval_sec > 0)
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
    state.allSessions = rows;          // 地图的星、跨作品徽章、成长视图都读它
    const done = rows.filter(r => r.status === "done");
    const wrap = $("#collection-wrap"), grid = $("#collection"), empty = $("#dex-empty");
    if (empty) empty.classList.toggle("hidden", !!done.length);
    if (!done.length) { wrap.classList.add("hidden"); return; }
    wrap.classList.remove("hidden");
    const titleOf = (qid) => (state.quests.find(q => q.id === qid) || {}).title || qid;
    const styleOf = (qid) => QUEST_STYLE[qid] || { icon: "palette", c: "#f79433" };
    grid.innerHTML = done.slice(0, 12).map(r => {
      const st = styleOf(r.quest_id);
      const feat = (r.featured || {}).state;
      const flag = feat === "accepted"
        ? `<button class="dex-featured on" data-sid="${r.session_id}" data-accept="0"
             title="收回来，不再给大家看">${icon("pin", 12)}在大家的图鉴里</button>`
        : feat === "declined"
          ? `<button class="dex-featured" data-sid="${r.session_id}" data-accept="1"
               title="老师选过它，你当时说先不要">${icon("pin", 12)}老师选过它</button>`
          : "";
      return `<div class="dex-card" style="--qc:${st.c}">
        <a class="dex-open" href="/api/sessions/${r.session_id}" target="_blank">
          <div class="dex-thumb"><img src="/files/${r.session_id}/after.png" alt="" loading="lazy"></div>
          <div class="dex-cap"><b>${icon(st.icon, 14)}${titleOf(r.quest_id)}</b><span>${(r.created_at || "").slice(0, 10)}</span></div>
        </a>${flag}</div>`;
    }).join("");
    grid.querySelectorAll(".dex-featured").forEach(b => {
      b.onclick = async () => {
        await api(`/api/sessions/${b.dataset.sid}/featured`,
          { method: "POST", body: JSON.stringify({ accept: b.dataset.accept === "1" }) });
        await loadCollection(); await renderWall();
      };
    });
    const types = new Set(done.map(r => r.quest_id)), total = state.quests.length;
    $("#dex-progress").innerHTML = `已解锁 ${types.size}/${total} 种任务`
      + (types.size >= total ? ` · <b style="color:var(--accent-d)">${icon("medal", 14)} 创作者勋章达成！</b>` : "");
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
    $("#growth-rings").innerHTML = rings ? icon("star", 16).repeat(rings) : "";
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
    card.innerHTML = `<h4>${icon("compass", 15)}你的创作轨迹</h4>`
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
    $("#btn-ref-toggle").innerHTML = icon("image", 17) + (willOpen ? "收起参考图" : "看看参考图");
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

  // 进了世界看到的是**一张地图上的十个地方**，不是一条排队的线。
  // 任务家族之间本来就没有先后 —— 孩子想画哪个就画哪个，一条线会凭空
  // 承诺一个不存在的顺序。有顺序的那件事（做一幅画的六步）在顶栏进度条上。
  // 十个家族是一张排过的图，不是自动摆出来的格子——手放的位置才有「地方」的感觉
  const MAP_LAYOUTS = {
    10: [[13, 19], [37, 13], [61, 20], [86, 15],
         [22, 47], [50, 52], [78, 45],
         [16, 78], [46, 80], [76, 72]],
  };
  /** 同一个数量永远摆出同一张图：换设备、换屏宽，地方还在原来的位置。 */
  function mapSpots(n) {
    if (MAP_LAYOUTS[n]) return MAP_LAYOUTS[n];
    const rows = [];
    for (let i = 0, r = 0; i < n; r++) {
      const take = Math.min(n - i, r % 2 === 0 ? 3 : 4);
      rows.push(take); i += take;
    }
    const out = [];
    rows.forEach((take, ri) => {
      const y = 17 + (rows.length > 1 ? (ri / (rows.length - 1)) * 63 : 34);
      for (let c = 0; c < take; c++) {
        const x = ((c + 0.5) / take) * 100;
        // 一点错位，免得读成一张表格
        out.push([clamp(x + (((ri * 7 + c * 13) % 5) - 2) * 1.6, 12, 88),
                  clamp(y + (((ri * 11 + c * 5) % 5) - 2) * 2.2, 14, 82)]);
      }
    });
    return out;
  }
  function renderQuests() {
    const grid = $("#quest-grid"); if (!grid) return;
    grid.querySelectorAll(".quest-card").forEach(el => el.remove());
    const seq = state.study && state.study.sequence ? state.study.sequence : null;
    const byId = Object.fromEntries(state.quests.map(q => [q.id, q]));

    // Study Mode: the protocol names exact forms, in order. Free play: the child
    // picks a *mission family* — 75 forms is a task library, not a treasure map,
    // and which parallel form they get is not a choice the child should make.
    const cards = seq
      ? seq.map(id => byId[id]).filter(Boolean).map((q, i) => ({
          key: q.id, icon: q.icon, color: q.color, kind: q.type, title: q.title,
          locked: i !== state.seqIdx, task: q }))
      // 家族卡：标题已经是家族名了，副标题换成「这个家族有几种玩法」
      : (state.families || []).filter(f => f.n_forms).map(f => ({
          key: f.id, icon: f.icon, color: f.color, kind: `${f.n_forms} 种玩法`,
          title: f.name, locked: false, family: f.id }));

    const doneFam = new Set((state.allSessions || []).filter(r => r.status === "done")
      .map(r => familyOf(r.task_id)).filter(Boolean));
    const spots = mapSpots(cards.length);
    let nextMarked = false, nDone = 0;
    cards.forEach((c, i) => {
      const fam = c.family || (c.task && c.task.family) || "";
      const done = !c.locked && doneFam.has(fam);
      const isNext = !c.locked && !done && !nextMarked;
      if (done) nDone++;
      if (isNext) nextMarked = true;
      const el = document.createElement("div");
      el.className = "quest-card" + (c.locked ? " locked" : "") + (done ? " done" : "") + (isNext ? " next" : "");
      el.style.setProperty("--qc", c.color || "#f79433");
      const qc = c.color || "#f79433";
      el.style.setProperty("--qc-edge", mixHex(qc, 72, "#000"));
      el.style.setProperty("--qc-soft", mixHex(qc, 18, "#fff"));
      const spot = spots[i] || [50, 50];
      el.style.setProperty("--mx", spot[0] + "%");
      el.style.setProperty("--my", spot[1] + "%");
      const mark = glyph(fam, "currentColor", 34) || `<span class="qc-icon">${c.icon || ""}</span>`;
      el.innerHTML =
        (isNext ? `<svg class="sprite node-here" viewBox="0 0 200 200">${spriteInner(buddyColor(), "normal")}</svg>` : "")
        + `<div class="node-btn">${c.locked ? icon("lock", 30) : mark}`
        + (done ? `<span class="node-star">${icon("star", 14)}</span>` : "")
        + `</div><h3>${c.title}</h3>`
        + `<div class="node-sub">${c.locked ? "稍后解锁" : c.kind}</div>`;
      if (!c.locked) el.onclick = () => {
        const q = c.task || randomForm(c.family);
        if (q) chooseQuest(q);
      };
      grid.appendChild(el);
    });
    const prog = $("#map-progress");
    if (prog) prog.textContent = cards.length ? `走过 ${nDone}/${cards.length} 关` : "";
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
    loadBuddyName(); paintBuddyName();
    $("#backend-badge").textContent = `评分: ${state.cfg.scorer} · 反馈: ${state.cfg.feedback}` + (state.cfg.claude_available ? "" : " (离线模式)");
    await setupStudy();
    applyCondition();
    $("#participant").value = savedPid();
    renderQuests();
    const chips = $("#emotion-chips"); chips.innerHTML = "";
    state.cfg.emotions.forEach(em => { const b = document.createElement("button"); b.textContent = em; b.onclick = () => { state.emotion = em; chips.querySelectorAll("button").forEach(x => x.classList.toggle("active", x === b)); }; chips.appendChild(b); });
    await loadCollection();          // 地图要知道哪几关走过了
    renderQuests();
    try { state.entered = sessionStorage.getItem("artquest.entered") === "1"; } catch (e) { /* 无所谓 */ }
    if (state.entered || state.condition.ui === "quiet") { show("quest"); }
    else { await renderWorld(); show("world"); }
    checkFeatured();
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
    renderQuests();
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
      participant: { anon_id: state.anonId, participant_id: savedPid(), label: "", buddy_name: state.buddyName },
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
    $("#final-meta").textContent = `Session ${session.session_id} · 过程截图 ${session.snapshots.length} 张 · 事件 ${session.events.length} 条 · 数据在 data/sessions/${session.session_id}/`;
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
  const sizesUsed = (s) => payloads(s, ["SIZE_CHANGE", "STROKE_START", "STROKE_END"], "size").map(Number);
  const firstStrokeMs = (s) => {
    const t = evOf(s, ["STROKE_START"]).map(e => Number(e.t_ms) || 0);
    return t.length ? Math.min(...t) : 0;
  };
  const maxStrokePoints = (s) => Math.max(0, ...payloads(s, ["STROKE_END", "ERASE"], "n").map(Number));
  const doneRows = () => (state.allSessions || []).filter(r => r.status === "done");
  const activeDays = () => new Set(doneRows().map(r => (r.created_at || "").slice(0, 10)).filter(Boolean)).size;
  const deepestFamily = () => {
    const c = {};
    doneRows().forEach(r => { const f = familyOf(r.task_id); if (f) c[f] = (c[f] || 0) + 1; });
    return Math.max(0, ...Object.values(c));
  };
  const familyOf = (taskId) => (state.quests.find(q => q.id === taskId) || {}).family || "";

  const ALL_BADGES = [
    // -- 颜色与工具 --
    { g: "色彩与工具", icon: "palette", name: "缤纷调色", desc: "用了 5 种以上颜色",
      earned: s => colorsUsed(s).size >= 5 },
    { g: "色彩与工具", icon: "contrast", name: "冷暖并用", desc: "暖色和冷色都用上了",
      earned: s => hasWarmAndCool(s) },
    { g: "色彩与工具", icon: "brush", name: "工具全能", desc: "用了 3 种以上工具",
      earned: s => toolsUsed(s).size >= 3 },
    { g: "色彩与工具", icon: "pencil", name: "一支到底", desc: "只用一种工具画完 30 笔以上",
      earned: s => toolsUsed(s).size === 1 && nStrokes(s) >= 30 },
    // -- 过程与节奏 --
    { g: "过程与节奏", icon: "clock", name: "专注之心", desc: "专注创作超过 5 分钟",
      earned: s => drawMs(s) >= 300000 },
    { g: "过程与节奏", icon: "think", name: "深思熟虑", desc: "停下来想了 30 秒以上，然后继续",
      earned: s => longestPause(s) >= 30000 && nStrokes(s) >= 5 },
    { g: "过程与节奏", icon: "bolt", name: "一气呵成", desc: "20 笔以上，中间几乎没停",
      earned: s => nStrokes(s) >= 20 && longestPause(s) < 10000 },
    { g: "过程与节奏", icon: "loop", name: "反复打磨", desc: "撤销 5 次以上，还在继续画",
      earned: s => evOf(s, ["UNDO"]).length >= 5 && nStrokes(s) >= 10 },
    { g: "过程与节奏", icon: "trash", name: "推倒重来", desc: "清空过画布，然后重新画完",
      earned: s => evOf(s, ["CLEAR"]).length >= 1 && nStrokes(s) >= 10 },
    // -- 观察与细节 --
    { g: "观察与细节", icon: "search", name: "细节猎人", desc: "放大到 3 倍以上作画",
      earned: s => zoomMax(s) >= 3 },
    { g: "观察与细节", icon: "map", name: "大局观", desc: "在整体和局部之间来回看了 5 次以上",
      earned: s => evOf(s, ["ZOOM", "PAN"]).length >= 5 },
    { g: "观察与细节", icon: "eye", name: "对照高手", desc: "参考图看了 3 次以上",
      earned: s => evOf(s, ["REFERENCE_OPEN"]).length >= 3, needs: "reference" },
    { g: "观察与细节", icon: "hourglass", name: "看得仔细", desc: "参考图累计看了 30 秒以上",
      earned: s => refMs(s) >= 30000, needs: "reference" },
    // -- 探索与坚持（跨作品）--
    { g: "探索与坚持", icon: "compass", name: "探险家", desc: "玩过 3 个不同的任务家族",
      earned: () => new Set(doneRows().map(r => familyOf(r.task_id)).filter(Boolean)).size >= 3 },
    { g: "探索与坚持", icon: "books", name: "小有收藏", desc: "完成 5 幅作品",
      earned: () => doneRows().length >= 5 },
    { g: "探索与坚持", icon: "medal", name: "走遍全图", desc: "每个任务家族都完成过一次",
      earned: () => {
        const fams = new Set((state.families || []).map(f => f.id));
        const done = new Set(doneRows().map(r => familyOf(r.task_id)).filter(Boolean));
        return fams.size > 0 && [...fams].every(f => done.has(f));
      } },
    { g: "探索与坚持", icon: "sparkle", name: "进化大师", desc: "走完进化关，改了自己的作品",
      earned: s => s.revised === true, evo: true },
    // -- 后加的一批：没点亮的不展示，所以多一些才有得发现 --
    { g: "色彩与工具", icon: "marker", name: "单色也精彩", desc: "只用一种颜色画完 20 笔以上",
      earned: s => colorsUsed(s).size === 1 && nStrokes(s) >= 20 },
    { g: "色彩与工具", icon: "drops", name: "彩虹收集者", desc: "一幅画里用了 8 种以上颜色",
      earned: s => colorsUsed(s).size >= 8 },
    { g: "色彩与工具", icon: "sliders", name: "粗细都试", desc: "最粗和最细的笔差了 20 以上",
      earned: s => { const z = sizesUsed(s); return z.length > 1 && Math.max(...z) - Math.min(...z) >= 20; } },
    { g: "过程与节奏", icon: "pause", name: "想好再落笔", desc: "看了 15 秒以上才画第一笔",
      earned: s => firstStrokeMs(s) >= 15000 && nStrokes(s) >= 3 },
    { g: "过程与节奏", icon: "hourglass", name: "慢慢来", desc: "在一幅画上待了 10 分钟以上",
      earned: s => drawMs(s) >= 600000 },
    { g: "过程与节奏", icon: "wave", name: "长长的一笔", desc: "一笔画了很长都没抬手",
      earned: s => maxStrokePoints(s) >= 300 },
    { g: "过程与节奏", icon: "dense", name: "画得很满", desc: "一幅画里画了 60 笔以上",
      earned: s => nStrokes(s) >= 60 },
    { g: "观察与细节", icon: "swap", name: "来回对照", desc: "在参考图和画布之间来回看了 6 次以上",
      earned: s => evOf(s, ["REFERENCE_FOCUS", "CANVAS_FOCUS"]).length >= 6, needs: "reference" },
    { g: "观察与细节", icon: "route", name: "走遍画布", desc: "移动画布 8 次以上，每个角落都去过",
      earned: s => evOf(s, ["PAN"]).length >= 8 },
    { g: "探索与坚持", icon: "calendar", name: "常来的人", desc: "在 3 个不同的日子画过画",
      earned: () => activeDays() >= 3 },
    { g: "探索与坚持", icon: "books", name: "十幅收藏", desc: "完成 10 幅作品",
      earned: () => doneRows().length >= 10 },
    { g: "探索与坚持", icon: "layers", name: "专攻一门", desc: "同一个任务家族完成 3 次以上",
      earned: () => deepestFamily() >= 3 },
  ];
  // 每组一个颜色，徽章不再是一片一样的黄
  const BADGE_COLORS = { "色彩与工具": "#f79433", "过程与节奏": "#4db8ef",
                         "观察与细节": "#6cc24a", "探索与坚持": "#b98cf0" };
  const BADGE_RULES_VERSION = "badges/1";

  /** Tell the server what this session lit, so rarity can be counted.
   *  Stored with the rule-set version: tightening a rule later must not take a
   *  badge off a child who already had it. */
  async function reportBadges(session) {
    const pool = badgePool(session);
    const earned = pool.filter(b => { try { return !!b.earned(session); } catch (e) { return false; } });
    try {
      await api(`/api/sessions/${session.session_id}/badges`, { method: "POST", body: JSON.stringify({
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
        <div class="p-pin">${icon("pin", 13)}老师选的</div></div>`;
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
      data = await api(`/api/gallery/task/${encodeURIComponent(session.quest_id)}?exclude=${session.session_id}&k=3`);
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
        ${c.featured_by ? `<div class="p-pin">${icon("pin", 13)}老师选的</div>` : ""}</div>`;
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
      return `<span class="tchip" style="--tc:${fam.color};--tc-bg:${mixHex(fam.color, 13, "#fff")}`
        + `;--tc-fg:${mixHex(fam.color, 72, "#000")}"><i></i>${(byKey[k] || {}).zh || k}</span>`;
    };
    el.innerHTML = `<h4>${icon("sprout", 16)}这一关练的是</h4><div class="tchips">${primary.map(chip).join("")}</div>`
      + `<div class="tnote">${buddyName()}在这几项上又长了一点。`
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

  /** One badge grid, used by both the end-of-task result and the all-time wall.
   *
   *  **Only lit badges are shown.** A wall of greyed-out ones tells the child
   *  exactly what is coming, which is the opposite of a surprise — and it reads
   *  as a list of things they have failed to do. What is left is told as a
   *  number instead, so there is still something to go and find.
   */
  function badgeGroupsHtml(pool, isOn, { newTag = false } = {}) {
    const lit = pool.filter(isOn);
    const groups = [];
    lit.forEach(b => {
      let g = groups.find(x => x.name === b.g);
      if (!g) groups.push(g = { name: b.g, items: [] });
      g.items.push(b);
    });
    const html = groups.map(g => {
      const c = BADGE_COLORS[g.name] || "#f79433";
      const style = `--bc:${c};--bc-l:${mixHex(c, 62, "#fff")};--bc-d:${mixHex(c, 66, "#000")}`;
      return `<div class="badge-group"><h4>${g.name}</h4><div class="badge-row">` + g.items.map(b => {
        // Rarity is about the badge, not about you: "8 % of people have lit this"
        // gives the collecting feeling without comparing anyone's drawing.
        const st = ((state.rarity || {}).badges || {})[b.name];
        const pct = st && st.rarity !== null ? Math.round(st.rarity * 100) : null;
        const rare = pct !== null && pct <= 15;
        const line = pct === null ? ""
          : `<div class="rarity">${pct <= 0 ? "还没有人点亮过" : `${pct}% 的人点亮过`}</div>`;
        return `<div class="badge on${newTag ? " new" : ""}${b.evo ? " evo" : ""}${rare ? " rare" : ""}"
          style="${style}" title="${b.desc}">
          <div class="b-ico">${icon(b.icon, 30)}</div><div class="b-name">${b.name}</div>
          <div class="b-desc">${b.desc}</div>${line}</div>`;
      }).join("") + "</div></div>";
    }).join("");
    const left = pool.length - lit.length;
    return html + (left > 0
      ? `<p class="badge-left">还有 ${left} 枚等你发现——它们长什么样，点亮了才知道。</p>`
      : lit.length ? `<p class="badge-left">全部 ${lit.length} 枚都点亮了。</p>` : "");
  }

  function renderBadges(session) {
    const el = $("#badges"); if (!el) return;
    // A badge the condition makes unreachable is not shown as "not earned":
    // greying it out tells the child they missed something never on offer.
    const pool = badgePool();
    const got = pool.filter(b => { try { return !!b.earned(session); } catch (e) { return false; } });
    const gotSet = new Set(got);
    el.innerHTML = got.length
      ? badgeGroupsHtml(pool, b => gotSet.has(b), { newTag: true })
      : `<p class="badge-left">这次没有点亮新徽章——换个画法试试，它们藏在过程里。</p>`;
    $("#badges-count").textContent = got.length ? `点亮了 ${got.length} 枚` : "";
    if (got.length) {
      // one beat of delight, then back to breathing
      document.querySelectorAll("#view-final .sprite").forEach(el => {
        el.classList.remove("cheer"); void el.offsetWidth; el.classList.add("cheer");
      });
    }
  }

  /** 徽章墙：把每次结算时上报给服务器的徽章并起来，看看还差哪几枚。
   *  读的是那份上报记录本身，不重算——规则以后收紧，也不会把已经拿到的从孩子手上取走。 */
  async function renderBadgeWall() {
    const el = $("#badge-wall"); if (!el) return;
    // 每次都重新取：徽章是刚刚那一局才上报的，缓存里的名单一定是旧的
    try { state.allSessions = await api("/api/sessions"); } catch (e) { /* 离线就先空着 */ }
    const lit = new Set();
    (state.allSessions || []).forEach(r => ((r.badges || {}).earned || []).forEach(n => lit.add(n)));
    try { state.rarity = await api("/api/achievements"); } catch (e) { /* 稀有度是可选的 */ }
    const pool = badgePool();
    const n = pool.filter(b => lit.has(b.name)).length;
    el.innerHTML = n ? badgeGroupsHtml(pool, b => lit.has(b.name))
      : `<p class="badge-left">还一枚都没有。画一幅试试——徽章只看你怎么画，不看画得好不好。</p>`;
    $("#badge-wall-count").textContent = n ? `已点亮 ${n} 枚` : "";
  }

  $("#btn-again").onclick = async () => {
    await flushLog();
    state.sessionId = null; state.startedAt = null; state.phase = "before"; state.pendingFinal = null;
    $("#intent-text").value = "";
    if (state.study && state.study.sequence) {   // advance to the next task in the assigned order
      state.seqIdx = Math.min(state.seqIdx + 1, state.study.sequence.length - 1);
      renderStudyBar();
    }
    await loadCollection();
    renderQuests();
    show("quest");
    checkFeatured();
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
        <g transform="translate(${cx - 13},${cy - 13})" style="color:var(--muted)">${icon("palette", 26)}</g>
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
    el.innerHTML = `<div class="ability-head">${icon("palette", 17)}能力值 · 你这次在这些地方使了劲<span class="muted small">（我们不打分，只看能力往哪长）</span></div>`
      + roseChart(scores, baseline) + `<div class="dim-notes">${notes}</div>`;
  }

  // ---------- 「我的」：作品记录 + 这台机器上的设置 ----------
  async function loadSessions() {
    const rows = await api("/api/sessions");
    state.allSessions = rows;
    const tb = $("#sessions-table tbody"); tb.innerHTML = "";
    rows.forEach(s => { const tr = document.createElement("tr"); tr.innerHTML = `<td>${s.created_at}</td><td>${s.quest_id}</td><td>${s.participant || ""}</td><td>${s.status}</td><td>${s.revised === null ? "—" : s.revised ? "是" : "否"}</td><td><a href="/files/${s.session_id}/before.png" target="_blank">before</a> · <a href="/files/${s.session_id}/after.png" target="_blank">after</a> · <a href="/api/sessions/${s.session_id}" target="_blank">json</a></td>`; tb.appendChild(tr); });
    $("#anon-badge").textContent = state.anonId;
  }
  $("#btn-sessions-back").onclick = () => openTab("map");
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
