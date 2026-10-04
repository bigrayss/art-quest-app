#!/usr/bin/env python3
"""把 docs/ 里用户给的精灵素材出成界面用的小文件（static/art/buddy/<角色>/）。

五个新形象（normal 那套还是老路子，见 static/art/buddy/README.md）：

    happy      02  提交保存成功后播一次的「开心小画家」
    thinking   03  等 AI 回话时的「想一想」
    explore    04  地图上「今天」卡旁边的「拿放大镜」
    reading    05  任务说明页的「看书」
    encourage  06  问卷/结算那张鼓励卡上的「抱心」

每个角色出三样：
    body.webp   整只的静态图，480 宽（最大显示 ~160 CSS px × 2 倍屏）
    icon.webp   256×256 的头部特写，给 26–54px 的小头像位
    eyes.webp   只有 explore / reading 有：9 帧眨眼贴片。**贴在整只静态图上面**，
                不像 normal 那样把身体挖空——所以缩小也不会露缝（第 0 帧和身体
                同一次缩放出来，像素一样）。贴片的位置用整数像素框算成百分比，
                打印出来抄进 style.css。
    cheer.webp  只有 happy 有：从用户给的 97 帧 webp 里按 10fps 取 3 秒，6×5 格，
                每格 288×263。CSS steps() 播一遍就停。

素材来源：docs/04_explore_complete.zip（有分层）、docs/demo_standalone.html（05 的分层
内嵌在 HTML 里）、其余只有静态 PNG + 烤死的 webp。

用法：.venv/bin/python tools/build_buddy_roles.py
"""
import base64
import io
import re
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT = ROOT / "static" / "art" / "buddy"
W, H = 1312, 1199            # 所有素材的原生画布
BODY_W = 480
BODY_H = round(H * BODY_W / W)   # 439
S = BODY_W / W
ICON = 256
CHEER_W, CHEER_H = 288, 263
CHEER_FPS, CHEER_SEC = 10, 3
CHEER_COLS = 6


def save_webp(im, path, q=85):
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "WEBP", quality=q, method=6)
    print(f"  {path.relative_to(ROOT)}  {im.size[0]}×{im.size[1]}  {path.stat().st_size // 1024} KB")


def ndiff(a, b, thr=30):
    d = ImageChops.difference(a.convert("RGBA"), b.convert("RGBA")).convert("L")
    return sum(d.histogram()[thr:])


def head_icon(full, cx_frac=None, top_frac=0.0, side_frac=0.62):
    """头部特写：按 alpha 外框取上面一段，裁成正方形。"""
    bb = full.getbbox()
    bw, bh = bb[2] - bb[0], bb[3] - bb[1]
    side = int(bh * side_frac)
    cx = bb[0] + bw * (0.5 if cx_frac is None else cx_frac)
    top = bb[1] + int(bh * top_frac)
    box = (int(cx - side / 2), top, int(cx + side / 2), top + side)
    return full.crop(box).resize((ICON, ICON), Image.LANCZOS)


def blink_role(name, full, eye_frames, box):
    """full：整只静态图；eye_frames：9 张原生尺寸的眼睛贴片；box：贴片在原图里的 (x,y,w,h)。
    输出 body.webp + eyes.webp，并打印 CSS 百分比。"""
    x, y, w, h = box
    # 先在原生分辨率合成 9 张整图，再整图缩小、再裁——贴片和身体是同一次缩放出来的
    frames = []
    for k, ef in enumerate(eye_frames):
        f = full.copy()
        f.alpha_composite(ef, (x, y))
        frames.append(f.resize((BODY_W, BODY_H), Image.LANCZOS))
    body = frames[0]
    # 缩小后的框，外扩 4px 盖住重采样核
    m = 4
    sx, sy = max(0, int(x * S) - m), max(0, int(y * S) - m)
    ex, ey = min(BODY_W, int((x + w) * S + 1) + m), min(BODY_H, int((y + h) * S + 1) + m)
    cw, ch = ex - sx, ey - sy
    sheet = Image.new("RGBA", (cw * 9, ch), (0, 0, 0, 0))
    for k, f in enumerate(frames):
        sheet.alpha_composite(f.crop((sx, sy, ex, ey)), (k * cw, 0))
    # 自检：第 0 帧贴回去必须和身体一模一样
    chk = body.copy(); chk.alpha_composite(sheet.crop((0, 0, cw, ch)), (sx, sy))
    assert ndiff(chk, body) == 0, f"{name}: 第 0 帧和身体对不上"
    save_webp(body, OUT / name / "body.webp")
    save_webp(sheet, OUT / name / "eyes.webp", q=90)
    print(f"  CSS .bd-fig[data-role={name}] .bd-eyes {{ left:{sx / BODY_W * 100:.6f}%; top:{sy / BODY_H * 100:.6f}%;"
          f" width:{cw / BODY_W * 100:.6f}%; height:{ch / BODY_H * 100:.6f}%; }}")
    return body


def explore():
    print("explore (04)")
    z = zipfile.ZipFile(DOCS / "04_explore_complete.zip")
    rd = lambda n: Image.open(io.BytesIO(z.read("04_explore/" + n))).convert("RGBA")
    full = rd("assets/04_explore.png")
    sprite = rd("assets/05_blink_sprite.png")
    fw = sprite.size[0] // 9
    box = (478, 489, 807 - 478, 685 - 489)                      # rig.json eye_patch
    eyes = [sprite.crop((k * fw, 0, (k + 1) * fw, sprite.size[1])) for k in range(9)]
    # 包里给了闭眼检查帧：静态图 + 第 8 帧 必须等于它
    chk = full.copy(); chk.alpha_composite(eyes[8], box[:2])
    assert ndiff(chk, rd("assets/04_explore_closed.png")) == 0
    body = blink_role("explore", full, eyes, box)
    save_webp(head_icon(full, cx_frac=0.42), OUT / "explore" / "icon.webp")


def reading():
    print("reading (05)")
    h = (DOCS / "demo_standalone.html").read_text(encoding="utf-8")
    css = re.search(r"<style>(.*?)</style>", h, re.S).group(1)
    assert "mascot-05" in css
    def data_img(pat, src):
        d = re.search(pat, src).group(1).strip("\"'")
        return Image.open(io.BytesIO(base64.b64decode(d.split(",", 1)[1]))).convert("RGBA")
    sprite = data_img(r"mascot-05__eyes\{[^}]*?url\(([^)]*)\)", css)
    body_html = h[h.index("</style>"):]
    full = data_img(r'<img class="mascot-05__full mascot-05__fallback" src="([^"]*)"', body_html)
    assert full.size == (W, H)
    # 百分比照抄 05 的 mascot.css（left/top/width/height），换算回整数像素
    x, y = round(0.400152439024 * W), round(0.400333611343 * H)
    w, hh = round(0.293445121951 * W), round(0.185154295246 * H)
    fw = sprite.size[0] // 9
    assert (fw, sprite.size[1]) == (w, hh), (fw, sprite.size[1], w, hh)
    eyes = [sprite.crop((k * fw, 0, (k + 1) * fw, hh)) for k in range(9)]
    blink_role("reading", full, eyes, (x, y, w, hh))
    save_webp(head_icon(full, cx_frac=0.5, side_frac=0.6), OUT / "reading" / "icon.webp")


def static_role(name, label, png, icon_kw, body=None):
    """body：整只静态图用哪张（默认就是 PNG 本身；happy 用动图第 0 帧，见下）。"""
    print(f"{name} ({label})")
    full = Image.open(DOCS / png).convert("RGBA")
    assert full.size == (W, H)
    save_webp((body or full).resize((BODY_W, BODY_H), Image.LANCZOS), OUT / name / "body.webp")
    save_webp(head_icon(full, **icon_kw), OUT / name / "icon.webp")
    return full


def happy():
    anim = Image.open(DOCS / "02_happy_painter_transparent.webp")
    anim.seek(0); f0 = anim.convert("RGBA")
    # 静态 PNG 和动图第 0 帧的姿势差了四万多个像素：庆祝播完换回静态图会跳一下。
    # 所以 happy 的 body 用动图第 0 帧（播完正好停在它上面），PNG 只出头像。
    full = static_role("happy", "02", "02_欢乐彩绘小画家.png", dict(cx_frac=0.5, top_frac=0.1, side_frac=0.56), body=f0)
    # PIL 读不到每帧时长（都报 None），用 webpmux 的清单：74 帧 50ms + 23 帧 100ms = 6000ms
    durs = []
    import subprocess
    info = subprocess.run(["webpmux", "-info", str(DOCS / "02_happy_painter_transparent.webp")],
                          capture_output=True, text=True).stdout
    for line in info.splitlines():
        p = line.split()
        if p and re.fullmatch(r"\d+:", p[0]):
            durs.append(int(p[6]))
    assert len(durs) == anim.n_frames, (len(durs), anim.n_frames)
    starts = [sum(durs[:i]) for i in range(len(durs))]
    n = CHEER_FPS * CHEER_SEC
    picks = []
    for k in range(n):
        t = k * 1000 / CHEER_FPS
        i = max(j for j, s in enumerate(starts) if s <= t)
        picks.append(i)
    frames = []
    for i in picks:
        anim.seek(i); frames.append(anim.convert("RGBA").resize((CHEER_W, CHEER_H), Image.LANCZOS))
    print(f"  取 {n} 帧：{picks}")
    print(f"  动图第 0 帧 vs 静态 PNG 差异像素 {ndiff(f0, full)}；第 {picks[-1]} 帧 vs 第 0 帧 {ndiff(frames[-1], frames[0])}")
    rows = -(-n // CHEER_COLS)
    sheet = Image.new("RGBA", (CHEER_W * CHEER_COLS, CHEER_H * rows), (0, 0, 0, 0))
    for k, f in enumerate(frames):
        sheet.alpha_composite(f, ((k % CHEER_COLS) * CHEER_W, (k // CHEER_COLS) * CHEER_H))
    save_webp(sheet, OUT / "happy" / "cheer.webp", q=82)
    # CSS：steps 走格子。background-size = 列数×100% / 行数×100%
    print(f"  CSS .bd-cheer {{ background-size:{CHEER_COLS * 100}% {rows * 100}%; animation:bd-cheer {CHEER_SEC}s steps(1,end) 1 forwards; }}")
    print("  @keyframes bd-cheer {")
    for k in range(n):
        c, r = k % CHEER_COLS, k // CHEER_COLS
        px = c / (CHEER_COLS - 1) * 100 if CHEER_COLS > 1 else 0
        py = r / (rows - 1) * 100 if rows > 1 else 0
        print(f"    {k / n * 100:.4f}% {{ background-position:{px:.4f}% {py:.4f}%; }}")
    print("    100% { background-position:0% 0%; }")
    print("  }")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    happy()
    static_role("thinking", "03", "03_thinking.png", dict(cx_frac=0.55, side_frac=0.64))
    explore()
    reading()
    static_role("encourage", "06", "06_橙帽眨眼抱心萌球.png", dict(cx_frac=0.5, side_frac=0.62))


if __name__ == "__main__":
    sys.exit(main())
