#!/usr/bin/env python3
"""小红书 KOL Agent — CLI 入口。

直接运行 `python run.py` 进入交互式菜单。
也可通过命令行参数直接执行指定操作（适合脚本/定时任务）。
"""

import argparse
import sys


def main():
    if len(sys.argv) == 1:
        from src.cli import interactive_menu
        interactive_menu()
        return

    parser = argparse.ArgumentParser(
        description="小红书 KOL Agent — 内容自动生成 & 智能互动\n"
                    "直接运行 python run.py 进入交互式菜单",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # --- Auth ---
    parser.add_argument("--import-cookies", action="store_true",
                        help="从本地 Chrome 导入小红书登录状态（免扫码）")
    parser.add_argument("--login", action="store_true", help="登录小红书主站（浏览/互动用）")
    parser.add_argument("--login-creator", action="store_true", help="登录创作者平台（发帖用）")

    # --- Content generation ---
    parser.add_argument("topic", nargs="?", help="笔记主题 (e.g. '波士顿租房攻略')")
    parser.add_argument("--random", action="store_true", help="从主题池随机选一个主题")
    parser.add_argument("--list", action="store_true", help="列出所有可用主题")
    parser.add_argument("--publish", action="store_true", help="生成后自动发布到小红书")
    parser.add_argument("--render-slides", action="store_true",
                        help="用 HTML 模板渲染笔记风格图片（而非搜索素材图）")

    # --- Engagement ---
    parser.add_argument("--browse", action="store_true", help="浏览小红书笔记")
    parser.add_argument("--keyword", default="", help="搜索关键词 (配合 --browse / --engage)")
    parser.add_argument("--engage", action="store_true", help="自动浏览笔记并点赞+评论")
    parser.add_argument("--count", type=int, default=5, help="互动笔记数量 (默认 5)")
    parser.add_argument("--like-only", action="store_true", help="仅点赞，不评论")
    parser.add_argument("--like", metavar="NOTE_ID", help="给指定笔记点赞")
    parser.add_argument("--comment", metavar="NOTE_ID", help="给指定笔记评论")
    parser.add_argument("-m", "--message", default="", help="自定义评论内容 (配合 --comment)")

    args = parser.parse_args()

    # --- Dispatch ---

    if args.import_cookies:
        from src.publisher.chrome_cookies import save_chrome_cookies_to_file
        from src.publisher.xhs_client import COOKIES_FILE
        count = save_chrome_cookies_to_file(COOKIES_FILE)
        if count > 0:
            print(f"✅ 成功从 Chrome 导入 {count} 条 Cookie!")
        else:
            print("⚠️  未找到 Cookie，请先在 Chrome 中登录小红书")
        return

    if args.login:
        from src.publisher.xhs_client import XHSClient
        client = XHSClient(headless=False)
        try:
            client.login()
            print("✅ 主站登录成功! Cookie 已保存。")
        finally:
            client.close()
        return

    if args.login_creator:
        from src.publisher.xhs_client import XHSClient
        client = XHSClient(headless=False)
        try:
            client.login_creator()
            print("✅ 创作者平台登录成功! Cookie 已保存。")
        finally:
            client.close()
        return

    if args.list:
        from src.agent import list_topics
        list_topics()
        return

    if args.browse:
        from src.engager import browse_notes
        browse_notes(keyword=args.keyword)
        return

    if args.engage:
        from src.engager import engage
        engage(
            count=args.count,
            like_only=args.like_only,
            keyword=args.keyword,
        )
        return

    if args.like is not None:
        from src.engager import like_single_note
        like_single_note(args.like)
        return

    if args.comment is not None:
        from src.engager import comment_single_note
        comment_single_note(args.comment, content=args.message)
        return

    if args.random:
        from src.agent import pick_random_topic, run
        topic = pick_random_topic()
        run(topic, publish=args.publish, render_slides=args.render_slides)
        return

    if args.topic:
        from src.agent import run
        run(args.topic, publish=args.publish, render_slides=args.render_slides)
        return

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
