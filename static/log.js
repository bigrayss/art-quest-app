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
  const DB_NAME = "artquest-log", DB_VERSION = 1, STORE = "queue";
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
      };
      req.onsuccess = () => res(req.result);
      req.onerror = () => res(null);
    });
  }
  const tx = (mode) => db.transaction(STORE, mode).objectStore(STORE);

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
    const n = await count();
    listeners.forEach(fn => { try { fn({ pending: n, online: navigator.onLine, quarantined }); } catch (e) { /* ignore */ } });
    return n;
  }

  async function post(sessionId, body) {
    const res = await fetch(`/api/sessions/${sessionId}/log`, {
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

  async function flush() {
    if (!sid || flushing || !navigator.onLine) return notify();
    flushing = true;
    try {
      for (;;) {
        const rows = await pull(MAX_BATCH);
        if (!rows.length) break;
        const bySid = {};
        rows.forEach(r => { (bySid[r.sid] = bySid[r.sid] || { events: [], strokes: [], pending: 0, keys: [] }); bySid[r.sid][r.stream].push(r.rec); bySid[r.sid].keys.push(r.k); });
        for (const s of Object.keys(bySid)) {
          const { keys, ...body } = bySid[s];
          try {
            await post(s, body);
            await drop(keys);
          } catch (e) {
            if (e.status >= 400 && e.status < 500 && e.status !== 408 && e.status !== 429) {
              await postRowsIndividually(s, rows.filter(r => r.sid === s));
            } else { throw e; }
          }
        }
        if (rows.length < MAX_BATCH) break;
      }
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
        `/api/sessions/${s}/log`, new Blob([JSON.stringify(bySid[s])], { type: "application/json" })));
    });
  }

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
    onstatus(fn) { listeners.push(fn); },
  };
  window.ArtLog = ArtLog;
  window.addEventListener("pagehide", beacon);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") { flush(); beacon(); } });
})();
