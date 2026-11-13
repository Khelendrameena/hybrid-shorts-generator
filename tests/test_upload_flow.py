"""Upload flow tests (2026-11-13 fix).

Purana flow: ek hi synchronous request me pura upload — koi progress
nahi, connection atke to status hamesha ke liye "progress" par latka
rehta tha, aur page reload upload fetch ko abort kar deta tha.

Naya flow: route turant {"status": "uploading"} deti hai, asal upload
background thread me chalta hai, progress metadata.upload me likhi
jati hai, fail ho to "failed" + wajah, aur chal rahe upload par dusra
upload start nahi hota (duplicate video guard).
"""
import time

import pytest


def _client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.main import app
    return TestClient(app)


def _make_clip(tmp_path):
    from backend.storage import project_manager as pm

    proj = pm.create_project("Upload test", "youtube",
                             "https://www.youtube.com/watch?v=abc123")
    f = tmp_path / "clip.mp4"
    # Asli mp4 nahi — probe invalid aayega, format guard skip ho jata
    # hai (guard sirf valid-but-galat-format par rokta hai).
    f.write_bytes(b"not-a-real-mp4")
    cid = "clip-upload-" + proj["id"][-8:]
    pm.save_clip({
        "id": cid, "project_id": proj["id"], "start": 0, "end": 30,
        "score": 70, "transcript": "hello", "category": "test",
        "metadata": {"title": "Test Short", "opening_hook": "hook"},
        "status": "rendered", "output_path": str(f),
    })
    return proj["id"], cid


def _upload_state(cid):
    from backend.storage import database as db

    row = db.query_one("SELECT * FROM clips WHERE id=?", (cid,))
    md = db.loads(row.get("metadata"), {})
    return md.get("upload") or {}


def _wait_status(cid, want, timeout=10):
    up = {}
    t0 = time.time()
    while time.time() - t0 < timeout:
        up = _upload_state(cid)
        if up.get("status") == want:
            return up
        time.sleep(0.1)
    raise AssertionError(f"status '{want}' nahi aaya; last={up}")


def _patch_youtube(monkeypatch, upload_impl):
    import backend.upload.thumbnail as thumb_mod
    import backend.upload.youtube as yt_mod

    monkeypatch.setattr(yt_mod, "is_configured", lambda: True)
    monkeypatch.setattr(yt_mod, "upload_video", upload_impl)
    monkeypatch.setattr(yt_mod, "set_thumbnail", lambda *a, **k: None)
    monkeypatch.setattr(thumb_mod, "pick_thumbnail",
                        lambda path, out, text="": str(out))


def test_upload_background_success_with_progress(tmp_path, monkeypatch):
    seen = {}

    def fake_upload(path, title, description="", tags=None,
                    privacy_status="public", progress_cb=None, **kw):
        seen["title"] = title
        if progress_cb:
            progress_cb(40)
            progress_cb(90)
        return "https://www.youtube.com/watch?v=TESTVID123"

    _patch_youtube(monkeypatch, fake_upload)
    _pid, cid = _make_clip(tmp_path)

    r = _client().post(f"/api/clips/{cid}/upload")
    assert r.status_code == 200
    # Route turant wapas aati hai — upload background me hai.
    assert r.json()["status"] == "uploading"

    up = _wait_status(cid, "uploaded")
    assert up["youtube_url"].endswith("TESTVID123")
    assert up["progress"] == 100
    assert up["thumbnail"] == "set"
    assert seen["title"]  # title package bana tha


def test_upload_failure_writes_failed_status(tmp_path, monkeypatch):
    def bad_upload(*a, **kw):
        raise RuntimeError("boom network gaya")

    _patch_youtube(monkeypatch, bad_upload)
    _pid, cid = _make_clip(tmp_path)

    r = _client().post(f"/api/clips/{cid}/upload")
    assert r.status_code == 200 and r.json()["status"] == "uploading"

    up = _wait_status(cid, "failed")
    assert "boom network" in up["error"]


def test_upload_duplicate_guard(tmp_path, monkeypatch):
    calls = {"n": 0}

    def counting_upload(*a, **kw):
        calls["n"] += 1
        return "https://www.youtube.com/watch?v=SHOULDNOTHAPPEN"

    _patch_youtube(monkeypatch, counting_upload)
    _pid, cid = _make_clip(tmp_path)

    from backend.storage import project_manager as pm
    row_md = {"title": "T", "upload": {"status": "uploading",
                                       "progress": 55,
                                       "started_at": time.time()}}
    pm.update_clip(cid, metadata=row_md)

    r = _client().post(f"/api/clips/{cid}/upload")
    assert r.status_code == 200
    assert r.json()["status"] == "uploading"
    assert r.json()["progress"] == 55
    time.sleep(0.5)
    assert calls["n"] == 0  # dusra upload start nahi hua


def test_upload_not_configured(tmp_path, monkeypatch):
    import backend.upload.youtube as yt_mod

    monkeypatch.setattr(yt_mod, "is_configured", lambda: False)
    _pid, cid = _make_clip(tmp_path)

    r = _client().post(f"/api/clips/{cid}/upload")
    assert r.status_code == 400
