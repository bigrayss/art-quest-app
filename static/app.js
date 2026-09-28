/* ArtQuest Stage 1 front-end: quest → intent → draw → feedback → revise → done. */
(() => {
  const $ = (s) => document.querySelector(s);

  // ---------- 这份代码跑在哪儿 ----------
  // 同一套界面有两个壳：浏览器（网页版，API 同源）和 iOS app（外壳打在 app 包里，
  // 从 artquest://app 载入，API 在别的源上）。iOS 壳在页面开始之前注入
  // `window.ArtQuestNative = { server, token, version, platform }`，这里据此拼地址。
  // 没有它就是网页版，所有地址相对于当前源——这一行改动之外，网页版一个字节没变。
  const NATIVE = window.ArtQuestNative || null;
  const ORIGIN = (NATIVE && NATIVE.server) ? String(NATIVE.server).replace(/\/+$/, "") : "";
  const API = `${ORIGIN}/api/v1`;          // 接口从 1.0 起就有版本号，见 main.py 末尾
  const FILES = `${ORIGIN}/files`;
  /** 服务器回的图片地址是相对根的（files 开头），网页版直接用，app 里要接上服务器。 */
  const fileUrl = (p) => (p && p[0] === "/" && ORIGIN) ? ORIGIN + p : p;
  /** 和原生壳说话（只在 app 里有效；网页版里是空操作）。 */
  const native = (type, payload) => {
    try { window.webkit.messageHandlers.artquest.postMessage(Object.assign({ type }, payload || {})); }
    catch (e) { /* 不在 app 里 */ }
  };

  const api = async (path, opts = {}) => {
    const headers = { "Content-Type": "application/json" };
    // 登录着就带上令牌。走请求头不走查询串——URL 会原样进服务器的 access log。
    const tok = savedToken(); if (tok) headers.Authorization = `Bearer ${tok}`;
    const r = await fetch(path, { headers, ...opts });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json();
  };

  const state = { cfg: null, quests: [], families: [], allSessions: [], rarity: null, quest: null, emotion: null, sessionId: null, phase: "before", feedback: null,
    startedAt: null, dirtySinceSnapshot: false, timers: [], before: null, color: "#f79433", buddyTick: 0,
    anonId: "", condition: {}, study: null, seqIdx: 0, lastActivity: 0, idle: false, timeUp: false, pendingFinal: null,
    entered: false, worldColor: "", buddyName: "", account: null, unclaimed: 0 };

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
  // 第三个身份：账号。前两个都跟着**设备**走（清一次缓存、换一台 iPad 就没了），
  // 账号跟着人走——孩子自己起的名字 + 四位暗号，在「我的」那一屏里注册。
  // 令牌只是登录态，作品的归属靠 account_id（见后端 accounts.py）。
  // app 里令牌的正本在钥匙串（Keychain）里：删掉重装、清掉网站数据都还在——
  // 「画跟着人走」这句话在手机上就靠它。localStorage 那份只是网页版的家。
  const savedToken = () => {
    if (NATIVE && typeof NATIVE.token === "string") return NATIVE.token;
    try { return localStorage.getItem("artquest.token") || ""; } catch (e) { return ""; }
  };
  const setToken = (t) => {
    t = t || "";
    if (NATIVE) { NATIVE.token = t; native("token", { value: t }); }
    try { t ? localStorage.setItem("artquest.token", t) : localStorage.removeItem("artquest.token"); } catch (e) { /* 无所谓 */ }
  };
  const accountId = () => (state.account || {}).account_id || "";
  // 服务器上可能不止一个孩子。凡是界面里说「我的」的地方，都只问自己那些。
  const whoQuery = () => `anon_id=${encodeURIComponent(state.anonId)}`
    + `&account_id=${encodeURIComponent(accountId())}`
    + `&participant_id=${encodeURIComponent(savedPid())}`;
  const mySessions = () => api(`${API}/sessions?${whoQuery()}`);
  const deviceInfo = () => ({
    ua: navigator.userAgent, platform: navigator.platform || "",
    screen: [screen.width, screen.height], viewport: [innerWidth, innerHeight], dpr: devicePixelRatio || 1,
    pointer_types: [matchMedia("(pointer:fine)").matches ? "fine" : "", matchMedia("(any-pointer:coarse)").matches ? "coarse" : ""].filter(Boolean),
    timezone: (Intl.DateTimeFormat().resolvedOptions() || {}).timeZone || "", language: navigator.language || "",
    // 哪个壳：浏览器里是空的；app 里记下平台和 app 版本——Pencil 的压感、采样率
    // 都跟壳有关，分析时它是协变量
    app: NATIVE ? { platform: NATIVE.platform || "ios", version: NATIVE.version || "" } : {},
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
    dropper: '<path d="m17.4 3.4 3.2 3.2"/><path d="m15 5.8 3.2 3.2"/><path d="M13.4 7.4 16.6 10.6 8.2 19a2.2 2.2 0 0 1-3.1 0l-.1-.1a2.2 2.2 0 0 1 0-3.1Z"/><path d="m4.2 19.8-1 1"/>',
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
    // 后来那批「奇遇」徽章用的：它们记的是画法的**形状**和**时机**，
    // 图标也跟着具体一点——月亮就是夜里画的，羽毛就是轻轻一笔。
    moon: '<path d="M20 14.6A8.6 8.6 0 0 1 9.4 4a8.6 8.6 0 1 0 10.6 10.6Z"/>',
    sun: '<circle cx="12" cy="12" r="4.4"/><path d="M12 2.8v2.4M12 18.8v2.4M4.5 4.5l1.7 1.7M17.8 17.8l1.7 1.7M2.8 12h2.4M18.8 12h2.4M4.5 19.5l1.7-1.7M17.8 6.2l1.7-1.7"/>',
    feather: '<path d="M19.4 4.6c-6 0-10.8 2.4-10.8 8.4 0 1.5.4 2.7 1 3.6l9.8-12Z"/><path d="M4.6 19.4 12 12"/><path d="M8.6 15.4h4.8"/>',
    fire: '<path d="M12 21c3.6 0 6-2.3 6-5.6 0-4.2-4.2-5.6-3.4-10.4-2.6 1-4.6 3.4-4.6 6 0 1-.6 1.6-1.2 1.6-.8 0-1.4-.7-1.4-2C5.6 12 6 13 6 15.4 6 18.7 8.4 21 12 21Z"/>',
    rainbow: '<path d="M3.4 19.6a8.6 8.6 0 0 1 17.2 0"/><path d="M7 19.6a5 5 0 0 1 10 0"/><path d="M10.6 19.6a1.4 1.4 0 0 1 2.8 0"/>',
    ghost: '<path d="M5.4 20.4V10a6.6 6.6 0 0 1 13.2 0v10.4l-2.2-1.8-2.2 1.8-2.2-1.8-2.2 1.8-2.2-1.8Z"/><circle cx="9.6" cy="10" r="1.2" fill="currentColor" stroke="none"/><circle cx="14.4" cy="10" r="1.2" fill="currentColor" stroke="none"/>',
    crown: '<path d="M3.6 7.4 7 11l5-6.6 5 6.6 3.4-3.6-1.6 11.2H5.2Z"/><path d="M5.2 20.6h13.6"/>',
    key: '<circle cx="8" cy="12" r="4.4"/><path d="M12.4 12h8"/><path d="M17.6 12v3.4M20.4 12v2.4"/>',
    target: '<circle cx="12" cy="12" r="8.4"/><circle cx="12" cy="12" r="4.4"/><circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none"/>',
    heart: '<path d="M12 20.4S3.6 15.6 3.6 9.6A4.6 4.6 0 0 1 12 7a4.6 4.6 0 0 1 8.4 2.6c0 6-8.4 10.8-8.4 10.8Z"/>',
    gift: '<rect x="3.6" y="9.4" width="16.8" height="11" rx="2.4"/><path d="M2.6 9.4h18.8M12 9.4v11"/><path d="M12 9.4S10.6 4 8 4a2.4 2.4 0 0 0 0 5.4M12 9.4S13.4 4 16 4a2.4 2.4 0 0 1 0 5.4"/>',
    question: '<circle cx="12" cy="12" r="8.6"/><path d="M9.4 9.6a2.7 2.7 0 0 1 5.2.9c0 1.8-2.6 2.1-2.6 3.9"/><circle cx="12" cy="17.4" r="1.1" fill="currentColor" stroke="none"/>',
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
  /** 一张画该用哪个颜色、哪枚图标：老的五关有自己的，其余跟着**任务家族**走
   *  （家族色写在 missions.py，地图圆钮、画廊卡片、chip 用的是同一份）。
   *  漏掉家族这一档的话，75 个 form 里有 70 个会退成同一个橙色。 */
  const styleOf = (qid) => {
    if (QUEST_STYLE[qid]) return QUEST_STYLE[qid];
    const q = (state.quests || []).find(x => x.id === qid);
    const f = q && (state.families || []).find(x => x.id === q.family);
    // 家族在 missions.py 里挂的 icon 是个 emoji，这个 app 不用 emoji——
    // 画的是 GLYPHS 里那枚线条字形，和地图圆钮上是同一枚。
    return f ? { fam: f.id, c: f.color || "#f79433" } : { icon: "palette", c: "#f79433" };
  };
  /** 一张画的小标记：老五关用自己的图标，其余用家族字形。 */
  const markOf = (st, size) => st.fam ? glyph(st.fam, "currentColor", size) : icon(st.icon, size);
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
  function setBuddyName(name, opts) {
    state.buddyName = (name || "").trim().slice(0, 8);
    try {
      if (state.buddyName) localStorage.setItem("artquest.buddy_name", state.buddyName);
      else localStorage.removeItem("artquest.buddy_name");
    } catch (e) { /* 无所谓 */ }
    // 登录着就让名字跟着账号走，换台设备它还叫这个名字。推不上去也不要紧，
    // 名字首先是这台设备上的事。
    if (!(opts && opts.push === false) && savedToken()) {
      api(`${API}/accounts/profile`, { method: "POST",
        body: JSON.stringify({ token: savedToken(), buddy_name: state.buddyName }) }).catch(() => {});
    }
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

  // ===== 账号：一个名字，四位数字暗号 =====
  // 在这之前，「我」就是浏览器里的一串 anon_id：清一次缓存、换一台设备，
  // 画过的一切就不认得你了。而这个 app 想要的恰恰是「在 iPad 上画、在 iPhone 上看」。
  // 所以账号只解决这一件事——它不收邮箱、不收真名，也不是登录墙：
  // 不注册照样能画，注册了那些画才跟着人走。
  const ACCT_KEY = "artquest.account";
  function cachedAccount() {
    try { return JSON.parse(localStorage.getItem(ACCT_KEY) || "null"); } catch (e) { return null; }
  }
  function cacheAccount(acc) {
    try { acc ? localStorage.setItem(ACCT_KEY, JSON.stringify(acc)) : localStorage.removeItem(ACCT_KEY); }
    catch (e) { /* 无所谓 */ }
  }
  /** 后端的 detail 是写给孩子看的一句话，别把状态码丢给他。 */
  function errText(e) {
    const m = /\{[\s\S]*\}/.exec((e && e.message) || "");
    try {
      const d = JSON.parse(m[0]).detail;       // 422 的 detail 是一串校验对象，不是话
      return typeof d === "string" && d ? d : "再试一次吧";
    } catch (x) { return "连不上服务器，等会儿再试"; }
  }
  const sinceText = (iso) => {
    const t = new Date(iso);
    if (isNaN(t)) return "";
    const y = t.getFullYear() === new Date().getFullYear() ? "" : `${t.getFullYear()}年`;
    return `${y}${t.getMonth() + 1}月${t.getDate()}日`;
  };

  async function loadAccount() {
    // 先用本机存着的那份：离线时「我的」也该知道自己是谁，
    // 不然一断网，画过的画看起来就像丢了。
    state.account = cachedAccount();
    const token = savedToken();
    if (!token) { state.account = null; cacheAccount(null); return; }
    try {
      const r = await api(`${API}/accounts/me?anon_id=${encodeURIComponent(state.anonId)}`);
      state.account = r.account || null;
      state.unclaimed = r.unclaimed_here || 0;
      cacheAccount(state.account);
      if (state.account && state.account.buddy_name && !state.buddyName) {
        setBuddyName(state.account.buddy_name, { push: false });
      }
    } catch (e) {
      // 401 = 令牌过期或在别处退掉了，那就真的退出；其它错误多半只是离线，
      // 这时候把人踢下线是在帮倒忙。
      if (/^401/.test((e && e.message) || "")) { setToken(""); cacheAccount(null); state.account = null; }
    }
  }

  function paintAccount() {
    const out = $("#acct-out"), inBox = $("#acct-in"); if (!out || !inBox) return;
    const acc = state.account;
    out.classList.toggle("hidden", !!acc);
    inBox.classList.toggle("hidden", !acc);
    // 名字就写在卡片上，标题旁边再写一遍是重复的；登录之后那个位置改说设备
    $("#acct-chip").textContent = acc && acc.devices > 1 ? `${acc.devices} 台设备` : "";
    if (!acc) return;
    $("#acct-initial").textContent = Array.from(acc.name || "?")[0] || "?";
    $("#acct-name").textContent = acc.name;
    const n = acc.devices || 1;
    $("#acct-sub").textContent = `${sinceText(acc.created_at)}起`
      + (n > 1 ? ` · 在 ${n} 台设备上用过` : " · 只在这台设备上用过");
    const claim = $("#acct-claim");
    claim.classList.toggle("hidden", !state.unclaimed);
    $("#acct-claim-text").textContent = state.unclaimed
      ? `这台设备上还有 ${state.unclaimed} 张画没写名字，是你画的吗？` : "";
  }

  const acctModal = $("#acct-modal");
  let acctMode = "register";
  function openAcct(mode) {
    acctMode = mode;
    const reg = mode === "register";
    $("#acct-modal-title").textContent = reg ? "起个名字" : "用名字找回";
    $("#acct-modal-sub").textContent = reg
      ? "名字是给你自己看的，不用写真名。暗号是四位数字，记住它就行。"
      : "输入你起过的名字和那四位数字，画过的画就跟过来了。";
    $("#btn-acct-go").textContent = reg ? "就用这个" : "进去";
    $("#btn-acct-switch").textContent = reg ? "我已经有名字了" : "还没有，我要起一个";
    $("#acct-err").classList.add("hidden");
    $("#acct-name-input").value = "";
    $("#acct-pin-input").value = "";
    acctModal.classList.remove("hidden");
    setTimeout(() => $("#acct-name-input").focus(), 50);
  }
  const closeAcct = () => acctModal.classList.add("hidden");
  function acctError(text) {
    const el = $("#acct-err"); el.textContent = text; el.classList.remove("hidden");
  }
  $("#acct-pin-input").oninput = (e) => { e.target.value = e.target.value.replace(/\D/g, "").slice(0, 4); };

  async function submitAcct() {
    const name = $("#acct-name-input").value.trim();
    const pin = $("#acct-pin-input").value.trim();
    if (!name) { acctError("先起个名字吧"); return; }
    if (!/^\d{4}$/.test(pin)) { acctError("暗号是四位数字"); return; }
    const btn = $("#btn-acct-go"); btn.disabled = true;
    try {
      const body = { name, pin, anon_id: state.anonId };
      if (acctMode === "register") body.buddy_name = state.buddyName;
      const r = await api(`${API}/accounts/${acctMode}`, { method: "POST", body: JSON.stringify(body) });
      setToken(r.token); state.account = r.account; cacheAccount(r.account);
      // 换台设备登录进来：伙伴的名字跟着账号回来。这台设备上起过名字而账号还空着，
      // 就反过来把它带上去。
      if (r.account.buddy_name) setBuddyName(r.account.buddy_name, { push: false });
      else if (state.buddyName) setBuddyName(state.buddyName);
      closeAcct();
      paintIntentIdentity();        // 心愿页那句「起个名字」现在不用再说了
      await loadAccount();          // 顺便问一句这台设备上有没有还没写名字的画
      await loadCollection(); renderQuests();
      await loadSessions();
    } catch (e) {
      acctError(errText(e));
    } finally { btn.disabled = false; }
  }
  $("#btn-acct-register").onclick = () => openAcct("register");
  $("#btn-acct-login").onclick = () => openAcct("login");
  $("#btn-acct-switch").onclick = () => openAcct(acctMode === "register" ? "login" : "register");
  $("#btn-acct-go").onclick = submitAcct;
  $("#btn-acct-cancel").onclick = closeAcct;
  acctModal.onclick = (e) => { if (e.target === acctModal) closeAcct(); };
  $("#acct-pin-input").onkeydown = (e) => { if (e.key === "Enter") submitAcct(); };
  $("#acct-name-input").onkeydown = (e) => { if (e.key === "Enter") $("#acct-pin-input").focus(); };

  // 认领：把这台设备上以前画的收进自己名下。**要孩子自己点**——
  // 一台共用的 iPad 上，上一个孩子的画不该因为设备相同就自动归了下一个人。
  $("#btn-acct-claim").onclick = async () => {
    const btn = $("#btn-acct-claim"); btn.disabled = true;
    try {
      await api(`${API}/accounts/claim`, { method: "POST",
        body: JSON.stringify({ token: savedToken(), anon_id: state.anonId }) });
      state.unclaimed = 0;
      await loadAccount(); await loadCollection(); renderQuests(); await loadSessions();
    } catch (e) { alert(errText(e)); } finally { btn.disabled = false; }
  };

  $("#btn-acct-logout").onclick = async () => {
    if (!confirm("退出之后，这一屏就只剩这台设备上画的画了。\n名字和暗号都还在，随时能再登回来。")) return;
    try { await api(`${API}/accounts/logout`, { method: "POST", body: JSON.stringify({ token: savedToken() }) }); }
    catch (e) { /* 退出是本地的事，网不通也要退得掉 */ }
    setToken(""); cacheAccount(null); state.account = null; state.unclaimed = 0;
    paintIntentIdentity();
    await loadCollection(); renderQuests();
    await loadSessions();
  };

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
  const TITLES = { world: "彩点的世界", quest: "创作冒险", dex: "画廊", buddy: "彩点", sessions: "我的" };
  function show(name) {
    VIEWS.forEach(v => $(`#view-${v}`).classList.toggle("hidden", v !== name));
    native("keepAwake", { on: name === "draw" });     // 画着画的时候屏幕别自己暗下去
    const tab = VIEW_TAB[name];
    document.body.classList.toggle("inflow", !tab);
    // 每块 tab 有自己的空气颜色：切 tab 像换了个房间，而不是换了一页文档。
    // 具体的色值在 CSS 里（body[data-room]），这里只说现在在哪个房间。
    document.body.dataset.room = tab || (name === "draw" ? "draw" : "flow");
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
    // 画布的像素上限和笔尖预览都只有在这一屏真的显示出来之后才量得到
    // （hidden 的时候 clientWidth/Height 全是 0）。上面那行 classList 已经把它
    // 显示出来了，所以这里**同步**量——不能丢给 rAF：那样画布会在创作屏画出来
    // 之后再改一次尺寸，那一帧里落的笔坐标就是偏的。机器慢的时候这个窗口是真的
    // 能被撞上（满负载跑测试时抓到过一次，第一笔从 200 偏到了 172.5）。
    if (name === "draw") { fitCanvas(); paintNib(); }
    // 地图藏着的时候 getBoundingClientRect 全是 0，小路要在它真的显示出来之后画
    if (name === "quest") paintMapPath();
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
    else if (view === "buddy") { await renderBadgeWall(); await renderGrowth(); }
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
      const r = await api(`${API}/participants/${encodeURIComponent(savedPid() || " ")}/featured?${whoQuery()}`);
      featuredQueue = r.pending || [];
    } catch (e) { return; }
    showNextFeatured();
  }
  function showNextFeatured() {
    const m = $("#featured-modal");
    const item = featuredQueue[0];
    if (!item) { m.classList.add("hidden"); return; }
    // 挑中的可能是老师，也可能是每天自动轮到的那一批（by = curator/...）。
    // 自动那批不说「老师说」——它没在评价这张画，只是把它排到了今天。
    const auto = (item.by || "").startsWith("curator/");
    $("#featured-title").textContent = auto ? "今天轮到你的画了" : "老师选中了你的一张画";
    $("#featured-note").textContent = auto
      ? `你画的《${item.title}》今天轮到挂出去给大家看啦` + (item.note ? `，旁边会写着「${item.note}」。` : "。")
      : item.note ? `老师说：「${item.note}」` : `你画的《${item.title}》被老师挑出来了。`;
    $("#featured-img").src = fileUrl(item.image);
    m.classList.remove("hidden");
  }
  async function answerFeatured(accept) {
    const item = featuredQueue.shift();
    $("#featured-modal").classList.add("hidden");
    if (!item) return;
    try {
      await api(`${API}/sessions/${item.session_id}/featured`,
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
      g = await api(`${API}/participants/${encodeURIComponent(savedPid() || " ")}/growth?${whoQuery()}`);
    } catch (e) { /* 离线就当还没点亮 */ }
    const lit = !!(g && g.n_tasks);
    const best = lit ? Object.entries(g.dims).sort((a, b) => b[1].practice - a[1].practice)[0] : null;
    const col = lit && best && best[1].practice ? FAMILIES[DIM_FAMILY[best[0]]].color : "#cfcbc4";
    state.worldColor = col;
    sp.innerHTML = spriteInner(col, lit && g.total_level >= 9 ? "happy" : "normal");
    sp.classList.toggle("grey", !lit);

    // 封面这张照片的饱和度就是进度：九处里还原了几处，颜色就回来几成。
    // 数据还是九维（dims[key].level > 0 算一处），只是门口不再摆成九个东西。
    const on = CHART_ORDER.filter(k => lit && (g.dims[k] || {}).level > 0).length;
    const p = on / CHART_ORDER.length;
    // 身后那圈光 = 彩点当前的颜色，练到的项数决定它有多亮
    const cover = $(".cover");
    if (cover) {
      cover.style.setProperty("--glow", col);
      cover.style.setProperty("--glow-a", (0.1 + 0.34 * p).toFixed(2));
    }
    $(".world").classList.toggle("lit", on > 0);
    // 封面不再有等级、进度条和说明文字（2026-09-26 用户定的简约风）：
    // 进度只体现在精灵的颜色和身后那圈光的亮度上，九维数据一个字段没少。
  }

  // ---------- 第一次进来的导览 ----------
  // 不是一页一页讲完再放人进来：**暗掉全屏，只把正在说的那个东西留在亮处**，
  // 旁边一句话指着它。一句一个按钮，说完就走。
  // 说明只说一次，所以界面上不再挂常驻的小字。
  // 彩点在别处一直是第一人称（「我还没有名字呢…」「选个颜色，我就变成它！」），
  // 导览原来却用第三人称介绍它——一上来就把角色说没了。统一成它自己开口。
  const TOUR = [
    { sel: "#world-sprite",    text: "我是彩点。你用什么颜色，我就变什么颜色。" },
    { sel: "#btn-rename",      text: "点这支笔，给我起个名字。" },
    { sel: "#btn-enter-world", text: "走，进地图看看。", after: () => enterWorld() },
    { sel: "#quest-grid .quest-card", text: "一个钮是一类任务，挑你想画的。" },
    { sel: ".tab[data-tab='dex']", text: "画过的都挂在画廊里，归你。",
      after: () => openTab("buddy") },
    // 指着**真的那一枚**，不是画一个例子给他看。这一枚一打开就有，
    // 所以第一次进来的孩子在这一步一定看得到东西。
    { sel: "#badge-wall .badge", text: "徽章在我这儿。你已经有一枚了——它们只看你怎么画，不看画得好不好。",
      after: () => openTab("map") },
  ];
  let tourAt = 0, tourOn = false;
  const tourEl = $("#tour");
  function placeTour() {
    const step = TOUR[tourAt];
    const t = document.querySelector(step.sel);
    if (!t) return nextTour(true);
    const r = t.getBoundingClientRect();
    const pad = 10, vw = innerWidth, vh = innerHeight;
    const hole = $("#tour-hole");
    hole.style.left = (r.left - pad) + "px";
    hole.style.top = (r.top - pad) + "px";
    hole.style.width = (r.width + pad * 2) + "px";
    hole.style.height = (r.height + pad * 2) + "px";
    // 圆的东西给圆洞，方的给圆角方洞——洞的形状要跟按钮长得一样
    const square = Math.abs(r.width - r.height) / Math.max(r.width, r.height) < 0.25;
    hole.style.borderRadius = square ? "999px" : "26px";

    $("#tour-text").textContent = step.text;
    $("#tour-dots").innerHTML = TOUR.map((_, i) => `<i class="${i === tourAt ? "on" : ""}"></i>`).join("");
    $("#btn-tour-next").textContent = tourAt === TOUR.length - 1 ? "开始画吧" : "下一步";
    const tip = $("#tour-tip");
    tip.style.visibility = "hidden"; tip.style.left = "0px"; tip.style.top = "0px";
    requestAnimationFrame(() => {
      const tr = tip.getBoundingClientRect();
      const below = r.bottom + pad + 14 + tr.height < vh - 8;
      const top = below ? r.bottom + pad + 14 : Math.max(12, r.top - pad - 14 - tr.height);
      const left = Math.min(Math.max(12, r.left + r.width / 2 - tr.width / 2), vw - tr.width - 12);
      tip.style.left = left + "px";
      tip.style.top = top + "px";
      tip.classList.toggle("up", !below);
      tip.style.setProperty("--arrow", (r.left + r.width / 2 - left) + "px");
      tip.style.visibility = "visible";
    });
  }
  function nextTour(skipAfter) {
    const step = TOUR[tourAt];
    if (!skipAfter && step && step.after) { try { step.after(); } catch (e) { /* 走不通就往下 */ } }
    if (tourAt >= TOUR.length - 1) return endTour();
    tourAt++;
    setTimeout(placeTour, 220);          // 等视图切过去再定位
  }
  function startTour() {
    tourAt = 0; tourOn = true;
    tourEl.classList.remove("hidden");
    setTimeout(placeTour, 60);
  }
  function endTour() {
    tourOn = false;
    tourEl.classList.add("hidden");
    try { localStorage.setItem(TOUR_KEY, "1"); } catch (e) { /* 无所谓 */ }
    checkFeatured();
  }
  $("#btn-tour-next").onclick = () => nextTour(false);
  $("#btn-tour-skip").onclick = endTour;
  $("#btn-guide-again").onclick = () => { show("world"); renderWorld().then(startTour); };
  window.addEventListener("resize", () => { if (tourOn) placeTour(); });
  // 转屏、分屏、收起侧栏——地方都挪了，小路得跟着重画
  let mapPathTimer = 0;
  window.addEventListener("resize", () => {
    clearTimeout(mapPathTimer);
    mapPathTimer = setTimeout(() => { if (!$("#view-quest").classList.contains("hidden")) paintMapPath(); }, 120);
  });
  // 记录带版本号：导览换过一次（从一叠讲解页换成聚光灯），那些在旧版本上点过
  // 「看过了」的设备必须再看一次新的——否则改了等于没改。
  const TOUR_KEY = "artquest.tour/2";
  const guideSeen = () => { try { return localStorage.getItem(TOUR_KEY) === "1"; } catch (e) { return true; } };

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
    // 一张纸，一道从纸里画到纸外的笔迹——「想画什么画什么」。
    // 这儿原来直接借用了 ICONS.palette，但那是**工具箱里的图标**：
    // 三颗实心圆点在一圈描边里，摆进这十个字形中间一眼就看得出不是一套
    // （其余九个都是轮廓为主、最多一两个小实心点的「地方」）。
    M0: '<path d="M5.4 4.4a1 1 0 0 1 1-1h6.6l4.6 4.6v11.6a1 1 0 0 1-1 1H6.4a1 1 0 0 1-1-1Z"/><path d="M12.8 3.6v4.2h4.6"/><path d="M8.2 16.2c1.5-4.4 3.1-4.4 4.3 0 .8 2.8 1.9 2.8 2.7 0"/>',
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
    OPACITY_CHANGE: "OPACITY_CHANGE",
    ZOOM: "ZOOM", PAN: "PAN",
    REFERENCE_SHOW: "REFERENCE_SHOW", REFERENCE_OPEN: "REFERENCE_OPEN",
    REFERENCE_CLOSE: "REFERENCE_CLOSE", REFERENCE_ZOOM: "REFERENCE_ZOOM",
    REFERENCE_PAN: "REFERENCE_PAN", REFERENCE_FOCUS: "REFERENCE_FOCUS",
    CANVAS_FOCUS: "CANVAS_FOCUS",
    PAUSE_START: "PAUSE_START", PAUSE_END: "PAUSE_END",
    TIME_LIMIT_REACHED: "TIME_LIMIT_REACHED", CANVAS_GEOMETRY: "CANVAS_GEOMETRY",
    STROKE_CANCELLED: "STROKE_CANCELLED",
    ASSIST_OPEN: "ASSIST_OPEN",
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
  let tool = "pencil", color = "#222222", size = 4, opacity = 1, drawing = false, last = null, strokeCount = 0, curStroke = null;
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
  /** 这一笔用多浓的颜色。
   *
   *  原来是 `TOOLS[tool].alpha`——浓淡是工具的属性，孩子动不了。
   *  但 stroke 一直在记 `opacity`，`reconstruct.py` 也一直是**按这个字段**合成的
   *  （连同一笔自我重叠的 1-(1-a)^k 都算），并不是查工具表。
   *  所以把它放开给孩子，重建和 QC 一行都不用改。
   *  橡皮例外：它擦回初始画布，半透明的橡皮只会擦出一团脏东西。 */
  const toolAlpha = () => tool === "eraser" ? 1 : opacity;
  function strokeStyle(p) {
    const t = TOOLS[tool];
    const w = size * t.size * (t.pressure ? (1 - t.pressure + t.pressure * 2 * p) : 1);
    ctx.lineWidth = Math.max(0.5, w); ctx.lineCap = t.cap; ctx.lineJoin = "round";
    // the eraser paints back the starting canvas, so it removes the child's
    // marks and never the task's printed stimulus
    ctx.strokeStyle = (tool === "eraser" && eraserPattern) ? eraserPattern : (t.color || color);
    ctx.globalAlpha = toolAlpha();
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
    curStroke = { id, t0, tool, color: TOOLS[tool].color || color, size, opacity: toolAlpha(),
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

  /** 手指的坐标是 clientX/clientY（整页的），而 view.tx/ty 量的是**框内**的位移。
   *  两者差着框的左上角——滚轮那条路早就减掉了 r.left/r.top，捏合这条路没减，
   *  于是「手指按住的那一点不动」根本没做到：一捏，画面整个往上跳一个顶栏的高度
   *  （iPad 上大约 150px）。触摸屏才走这条路，所以这个毛病只在 pad 上犯。
   *  这里在手势开始时就把中点折进框内坐标，后面全程用同一套单位。 */
  function startGesture() {
    const pts = [...touches.values()];
    if (pts.length < 2) return;
    const m = _mid(pts[0], pts[1]), r = viewport.getBoundingClientRect();
    gesture = { n: touches.size, t0: elapsed(), moved: 0,
                d0: _dist(pts[0], pts[1]), z0: view.z, mx0: m.x - r.left, my0: m.y - r.top,
                tx0: view.tx, ty0: view.ty,
                panFrom: [Math.round(view.tx), Math.round(view.ty)], points: [] };
  }
  function moveGesture() {
    const pts = [...touches.values()];
    if (!gesture || pts.length < 2) return;
    gesture.n = Math.max(gesture.n, touches.size);
    const r = viewport.getBoundingClientRect();
    const _m = _mid(pts[0], pts[1]), d = _dist(pts[0], pts[1]);
    const m = { x: _m.x - r.left, y: _m.y - r.top };     // 和 view.tx/ty 同一套坐标
    gesture.moved = Math.max(gesture.moved, Math.hypot(m.x - gesture.mx0, m.y - gesture.my0),
                             Math.abs(d - gesture.d0));
    const prev = view.z;
    // 一步算完：让「手指落下时那个中点下面的画布位置」始终待在当前中点下面
    const z = clamp(gesture.d0 > 0 ? gesture.z0 * (d / gesture.d0) : view.z, MIN_ZOOM, MAX_ZOOM);
    const lx = (gesture.mx0 - gesture.tx0) / gesture.z0, ly = (gesture.my0 - gesture.ty0) / gesture.z0;
    view.z = z;
    view.tx = m.x - lx * z;
    view.ty = m.y - ly * z;
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
    if (eyedrop) { e.preventDefault(); canvas.setPointerCapture(e.pointerId); dropping = true; sampleAt(e); return; }
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
    if (dropping) { sampleAt(e); return; }
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
    if (dropping) { if (!e || e.type !== "pointerleave") commitDrop(); return; }
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

  /** 画布必须整张看得见。
   *
   *  样式表里写的是 `canvas { max-height:100% }`，它**解析不出值**：
   *  .canvas-viewport 的高度是 flex 收缩出来的，specified height 还是 auto，
   *  百分比没有可依的高度，于是 max-height 计算成 none——画布按宽度撑满、
   *  比框高出一截，被 overflow:hidden 切掉。iPad 横屏上下各切 22px（整幅画的
   *  7.7%），桌面各切 16px。孩子看不到自己画到了边上没有，而构图这一维评的
   *  正是他从来没看全过的那个框。
   *
   *  所以上限按**像素**写进 style：先松开让布局自己说有多少地方，再按量到的
   *  高度封顶。画布小于框的那一边留白是白的，和画布同色，看不出来。 */
  function fitCanvas() {
    if (!viewport) return;
    const studio = $("#view-draw .studio"), stage = $("#view-draw .stage");
    if (studio) { studio.style.gridTemplateRows = ""; studio.style.gridTemplateColumns = ""; }   // 先松开再量
    canvas.style.maxHeight = "";                 // 先松开，否则量到的是上一次的结果
    // 画布的高度上限**只能问 viewport**：它是 flex 子项，画布的自然高度一旦
    // 超过能给的空间就会被压缩，压缩后的 clientHeight 正是画布该有的上限。
    // 换成 stage.clientHeight 就是拿了压缩**前**的空间，画布照着长出去，
    // 再被 overflow:hidden 切掉——test_no_edge_of_the_canvas_is_cut_off 守的就是这个。
    const avail = viewport.clientHeight;
    if (avail > 0) canvas.style.maxHeight = avail + "px";
    // 画布是 1024:704（1.45），画布区通常比这更扁，于是画布总是**宽度先到顶**、
    // 高度余出一截。那一截不处理的话：居中会让三列的顶边各错开一半，
    // 全甩到底下又会在画布和 dock 之间裂出一条空带。
    // 所以把第一行收到画布的实高——顶边齐，dock 也贴着画布。
    // 右栏跨这两行，跟着一起收，它底部的主按钮就和 dock 落在同一条线上。
    // 窄屏是 flex 单列，这个属性不起作用，设了也无害。
    // 收行高是另一回事，那要问 stage —— 它才知道这一行**本来**有多少高度。
    const h = canvas.offsetHeight, room = stage ? stage.clientHeight : avail;
    if (studio && h > 0 && h < room - 1) studio.style.gridTemplateRows = h + "px auto";
    // 左边细条和画布等高：撤销/重做各占一头，两根槽把剩下的高度平分。
    // 槽 = 轨道 --sl-len + 22px 的圆头余量；元素之间 10px。
    const rail = $("#view-draw .railbar");
    if (rail && h > 0 && getComputedStyle(rail).flexDirection === "column") {
      const btns = [...rail.querySelectorAll(".railbtn")].filter(b => !b.classList.contains("hidden"));
      const btnH = btns.reduce((a, b) => a + b.offsetHeight, 0), items = btns.length + 2;
      const sl = Math.floor((h - btnH - 10 * (items - 1) - 44) / 2);
      rail.style.setProperty("--sl-len", clamp(sl, 100, 320) + "px");
    }
    // 视口矮的时候（真 iPad 的 Safari 有工具栏，比模拟器矮一截）画布是**高度**先到顶，
    // 宽度占不满中间那一列：画布在列里居中，dock 和右栏却还按整列排——
    // dock 比画框宽出一截，右栏离画布比离 dock 远。把中间那一列收到画布的实宽，
    // 三列一起在屏幕里居中，细条、画布、dock、右栏就永远贴在一起。
    // 宽度先到顶的时候实宽就是整列，等于没改。
    const w = canvas.offsetWidth, grid = studio && getComputedStyle(studio).display === "grid";
    if (grid && stage && w > 0 && w < stage.clientWidth - 1) {
      const cols = getComputedStyle(studio).gridTemplateColumns.split(" ");
      if (cols.length === 3) studio.style.gridTemplateColumns = `${cols[0]} ${w}px ${cols[2]}`;
    }
    applyView();                                  // 框变了，平移的边界跟着变
  }
  let fitPending = false;
  const scheduleFit = () => {
    if (fitPending) return;
    fitPending = true;
    requestAnimationFrame(() => { fitPending = false; if (drawViewOpen()) fitCanvas(); });
  };
  addEventListener("resize", scheduleFit);
  addEventListener("orientationchange", scheduleFit);
  if (window.visualViewport) visualViewport.addEventListener("resize", scheduleFit);

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
    $("#btn-hand").classList.toggle("active", handMode); applyView(); syncName();
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
  const clearModal = $("#clear-modal");
  $("#btn-clear").onclick = () => {
    const n = visible.length;
    $("#clear-body").textContent = n
      ? `这张画上的 ${n} 笔都会被擦掉。想反悔的话，撤销键能找回来。`
      : "画布上还没有笔画。";
    clearModal.classList.remove("hidden");
  };
  $("#btn-clear-keep").onclick = () => clearModal.classList.add("hidden");
  $("#btn-clear-go").onclick = () => {
    clearModal.classList.add("hidden");
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
  // ---------- dock 上那一个小框：现在手里是什么 ----------
  // 图标底下不放字。选中的工具名常驻在这儿；按一下就发生的按钮（缩放、清空、
  // 撤销……）和拖滑块的时候，它闪一下那个名字，一秒后回到当前工具。
  const TOOL_NAMES = { pencil: "铅笔", brush: "笔刷", marker: "马克笔", eraser: "橡皮" };
  let nameTimer = null;
  function syncName() {
    const el = $("#dock-name"); if (!el) return;
    clearTimeout(nameTimer); el.classList.remove("flash");
    el.textContent = handMode ? "移动" : (eyedrop ? "吸色" : TOOL_NAMES[tool]);
  }
  function flashName(text) {
    const el = $("#dock-name"); if (!el) return;
    clearTimeout(nameTimer); el.textContent = text; el.classList.add("flash");
    nameTimer = setTimeout(syncName, 1000);
  }
  document.querySelectorAll(".dock [data-name], .railbar [data-name]").forEach(b =>
    b.addEventListener("pointerdown", () => { if (!b.disabled) flashName(b.dataset.name); }));

  /** 把界面调到某个工具的状态。不记事件——记事件是点击那一步的事。 */
  function applyTool(name) {
    tool = name;
    document.querySelectorAll("#tools button").forEach(x => x.classList.toggle("active", x.dataset.tool === name));
    handMode = false; $("#btn-hand").classList.remove("active"); applyView();
    // 橡皮永远 100%、也没有颜色：浓淡那根滑块变灰、色块变成空心，别让孩子拖了半天没反应
    const erasing = tool === "eraser";
    document.body.classList.toggle("erasing", erasing);
    $("#opacity").disabled = erasing; $("#opacity").closest(".vsl").classList.toggle("off", erasing);
    setEyedrop(false);
    syncName();
    paintNib();     // 换了工具，笔尖的粗细倍率和浓淡都变了
  }
  document.querySelectorAll("#tools button").forEach(b => b.onclick = () => {
    if (b.disabled) return;
    applyTool(b.dataset.tool); logEvent(EV.BRUSH_CHANGE, { tool });
  });
  // 壳把画存进相册之后回一句：成了就把钮变成「存好了」，没成说一句孩子看得懂的话，能再试
  window.addEventListener("artquest:saved", (e) => {
    const sv = $("#btn-save"); if (!sv) return;
    const ok = !!(e.detail && e.detail.ok);
    sv.textContent = ok ? "存好了，在相册里" : "没存上，再试一次";
    sv.disabled = ok;
    if (ok) native("haptic", { style: "success" });
  });

  // Apple Pencil 双击（原生壳转发过来）：橡皮 ↔ 刚才用的那支笔。记成 BRUSH_CHANGE，
  // 多一个 source 说它是笔杆上来的——和点 dock 是两种不同的动作。
  let toolBeforeEraser = "pencil";
  window.addEventListener("artquest:pencilTap", () => {
    if ($("#view-draw").classList.contains("hidden")) return;
    const next = tool === "eraser" ? toolBeforeEraser : "eraser";
    if (tool !== "eraser") toolBeforeEraser = tool;
    const btn = document.querySelector(`[data-tool="${next}"]`);
    if (!btn || btn.disabled) return;
    applyTool(next); logEvent(EV.BRUSH_CHANGE, { tool, source: "pencil_tap" });
  });
  // 粗细的刻度是**非线性**的：1→2 是把线加粗一倍，40→41 根本看不出来。
  // 滑杆走 0–100 的均匀格子，映射到 1–60 的平方曲线，细的那头才有分辨力。
  // 存进 stroke 的仍然是最终像素值，语义没变。
  const SIZE_MIN = 1, SIZE_MAX = 60;
  const posToSize = (v) => Math.max(SIZE_MIN, Math.round(SIZE_MIN + (SIZE_MAX - SIZE_MIN) * Math.pow(v / 100, 2)));
  const sizeToPos = (px) => Math.round(100 * Math.sqrt(Math.max(0, (px - SIZE_MIN) / (SIZE_MAX - SIZE_MIN))));

  /** 笔尖预览：按当前粗细和浓淡画一个**真实大小**的点。
   *  滑杆上的「24」说不清 24px 有多粗，一个点说得清。 */
  function paintNib() {
    const dot = $("#nib-dot"); if (!dot) return;
    // 初始化时创作屏还是 hidden，clientHeight 是 0——直接减 8 会得到负宽度，
    // 预览框就一直是空的。量不到就按样式里的 48px 算。
    const box = ($("#nib").clientHeight || 74) - 10;
    const w = Math.min(box, Math.max(2, size * (TOOLS[tool].size || 1)));
    dot.style.width = dot.style.height = w + "px";
    dot.style.opacity = toolAlpha();
    dot.style.background = tool === "eraser" ? "#fff" : color;
    dot.style.boxShadow = tool === "eraser" ? "inset 0 0 0 2px var(--line)" : "none";
  }

  /** 拖滑块的那几秒把笔尖预览浮在滑块边上，松手九百毫秒后收走。
   *  原来它常驻在画笔条里占着 48px；现在细条上只有滑块本身，
   *  真实大小的点在需要的时候才出现——这比一个「粗细 24」的标签直观。 */
  let nibTimer = null;
  function flashNib(input) {
    const nib = $("#nib"); if (!nib) return;
    paintNib();
    const r = input.getBoundingClientRect(), S = 74, gap = 10;
    // 滑块立着的时候浮在它右边，躺着的时候浮在它上方
    const vertical = r.height > r.width;
    const left = vertical ? r.right + gap : r.left + r.width / 2 - S / 2;
    const top = vertical ? r.top + r.height / 2 - S / 2 : r.top - S - gap;
    nib.style.left = clamp(left, 8, innerWidth - S - 8) + "px";
    nib.style.top = clamp(top, 8, innerHeight - S - 8) + "px";
    nib.classList.add("show");
    clearTimeout(nibTimer);
    nibTimer = setTimeout(() => nib.classList.remove("show"), 900);
  }

  /** 竖排里那颗看得见的拇指是我们自己画的（原生的居中各家算法不同），按 value 摆位置。 */
  function placeThumb(input) {
    const well = input.closest(".vsl"); if (!well) return;
    const lo = +input.min || 0, hi = +input.max || 100;
    well.style.setProperty("--pos", String((+input.value - lo) / (hi - lo)));
  }
  $("#size").oninput = (e) => {
    placeThumb(e.target);
    size = posToSize(+e.target.value);
    $("#size-val").textContent = size; flashNib(e.target); flashName("粗细");
    logEvent(EV.SIZE_CHANGE, { size });
  };
  $("#opacity").oninput = (e) => {
    placeThumb(e.target);
    opacity = Math.round(+e.target.value) / 100;
    $("#opacity-val").textContent = Math.round(opacity * 100) + "%"; flashNib(e.target); flashName("浓淡");
    logEvent(EV.OPACITY_CHANGE, { opacity: R(opacity, 2) });
  };

  /** 点开才浮出、点别处就收。这是 Procreate 那套简约真正的来源——
   *  不是把面板挪到哪条边上，是**默认一个面板都不展开**。 */
  let popOpen = null;
  const closePop = () => { if (popOpen) { popOpen.classList.add("hidden"); popOpen = null; } };
  function openPop(pop, anchor) {
    closePop();
    pop.classList.remove("hidden");
    popOpen = pop;
    // 先放到触发它的按钮上方；上面塞不下就翻到下方。左右都夹在屏幕里。
    const a = anchor.getBoundingClientRect(), r = pop.getBoundingClientRect(), gap = 10;
    let top = a.top - r.height - gap;
    if (top < 8) top = Math.min(a.bottom + gap, innerHeight - r.height - 8);
    pop.style.top = clamp(top, 8, Math.max(8, innerHeight - r.height - 8)) + "px";
    pop.style.left = clamp(a.left + a.width / 2 - r.width / 2, 8,
                           Math.max(8, innerWidth - r.width - 8)) + "px";
  }
  // 捕获阶段监听：面板里的点击照常走自己的 handler，外面的一律先收面板。
  document.addEventListener("pointerdown", (e) => {
    if (!popOpen || popOpen.contains(e.target) || e.target.closest("#btn-color")) return;
    closePop();
  }, true);
  addEventListener("resize", closePop);
  const PALETTE = ["#222222", "#7a7a7a", "#ffffff", "#e63946", "#f4a261", "#ffd166", "#2a9d8f", "#4caf50", "#1d6fe0", "#7b4fd6", "#f28cb1", "#8d5524"];
  const pal = $("#palette");
  PALETTE.forEach(c => { const d = document.createElement("div"); d.style.background = c; d.title = c;
    d.onclick = () => { setColor(c, d, "palette"); closePop(); }; pal.appendChild(d); });
  // ---------- 彩点的窗 ----------
  // 第一次创作时蒙着一层模糊，孩子点一下才揭开。不做输入框是有意的：
  // 8–14 岁打一句话要半分钟，输入法还盖住画布；而**他什么时候点**本身
  // 就是这个研究要的信号，一次点击比一段聊天记录好编码得多。
  const ASSIST_COOLDOWN_MS = 30000;
  let assistNth = 0, assistAt = 0, assistLast = "";

  // 对照组（dialogue_mode=none）整扇窗都不出现——后端也会 403，两头一致。
  const assistOn = () => (state.condition.dialogue_mode || "on_demand") !== "none";

  const INTENT_LEADS = ["我想要画", "我想画", "我要画", "我想要", "我想", "我要", "想画", "画一个", "画"];
  function bareIntent(t) {
    t = String(t || "").trim();
    for (const lead of INTENT_LEADS) if (t.startsWith(lead) && t.length > lead.length) { t = t.slice(lead.length); break; }
    return t.replace(/^[。！!，,、\s]+|[。！!，,、\s]+$/g, "");
  }

  function assistSay(text, cls) {
    const log = $("#assist-log");
    const d = document.createElement("div");
    d.className = "assist-msg" + (cls ? " " + cls : "");
    d.textContent = text;
    log.appendChild(d); log.scrollTop = log.scrollHeight;
    return d;
  }

  function assistReset(intent) {
    const box = $("#assist"); if (!box) return;
    box.classList.toggle("hidden", !assistOn());
    // 计时器：有窗的时候坐进窗的标题行右侧，窗的底边才能和画布底边对齐；
    // 对照组没有窗，它就还是右栏里自己的一行。
    const timer = $(".timer");
    if (timer) (assistOn() ? box.querySelector(".assist-head") : $(".brief-spacer").parentNode)
      .insertBefore(timer, assistOn() ? null : $(".brief-spacer"));
    if (!assistOn()) return;
    $("#assist-log").innerHTML = "";
    box.classList.add("veiled"); box.classList.remove("open-fb");
    $("#btn-assist").classList.remove("hidden");
    $(".assist-veil-t").textContent = `听听${buddyName()}怎么说`;
    assistNth = 0; assistAt = 0; assistLast = "";
    // 心情那张卡去掉了，但他自己写的意图还给他：画到一半最容易忘的
    // 就是本来要画什么。蒙着的时候看不见，揭开第一眼就是这句。
    const want = ((intent && intent.text) || "").trim();
    // 孩子写的几乎都从「我想画」起头，直接拼是「你说你想画我想画……」。剥掉起头和句号再嵌。
    if (want) assistSay(`你说想画的是「${bareIntent(want)}」。`);
  }

  /** 第二阶段：那份正式反馈直接摊开，**不再蒙**——他正要照着改，得能反复看。
   *  这时也不用再调接口，反馈早就在手里了。 */
  function assistShowFeedback(text) {
    const box = $("#assist"); if (!box || !assistOn()) return;
    box.classList.remove("hidden", "veiled");
    $("#assist-log").innerHTML = "";
    if (text) assistSay(text, "fb");
    // 正式反馈比过程中的一句话长得多，给它整块地方，别让孩子在小窗里滚着读
    box.classList.add("open-fb");
    // 这里用 .hidden 类而不是 hidden 属性：全局的 `button { display:inline-flex }`
    // 压过 UA 样式表里的 `[hidden] { display:none }`，属性对按钮根本不生效。
    $("#btn-assist").classList.add("hidden");
  }

  const btnAssist = $("#btn-assist");
  if (btnAssist) btnAssist.onclick = async () => {
    const box = $("#assist");
    // 连点命中冷却时也照记（cached=true）：否则「想看」的次数会被吃掉，
    // 而那正是他卡住的强度。
    const cached = Date.now() - assistAt < ASSIST_COOLDOWN_MS && !!assistLast;
    assistNth++;
    logEvent(EV.ASSIST_OPEN, { nth: assistNth, cached, phase: state.phase });
    box.classList.remove("veiled");
    $(".assist-veil-t").textContent = `${buddyName()}，帮帮我`;
    if (cached) {
      // 冷却里再点，不追加一条一模一样的（那看着像坏了）——让最后那条闪一下，
      // 他就知道「就是刚才那句」。点击本身照样记了账，上面那行。
      const last = $("#assist-log").lastElementChild;
      if (last) { last.classList.remove("again"); void last.offsetWidth; last.classList.add("again"); }
      return;
    }
    const wait = assistSay("……", "wait");
    try {
      const r = await api(`${API}/sessions/${state.sessionId}/assist`, {
        method: "POST",
        body: JSON.stringify({ image: canvas.toDataURL("image/png"),
                               elapsed_ms: Math.round(elapsed()), nth: assistNth }),
      });
      wait.remove();
      assistLast = r.text; assistAt = Date.now();
      assistSay(r.text);
    } catch (e) {
      // 陪伴挂了绝不能挡住画画
      wait.remove(); assistSay("我在这儿呢，接着画。");
    }
  };

  const BUDDY_LINES = ["选个颜色，我就变成它！", "这个颜色真好看～", "大胆画，画错也没关系！", "多试几种颜色，我陪你！", "你画什么，我就变什么～"];
  function updateBuddy() {
    state.color = color;
    const sp = $("#draw-sprite"); if (sp) sp.innerHTML = spriteInner(color, "normal");
    // 那行「选个颜色，我就变成它！」的静态台词退役了：彩点现在在窗里真的说话。
    // sprite 还留着（窗的头像），所以它仍然跟着当前颜色变。
    if (!$("#view-draw").classList.contains("hidden")) renderFlow(state.phase === "after" ? "evolve" : "draw");
  }
  // 刚用过的颜色。重复挑同一个色本身就是过程信号，别让孩子每次重新找。
  const RECENT_MAX = 8;
  let recent = [];
  function pushRecent(c) {
    c = String(c).toLowerCase();
    if (PALETTE.includes(c)) return;              // 预设本来就在手边，不占这几格
    recent = [c, ...recent.filter(x => x !== c)].slice(0, RECENT_MAX);
    const wrap = $("#pk-recent-wrap"), box = $("#pk-recent");
    if (!wrap || !box) return;
    wrap.classList.toggle("hidden", !recent.length);
    box.innerHTML = "";
    recent.forEach(x => {
      const b = document.createElement("button");
      b.style.background = x; b.title = x;
      b.onclick = () => { setPickerColor(x); };
      box.appendChild(b);
    });
  }

  // source：palette / picker / eyedropper——同一个 COLOR_CHANGE，多一个字段说它从哪儿来。
  // 从自己画里吸出来的颜色和从色板上点的，在「他怎么用色」这件事上不是一回事。
  function setColor(c, el, source) {
    color = c;
    document.documentElement.style.setProperty("--cur", c);
    pal.querySelectorAll("div").forEach(x => x.classList.toggle("active", x === el));
    if (tool === "eraser") document.querySelector('[data-tool="pencil"]').click();
    logEvent(EV.COLOR_CHANGE, source ? { color: c, source } : { color: c });
    state.buddyTick++; updateBuddy(); paintNib();
  }
  pal.firstChild.classList.add("active");

  // ---------- 取色器 ----------
  // 饱和度/明度面板是两层 CSS 渐变叠出来的，不用 canvas：任何尺寸都清晰，
  // 也不用管 devicePixelRatio。横轴饱和度、纵轴明度、下面一条色相。
  const hex2 = (n) => n.toString(16).padStart(2, "0");
  function hsv2hex(h, sv, v) {
    const f = (n) => { const k = (n + h / 60) % 6; return v - v * sv * Math.max(0, Math.min(k, 4 - k, 1)); };
    return "#" + hex2(Math.round(f(5) * 255)) + hex2(Math.round(f(3) * 255)) + hex2(Math.round(f(1) * 255));
  }
  function hex2hsv(hx) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hx || "");
    if (!m) return { h: 0, s: 0, v: 0.13 };
    const n = parseInt(m[1], 16), r = (n >> 16) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
    let h = 0;
    if (d) h = mx === r ? 60 * (((g - b) / d) % 6) : mx === g ? 60 * ((b - r) / d + 2) : 60 * ((r - g) / d + 4);
    return { h: (h + 360) % 360, s: mx ? d / mx : 0, v: mx };
  }

  const pkModal = $("#color-modal"), pkSv = $("#pk-sv"), pkCur = $("#pk-cur"), pkHue = $("#pk-hue");
  let pk = { h: 0, s: 0, v: 0.13 };
  function paintPicker() {
    const hx = hsv2hex(pk.h, pk.s, pk.v);
    document.documentElement.style.setProperty("--pk-h", String(Math.round(pk.h)));
    pkCur.style.left = (pk.s * 100) + "%";
    pkCur.style.top = ((1 - pk.v) * 100) + "%";
    pkCur.style.background = hx;
    $("#pk-now-hex").textContent = hx.toUpperCase();
    $("#pk-now-dot").style.background = hx;
    pkHue.value = Math.round(pk.h);
    return hx;
  }
  function setPickerColor(hx) { pk = hex2hsv(hx); paintPicker(); }
  function pickAt(e) {
    const r = pkSv.getBoundingClientRect();
    pk.s = clamp((e.clientX - r.left) / r.width, 0, 1);
    pk.v = 1 - clamp((e.clientY - r.top) / r.height, 0, 1);
    paintPicker();
  }
  let picking = false;
  pkSv.addEventListener("pointerdown", (e) => { picking = true; pkSv.setPointerCapture(e.pointerId); pickAt(e); e.preventDefault(); });
  pkSv.addEventListener("pointermove", (e) => { if (picking) pickAt(e); });
  pkSv.addEventListener("pointerup", () => { picking = false; });
  pkSv.addEventListener("pointercancel", () => { picking = false; });
  pkHue.oninput = (e) => { pk.h = +e.target.value; paintPicker(); };

  $("#btn-color").onclick = () => {
    if (popOpen === $("#pop-color")) { closePop(); return; }
    openPop($("#pop-color"), $("#btn-color"));
  };
  $("#btn-more-color").onclick = () => {
    closePop(); setPickerColor(color); pkModal.classList.remove("hidden");
  };
  $("#pk-ok").onclick = () => {
    const hx = paintPicker();
    pkModal.classList.add("hidden");
    setColor(hx, null, "picker"); pushRecent(hx);
  };
  $("#pk-cancel").onclick = () => pkModal.classList.add("hidden");
  pkModal.onclick = (e) => { if (e.target === pkModal) pkModal.classList.add("hidden"); };

  // ---------- 吸管：从自己的画里取颜色 ----------
  // 取色器整个盖住画布，孩子想要「刚才那个蓝」只能凭记忆。吸管让他直接去画里指。
  // 按住可以拖，笔尖那个泡泡跟着指尖显示当前颜色，松手才算数——
  // 手指本身就挡住了要吸的那个点，不预览的话吸到哪儿全靠运气。
  let eyedrop = false, dropping = false, dropHex = null;
  function setEyedrop(on) {
    eyedrop = on; dropping = false; dropHex = null;
    document.body.classList.toggle("eyedrop", on);
    $("#eyedrop-tip").classList.toggle("hidden", !on);
    if (typeof syncName === "function") syncName();
    if (!on) $("#nib").classList.remove("show");
  }
  function sampleAt(e) {
    const p = pos(e);
    const x = clamp(Math.floor(p.x), 0, canvas.width - 1), y = clamp(Math.floor(p.y), 0, canvas.height - 1);
    const d = ctx.getImageData(x, y, 1, 1).data;
    dropHex = "#" + [d[0], d[1], d[2]].map(v => v.toString(16).padStart(2, "0")).join("");
    const nib = $("#nib"), dot = $("#nib-dot"), S = 74;
    dot.style.width = dot.style.height = "40px"; dot.style.opacity = 1; dot.style.background = dropHex;
    dot.style.boxShadow = "inset 0 0 0 2px rgba(0,0,0,.08)";
    nib.style.left = clamp(e.clientX - S / 2, 8, innerWidth - S - 8) + "px";
    nib.style.top = clamp(e.clientY - S - 26, 8, innerHeight - S - 8) + "px";
    nib.classList.add("show"); clearTimeout(nibTimer);
  }
  function commitDrop() {
    const hx = dropHex; setEyedrop(false);
    if (!hx) return;
    const el = [...pal.querySelectorAll("div")].find(d => d.title === hx) || null;
    setColor(hx, el, "eyedropper"); pushRecent(hx);
  }
  $("#btn-eyedrop").onclick = () => { closePop(); setEyedrop(true); };
  $("#btn-eyedrop-cancel").onclick = () => setEyedrop(false);

  // 两根滑杆的初始位置得从状态反推，不能写死在 HTML 里——粗细的刻度是非线性的，
  // 写死一个 value 就意味着「滑块在哪」和「size 是多少」从第一帧起就对不上。
  $("#size").value = sizeToPos(size);
  $("#size-val").textContent = size;
  $("#opacity").value = Math.round(opacity * 100);
  $("#opacity-val").textContent = Math.round(opacity * 100) + "%";
  placeThumb($("#size")); placeThumb($("#opacity"));
  document.documentElement.style.setProperty("--cur", color);
  paintNib();
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
      await api(`${API}/sessions/${state.sessionId}/snapshot`, { method: "POST", body: JSON.stringify({ image: canvas.toDataURL("image/png"), elapsed_ms: elapsed() }) });
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
    // 不在孩子眼前倒数（原来这里写「· 剩 08:59」）：倒计时本身就是压力，
    // 到点自动交卷的逻辑照旧。研究要的 TIME_LIMIT_REACHED 一条不少。
    if (left === 0) {
      state.timeUp = true; logEvent("TIME_LIMIT_REACHED", { limit_sec: limit });
      const btn = state.phase === "after" ? $("#btn-submit-after") : $("#btn-submit");
      if (btn) btn.click();
    }
  }
  function stopTimers() { state.timers.forEach(clearInterval); state.timers = []; }

  // ===== 画廊：自己的画（画完的和没画完的都在）=====
  async function loadCollection() {
    const wrap = $("#collection-wrap"), grid = $("#collection"), empty = $("#dex-empty");
    // 一张画都没有的时候也**把墙挂在那儿**，只是墙上空着——
    // 整块消失会让人以为这一屏坏了，而它只是还在等第一张画。
    // 和下面「大家的画廊」是同一个做法。连不上服务器时同理：宁可挂一面空墙。
    wrap.classList.remove("hidden");
    let rows = [];
    try { rows = await mySessions(); }
    catch (e) { if (empty) empty.classList.remove("hidden"); return; }
    state.allSessions = rows;          // 地图的星、跨作品徽章、成长视图都读它
    // 撤回是真删，界面里也不留痕；没画完的**留着**——半张画也是画过的证据，
    // 把它藏起来等于说「没画完就不算」。
    const mine = rows.filter(r => r.status !== "withdrawn");
    const done = mine.filter(r => r.status === "done");
    if (empty) empty.classList.toggle("hidden", !!mine.length);
    const titleOf = (qid) => (state.quests.find(q => q.id === qid) || {}).title || qid;
    grid.innerHTML = mine.map((r, i) => {
      const st = styleOf(r.quest_id);
      const feat = (r.featured || {}).state;
      const flag = feat === "accepted"
        ? `<button class="dex-featured on" data-sid="${r.session_id}" data-accept="0"
             title="收回来，不再给大家看">${icon("pin", 12)}挂在大家的墙上</button>`
        : feat === "declined"
          ? `<button class="dex-featured" data-sid="${r.session_id}" data-accept="1"
               title="老师选过它，你当时说先不要">${icon("pin", 12)}老师选过它</button>`
          : "";
      const flagName = WORK_STATUS[r.status];
      const tags = (flagName ? `<span class="work-chip ${flagName.cls}">${flagName.zh}</span>` : "")
        + (r.revised ? `<span class="work-chip evolve">改过一次</span>` : "");
      // 贴在墙上的照片没有一张是绝对正的。角度按 id 定死，不随机——
      // 每次打开都换一个角度就成了晃动，不是手贴的感觉。
      const tilt = ((r.session_id || "").charCodeAt(0) + i) % 5 - 2;
      return `<div class="dex-card" style="--qc:${st.c};--tilt:${(tilt * 0.8).toFixed(2)}deg">
        <button class="dex-open" data-sid="${r.session_id}" data-qid="${r.quest_id}">
          <span class="dex-thumb">${r.status === "done"
            ? `<img src="${FILES}/${r.session_id}/after.png" alt="" loading="lazy"
                 onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'dex-unfinished'}))">`
            : `<span class="dex-unfinished">${icon("pencil", 22)}</span>`}</span>
          <span class="dex-cap"><b>${markOf(st, 14)}${titleOf(r.quest_id)}</b>
            <span class="dex-when">${whenText(r.created_at)}</span>
            ${tags ? `<span class="dex-tags">${tags}</span>` : ""}</span>
        </button>${flag}</div>`;
    }).join("");
    grid.querySelectorAll(".dex-open").forEach(b => {
      b.onclick = () => openWork(b.dataset.sid, b.dataset.qid);
    });
    grid.querySelectorAll(".dex-featured").forEach(b => {
      b.onclick = async (e) => {
        e.stopPropagation();
        await api(`${API}/sessions/${b.dataset.sid}/featured`,
          { method: "POST", body: JSON.stringify({ accept: b.dataset.accept === "1" }) });
        await loadCollection(); await renderWall();
      };
    });
    // 右上角说的是「你画了多少」，不是「还差多少」。
    // 「3/75 种」看着永远像还差得远，而把 75 个 form 摊给孩子本来也没意义。
    const fams = new Set(done.map(r => familyOf(r.task_id || r.quest_id)).filter(Boolean));
    const allFams = (state.families || []).length;
    const dp = $("#dex-progress");
    const every = allFams > 0 && fams.size >= allFams;
    dp.classList.toggle("done", every);
    dp.textContent = !mine.length ? "" : every ? "每个地方都画过了" : `${mine.length} 张`;
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
    try { g = await api(`${API}/participants/${encodeURIComponent(savedPid() || " ")}/growth?${whoQuery()}`); }
    catch (e) { return; }
    if (!g || !g.n_tasks) { wrap.classList.add("hidden"); return; }
    wrap.classList.remove("hidden");

    const byKey = Object.fromEntries(state.cfg.dimensions.map(d => [d.key, d]));
    const best = Object.entries(g.dims).sort((a, b) => b[1].practice - a[1].practice)[0];
    const col = FAMILIES[DIM_FAMILY[best[0]]].color;
    $("#growth-sprite").innerHTML = spriteInner(col, g.total_level >= 9 ? "happy" : "normal");
    // one ring per three levels: a visible shape change, not a number
    const rings = Math.min(5, Math.floor(g.total_level / 3));
    $("#growth-rings").innerHTML = rings ? icon("star", 16).repeat(rings) : "";
    $("#growth-total").textContent = `成长 ${g.total_level}/${g.max_total}`;
    $("#growth-say").textContent = best[1].practice
      ? `我在「${byKey[best[0]].zh}」上长得最快！`
      : "再画几幅，我就开始长啦～";

    $("#growth-dims").innerHTML = CHART_ORDER.map(key => {
      const d = byKey[key], v = g.dims[key];
      if (!d || !v) return "";
      const fam = FAMILIES[DIM_FAMILY[key]];
      const pips = Array.from({ length: v.max_level }, (_, i) =>
        `<i class="${i < v.level ? "on" : ""}"></i>`).join("");
      // 「评价层已唤醒 · 29 次评分」是后台说话。孩子这儿只要两件事：
      // 还差几幅能长一格，以及这项现在有没有人在评。
      const left = Math.ceil(Math.max(0, (v.next_at || 0) - v.practice));
      const next = v.next_at !== null
        ? (left <= 0 ? "马上升一格" : `再画 ${left} 幅长一格`)
        : "长满了";
      const layer = v.awake ? "" : `<div class="gsleep">这项等模型来评</div>`;
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
      state.study = await api(`${API}/study/assign`, { method: "POST",
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
    $("#ref-modal").classList.add("hidden");
    refView.z = 1; refView.tx = refView.ty = 0; refViewedMs = 0; refOpenedAt = null; attention = "canvas";
    if (allowRef) {
      const src = ref.file || `/static/refs/${ref.id}.png`;
      $("#ref-img").src = src; $("#ref-thumb-img").src = src;
      // always：缩略图一直在右栏里；on_demand：只有一颗钮，画面要他自己点开
      $("#refpanel").classList.toggle("peek", ref.mode !== "always");
      applyRefView();
      // presented by the task, as distinct from the child choosing to open it
      logEvent(EV.REFERENCE_SHOW, { reference_id: ref.id, mode: ref.mode,
        placeholder: !!(q.stimulus && q.stimulus.placeholder), task_id: q.id });
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

  /** 大图的框按图片的长宽比撑到 86vw × 74vh 里最大的那个尺寸。
   *  框和图严丝合缝，applyRefView 的平移边界才是对的（和画布 viewport 同一个道理）。 */
  function sizeRefStage() {
    const vp = $("#ref-viewport"), img = $("#ref-img");
    const nw = img.naturalWidth || 4, nh = img.naturalHeight || 3;
    const maxW = innerWidth * 0.86, maxH = innerHeight * 0.66;   // 卡里还有工具栏和内衬
    const w = Math.min(maxW, maxH * nw / nh);
    vp.style.width = Math.round(w) + "px"; vp.style.height = Math.round(w * nh / nw) + "px";
  }
  function toggleRef(open) {
    const modal = $("#ref-modal"), willOpen = open !== undefined ? open : modal.classList.contains("hidden");
    modal.classList.toggle("hidden", !willOpen);
    const now = elapsed();
    if (willOpen) {
      refOpenedAt = now;
      logEvent(EV.REFERENCE_OPEN, { reference_id: refId(), task_id: state.quest && state.quest.id });
      const img = $("#ref-img");
      if (img.complete && img.naturalWidth) { sizeRefStage(); applyRefView(); }
      else img.onload = () => { sizeRefStage(); applyRefView(); };
      noteAttention("reference");
    } else {
      const dur = refOpenedAt != null ? Math.round(now - refOpenedAt) : null;
      if (dur != null) refViewedMs += dur;
      refOpenedAt = null;
      noteAttention("canvas");
      logEvent(EV.REFERENCE_CLOSE, { reference_id: refId(), task_id: state.quest && state.quest.id,
        view_duration_ms: dur, viewed_total_ms: refViewedMs, zoom: R(refView.z, 3) });
    }
  }
  $("#btn-ref-toggle").onclick = () => toggleRef(true);
  $("#btn-ref-close").onclick = () => toggleRef(false);
  $("#ref-modal").onclick = (e) => { if (e.target === $("#ref-modal")) toggleRef(false); };
  addEventListener("resize", () => { if (!$("#ref-modal").classList.contains("hidden")) { sizeRefStage(); applyRefView(); } });

  (function wireReference() {
    const vp = $("#ref-viewport");
    if (!vp) return;
    vp.addEventListener("wheel", (e) => {
      e.preventDefault();
      const r = vp.getBoundingClientRect();
      refZoomAt(refView.z * Math.pow(1.0015, -e.deltaY), e.clientX - r.left, e.clientY - r.top, "wheel");
    }, { passive: false });
    // 第二根手指落下就是捏合：两指距离的比值直接当缩放倍率，焦点在两指中间
    const fingers = new Map(); let pinch = null;
    vp.addEventListener("pointerdown", (e) => {
      vp.setPointerCapture(e.pointerId);
      if (e.pointerType === "touch") {
        fingers.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (fingers.size === 2) {
          const [a, b] = [...fingers.values()];
          pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), z: refView.z };
          refDrag = null; vp.classList.remove("dragging");
          return;
        }
      }
      refDrag = { id: e.pointerId, x: e.clientX, y: e.clientY, t0: elapsed(),
                  from: [Math.round(refView.tx), Math.round(refView.ty)], moved: false };
      vp.classList.add("dragging");
    });
    vp.addEventListener("pointermove", (e) => {
      if (e.pointerType === "touch" && fingers.has(e.pointerId)) {
        fingers.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (pinch && fingers.size === 2) {
          const [a, b] = [...fingers.values()], r = vp.getBoundingClientRect();
          const d = Math.hypot(a.x - b.x, a.y - b.y);
          refZoomAt(pinch.z * d / pinch.d, (a.x + b.x) / 2 - r.left, (a.y + b.y) / 2 - r.top, "pinch");
          return;
        }
      }
      if (!refDrag || e.pointerId !== refDrag.id) return;
      refView.tx += e.clientX - refDrag.x; refView.ty += e.clientY - refDrag.y;
      refDrag.x = e.clientX; refDrag.y = e.clientY; refDrag.moved = true;
      applyRefView();
    });
    const endRefDrag = (e) => {
      if (e && e.pointerType === "touch") { fingers.delete(e.pointerId); if (fingers.size < 2) pinch = null; }
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

    const doneRows2 = (state.allSessions || []).filter(r => r.status === "done");
    const doneFam = new Set(doneRows2.map(r => familyOf(r.task_id)).filter(Boolean));
    // 去过的地方挂**自己画的那张画**当地标：服务端按时间倒序给，所以第一张就是最近的。
    // 这是这张地图上唯一不需要美术资源、而且只有这个 app 才有的素材——
    // 一排一模一样的图标谁都做得出来，十扇开着自己画的窗做不到。
    const shotOf = {};
    doneRows2.forEach(r => {
      const f = familyOf(r.task_id || r.quest_id);
      if (f && !shotOf[f]) shotOf[f] = r.session_id;
    });
    const spots = mapSpots(cards.length);
    let nextMarked = false, nDone = 0, nextCard = null;
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
      const glyphMark = glyph(fam, "currentColor", 34) || `<span class="qc-icon">${c.icon || ""}</span>`;
      const shot = !c.locked && shotOf[fam];
      // 画没加载出来（撤回过、还没传上去）就退回那枚字形，别留一个洞
      const mark = shot
        ? `<img class="node-shot" src="${FILES}/${shot}/after.png" alt="" loading="lazy"
             onerror="this.closest('.node-btn').classList.remove('has-shot');this.remove()">`
        : c.locked ? icon("lock", 30) : glyphMark;
      el.innerHTML =
        (isNext ? `<svg class="sprite node-here" viewBox="0 0 200 200">${spriteInner(buddyColor(), "normal")}</svg>` : "")
        + `<div class="node-btn${shot ? " has-shot" : ""}">${mark}`
        // 挂着自己画的画的时候不用再盖一颗星：那张画本身就是「来过」
        + (done && !shot ? `<span class="node-star">${icon("star", 14)}</span>` : "")
        + `</div><h3>${c.title}</h3>`
        + `<div class="node-sub">${c.locked ? "稍后解锁" : c.kind}</div>`;
      if (!c.locked) el.onclick = () => {
        const q = c.task || randomForm(c.family);
        if (q) chooseQuest(q);
      };
      if (isNext) nextCard = c;
      grid.appendChild(el);
    });
    paintToday(nextCard, nDone, cards.length);
    paintMapPath();
  }

  /** 十个地方之间那条小路。
   *
   *  按**渲染之后各个钮的真实位置**算，不按布局的那张坐标表——宽屏是一张
   *  绝对定位的图，窄屏是交错的两列，两套布局共用这一段代码。
   *  地图藏着的时候量出来全是 0，所以 `show("quest")` 里还会再画一次。
   *
   *  它不带箭头、不编号、粗细也不变：家族之间没有先后，这条路说的是
   *  「这十个地方连在一起」，不是「按这个顺序走」。 */
  function paintMapPath() {
    const map = $("#quest-grid"), svg = $("#map-path");
    if (!map || !svg) return;
    const nodes = [...map.querySelectorAll(".quest-card .node-btn")];
    const mb = map.getBoundingClientRect();
    if (nodes.length < 2 || !mb.width || !mb.height) { svg.innerHTML = ""; return; }
    const pts = nodes.map(n => {
      const r = n.getBoundingClientRect();
      return [r.left + r.width / 2 - mb.left, r.top + r.height / 2 - mb.top];
    });
    svg.setAttribute("viewBox", `0 0 ${Math.round(mb.width)} ${Math.round(mb.height)}`);
    svg.innerHTML = `<path d="${smoothPath(pts)}"/>`;
  }
  /** 一条穿过所有点的平滑曲线（Catmull-Rom 折成三次贝塞尔）。
   *  直接连直线的话十个点会连成一张折线图；这条要像一条散步道。 */
  function smoothPath(pts) {
    if (pts.length < 2) return "";
    const d = [`M ${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`];
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2;
      const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
      const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
      d.push(`C ${c1[0].toFixed(1)} ${c1[1].toFixed(1)}, ${c2[0].toFixed(1)} ${c2[1].toFixed(1)},`
        + ` ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`);
    }
    return d.join(" ");
  }

  /** 「今天从这儿开始」——地图上那个默认入口。
   *
   *  十个家族一样大、一样亮地平铺着，孩子得一次评估十个陌生的名字才敢下手。
   *  这张卡不替他决定（十个仍然全开着，下面那片地图一个没少），它做的是
   *  **让「不想决定」也能开始**：彩点站在这儿，说清楚今天画什么，一个按钮进去。
   *  走完一轮之后它会变成下一个没走过的家族；全走完了就收起来，
   *  那时候孩子已经认识这十个地方了，不需要人再领路。 */
  /** 地图顶上那一条。**一条，不是一张海报**。
   *
   *  它只回答一个问题：「不想挑的话，从哪儿开始」。所以上面不再有
   *  「8 种玩法」（那是个数量，不是给孩子的话——地图上的同一行字早就删了，
   *  这儿是漏网的那份），进度也并了进来，中间那条说明灰带整条去掉。
   *  十个地方都走过之后它不消失，换句话继续站在那儿：整块消失会让人
   *  以为这一屏坏了。 */
  function paintToday(card, nDone, nTotal) {
    const box = $("#today"); if (!box) return;
    const all = !card && nTotal > 0 && nDone >= nTotal;
    if (!card && !all) { box.classList.add("hidden"); box.innerHTML = ""; return; }
    const c = (card && card.color) || buddyColor();
    box.style.setProperty("--tc-l", mixHex(c, 14, "#fff"));   // 14% 家族色兑白，一层淡底不是一块色卡
    box.style.setProperty("--tc-d", mixHex(c, 72, "#000"));
    // 这张卡上不写小字（原来有一行「从这儿开始 · 走过 n/10 关」）：精灵、家族名、按钮，够了。
    // 走过几关，地图上的圆钮亮着就是答案。
    box.innerHTML =
      `<svg class="sprite t-sprite" viewBox="0 0 200 200">${spriteInner(buddyColor(), all ? "happy" : "normal")}</svg>`
      + `<div class="t-body">`
      +   `<div class="t-title">${all ? "再挑一个" : card.title}</div>`
      + `</div>`
      + `<div class="t-go"><button class="primary big" id="btn-today">`
      +   `${all ? "随便一个" : "开始画"}${icon("arrowRight", 17)}</button></div>`;
    box.classList.remove("hidden");
    $("#btn-today").onclick = () => {
      const q = card ? (card.task || randomForm(card.family))
        : randomForm(((state.families || [])[Math.floor(Math.random() * (state.families || []).length)] || {}).id);
      if (q) chooseQuest(q);
    };
  }

  /** One child-facing line per family — never the research goal. */
  const FAMILY_BLURB = {
    M0: "画什么由你定。",
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
  // ---------- 左侧导航栏：收起 / 展开 ----------
  // 上一轮我反对过做这个，理由是「它在创作流程里本来就已经收起来了」。
  // 那条现在只对了一半：字号调到 135% 之后，这一栏要装下「KidsArtQuest」
  // 得比原来宽不少，而它在四块 tab 界面上是一直占着的。能收起来，
  // 展开时才敢给够宽度。收起的状态记在这台设备上。
  const RAIL_KEY = "artquest.rail_off";
  function paintRail() {
    const off = document.body.classList.contains("rail-off");
    const b = $("#btn-rail");
    if (b) { b.title = off ? "展开这一栏" : "收起这一栏"; b.setAttribute("aria-label", b.title); }
  }
  try { document.body.classList.toggle("rail-off", localStorage.getItem(RAIL_KEY) === "1"); } catch (e) { /* 无所谓 */ }
  if ($("#btn-rail")) $("#btn-rail").onclick = () => {
    const off = document.body.classList.toggle("rail-off");
    try { off ? localStorage.setItem(RAIL_KEY, "1") : localStorage.removeItem(RAIL_KEY); } catch (e) { /* 无所谓 */ }
    paintRail();
    scheduleFit();      // 栏宽变了，画布能用的地方也变了
  };
  paintRail();

  // ---------- 备用创作名额（票）----------
  // 有网的时候把设备上的票补满，断网时才有得花。一张票 = 服务端发的
  // session_id + 冻好的 condition；设备从不自己编 id，理由见 README「离线创作」。
  const TICKET_TARGET = 3;
  async function topUpTickets() {
    if (!navigator.onLine) return;
    try {
      if (!(await ArtLog.ready())) return;               // 无痕模式没有 IndexedDB，就不假装能离线
      const have = await ArtLog.countTickets();
      if (have >= TICKET_TARGET) return;
      const r = await api(`${API}/tickets`, { method: "POST", body: JSON.stringify({
        n: TICKET_TARGET - have,
        participant: { anon_id: state.anonId, participant_id: savedPid(), account_id: accountId(),
                       label: "", buddy_name: state.buddyName },
        study: state.study ? { active: !!state.study.active, study_id: state.study.study_id,
                               group: state.study.group || "" } : {},
      }) });
      await ArtLog.saveTickets(r.tickets || []);
    } catch (e) { /* 领不到票只是不能离线开新的，不该挡住任何事 */ }
  }
  addEventListener("online", () => { topUpTickets(); ArtLog.flush(); });

  async function init() {
    state.cfg = await api(`${API}/config`); state.quests = await api(`${API}/quests`);
    state.families = await api(`${API}/families`);
    state.anonId = anonId();
    loadBuddyName(); paintBuddyName();
    // 账号要在取任何「我的」数据之前问清楚：画廊、地图上的星都按它来筛
    await loadAccount();
    $("#backend-badge").textContent = `${state.cfg.scorer} · ${state.cfg.feedback}` + (state.cfg.claude_available ? "" : "（离线）");
    // 设备上跑的是哪一版外壳。iPad 上「到底更新了没有」以前只能靠猜——
    // 这一行就是答案：和电脑上 `curl .../api/config` 里的 shell 对一下就知道。
    const sb = $("#shell-badge");
    if (sb) sb.textContent = (state.cfg.shell || "—") + (NATIVE ? ` · app ${NATIVE.version || ""}`.trimEnd() : "");
    // 「全部记录」= 这台设备 / 这个账号自己的那些。全服的列表要研究员令牌，不是界面上的一个链接。
    const ex = $("#export-link"); if (ex) ex.href = `${API}/sessions?${whoQuery()}`;
    await setupStudy();
    applyCondition();
    $("#participant").value = savedPid();
    renderQuests();
    const chips = $("#emotion-chips"); chips.innerHTML = "";
    // 每个心情配一个表情：孩子扫一眼表情比读两个字快，存下来的仍然是那两个字。
    // （这个 app 别处不用 emoji，心情这一排是用户拍板的唯一例外：表情比字快。）
    const EMOJI = { "开心": "😊", "平静": "😌", "兴奋": "🤩", "好奇": "🤔", "期待": "😃",
                    "紧张": "😬", "难过": "😢", "生气": "😠", "累了": "😴", "难说": "😶" };
    state.cfg.emotions.forEach(em => {
      const b = document.createElement("button");
      b.innerHTML = (EMOJI[em] ? `<span class="emo">${EMOJI[em]}</span>` : "") + `<span>${em}</span>`;
      // 不是必选：再点一下就取消
      b.onclick = () => {
        state.emotion = state.emotion === em ? "" : em;
        chips.querySelectorAll("button").forEach(x => x.classList.toggle("active", x === b && !!state.emotion));
      };
      chips.appendChild(b);
    });
    await loadCollection();          // 地图要知道哪几关走过了
    renderQuests();
    topUpTickets();                  // 不 await：领票慢也不该让界面等着
    try { state.entered = sessionStorage.getItem("artquest.entered") === "1"; } catch (e) { /* 无所谓 */ }
    if (state.entered || state.condition.ui === "quiet") { show("quest"); }
    else { await renderWorld(); show("world"); }
    if (!guideSeen() && state.condition.ui !== "quiet") startTour();
    else checkFeatured();
  }
  function chooseQuest(q) {
    state.quest = q;
    // 任务自带参考图、而且是「一直可见」那种的，心愿屏的任务卡里就先给他看：
    // 写心愿之前知道要照着什么画。on_demand 的不放——画面要等他自己点开。
    const ref = q.reference, showRef = ref && state.condition.reference_allowed && ref.mode === "always";
    const refImg = showRef ? `<img class="intent-ref" src="${ref.file || `/static/refs/${ref.id}.png`}" alt="参考图">` : "";
    $("#intent-quest-card").innerHTML = `<div class="type">${q.type}</div><h3 id="intent-quest-title">${q.title}</h3><p id="intent-quest-prompt">${q.prompt}</p>${refImg}`;
    paintIntentIdentity();
    show("intent");
  }

  /** 画之前这一屏上的「我是谁」。
   *
   *  以前这儿摆着一个「给自己起个代号（别用真名）」的输入框，每个孩子都看得见。
   *  那是**研究员的把手**——代号由研究员分配（`?pid=P007` 带进来），
   *  和这个项目里其他把手（后端名、本机代号、导出 JSON）是一类东西，
   *  它们该折起来，不该摆在孩子的创作流程里。现在它只在实验模式下出现。
   *
   *  孩子自己的身份是**账号**：注册过就跟着人走，没注册也照样画——所以这里
   *  只留一句可选的提示，而且点它就地注册，不用离开这一屏、不用重挑任务。 */
  function paintIntentIdentity() {
    const box = $("#pidbox");
    if (box) box.classList.toggle("hidden", !state.study);
    // 「起个名字」的提示不再出现在这一屏：起名在「我的」里，画画的入口只问两件事。
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
        await api(`${API}/sessions/${state.sessionId}/submit`, { method: "POST",
          body: JSON.stringify({ image: canvas.toDataURL("image/png"), elapsed_ms: elapsed(),
                                 phase: "before", pending }) });
        await api(`${API}/sessions/${state.sessionId}/finalize`, { method: "POST",
          body: JSON.stringify({ elapsed_ms: elapsed(), pending }) });
      } else {
        // the strokes are kept, the session is marked — changing your mind is
        // process data, and a silently deleted session makes a task_id lie
        await api(`${API}/sessions/${state.sessionId}/abandon`, { method: "POST",
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
    if (e.key !== "Escape") return;
    [leaveModal, clearModal, pkModal].forEach(m => m.classList.add("hidden"));
    if (!$("#ref-modal").classList.contains("hidden")) toggleRef(false);
    if (eyedrop) setEyedrop(false);
  });
  $("#btn-start-draw").onclick = async () => {
    const intent = { emotion: state.emotion || "", text: $("#intent-text").value.trim() };   // 心情不是必选
    const pid = $("#participant").value.trim();
    if (pid && pid !== savedPid()) setPid(pid);
    const body = {
      quest_id: state.quest.id, intent,
      participant: { anon_id: state.anonId, participant_id: savedPid(), account_id: accountId(),
                     label: "", buddy_name: state.buddyName },
      condition: state.condition, device: deviceInfo(), canvas: canvasGeom(),
      study: state.study ? { active: !!state.study.active, study_id: state.study.study_id, group: state.study.group || "",
        order_index: state.seqIdx, sequence_id: (state.study.sequence || []).join(">") } : {},
    };
    // 联网就照旧：服务端当场发 id、冻条件。连不上就花一张**预领的票**——
    // 那张票上的 id 和条件也是服务端定的，只是定得早一点。设备从不自己编 id。
    let r = null, ticket = null;
    try {
      r = await api(`${API}/sessions`, { method: "POST", body: JSON.stringify(body) });
    } catch (e) {
      ticket = await ArtLog.takeTicket(state.quest.id).catch(() => null);
      if (!ticket) {
        alert("连不上网，备用名额也用完了。\n连上再试——画过的都还在。");
        return;
      }
      body.session_id = ticket.session_id;
      await ArtLog.defer("create", ticket.session_id, body);
      r = { session_id: ticket.session_id, session: { condition: ticket.condition || {} }, personalization: {} };
    }
    state.sessionId = r.session_id; state.phase = "before"; state.before = null; state.revised = null;
    state.feedback = null; state.offlineSession = !!ticket;
    renderHistory(r.personalization);
    state.condition = { ...state.condition, ...(r.session.condition || {}) };  // the server froze it; mirror it back
    resetCanvas(); state.startedAt = Date.now(); state.dirtySinceSnapshot = false;
    strokeCount = 0; state.lastActivity = 0; state.idle = false;
    applyTool("pencil");                 // 上一张用橡皮收的尾，不该带进下一张
    resetView(null); applyCondition(); syncName();   // a fresh canvas starts at 100 %, pen in hand
    await ArtLog.start(state.sessionId);
    applyTask(state.quest);
    $("#draw-quest-card").innerHTML = `<div class="type">${state.quest.type}</div><h3>${state.quest.title}</h3><p>${state.quest.prompt}</p>`;
    assistReset(intent);
    $("#revision-banner").classList.add("hidden"); $("#btn-submit").classList.remove("hidden"); $("#snap-info").textContent = "";
    // 不承诺走不到的站：条件里没有 AI 反馈时，这颗按钮后面根本没有「支招」那一步。
    // 「画好了」什么都不许诺，两臂用同一句；有没有反馈是后面那一屏的事。
    $("#btn-submit").innerHTML = "画好了" + icon("arrowRight", 18);
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
      const r = await api(`${API}/sessions/${state.sessionId}/submit`, { method: "POST", body: JSON.stringify({ image, elapsed_ms: elapsed(), phase: "before", pending }) });
      state.before = { image, scores: r.scores };
      if (!r.feedback) {
        // the frozen condition says this session carries no feedback, so there
        // is nothing to read and nothing to revise in response to
        const done = await api(`${API}/sessions/${state.sessionId}/finalize`,
          { method: "POST", body: JSON.stringify({ elapsed_ms: elapsed(), pending }) });
        overlay(null);
        return endSession(done.session, image, image, null);
      }
      $("#result-img").src = image; renderScores($("#scores"), r.scores, null); $("#score-summary").textContent = r.scores.summary || "";
      const fbSp = $("#fb-sprite"); if (fbSp) fbSp.innerHTML = spriteInner(buddyColor(), "happy");
      // remember which feedback this is, so the revision can be attributed to it
      state.feedback = { id: r.feedback.feedback_id || "", text: r.feedback.text || "", shown_ms: elapsed() };
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
    assistShowFeedback(fb.text || "");
    $("#btn-submit").classList.add("hidden"); $("#revision-banner").classList.remove("hidden"); startTimers(); show("draw");
  };
  $("#btn-skip-revise").onclick = async () => {
    dismissFeedback("skip");
    overlay("正在保存……");
    const pending = await flushLog();
    const r = await api(`${API}/sessions/${state.sessionId}/finalize`, { method: "POST", body: JSON.stringify({ elapsed_ms: elapsed(), pending }) });
    endSession(r.session, state.before.image, state.before.image, null); overlay(null);
  };
  $("#btn-submit-after").onclick = async () => {
    overlay("正在比较修改前后……"); stopTimers();
    const image = canvas.toDataURL("image/png");
    try {
      const pending = await flushLog();
      const r = await api(`${API}/sessions/${state.sessionId}/submit`, { method: "POST", body: JSON.stringify({ image, elapsed_ms: elapsed(), phase: "after", pending }) });
      endSession(r.session, state.before.image, image, r.comparison);
    } catch (e) { alert("提交失败：" + e.message); startTimers(); }
    overlay(null);
  };
  // ---------- self-report ----------
  const SURVEY = [
    { key: "difficulty", q: "难不难？", lo: "很简单", hi: "很难" },
    { key: "confidence", q: "画得怎么样？", lo: "还差点", hi: "挺满意" },
    { key: "enjoyment", q: "开心吗？", lo: "一般", hi: "很开心" },
  ];
  const answers = {};
  function renderSurvey() {
    SURVEY.forEach(i => delete answers[i.key]);
    // a closed set makes the answer comparable across tasks and children; the
    // text box stays beside it, because a list that fits nobody is worse
    state.hardestChoice = null;
    const chips = $("#survey-hardest-choices"); chips.innerHTML = "";
    const paintHard = () => chips.querySelectorAll("button").forEach(x =>
      x.classList.toggle("active", x.dataset.key === state.hardestChoice));
    (state.cfg.hardest_parts || []).forEach(opt => {
      if (opt.key === "other") {
        // 「其他」不是一颗钮，就是那格输入框：写了字 = 选了其他，清空 = 取消
        const inp = document.createElement("input");
        inp.type = "text"; inp.id = "survey-hardest"; inp.placeholder = opt.label + "…"; inp.autocomplete = "off";
        inp.oninput = () => { state.hardestChoice = inp.value.trim() ? "other" : (state.hardestChoice === "other" ? null : state.hardestChoice); paintHard(); };
        chips.appendChild(inp); return;
      }
      const b = document.createElement("button");
      b.textContent = opt.label; b.dataset.key = opt.key;
      b.onclick = () => {
        state.hardestChoice = state.hardestChoice === opt.key ? null : opt.key;
        if (state.hardestChoice !== "other") $("#survey-hardest").value = "";
        paintHard();
      };
      chips.appendChild(b);
    });
    const sp = $("#survey-sprite"); if (sp) sp.innerHTML = spriteInner(buddyColor(), "happy");
    $("#survey").innerHTML = SURVEY.map(item => `<div class="sq" data-key="${item.key}">
      <div class="sq-q">${item.q}</div>
      <div class="sq-scale"><span class="sq-end">${item.lo}</span>${[1, 2, 3, 4, 5].map(v => `<button data-v="${v}">${v}</button>`).join("")}<span class="sq-end">${item.hi}</span></div></div>`).join("");
    $("#survey").querySelectorAll(".sq").forEach(row => row.querySelectorAll("button").forEach(b => b.onclick = () => {
      answers[row.dataset.key] = +b.dataset.v;
      row.querySelectorAll("button").forEach(x => x.classList.toggle("active", x === b));
    }));
  }
  async function sendSurvey(skip) {
    const body = skip ? { t_ms: elapsed() } : { ...answers,
      hardest_part_choice: state.hardestChoice || null,
      hardest_part: $("#survey-hardest").value.trim(), t_ms: elapsed() };
    try { await api(`${API}/sessions/${state.sessionId}/questionnaire`, { method: "POST", body: JSON.stringify(body) }); }
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
      : (comparison ? comparison.text : "下次照我的话改一小处，就能点亮进化大师。");
    // 「这一关练的是」那张卡不再放在结算页：能力图上练的那几项本来就是橙色高亮的，
    // 再摆一张卡说一遍是重复。（伙伴那页的成长面板照旧用它。）
    renderBadges(session);
    if (earnedNow(session).length) native("haptic", { style: "success" });   // 章亮了，手里也知道
    reportBadges(session).then(() => renderBadges(session));   // rarity needs this session counted
    // 「存进相册」只在 app 里有：浏览器里长按图片就能存，按钮是多的。
    // 一颗钮只做一件事：直接存进相册，不弹系统分享面板——那张面板上一排陌生的图标，
    // 八到十四岁的孩子不知道该点哪个。存好了钮自己变成「存好了」，存不上说一句人话。
    const sv = $("#btn-save");
    if (sv) {
      sv.classList.toggle("hidden", !NATIVE);
      sv.disabled = false;
      sv.innerHTML = `${icon("download", 17)}存进相册`;
      sv.onclick = () => { sv.disabled = true; sv.textContent = "正在存…"; native("save", { image: afterImg }); };
    }
    renderPeers(session);
    // What the child is shown of their own growth is its own condition, separate
    // from whether this artwork got feedback: a no-intervention arm can still
    // let a child see their cumulative practice without being told about *this*
    // drawing.
    const showScores = (state.condition.growth_display || "full") === "full";
    const scores = $("#final-scores");
    scores.classList.toggle("hidden", !showScores);
    if (showScores) renderScores(scores, session.after.scores, session.before.scores);
    // 这一行是给研究员看的，不是给孩子看的：session id、事件条数、盘上的路径。
    // 和「我的」页那批把手同一个道理——实验模式下才露出来。
    const fm = $("#final-meta");
    fm.classList.toggle("hidden", !state.study);
    if (state.study) fm.textContent = `Session ${session.session_id} · 过程截图 ${session.snapshots.length} 张`
      + ` · 事件 ${session.events.length} 条 · 数据在 data/sessions/${session.session_id}/`;
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

  // -- 后来那批「奇遇」徽章要的信号 --------------------------------------
  // 阈值类的条件（5 种颜色、30 笔）能点亮，但点亮的时候没人惊讶。
  // 下面这些看的是画法的**形状**（只用黑白、擦得比画得多、全是小点）
  // 和**时机**（半夜画的、同一关又来一次），点亮的那一下才像被发现。
  const hourOf = (s) => {
    const t = new Date(s.created_at || (s.times || {}).created_at || Date.now());
    return isNaN(t) ? -1 : t.getHours();          // 本地时间：孩子经历的那个「几点」
  };
  const isGrey = (hex) => {
    const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || ""));
    if (!m) return false;
    const n = parseInt(m[1], 16), r = n >> 16, g = (n >> 8) & 255, b = n & 255;
    return Math.max(r, g, b) - Math.min(r, g, b) <= 18;   // 三分量挨得很近 = 灰阶
  };
  const strokeSizes = (s) => payloads(s, ["STROKE_END"], "size").map(Number).filter(n => n > 0);
  const strokePoints = (s) => payloads(s, ["STROKE_END"], "n").map(Number).filter(n => n > 0);
  const strokeTimes = (s) => evOf(s, ["STROKE_END"]).map(e => Number(e.t_ms) || 0);
  const zoomMin = (s) => Math.min(1, ...payloads(s, ["ZOOM"], "to").map(Number));
  const paletteHits = (s) => [...colorsUsed(s)].filter(c => PALETTE.includes(c)).length;
  const dayOf = (iso) => (iso || "").slice(0, 10);
  const doneDays = () => [...new Set(doneRows().map(r => dayOf(r.created_at)).filter(Boolean))].sort();
  const backToBackDays = () => {
    const d = doneDays();
    return d.some((x, i) => i > 0 && (new Date(x) - new Date(d[i - 1])) === 86400000);
  };
  const twoInOneDay = () => {
    const c = {};
    doneRows().forEach(r => { const k = dayOf(r.created_at); if (k) c[k] = (c[k] || 0) + 1; });
    return Math.max(0, ...Object.values(c)) >= 2;
  };
  const timesAtTask = (taskId) => doneRows().filter(r => (r.task_id || r.quest_id) === taskId).length;
  const onTheWall = () => doneRows().some(r => (r.featured || {}).state === "accepted");

  const ALL_BADGES = [
    // -- 开始 --
    // 第一枚徽章，一打开就有。它**不读任何东西**——不读过程也不读质量，
    // 只是一句「你来了」。所以它不会变成对孩子的判决，而墙上从第一天起
    // 就有东西可看：空墙加上一句「画一幅试试」，读起来像还没及格。
    // 说明写的是事实（你和彩点认识了），不是夸奖。
    { g: "开始", icon: "sprout", name: "加入家庭", desc: "你和彩点认识了",
      welcome: true, earned: () => true },
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

    // ================= 奇遇 =================
    // 这一组的条件都不是「做够多少」，而是「做了件特别的事」。
    // 它们不写在任何地方，只能自己撞上——所以墙上那张「?」卡说的是实话。
    // 白卷的彩蛋：一笔没画也交了，那就只给这一枚，别的都不给（见 earnedNow）。
    { g: "奇遇", icon: "image", name: "一片空白", desc: "交了一张什么都没画的画",
      earned: s => nStrokes(s) === 0, blank: true },
    { g: "奇遇", icon: "moon", name: "夜猫子", desc: "夜里九点以后还在画",
      earned: s => { const h = hourOf(s); return h >= 21 || (h >= 0 && h < 4); } },
    { g: "奇遇", icon: "sun", name: "早起的鸟", desc: "太阳刚出来就开画了",
      earned: s => { const h = hourOf(s); return h >= 4 && h < 7; } },
    { g: "奇遇", icon: "contrast", name: "黑白世界", desc: "整幅画只用了黑白灰",
      earned: s => { const c = [...colorsUsed(s)]; return c.length > 0 && nStrokes(s) >= 12 && c.every(isGrey); } },
    { g: "奇遇", icon: "rainbow", name: "把调色板搬空", desc: "调色板上的颜色用了 10 种以上",
      earned: s => paletteHits(s) >= 10 },
    { g: "奇遇", icon: "eraser", name: "橡皮朋友", desc: "擦的次数比留下的笔还多",
      earned: s => { const e = evOf(s, ["ERASE"]).length; return e >= 8 && e > nStrokes(s); } },
    { g: "奇遇", icon: "ghost", name: "幽灵画家", desc: "两次推翻重来，最后还是画完了",
      earned: s => evOf(s, ["CLEAR"]).length >= 2 && nStrokes(s) >= 8 },
    { g: "奇遇", icon: "wave", name: "一笔到底", desc: "整幅画只有几笔，每一笔都很长",
      earned: s => { const n = nStrokes(s); const pts = strokePoints(s);
        return n > 0 && n <= 3 && Math.min(...pts) >= 150; } },
    { g: "奇遇", icon: "dense", name: "点点点", desc: "30 笔以上，每一笔都只是一小点",
      earned: s => { const pts = strokePoints(s);
        return pts.length >= 30 && Math.max(...pts) <= 12; } },
    { g: "奇遇", icon: "feather", name: "越画越轻", desc: "笔越换越细，收尾轻轻的",
      earned: s => { const z = strokeSizes(s);
        if (z.length < 10) return false;
        const head = z.slice(0, 5), tail = z.slice(-5);
        return Math.max(...tail) < Math.min(...head); } },
    { g: "奇遇", icon: "fire", name: "最后冲刺", desc: "结尾十笔一口气画完",
      earned: s => { const t = strokeTimes(s);
        return t.length >= 15 && (t[t.length - 1] - t[t.length - 10]) <= 30000; } },
    { g: "奇遇", icon: "target", name: "贴着画布看", desc: "放大到 6 倍还在画",
      earned: s => zoomMax(s) >= 6 },
    { g: "奇遇", icon: "compass", name: "退后一步", desc: "缩小到看得见整张画，再接着画",
      earned: s => zoomMin(s) <= 0.8 && nStrokes(s) >= 10 },
    { g: "奇遇", icon: "loop", name: "故地重游", desc: "同一个任务又画了一次",
      earned: s => timesAtTask(s.quest_id) >= 2 },
    { g: "奇遇", icon: "gift", name: "一天两张", desc: "同一天里画完了两幅",
      earned: () => twoInOneDay() },
    { g: "奇遇", icon: "fire", name: "连着两天", desc: "昨天画了，今天又来了",
      earned: () => backToBackDays() },
    { g: "奇遇", icon: "heart", name: "起了名字", desc: "给伙伴起了自己的名字",
      earned: () => !!state.buddyName },
    { g: "奇遇", icon: "key", name: "有名字的人", desc: "有了自己的名字和暗号，画跟着你走",
      earned: () => !!(state.account && state.account.account_id) },
    { g: "奇遇", icon: "people", name: "两处都画过", desc: "在两台设备上画过画",
      earned: () => !!(state.account && (state.account.devices || 0) >= 2) },
    { g: "奇遇", icon: "pin", name: "挂上了墙", desc: "有一幅画挂在大家的墙上",
      earned: () => onTheWall() },
    { g: "奇遇", icon: "crown", name: "满墙的画", desc: "画廊里攒够了 20 幅",
      earned: () => doneRows().length >= 20 },
  ];
  // 每组一个颜色，徽章不再是一片一样的黄
  const BADGE_COLORS = { "色彩与工具": "#f79433", "过程与节奏": "#4db8ef",
                         "观察与细节": "#6cc24a", "探索与坚持": "#b98cf0",
                         "奇遇": "#f2706e", "开始": "#f5c243" };
  // 规则集变了就换版本号：旧 session 上报的那批仍按旧规则算，
  // 已经拿到手的徽章不会因为后来加了新规则而被收回去。
  const BADGE_RULES_VERSION = "badges/3";   // 3：白卷什么都不点亮；结算页只报这次新点亮的

  /** Tell the server what this session lit, so rarity can be counted.
   *  Stored with the rule-set version: tightening a rule later must not take a
   *  badge off a child who already had it. */
  /** 这一局点亮了哪些：白卷一枚都不给——「夜猫子」「起了名字」这类看状态不看画的章，
   *  不该被一张空画布领走。 */
  function earnedNow(session) {
    const pool = badgePool(session);
    if (!nStrokes(session)) return pool.filter(b => b.blank);      // 白卷只有那一枚彩蛋
    return pool.filter(b => !b.blank && (() => { try { return !!b.earned(session); } catch (e) { return false; } })());
  }
  /** 这一局之前就已经亮着的：别的 session 上报过的名单。结算页只报**新**点亮的，
   *  不然「常来的人」「有名字的人」这些跨作品的章每一局都会再报一遍。 */
  /** 这枚章以前亮过几次（别的 session 上报过的次数）。 */
  let curSessionId = null;
  function timesLit(name) {
    return (state.allSessions || []).filter(r => r.session_id !== curSessionId)
      .filter(r => ((r.badges || {}).earned || []).includes(name)).length;
  }
  function litBefore(session) {
    curSessionId = session.session_id;
    const lit = new Set();
    (state.allSessions || []).filter(r => r.session_id !== session.session_id)
      .forEach(r => ((r.badges || {}).earned || []).forEach(n => lit.add(n)));
    return lit;
  }
  async function reportBadges(session) {
    const pool = badgePool(session);
    const earned = earnedNow(session);
    try {
      await api(`${API}/sessions/${session.session_id}/badges`, { method: "POST", body: JSON.stringify({
        earned: earned.map(b => b.name), offered: pool.map(b => b.name),
        version: BADGE_RULES_VERSION }) });
      state.rarity = await api(`${API}/achievements`);
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
    try { data = await api(`${API}/gallery/featured?k=8`); } catch (e) { el.classList.add("hidden"); return; }
    const cards = (data && data.examples) || [];
    // 空墙也说一句。这面墙需要两个人点头（老师挑 + 本人答应），
    // 整块消失会让人以为功能坏了，而它只是还没有人挑过。
    el.classList.remove("hidden");
    $("#wall-empty").classList.toggle("hidden", !!cards.length);
    $("#wall-count").textContent = cards.length ? `${cards.length} 张` : "";
    $("#wall-grid").innerHTML = cards.map(c => {
      const a = c.approach || {};
      const title = (state.quests.find(q => q.id === c.task_id) || {}).title || c.task_id;
      return `<figure class="peer">
        <div class="peer-shot"><img src="${fileUrl(c.image)}" alt="挂出来的画" loading="lazy"></div>
        <figcaption>
          <b>${escapeHtml(title)}</b>
          <div class="peer-chips"><span>${a.strokes} 笔</span><span>${a.colors || 1} 种颜色</span>
            <span>${a.minutes} 分钟</span>${a.zoomed ? "<span>放大看过</span>" : ""}</div>
          ${c.why ? `<p class="peer-why">${escapeHtml(c.why)}</p>` : ""}
          <div class="p-pin">${icon("pin", 13)}${c.curated ? "今天挂出来的" : "老师选的"}</div>
        </figcaption></figure>`;
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
      data = await api(`${API}/gallery/task/${encodeURIComponent(session.quest_id)}?exclude=${session.session_id}&k=3`);
    } catch (e) { el.classList.add("hidden"); return; }
    let cards = (data && data.examples) || [];
    try {
      const pinned = await api(`${API}/gallery/featured?task_id=${encodeURIComponent(session.quest_id)}&k=2`);
      // a pinned drawing may also be one of the diverse picks — show it once,
      // with the teacher's note rather than the process contrast
      const seen = new Set((pinned.examples || []).map(c => c.session_id));
      cards = (pinned.examples || []).concat(cards.filter(c => !seen.has(c.session_id))).slice(0, 4);
    } catch (e) { /* featured is optional */ }
    if (!cards.length) { el.classList.add("hidden"); return; }
    el.classList.remove("hidden");
    $("#peers-note").textContent = `${cards.length} 种做法`;
    $("#peer-grid").innerHTML = cards.map(c => {
      const a = c.approach || {};
      const how = [`${a.strokes} 笔`, `${a.colors || 1} 种颜色`, `${a.minutes} 分钟`,
                   a.zoomed ? "放大过" : null].filter(Boolean).join(" · ");
      return `<div class="peer">
        <img src="${fileUrl(c.image)}" alt="别人的作品" loading="lazy">
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
      + `<div class="tnote">${buddyName()}跟着长了一截。`
      + (na.length ? `这一关用不上「${na.map(k => (byKey[k] || {}).zh || k).join("、")}」。` : "")
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
   *  as a list of things they have failed to do.
   *
   *  剩下多少枚也**不说**。报个数听着无害，其实把发现变回了进度条：
   *  「还有 31 枚」是一张待办清单，孩子会开始数，而不是继续画。
   *  墙尾只留一张「?」——它说还有，但不说有多少。
   */
  const BADGE_ORDER = ["开始", "色彩与工具", "过程与节奏", "观察与细节", "探索与坚持", "奇遇"];
  function badgeGroupsHtml(pool, isOn, { newTag = false, mystery = false, count = false } = {}) {
    // 组的顺序是固定的，不跟着「谁先点亮」走：同一面墙每次打开都该长一个样，
    // 孩子才记得住自己的章排在哪儿。
    //
    // **组的名字不写出来。** 「开始」「色彩与工具」这些是给大人分类用的词，
    // 对着一墙章的孩子只是几行灰字；每枚章底下本来就有名字和说明。
    // 颜色已经把组分出来了（同一组一个色），不用再标一遍。
    const lit = pool.filter(isOn)
      .sort((a, b) => BADGE_ORDER.indexOf(a.g) - BADGE_ORDER.indexOf(b.g));
    const html = lit.map(b => {
      const c = BADGE_COLORS[b.g] || "#f79433";
      const style = `--bc:${c};--bc-l:${mixHex(c, 62, "#fff")};--bc-d:${mixHex(c, 66, "#000")}`;
      // Rarity is about the badge, not about you: "8 % of people have lit this"
      // gives the collecting feeling without comparing anyone's drawing.
      const st = ((state.rarity || {}).badges || {})[b.name];
      const pct = st && st.rarity !== null ? Math.round(st.rarity * 100) : null;
      const rare = pct !== null && pct <= 15;
      // 只有**真的少见**的那几枚才写一句。常见的也挂上百分比的话，
      // 每枚章底下都拖着一行数字，一面墙就读成了统计表。
      const line = !rare ? ""
        : `<div class="rarity">${pct <= 0 ? "还没有人点亮过" : `只有 ${pct}% 的人点亮过`}</div>`;
      const isNew = typeof newTag === "function" ? newTag(b) : !!newTag;
      // 角标写第几次：结算页是「以前的次数 + 这一次」，墙上是总次数（count）
      const n = count ? timesLit(b.name)
        : (typeof newTag === "function" && !isNew ? timesLit(b.name) + 1 : 0);
      return `<div class="badge on${isNew ? " new" : ""}${n > 1 ? " again" : ""}${b.evo ? " evo" : ""}${rare ? " rare" : ""}"${n > 1 ? ` data-n="${n}"` : ""}
        style="${style}" title="${b.desc}">
        <div class="b-ico">${icon(b.icon, 30)}</div><div class="b-name">${b.name}</div>
        <div class="b-desc">${b.desc}</div>${line}</div>`;
    }).join("");
    // 墙尾那一枚：说还有，不说有多少。一句话，不再多解释一行。
    const q = mystery ? `<div class="badge mystery">
      <div class="b-ico">${icon("question", 30)}</div>
      <div class="b-name">更多等你发现</div></div>` : "";
    return `<div class="badge-row">${html}${q}</div>`;
  }

  /** 徽章的说明不常驻：点一枚，贴着它浮出一句（名字、条件、亮了几次、稀有度）。 */
  function wireBadgePops(root) {
    root.querySelectorAll(".badge:not(.mystery)").forEach(bd => bd.onclick = (e) => {
      e.stopPropagation();
      const pop = $("#pop-badge"); if (!pop) return;
      const name = bd.querySelector(".b-name").textContent;
      if (popOpen === pop && pop.dataset.for === name) { closePop(); return; }
      pop.dataset.for = name;
      const n = +bd.dataset.n || 0;
      pop.innerHTML = `<b>${name}</b><p>${bd.title}</p>`
        + (n > 1 ? `<span class="muted small">亮了 ${n} 次</span>` : "")
        + (bd.querySelector(".rarity") ? `<span class="muted small">${bd.querySelector(".rarity").textContent}</span>` : "");
      openPop(pop, bd);
    });
  }

  function renderBadges(session) {
    const el = $("#badges"); if (!el) return;
    // A badge the condition makes unreachable is not shown as "not earned":
    // greying it out tells the child they missed something never on offer.
    const pool = badgePool();
    // 入门徽章不在结算页出现：它不是这一局做到的事，每次都挂个「新」上去
    // 就成了噪音，也冲淡了真正刚点亮的那几枚。
    // 这一局做到的都亮出来（一张认真画的画总该有几枚）；第一次亮的才挂「NEW」，
    // 以前亮过又做到的照样算——只有跨作品看状态的那几枚（起了名字、常来的人……）
    // 亮过一次就不再重复报。白卷照旧一枚都没有。
    const before = litBefore(session);
    const got = earnedNow(session).filter(b => !b.welcome && (b.earned.length > 0 || !before.has(b.name)));
    const gotSet = new Set(got);
    // 一行放六枚；多出来的先收着，一颗钮展开——一局点亮十几枚的时候卡不该撑成一面墙
    const FOLD_AT = 6;
    el.classList.toggle("folded", got.length > FOLD_AT);
    el.innerHTML = got.length
      ? badgeGroupsHtml(pool, b => gotSet.has(b), { newTag: b => !before.has(b.name) })
        + (got.length > FOLD_AT ? `<button class="ghost badge-more" id="btn-badge-more">还有 ${got.length - FOLD_AT} 枚，展开</button>` : "")
      : `<p class="badge-left">这次没点亮新的。换个画法再来一张。</p>`;
    wireBadgePops(el);
    $("#badges-count").textContent = got.length ? `点亮了 ${got.length} 枚` : "";
    const more = $("#btn-badge-more");
    if (more) more.onclick = () => { el.classList.remove("folded"); more.remove(); };
    if (got.length) {
      // one beat of delight, then back to breathing
      document.querySelectorAll("#view-final .sprite").forEach(el => {
        el.classList.remove("cheer"); void el.offsetWidth; el.classList.add("cheer");
      });
    }
  }

  /** 我点亮过哪些章。两个地方要用（徽章墙、「我的」小传），所以只算一次。
   *
   *  两个来源：**上报记录**（每次结算时存到服务器的那份名单，规则以后收紧
   *  也不会把拿到的收回去），加上**不挂在任何一次创作上**的那几枚——
   *  起了名字、有了账号、连着两天来、挂上了墙。后者只读当下的状态，
   *  随时算得出来，不然孩子得再画一张才看得见它们。 */
  function litBadges() {
    const lit = new Set();
    (state.allSessions || []).forEach(r => ((r.badges || {}).earned || []).forEach(n => lit.add(n)));
    ALL_BADGES.filter(b => b.earned.length === 0).forEach(b => {
      try { if (b.earned()) lit.add(b.name); } catch (e) { /* 算不出来就当没有 */ }
    });
    return lit;
  }

  /** 徽章墙：把每次结算时上报给服务器的徽章并起来。
   *  读的是那份上报记录本身，不重算——规则以后收紧，也不会把已经拿到的从孩子手上取走。 */
  async function renderBadgeWall() {
    const el = $("#badge-wall"); if (!el) return;
    // 每次都重新取：徽章是刚刚那一局才上报的，缓存里的名单一定是旧的
    try { state.allSessions = await mySessions(); } catch (e) { /* 离线就先空着 */ }
    const lit = litBadges();
    try { state.rarity = await api(`${API}/achievements`); } catch (e) { /* 稀有度是可选的 */ }
    // 墙上展示的是**已经点亮的**，所以不按当前任务过滤：
    // `badgePool()` 是给「这一局能拿到哪些」用的，拿它筛墙会让「对照高手」
    // 这种要参考图的徽章在没选任务时整枚消失。
    const pool = ALL_BADGES;
    const n = pool.filter(b => lit.has(b.name)).length;
    curSessionId = null;                      // 墙上数的是全部次数
    el.innerHTML = n ? badgeGroupsHtml(pool, b => lit.has(b.name), { mystery: true, count: true })
      : `<p class="badge-left">画一幅试试。徽章只看你怎么画，不看画得好不好。</p>`;
    wireBadgePops(el);
    $("#badge-wall-count").textContent = n ? `${n} 枚` : "";
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
        + `<title>${d.zh}${ph ? "（等模型来评）" : ""}</title></path>`;
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
          <span class="sval">${ph ? '<span class="wait">等模型来评</span>' : `<span class="st">${stars(s.score)}</span>${arrow}`}</span></div></div>`;
    }).join("");
    el.innerHTML = `<div class="ability-head">${icon("palette", 17)}这一幅，你长在这儿</div>`
      + roseChart(scores, baseline)
      // 九项的逐条细节默认收起来：宝藏这一屏要在一块 pad 上放得下，
      // 而且第一眼该是「你的画」和「这次练了什么」，不是一张九行的表。
      + `<details class="dim-fold"><summary>${icon("sliders", 15)}看看九项的细节</summary>`
      + `<div class="dim-notes">${notes}</div></details>`;
  }

  // ---------- 「我的」：画过的画 + 这台设备 ----------
  // A child (or their parent) opening this on a phone should see their own
  // drawings, not a research export. `2026-09-15T04:33:28.149+00:00`, `M8_R03`
  // and `before · after · json` are the same facts said in a language nobody
  // here reads — and six columns of them ran straight off the side of a phone.
  // The identifiers are still one fold away, for whoever runs the study on
  // this device.
  const WORK_STATUS = {
    done: null, drawing: { cls: "open", zh: "还没画完" },
    abandoned: { cls: "open", zh: "中途换了任务" },
  };
  /** Timestamps a person can read: today and yesterday by the clock, then the date. */
  function whenText(iso) {
    const t = new Date(iso);
    if (isNaN(t)) return iso || "";
    const hm = `${t.getHours()}:${String(t.getMinutes()).padStart(2, "0")}`;
    const midnight = new Date(); midnight.setHours(0, 0, 0, 0);
    const days = Math.floor((midnight - t) / 86400000);
    if (days < 0) return `今天 ${hm}`;
    if (days < 1) return `昨天 ${hm}`;
    if (t.getFullYear() === new Date().getFullYear()) return `${t.getMonth() + 1}月${t.getDate()}日`;
    return `${t.getFullYear()}年${t.getMonth() + 1}月${t.getDate()}日`;
  }
  /** 「我的」这一屏说的是**你**，不是你的画——画全在画廊里。
   *  这里只有三样：你和伙伴是谁、这些画归在谁名下、以及这台设备的情况。 */
  async function loadSessions() {
    let rows = []; try { rows = await mySessions(); } catch (e) { /* 离线也要画得出壳 */ }
    if (rows.length || !state.allSessions) state.allSessions = rows;
    const mine = (state.allSessions || []).filter(r => r.status !== "withdrawn");

    paintAccount();
    const done = mine.filter(r => r.status === "done");
    $("#me-sprite").innerHTML = spriteInner(buddyColor(), done.length ? "happy" : "normal");
    $("#me-name").textContent = state.buddyName || "彩点";
    renderStory(mine, done);

    $("#anon-badge").textContent = state.anonId + (savedPid() ? ` · ${savedPid()}` : "");
    paintSync(await ArtLog.pending().catch(() => 0), navigator.onLine);
  }

  /** 小传：四个数字 + 一句话。都是**做过的事**，没有一个是对画的评价。 */
  function renderStory(mine, done) {
    const el = $("#story"); if (!el) return;
    const days = new Set(done.map(r => (r.created_at || "").slice(0, 10)).filter(Boolean)).size;
    const fams = new Set(done.map(r => familyOf(r.task_id || r.quest_id)).filter(Boolean)).size;
    const lit = litBadges();
    // 三块数字是**门**，不只是数字：点「画完的画」去画廊，点「点亮的徽章」
    // 去徽章墙。数字后面站着东西，就该让人走过去看。
    const tiles = [
      { icon: "image",    v: done.length, unit: "张", label: "画完的画",   c: "blue",   go: "dex" },
      { icon: "compass",  v: fams,        unit: "个", label: "去过的地方", c: "orange", go: "map" },
      { icon: "calendar", v: days,        unit: "天", label: "画画的日子", c: "green" },
      { icon: "medal",    v: lit.size,    unit: "枚", label: "点亮的徽章", c: "purple", go: "buddy" },
    ];
    el.innerHTML = `<div class="story-tiles">` + tiles.map(t =>
      `<${t.go ? "button" : "div"} class="stile${t.go ? " jump" : ""}"${t.go ? ` data-go="${t.go}"` : ""}
         style="--tc:var(--${t.c});--tc-l:var(--${t.c}-l)">
         <span class="stile-ico">${icon(t.icon, 18)}</span>
         <b>${t.v}<i>${t.unit}</i></b><span>${t.label}</span>
       </${t.go ? "button" : "div"}>`).join("") + `</div>`;
    el.querySelectorAll(".stile.jump").forEach(b => { b.onclick = () => openTab(b.dataset.go); });
  }

  // 「画还在不在这台设备上」——和顶栏的 recstat 是同一件事，换成孩子看得懂的话
  function paintSync(pending, online) {
    const me = $("#me-sync"); if (!me) return;
    me.classList.toggle("warn", !online || pending > 0);
    me.innerHTML = `<b></b>${!online ? "没网，先记在这台设备里" : pending ? "正在收好…" : "都收好啦"}`;
  }

  // 点开一张：先看画，再说它是哪个任务。原始文件只在实验模式下露出来。
  const workModal = $("#work-modal");
  function openWork(sid, qid) {
    const row = (state.allSessions || []).find(r => r.session_id === sid) || {};
    const q = state.quests.find(x => x.id === qid);
    $("#work-title").textContent = (q && q.title) || qid;
    $("#work-sub").textContent = whenText(row.created_at)
      + (row.revised ? " · 画完又改过一次" : "") + (row.status === "done" ? "" : " · 没画完");
    const img = $("#work-img");
    img.classList.remove("hidden");
    img.onerror = () => img.classList.add("hidden");
    img.src = `${FILES}/${sid}/after.png`;
    const raw = $("#work-raw");
    raw.classList.toggle("hidden", !state.study);
    if (state.study) raw.innerHTML = `${qid} · ${sid} · <a href="${API}/sessions/${sid}" target="_blank">json</a>`;
    $("#btn-work-again").classList.toggle("hidden", !q);
    $("#btn-work-again").onclick = () => { workModal.classList.add("hidden"); if (q) chooseQuest(q); };
    workModal.classList.remove("hidden");
  }
  $("#btn-work-close").onclick = () => workModal.classList.add("hidden");
  workModal.onclick = (e) => { if (e.target === workModal) workModal.classList.add("hidden"); };
  // recording indicator: what is still only on this device
  ArtLog.onstatus(({ pending, online }) => {
    const el = $("#recstat");
    if (el) {
      // 没在画、没有待传、网也通着的时候它不说话：「等你开画」不携带任何信息，
      // 只是顶栏上常驻的一块灰。真有事的三种情况（正在记、还没传完、断网）
      // 它自己会回来。
      el.classList.toggle("hidden", !state.sessionId && !pending && online);
      el.classList.toggle("warn", !online || pending > 0);
      $("#recstat-text").textContent = !online ? `没网 · 先记在这儿 ${pending}`
        : pending ? `收着 ${pending}` : "我看着呢";
    }
    paintSync(pending, online);
  });
  window.addEventListener("beforeunload", (e) => { if (state.sessionId && !$("#view-draw").classList.contains("hidden")) { e.preventDefault(); e.returnValue = ""; } });

  // ---------- 装到主屏之后：外壳存在设备上 ----------
  // Service Worker 只在 HTTPS（或 localhost）下注册，这是浏览器的规矩，不是选择——
  // 所以局域网 http:// 那条路上「装到主屏」装得上，图标点开也能用，
  // 但外壳不会被存下来，断网就是白屏。真要离线得先有域名和证书。
  // 它存的只有外壳；孩子画的每一笔仍然走 ArtLog 的 IndexedDB 队列，两件事不重叠。
  if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1")) {
    window.addEventListener("load", async () => {
      let reg;
      try { reg = await navigator.serviceWorker.register("/sw.js"); }
      catch (e) { console.warn("sw:", e.message); return; }

      // 新 SW 装好就自己接手了（见 sw.js 里 install 末尾那句）。这边只管一件事：
      // 接手之后**整页重载一次**，让页面和它的外壳回到同一个版本上——
      // 一半新一半旧比全旧还糟。
      // 但孩子正画着的时候绝不重载：那会把没提交的一笔直接冲掉。
      // 不重载也不要紧，下次冷启动自然就是齐的。
      // 第一次装上（这页之前根本没有 SW 管着）不用重载：没有「旧外壳」可言，页面里
      // 跑的就是刚从网上拿的这一版。以前这里也重载，结果是第一次打开时页面会在几百毫秒
      // 到几秒后无缘无故闪一下——要是孩子已经点进了别的 tab，就被拽回地图。
      let reloading = false, hadController = !!navigator.serviceWorker.controller;
      navigator.serviceWorker.addEventListener("controllerchange", () => {
        if (!hadController) { hadController = true; return; }
        if (reloading || state.sessionId) return;
        reloading = true;
        location.reload();
      });
    });
  }

  init().catch(e => alert("初始化失败：" + e.message));
})();
