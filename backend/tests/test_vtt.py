from app.services.vtt import parse_vtt


def test_parse_teams_vtt():
    sample = """WEBVTT

00:00:05.000 --> 00:00:08.000
<v Pranjay>I fixed the backend issue yesterday.</v>
"""
    cues = parse_vtt(sample)
    assert len(cues) == 1
    assert cues[0]["speaker"] == "Pranjay"
    assert cues[0]["text"] == "I fixed the backend issue yesterday."
    assert cues[0]["offset_ms"] == 5000
