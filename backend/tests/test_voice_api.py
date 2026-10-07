from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import main, voice


@pytest.fixture
def client(monkeypatch):
    """The voice endpoint with a stub membership (no database) and a stub 60db."""
    monkeypatch.setenv("SIXTYDB_API_KEY", "test-key")
    monkeypatch.setattr(voice, "_recent", {})
    main.app.dependency_overrides[main.current_member] = lambda: main.Member(
        hid="00000000-0000-0000-0000-000000000001", user_id="user-1", role="member", roommate_id=7,
    )
    yield TestClient(main.app)  # no `with`: skips the lifespan, so no DB pool
    main.app.dependency_overrides.clear()


def stub_stt(monkeypatch, text=None, error=None):
    calls = []

    def transcribe(audio, content_type):
        calls.append((audio, content_type))
        if error:
            raise error
        return text

    monkeypatch.setattr(voice, "transcribe", transcribe)
    return calls


def post(client, body=b"audio", today="2026-10-07", content_type="audio/webm;codecs=opus"):
    return client.post("/api/voice/payment", content=body, params={"today": today},
                       headers={"Content-Type": content_type})


def test_returns_a_draft(client, monkeypatch):
    calls = stub_stt(monkeypatch, "kal DG mein dedh hazaar dale")
    r = post(client)
    assert r.status_code == 200
    assert r.json() == {
        "transcript": "kal DG mein dedh hazaar dale", "amount": 1500.0, "date": "2026-10-06",
        "date_said": True, "meter": "dg", "meter_said": True,
    }
    assert calls == [(b"audio", "audio/webm;codecs=opus")]


def test_uses_the_phones_date_only_if_plausible(client, monkeypatch):
    stub_stt(monkeypatch, "500 today")
    assert post(client, today="2020-01-01").json()["date"] == date.today().isoformat()


def test_not_set_up(client, monkeypatch):
    monkeypatch.delenv("SIXTYDB_API_KEY")
    stub_stt(monkeypatch, "500")
    assert post(client).status_code == 503


def test_empty_and_oversized_recordings(client, monkeypatch):
    stub_stt(monkeypatch, "500")
    assert post(client, body=b"").status_code == 422
    assert post(client, body=b"x" * (main.MAX_VOICE_BYTES + 1)).status_code == 413


def test_silence(client, monkeypatch):
    stub_stt(monkeypatch, "")
    r = post(client)
    assert r.status_code == 422 and "Didn't catch" in r.json()["detail"]


def test_provider_errors_are_passed_on_politely(client, monkeypatch):
    stub_stt(monkeypatch, error=voice.VoiceError(503, "Voice entry is out of credits for this month."))
    r = post(client)
    assert r.status_code == 503 and "out of credits" in r.json()["detail"]


def test_rate_limit(client, monkeypatch):
    stub_stt(monkeypatch, "500")
    codes = [post(client).status_code for _ in range(voice.LIMIT_PER_MINUTE + 1)]
    assert codes[-1] == 429 and set(codes[:-1]) == {200}


def test_transcribe_hides_provider_error_bodies(monkeypatch):
    monkeypatch.setenv("SIXTYDB_API_KEY", "test-key")

    class Resp:
        status_code = 500
        text = "secret internal detail"

    monkeypatch.setattr(voice.requests, "post", lambda *a, **k: Resp())
    with pytest.raises(voice.VoiceError) as exc:
        voice.transcribe(b"audio", "audio/webm")
    assert "secret" not in str(exc.value) and exc.value.status == 502


def test_transcribe_sends_hindi_and_english_hints(monkeypatch):
    monkeypatch.setenv("SIXTYDB_API_KEY", "test-key")
    sent = {}

    class Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"text": " 500 rupees "}

    def fake_post(url, headers, files, data, timeout):
        sent.update(url=url, headers=headers, files=files, data=data)
        return Resp()

    monkeypatch.setattr(voice.requests, "post", fake_post)
    assert voice.transcribe(b"audio", "audio/mp4") == "500 rupees"
    assert sent["url"] == "https://api.60db.ai/stt"
    assert sent["headers"] == {"Authorization": "Bearer test-key"}
    assert sent["files"]["file"][0] == "payment.m4a"
    assert sent["data"]["languages"] == "en,hi"
