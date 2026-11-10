from backend.video.downloader import validate_youtube_url


def test_youtube_url_validation():
    assert validate_youtube_url("https://www.youtube.com/watch?v=abc123")
    assert validate_youtube_url("https://youtu.be/abc123")
    assert not validate_youtube_url("https://vimeo.com/123")
    assert not validate_youtube_url("not a url")
    assert not validate_youtube_url("")


def test_api_health_and_project_flow():
    import pytest

    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.main import app

    c = TestClient(app)
    r = c.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"] is True

    r = c.post("/api/projects/youtube", json={"url": "https://example.com/nope"})
    assert r.status_code == 400

    r = c.post("/api/projects/youtube", json={"url": "https://www.youtube.com/watch?v=abc123", "title": "T"})
    assert r.status_code == 200
    pid = r.json()["id"]

    r = c.get(f"/api/projects/{pid}")
    assert r.status_code == 200 and r.json()["clips"] == []

    r = c.get("/api/settings")
    assert r.status_code == 200 and "ollama_model" in r.json()
