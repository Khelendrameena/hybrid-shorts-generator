"""YouTube transport regression tests (2026-11-13 shaam).

User ke WSL par upload crash hua: "No module named
'google.auth.transport.httplib2'" — google-auth ke naye versions ne
wo module hata diya hai. Pichle upload tests upload_video ko mock
karte the, isliye asli client construction kabhi test hi nahi hua.
Ye tests WAHI construction chalate hain (network nahi — build() ko
fake se badal kar), taaki transport import dobara chup-chaap na toote.
"""
from unittest.mock import Mock

import pytest


def test_authorized_http_builds_with_timeout():
    pytest.importorskip("google_auth_httplib2")
    pytest.importorskip("httplib2")

    from backend.upload.youtube import _authorized_http

    http = _authorized_http(Mock())
    assert http is not None
    # google_auth_httplib2.AuthorizedHttp andar wale httplib2.Http ko
    # wrap karta hai — usi par hamara 60s timeout laga hona chahiye.
    inner = getattr(http, "http", None)
    timeout = getattr(inner, "timeout", None)
    assert timeout == 60


def test_youtube_client_constructs_without_transport_module(monkeypatch):
    pytest.importorskip("googleapiclient.discovery")

    import backend.upload.youtube as yt

    captured = {}

    def fake_build(api, version, **kwargs):
        captured.update(kwargs)
        return "fake-service"

    monkeypatch.setattr(yt, "_credentials", lambda: Mock())
    import googleapiclient.discovery as disc
    monkeypatch.setattr(disc, "build", fake_build)

    svc = yt._youtube()
    assert svc == "fake-service"
    # Ya to timeout-wala http mila, ya credentials fallback — par
    # ModuleNotFoundError bilkul nahi aana chahiye.
    assert ("http" in captured) or ("credentials" in captured)
