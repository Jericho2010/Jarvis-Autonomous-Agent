import pytest
from pathlib import Path

from jarvis.config.paths import capture_public_url, get_webvision_dir


def test_capture_public_url():
    assert capture_public_url("retinal_capture.png") == "/v1/captures/retinal_capture.png"


def test_capture_filename_sanitization_rules():
    invalid = ["../secret.png", "nested/file.png", "..\\secret.png", ""]
    for name in invalid:
        assert "/" in name or "\\" in name or ".." in name or not name


@pytest.mark.asyncio
async def test_capture_route_serves_file(tmp_path, monkeypatch):
    from jarvis.server.app import app
    from fastapi.testclient import TestClient

    capture_dir = tmp_path / "webvision"
    capture_dir.mkdir()
    sample = capture_dir / "sample.png"
    sample.write_bytes(b"fake-png")

    monkeypatch.setattr("jarvis.server.app.get_webvision_dir", lambda: capture_dir)

    client = TestClient(app)
    ok = client.get("/v1/captures/sample.png")
    assert ok.status_code == 200
    assert ok.content == b"fake-png"

    blocked = client.get("/v1/captures/..%2Fsample.png")
    assert blocked.status_code in (400, 404)

    missing = client.get("/v1/captures/missing.png")
    assert missing.status_code == 404
