#!/usr/bin/env python3
"""新报告素材校准管线（ADR-0019 素材调整，一次性/可重跑）。

对三张 uidesign 新素材做两件处理，保证与纸色 #fffdf9 融合、打印画质不损失：
1. 白点缩放（white-point scaling）：按角点实测底色等比提亮到目标色，
   水彩笔触颜色按比例保留，不做逐像素硬替换（避免边缘锯齿）。
2. 横条自动裁中间内容带：原图 1774x887 但笔刷只在中间约 1/6 高度，
   按「与底色偏差超过阈值」的行自动定位裁剪（含少量留白边）。

用法：python3 scripts/calibrate_assets.py
输入：/home/gitclone/BeingDoing/uidesign/report/{封面背景图,阅读指南页的横条,一页信}.png
输出：src/report-renderer/assets/report-assets/ 下对应文件（覆盖封面 A；新增两个装饰素材）
"""

from pathlib import Path
from statistics import median

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = REPO_ROOT / "uidesign" / "report"
OUT_DIR = Path(__file__).resolve().parents[1] / "assets" / "report-assets"
# 设计母版（只读）：拷贝类素材的源
MASTER_ASSETS_DIR = REPO_ROOT / "report" / "xunlu" / "public" / "report-assets"

# 抠图素材（用户外制，背景已抠干净的 RGBA 原图）：直接拷贝使用，不做任何处理
CUTOUT_DIR = REPO_ROOT / "report" / "抠图"
CUTOUT_ASSETS = {
    "hero-watercolor-a4-抠图.png": "hero-watercolor-a4.png",
    "footer-sailboat-a4-抠图.png": "footer-sailboat-a4.png",
    "logo-mark-a4-抠图.png": "logo-mark-a4.png",
    "footer-mark-a-path-seal-抠图.png": "footer-marks/footer-mark-a-path-seal.png",
    "guide-brush-bar-抠图.png": "editorial/guide-brush-bar.png",
    "letter-frame-抠图.png": "editorial/letter-frame.png",
}
# 抠图后需要裁掉透明边缘的（如水印原图带大块透明画布）
CUTOUT_TRIM_ASSETS = {
    "openlife-水印-抠图.png": "brand/watermark-logo.png",
}

# 需要从母版拷贝并做 Color-to-Alpha 透明化的装饰素材（趴在纸色上、矩形边界会露馅的类）
# 封面/八卡片不做：封面全幅无缝可谈，卡片自带边框是独立物件
# 注意：hero/帆船/logo-mark/页脚标识A 已有抠图素材（见 CUTOUT_ASSETS），不在此列
ALPHA_FROM_MASTER = [
    *[
        f"module-trims/{name}"
        for name in [
            "module-01-career-framework-trim-v2.png",
            "module-02-values-center-trim-v1.png",
            "module-02-values-center-vertical-v2.png",
            "module-03-strengths-growth-trim-v1.png",
            "module-04-passion-rhythm-trim-v1.png",
            "module-04-passion-rhythm-vertical-v2.png",
            "module-05-mission-direction-trim-v1.png",
            "module-06-choice-convergence-trim-v1.png",
            "module-06-choice-convergence-vertical-v2.png",
            "module-07-insights-synthesis-trim-v1.png",
            "module-08-archetype-strata-trim-v1.png",
            "module-08-archetype-strata-vertical-v2.png",
        ]
    ],
    "signatures/signature-01.png",
    "signatures/signature-02.png",
    "signatures/signature-03.png",
    "footer-marks/footer-mark-b-compass-needle.png",
    "footer-marks/footer-mark-c-time-strata.png",
]

PAPER = (255, 253, 249)  # 页面纸色：封面（全幅页面背景）白点校准到此色；
# 装饰素材（横条/信件框）则以此色为键做 Color-to-Alpha 透明化——页面平色直接透出，
# 彻底消灭「图底 vs 纸色」的色差（实测 Chrome 打印对 ICC 图片有 1-2 级色偏，
# 不透明素材只能逼近、透明化才能相等）


def measure_bg(im: Image.Image) -> tuple:
    """取四角 20x20 区域的中位色作为底色实测值。"""
    rgb = im.convert("RGB")
    w, h = rgb.size
    samples = []
    for cx, cy in [(0, 0), (w - 20, 0), (0, h - 20), (w - 20, h - 20)]:
        region = rgb.crop((cx, cy, cx + 20, cy + 20))
        pixels = list(region.getdata())
        samples.append(tuple(int(median(c[i] for c in pixels)) for i in range(3)))
    return tuple(int(median(s[i] for s in samples)) for i in range(3))


def white_point_scale(im: Image.Image, target: tuple) -> Image.Image:
    """按实测底色把整图等比缩放到目标色（水彩笔触比例保留）。"""
    rgb = im.convert("RGB")
    bg = measure_bg(rgb)
    gains = [target[i] / max(1, bg[i]) for i in range(3)]
    lut = []
    for g in gains:
        lut.extend(min(255, round(v * g)) for v in range(256))
    out = rgb.point(lut)
    print(f"  底色实测 {bg} → 目标 {target}（增益 {[round(g, 4) for g in gains]}）")
    return out


def color_to_alpha(im: Image.Image, key: tuple) -> Image.Image:
    """以 key 色为键做 Color-to-Alpha（GIMP 同色算法的 numpy 版）。

    原理：alpha = 各通道「像素与键色的归一化距离」最大值；再对颜色做反预乘
    （un-premultiply），使合成回键色背景时数学上还原原像素。淡彩水洗区变半透明，
    页面纸色直接透出，融合效果等同真实水彩印在纸上。
    """
    rgb = np.asarray(im.convert("RGB"), dtype=np.float32)
    k = np.array(key, dtype=np.float32)
    lower = (k - rgb) / k
    denom = 255.0 - k
    upper = np.divide(rgb - k, denom, out=np.zeros_like(rgb), where=denom != 0)
    alpha = np.clip(np.where(rgb < k, lower, upper).max(axis=2), 0.0, 1.0)
    safe = np.maximum(alpha, 1e-6)[..., None]
    out_rgb = np.clip(k + (rgb - k) / safe, 0, 255)
    rgba = np.dstack([out_rgb, alpha * 255.0]).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def crop_content_band(im: Image.Image, row_threshold: float = 0.02, pad: int = 24) -> Image.Image:
    """按行内容占比自动定位中间内容带并裁剪（上下各留 pad px）。"""
    rgb = im.convert("RGB")
    bg = measure_bg(rgb)
    w, h = rgb.size
    pixels = rgb.load()
    top, bottom = None, None
    for y in range(h):
        deviated = sum(
            1 for x in range(0, w, 4)
            if sum(abs(pixels[x, y][i] - bg[i]) for i in range(3)) > 24
        ) / (w / 4)
        if deviated > row_threshold:
            if top is None:
                top = y
            bottom = y
    if top is None:
        raise SystemExit("未检测到内容带")
    top = max(0, top - pad)
    bottom = min(h, bottom + pad)
    print(f"  内容带 y={top}..{bottom}（原高 {h}）")
    return rgb.crop((0, top, w, bottom))


def main() -> None:
    # 1. 封面：全幅页面背景 → 校准到纸色，替换当前封面 A（代码逻辑不变）
    print("[1/3] 封面背景图 → cover-a-quiet-horizon.png")
    cover = Image.open(SRC_DIR / "封面背景图.png")
    white_point_scale(cover, PAPER).save(OUT_DIR / "cover-options" / "cover-a-quiet-horizon.png")

    # 2. 抠图素材：背景已抠净的 RGBA 原图，直接拷贝使用（页面 CSS 纸色自然透出）
    print("[2/3] 抠图素材直接拷贝（report/抠图/）")
    import shutil

    for src_name, dst_rel in CUTOUT_ASSETS.items():
        src = CUTOUT_DIR / src_name
        dst = OUT_DIR / dst_rel
        if not src.is_file():
            print(f"  跳过（抠图缺失）: {src_name}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        print(f"  {src_name} → {dst_rel}")
    for src_name, dst_rel in CUTOUT_TRIM_ASSETS.items():
        src = CUTOUT_DIR / src_name
        dst = OUT_DIR / dst_rel
        if not src.is_file():
            print(f"  跳过（抠图缺失）: {src_name}")
            continue
        im = Image.open(src).convert("RGBA")
        bbox = im.getbbox()
        if bbox:
            im = im.crop(bbox)
        dst.parent.mkdir(parents=True, exist_ok=True)
        im.save(dst)
        print(f"  {src_name} → {dst_rel}（裁透明边 {im.size}）")

    # 3. 母版拷贝类装饰素材：重新从母版拷贝（保证可重跑）并做 Color-to-Alpha 透明化
    print("[3/3] 母版装饰素材透明化（边饰/签名/页脚标识BC）")
    for rel in ALPHA_FROM_MASTER:
        src = MASTER_ASSETS_DIR / rel
        dst = OUT_DIR / rel
        if not src.is_file():
            print(f"  跳过（母版缺失）: {rel}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        color_to_alpha(Image.open(dst), PAPER).save(dst)
        print(f"  {rel}")

    print("完成。产物：")
    for f in ["cover-options/cover-a-quiet-horizon.png", "editorial/guide-brush-bar.png", "editorial/letter-frame.png"]:
        p = OUT_DIR / f
        print(f"  {f}: {Image.open(p).size}")


if __name__ == "__main__":
    main()
