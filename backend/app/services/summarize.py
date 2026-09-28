import logging

from app.services.extract import SENTIMENTS, Action, Draft, fallback_intelligence, merge_actions
from app.services.llm import active_model_name, complete_json, llm_configured

logger = logging.getLogger(__name__)

_SYSTEM = """You are a meeting analyst. Return JSON only with these keys:
executive_summary (string, 4 to 6 sentences of plain prose),
detailed_summary (string, the executive summary plus what each speaker contributed),
manager_summary (string with exactly three sections titled "Key Decisions:", "Risks:", and "Next Steps:", each followed by lines starting with "- "),
sentiment (one of: positive, neutral, urgent, blocked),
decisions (array of short strings),
action_items (array of objects with assignee, task, and due_label or null),
risks (array of strings),
next_steps (array of short strings).

Sentiment meanings:
- blocked: a person or workstream cannot proceed
- urgent: time pressure or an open risk without a total stop
- positive: progress without a material risk
- neutral: a status update without a strong signal

Use English. Do not invent people. Assignees must be speakers or people named in the transcript.
"""


def _tidy(task: str) -> str:
    task = " ".join(task.split()).strip().rstrip(".")
    if not task:
        return ""
    return task[0].upper() + task[1:]


def _from_model(data: dict, fallback: Draft) -> Draft:
    sentiment = str(data.get("sentiment") or "").strip().lower()
    if sentiment not in SENTIMENTS:
        sentiment = fallback.sentiment

    executive = str(data.get("executive_summary") or "").strip()
    detailed = str(data.get("detailed_summary") or "").strip()
    manager = str(data.get("manager_summary") or "").strip()
    if len(executive) < 40:
        executive = fallback.executive_summary
    if len(detailed) < 40:
        detailed = fallback.detailed_summary
    if "Key Decisions:" not in manager:
        manager = fallback.manager_summary

    def strings(key: str, fallback_values: list[str]) -> list[str]:
        raw = data.get(key)
        if not isinstance(raw, list):
            return fallback_values
        values = [str(item).strip() for item in raw if str(item).strip()]
        return values[:12] or fallback_values

    model_actions: list[Action] = []
    for item in data.get("action_items") or []:
        if not isinstance(item, dict):
            continue
        assignee = str(item.get("assignee") or "").strip()
        task = _tidy(str(item.get("task") or ""))
        due = item.get("due_label")
        due_label = str(due).strip() if isinstance(due, str) and due.strip() else None
        if assignee and task:
            model_actions.append(Action(assignee=assignee, task=task, due_label=due_label))

    return Draft(
        executive_summary=executive,
        detailed_summary=detailed,
        manager_summary=manager,
        sentiment=sentiment,
        decisions=strings("decisions", fallback.decisions),
        risks=strings("risks", fallback.risks),
        next_steps=strings("next_steps", fallback.next_steps),
        action_items=merge_actions(fallback.action_items, model_actions),
        model_name=active_model_name(),
    )


async def analyze(turns: list[dict], title: str) -> Draft:
    fallback = fallback_intelligence(turns, title)
    if not llm_configured() or not turns:
        return fallback
    lines = []
    for turn in turns:
        stamp = turn.get("timestamp") or ""
        speaker = turn.get("speaker") or "Speaker"
        text = turn.get("text") or ""
        lines.append(f"{stamp} {speaker}: {text}".strip())
    body = "\n".join(lines)
    if len(body) > 24000:
        body = "[Earlier transcript truncated]\n" + body[-24000:]
    user = f"Meeting title: {title}\n\nTranscript:\n{body}"
    try:
        data = await complete_json(_SYSTEM, user)
        return _from_model(data, fallback)
    except Exception:
        logger.exception("model summary failed; using transcript fallback")
        return fallback
