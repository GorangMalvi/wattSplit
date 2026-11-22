import pytest
from fastapi.testclient import TestClient

from app import db, main

HID = "00000000-0000-0000-0000-000000000001"


def client_as(role, monkeypatch):
    main.app.dependency_overrides[main.current_member] = lambda: main.Member(
        hid=HID, user_id="user-1", role=role, roommate_id=7,
    )
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    main.app.dependency_overrides.clear()


def test_owner_deletes_a_month(monkeypatch):
    calls = []
    monkeypatch.setattr(db, "delete_month", lambda hid, month, keep: calls.append((str(hid), month)) or True)
    r = client_as("owner", monkeypatch).delete("/api/months/2026-06")
    assert r.status_code == 204 and calls == [(HID, "2026-06")]


def test_deleting_a_missing_month_is_404(monkeypatch):
    monkeypatch.setattr(db, "delete_month", lambda hid, month, keep: False)
    assert client_as("owner", monkeypatch).delete("/api/months/2026-01").status_code == 404


def test_members_cannot_delete(monkeypatch):
    monkeypatch.setattr(db, "delete_month", lambda *a: pytest.fail("must not delete"))
    monkeypatch.setattr(db, "delete_household", lambda *a: pytest.fail("must not delete"))
    c = client_as("member", monkeypatch)
    assert c.delete("/api/months/2026-06").status_code == 403
    assert c.delete("/api/household", params={"confirm_name": "Golf"}).status_code == 403


def test_household_delete_needs_the_exact_name(monkeypatch):
    deleted = []
    monkeypatch.setattr(db, "get_household", lambda hid: {"id": hid, "name": "Golf_104", "invite_code": "X"})
    monkeypatch.setattr(db, "delete_household", lambda hid: deleted.append(str(hid)) or True)
    c = client_as("owner", monkeypatch)
    assert c.delete("/api/household", params={"confirm_name": "golf_104"}).status_code == 422
    assert c.delete("/api/household").status_code == 422  # no name at all
    assert deleted == []
    assert c.delete("/api/household", params={"confirm_name": " Golf_104 "}).status_code == 204
    assert deleted == [HID]
