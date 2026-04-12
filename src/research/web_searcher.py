from __future__ import annotations

from tavily import TavilyClient

from src.config import TAVILY_API_KEY
from src.llm import chat_json
from src.models import SearchResult
from src.utils.logger import logger

QUERY_GEN_SYSTEM = """你是一位搜索查询专家。根据用户给出的文章主题，生成 4 个多样化的搜索查询词。
要求：
- 2 个中文查询、2 个英文查询
- 覆盖不同角度（实用信息、经验分享、最新数据、避坑指南）
- 查询词应具体、有针对性

以 JSON 格式返回：{"queries": ["查询1", "查询2", "查询3", "查询4"]}"""


def generate_search_queries(topic: str) -> list[str]:
    data = chat_json(
        system_prompt=QUERY_GEN_SYSTEM,
        user_prompt=f"文章主题：{topic}",
    )
    queries = data.get("queries", [])
    logger.info(f"Generated {len(queries)} search queries for '{topic}'")
    for i, q in enumerate(queries, 1):
        logger.debug(f"  Query {i}: {q}")
    return queries


def search_web(queries: list[str], max_results_per_query: int = 5) -> list[SearchResult]:
    if not TAVILY_API_KEY:
        raise RuntimeError("TAVILY_API_KEY is not set. Check your .env file.")

    client = TavilyClient(api_key=TAVILY_API_KEY)
    seen_urls: set[str] = set()
    results: list[SearchResult] = []

    for query in queries:
        try:
            resp = client.search(
                query=query,
                max_results=max_results_per_query,
                search_depth="basic",
                include_answer=False,
            )
        except Exception as e:
            logger.warning(f"Search failed for '{query}': {e}")
            continue

        for item in resp.get("results", []):
            url = item.get("url", "")
            if url in seen_urls:
                continue
            seen_urls.add(url)
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=url,
                    content=item.get("content", ""),
                    score=item.get("score", 0.0),
                )
            )

    results.sort(key=lambda r: r.score, reverse=True)
    logger.info(f"Collected {len(results)} unique search results")
    return results


def format_results_for_llm(results: list[SearchResult], max_items: int = 12) -> str:
    lines: list[str] = []
    for i, r in enumerate(results[:max_items], 1):
        content_preview = r.content[:500] if r.content else "(no content)"
        lines.append(f"[{i}] {r.title}\n    URL: {r.url}\n    {content_preview}\n")
    return "\n".join(lines)
