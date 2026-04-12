from __future__ import annotations

import json
import re

from openai import OpenAI

from src.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from src.utils.logger import logger

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not LLM_API_KEY:
            raise RuntimeError(
                "LLM API Key 未设置。请在 .env 中配置 LLM_API_KEY（或 DEEPSEEK_API_KEY）。"
            )
        _client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    return _client


def chat(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    client = _get_client()
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    content = resp.choices[0].message.content or ""
    logger.debug(f"LLM response ({len(content)} chars)")
    return content


def _extract_json(raw: str) -> dict | None:
    """Try multiple strategies to extract JSON from LLM output."""
    # Strategy 1: direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strategy 2: extract from ```json ... ``` fences
    match = re.search(r"```(?:json)?\s*\n(.*?)```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: fences without closing ``` (truncated output)
    match = re.search(r"```(?:json)?\s*\n(.*)", raw, re.DOTALL)
    if match:
        fragment = match.group(1).rstrip("`").rstrip()
        try:
            return json.loads(fragment)
        except json.JSONDecodeError:
            pass

    # Strategy 4: find the outermost { ... } block
    start = raw.find("{")
    if start != -1:
        depth = 0
        end = start
        for i in range(start, len(raw)):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        try:
            return json.loads(raw[start:end])
        except json.JSONDecodeError:
            pass

    return None


def chat_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    retries: int = 2,
) -> dict:
    """Call LLM and parse the response as JSON.

    Retries automatically if JSON extraction fails.
    """
    last_raw = ""
    for attempt in range(1 + retries):
        if attempt > 0:
            logger.warning(f"JSON parse failed, retrying ({attempt}/{retries})...")

        raw = chat(system_prompt, user_prompt, temperature=temperature, max_tokens=max_tokens)
        last_raw = raw

        result = _extract_json(raw)
        if result is not None:
            return result

    raise ValueError(f"LLM did not return valid JSON after {1 + retries} attempts.\nRaw output:\n{last_raw[:800]}")
