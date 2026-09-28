import base64
import logging

import httpx
from openai import AsyncOpenAI

from app.config import get_settings
from app.errors import AppError
from app.services.llm import parse_json_blob

logger = logging.getLogger(__name__)

_AZURE_LANG = {
    "en": "en-US",
    "hi": "hi-IN",
    "es": "es-ES",
    "fr": "fr-FR",
    "de": "de-DE",
    "ar": "ar-SA",
    "zh": "zh-CN",
    "ja": "ja-JP",
    "pt": "pt-BR",
}


async def transcribe(audio: bytes, filename: str, content_type: str, language: str | None) -> tuple[str, str | None]:
    settings = get_settings()
    provider = settings.speech_provider.lower()
    if provider == "azure":
        return await _azure(audio, content_type, language), language
    if provider == "gemini" or (settings.gemini_api_key and not settings.openai_api_key):
        if not settings.gemini_api_key:
            raise AppError("Set GEMINI_API_KEY to transcribe microphone audio.", 400)
        return await _gemini(audio, content_type)
    if settings.openai_api_key:
        return await _openai(audio, filename, language)
    if settings.gemini_api_key:
        return await _gemini(audio, content_type)
    raise AppError("Set GEMINI_API_KEY or OPENAI_API_KEY to transcribe microphone audio.", 400)


async def _openai(audio: bytes, filename: str, language: str | None) -> tuple[str, str | None]:
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    kwargs: dict = {
        "model": settings.openai_transcribe_model,
        "file": (filename or "audio.webm", audio),
        "response_format": "verbose_json",
    }
    if language and language not in {"auto", "und"}:
        kwargs["language"] = language.split("-")[0]
    result = await client.audio.transcriptions.create(**kwargs)
    detected = getattr(result, "language", None)
    return (result.text or "").strip(), (str(detected).split("-")[0] if detected else None)


async def _gemini(audio: bytes, content_type: str) -> tuple[str, str | None]:
    settings = get_settings()
    mime = content_type.split(";")[0].strip() if content_type else "audio/webm"
    if mime not in {"audio/webm", "audio/wav", "audio/mpeg", "audio/mp4", "audio/ogg"}:
        mime = "audio/webm"
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    prompt = (
        "Transcribe the speech in this audio. Detect the spoken language. Do not translate. "
        'Return JSON {"language":"en","text":"..."} where language is an ISO 639-1 code. '
        "If there is no speech, return an empty text."
    )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime, "data": base64.b64encode(audio).decode("ascii")}},
                ],
            }
        ],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, params={"key": settings.gemini_api_key}, json=payload)
    if response.status_code >= 400:
        logger.warning("gemini transcription failed with status %s", response.status_code)
        raise AppError("Gemini could not transcribe that audio.", 502)
    try:
        raw = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        data = parse_json_blob(raw)
    except Exception as exc:
        logger.exception("gemini transcription response was not usable")
        raise AppError("Gemini could not transcribe that audio.", 502) from exc
    text = str(data.get("text") or "").strip()
    language = str(data.get("language") or "").strip().lower().split("-")[0][:16] or None
    return text, language


async def _azure(audio: bytes, content_type: str, language: str | None) -> str:
    settings = get_settings()
    if not settings.azure_speech_key or not settings.azure_speech_region:
        raise AppError("Set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION.", 400)
    wav = "wav" in (content_type or "").lower() or audio.startswith(b"RIFF")
    if not wav:
        raise AppError(
            "Azure Speech expects a WAV file. Use Gemini or OpenAI for WebM microphone audio.",
            400,
        )
    lang = (language or "en").split("-")[0].lower()
    azure_lang = language if language and "-" in language else _AZURE_LANG.get(lang, "en-US")
    url = (
        f"https://{settings.azure_speech_region}.stt.speech.microsoft.com"
        "/speech/recognition/conversation/cognitiveservices/v1"
    )
    headers = {
        "Ocp-Apim-Subscription-Key": settings.azure_speech_key,
        "Content-Type": "audio/wav",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, params={"language": azure_lang}, headers=headers, content=audio)
        response.raise_for_status()
        body = response.json()
    if body.get("RecognitionStatus") != "Success":
        raise AppError(body.get("RecognitionStatus") or "Speech recognition failed.", 422)
    return (body.get("DisplayText") or "").strip()
