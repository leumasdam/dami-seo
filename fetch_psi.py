#!/usr/bin/env python3
"""
fetch_psi.py — PageSpeed Insights cez verejné API (bez kľúča limit 25 req/deň,
s kľúčom 25k req/deň). API kľúč voliteľný cez PSI_API_KEY env var.

Volá pre top N landing pages a vracia per-URL CWV metriky (LCP, CLS, INP).
"""

import os
import sys
import json
import urllib.request
import urllib.parse
import urllib.error

API_KEY = os.environ.get("PSI_API_KEY", "")
ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def measure(url: str, strategy="mobile"):
    """Vráti dict s p75 LCP/CLS/INP alebo None."""
    params = {"url": url, "strategy": strategy, "category": "performance"}
    if API_KEY:
        params["key"] = API_KEY
    full_url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(full_url, timeout=30) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as e:
        print(f"  ⚠ PSI zlyhal pre {url}: {e}", file=sys.stderr)
        return None

    # CWV z loadingExperience (real user data, p75)
    le = payload.get("loadingExperience", {}).get("metrics", {})
    lcp = le.get("LARGEST_CONTENTFUL_PAINT_MS", {})
    cls = le.get("CUMULATIVE_LAYOUT_SHIFT_SCORE", {})
    inp = le.get("INTERACTION_TO_NEXT_PAINT", {})

    return {
        "url": url,
        "lcp_p75_ms": lcp.get("percentile"),
        "lcp_status": lcp.get("category", "").lower(),
        "cls_p75": cls.get("percentile") / 100 if cls.get("percentile") else None,
        "cls_status": cls.get("category", "").lower(),
        "inp_p75_ms": inp.get("percentile"),
        "inp_status": inp.get("category", "").lower(),
    }


def fetch_top_urls(urls: list):
    """Beží pre zoznam URL, agreguje p75 hodnoty."""
    results = []
    for u in urls:
        r = measure(u)
        if r:
            results.append(r)
    if not results:
        return None
    # priemer p75 hodnôt
    valid_lcp = [r["lcp_p75_ms"] for r in results if r["lcp_p75_ms"]]
    valid_cls = [r["cls_p75"] for r in results if r["cls_p75"] is not None]
    valid_inp = [r["inp_p75_ms"] for r in results if r["inp_p75_ms"]]
    return {
        "lcp_p75_ms": int(sum(valid_lcp) / len(valid_lcp)) if valid_lcp else None,
        "cls_p75": round(sum(valid_cls) / len(valid_cls), 3) if valid_cls else None,
        "inp_p75_ms": int(sum(valid_inp) / len(valid_inp)) if valid_inp else None,
        "per_url": results,
    }


if __name__ == "__main__":
    urls = [
        "https://www.dami-pracovne-odevy.sk/",
        "https://www.dami-pracovne-odevy.sk/kategoria/pracovne-rukavice",
        "https://www.dami-pracovne-odevy.sk/kategoria/pracovna-obuv",
    ]
    print(json.dumps(fetch_top_urls(urls), indent=2, ensure_ascii=False))
