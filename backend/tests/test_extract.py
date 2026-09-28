from app.services.extract import fallback_intelligence


def _turns():
    lines = [
        ("Jim", "Today we need to improve RIGORA deployment. The login issue is blocking users.", "10:05 AM"),
        ("Pranjay", "I fixed the backend issue yesterday. I will fix the login issue.", "10:06 AM"),
        ("David", "Let's test the new pipeline. I will test the frontend.", "10:07 AM"),
        (
            "Jim",
            "I will review the deployment before Friday. Frontend deployment is still a risk. Next review is Friday.",
            "10:08 AM",
        ),
    ]
    return [{"speaker": speaker, "text": text, "timestamp": stamp} for speaker, text, stamp in lines]


def test_sample_meeting_intelligence():
    draft = fallback_intelligence(_turns(), title="RIGORA deployment review")
    summary = draft.executive_summary
    assert "The team discussed deployment issues in RIGORA." in summary
    assert "Backend service is operational." in summary
    assert "Frontend requires additional testing." in summary
    assert "Pranjay, David, and Jim" in summary
    assert "Next review scheduled for Friday." in summary
    assert draft.sentiment == "blocked"
    tasks = {(item.assignee, item.task, item.due_label) for item in draft.action_items}
    assert ("Pranjay", "Fix the login issue", None) in tasks
    assert ("David", "Test the frontend", None) in tasks
    assert ("Jim", "Review the deployment", "Friday") in tasks
    assert "Backend fixed" in draft.decisions
    assert "Next review scheduled for Friday." in draft.decisions
    assert any("blocking" in risk for risk in draft.risks)
    assert any("risk" in risk.lower() for risk in draft.risks)
    assert draft.manager_summary.startswith("Key Decisions:")
    assert "Risks:" in draft.manager_summary
    assert "Next Steps:" in draft.manager_summary


def test_positive_and_neutral_sentiment():
    positive = fallback_intelligence(
        [{"speaker": "Ada", "text": "We shipped the update. I fixed the pipeline.", "timestamp": "9:00 AM"}]
    )
    assert positive.sentiment == "positive"
    assert "Pipeline fixed" in positive.decisions
    neutral = fallback_intelligence(
        [{"speaker": "Ada", "text": "We walked through the agenda and shared status.", "timestamp": "9:10 AM"}]
    )
    assert neutral.sentiment == "neutral"
    assert neutral.action_items == []
