import logging

import httpx

from app.config import get_settings
from app.errors import AppError
from app.services.llm import parse_json_blob

logger = logging.getLogger(__name__)


_SCRIPTS = (
    ("hi", 0x0900, 0x0980),
    ("bn", 0x0980, 0x0A00),
    ("pa", 0x0A00, 0x0A80),
    ("gu", 0x0A80, 0x0B00),
    ("or", 0x0B00, 0x0B80),
    ("ta", 0x0B80, 0x0C00),
    ("te", 0x0C00, 0x0C80),
    ("kn", 0x0C80, 0x0D00),
    ("ml", 0x0D00, 0x0D80),
    ("ar", 0x0600, 0x0700),
    ("he", 0x0590, 0x0600),
    ("ru", 0x0400, 0x0500),
    ("el", 0x0370, 0x0400),
    ("ko", 0xAC00, 0xD7B0),
    ("ja", 0x3040, 0x30A0),
    ("ja", 0x30A0, 0x3100),
    ("zh", 0x4E00, 0x9FFF),
)


def looks_english(text: str) -> bool:
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return True
    ascii_letters = [char for char in letters if ord(char) < 128]
    return len(ascii_letters) / len(letters) > 0.9


def detect_language(text: str) -> str:
    counts: dict[str, int] = {}
    for char in text:
        code = ord(char)
        for name, start, end in _SCRIPTS:
            if start <= code < end:
                counts[name] = counts.get(name, 0) + 1
                break
    if counts:
        return max(counts, key=counts.get)
    return "en" if looks_english(text) else "und"


def language_code(text: str, language: str | None) -> str:
    hint = (language or "").strip().lower()
    if hint and hint not in {"und", "auto"}:
        return hint.split("-")[0][:16]
    return detect_language(text)


async def to_english(text: str, language: str | None) -> tuple[str, str]:
    translated, detected = await translate_lines([text], language)
    return translated[0], detected[0]


async def translate_lines(lines: list[str], language: str | None) -> tuple[list[str], list[str]]:
    if not lines:
        return [], []
    settings = get_settings()
    if not settings.gemini_api_key:
        detected = [language_code(line, language) for line in lines]
        if all(code == "en" for code in detected):
            return list(lines), detected
        raise AppError("Set GEMINI_API_KEY to translate speech into English.", 400)
    try:
        return await _gemini_translate(lines, language)
    except AppError:
        raise
    except Exception as exc:
        logger.exception("gemini translation failed")
        raise AppError("Gemini could not translate that line into English.", 502) from exc


async def _gemini_translate(lines: list[str], language: str | None) -> tuple[list[str], list[str]]:
    settings = get_settings()
    translated: list[str] = []
    detected: list[str] = []
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    for start in range(0, len(lines), 20):
        batch = lines[start : start + 20]
        numbered = "\n".join(f"{index + 1}. {line}" for index, line in enumerate(batch))
        system = (
            "Detect the language of each numbered line and translate it into English. "
            'Return JSON {"lines":[{"language":"en","text":"..."}]} with the same count and order. '
            "language is an ISO 639-1 code. If a line is already English, copy it unchanged."
        )
        user = f"Hint: {language or 'detect'}\n\n{numbered}"
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, params={"key": settings.gemini_api_key}, json=payload)
        if response.status_code >= 400:
            logger.warning("gemini translation failed with status %s", response.status_code)
            raise AppError("Gemini could not translate that line into English.", 502)
        raw = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        data = parse_json_blob(raw)
        values = data.get("lines")
        if not isinstance(values, list) or len(values) != len(batch):
            raise AppError("Gemini returned an incomplete translation.", 502)
        for index, item in enumerate(values):
            if isinstance(item, dict):
                text = str(item.get("text") or "").strip()
                code = str(item.get("language") or "").strip().lower().split("-")[0][:16]
            else:
                text = str(item).strip()
                code = ""
            translated.append(text or batch[index])
            detected.append(code or language_code(batch[index], language))
    return translated, detected
