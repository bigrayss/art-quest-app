# -*- coding: utf-8 -*-
"""把参考课例做成一份 PDF 课件：static/classroom/<课 id>.pdf。

课的内容只有一份，在 artquest/classroom.py 里；这里把它排成 16:9 的页，用 Chrome 打印成 PDF。
改了参考课例的文字或示意图之后重跑：

    .venv/bin/python tools/build_courseware.py
"""
import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from artquest import classroom  # noqa: E402

TINTS = [("#fff3e6", "#dd7c1e"), ("#e8f5fd", "#3a9ad0"), ("#ecf8e4", "#56a637"), ("#f4eefd", "#9d71d9")]
CSS = """
@page { size: 1280px 720px; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; font-family: "Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", sans-serif; color: #3f3f3f; }
.page { width: 1280px; height: 720px; padding: 56px 72px 64px; position: relative; page-break-after: always; overflow: hidden;
        display: flex; flex-direction: column; gap: 22px; background: #fffdf9; }
.page::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 14px; background: var(--deep); }
h1 { margin: 0; font-size: 44px; line-height: 1.2; color: #2f2f2f; }
.body { flex: 1; display: grid; grid-template-columns: 1fr 1fr; gap: 44px; align-items: center; min-height: 0; }
.body.nofig { grid-template-columns: 1fr; }
ul { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 16px; font-size: 26px; line-height: 1.55; }
li { padding-left: 26px; position: relative; }
li::before { content: ""; position: absolute; left: 0; top: .62em; width: 11px; height: 11px; border-radius: 50%; background: var(--deep); }
.figs { display: grid; gap: 14px; color: #3f3f3f; }
.figs.many { grid-template-columns: 1fr 1fr; }
figure { margin: 0; background: #fff; border: 2px solid #ececec; border-radius: 18px; padding: 16px; }
figure svg { display: block; width: 100%; height: auto; }
.figs.pic figure { padding: 10px; border: 0; background: none; text-align: center; }
.figs.pic img { max-width: 100%; max-height: 430px; border-radius: 10px; }
.cover .figs.pic img { max-height: 300px; } .cover .figs.pic figcaption { display: none; }
.cover figure:has(img) { width: auto; background: none; padding: 0; }
figcaption { margin-top: 6px; font-size: 16px; text-align: center; line-height: 1.4; }
.ask { margin: 0; padding: 16px 22px; border-radius: 16px; background: var(--tint); font-size: 24px; font-weight: 700; color: #2f2f2f; }
.ask::before { content: "想一想　"; color: var(--deep); }
.foot { position: absolute; left: 72px; right: 72px; bottom: 22px; display: flex; justify-content: space-between; font-size: 15px; color: #a0a0a0; }
.cover { background: var(--tint); align-items: center; justify-content: center; text-align: center; gap: 18px; }
.cover h1 { font-size: 92px; letter-spacing: .06em; }
.cover .sub { font-size: 22px; color: var(--deep); font-weight: 700; letter-spacing: .08em; }
.cover ul { font-size: 28px; gap: 6px; } .cover li { padding: 0; } .cover li::before { display: none; }
.cover figure { width: 520px; background: #fff; border: 0; border-radius: 24px; padding: 22px 26px; color: var(--deep); }
.goal ul { font-size: 28px; gap: 22px; counter-reset: n; }
.goal li { padding-left: 62px; counter-increment: n; }
.goal li::before { content: counter(n); width: 42px; height: 42px; top: 0; border-radius: 50%; color: #fff; font-weight: 800; font-size: 22px;
                   display: flex; align-items: center; justify-content: center; }
.tasks .body { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; align-items: stretch; align-content: center; }
.task { background: #fff; border: 2px solid #ececec; border-radius: 18px; padding: 18px 22px; display: flex; flex-direction: column; gap: 8px; }
.task b { font-size: 25px; color: #2f2f2f; } .task p { margin: 0; font-size: 18.5px; line-height: 1.5; }
.tag { align-self: flex-start; font-size: 15px; font-weight: 700; padding: 3px 12px; border-radius: 999px; background: var(--tint); color: var(--deep); }
.req { color: #6a6a6a; }
"""


def e(s):
    return html.escape(str(s or ""))


def page_html(lesson, i):
    tint, deep = TINTS[i % len(TINTS)]
    L = classroom.lesson_full(lesson)
    tb = L.get("textbook") or {}
    pages = []

    def foot(n):
        return f'<div class="foot"><span>{e(L["title"])}</span><span>{n}</span></div>'

    n = 0
    for s in L["slides"]:
        n += 1
        figs, caps = s.get("figures") or [], s.get("captions") or []
        fig_html = ""
        if s.get("img"):
            src = (classroom.COURSEWARE_DIR / "img" / f"{s['img']}.jpg").as_uri()
            fig_html = f'<div class="figs pic"><figure><img src="{src}"><figcaption>{e(s.get("credit"))}</figcaption></figure></div>'
            figs = [1]
        elif figs:
            fig_html = '<div class="figs%s">%s</div>' % (" many" if len(figs) > 1 else "", "".join(
                f'<figure>{f}{"<figcaption>" + e(caps[k]) + "</figcaption>" if k < len(caps) and caps[k] else ""}</figure>'
                for k, f in enumerate(figs)))
        lines = "<ul>%s</ul>" % "".join(f"<li>{e(t)}</li>" for t in s.get("lines") or [])
        if s.get("kind") == "cover":
            sub = " · ".join(x for x in (tb.get("lesson"), L.get("subject")) if x)
            pages.append(f'<section class="page cover"><div class="sub">{e(sub)}</div><h1>{e(s["title"])}</h1>{fig_html}{lines}</section>')
            n += 1
            pages.append('<section class="page goal"><h1>这节课要学会</h1><div class="body nofig"><ul>%s</ul></div>%s</section>'
                         % ("".join(f"<li>{e(o)}</li>" for o in L["objectives"]), foot(n)))
            continue
        if s.get("kind") == "tasks":
            cards = "".join(
                f'<div class="task"><span class="tag">{e(t["kind_name"])}{" · 选做" if t.get("optional") else ""} · {t["minutes"]} 分钟</span>'
                f'<b>{e(t["title"])}</b><p>{e(t["instruction"])}</p><p class="req">要做到：{e(t["requirements"])}</p></div>' for t in L["tasks"])
            pages.append(f'<section class="page tasks"><h1>{e(s["title"])}</h1><div class="body">{cards}</div>{foot(n)}</section>')
            continue
        ask = f'<p class="ask">{e(s["ask"])}</p>' if s.get("ask") else ""
        pages.append(f'<section class="page"><h1>{e(s["title"])}</h1><div class="body{"" if figs else " nofig"}">{lines}{fig_html}</div>{ask}{foot(n)}</section>')
    return (f'<!doctype html><html lang="zh"><meta charset="utf-8"><title>{e(L["title"])}</title><style>{CSS}'
            f':root{{--tint:{tint};--deep:{deep}}}</style><body>{"".join(pages)}</body></html>')


def main():
    from playwright.sync_api import sync_playwright
    out = classroom.COURSEWARE_DIR
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        for i, lesson in enumerate(classroom.LESSONS):
            tmp = out / "_page.html"                       # 从文件打开，file:// 的图才加载得了
            tmp.write_text(page_html(lesson, i), encoding="utf-8")
            page.goto(tmp.as_uri(), wait_until="load")
            page.pdf(path=str(out / f"{lesson['id']}.pdf"), width="1280px", height="720px", print_background=True)
            if "--shots" in sys.argv:
                n = page.locator(".page").count()
                for k in range(n):
                    page.locator(".page").nth(k).screenshot(path=f"{sys.argv[sys.argv.index('--shots') + 1]}/{lesson['id']}_{k + 1:02d}.png")
            print(lesson["id"], (out / f"{lesson['id']}.pdf").stat().st_size // 1024, "KB")
        browser.close()
    (out / "_page.html").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
