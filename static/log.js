/* ArtLog — local-first recorder for the research data.
 *
 * Everything a child does is written to IndexedDB FIRST, then flushed to the
 * server in batches. Losing the network (or the tab) cannot lose a session:
 * the queue survives a reload and is re-sent, and because every record carries
 * a monotonic `seq` per stream, a re-sent batch is de-duplicated server-side.
 *
 * Raw only. Speed / hesitation / rhythm are derived offline from these points.
 */
(function () {
  "use strict";
  const DB_NAME = "artquest-log", DB_VERSION = 2, STORE = "queue";
  // v2 加了两个库：
  //   tickets —— 联网时预领的票（服务端发的 session_id + 冻好的 condition）。
  //              离线开始创作就是花掉一张，不用向服务器要 id。
  //   outbox  —— 离线时攒下的**整个请求**（建 session、快照、提交、收尾）。
  //              和 queue 里那些逐笔记录不一样，它们各自打到不同的接口上。
  const TICKETS = "tickets", OUTBOX = "outbox";
  // 同 app.js 开头：iOS 壳注入 window.ArtQuestNative.server，API 在别的源上；网页版同源。
  const ORIGIN = (window.ArtQuestNative && window.ArtQuestNative.server)
    ? String(window.ArtQuestNative.server).replace(/\/+$/, "") : "";
  const API = `${ORIGIN}/api/v1`;
  const FLUSH_MS = 4000, MAX_BATCH = 120;

  let db = null, sid = null, flushing = false, timer = null, memKey = 0, quarantined = 0;
  const seqs = { events: 0, strokes: 0 };
  const listeners = [];
  const memq = [];          // fallback when IndexedDB is unavailable (private mode)

  function openDB() {
    return new Promise((res) => {
      let req;
      try { req = indexedDB.open(DB_NAME, DB_VERSION); } catch (e) { return res(null); }
      req.onupgradeneeded = () => {
        const d = req.result;
        if (!d.objectStoreNames.contains(STORE)) {
          const os = d.createObjectStore(STORE, { keyPath: "k", autoIncrement: true });
          os.createIndex("sid", "sid");
        }
        if (!d.objectStoreNames.contains(TICKETS)) d.createObjectStore(TICKETS, { keyPath: "session_id" });
        if (!d.objectStoreNames.contains(OUTBOX)) {
          const ob = d.createObjectStore(OUTBOX, { keyPath: "k", autoIncrement: true });
          ob.createIndex("sid", "sid");
        }
      };
      req.onsuccess = () => res(req.result);
      req.onerror = () => res(null);
    });
  }
  const tx = (mode) => db.transaction(STORE, mode).objectStore(STORE);
  const store = (name, mode) => db.transaction(name, mode).objectStore(name);
  const req1 = (r) => new Promise((res) => { r.onsuccess = () => res(r.result); r.onerror = () => res(null); });
  const all = (name) => db ? req1(store(name, "readonly").getAll()).then(x => x || []) : Promise.resolve([]);

  function put(rec) {
    if (!db) { memq.push(Object.assign({ k: ++memKey }, rec)); return Promise.resolve(); }
    return new Promise((res) => {
      const r = tx("readwrite").add(rec);
      r.onsuccess = r.onerror = () => res();
    });
  }
  // Drains every session in the queue, not just the current one: records left
  // over from a session that ended offline still reach the server later.
  function pull(limit) {
    if (!db) return Promise.resolve(memq.filter(r => !r.bad).slice(0, limit));
    return new Promise((res) => {
      const out = [], r = tx("readonly").openCursor();
      r.onsuccess = () => {
        const c = r.result;
        if (!c || out.length >= limit) return res(out);
        if (!c.value.bad) out.push(c.value);   // quarantined rows stay on disk, out of the way
        c.continue();
      };
      r.onerror = () => res(out);
    });
  }
  function drop(keys) {
    if (!db) { keys.forEach(k => { const i = memq.findIndex(r => r.k === k); if (i >= 0) memq.splice(i, 1); }); return Promise.resolve(); }
    return new Promise((res) => {
      const st = tx("readwrite");
      keys.forEach(k => st.delete(k));
      st.transaction.oncomplete = st.transaction.onerror = () => res();
    });
  }
  function mark_bad(rows) {   // keep the record, stop it blocking everything behind it
    quarantined += rows.length;
    if (!db) { rows.forEach(r => { const m = memq.find(x => x.k === r.k); if (m) m.bad = true; }); return Promise.resolve(); }
    return new Promise((res) => {
      const st = tx("readwrite");
      rows.forEach(r => st.put(Object.assign({}, r, { bad: true })));
      st.transaction.oncomplete = st.transaction.onerror = () => res();
    });
  }
  function count() {
    if (!db) return Promise.resolve(memq.filter(r => !r.bad).length);
    return new Promise((res) => {
      const r = tx("readonly").openCursor();
      let n = 0;
      r.onsuccess = () => { const c = r.result; if (!c) return res(n); if (!c.value.bad) n++; c.continue(); };
      r.onerror = () => res(n);
    });
  }

  async function notify() {
    const n = await count() + (db ? (await all(OUTBOX)).filter(r => !r.bad).length : 0);
    listeners.forEach(fn => { try { fn({ pending: n, online: navigator.onLine, quarantined }); } catch (e) { /* ignore */ } });
    return n;
  }

  async function post(sessionId, body) {
    const res = await fetch(`${API}/sessions/${sessionId}/log`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (!res.ok) { const e = new Error("HTTP " + res.status); e.status = res.status; throw e; }
  }

  /** A batch the server refuses (4xx) must not block everything queued behind
   *  it: re-send the rows one by one, and quarantine only the ones that still
   *  fail. Quarantined rows stay in the local store for recovery. */
  async function postRowsIndividually(sessionId, rows) {
    const bad = [], good = [];
    for (const r of rows) {
      const one = { events: [], strokes: [], pending: 0 };
      one[r.stream].push(r.rec);
      try { await post(sessionId, one); good.push(r); }
      catch (e) { if (e.status >= 400 && e.status < 500 && e.status !== 408 && e.status !== 429) bad.push(r); else throw e; }
    }
    if (bad.length) { await mark_bad(bad); console.warn(`${bad.length} 条记录被服务器拒绝，已在本地隔离保留`); }
    await drop(good.concat(bad).map(r => r.k));
  }

  // ---------- 发件箱：离线时攒下的整个请求 ----------
  // queue 里是一条条记录，全部打到 /log；outbox 里是各自不同的接口
  // （建 session / 快照 / 提交 / 收尾），而且**必须按原来的先后顺序**重放。
  const OUTBOX_URL = {
    create:   () => `${API}/sessions`,
    snapshot: (s) => `${API}/sessions/${s}/snapshot`,
    submit:   (s) => `${API}/sessions/${s}/submit`,
    finalize: (s) => `${API}/sessions/${s}/finalize`,
  };

  /** 还没重放的「建 session」是哪些 —— 它们的笔画得等着。 */
  async function pendingCreates() {
    const rows = await all(OUTBOX);
    return new Set(rows.filter(r => r.kind === "create").map(r => r.sid));
  }

  /** 按顺序重放发件箱。任何一条没过去就停下——后面的都依赖前面的。 */
  async function drainOutbox(pred) {
    if (!db) return;
    const rows = (await all(OUTBOX)).filter(r => !r.bad && (!pred || pred(r))).sort((a, b) => a.k - b.k);
    for (const r of rows) {
      const url = (OUTBOX_URL[r.kind] || (() => null))(r.sid);
      if (!url) { await req1(store(OUTBOX, "readwrite").delete(r.k)); continue; }
      let res;
      try {
        res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" },
                                 body: JSON.stringify(r.body) });
      } catch (e) { return; }                       // 还是没网，原样留着
      if (res.ok || res.status === 409) {
        await req1(store(OUTBOX, "readwrite").delete(r.k));
        continue;
      }
      if (res.status >= 500 || res.status === 429 || res.status === 408) return;   // 服务器的问题，等下一轮
      // 4xx：这条请求服务器永远不会接受（比如票号它不认）。删掉它会让后面
      // 所有依赖它的东西一起失败得莫名其妙，所以留在本地、标记出来，
      // 让「这台设备上还有没送出去的东西」这件事始终是可见的。
      await req1(store(OUTBOX, "readwrite").put(Object.assign({}, r, { bad: true, status: res.status })));
      await req1(store(OUTBOX, "readwrite").delete(r.k));
      quarantined += 1;
      console.warn(`outbox ${r.kind} 被服务器拒绝（HTTP ${res.status}）`);
      return;
    }
  }

  async function flush() {
    if (flushing || !navigator.onLine) return notify();
    flushing = true;
    try {
      // 顺序：先把「建 session」送过去 → 再送笔画 → 最后送离线时存下的「交卷」。
      // 交卷排在笔画后面：服务器收到画的时候，这一局的笔画已经在了。
      await drainOutbox(r => r.kind !== "submit" && r.kind !== "finalize");
      const held = await pendingCreates();
      for (;;) {
        const rows = await pull(MAX_BATCH);
        if (!rows.length) break;
        // 被 create 挡住的行一条都不会被删掉，`rows.length` 就永远是满的——
        // 没有这个「这一轮到底动了没有」的判断，下面的 for(;;) 会原地转圈。
        let moved = 0;
        const bySid = {};
        rows.forEach(r => { (bySid[r.sid] = bySid[r.sid] || { events: [], strokes: [], pending: 0, keys: [] }); bySid[r.sid][r.stream].push(r.rec); bySid[r.sid].keys.push(r.k); });
        for (const s of Object.keys(bySid)) {
          // 这个 session 还没被建出来：它的笔画现在发过去只会撞 404，
          // 而 404 走的是「服务器拒了这一行」那条路——会被隔离掉，画了等于没画。
          if (held.has(s)) continue;
          const { keys, ...body } = bySid[s];
          try {
            await post(s, body);
            await drop(keys); moved += keys.length;
          } catch (e) {
            if (e.status >= 400 && e.status < 500 && e.status !== 408 && e.status !== 429) {
              await postRowsIndividually(s, rows.filter(r => r.sid === s));
              moved += 1;
            } else { throw e; }
          }
        }
        if (!moved) break;                      // 全被挡住了：这一轮没得做，等下一轮
        if (rows.length < MAX_BATCH) break;
      }
      if (!held.size && !(await count())) await drainOutbox(r => r.kind === "submit" || r.kind === "finalize");
    } catch (e) {
      // keep the queue; the next tick (or reconnect) retries
    } finally {
      flushing = false;
    }
    return notify();
  }

  // Last-gasp send on tab close — best effort, and the queue survives anyway.
  function beacon() {
    if (!navigator.sendBeacon) return;
    pull(MAX_BATCH).then(rows => {
      const bySid = {};
      rows.forEach(r => { (bySid[r.sid] = bySid[r.sid] || { events: [], strokes: [], pending: 0 })[r.stream].push(r.rec); });
      Object.keys(bySid).forEach(s => navigator.sendBeacon(
        `${API}/sessions/${s}/log`, new Blob([JSON.stringify(bySid[s])], { type: "application/json" })));
    });
  }

  // ---------- 票 ----------
  // 一张票 = 服务端发的 session_id + 冻好的 condition。联网时领，离线时花。
  // 不在设备上生成 id：那会同时毁掉 id 的可信性、条件冻结，以及重放时
  // 「还没建」和「不存在」的可分辨性（见 DESIGN.md「离线创作」）。
  /** 票和发件箱在**没有 session 的时候**也要能用——离线开工时 `start()` 还没跑过，
   *  `db` 还是 null。以前这些函数直接读 `db`，于是「有 3 张票」被读成「一张都没有」，
   *  孩子看到的是「这台设备上没有备用的创作名额了」。 */
  async function ensure() { if (db === null) db = await openDB(); return !!db; }

  async function saveTickets(list) {
    await ensure();
    if (!db || !list || !list.length) return 0;
    const os = store(TICKETS, "readwrite");
    list.forEach(t => os.put(t));
    await new Promise(res => { os.transaction.oncomplete = os.transaction.onerror = res; });
    return list.length;
  }
  async function countTickets() { await ensure(); return (await all(TICKETS)).length; }
  /** 花掉一张票。优先给绑了这个任务的那张；没有就用任务无关的。 */
  async function takeTicket(questId) {
    await ensure();
    const rows = await all(TICKETS);
    if (!rows.length) return null;
    const t = rows.find(r => r.quest_id === questId) || rows.find(r => !r.quest_id) || null;
    if (!t) return null;
    await req1(store(TICKETS, "readwrite").delete(t.session_id));
    return t;
  }
  /** 把一整个请求存进发件箱，等有网了按顺序重放。 */
  async function defer(kind, sessionId, body) {
    await ensure();
    if (!db) return false;
    await req1(store(OUTBOX, "readwrite").add({ kind, sid: sessionId, body, at: Date.now() }));
    await notify();
    return true;
  }
  async function outboxCount() { await ensure(); return (await all(OUTBOX)).filter(r => !r.bad).length; }

  const ArtLog = {
    async start(sessionId) {
      if (db === null) db = await openDB();
      sid = sessionId;
      seqs.events = seqs.strokes = 0;
      if (!timer) timer = setInterval(flush, FLUSH_MS);
      window.addEventListener("online", flush);
      flush();   // drain anything a previous session left behind
      return notify();
    },
    stop() { clearInterval(timer); timer = null; sid = null; },
    /** One line of the operation log: {t_ms, type, payload}. */
    event(type, t_ms, payload) {
      if (!sid) return;
      put({ sid, stream: "events", rec: { seq: ++seqs.events, t_ms: Math.round(t_ms), type, payload: payload || null } }).then(notify);
    },
    /** One completed stroke with its sampled points. */
    stroke(rec) {
      if (!sid) return;
      put({ sid, stream: "strokes", rec: Object.assign({ seq: ++seqs.strokes }, rec) }).then(notify);
    },
    flush,
    beacon,
    pending: count,
    // 离线创作要用的四件
    saveTickets, countTickets, takeTicket, defer, outboxCount,
    ready: ensure,
    onstatus(fn) { listeners.push(fn); },
  };
  window.ArtLog = ArtLog;
  window.addEventListener("pagehide", beacon);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") { flush(); beacon(); } });
})();
