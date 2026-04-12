from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SearchResult:
    title: str
    url: str
    content: str
    score: float = 0.0


@dataclass
class ImageResult:
    url: str
    thumb_url: str
    description: str
    photographer: str
    photographer_url: str
    keyword: str = ""


@dataclass
class Slide:
    """One page in a Xiaohongshu-style carousel post."""
    slide_title: str
    caption: str
    image_keyword: str


@dataclass
class PostPlan:
    """Structured plan for a Xiaohongshu-style carousel post."""
    title: str
    slides: list[Slide]
    tags: list[str]


@dataclass
class GeneratedPost:
    title: str
    markdown: str
    copy: str = ""
    images: list[ImageResult] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    plan: PostPlan | None = None
