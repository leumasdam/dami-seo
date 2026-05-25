#!/usr/bin/env python3
"""
fetch_gsc.py — stiahne Search Console dáta cez Google API.

Vyžaduje:
  - GOOGLE_APPLICATION_CREDENTIALS = path k service account JSON
  - SITE_URL = napr. 'sc-domain:dami-pracovne-odevy.sk' alebo 'https://www.dami-pracovne-odevy.sk/'

Volaná z generate_dashboard.py. Vracia dict s queries + pages za posledný
a predošlý týždeň (na WoW porovnanie).

Bez credentials: vráti None — generate_dashboard použije mock dáta.
"""

import os
import sys
from datetime import date, timedelta

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

SITE_URL = os.environ.get("GSC_SITE_URL", "sc-domain:dami-pracovne-odevy.sk")
CREDS_PATH = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")


def get_service():
    """Inicializuj GSC API klienta. Vráti None ak credentials chýbajú."""
    if not GOOGLE_AVAILABLE:
        print("  ⚠ google-api-python-client nie je nainštalovaný — pip install -r requirements.txt", file=sys.stderr)
        return None
    if not CREDS_PATH or not os.path.exists(CREDS_PATH):
        print(f"  ⚠ GOOGLE_APPLICATION_CREDENTIALS nie sú nastavené — používa mock", file=sys.stderr)
        return None
    try:
        creds = service_account.Credentials.from_service_account_file(
            CREDS_PATH, scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
        )
        return build("searchconsole", "v1", credentials=creds, cache_discovery=False)
    except Exception as e:
        print(f"  ⚠ GSC service init zlyhal: {e}", file=sys.stderr)
        return None


def query_gsc(service, start_date: str, end_date: str, dimensions=None, row_limit=1000):
    """Spustí GSC searchanalytics.query."""
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
    """Stiahne current week (last 7 dní) + previous week (7-14 dní späť)
    a vráti dict so štrukturovanými dátami.
    """
    service = get_service()
    if not service:
        return None

    today = date.today()
    cur_end = today - timedelta(days=1)         # včera
    cur_start = today - timedelta(days=7)       # 7 dní späť
    prev_end = today - timedelta(days=8)        # 8 dní späť
    prev_start = today - timedelta(days=14)     # 14 dní späť

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
    """Z GSC odpovedi vráti list dict {query, page, clicks, impressions, ctr, position}."""
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
        print("\n✗ GSC fetch zlyhal alebo credentials chýbajú.", file=sys.stderr)
        sys.exit(1)
    import json
    print(json.dumps(data, indent=2, ensure_ascii=False))
