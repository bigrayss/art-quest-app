// 语言：中文是源文本，英文是一张「中文 → 英文」的表（static/lang/en.js）。
//
// 为什么不是 t("key") 那种做法：这个 app 没有构建步骤，界面文本散在 HTML 和 app.js
// 的几百个模板字符串里。逐个改成键值调用等于把整个前端重写一遍，而且以后每加一句
// 都得记着加键。这里反过来：**中文原文就是键**。页面上凡是出现了字典里有的整段
// 文本（文本节点、placeholder、title、aria-label、alt），就换成英文；后来动态渲染
// 出来的由 MutationObserver 接着换。带变量的句子用 `{n}` 占位，编译成正则整段匹配。
//
// 孩子自己写的东西（名字、心愿）不会撞上字典里的键；服务器给的正文（任务、反馈）
// 由服务器按 Accept-Language 直接给英文，这里不碰。
(function () {
  "use strict";
  const KEY = "artquest.lang";
  const SUPPORTED = ["zh", "en"];
  function stored() { try { return localStorage.getItem(KEY) || ""; } catch (e) { return ""; } }
  function guess() {
    // 设备语言不是中文就给英文；存过的以存的为准
    const nav = (navigator.language || "zh").toLowerCase();
    return nav.startsWith("zh") ? "zh" : "en";
  }
  const lang = SUPPORTED.includes(stored()) ? stored() : guess();
  document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  document.documentElement.dataset.lang = lang;

  const dict = (lang === "en" && window.ARTQUEST_LANG_EN) || {};
  const exact = new Map();
  const patterns = [];
  Object.keys(dict).forEach(k => {
    if (/\{\w+\}/.test(k)) {
      const names = [];
      const re = new RegExp("^" + k.replace(/[.*+?^${}()|[\]\\]/g, m => m === "{" || m === "}" ? m : "\\" + m)
        .replace(/\{(\w+)\}/g, (_, n) => { names.push(n); return "([\\s\\S]+?)"; }) + "$");
      patterns.push({ re, names, out: dict[k] });
    } else exact.set(k, dict[k]);
  });

  const CJK = /[㐀-鿿　-〿＀-￯]/;
  function translate(s) {
    if (!s || !CJK.test(s)) return s;
    const hit = exact.get(s.trim());
    if (hit !== undefined) return s.replace(s.trim(), hit);
    for (const p of patterns) {
      const m = p.re.exec(s.trim());
      if (!m) continue;
      let out = p.out;
      p.names.forEach((n, i) => { out = out.split("{" + n + "}").join(translate(m[i + 1])); });
      return s.replace(s.trim(), out);
    }
    return s;
  }
  function t(s, vars) {
    let out = translate(String(s));
    if (vars) Object.keys(vars).forEach(k => { out = out.split("{" + k + "}").join(vars[k]); });
    return out;
  }

  const ATTRS = ["placeholder", "title", "aria-label", "alt", "data-label"];   // data-label：CSS attr() 显示的字
  const SKIP = new Set(["SCRIPT", "STYLE", "TEXTAREA", "INPUT"]);
  function walk(node) {
    if (node.nodeType === 3) {
      const v = node.nodeValue, w = translate(v);
      if (w !== v) node.nodeValue = w;
      return;
    }
    if (node.nodeType !== 1 || SKIP.has(node.tagName) || node.hasAttribute("data-no-i18n")) {
      // 输入框的内容是孩子写的，不碰；placeholder 是我们写的，要换
      if (node.nodeType === 1 && (node.tagName === "INPUT" || node.tagName === "TEXTAREA")) attrs(node);
      return;
    }
    attrs(node);
    for (let c = node.firstChild; c; c = c.nextSibling) walk(c);
  }
  function attrs(el) {
    ATTRS.forEach(a => {
      if (!el.hasAttribute(a)) return;
      const v = el.getAttribute(a), w = translate(v);
      if (w !== v) el.setAttribute(a, w);
    });
  }

  let observing = false;
  function apply(root) { walk(root || document.body); }
  function observe() {
    if (observing || lang === "zh") return;
    observing = true;
    // 先把此刻已经在页面上的换掉，再盯着后来加进来的
    apply(document.body);
    const mo = new MutationObserver(muts => {
      for (const m of muts) {
        if (m.type === "characterData") walk(m.target);
        else if (m.type === "attributes") attrs(m.target);
        else m.addedNodes.forEach(walk);
      }
    });
    mo.observe(document.body, { childList: true, subtree: true, characterData: true,
                                attributes: true, attributeFilter: ATTRS });
  }
  function set(next) {
    if (!SUPPORTED.includes(next) || next === lang) return;
    try { localStorage.setItem(KEY, next); } catch (e) { /* 无所谓 */ }
    location.reload();               // 整页重来最稳：所有已经渲染的文本都是用当前语言拼的
  }

  window.I18N = { lang, t, apply, observe, set, has: s => exact.has(s) };
  if (document.body) observe(); else document.addEventListener("DOMContentLoaded", observe);
})();
