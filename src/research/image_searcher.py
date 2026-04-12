"""多源图片搜索：Unsplash → Pexels → Pixabay → Tavily 四级 fallback。

任一来源成功即返回结果，全部失败则返回空列表。
Unsplash 免费版每小时 50 次，Pexels 免费版每月 20,000 次，
Pixabay 免费版每分钟 100 次（支持中文搜索，国内访问友好），
Tavily 作为最后兜底（返回的图片质量相对较低）。
"""

from __future__ import annotations

import httpx

from src.config import PEXELS_API_KEY, PIXABAY_API_KEY, TAVILY_API_KEY, UNSPLASH_ACCESS_KEY
from src.models import ImageResult
from src.utils.logger import logger

_TIMEOUT = 15


# ---------------------------------------------------------------------------
# Unsplash
# ---------------------------------------------------------------------------

def _search_unsplash(keyword: str, per_page: int, orientation: str) -> list[ImageResult]:
    if not UNSPLASH_ACCESS_KEY:
        return []
    try:
        resp = httpx.get(
            "https://api.unsplash.com/search/photos",
            params={"query": keyword, "per_page": per_page, "orientation": orientation},
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.debug(f"Unsplash failed for '{keyword}': {e}")
        return []

    results: list[ImageResult] = []
    for item in resp.json().get("results", []):
        urls = item.get("urls", {})
        user = item.get("user", {})
        results.append(
            ImageResult(
                url=urls.get("regular", ""),
                thumb_url=urls.get("small", ""),
                description=item.get("alt_description") or item.get("description") or keyword,
                photographer=user.get("name", "Unknown"),
                photographer_url=user.get("links", {}).get("html", ""),
                keyword=keyword,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Pexels
# ---------------------------------------------------------------------------

def _search_pexels(keyword: str, per_page: int, orientation: str) -> list[ImageResult]:
    if not PEXELS_API_KEY:
        return []
    try:
        resp = httpx.get(
            "https://api.pexels.com/v1/search",
            params={
                "query": keyword,
                "per_page": per_page,
                "orientation": orientation,
            },
            headers={"Authorization": PEXELS_API_KEY},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.debug(f"Pexels failed for '{keyword}': {e}")
        return []

    results: list[ImageResult] = []
    for photo in resp.json().get("photos", []):
        src = photo.get("src", {})
        results.append(
            ImageResult(
                url=src.get("large2x") or src.get("original", ""),
                thumb_url=src.get("medium", ""),
                description=photo.get("alt") or keyword,
                photographer=photo.get("photographer", "Unknown"),
                photographer_url=photo.get("photographer_url", ""),
                keyword=keyword,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Pixabay — 支持中文搜索，国内访问友好
# ---------------------------------------------------------------------------

_PIXABAY_ORIENTATION_MAP = {"portrait": "vertical", "landscape": "horizontal"}


def _search_pixabay(keyword: str, per_page: int, orientation: str) -> list[ImageResult]:
    if not PIXABAY_API_KEY:
        return []
    try:
        resp = httpx.get(
            "https://pixabay.com/api/",
            params={
                "key": PIXABAY_API_KEY,
                "q": keyword,
                "lang": "zh",
                "per_page": min(per_page, 200),
                "orientation": _PIXABAY_ORIENTATION_MAP.get(orientation, "all"),
                "safesearch": "true",
                "image_type": "photo",
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.debug(f"Pixabay failed for '{keyword}': {e}")
        return []

    results: list[ImageResult] = []
    for hit in resp.json().get("hits", []):
        results.append(
            ImageResult(
                url=hit.get("largeImageURL", ""),
                thumb_url=hit.get("webformatURL", ""),
                description=hit.get("tags") or keyword,
                photographer=hit.get("user", "Unknown"),
                photographer_url=hit.get("pageURL", ""),
                keyword=keyword,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Tavily (image search via include_images)
# ---------------------------------------------------------------------------

def _search_tavily_images(keyword: str, max_results: int = 3) -> list[ImageResult]:
    if not TAVILY_API_KEY:
        return []
    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": keyword,
                "include_images": True,
                "max_results": 1,
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.debug(f"Tavily image search failed for '{keyword}': {e}")
        return []

    results: list[ImageResult] = []
    for img_url in resp.json().get("images", [])[:max_results]:
        if not isinstance(img_url, str) or not img_url.startswith("http"):
            continue
        results.append(
            ImageResult(
                url=img_url,
                thumb_url=img_url,
                description=keyword,
                photographer="",
                photographer_url="",
                keyword=keyword,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Public API — 三级 fallback
# ---------------------------------------------------------------------------

_SOURCES = [
    ("Unsplash", _search_unsplash),
    ("Pexels", _search_pexels),
    ("Pixabay", _search_pixabay),
]


def search_images(
    keyword: str,
    per_page: int = 3,
    orientation: str = "portrait",
) -> list[ImageResult]:
    """搜索图片，按 Unsplash → Pexels → Pixabay → Tavily 顺序尝试。"""
    for name, fn in _SOURCES:
        results = fn(keyword, per_page, orientation)
        if results:
            logger.debug(f"[{name}] found {len(results)} images for '{keyword}'")
            return results

    # Tavily 兜底（接口不同，单独调用）
    results = _search_tavily_images(keyword, max_results=per_page)
    if results:
        logger.debug(f"[Tavily] found {len(results)} images for '{keyword}'")
        return results

    logger.warning(f"All image sources failed for '{keyword}'")
    return []


def search_images_batch(
    keywords: list[str], per_keyword: int = 2
) -> dict[str, list[ImageResult]]:
    """Search images for multiple keywords."""
    return {kw: search_images(kw, per_page=per_keyword) for kw in keywords}
