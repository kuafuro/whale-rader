"""
Run this ONCE locally to generate GOOGLE_TOKEN_B64.
Then paste the output into your VPS environment variable.

Usage:
  1. Download credentials.json from Google Cloud Console
     (OAuth 2.0 Client ID, Desktop app type)
  2. Place credentials.json in this directory
  3. Run: python auth_setup.py
  4. Copy the printed GOOGLE_TOKEN_B64 value to your server env
"""
import base64
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import os

SCOPES = ['https://www.googleapis.com/auth/calendar']
TOKEN_FILE = 'token.json'
CREDS_FILE = 'credentials.json'


def main():
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDS_FILE):
                print("❌ credentials.json not found!")
                print("Download it from: Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client IDs")
                return
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())

    token_b64 = base64.b64encode(creds.to_json().encode()).decode()
    print("\n✅ Google Calendar authorized!")
    print("\nAdd this to your server environment variables:")
    print(f"\nGOOGLE_TOKEN_B64={token_b64}\n")


if __name__ == '__main__':
    main()
