#!/usr/bin/env python3
"""
fetch_gsc.py — stiahne Search Console dáta cez OAuth.

Vyžaduje:
  - oauth-token.json (vygenerovaný cez oauth_setup.py)
  - GSC_SITE_URL env var, default 'https://www.dami-pracovne-odevy.sk/'

Bez tokenu: vráti None — generate_dashboard použije mock dáta.
"""

import os
import sys
import json
from datetime import date, timedelta
from pathlib import Path

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

SITE_URL = os.environ.get("GSC_SITE_URL", "https://www.dami-pracovne-odevy.sk/")

# Token: lokálne v ~/dami-seo-credentials/, na CI z env var OAUTH_TOKEN_JSON
CREDS_DIR = Path(os.environ.get("DAMI_CREDS_DIR", r"C:\Users\samue\dami-seo-credentials"))
TOKEN_FILE = CREDS_DIR / "oauth-token.json"


def get_credentials():
    """Načíta OAuth credentials z disku alebo z env var OAUTH_TOKEN_JSON (pre CI)."""
    if not GOOGLE_AVAILABLE:
        print("  ⚠ Chýba google-api-python-client — pip install -r requirements.txt", file=sys.stderr)
        return None

    token_json_env = os.environ.get("OAUTH_TOKEN_JSON", "").strip()
    if token_json_env:
        try:
            token_data = json.loads(token_json_env)
        except json.JSONDecodeError as e:
            print(f"  ⚠ OAUTH_TOKEN_JSON nie je platný JSON: {e}", file=sys.stderr)
            return None
    elif TOKEN_FILE.exists():
        token_data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    else:
        print(f"  ⚠ Nemôžem nájsť OAuth token. Spusti najprv: python oauth_setup.py", file=sys.stderr)
        return None

    creds = Credentials.from_authorized_user_info(token_data, token_data.get("scopes"))

    # Refresh ak je expirovaný
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:
            print(f"  ⚠ Token refresh zlyhal: {e}", file=sys.stderr)
            return None

    return creds


def get_service():
    """GSC API klient."""
    creds = get_credentials()
    if not creds:
        return None
    try:
        return build("searchconsole", "v1", credentials=creds, cache_discovery=False)
    except Exception as e:
        print(f"  ⚠ GSC service init zlyhal: {e}", file=sys.stderr)
        return None


def query_gsc(service, start_date: str, end_date: str, dimensions=None, row_limit=1000):
    """Spustí searchanalytics.query."""
    dimensions = dimensions or ["query", "page"]
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": dimensions,
        "rowLimit": row_limit,
        "dataState": "all",
    }
    try:
        return service.searchanalytics().query(siteUrl=SITE_URL, body=body).execute()
    except Exception as e:
        print(f"  ⚠ GSC query zlyhal: {e}", file=sys.stderr)
        return None


def fetch_weeks():
    """Vráti GSC dáta za posledný + predošlý týždeň."""
    service = get_service()
    if not service:
        return None

    today = date.today()
    cur_end = today - timedelta(days=1)
    cur_start = today - timedelta(days=7)
    prev_end = today - timedelta(days=8)
    prev_start = today - timedelta(days=14)

    print(f"  → GSC fetch: {cur_start} → {cur_end} (current)")
    cur = query_gsc(service, cur_start.isoformat(), cur_end.isoformat())
    print(f"  → GSC fetch: {prev_start} → {prev_end} (previous)")
    prev = query_gsc(service, prev_start.isoformat(), prev_end.isoformat())

    if not cur or not prev:
        return None

    return {
        "current_week": parse_rows(cur),
        "previous_week": parse_rows(prev),
        "date_range": {"current": [cur_start.isoformat(), cur_end.isoformat()],
                       "previous": [prev_start.isoformat(), prev_end.isoformat()]},
    }


def parse_rows(response):
    out = []
    for row in response.get("rows", []):
        keys = row.get("keys", [])
        out.append({
            "query": keys[0] if len(keys) > 0 else "",
            "page": keys[1] if len(keys) > 1 else "",
            "clicks": row.get("clicks", 0),
            "impressions": row.get("impressions", 0),
            "ctr": row.get("ctr", 0),
            "position": row.get("position", 0),
        })
    return out


if __name__ == "__main__":
    data = fetch_weeks()
    if data is None:
        print("\n✗ GSC fetch zlyhal alebo token chýba.", file=sys.stderr)
        sys.exit(1)
    print(f"\n✓ GSC OK")
    print(f"  Current week: {len(data['current_week'])} riadkov")
    print(f"  Previous week: {len(data['previous_week'])} riadkov")
    print(f"  Top 5 queries (current):")
    for r in sorted(data["current_week"], key=lambda x: -x["clicks"])[:5]:
        print(f"    {r['clicks']:>4} clicks · {r['impressions']:>5} impr · pos {r['position']:.1f} · {r['query']}")
