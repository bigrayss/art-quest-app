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
# 每一格四周留 2px 透明缝。没有缝的话，精灵一做缩放动画（呼吸 / 戳一下），格子边缘的采样会把
# 隔壁那一格的像素渗进来——隔壁格的边缘是身体的不透明像素，于是屏幕上多出一条细线。
# 贴片的框也跟着外扩 2px（框 = 整格），所以 background-position 还是整齐的 0/20/40…%。
GUTTER = 2


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


def gutter_sheet(frames, cols):
    """把等大的帧铺成 cols 列的格子图，每格四周留 GUTTER 透明缝。返回 (sheet, 格宽, 格高)。"""
    fw, fh = frames[0].size
    cw, ch = fw + 2 * GUTTER, fh + 2 * GUTTER
    rows = -(-len(frames) // cols)
    sheet = Image.new("RGBA", (cw * cols, ch * rows), (0, 0, 0, 0))
    for k, f in enumerate(frames):
        sheet.alpha_composite(f, ((k % cols) * cw + GUTTER, (k // cols) * ch + GUTTER))
    return sheet, cw, ch


def css_box(sel, x, y, w, h, W_, H_):
    return f"  {sel} {{ left:{x / W_ * 100:.6f}%; top:{y / H_ * 100:.6f}%; width:{w / W_ * 100:.6f}%; height:{h / H_ * 100:.6f}%; }}"


def parts_role(name, frames_of, boxes, eye_timeline=False):
    """通用：frames_of(k) 给第 k 帧的**整只**原生尺寸图；boxes = {部件名: (x,y,w,h) 原图像素框}。
    每个部件：9 帧（eyes，走 bd-blink）或 30 帧（其余，走 bd-limb 3 秒）。
    先合成整图、整图缩小、再裁——贴片和身体是同一次缩放出来的，第 0 帧贴回去像素一样。"""
    m = 4
    body = None
    css = []
    for part, (x, y, w, h) in boxes.items():
        n = 9 if part == "eyes" else 30
        frames = [frames_of(part, k).resize((BODY_W, BODY_H), Image.LANCZOS) for k in range(n)]
        if body is None:
            body = frames[0]
        sx, sy = max(0, int(x * S) - m), max(0, int(y * S) - m)
        ex, ey = min(BODY_W, int((x + w) * S + 1) + m), min(BODY_H, int((y + h) * S + 1) + m)
        crops = [f.crop((sx, sy, ex, ey)) for f in frames]
        chk = body.copy(); chk.alpha_composite(crops[0], (sx, sy))
        assert ndiff(chk, body) == 0, f"{name}/{part}: 第 0 帧和身体对不上 ({ndiff(chk, body)})"
        sheet, cw, ch = gutter_sheet(crops, 9 if part == "eyes" else CHEER_COLS)
        save_webp(sheet, OUT / name / f"{part}.webp", q=90)
        css.append(css_box(f".bd-fig[data-role={name}] .bd-{part}", sx - GUTTER, sy - GUTTER, cw, ch, BODY_W, BODY_H))
    save_webp(body, OUT / name / "body.webp")
    print("\n".join(css))
    return body


def blink_role(name, full, eye_frames, box):
    """只眨眼的角色：整只静态图 + 9 帧眼睛贴片。"""
    def frames_of(part, k):
        f = full.copy(); f.alpha_composite(eye_frames[k], box[:2]); return f
    return parts_role(name, frames_of, {"eyes": box})


def explore():
    """04 有分层：身体（挖了眼睛和双脚）+ 放大镜手 + 另一只手 + 脚的 60 帧 + 眨眼 9 帧。
    两只手按 rig.json 绕各自的轴小幅转（±1.3° / ±2.6°，3 秒一周期），脚取每 2 帧一帧凑 30 帧。
    全部在原生尺寸合成整图再缩再裁，所以四块贴片之间、贴片和身体之间都严丝合缝。"""
    print("explore (04)")
    import math
    z = zipfile.ZipFile(DOCS / "04_explore_complete.zip")
    rd = lambda n: Image.open(io.BytesIO(z.read("04_explore/" + n))).convert("RGBA")
    body, mag, rest = rd("assets/01_body.png"), rd("assets/02_magnifier_hand.png"), rd("assets/03_rest_hand.png")
    sprite, feet_sheet = rd("assets/05_blink_sprite.png"), rd("assets/04_feet_motion.png")
    full = rd("assets/04_explore.png")
    eye_box = (478, 489, 807 - 478, 685 - 489)
    feet_box = (360, 837, 875 - 360, 1057 - 837)
    fw = sprite.size[0] // 9
    eyes = [sprite.crop((k * fw, 0, (k + 1) * fw, sprite.size[1])) for k in range(9)]
    fcw, fch = feet_sheet.size[0] // 8, feet_sheet.size[1] // 8
    feet = [feet_sheet.crop(((k % 8) * fcw, (k // 8) * fch, (k % 8 + 1) * fcw, (k // 8 + 1) * fch)) for k in range(60)]
    MAG_PIVOT, REST_PIVOT = (902, 688), (282, 744)            # rig.json
    def rot(layer, deg, pivot):
        # PIL 的 rotate 正角是逆时针；CSS rotate 正角是顺时针，所以取负
        return layer.rotate(-deg, resample=Image.BICUBIC, center=pivot)
    def frames_of(part, k):
        t = 0 if part == "eyes" else k / 30 * 3          # 秒
        ang = math.sin(2 * math.pi * t / 3)
        f = rot(rest, -2.6 * ang, REST_PIVOT)             # 另一只手在身体后面
        f.alpha_composite(body)
        f.alpha_composite(feet[(2 * k) % 60] if part != "eyes" else feet[0], feet_box[:2])
        f.alpha_composite(eyes[k] if part == "eyes" else eyes[0], eye_box[:2])
        f.alpha_composite(rot(mag, 1.3 * ang, MAG_PIVOT))
        return f
    # 自检：不转、第 0 帧 ≈ 包里的完整静态图（分层叠回去应该就是它）
    print(f"  分层叠回去 vs 04_explore.png 差异像素 {ndiff(frames_of('eyes', 0), full)}")
    # 手的框：各自 bbox 外扩，盖住 ±角度转出去的范围
    def box_of(layer, pad=18):
        b = layer.getbbox(); return (b[0] - pad, b[1] - pad, b[2] - b[0] + 2 * pad, b[3] - b[1] + 2 * pad)
    parts_role("explore", frames_of, {"eyes": eye_box, "feet": feet_box, "rest": box_of(rest), "mag": box_of(mag)})
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


def normal_rig():
    """normal 的三张帧图（门口 / 世界那张大图用的）：从 v2 包重出，**原生分辨率、不缩**（缩了补丁边界会露缝，
    见 static/art/buddy/README.md），只是每格加 2px 透明缝。身体 hero.webp 不动。"""
    print("normal (01) 帧图")
    z = zipfile.ZipFile(DOCS / "彩绘精灵_眨眼与手脚微动_v2.zip")
    rd = lambda n: Image.open(io.BytesIO(z.read("assets/" + n))).convert("RGBA")
    css = []
    for part, file, box, cols, rows in [("hand", "02_hand_motion.png", (931, 517, 1173, 795), 8, 8),
                                        ("feet", "03_feet_motion.png", (463, 807, 976, 1057), 8, 8)]:
        sheet = rd(file); x, y, x2, y2 = box; fw, fh = x2 - x, y2 - y
        assert sheet.size == (fw * cols, fh * rows), (part, sheet.size)
        frames = [sheet.crop(((k % cols) * fw, (k // cols) * fh, (k % cols + 1) * fw, (k // cols + 1) * fh)) for k in range(0, 60, 2)]
        out, cw, ch = gutter_sheet(frames, CHEER_COLS)
        save_webp(out, OUT / f"hero-{part}.webp", q=90)
        css.append(css_box(f".bd-{part}", x - GUTTER, y - GUTTER, cw, ch, W, H))
    eyes = rd("04_blink_sprite.png"); x, y, x2, y2 = 578, 489, 907, 685; fw = x2 - x
    frames = [eyes.crop((k * fw, 0, (k + 1) * fw, eyes.size[1])) for k in range(9)]
    out, cw, ch = gutter_sheet(frames, 9)
    save_webp(out, OUT / "hero-eyes.webp", q=90)
    css.append(css_box(".bd-eyes", x - GUTTER, y - GUTTER, cw, ch, W, H))
    print("\n".join(css))


def normal_body():
    """normal 的整只静态图（顶栏头像用）。normal 的头像 icon.webp 是硬裁的头部，底边切平，
    放在圆头像里像缺了一块——顶栏改用整只。原图就是 docs/橙色贝雷帽的开心小画家.png（= v2 包的 00_original）。"""
    print("normal (01) 整只")
    full = Image.open(DOCS / "橙色贝雷帽的开心小画家.png").convert("RGBA")
    assert full.size == (W, H)
    save_webp(full.resize((BODY_W, BODY_H), Image.LANCZOS), OUT / "normal" / "body.webp")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    normal_rig()
    normal_body()
    happy()
    static_role("thinking", "03", "03_thinking.png", dict(cx_frac=0.55, side_frac=0.64))
    explore()
    reading()
    static_role("encourage", "06", "06_橙帽眨眼抱心萌球.png", dict(cx_frac=0.5, side_frac=0.62))


if __name__ == "__main__":
    sys.exit(main())
