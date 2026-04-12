"""下载 Unsplash 图片到本地，用于上传到小红书。"""

from __future__ import annotations

import shutil
from pathlib import Path

import httpx

from src.config import DATA_DIR
from src.models import ImageResult
from src.utils.logger import logger

IMAGES_DIR = DATA_DIR / "images"
MAX_IMAGES = 9
MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


def _ensure_dir() -> Path:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    return IMAGES_DIR


def _clean_dir() -> None:
    if IMAGES_DIR.exists():
        shutil.rmtree(IMAGES_DIR)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def download_images(images: list[ImageResult]) -> list[Path]:
    """Download images to local temp directory.

    Returns list of local file paths, at most MAX_IMAGES items.
    Skips images that fail to download or exceed MAX_SIZE_BYTES.
    """
    _clean_dir()
    target_dir = _ensure_dir()

    downloaded: list[Path] = []
    for i, img in enumerate(images[:MAX_IMAGES]):
        url = img.url
        if not url:
            continue

        ext = ".jpg"
        if ".png" in url:
            ext = ".png"
        elif ".webp" in url:
            ext = ".webp"

        filename = f"slide_{i + 1:02d}{ext}"
        filepath = target_dir / filename

        try:
            with httpx.stream("GET", url, timeout=30, follow_redirects=True) as resp:
                resp.raise_for_status()
                with open(filepath, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=8192):
                        f.write(chunk)
        except httpx.HTTPError as e:
            logger.warning(f"Failed to download image {i + 1} ({url[:80]}): {e}")
            continue

        size = filepath.stat().st_size
        if size > MAX_SIZE_BYTES:
            logger.warning(
                f"Image {filename} is {size / 1024 / 1024:.1f}MB (>{MAX_SIZE_BYTES / 1024 / 1024:.0f}MB limit), "
                f"trying smaller version"
            )
            filepath.unlink()
            # Retry with the smaller thumbnail URL
            if img.thumb_url:
                try:
                    with httpx.stream("GET", img.thumb_url, timeout=30, follow_redirects=True) as resp:
                        resp.raise_for_status()
                        with open(filepath, "wb") as f:
                            for chunk in resp.iter_bytes(chunk_size=8192):
                                f.write(chunk)
                except httpx.HTTPError:
                    logger.warning(f"Thumbnail download also failed for image {i + 1}")
                    continue
            else:
                continue

        downloaded.append(filepath)
        logger.debug(f"  Downloaded: {filename} ({size / 1024:.0f}KB)")

    logger.info(f"Downloaded {len(downloaded)}/{len(images)} images to {target_dir}")
    return downloaded


def cleanup_images() -> None:
    """Remove the temp images directory after successful upload."""
    if IMAGES_DIR.exists():
        shutil.rmtree(IMAGES_DIR)
        logger.debug("Cleaned up temp images directory")
