#!/usr/bin/env python3
"""
fetch_ga4.py — stiahne GA4 dáta cez Data API.

Vyžaduje:
  - GOOGLE_APPLICATION_CREDENTIALS = path k service account JSON
  - GA4_PROPERTY_ID = numerické ID property (napr. '123456789')

Vracia per-page metriky: sessions, conversions, conversion_rate, revenue,
bounce_rate, avg_session_duration — za posledný a predošlý týždeň.
"""

import os
import sys
from datetime import date, timedelta

try:
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, RunReportRequest, FilterExpression, Filter
    )
    from google.oauth2 import service_account
    GA4_AVAILABLE = True
except ImportError:
    GA4_AVAILABLE = False

PROPERTY_ID = os.environ.get("GA4_PROPERTY_ID", "")
CREDS_PATH = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")


def get_client():
    """Inicializuj GA4 Data API klienta."""
    if not GA4_AVAILABLE:
        print("  ⚠ google-analytics-data nie je nainštalovaný — pip install -r requirements.txt", file=sys.stderr)
        return None
    if not PROPERTY_ID or not CREDS_PATH or not os.path.exists(CREDS_PATH):
        print(f"  ⚠ GA4 credentials chýbajú (PROPERTY_ID alebo creds) — používa mock", file=sys.stderr)
        return None
    try:
        creds = service_account.Credentials.from_service_account_file(
            CREDS_PATH, scopes=["https://www.googleapis.com/auth/analytics.readonly"]
        )
        return BetaAnalyticsDataClient(credentials=creds)
    except Exception as e:
        print(f"  ⚠ GA4 client init zlyhal: {e}", file=sys.stderr)
        return None


def run_report(client, start: str, end: str, channel="Organic Search"):
    """Vráti per-landing-page metriky za daný interval."""
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
    """Current + previous week organic landing-page metrics."""
    client = get_client()
    if not client:
        return None

    today = date.today()
    cur_end = today - timedelta(days=1)
    cur_start = today - timedelta(days=7)
    prev_end = today - timedelta(days=8)
    prev_start = today - timedelta(days=14)

    print(f"  → GA4 fetch: {cur_start} → {cur_end} (current)")
    cur = run_report(client, cur_start.isoformat(), cur_end.isoformat())
    print(f"  → GA4 fetch: {prev_start} → {prev_end} (previous)")
    prev = run_report(client, prev_start.isoformat(), prev_end.isoformat())

    return {"current_week": cur, "previous_week": prev}


if __name__ == "__main__":
    data = fetch_weeks()
    if data is None:
        print("\n✗ GA4 fetch zlyhal alebo credentials chýbajú.", file=sys.stderr)
        sys.exit(1)
    import json
    print(json.dumps(data, indent=2, ensure_ascii=False))
