"""Content generation pipeline — 小红书风格内容生成。

Flow:  plan slides → search images → write copy → assemble post
"""

from __future__ import annotations

import re
from datetime import datetime

from src.llm import chat, chat_json
from src.models import (
    GeneratedPost,
    ImageResult,
    PostPlan,
    SearchResult,
    Slide,
)
from src.research.image_searcher import search_images
from src.research.web_searcher import format_results_for_llm
from src.utils.logger import logger

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

PLAN_SYSTEM = """你是一位超会做小红书爆款笔记的博主，粉丝10w+，涉猎广泛（生活、时尚、美食、旅行、投资理财、科技、健身、职场等）。
现在你需要根据搜索素材，策划一篇小红书风格的图文笔记。

核心原则：
- 这是一篇「轮播图笔记」，每张图配一小段干货文字
- 封面（第1张）要有冲击力，让人忍不住点进来
- 每张图聚焦一个小知识点，信息密度高但文字精简
- 总共 6-9 张轮播图（含封面和尾页）

以严格 JSON 格式返回，不要添加任何其他文字：
{
  "title": "小红书风格标题（用emoji分隔，有冲击力，如：💰A股下周走势｜3个信号告诉你答案❗️）",
  "slides": [
    {
      "slide_title": "这页的大标题（简短有力，5-12字）",
      "caption": "这页的核心内容文案（60-120字，口语化，有干货）",
      "image_keyword": "用于搜索配图的英文关键词（具体、有画面感）"
    }
  ],
  "tags": ["#标签1", "#标签2", "#标签3", "#标签4", "#标签5"]
}

slides 规划要求：
- 第1张（封面）：slide_title 写封面大字标题，caption 写副标题/吸引语
- 第2-7/8张（内容页）：每张一个知识点，caption 要有具体信息和数据
- 最后1张（尾页）：总结/互动引导，如"觉得有用就收藏吧～"
- image_keyword 必须是英文，偏生活感、美观、有质感的关键词
- tags 要 5-8 个，贴合小红书热门标签习惯"""

COPY_SYSTEM = """你是一位小红书爆款博主，正在为一篇笔记写正文描述。

小红书正文风格要求：
- 300-500 字，不要太长！用户没耐心看长文
- 开头要抓人：用感叹句、反问句或吐槽开场
- 大量使用 emoji，每 1-2 句话至少一个
- 语气像在跟朋友分享经验，自然亲切
- 用「」标注关键信息
- 善用换行，每 1-2 句话就换行，不要写大段文字
- 可以用 ⚠️ 标注避坑点
- 文末加互动引导（如：有问题评论区问我～）
- 不要用 Markdown 格式（没有 # 号标题、没有 **加粗**）

绝对不要：
- 写成正式文章/攻略体
- 使用"首先、其次、最后"这种论文连接词
- 超过 500 字"""

# ---------------------------------------------------------------------------
# Step 1: Plan Slides
# ---------------------------------------------------------------------------


def plan_slides(topic: str, search_results: list[SearchResult]) -> PostPlan:
    materials = format_results_for_llm(search_results)
    user_prompt = f"笔记主题：{topic}\n\n搜索素材：\n{materials}"

    data = chat_json(
        system_prompt=PLAN_SYSTEM,
        user_prompt=user_prompt,
        temperature=0.6,
        max_tokens=8192,
    )

    slides = [
        Slide(
            slide_title=s.get("slide_title", ""),
            caption=s.get("caption", ""),
            image_keyword=s.get("image_keyword", ""),
        )
        for s in data.get("slides", [])
    ]

    plan = PostPlan(
        title=data.get("title", topic),
        slides=slides,
        tags=data.get("tags", []),
    )
    logger.info(f"Post plan: '{plan.title}' with {len(plan.slides)} slides")
    return plan


# ---------------------------------------------------------------------------
# Step 2: Search Images
# ---------------------------------------------------------------------------


def fetch_images_for_slides(plan: PostPlan) -> list[ImageResult]:
    """Search one image per slide."""
    images: list[ImageResult] = []

    for i, slide in enumerate(plan.slides):
        if not slide.image_keyword:
            continue
        results = search_images(slide.image_keyword, per_page=2)
        if results:
            images.append(results[0])
            logger.debug(f"  Slide {i + 1}: found image for '{slide.image_keyword}'")
        else:
            logger.warning(f"  Slide {i + 1}: no image for '{slide.image_keyword}'")

    logger.info(f"Fetched {len(images)} images for {len(plan.slides)} slides")
    return images


# ---------------------------------------------------------------------------
# Step 3: Write Copy (正文描述)
# ---------------------------------------------------------------------------


def write_copy(
    topic: str,
    plan: PostPlan,
    search_results: list[SearchResult],
) -> str:
    materials = format_results_for_llm(search_results, max_items=8)

    slide_summary = ""
    for i, slide in enumerate(plan.slides, 1):
        slide_summary += f"  第{i}页：{slide.slide_title} — {slide.caption[:60]}\n"

    user_prompt = f"""笔记主题：{topic}
笔记标题：{plan.title}

轮播图内容概要：
{slide_summary}

参考素材（提取关键信息即可，不要照搬）：
{materials}

请写出这篇笔记的正文描述（发在图片下方的文字）："""

    copy = chat(
        system_prompt=COPY_SYSTEM,
        user_prompt=user_prompt,
        temperature=0.8,
        max_tokens=1024,
    )

    # Strip any markdown headers the LLM might have added
    copy = re.sub(r"^#+\s+.*$", "", copy, flags=re.MULTILINE).strip()

    logger.info(f"Post copy written: {len(copy)} chars")
    return copy


# ---------------------------------------------------------------------------
# Step 4: Assemble Final Output
# ---------------------------------------------------------------------------


def assemble_post(
    plan: PostPlan,
    images: list[ImageResult],
    copy: str,
) -> str:
    lines: list[str] = []

    date_str = datetime.now().strftime("%Y-%m-%d")
    tags_str = " ".join(plan.tags)

    # Front-matter
    lines.append("---")
    lines.append(f"title: \"{plan.title}\"")
    lines.append(f"platform: 小红书")
    lines.append(f"date: {date_str}")
    lines.append(f"slides: {len(plan.slides)}")
    lines.append(f"tags: [{', '.join(plan.tags)}]")
    lines.append("---\n")

    # Title
    lines.append(f"# {plan.title}\n")

    # Slides
    for i, slide in enumerate(plan.slides):
        lines.append(f"---\n")
        lines.append(f"### 📖 第 {i + 1} 页 — {slide.slide_title}\n")

        # Image (if available for this slide)
        if i < len(images):
            img = images[i]
            lines.append(f"![{img.description}]({img.url})")
            credit = f"Photo by [{img.photographer}]({img.photographer_url})"
            lines.append(f"<sub>{credit}</sub>\n")

        # Slide caption
        lines.append(f"> 💡 {slide.caption}\n")

    # Post copy
    lines.append("---\n")
    lines.append("## ✏️ 正文\n")
    lines.append(copy)
    lines.append("")

    # Tags
    lines.append("---\n")
    lines.append(tags_str)
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Full Pipeline
# ---------------------------------------------------------------------------


def run_pipeline(
    topic: str,
    search_results: list[SearchResult],
    render_slides_mode: bool = False,
) -> GeneratedPost:
    """Execute the full content generation pipeline (Xiaohongshu style).

    Parameters
    ----------
    render_slides_mode : bool
        True = 用 HTML 模板渲染笔记风格图片（带文字排版）。
        False = 搜索素材图片（Unsplash/Pexels）。
    """

    # Step 1: Plan slides
    plan = plan_slides(topic, search_results)

    # Step 2: Get images
    images: list[ImageResult] = []
    rendered_paths: list[str] = []

    if render_slides_mode:
        from src.generator.slide_renderer import render_slides

        logger.info("使用模板渲染笔记图片...")
        paths = render_slides(plan)
        rendered_paths = [str(p) for p in paths]
        # 为 rendered 模式构造 ImageResult（url 指向本地文件）
        for p in paths:
            images.append(
                ImageResult(
                    url=str(p),
                    thumb_url=str(p),
                    description=plan.title,
                    photographer="",
                    photographer_url="",
                    keyword="rendered",
                )
            )
    else:
        images = fetch_images_for_slides(plan)

    # Step 3: Write post copy
    copy = write_copy(topic, plan, search_results)

    # Step 4: Assemble
    markdown = assemble_post(plan, images, copy)

    post = GeneratedPost(
        title=plan.title,
        markdown=markdown,
        copy=copy,
        images=images,
        tags=plan.tags,
        plan=plan,
    )
    # 附加渲染模式的本地路径，供 publisher 直接使用
    post._rendered_paths = rendered_paths  # type: ignore[attr-defined]
    return post
