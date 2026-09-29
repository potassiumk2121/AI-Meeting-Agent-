import asyncio
import json
import logging
import re
import time

import httpx
from openai import AsyncOpenAI

from app.config import get_settings
from app.errors import AppError

logger = logging.getLogger(__name__)

_resting_until: dict[str, float] = {}


def gemini_models() -> list[str]:
    settings = get_settings()
    chain = [settings.gemini_model, *settings.gemini_fallback_models.split(",")]
    ordered = [name for name in dict.fromkeys(item.strip() for item in chain) if name]
    now = time.monotonic()
    ready = [name for name in ordered if _resting_until.get(name, 0) <= now]
    return ready or ordered


async def gemini_generate(payload: dict, *, timeout: float = 60) -> httpx.Response:
    """Returns the first Gemini response that is not a quota, missing-model, or overload error.

    Free-tier keys get a small daily quota per model, so a model that answers 429 is
    skipped for a while and the next model in GEMINI_FALLBACK_MODELS is tried.
    """
    settings = get_settings()
    response: httpx.Response | None = None
    async with httpx.AsyncClient(timeout=timeout) as client:
        for model in gemini_models():
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            for attempt in range(2):
                try:
                    response = await client.post(url, params={"key": settings.gemini_api_key}, json=payload)
                except httpx.HTTPError:
                    logger.warning("gemini request to %s failed", model, exc_info=True)
                    response = None
                    break
                if response.status_code in {500, 502, 503, 504} and attempt == 0:
                    await asyncio.sleep(1)
                    continue
                break
            if response is None:
                continue
            status = response.status_code
            if status == 429:
                per_day = "PerDay" in response.text
                _resting_until[model] = time.monotonic() + (3600 if per_day else 60)
                logger.warning("gemini model %s hit its %s quota", model, "daily" if per_day else "per-minute")
                continue
            if status == 404:
                _resting_until[model] = time.monotonic() + 86400
                logger.warning("gemini model %s is not available", model)
                continue
            if status >= 500:
                continue
            return response
    if response is None:
        raise AppError("Gemini did not answer in time. The next clip will continue.", 503)
    return response


def llm_configured() -> bool:
    settings = get_settings()
    if settings.ai_provider.lower() == "gemini":
        return bool(settings.gemini_api_key)
    return bool(settings.openai_api_key or settings.gemini_api_key)


def active_model_name() -> str:
    settings = get_settings()
    if not llm_configured():
        return "fallback"
    if settings.ai_provider.lower() == "gemini":
        return settings.gemini_model
    return settings.openai_chat_model


def parse_json_blob(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Model response was not a JSON object")
    return data


async def complete(system: str, user: str, *, json_mode: bool) -> str:
    settings = get_settings()
    if settings.ai_provider.lower() == "gemini":
        return await _gemini(system, user, json_mode)
    try:
        return await _openai(system, user, json_mode)
    except Exception:
        if not settings.gemini_api_key:
            raise
        logger.warning("openai completion failed; trying gemini", exc_info=True)
        return await _gemini(system, user, json_mode)


async def complete_json(system: str, user: str) -> dict:
    return parse_json_blob(await complete(system, user, json_mode=True))


async def _openai(system: str, user: str, json_mode: bool) -> str:
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    kwargs: dict = {
        "model": settings.openai_chat_model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = await client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


async def _gemini(system: str, user: str, json_mode: bool) -> str:
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0.2},
    }
    if json_mode:
        payload["generationConfig"]["responseMimeType"] = "application/json"
    response = await gemini_generate(payload)
    response.raise_for_status()
    data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


async def embed_texts(texts: list[str]) -> list[list[float]]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    if not texts:
        return []
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    vectors: list[list[float]] = []
    for start in range(0, len(texts), 64):
        batch = texts[start : start + 64]
        result = await client.embeddings.create(model=settings.openai_embed_model, input=batch)
        ordered = sorted(result.data, key=lambda item: item.index)
        vectors.extend(item.embedding for item in ordered)
    return vectors
