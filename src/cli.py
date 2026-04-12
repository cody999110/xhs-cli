"""小红书 KOL Agent 交互式 CLI 菜单。"""

from __future__ import annotations

import sys


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
"""


def _input(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"  {prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return val or default


def _input_int(prompt: str, default: int) -> int:
    raw = _input(prompt, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def _choose(prompt: str, options: list[str], default: str = "") -> str:
    options_str = " / ".join(options)
    return _input(f"{prompt} ({options_str})", default)


def _do_import_chrome() -> None:
    from src.publisher.chrome_cookies import save_chrome_cookies_to_file
    from src.publisher.xhs_client import COOKIES_FILE

    print("\n  正在从本地 Chrome 浏览器读取小红书 Cookie...")
    print("  （请确保你已经在 Chrome 里登录了小红书和创作者平台）\n")
    try:
        count = save_chrome_cookies_to_file(COOKIES_FILE)
        if count > 0:
            print(f"\n  ✅ 成功导入 {count} 条 Cookie!")
            print("  主站和创作者平台的登录状态都已同步")
            print("  现在可以直接使用「生成+发布」和「互动」功能了\n")
        else:
            print("\n  ⚠️  Chrome 中未找到小红书 Cookie")
            print("  请先在 Chrome 浏览器中登录 www.xiaohongshu.com 和 creator.xiaohongshu.com")
            print("  然后重新执行此操作\n")
    except FileNotFoundError as e:
        print(f"\n  ⚠️  {e}")
    except RuntimeError as e:
        print(f"\n  ⚠️  {e}")
    except Exception as e:
        print(f"\n  ❌ 导入失败: {e}")
        print("  如果 Chrome 正在运行，这是正常的（数据库可能被锁定）")
        print("  你也可以使用选项 [2]/[3] 手动扫码登录\n")


def _do_login_main() -> None:
    from src.publisher.xhs_client import XHSClient

    print("\n  将打开浏览器窗口，请登录小红书主站...\n")
    client = XHSClient(headless=False)
    try:
        client.login()
        print("\n  ✅ 主站登录成功! Cookie 已保存\n")
    finally:
        client.close()


def _do_login_creator() -> None:
    from src.publisher.xhs_client import XHSClient

    print("\n  将打开浏览器窗口，请登录小红书创作者平台...")
    print("  支持：扫码 / 手机验证码 / 密码登录\n")
    client = XHSClient(headless=False)
    try:
        client.login_creator()
        print("\n  ✅ 创作者平台登录成功! Cookie 已保存")
        print("  现在可以使用「生成+发布」功能了\n")
    finally:
        client.close()


def _do_generate(publish: bool = False) -> None:
    from src.agent import pick_random_topic, run

    print()
    topic = _input("输入主题（留空则随机选题）")
    if not topic:
        topic = pick_random_topic()
        print(f"  → 随机选题: {topic}")

    print()
    print("  选择图片模式:")
    print("    [1] 🖼️  素材图 — 从 Unsplash/Pexels 搜索配图")
    print("    [2] 🎨 笔记图 — 渲染小红书风格排版图（推荐）")
    img_choice = _input("图片模式", "2")
    render = img_choice == "2"
    if render:
        print("  → 将使用模板渲染小红书风格笔记图片")
    else:
        print("  → 将搜索网络素材图作为配图")
    print()
    run(topic, publish=publish, render_slides=render)


def _do_browse() -> None:
    from src.engager import browse_notes

    keyword = _input("搜索关键词（留空浏览推荐）")
    items = browse_notes(keyword=keyword)

    while items:
        action = _input("输入笔记 ID 进行操作，或直接回车返回菜单")
        if not action:
            break

        note_id = action.strip()
        op = _choose("操作", ["like", "comment", "both"], "like")
        if op in ("like", "both"):
            from src.engager import like_single_note
            like_single_note(note_id)
        if op in ("comment", "both"):
            _do_comment_for(note_id)


def _do_engage() -> None:
    from src.engager import engage

    count = _input_int("互动笔记数量", 5)
    keyword = _input("搜索关键词（留空浏览推荐）")
    like_only_str = _choose("模式", ["点赞+评论", "仅点赞"], "点赞+评论")
    like_only = like_only_str == "仅点赞"

    print()
    engage(count=count, like_only=like_only, keyword=keyword)


def _do_like() -> None:
    from src.engager import like_single_note

    note_id = _input("笔记 ID（24位十六进制字符串）")
    if not note_id:
        return
    like_single_note(note_id)


def _do_comment_for(note_id: str | None = None) -> None:
    from src.engager import comment_single_note

    if note_id is None:
        note_id = _input("笔记 ID（24位十六进制字符串）")
        if not note_id:
            return

    msg = _input("评论内容（留空则 AI 自动生成）")
    comment_single_note(note_id, content=msg)


def _do_list_topics() -> None:
    from src.agent import list_topics
    list_topics()


ACTIONS = {
    "1": ("从 Chrome 导入", _do_import_chrome),
    "2": ("登录主站", _do_login_main),
    "3": ("登录创作者平台", _do_login_creator),
    "4": ("生成笔记", lambda: _do_generate(publish=False)),
    "5": ("生成+发布", lambda: _do_generate(publish=True)),
    "6": ("浏览笔记", _do_browse),
    "7": ("自动互动", _do_engage),
    "8": ("点赞笔记", _do_like),
    "9": ("评论笔记", lambda: _do_comment_for()),
    "t": ("查看主题池", _do_list_topics),
}


def interactive_menu() -> None:
    """运行交互式 CLI 菜单。"""
    print(BANNER)

    while True:
        print(MENU)
        choice = _input("请输入编号")

        if choice == "0":
            print("\n  👋 再见!\n")
            sys.exit(0)

        action = ACTIONS.get(choice)
        if action:
            _, func = action
            print()
            try:
                func()
            except KeyboardInterrupt:
                print("\n  ⏹  操作已取消")
            except Exception as e:
                print(f"\n  ❌ 出错了: {e}")
            print()
        else:
            print("  ⚠️  无效选项，请输入 0-9 或 t")
