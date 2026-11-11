"""One-time YouTube OAuth setup for uploads (run on the laptop).

    python scripts/youtube_auth.py --client-secret /path/client_secret.json

Opens a browser for Google sign-in (use the channel's Google account),
then saves the token to ~/.hybrid-shorts/yt_token.json. The token never
leaves this machine. See CLOUD.md for the Google Cloud setup steps.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.upload.youtube import SCOPES, TOKEN_PATH  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-secret", required=True,
                    help="Google Cloud se download ki hui client_secret JSON")
    args = ap.parse_args()

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(args.client_secret, SCOPES)
    creds = flow.run_local_server(port=0)
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
    print(f"✓ Token save ho gaya: {TOKEN_PATH}")
    print("Ab worker YouTube par upload kar sakta hai.")


if __name__ == "__main__":
    main()
