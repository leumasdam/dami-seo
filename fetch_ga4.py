#!/usr/bin/env python3
"""
fetch_ga4.py — stiahne GA4 dáta cez OAuth.

Vyžaduje:
  - oauth-token.json (vygenerovaný cez oauth_setup.py)
  - GA4_PROPERTY_ID env var
"""

import os
import sys
import json
from datetime import date, timedelta
from pathlib import Path

try:
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, RunReportRequest, FilterExpression, Filter
    )
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    GA4_AVAILABLE = True
except ImportError:
    GA4_AVAILABLE = False

PROPERTY_ID = os.environ.get("GA4_PROPERTY_ID", "")
CREDS_DIR = Path(os.environ.get("DAMI_CREDS_DIR", r"C:\Users\samue\dami-seo-credentials"))
TOKEN_FILE = CREDS_DIR / "oauth-token.json"


def get_credentials():
    if not GA4_AVAILABLE:
        print("  ⚠ Chýba google-analytics-data — pip install -r requirements.txt", file=sys.stderr)
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
        print(f"  ⚠ Nemôžem nájsť OAuth token. Spusti: python oauth_setup.py", file=sys.stderr)
        return None

    creds = Credentials.from_authorized_user_info(token_data, token_data.get("scopes"))

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:
            print(f"  ⚠ Token refresh zlyhal: {e}", file=sys.stderr)
            return None
    return creds


def get_client():
    if not PROPERTY_ID:
        print("  ⚠ GA4_PROPERTY_ID nie je nastavený", file=sys.stderr)
        return None
    creds = get_credentials()
    if not creds:
        return None
    try:
        return BetaAnalyticsDataClient(credentials=creds)
    except Exception as e:
        print(f"  ⚠ GA4 client init zlyhal: {e}", file=sys.stderr)
        return None


def run_report(client, start: str, end: str, channel="Organic Search"):
    request = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[Dimension(name="landingPagePlusQueryString")],
        metrics=[
            Metric(name="sessions"),
            Metric(name="conversions"),
            Metric(name="purchaseRevenue"),
            Metric(name="bounceRate"),
            Metric(name="averageSessionDuration"),
        ],
        date_ranges=[DateRange(start_date=start, end_date=end)],
        dimension_filter=FilterExpression(
            filter=Filter(
                field_name="sessionDefaultChannelGroup",
                string_filter=Filter.StringFilter(value=channel)
            )
        ) if channel else None,
        limit=500,
    )
    try:
        response = client.run_report(request)
    except Exception as e:
        print(f"  ⚠ GA4 report zlyhal: {e}", file=sys.stderr)
        return []

    rows = []
    for r in response.rows:
        rows.append({
            "landing_page": r.dimension_values[0].value,
            "sessions": int(r.metric_values[0].value),
            "conversions": float(r.metric_values[1].value),
            "revenue": float(r.metric_values[2].value),
            "bounce_rate": float(r.metric_values[3].value) * 100,
            "avg_session_sec": float(r.metric_values[4].value),
        })
    return rows


def fetch_weeks():
    client = get_client()
    if not client:
        return None

    window = int(os.environ.get("WINDOW_DAYS", "28"))
    today = date.today()
    cur_end = today - timedelta(days=1)
    cur_start = today - timedelta(days=window)
    prev_end = today - timedelta(days=window + 1)
    prev_start = today - timedelta(days=2*window + 1)

    print(f"  → GA4 fetch: {cur_start} → {cur_end} ({window} dní · current)")
    cur = run_report(client, cur_start.isoformat(), cur_end.isoformat())
    print(f"  → GA4 fetch: {prev_start} → {prev_end} ({window} dní · previous)")
    prev = run_report(client, prev_start.isoformat(), prev_end.isoformat())

    return {"current_week": cur, "previous_week": prev}


if __name__ == "__main__":
    data = fetch_weeks()
    if data is None:
        print("\n✗ GA4 fetch zlyhal alebo token/property chýba.", file=sys.stderr)
        sys.exit(1)
    print(f"\n✓ GA4 OK")
    print(f"  Current week: {len(data['current_week'])} landing pages")
    print(f"  Top 5 podľa návštev:")
    for r in sorted(data["current_week"], key=lambda x: -x["sessions"])[:5]:
        print(f"    {r['sessions']:>4} sess · {r['conversions']:.0f} conv · {r['revenue']:.0f} € · {r['landing_page']}")
