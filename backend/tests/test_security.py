from app.auth import create_token, decode_token, hash_password, verify_password
from app.models import User
from app.services.translate import detect_language, looks_english


def test_password_roundtrip():
    stored = hash_password("ChangeMe!2026")
    assert verify_password("ChangeMe!2026", stored)
    assert not verify_password("wrong-password", stored)


def test_token_roundtrip():
    user = User(email="a@example.com", name="A", password_hash="x")
    payload = decode_token(create_token(user))
    assert payload["email"] == "a@example.com"
    assert payload["sub"] == str(user.id)


def test_language_heuristic():
    assert looks_english("Today we need to improve deployment.")
    assert not looks_english("आज हमें डिप्लॉयमेंट सुधारना है")
    assert detect_language("आज हमें डिप्लॉयमेंट सुधारना है") == "hi"
    assert detect_language("Today we need to improve deployment.") == "en"
