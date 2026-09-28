import base64
import logging
import re
from dataclasses import dataclass

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


@dataclass
class SpeechTurn:
    speaker: str
    text: str
    language: str | None
    english: str


def canonical_speaker(raw: str, known: list[str]) -> str:
    cleaned = re.sub(r"\s+", " ", (raw or "").strip())
    if not cleaned:
        return ""
    for name in known:
        if name.casefold() == cleaned.casefold():
            return name
    match = re.fullmatch(r"(?:person|speaker)\s*([A-Za-z]|\d+)", cleaned, re.IGNORECASE)
    token = match.group(1) if match else (cleaned if re.fullmatch(r"[A-Za-z]", cleaned) else "")
    if not token:
        return ""
    if token.isdigit():
        index = int(token) - 1
    else:
        index = ord(token.upper()) - ord("A")
    if index < 0 or index > 25:
        return ""
    label = f"Person {chr(ord('A') + index)}"
    for name in known:
        if name.casefold() == label.casefold():
            return name
    return label


def next_person(used: list[str]) -> str:
    taken = {name.casefold() for name in used}
    for index in range(26):
        label = f"Person {chr(ord('A') + index)}"
        if label.casefold() not in taken:
            return label
    return f"Person {len(used) + 1}"


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


async def transcribe_speakers(
    audio: bytes,
    content_type: str,
    known_speakers: list[str],
    recent: list[tuple[str, str]],
) -> list[SpeechTurn]:
    settings = get_settings()
    if not settings.gemini_api_key:
        text, language = await transcribe(audio, "audio.webm", content_type, None)
        if not text:
            return []
        speaker = known_speakers[-1] if known_speakers else "Person A"
        return [SpeechTurn(speaker=speaker, text=text, language=language, english="")]
    mime = content_type.split(";")[0].strip() if content_type else "audio/webm"
    if mime not in {"audio/webm", "audio/wav", "audio/mpeg", "audio/mp4", "audio/ogg"}:
        mime = "audio/webm"
    roster = ", ".join(known_speakers) if known_speakers else "none yet"
    history = "\n".join(f"{speaker}: {text}" for speaker, text in recent[-4:]) or "none"
    prompt = (
        "This audio is a meeting playing through a laptop speaker. Several people may be heard. "
        "Transcribe every spoken turn and translate each turn into English. "
        "Label distinct voices Person A, Person B, Person C, in the order they first speak. "
        f"Speakers already used in this meeting: {roster}. "
        "Reuse an existing name when it is the same voice or the sentence continues that person. "
        "Use the next unused Person letter only for a clearly different voice. "
        f"Recent lines:\n{history}\n"
        'Return JSON {"turns":[{"speaker":"Person A","language":"hi","text":"...","english":"..."}]}. '
        "language is ISO 639-1. text is the original speech. english is the English translation, "
        "or a copy of text when the speech is already English. If there is no speech, return {\"turns\":[]}."
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
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
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.post(url, params={"key": settings.gemini_api_key}, json=payload)
    if response.status_code >= 400:
        logger.warning("gemini speaker transcription failed with status %s", response.status_code)
        raise AppError("Gemini could not transcribe that audio.", 502)
    try:
        raw = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        data = parse_json_blob(raw)
    except Exception as exc:
        logger.exception("gemini speaker transcription response was not usable")
        raise AppError("Gemini could not transcribe that audio.", 502) from exc
    turns = data.get("turns") if isinstance(data, dict) else None
    if not isinstance(turns, list):
        text = str((data or {}).get("text") or "").strip() if isinstance(data, dict) else ""
        if not text:
            return []
        turns = [{"speaker": "Person A", "language": data.get("language"), "text": text, "english": data.get("english") or ""}]
    parsed: list[SpeechTurn] = []
    used = list(known_speakers)
    fresh: dict[str, str] = {}
    for item in turns:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        raw_speaker = str(item.get("speaker") or "").strip()
        speaker = canonical_speaker(raw_speaker, used)
        if not speaker:
            speaker = fresh.get(raw_speaker.casefold()) if raw_speaker else None
        if not speaker:
            speaker = next_person(used)
            if raw_speaker:
                fresh[raw_speaker.casefold()] = speaker
        if speaker not in used:
            used.append(speaker)
        language = str(item.get("language") or "").strip().lower().split("-")[0][:16] or None
        english = str(item.get("english") or "").strip()
        parsed.append(SpeechTurn(speaker=speaker, text=text[:8000], language=language, english=english[:8000]))
    return parsed


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
