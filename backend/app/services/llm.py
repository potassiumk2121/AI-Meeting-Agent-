import json
import logging
import re

import httpx
from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)


def llm_configured() -> bool:
    settings = get_settings()
    if settings.ai_provider.lower() == "gemini":
        return bool(settings.gemini_api_key)
    return bool(settings.openai_api_key)


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
    return await _openai(system, user, json_mode)


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
    settings = get_settings()
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0.2},
    }
    if json_mode:
        payload["generationConfig"]["responseMimeType"] = "application/json"
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, params={"key": settings.gemini_api_key}, json=payload)
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
