/* ArtQuest Service Worker — 让这个 app 在 iPad 上真的像个 app。
 *
 * 它只做一件事：**把外壳（HTML/CSS/JS/字体/图标/参考图）存在设备上**，
 * 所以装到主屏之后点开就是即时的，wifi 抖一下也不会白屏。
 *
 * 它**不做**的三件事，每一件都是故意的：
 *
 *   1. 不缓存任何 POST / PUT。孩子画的每一笔走的是 ArtLog 的 IndexedDB 队列
 *      （log.js），断网时排在设备上、连上再补发，去重靠每条记录的 seq。
 *      Service Worker 再插一手只会多出一条谁也说不清的重发路径。
 *   2. 不缓存 /files/。那是孩子的画。「撤回」是这个项目里唯一一处真删——
 *      要是 SW 把作品存进了设备缓存，撤回之后它还在，那条承诺就是假的。
 *   3. 不缓存带身份的 API（任何 /api/sessions、/api/participants）。
 *      离线时该显示「连不上」，不该显示一份说不清是什么时候的旧数据。
 *
 * 能离线看的只有「开得起来」：外壳 + 任务清单 + 参考图。**创作本身仍然需要服务器**
 * （POST /api/sessions 才拿得到 session_id）。这一点不糊弄——真要能离线创作，
 * 得让客户端先发 session_id、服务端认它，那是另一件事。
 */
// 这一行的值由服务端在发出去的时候**换成外壳文件的哈希**（见 main.py 的 `/sw.js`）。
// 手写版本号总会忘：改完 CSS 忘了 bump，装在主屏上的那份就一直抱着旧缓存。
// 直接打开这个文件看到的 "dev" 只是占位。
const VERSION = "dev";
const SHELL = `artquest-shell-${VERSION}`;   // 外壳：换版本就整个换掉
const ASSETS = `artquest-assets-${VERSION}`; // 参考图之类按需存下来的

// 外壳里缺一个都跑不起来，所以装的时候一次全拿
const SHELL_URLS = [
  "/",
  "/static/style.css",
  "/static/app.js",
  "/static/log.js",
  "/static/i18n.js",
  "/static/lang/en.js",
  "/static/manifest.webmanifest",
  "/static/fonts/nunito-latin.woff2",
  "/static/fonts/rhr-sc-400.woff2",
  "/static/fonts/rhr-sc-700.woff2",
  "/static/art/buddy/hero.webp",       // 门口那张立绘（身体）：首屏就要，走缓存优先
  "/static/art/buddy/hero-paint.webp", // 身上那几点颜料，染色用的剪影
  "/static/icons/icon-180.png",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
];

// 读的、没有身份的、离线也该能开起来的那几个。
// **`/api/study` 故意不在里面**：它说的是这个孩子跑在哪一条实验臂上。
// 拿一份说不清多旧的实验配置去渲染界面，比转个圈等服务器糟得多。
// （真正生效的那份条件是 POST /api/sessions 时服务端冻下来的，那条路从不缓存。）
const PUBLIC_API = ["/api/v1/config", "/api/v1/families", "/api/v1/quests", "/api/v1/achievements"];
// 发同一份 index.html 的那几条路径。`/privacy` 不在里面：那是另一个页面，
// 拿外壳顶替它会让隐私政策变成地图。
const SHELL_PATHS = ["/", "/teacher", "/teacher/"];

self.addEventListener("install", (e) => {
  e.waitUntil((async () => {
    const c = await caches.open(SHELL);
    await c.addAll(SHELL_URLS);
    // 那几个公共读接口要**在装的时候就抓一份**，不能等第一次用到再存。
    // 第一次打开页面的时候 SW 还没接管，那几个请求根本不经过它；要是不在这儿
    // 主动抓，第一次断网冷启动就只能指望浏览器自己的 HTTP 缓存——那是撞运气，
    // 撞不到就是地图空白、连任务都选不了。
    // 用 allSettled：少抓到一个也不该让整个 SW 装不上。
    await Promise.allSettled(PUBLIC_API.map(async (u) => {
      const r = await fetch(u, { cache: "no-store" });
      if (r.ok) await c.put(u, r);
    }));
  })());
  // **装好就接手。** 原来这里是「等页面全关掉再说」，听起来更稳妥，实际是个死锁：
  // 旧 SW 一直在给旧的 app.js，而「放行新版本」的逻辑写在新的 app.js 里——
  // 谁也等不到谁。真机上就是这么卡住的：新 HTML 里的按钮画出来了，
  // 旧 CSS 和旧 JS 让它完全没反应。
  //
  // 接手本身是安全的：已经跑起来的那个页面留着它自己那份 JS，SW 只影响之后的请求。
  // 危险的是**重载页面**，那一步交给页面自己判断（孩子正画着就不重载）。
  self.skipWaiting();
});

// 新版本默认在旁边等着——孩子正画到一半的时候，脚底下不该被换掉一套 JS。
// 但「等到所有页面都关掉」对装在主屏上的 app 来说可能是好几天。
// 所以让页面自己说什么时候安全：它没有正在进行的创作时会发这条消息过来。
self.addEventListener("message", (e) => {
  if (e.data && e.data.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => k !== SHELL && k !== ASSETS).map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

/** 外壳：有存下来的就直接给，没有才去网上拿。
 *
 *  **这里一度是全局网络优先**，理由写在下面那段注释里：「不能 stale-while-revalidate，
 *  否则新的 HTML 配旧的 CSS 和 JS」。那条担心对 stale-while-revalidate 成立——
 *  每个文件各自过期，版本会错配。但对**缓存优先 + 带版本的缓存名**不成立：
 *  `SHELL` 这个名字里带着 VERSION（服务端发 sw.js 时换成外壳七个文件的哈希），
 *  同一个缓存里的文件必然是同一版；新版本装进新缓存，activate 时把旧的整个删掉
 *  再 claim。要么全旧要么全新，中间没有状态。
 *
 *  换过来的理由是实测的：服务器 RTT 211 ms，网络优先意味着**每次点开 app 都要把
 *  外壳重拉一遍**——这就是「每次启动都卡一下」的根因。改完外壳是即时的。
 *  新版本照旧会装：浏览器每次导航都重新查 sw.js（服务端给它发 no-cache），
 *  装好之后 controllerchange 让页面在安全的时候重载一次（见 app.js 末尾）。
 *
 *  带身份的 API 和 /files/ 仍然一个字节都不缓存，文件头那三条没变。 */
async function cacheFirst(req) {
  const hit = await caches.match(req);     // 外壳在 SHELL 里，按需存的在 ASSETS 里
  if (hit) return hit;
  try {
    const res = await fetch(req);
    if (res && res.ok) (await caches.open(ASSETS)).put(req, res.clone());
    return res;
  } catch (e) {
    return new Response("", { status: 504, statusText: "offline" });
  }
}

/** 有网就用网上的，没网才用存下来的。**公共读接口和参考图还走这条**：
 *  它们的内容改了不会让外壳哈希变（换一张参考图、改一道题都不会），
 *  缓存优先会让设备上一直是旧的。
 *
 *  **不能用 stale-while-revalidate。** 那个策略先给旧的、后台换新的，听起来
 *  只是「慢一步」，实际后果严重得多：HTML、CSS、JS 各自独立地过期，于是会出现
 *  **新的 HTML 配旧的 CSS 和 JS**——按钮画出来了但没有样式也没有事件，
 *  页面看起来就是坏的。外壳必须整体一致，要么全旧要么全新。
 *
 *  这个 SW 的职责从一开始就写的是「没网的时候还能开」，不是「有网的时候快一点」。
 *  网络优先正好就是那句话，快那几十毫秒本来也不值得拿版本错配去换。 */
async function networkFirst(req, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    // `cache: "reload"` 跳过浏览器自己那层 HTTP 缓存。少了它，SW 以为自己在
    // 「网络优先」，其实拿到的还是浏览器缓存里的旧文件——两层缓存要一起堵。
    const res = await fetch(new Request(req, { cache: "reload" }));
    if (res && res.ok) cache.put(req, res.clone());
    return res;
  } catch (e) {
    const hit = await cache.match(req);
    return hit || new Response("", { status: 504, statusText: "offline" });
  }
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;                       // 写入一律不碰，见文件头第 1 条
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith("/files/")) return;         // 孩子的画不留副本，见第 2 条

  if (url.pathname.startsWith("/api/")) {
    // 公共的读接口可以留一份，好让离线时地图不是空的；带身份的一律走网络
    if (PUBLIC_API.includes(url.pathname)) e.respondWith(networkFirst(req, SHELL));
    return;                                               // 其余的：网络，连不上就是连不上
  }

  // 导航（点主屏图标、刷新）：外壳直接给存下来的那一份，不等网络。
  if (req.mode === "navigate") {
    if (!SHELL_PATHS.includes(url.pathname)) return;     // /privacy 之类照常走网络
    e.respondWith((async () => {
      const hit = await caches.match("/");
      if (hit) return hit;
      try {
        const res = await fetch(req);
        if (res && res.ok) (await caches.open(SHELL)).put("/", res.clone());
        return res;
      } catch (e2) {
        return new Response("", { status: 504 });
      }
    })());
    return;
  }

  if (url.pathname.startsWith("/static/")) {
    e.respondWith(SHELL_URLS.includes(url.pathname) ? cacheFirst(req) : networkFirst(req, ASSETS));
  }
});
