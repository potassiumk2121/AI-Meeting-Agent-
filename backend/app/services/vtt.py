import re


_TIME = re.compile(r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})")
_VOICE = re.compile(r"<v\s+([^>]+)>(.*)", re.IGNORECASE)


def parse_vtt(content: str) -> list[dict]:
    """Parse a Teams-style WebVTT transcript into speaker cues."""
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cues: list[dict] = []
    index = 0
    while index < len(lines):
        match = _TIME.search(lines[index])
        if not match:
            index += 1
            continue
        hours, minutes, seconds, millis = (int(part) for part in match.groups())
        offset_ms = ((hours * 3600 + minutes * 60 + seconds) * 1000) + millis
        index += 1
        text_lines: list[str] = []
        while index < len(lines) and lines[index].strip():
            text_lines.append(lines[index].strip())
            index += 1
        raw = " ".join(text_lines)
        voice = _VOICE.match(raw)
        if voice:
            speaker = voice.group(1).strip()
            text = voice.group(2).replace("</v>", "").strip()
        else:
            speaker = "Speaker"
            text = re.sub(r"<[^>]+>", "", raw).strip()
        if text:
            cues.append({"speaker": speaker, "text": text, "offset_ms": offset_ms})
    return cues
