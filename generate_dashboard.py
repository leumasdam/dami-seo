#!/usr/bin/env python3
"""
generate_dashboard.py — orchestrator pre dami-seo dashboard.

1. Pokúsi sa stiahnuť GSC + GA4 + PSI dáta (ak sú credentials).
2. Spustí analyze.py rule-based detekciu opportunities.
3. Voliteľne volá Claude API pre AI executive summary.
4. Zapíše data.json pre dashboard.html.

Bez credentials: zapíše current data.json nedotknutý (mock dáta zostávajú).
"""

import os
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
DATA_PATH = ROOT / "data.json"


def main() -> int:
    today = date.today()
    week_no = today.isocalendar()[1]
    print(f"=== Dami SEO Dashboard · KW {week_no:02d} · {today.isoformat()} ===\n")

    # 1. GSC
    try:
        from fetch_gsc import fetch_weeks as fetch_gsc
        gsc = fetch_gsc()
    except Exception as e:
        print(f"  ✗ fetch_gsc.py crash: {e}", file=sys.stderr)
        gsc = None

    # 2. GA4
    try:
        from fetch_ga4 import fetch_weeks as fetch_ga4
        ga4 = fetch_ga4()
    except Exception as e:
        print(f"  ✗ fetch_ga4.py crash: {e}", file=sys.stderr)
        ga4 = None

    # 3. PSI (top 5 stránok)
    try:
        from fetch_psi import fetch_top_urls
        psi_urls = [
            "https://www.dami-pracovne-odevy.sk/",
            "https://www.dami-pracovne-odevy.sk/kategoria/pracovne-rukavice",
            "https://www.dami-pracovne-odevy.sk/kategoria/pracovna-obuv",
            "https://www.dami-pracovne-odevy.sk/kategoria/monterky-panske",
        ]
        psi = fetch_top_urls(psi_urls)
    except Exception as e:
        print(f"  ✗ fetch_psi.py crash: {e}", file=sys.stderr)
        psi = None

    # === Ak chýbajú dáta, nechaj mock ===
    if gsc is None and ga4 is None:
        print("\nℹ Žiadne live dáta nedostupné — data.json zostáva nezmenený (mock).")
        return 0

    # === Analyze ===
    from analyze import (
        diff_queries, find_quick_wins, find_ctr_underperformers,
        find_falling_pages, find_rising_queries, find_cro_opportunities,
        build_top_actions
    )

    if gsc:
        gsc_diff = diff_queries(gsc["current_week"], gsc["previous_week"])
        quick_wins = find_quick_wins(gsc_diff)
        ctr_under = find_ctr_underperformers(gsc_diff)
        falling = find_falling_pages(gsc_diff)
        rising = find_rising_queries(gsc_diff)
    else:
        quick_wins = ctr_under = falling = rising = []

    cro = find_cro_opportunities(ga4["current_week"]) if ga4 else []
    top_actions = build_top_actions(quick_wins, ctr_under, falling, cro, rising)

    # === Aggregate KPIs ===
    kpi = _aggregate_kpi(gsc, ga4)

    # === Build report ===
    report = {
        "lastUpdated": today.isoformat(),
        "week": f"KW {week_no:02d} · {(today - timedelta(days=7)).isoformat()} → {today.isoformat()}",
        "site": "dami-pracovne-odevy.sk",
        "source": "GSC + GA4 + PSI · auto-update Mondays 06:00 UTC",
        "_meta": {
            "gsc_status": "live" if gsc else "pending_credentials",
            "ga4_status": "live" if ga4 else "pending_credentials",
            "psi_status": "live" if psi else "pending_credentials",
            "ai_provider": "claude-opus-4-7" if os.environ.get("ANTHROPIC_API_KEY") else "template-fallback",
        },
        "kpi": kpi,
        "ai_summary": _generate_summary(kpi, quick_wins, falling, top_actions),
        "quick_wins": quick_wins,
        "ctr_underperformers": ctr_under,
        "falling_pages": falling,
        "rising_queries": rising,
        "cro_opportunities": cro,
        "technical": {
            "core_web_vitals": psi if psi else _mock_cwv(),
            "indexed_pages": 0,  # treba zo Sitemap API
            "sitemap_pages": 0,
            "not_indexed": 0,
            "duplicate_titles": 0,
            "missing_meta_desc": 0,
            "missing_h1": 0,
            "missing_product_schema": 0,
        },
        "top_actions_this_week": top_actions,
    }

    DATA_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n✓ data.json updated · {len(quick_wins)} quick wins · {len(top_actions)} top actions")
    return 0


def _aggregate_kpi(gsc, ga4):
    """Zostaví KPI dict z agregovaných GSC + GA4 dát."""
    kpi = {}
    if gsc:
        cur, prev = gsc["current_week"], gsc["previous_week"]
        clicks_cur = sum(r["clicks"] for r in cur)
        clicks_prev = sum(r["clicks"] for r in prev) or 1
        imp_cur = sum(r["impressions"] for r in cur)
        imp_prev = sum(r["impressions"] for r in prev) or 1
        pos_cur = sum(r["position"] * r["impressions"] for r in cur) / imp_cur if imp_cur else 0
        pos_prev = sum(r["position"] * r["impressions"] for r in prev) / imp_prev if imp_prev else 0
        kpi.update({
            "clicks": {"value": clicks_cur, "wow_pct": round((clicks_cur / clicks_prev - 1) * 100, 1)},
            "impressions": {"value": imp_cur, "wow_pct": round((imp_cur / imp_prev - 1) * 100, 1)},
            "avg_position": {"value": round(pos_cur, 1), "wow_delta": round(pos_cur - pos_prev, 1)},
            "ctr": {"value": round(clicks_cur / max(imp_cur, 1) * 100, 2),
                    "wow_delta": round(clicks_cur/max(imp_cur,1)*100 - clicks_prev/max(imp_prev,1)*100, 2)},
        })
    if ga4:
        cur = ga4["current_week"]
        prev = ga4["previous_week"]
        sess_cur = sum(r["sessions"] for r in cur)
        sess_prev = sum(r["sessions"] for r in prev) or 1
        conv_cur = sum(r["conversions"] for r in cur)
        conv_prev = sum(r["conversions"] for r in prev) or 1
        rev_cur = sum(r["revenue"] for r in cur)
        rev_prev = sum(r["revenue"] for r in prev) or 1
        kpi.update({
            "sessions_organic": {"value": sess_cur, "wow_pct": round((sess_cur/sess_prev - 1)*100, 1)},
            "conversion_rate": {"value": round(conv_cur/max(sess_cur,1)*100, 2),
                                "wow_delta": round((conv_cur/max(sess_cur,1) - conv_prev/max(sess_prev,1))*100, 2)},
            "revenue_eur": {"value": int(rev_cur), "wow_pct": round((rev_cur/rev_prev - 1)*100, 1)},
        })
    return kpi


def _generate_summary(kpi, quick_wins, falling, top_actions):
    """Adaptívny template-based 3-vetný summary v SK. Voliteľne Claude API."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if api_key:
        ai = _claude_summary(kpi, quick_wins, falling, top_actions, api_key)
        if ai:
            return ai

    # Template fallback — adaptívne podľa veľkosti webu
    clicks = kpi.get("clicks", {}).get("value", 0)
    impressions = kpi.get("impressions", {}).get("value", 0)
    ctr = kpi.get("ctr", {}).get("value", 0)
    position = kpi.get("avg_position", {}).get("value", 0)
    sessions = kpi.get("sessions_organic", {}).get("value", 0)
    revenue = kpi.get("revenue_eur", {}).get("value", 0)
    clicks_delta = kpi.get("clicks", {}).get("wow_pct", 0)
    sessions_delta = kpi.get("sessions_organic", {}).get("wow_pct", 0)

    # Veta 1: stav webu
    if clicks == 0 and impressions > 50:
        v1 = f"Web má dobrú viditeľnosť (<b>{impressions} zobrazení</b>) ale <b>žiadne kliky</b> v tomto okne — Google ťa ukazuje, ale titulky nezaujmú. CTR <b>{ctr:.2f} %</b> je výrazne pod retail benchmarkom (3-5 %)."
    elif clicks > 0 and clicks < 50:
        v1 = f"Malý objem za sledované obdobie (<b>{clicks} klikov</b>, <b>{impressions} zobrazení</b>). Priemerná pozícia <b>{position:.1f}</b> — viditeľnosť je, ale CTR <b>{ctr:.2f} %</b> ukazuje že title/snippet potrebujú prácu."
    else:
        sign = "+" if clicks_delta > 0 else ""
        v1 = f"Web stabilný: <b>{clicks} klikov</b> ({sign}{clicks_delta:.0f} % vs predošlé obdobie), <b>{impressions} zobrazení</b>, priemerná pozícia <b>{position:.1f}</b>."

    # Veta 2: najsilnejšia opportunity
    if quick_wins:
        q = quick_wins[0]
        v2 = f"Najsilnejšia príležitosť: query <i>{q['query']}</i> na pozícii {q['position']:.1f} s <b>{q['impressions']}</b> zobrazeniami — push do top 3 môže priniesť ~<b>+{q['potential_clicks']} klikov</b>."
    else:
        v2 = "Žiadne jasné quick-win príležitosti v tomto okne — možno je potrebné rozšíriť content alebo zacieliť na nové queries."

    # Veta 3: risk alebo CRO
    if falling:
        f = falling[0]
        v3 = f"Risk: stránka <code>{f['page']}</code> stratila <b>{abs(f['wow_pct']):.0f} %</b> klikov vs predošlé obdobie — odporúčam audit."
    elif revenue == 0 and sessions > 0:
        v3 = f"Organic návštev je <b>{sessions}</b>, ale <b>žiadny atribuovaný nákup</b> — uvažuj nad CRO: pridanie social proof, jasnejšie CTA, decision tree pre kategórie."
    else:
        v3 = 'Pre konkrétne akcie pozri tab Akcie - todo-list zoradený podľa impact/effort.'

    return {"sk": f"{v1} {v2} {v3}"}


def _claude_summary(kpi, quick_wins, falling, top_actions, api_key):
    """Claude API — voliteľný, vráti None pri zlyhaní."""
    import urllib.request
    import urllib.error
    facts = {
        "kpi": kpi,
        "top_quick_win": quick_wins[0] if quick_wins else None,
        "top_falling": falling[0] if falling else None,
        "actions": [a["title"] for a in top_actions[:5]],
    }
    prompt = (
        "Napíš 3-vetný executive summary pre SEO dashboard slovenského e-commerce "
        "(dami-pracovne-odevy.sk — pracovné odevy). Tón: dátový, konkrétny, "
        "pre rozhodovanie. Použi <b>...</b> pre čísla, <i>...</i> pre queries, "
        "<code>...</code> pre URL. Vráť čistý JSON {\"sk\": \"...\"} bez ďalšieho textu.\n\n"
        f"Fakty: {json.dumps(facts, ensure_ascii=False)}"
    )
    body = json.dumps({
        "model": "claude-opus-4-7",
        "max_tokens": 700,
        "messages": [{"role": "user", "content": prompt}]
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read().decode("utf-8"))
        text = payload["content"][0]["text"].strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
        return json.loads(text)
    except Exception as e:
        print(f"  ⚠ Claude API zlyhalo: {e}", file=sys.stderr)
        return None


def _mock_cwv():
    return {
        "lcp_p75_ms": 2840, "cls_p75": 0.08, "inp_p75_ms": 215,
        "lcp_status": "needs_improvement", "cls_status": "good", "inp_status": "good",
    }


if __name__ == "__main__":
    sys.exit(main())
