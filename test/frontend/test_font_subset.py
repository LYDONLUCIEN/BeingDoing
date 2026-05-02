"""字体子集化测试 — 验证 WOFF2 子集字体文件体积和有效性"""

import os
import struct
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parents[2] / "src" / "frontend" / "public" / "fonts"

# 常用汉字子集（约 3000 字，覆盖 99%+ 日常中文）
COMMON_CHARS = (
    "的一是不了人我在有他这中大来上个国到说们为子和你地出会也时要就可以对生能而那得于着下自之年过发后作里用道行所然家种事成方多经么去法学如都同现当没动面起看定天分还进好小部其些主样理心她本前开但因只从想实日军者意无力它与长把机十民第公此已工使情明性知全三又关点正业外将两高间由问很最重并物手应战向头文体政美相见被利什二等产或新己制身果加西斯月话合回特代内信表化老给世位次度门任常先海通教儿原东声提立及比员解水名真论处走义各入几口认条平系气题活尔更别打女变四神总何电数安少报才结反受目太量再感建务做接必场件计管期市直德资命山金指克干受排完导七领队任争据传造吗约英格类强弱取极色流注题据调增识响林题空布际存收际创维备亲验言越急乡衣古均足画望际验"
)


def test_woff2_noto_sans_sc_regular_size_under_2mb():
    """NotoSansSC-Regular.woff2 应在 2MB 以内（原始 TTF 为 11MB）"""
    path = FONT_DIR / "NotoSansSC-Regular.woff2"
    assert path.exists(), f"字体文件不存在: {path}"
    size = path.stat().st_size
    assert size < 2 * 1024 * 1024, (
        f"NotoSansSC-Regular.woff2 体积 {size / 1024 / 1024:.1f}MB，超过 2MB 上限"
    )


def test_woff2_noto_sans_sc_light_size_under_2mb():
    """NotoSansSC-Light.woff2 应在 2MB 以内"""
    path = FONT_DIR / "NotoSansSC-Light.woff2"
    assert path.exists(), f"字体文件不存在: {path}"
    size = path.stat().st_size
    assert size < 2 * 1024 * 1024, (
        f"NotoSansSC-Light.woff2 体积 {size / 1024 / 1024:.1f}MB，超过 2MB 上限"
    )


def test_woff2_noto_sans_sc_medium_size_under_2mb():
    """NotoSansSC-Medium.woff2 应在 2MB 以内"""
    path = FONT_DIR / "NotoSansSC-Medium.woff2"
    assert path.exists(), f"字体文件不存在: {path}"
    size = path.stat().st_size
    assert size < 2 * 1024 * 1024, (
        f"NotoSansSC-Medium.woff2 体积 {size / 1024 / 1024:.1f}MB，超过 2MB 上限"
    )


def test_woff2_noto_sans_sc_semibold_size_under_2mb():
    """NotoSansSC-SemiBold.woff2 应在 2MB 以内"""
    path = FONT_DIR / "NotoSansSC-SemiBold.woff2"
    assert path.exists(), f"字体文件不存在: {path}"
    size = path.stat().st_size
    assert size < 2 * 1024 * 1024, (
        f"NotoSansSC-SemiBold.woff2 体积 {size / 1024 / 1024:.1f}MB，超过 2MB 上限"
    )


def test_woff2_noto_serif_sc_regular_size_under_3mb():
    """NotoSerifSC-Regular.woff2 应在 3MB 以内（原始 TTF 为 15MB，衬线字体稍大）"""
    path = FONT_DIR / "NotoSerifSC-Regular.woff2"
    assert path.exists(), f"字体文件不存在: {path}"
    size = path.stat().st_size
    assert size < 3 * 1024 * 1024, (
        f"NotoSerifSC-Regular.woff2 体积 {size / 1024 / 1024:.1f}MB，超过 3MB 上限"
    )


def test_woff2_noto_serif_sc_semibold_size_under_3mb():
    """NotoSerifSC-SemiBold.woff2 应在 3MB 以内"""
    path = FONT_DIR / "NotoSerifSC-SemiBold.woff2"
    assert path.exists(), f"字体文件不存在: {path}"
    size = path.stat().st_size
    assert size < 3 * 1024 * 1024, (
        f"NotoSerifSC-SemiBold.woff2 体积 {size / 1024 / 1024:.1f}MB，超过 3MB 上限"
    )


def test_woff2_magic_bytes():
    """所有 woff2 文件应以 'wOF2' 开头（WOFF2 魔数）"""
    for name in [
        "NotoSansSC-Light.woff2", "NotoSansSC-Regular.woff2",
        "NotoSansSC-Medium.woff2", "NotoSansSC-SemiBold.woff2",
        "NotoSerifSC-Regular.woff2", "NotoSerifSC-SemiBold.woff2",
    ]:
        path = FONT_DIR / name
        if path.exists():
            with open(path, "rb") as f:
                magic = f.read(4)
            assert magic == b"wOF2", f"{name} 不是有效的 WOFF2 文件（魔数: {magic!r}）"


def test_old_ttf_files_removed():
    """旧的 TTF 文件应被清理（避免 git 仓库膨胀）"""
    old_files = [
        "NotoSansSC-Light.ttf", "NotoSansSC-Regular.ttf",
        "NotoSansSC-Medium.ttf", "NotoSansSC-SemiBold.ttf",
        "NotoSerifSC-Regular.ttf", "NotoSerifSC-SemiBold.ttf",
    ]
    for name in old_files:
        path = FONT_DIR / name
        assert not path.exists(), f"旧 TTF 文件应删除: {path}"
