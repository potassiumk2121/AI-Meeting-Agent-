from app.services.pdf_report import ReportData, build_pdf


def test_pdf_is_written(tmp_path):
    path = tmp_path / "meeting_2026_09_28.pdf"
    build_pdf(
        ReportData(
            title="RIGORA deployment review",
            when_label="28 Sep 2026 · 10:05 AM",
            platform="Microsoft Teams",
            participants=["Jim", "Pranjay", "David"],
            sentiment="blocked",
            executive_summary="The team discussed deployment issues in RIGORA.",
            detailed_summary="The team discussed deployment issues in RIGORA.",
            manager_summary="Key Decisions:\n- Backend fixed\n\nRisks:\n- Login is blocking users\n\nNext Steps:\n- Fix the login issue",
            decisions=["Backend fixed"],
            risks=["Login is blocking users"],
            next_steps=["Fix the login issue"],
            action_items=[("Pranjay", "Fix the login issue", "open")],
            segments=[("10:05 AM", "Jim", "Today we need to improve RIGORA deployment.", "Today we need to improve RIGORA deployment.")],
            chat=[("10:09 AM", "Jim", "Deployment checklist is in the RIGORA channel.")],
        ),
        path,
    )
    data = path.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(data) > 1000
