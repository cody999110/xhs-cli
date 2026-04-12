#!/usr/bin/env python3
"""重新生成 CLI 菜单的 SVG 截图（用于 README 展示）。

Usage:
    pip install rich
    python docs/render_cli_screenshot.py
"""

from pathlib import Path

from rich.console import Console
from rich.text import Text

BANNER = """\033[31m
     ╔═══════════════════════════════════════════╗
     ║                                           ║
     ║   📕  小 红 书  K O L  A g e n t          ║
     ║                                           ║
     ║   内容自动生成 · 智能互动 · AI 驱动       ║
     ║                                           ║
     ╚═══════════════════════════════════════════╝\033[0m
"""

DIVIDER = "\033[31m  ─────────────────────────────────────────────\033[0m"

MENU = f"""
{DIVIDER}
  \033[1m账号管理\033[0m
    [1] 🍪  从 Chrome 导入登录状态（推荐，免扫码）
    [2] 🔑  手动登录小红书主站（扫码）
    [3] 🔑  手动登录创作者平台（扫码）

  \033[1m内容创作\033[0m
    [4] 📝  生成笔记（仅保存本地）
    [5] 📤  生成笔记 + 发布到小红书

  \033[1m社区互动\033[0m
    [6] 📋  浏览笔记
    [7] 🤝  自动互动（点赞 + AI 评论）
    [8] ❤️   给指定笔记点赞
    [9] 💬  给指定笔记评论

  \033[1m工具\033[0m
    [t] 📂  查看主题池
    [0] 🚪  退出
{DIVIDER}

  请输入编号: """

if __name__ == "__main__":
    output = Path(__file__).parent / "cli-menu.svg"

    console = Console(record=True, width=60, force_terminal=True)
    console.print(Text.from_ansi(BANNER + MENU), end="")

    svg = console.export_svg(title="小红书 KOL Agent")
    output.write_text(svg, encoding="utf-8")
    print(f"Saved → {output}")
