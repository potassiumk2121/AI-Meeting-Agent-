from app.services.speech import canonical_speaker, next_person


def test_person_labels_stay_stable():
    known = ["Person A", "Pranjay"]
    assert canonical_speaker("person a", known) == "Person A"
    assert canonical_speaker("Speaker 2", known) == "Person B"
    assert canonical_speaker("Pranjay", known) == "Pranjay"
    assert canonical_speaker("deep voice", known) == ""
    assert next_person(known) == "Person B"
