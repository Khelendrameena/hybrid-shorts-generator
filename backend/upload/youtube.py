"""YouTube upload via the official YouTube Data API v3.

One-time setup (on the laptop, see CLOUD.md):
  1. Google Cloud project -> enable "YouTube Data API v3"
  2. OAuth client (Desktop) -> download client_secret_*.json
  3. python scripts/youtube_auth.py --client-secret <file>
     -> saves a token to ~/.hybrid-shorts/yt_token.json

The token lives ONLY on the user's machine. Nothing here sends it
anywhere except Google's own API endpoints.
"""

from __future__ import annotations

import os

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


def upload_video(file_path: str, title: str, description: str = "",
                 tags: list[str] | None = None,
                 privacy_status: str = "unlisted",
                 category_id: str = "24") -> str:
    """Upload one video; returns its YouTube watch URL."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    if "#shorts" not in title.lower():
        title = (title[:90] + " #Shorts").strip()
    youtube = build("youtube", "v3", credentials=creds)
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
    while resp is None:
        _status, resp = req.next_chunk()
    vid = resp["id"]
    return f"https://www.youtube.com/watch?v={vid}"
