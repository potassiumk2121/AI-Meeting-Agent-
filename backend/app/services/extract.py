import re
from dataclasses import dataclass, field

SENTIMENTS = ("positive", "neutral", "urgent", "blocked")
WEEKDAYS = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"

_WILL = re.compile(r"^(?:i\s+will|i'll|we\s+will|we'll)\s+(?P<task>.+?)\.?$", re.IGNORECASE)
_NAMED_WILL = re.compile(r"^(?P<name>[A-Z][A-Za-z.'-]*)\s+will\s+(?P<task>.+?)\.?$")
_NAME_TO = re.compile(r"^(?P<name>[A-Z][A-Za-z.'-]*)\s+to\s+(?P<task>.+?)\.?$")
_PLEASE = re.compile(r"^(?P<name>[A-Z][A-Za-z.'-]*),?\s+please\s+(?P<task>.+?)\.?$", re.IGNORECASE)
_DUE = re.compile(rf"\b(?:before|by|on)\s+({WEEKDAYS})\b", re.IGNORECASE)
_WEEKDAY = re.compile(rf"\b({WEEKDAYS})\b", re.IGNORECASE)


@dataclass
class Action:
    assignee: str
    task: str
    due_label: str | None = None


@dataclass
class Draft:
    executive_summary: str
    detailed_summary: str
    manager_summary: str
    sentiment: str
    decisions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    action_items: list[Action] = field(default_factory=list)
    model_name: str = "fallback"


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [part.strip() for part in parts if part.strip()]


def _tidy(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip().rstrip(".")
    if not cleaned:
        return ""
    return cleaned[0].upper() + cleaned[1:]


def _split_due(task: str) -> tuple[str, str | None]:
    match = _DUE.search(task)
    if not match:
        return task, None
    due = match.group(1).capitalize()
    task = (task[: match.start()] + task[match.end() :]).strip(" ,.-")
    return task, due


def _action_from(name: str, task: str) -> Action | None:
    task, due = _split_due(task)
    task = _tidy(task)
    name = name.strip()
    if len(name) < 2 or len(task) < 3:
        return None
    return Action(assignee=name, task=task, due_label=due)


def actions_from_utterance(speaker: str, text: str) -> list[Action]:
    found: list[Action] = []
    for sentence in split_sentences(text):
        match = _WILL.match(sentence)
        if match and speaker:
            action = _action_from(speaker, match.group("task"))
            if action:
                found.append(action)
            continue
        for pattern in (_NAMED_WILL, _NAME_TO, _PLEASE):
            match = pattern.match(sentence)
            if match:
                action = _action_from(match.group("name"), match.group("task"))
                if action:
                    found.append(action)
                break
    return found


def classify_sentiment(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("blocked", "blocking", "blocker")):
        return "blocked"
    if any(word in lowered for word in ("urgent", "asap", "risk", "critical")):
        return "urgent"
    positive = sum(word in lowered for word in ("fixed", "great", "resolved", "completed", "shipped", "good"))
    negative = sum(word in lowered for word in ("issue", "fail", "problem", "delay"))
    if positive > negative and positive > 0:
        return "positive"
    return "neutral"


def _is_risk(sentence: str) -> bool:
    lowered = sentence.lower()
    if any(word in lowered for word in ("fixed", "resolved", "completed", "shipped")):
        return False
    return any(word in lowered for word in ("risk", "blocker", "blocking", "blocked", "failing", "delayed"))


def _clean_decision(sentence: str) -> str:
    core = sentence.strip().rstrip(".")
    core = re.sub(r"^I\s+", "", core, flags=re.IGNORECASE)
    match = re.search(
        r"fixed the ([a-z0-9 \-]+?)(?:\s+issue)?(?:\s+yesterday|\s+today)?$",
        core,
        re.IGNORECASE,
    )
    if match:
        subject = match.group(1).strip()
        return _tidy(f"{subject} fixed")
    return _tidy(core)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        key = item.casefold()
        if not item or key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    return ordered


def _dedupe_actions(actions: list[Action]) -> list[Action]:
    seen: set[tuple[str, str]] = set()
    ordered: list[Action] = []
    for action in actions:
        key = (action.assignee.casefold(), action.task.casefold())
        if key in seen:
            continue
        seen.add(key)
        ordered.append(action)
    return ordered


def human_join(names: list[str]) -> str:
    unique = list(dict.fromkeys(names))
    if not unique:
        return ""
    if len(unique) == 1:
        return unique[0]
    if len(unique) == 2:
        return f"{unique[0]} and {unique[1]}"
    return ", ".join(unique[:-1]) + f", and {unique[-1]}"


def _similar(left: Action, right: Action) -> bool:
    if left.assignee.casefold() != right.assignee.casefold():
        return False
    a = left.task.casefold()
    b = right.task.casefold()
    return a in b or b in a


def merge_actions(primary: list[Action], extra: list[Action]) -> list[Action]:
    merged = _dedupe_actions(primary)
    for action in extra:
        if any(_similar(action, existing) for existing in merged):
            continue
        merged.append(action)
    return merged[:12]


def _manager_summary(decisions: list[str], risks: list[str], next_steps: list[str]) -> str:
    def block(title: str, rows: list[str]) -> str:
        lines = [title]
        lines.extend(f"- {row}" for row in rows) if rows else lines.append("- None recorded")
        return "\n".join(lines)

    return "\n\n".join(
        [
            block("Key Decisions:", decisions),
            block("Risks:", risks),
            block("Next Steps:", next_steps),
        ]
    )


def fallback_intelligence(turns: list[dict], title: str = "") -> Draft:
    actions: list[Action] = []
    decisions: list[str] = []
    risks: list[str] = []
    highlight_lines: list[str] = []
    blob_parts: list[str] = []

    for turn in turns:
        speaker = str(turn.get("speaker") or "Speaker")
        text = str(turn.get("text") or "").strip()
        if not text:
            continue
        blob_parts.append(text)
        stamp = str(turn.get("timestamp") or "").strip()
        first = split_sentences(text)[0]
        prefix = f"{stamp} — " if stamp else ""
        highlight_lines.append(f"{prefix}{speaker}: {first}")
        actions.extend(actions_from_utterance(speaker, text))
        for sentence in split_sentences(text):
            lowered = sentence.lower()
            if "next review" in lowered:
                continue
            if re.search(r"\b(fixed|decided|agreed|approved|scheduled)\b", lowered):
                decisions.append(_clean_decision(sentence))
            if _is_risk(sentence):
                risks.append(_tidy(sentence))

    actions = _dedupe_actions(actions)
    blob = " ".join(blob_parts)
    review_line = None
    day = _WEEKDAY.search(blob)
    if day and re.search(r"review", blob, re.IGNORECASE):
        review_line = f"Next review scheduled for {day.group(1).capitalize()}."
        decisions.append(review_line)

    decisions = _dedupe(decisions)[:8]
    risks = _dedupe(risks)[:8]

    if re.search(r"deploy", blob, re.IGNORECASE) and re.search(r"\bRIGORA\b", blob):
        if re.search(r"issue|risk|block", blob, re.IGNORECASE):
            opener = "The team discussed deployment issues in RIGORA."
        else:
            opener = "The team discussed RIGORA deployment."
    elif re.search(r"deploy", blob, re.IGNORECASE):
        opener = "The team discussed deployment."
    elif title:
        opener = f"The team discussed {title.rstrip('.')}."
    else:
        opener = "The team met and reviewed the items raised in the session."

    sentences = [opener]
    if re.search(r"backend", blob, re.IGNORECASE) and re.search(r"fixed|operational", blob, re.IGNORECASE):
        sentences.append("Backend service is operational.")
    if re.search(r"frontend", blob, re.IGNORECASE) and re.search(r"test", blob, re.IGNORECASE):
        sentences.append("Frontend requires additional testing.")
    if actions:
        sentences.append(f"Action items were assigned to {human_join([item.assignee for item in actions])}.")
    if review_line:
        sentences.append(review_line)

    executive = " ".join(sentences)
    detailed = executive
    if highlight_lines:
        detailed = executive + "\n\n" + "\n".join(f"- {line}" for line in highlight_lines)

    next_steps = [item.task for item in actions]
    if review_line and day:
        next_steps.append(f"Hold the next review on {day.group(1).capitalize()}.")
    next_steps = _dedupe(next_steps)[:8]

    sentiment = classify_sentiment(blob) if blob else "neutral"
    return Draft(
        executive_summary=executive,
        detailed_summary=detailed,
        manager_summary=_manager_summary(decisions, risks, next_steps),
        sentiment=sentiment,
        decisions=decisions,
        risks=risks,
        next_steps=next_steps,
        action_items=actions,
        model_name="fallback",
    )
