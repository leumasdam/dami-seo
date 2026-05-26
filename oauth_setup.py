#!/usr/bin/env python3
"""
oauth_setup.py — jednorázový skript na získanie refresh tokenu cez OAuth.

Vyžaduje:
  - oauth-client.json v C:\\Users\\samue\\dami-seo-credentials\\
    (alebo nastav DAMI_CREDS_DIR env var)

Spusti raz:
    python oauth_setup.py

Otvorí browser, prihlásiš sa Gmailom (samuel.zenko@gmail.com),
povolíš prístup k Search Console + Google Analytics (read-only).
Vygeneruje oauth-token.json — to si potom použiť pre fetch_gsc.py + fetch_ga4.py.

Pozn.: pri prvom spustení môže Google zobraziť varovanie 'This app isn't
verified'. Klikni 'Advanced' → 'Go to dami-seo (unsafe)'. Je to OK lebo
appka je tvoja vlastná a v testing móde.
"""

import os
import json
import sys
from pathlib import Path

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("✗ Chýba google-auth-oauthlib. Spusti:\n  pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)

# Read-only scopes pre GSC + GA4
SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
]

CREDS_DIR = Path(os.environ.get("DAMI_CREDS_DIR", r"C:\Users\samue\dami-seo-credentials"))
CLIENT_FILE = CREDS_DIR / "oauth-client.json"
TOKEN_FILE = CREDS_DIR / "oauth-token.json"


def main():
    if not CLIENT_FILE.exists():
        print(f"✗ Nemôžem nájsť {CLIENT_FILE}", file=sys.stderr)
        print(f"  Skontroluj, že oauth-client.json je v priečinku:")
        print(f"  {CREDS_DIR}")
        return 1

    print(f"→ Načítavam OAuth client z:\n  {CLIENT_FILE}\n")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)

    print("→ Otváram browser pre autorizáciu...")
    print("  Prihlás sa cez samuel.zenko@gmail.com a povol prístup k:")
    print("    • Google Search Console (read-only)")
    print("    • Google Analytics (read-only)")
    print()
    print("  Ak vidíš varovanie 'This app isn't verified':")
    print("    1. Klikni 'Advanced'")
    print("    2. Klikni 'Go to dami-seo (unsafe)'")
    print("    Je to OK — je to tvoja vlastná appka v testing móde.\n")

    creds = flow.run_local_server(port=0, open_browser=True)

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2), encoding="utf-8")
    print(f"\n✓ Token uložený do:\n  {TOKEN_FILE}\n")
    print("Teraz môžeš spustiť:")
    print("  python fetch_gsc.py")
    print("  python fetch_ga4.py")
    print("  python generate_dashboard.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
