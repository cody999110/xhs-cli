"""将 PostPlan 的每个 slide 渲染为小红书风格的图片。

使用 HTML/CSS 模板 + Playwright 截图，输出 1080x1440 (3:4) 的 PNG 图片。
模板分三类：封面、内容页、尾页，配色方案随机或由 AI 提示选择。
"""

from __future__ import annotations

import html as html_lib
import random
import re
from pathlib import Path
from string import Template

from src.config import DATA_DIR
from src.models import PostPlan, Slide
from src.utils.logger import logger

SLIDES_DIR = DATA_DIR / "slides"
WIDTH = 1080
HEIGHT = 1440

# ---------------------------------------------------------------------------
# 配色方案 — bg_solid 用于卡片外背景色
# ---------------------------------------------------------------------------

COLOR_SCHEMES = [
    {
        "name": "蜜桃粉",
        "bg": "linear-gradient(160deg, #FADADD 0%, #F8AFA6 50%, #F4978E 100%)",
        "card_bg": "rgba(255,255,255,0.88)",
        "accent": "#E84057",
        "text": "#3D1E1E",
        "subtitle": "#6B3A3A",
        "num_bg": "#E84057",
    },
    {
        "name": "薄荷绿",
        "bg": "linear-gradient(160deg, #D4F1E3 0%, #95DAB6 50%, #6BC89A 100%)",
        "card_bg": "rgba(255,255,255,0.88)",
        "accent": "#1B8A5A",
        "text": "#1A3327",
        "subtitle": "#2D5E45",
        "num_bg": "#1B8A5A",
    },
    {
        "name": "奶油橘",
        "bg": "linear-gradient(160deg, #FFE0B2 0%, #FFB74D 50%, #FFA726 100%)",
        "card_bg": "rgba(255,255,255,0.90)",
        "accent": "#E65100",
        "text": "#3E2723",
        "subtitle": "#5D4037",
        "num_bg": "#E65100",
    },
    {
        "name": "薰衣草",
        "bg": "linear-gradient(160deg, #E8D5F5 0%, #CE93D8 50%, #AB47BC 100%)",
        "card_bg": "rgba(255,255,255,0.88)",
        "accent": "#7B1FA2",
        "text": "#2E1437",
        "subtitle": "#4A2660",
        "num_bg": "#7B1FA2",
    },
    {
        "name": "天空蓝",
        "bg": "linear-gradient(160deg, #BBDEFB 0%, #64B5F6 50%, #42A5F5 100%)",
        "card_bg": "rgba(255,255,255,0.88)",
        "accent": "#1565C0",
        "text": "#0D2744",
        "subtitle": "#1A4A73",
        "num_bg": "#1565C0",
    },
    {
        "name": "柠檬黄",
        "bg": "linear-gradient(160deg, #FFF9C4 0%, #FFF176 50%, #FFEE58 100%)",
        "card_bg": "rgba(255,255,255,0.90)",
        "accent": "#F57F17",
        "text": "#33301A",
        "subtitle": "#5D4E1F",
        "num_bg": "#F57F17",
    },
    {
        "name": "莫兰迪灰",
        "bg": "linear-gradient(160deg, #EFEBE9 0%, #D7CCC8 50%, #BCAAA4 100%)",
        "card_bg": "rgba(255,255,255,0.85)",
        "accent": "#6D4C41",
        "text": "#3E2723",
        "subtitle": "#5D4037",
        "num_bg": "#6D4C41",
    },
]

# ---------------------------------------------------------------------------
# HTML 模板（使用 $var 语法避免 CSS {} 冲突）
# ---------------------------------------------------------------------------

COVER_TMPL = Template("""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    width: ${W}px; height: ${H}px;
    background: $bg;
    font-family: "PingFang SC", "Noto Sans SC", "Hiragino Sans GB", sans-serif;
    display: flex; flex-direction: column;
    justify-content: center; align-items: center;
    overflow: hidden; position: relative;
}
.deco-circle-1 {
    position: absolute; top: -120px; right: -100px;
    width: 380px; height: 380px; border-radius: 50%;
    background: rgba(255,255,255,0.15);
}
.deco-circle-2 {
    position: absolute; bottom: -80px; left: -60px;
    width: 280px; height: 280px; border-radius: 50%;
    background: rgba(255,255,255,0.12);
}
.card {
    position: absolute;
    top: 56px; left: 56px; right: 56px; bottom: 56px;
    background: $card_bg;
    border-radius: 36px;
    padding: 80px 64px;
    display: flex; flex-direction: column;
    justify-content: center; align-items: center;
    text-align: center;
    box-shadow: 0 8px 40px rgba(0,0,0,0.08);
    z-index: 1;
}
.badge {
    display: inline-block;
    background: $accent; color: #fff;
    padding: 12px 36px; border-radius: 50px;
    font-size: 26px; font-weight: 600;
    letter-spacing: 3px; margin-bottom: 48px;
}
.title {
    font-size: 68px; font-weight: 900;
    color: $text_color; line-height: 1.4;
    margin-bottom: 36px;
}
.divider {
    width: 60px; height: 5px; border-radius: 3px;
    background: $accent; margin: 0 auto 36px;
}
.subtitle {
    font-size: 34px; color: $subtitle_color;
    line-height: 1.8; font-weight: 500;
}
.footer {
    position: absolute; bottom: 72px;
    font-size: 22px; color: rgba(255,255,255,0.7);
    letter-spacing: 3px; z-index: 2;
}
</style></head><body>
<div class="deco-circle-1"></div>
<div class="deco-circle-2"></div>
<div class="card">
    <div class="badge">$badge</div>
    <div class="title">$title_text</div>
    <div class="divider"></div>
    <div class="subtitle">$subtitle_text</div>
</div>
<div class="footer">$deco</div>
</body></html>""")

CONTENT_TMPL = Template("""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    width: ${W}px; height: ${H}px;
    background: $bg;
    font-family: "PingFang SC", "Noto Sans SC", "Hiragino Sans GB", sans-serif;
    overflow: hidden; position: relative;
}
.deco-circle {
    position: absolute; top: -60px; left: -80px;
    width: 260px; height: 260px; border-radius: 50%;
    background: rgba(255,255,255,0.12);
}
.page-num {
    position: absolute; top: 52px; right: 56px;
    width: 64px; height: 64px; border-radius: 50%;
    background: $num_bg; color: #fff;
    font-size: 28px; font-weight: 700;
    display: flex; justify-content: center; align-items: center;
    z-index: 2;
}
.card {
    position: absolute;
    top: 56px; left: 56px; right: 56px; bottom: 56px;
    background: $card_bg;
    border-radius: 36px;
    padding: 80px 56px 64px;
    display: flex; flex-direction: column;
    box-shadow: 0 8px 40px rgba(0,0,0,0.08);
    z-index: 1;
}
.header {
    text-align: center;
    padding: 20px 0 0;
}
.slide-title {
    font-size: 54px; font-weight: 900;
    color: $text_color; text-align: center;
    line-height: 1.35; margin-bottom: 32px;
}
.accent-line {
    width: 56px; height: 5px; border-radius: 3px;
    background: $accent; margin: 0 auto 0;
}
.content-area {
    flex: 1;
    display: flex; flex-direction: column;
    justify-content: flex-start;
    padding: 40px 12px 0;
}
.caption {
    font-size: 34px; color: $subtitle_color;
    line-height: 2.05; text-align: left;
    width: 100%; word-break: break-word;
    font-weight: 450;
}
.caption .hl {
    color: $accent; font-weight: 700;
}
.tip-box {
    margin-top: auto;
    padding: 28px 32px;
    background: rgba($accent_r, $accent_g, $accent_b, 0.07);
    border-radius: 20px;
    border-left: 5px solid $accent;
}
.tip-label {
    font-size: 22px; color: $accent;
    font-weight: 700; margin-bottom: 8px;
    letter-spacing: 2px;
}
.tip-content {
    font-size: 28px; color: $subtitle_color;
    line-height: 1.7;
}
</style></head><body>
<div class="deco-circle"></div>
<div class="page-num">$page_num</div>
<div class="card">
    <div class="header">
        <div class="slide-title">$slide_title</div>
        <div class="accent-line"></div>
    </div>
    <div class="content-area">
        <div class="caption">$caption_html</div>
    </div>
    <div class="tip-box">
        <div class="tip-label">$tip_label</div>
        <div class="tip-content">$tip_text</div>
    </div>
</div>
</body></html>""")

ENDING_TMPL = Template("""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    width: ${W}px; height: ${H}px;
    background: $bg;
    font-family: "PingFang SC", "Noto Sans SC", "Hiragino Sans GB", sans-serif;
    display: flex; flex-direction: column;
    justify-content: center; align-items: center;
    overflow: hidden; position: relative;
}
.deco-circle-1 {
    position: absolute; bottom: -100px; right: -80px;
    width: 320px; height: 320px; border-radius: 50%;
    background: rgba(255,255,255,0.15);
}
.deco-circle-2 {
    position: absolute; top: -60px; left: -40px;
    width: 200px; height: 200px; border-radius: 50%;
    background: rgba(255,255,255,0.10);
}
.card {
    position: absolute;
    top: 56px; left: 56px; right: 56px; bottom: 56px;
    background: $card_bg;
    border-radius: 36px;
    padding: 80px 64px;
    display: flex; flex-direction: column;
    justify-content: center; align-items: center;
    text-align: center;
    box-shadow: 0 8px 40px rgba(0,0,0,0.08);
    z-index: 1;
}
.emoji { font-size: 80px; margin-bottom: 40px; }
.title {
    font-size: 60px; font-weight: 900;
    color: $text_color; line-height: 1.4;
    margin-bottom: 32px;
}
.divider {
    width: 56px; height: 5px; border-radius: 3px;
    background: $accent; margin: 0 auto 32px;
}
.caption {
    font-size: 32px; color: $subtitle_color;
    line-height: 1.8; margin-bottom: 56px;
    font-weight: 450;
}
.actions { display: flex; gap: 20px; justify-content: center; }
.action-btn {
    background: $accent; color: #fff;
    padding: 20px 48px; border-radius: 50px;
    font-size: 30px; font-weight: 600;
}
.action-btn.outline {
    background: transparent;
    border: 3px solid $accent; color: $accent;
}
.hint {
    margin-top: 40px;
    font-size: 24px; color: rgba(0,0,0,0.3);
    letter-spacing: 2px;
}
</style></head><body>
<div class="deco-circle-1"></div>
<div class="deco-circle-2"></div>
<div class="card">
    <div class="emoji">$emoji</div>
    <div class="title">$title_text</div>
    <div class="divider"></div>
    <div class="caption">$caption_text</div>
    <div class="actions">
        <div class="action-btn">❤️ 点赞</div>
        <div class="action-btn">⭐ 收藏</div>
        <div class="action-btn outline">＋ 关注</div>
    </div>
    <div class="hint">你的支持是我更新的动力 ✨</div>
</div>
</body></html>""")


# ---------------------------------------------------------------------------
# 渲染逻辑
# ---------------------------------------------------------------------------

def _esc(text: str) -> str:
    return html_lib.escape(text).replace("\n", "<br>")


def _highlight_quotes(text: str) -> str:
    """把「」包裹的文字用 <span class="hl"> 高亮。"""
    escaped = _esc(text)
    return re.sub(r"「(.+?)」", r'<span class="hl">「\1」</span>', escaped)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


_TIP_LABELS = ["💡 划重点", "⚡ 小贴士", "📌 敲黑板", "✨ 要点", "🔑 关键"]


def _make_tip(caption: str, index: int) -> tuple[str, str]:
    """从 caption 中提取最后一句或生成一句简短的提示语。"""
    label = _TIP_LABELS[index % len(_TIP_LABELS)]
    sentences = re.split(r"[。！？~～]", caption)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 4]
    if sentences:
        tip = sentences[-1]
        if not tip.endswith(("。", "！", "～")):
            tip += " ✅"
    else:
        tip = "记得收藏备用哦～"
    return label, tip


def _base_vars(scheme: dict) -> dict:
    r, g, b = _hex_to_rgb(scheme["accent"])
    return {
        "W": str(WIDTH),
        "H": str(HEIGHT),
        "bg": scheme["bg"],
        "card_bg": scheme["card_bg"],
        "accent": scheme["accent"],
        "text_color": scheme["text"],
        "subtitle_color": scheme["subtitle"],
        "num_bg": scheme.get("num_bg", scheme["accent"]),
        "accent_r": str(r),
        "accent_g": str(g),
        "accent_b": str(b),
    }


def render_slides(plan: PostPlan, scheme: dict | None = None) -> list[Path]:
    """将 PostPlan 渲染为一组 PNG 图片（1080x1440）。"""
    if scheme is None:
        scheme = random.choice(COLOR_SCHEMES)
    logger.info(f"使用配色方案「{scheme['name']}」渲染 {len(plan.slides)} 张 slide")

    SLIDES_DIR.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    paths: list[Path] = []
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})

    try:
        for i, slide in enumerate(plan.slides):
            is_cover = (i == 0)
            is_ending = (i == len(plan.slides) - 1)

            html_content = _build_html(slide, plan, i, scheme, is_cover, is_ending)

            page.set_content(html_content, wait_until="networkidle")
            out_path = SLIDES_DIR / f"slide_{i + 1:02d}.png"
            page.screenshot(path=str(out_path), type="png")
            paths.append(out_path)
            logger.debug(f"  渲染 slide {i + 1}: {out_path.name}")
    finally:
        browser.close()
        pw.stop()

    logger.info(f"渲染完成: {len(paths)} 张图片 → {SLIDES_DIR}")
    return paths


def _build_html(
    slide: Slide,
    plan: PostPlan,
    index: int,
    scheme: dict,
    is_cover: bool,
    is_ending: bool,
) -> str:
    base = _base_vars(scheme)

    if is_cover:
        title_parts = plan.title.split("｜")
        main_title = title_parts[0].strip()
        sub = title_parts[1].strip() if len(title_parts) > 1 else slide.caption[:50]
        return COVER_TMPL.substitute(
            **base,
            badge="干货分享",
            title_text=_esc(main_title),
            subtitle_text=_esc(sub),
            deco="左滑查看更多 →",
        )

    if is_ending:
        return ENDING_TMPL.substitute(
            **base,
            emoji="🌟",
            title_text=_esc(slide.slide_title or "觉得有用就收藏吧"),
            caption_text=_esc(slide.caption or "关注我，持续分享更多干货～"),
        )

    tip_label, tip_text = _make_tip(slide.caption, index)
    return CONTENT_TMPL.substitute(
        **base,
        page_num=f"{index + 1:02d}",
        slide_title=_esc(slide.slide_title),
        caption_html=_highlight_quotes(slide.caption),
        tip_label=_esc(tip_label),
        tip_text=_esc(tip_text),
    )
