"""互动引擎 — 自动浏览小红书笔记、点赞、AI 评论。"""

from __future__ import annotations

import random
import time

from src.llm import chat
from src.publisher.xhs_client import XHSClient, XHSClientError
from src.utils.logger import logger

COMMENT_SYSTEM = """你是一个普通的小红书用户，平时关注时尚、生活、美食、旅行、投资理财、科技等各种话题。
你正在浏览其他用户的笔记并留言互动。

你的评论必须：
- 自然、真诚，像真人留言，绝对不能有 AI 味
- 和笔记内容直接相关，体现你认真读了笔记
- 简短有力，20-80 字之间
- 口语化，可以用 emoji 但不要过多（0-2 个）
- 根据笔记内容选择合适的语气：共鸣、提问、补充经验、感谢分享等
- 每次风格要有变化，不要重复套路

绝对不要：
- 用"写得真好"、"干货满满"、"收藏了"这类万能评论
- 用"作为一个..."开头
- 超过 80 字
- 用英文回复中文笔记

直接输出评论内容，不要加引号或任何额外说明。"""

COMMENT_ANGLES = [
    "请从「个人经验共鸣」的角度留言，分享你类似的经历或感受。",
    "请从「真诚提问」的角度留言，对笔记某个细节提出一个具体问题。",
    "请从「补充信息」的角度留言，补充一个笔记没提到但相关的小知识。",
    "请从「感谢+具体反馈」的角度留言，说明笔记哪个部分对你最有帮助。",
    "请从「轻松互动」的角度留言，语气轻松有趣，拉近距离。",
]


def generate_comment(title: str, content: str) -> str:
    """使用 LLM 为笔记生成上下文相关的评论。"""
    angle = random.choice(COMMENT_ANGLES)
    preview = content[:500] if len(content) > 500 else content

    user_prompt = f"""{angle}

笔记标题：{title}
笔记内容：{preview}"""

    comment = chat(
        system_prompt=COMMENT_SYSTEM,
        user_prompt=user_prompt,
        temperature=0.9,
        max_tokens=256,
    )

    comment = comment.strip().strip('"').strip("'").strip("\u201c").strip("\u201d")
    if len(comment) > 500:
        comment = comment[:497] + "..."

    return comment


def browse_notes(
    keyword: str = "",
    count: int = 20,
) -> list[dict]:
    """浏览并显示小红书笔记列表。"""
    client = XHSClient()
    try:
        client.login()
        items = client.browse_notes(keyword=keyword, count=count)

        if not items:
            print("\n  没有找到笔记\n")
            return []

        label = f"搜索: {keyword}" if keyword else "推荐"
        print(f"\n📋 小红书笔记 ({label})")
        print(f"{'─' * 64}")

        for note in items:
            nid = note.get("id", "?")[:8]
            title = note.get("title", "(无标题)")[:40]
            author = note.get("author", "")[:10]
            likes = note.get("likes", "0")

            print(f"  {nid}  {title:<42} 👤 {author:<10} ❤️  {likes}")

        print(f"{'─' * 64}")
        print(f"  共 {len(items)} 篇\n")
        return items

    finally:
        client.close()


def like_single_note(note_id: str) -> None:
    """给指定笔记点赞。"""
    client = XHSClient()
    try:
        client.login()
        client.like_note(note_id)
        logger.info(f"已点赞笔记 {note_id}")
    finally:
        client.close()


def comment_single_note(note_id: str, content: str = "") -> None:
    """给指定笔记评论。空内容则 AI 自动生成。"""
    client = XHSClient()
    try:
        client.login()

        if not content:
            logger.info(f"获取笔记详情并生成 AI 评论...")
            detail = client.get_note_detail(note_id)
            content = generate_comment(
                title=detail.get("title", ""),
                content=detail.get("content", ""),
            )

        client.comment_on_note(note_id, content)
        logger.info(f"已评论笔记 {note_id}: {content}")
    finally:
        client.close()


def engage(
    count: int = 5,
    like_only: bool = False,
    keyword: str = "",
) -> None:
    """自动浏览小红书笔记，点赞并 AI 评论。

    Args:
        count: 互动笔记数量。
        like_only: 仅点赞，不评论。
        keyword: 搜索关键词（为空则浏览推荐）。
    """
    client = XHSClient()
    try:
        client.login()

        logger.info(f"{'=' * 60}")
        logger.info(f"🤝 互动模式 — {'仅点赞' if like_only else '点赞+评论'}")
        logger.info(f"   目标: {count} 篇笔记")
        if keyword:
            logger.info(f"   搜索: {keyword}")
        logger.info(f"{'=' * 60}")

        items = client.browse_notes(keyword=keyword, count=count * 2)

        if not items:
            logger.warning("没有找到可互动的笔记")
            return

        engaged = 0
        for note in items:
            if engaged >= count:
                break

            note_id = note.get("id", "")
            note_title = note.get("title", "")

            if not note_id:
                continue

            logger.info(f"\n--- 笔记 {note_id[:8]}: {note_title[:50]} ---")

            try:
                client.like_note(note_id)
                logger.info(f"  ❤️  已点赞")
            except XHSClientError as e:
                logger.warning(f"  点赞失败: {e}")

            if not like_only:
                delay = random.uniform(5, 12)
                logger.debug(f"  等待 {delay:.0f}s 后评论...")
                time.sleep(delay)

                try:
                    detail = client.get_note_detail(note_id)
                    comment_text = generate_comment(
                        detail.get("title", note_title),
                        detail.get("content", ""),
                    )
                    client.comment_on_note(note_id, comment_text)
                    logger.info(f"  💬 已评论: {comment_text}")
                except (XHSClientError, ValueError) as e:
                    logger.warning(f"  评论失败: {e}")

            engaged += 1

            if engaged < count:
                wait = random.uniform(20, 45)
                logger.info(f"  ⏳ 等待 {wait:.0f}s 后继续...")
                time.sleep(wait)

        logger.info(f"\n{'=' * 60}")
        logger.info(f"✅ 互动完成! 共互动 {engaged} 篇笔记")
        logger.info(f"{'=' * 60}")

    finally:
        client.close()
