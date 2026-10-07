import pytest
from fastapi.testclient import TestClient

from app import dev_login, main


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "eyJ-service-role")
    monkeypatch.setenv("DEV_LOGIN_EMAILS", "me@example.com, @test.dev")


class Resp:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body or {}

    def json(self):
        return self._body


def stub_supabase(monkeypatch, replies):
    """Each POST pops the next reply; returns the calls made."""
    calls = []

    def post(url, headers, json, timeout):
        calls.append((url.rsplit("/", 1)[-1], headers, json))
        return replies.pop(0)

    monkeypatch.setattr(dev_login.requests, "post", post)
    return calls


def test_off_without_settings(monkeypatch):
    for name in ("SUPABASE_SERVICE_ROLE_KEY", "DEV_LOGIN_EMAILS"):
        monkeypatch.delenv(name, raising=False)
    client = TestClient(main.app)
    assert client.get("/api/dev/login").json() == {"enabled": False, "code": None}
    assert client.post("/api/dev/login", json={"email": "me@example.com", "code": "123456"}).status_code == 404


def test_signs_in_with_the_fixed_code(env, monkeypatch):
    calls = stub_supabase(monkeypatch, [Resp(200, {"hashed_token": "abc", "verification_type": "magiclink"})])
    client = TestClient(main.app)
    assert client.get("/api/dev/login").json() == {"enabled": True, "code": "123456"}
    r = client.post("/api/dev/login", json={"email": " Me@Example.com ", "code": "123456"})
    assert r.status_code == 200 and r.json() == {"token_hash": "abc", "type": "magiclink"}
    endpoint, headers, body = calls[0]
    assert endpoint == "generate_link" and body == {"type": "magiclink", "email": "me@example.com"}
    assert headers == {"apikey": "eyJ-service-role", "Authorization": "Bearer eyJ-service-role"}


def test_new_secret_keys_go_in_apikey_only(env, monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "sb_secret_xyz")
    calls = stub_supabase(monkeypatch, [Resp(200, {"properties": {"hashed_token": "h", "verification_type": "signup"}})])
    assert dev_login.sign_in_token("x@test.dev", "123456") == {"token_hash": "h", "type": "signup"}
    assert calls[0][1] == {"apikey": "sb_secret_xyz"}


def test_creates_a_missing_user_then_retries(env, monkeypatch):
    calls = stub_supabase(monkeypatch, [Resp(404), Resp(200), Resp(200, {"hashed_token": "t", "verification_type": "magiclink"})])
    assert dev_login.sign_in_token("new@test.dev", "123456")["token_hash"] == "t"
    assert [c[0] for c in calls] == ["generate_link", "users", "generate_link"]
    assert calls[1][2] == {"email": "new@test.dev", "email_confirm": True}


@pytest.mark.parametrize("email, code, status", [
    ("someone@else.com", "123456", 403),  # not in DEV_LOGIN_EMAILS
    ("me@example.com", "000000", 401),    # wrong code
])
def test_rejects(env, monkeypatch, email, code, status):
    calls = stub_supabase(monkeypatch, [])
    r = TestClient(main.app).post("/api/dev/login", json={"email": email, "code": code})
    assert r.status_code == status and calls == []  # Supabase never asked


def test_wildcard_allows_anyone(env, monkeypatch):
    monkeypatch.setenv("DEV_LOGIN_EMAILS", "*")
    assert dev_login.email_allowed("anyone@anywhere.com")


def test_bad_key_is_reported_without_supabase_details(env, monkeypatch):
    stub_supabase(monkeypatch, [Resp(401, {"msg": "secret detail"})])
    with pytest.raises(dev_login.DevLoginError) as exc:
        dev_login.sign_in_token("me@example.com", "123456")
    assert exc.value.status == 502 and "secret" not in str(exc.value)
