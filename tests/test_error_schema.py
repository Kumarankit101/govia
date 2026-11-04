from __future__ import annotations


def assert_error_envelope(response, status_code: int, code: str) -> None:
    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)
    assert "detail" not in body


def test_unknown_route_uses_standard_error_envelope(client):
    assert_error_envelope(client.get("/route-that-does-not-exist"), 404, "not_found")


def test_unsupported_method_uses_standard_error_envelope_and_preserves_allow(client):
    response = client.put("/observations")
    assert_error_envelope(response, 405, "method_not_allowed")
    assert response.headers["allow"] == "POST"


def test_missing_static_resource_uses_standard_error_envelope(client):
    assert_error_envelope(client.get("/static/missing.css"), 404, "not_found")
