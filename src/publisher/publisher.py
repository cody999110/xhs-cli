"""Publisher — 下载配图并发布笔记到小红书。"""

from __future__ import annotations

from src.models import GeneratedPost
from src.publisher.image_downloader import cleanup_images, download_images
from src.publisher.xhs_client import XHSClient, XHSClientError
from src.utils.logger import logger


def publish_post(post: GeneratedPost) -> dict:
    """发布 GeneratedPost 到小红书。

    流程: 登录验证 → 准备图片 → 上传并发帖。
    如果是渲染模式（_rendered_paths 非空），直接使用本地渲染图片；
    否则从 Unsplash/Pexels 下载。
    """
    logger.info("准备发布到小红书...")

    client = XHSClient()
    try:
        logger.info("[Publish 1/3] 登录小红书主站...")
        client.login()

        logger.info("[Publish 2/3] 验证创作者平台登录...")
        client.login_creator()

        logger.info("[Publish 3/3] 准备配图并发布...")

        # 渲染模式：图片已在本地，直接使用
        rendered_paths = getattr(post, "_rendered_paths", [])
        if rendered_paths:
            from pathlib import Path
            local_files = [Path(p) for p in rendered_paths if Path(p).exists()]
            logger.info(f"使用本地渲染图片: {len(local_files)} 张")
        else:
            local_files = download_images(post.images)

        if not local_files:
            raise XHSClientError(
                "没有可用的配图，小红书笔记至少需要 1 张图片才能发布。\n"
                "可能原因：图片搜索 API 配额用尽或渲染失败。\n"
                "解决方案：等待后重试，或在 .env 中配置 PEXELS_API_KEY 作为备选。\n"
                "提示：笔记已保存到 output/ 目录，稍后可手动发布。"
            )

        result = client.create_post(
            title=post.title,
            content=post.copy,
            image_paths=local_files,
            tags=post.tags,
        )

        return result
    finally:
        client.close()
        if not rendered_paths:
            cleanup_images()
