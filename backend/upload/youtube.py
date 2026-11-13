"""YouTube upload via the official YouTube Data API v3.

One-time setup (on the laptop):
  1. Google Cloud project -> enable "YouTube Data API v3"
  2. OAuth client (Desktop) -> download client_secret_*.json
  3. python scripts/youtube_auth.py --client-secret <file>
     -> saves a token to ~/.hybrid-shorts/yt_token.json

The token lives ONLY on the user's machine. Nothing here sends it
anywhere except Google's own API endpoints.
"""

from __future__ import annotations

import os
import re

TOKEN_PATH = os.environ.get(
    "YT_TOKEN_FILE",
    os.path.join(os.path.expanduser("~"), ".hybrid-shorts", "yt_token.json"))

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def is_configured() -> bool:
    if not os.path.exists(TOKEN_PATH):
        return False
    try:
        import googleapiclient.discovery  # noqa: F401
        import google.oauth2.credentials  # noqa: F401
        return True
    except Exception:
        return False


def _credentials():
    """Saved token load karo; expire ho gaya ho to refresh + re-save."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    return creds


def _authorized_http(creds):
    """Credentials ke saath 60s socket-timeout wala HTTP transport.

    Default transport ka koi timeout nahi hota — ek atka hua chunk
    upload ko hamesha ke liye latka sakta hai (user report 2026-11-13:
    status "progress" par hi ruk gaya tha). 60s timeout ke saath atki
    request fail hogi, hang nahi hogi.

    Transport class ki jagah dhyaan se: google-auth ke NAYE versions
    me `google.auth.transport.httplib2` module hata diya gaya hai —
    user ke WSL par wahi crash aaya ("No module named
    'google.auth.transport.httplib2'", 2026-11-13 shaam). Pehle
    `google_auth_httplib2` try karo (yahi class google-api-python-
    client khud andar use karta hai), phir purana transport, aur
    aakhir me None (caller default credentials flow par gir jayega —
    timeout nahi milega, par upload chalega to sahi)."""
    import httplib2

    http = httplib2.Http(timeout=60)
    try:
        import google_auth_httplib2
        return google_auth_httplib2.AuthorizedHttp(creds, http=http)
    except ImportError:
        pass
    try:
        from google.auth.transport.httplib2 import AuthorizedHttp
        return AuthorizedHttp(creds, http=http)
    except ImportError:
        return None


def _youtube():
    from googleapiclient.discovery import build

    creds = _credentials()
    http = _authorized_http(creds)
    if http is not None:
        return build("youtube", "v3", http=http)
    return build("youtube", "v3", credentials=creds)


def video_id_from_url(url: str) -> str:
    m = re.search(r"(?:v=|shorts/|youtu\.be/)([A-Za-z0-9_-]{6,})", url or "")
    return m.group(1) if m else ""


def upload_video(file_path: str, title: str, description: str = "",
                 tags: list[str] | None = None,
                 privacy_status: str = "public",
                 category_id: str = "24",
                 progress_cb=None) -> str:
    """Upload one video; returns its YouTube watch URL.

    progress_cb(pct) har chunk ke baad call hota hai (0-100), taaki UI
    me asal progress % dikhe — sirf ghumta hua spinner nahi. Chunk fail
    ho to kuch baar retry hota hai; resumable upload hai, dobara chunk
    bhejna safe hai. Saare retries khatm ho jayein to exception uthta
    hai — pehle wala loop bina timeout/retry-limit ke hamesha ke liye
    atak sakta tha."""
    import time as _time

    from googleapiclient.http import MediaFileUpload

    if "#shorts" not in title.lower():
        title = (title[:90] + " #Shorts").strip()
    youtube = _youtube()
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:4900],
            "tags": (tags or []) + ["shorts"],
            "categoryId": category_id,
        },
        "status": {"privacyStatus": privacy_status,
                   "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(file_path, mimetype="video/mp4", resumable=True,
                            chunksize=8 * 1024 * 1024)
    req = youtube.videos().insert(part="snippet,status", body=body,
                                  media_body=media)
    resp = None
    attempts = 0
    while resp is None:
        try:
            status, resp = req.next_chunk()
        except Exception:
            attempts += 1
            if attempts > 5:
                raise
            _time.sleep(min(30, 2 * attempts))
            continue
        if status is not None and progress_cb is not None:
            try:
                progress_cb(int(status.progress() * 100))
            except Exception:
                pass
    vid = resp["id"]
    return f"https://www.youtube.com/watch?v={vid}"


def set_thumbnail(video_id: str, image_path: str) -> None:
    """Video par custom thumbnail lagao (thumbnails.set).

    Note: channel ka custom-thumbnail feature eligible hona chahiye
    (aam taur par phone-verified channel). Nahi ho to API error degi —
    caller use pakad kar user ko bata deta hai, upload fail nahi hota."""
    from googleapiclient.http import MediaFileUpload

    youtube = _youtube()
    youtube.thumbnails().set(
        videoId=video_id,
        media_body=MediaFileUpload(image_path, mimetype="image/jpeg"),
    ).execute()
