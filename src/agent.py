"""小红书 KOL Agent — 主编排器。

Usage:
    python run.py "波士顿租房攻略"               # 仅生成
    python run.py "波士顿租房攻略" --publish      # 生成 + 发布到小红书
    python run.py --random --publish             # 随机选题 + 发布
    python run.py --list                         # 查看主题池
"""

from __future__ import annotations

import random
from datetime import datetime
from pathlib import Path

import yaml

from src.config import CONFIG_DIR, OUTPUT_DIR
from src.generator.pipeline import run_pipeline
from src.models import GeneratedPost
from src.research.web_searcher import generate_search_queries, search_web
from src.utils.logger import logger


def load_topic_pool() -> dict[str, list[str]]:
    topics_file = CONFIG_DIR / "topics.yaml"
    if not topics_file.exists():
        logger.warning(f"Topics file not found: {topics_file}")
        return {}
    with open(topics_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("categories", {})


def pick_random_topic() -> str:
    pool = load_topic_pool()
    all_topics = [topic for topics in pool.values() for topic in topics]
    if not all_topics:
        raise RuntimeError("Topic pool is empty. Check config/topics.yaml")
    chosen = random.choice(all_topics)
    logger.info(f"Randomly picked topic: {chosen}")
    return chosen


def list_topics() -> None:
    pool = load_topic_pool()
    for category, topics in pool.items():
        print(f"\n📂 {category}")
        for i, t in enumerate(topics, 1):
            print(f"   {i}. {t}")


def save_post(post: GeneratedPost) -> Path:
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = post.title[:40].replace("/", "-").replace(" ", "_")
    filename = f"{date_str}_{safe_title}.md"
    filepath = OUTPUT_DIR / filename

    filepath.write_text(post.markdown, encoding="utf-8")
    logger.info(f"Post saved to {filepath}")
    return filepath


def run(
    topic: str,
    publish: bool = False,
    render_slides: bool = False,
) -> Path:
    """执行完整的 Agent 流水线。

    Args:
        topic: 笔记主题。
        publish: 是否同时发布到小红书。
        render_slides: True=用模板渲染笔记图片, False=搜索素材图。
    """
    total_steps = 5 if publish else 4
    mode_label = "模板渲染" if render_slides else "素材图"

    logger.info(f"{'=' * 60}")
    logger.info(f"📕 小红书 KOL Agent — 开始生成")
    logger.info(f"   主题: {topic}")
    logger.info(f"   图片: {mode_label}")
    logger.info(f"   模式: {'生成 + 发帖' if publish else '仅生成'}")
    logger.info(f"{'=' * 60}")

    logger.info(f"[1/{total_steps}] 生成搜索关键词...")
    queries = generate_search_queries(topic)

    logger.info(f"[2/{total_steps}] 搜索素材...")
    search_results = search_web(queries)
    if not search_results:
        raise RuntimeError("No search results found. Check your TAVILY_API_KEY or try a different topic.")

    logger.info(f"[3/{total_steps}] 生成小红书风格笔记...")
    post = run_pipeline(topic, search_results, render_slides_mode=render_slides)

    logger.info(f"[4/{total_steps}] 保存笔记...")
    filepath = save_post(post)

    slides_count = len(post.plan.slides) if post.plan else 0
    logger.info(f"   标题: {post.title}")
    logger.info(f"   轮播图: {slides_count} 页 | 配图: {len(post.images)} 张")
    logger.info(f"   正文: {len(post.copy)} 字")
    logger.info(f"   文件: {filepath}")

    if publish:
        if not post.images:
            logger.warning("⚠️  没有配图！Unsplash API 可能配额用尽（免费版每小时 50 次）")
            logger.warning("   笔记已保存到本地，等配额恢复后可重新生成并发布")
            logger.warning("   跳过发布步骤")
            publish = False

    if publish:
        logger.info(f"[{total_steps}/{total_steps}] 发布到小红书...")
        from src.publisher.publisher import publish_post

        result = publish_post(post=post)
        status = result.get("status", "unknown")
        status_icon = "✅ 已发布" if status == "published" else "⏳ 待审核"
        logger.info(f"   发帖结果: {status_icon}")

    logger.info(f"{'=' * 60}")
    logger.info("✅ 全部完成!")
    logger.info(f"{'=' * 60}")

    return filepath
