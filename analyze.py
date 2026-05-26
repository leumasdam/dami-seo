#!/usr/bin/env python3
"""
analyze.py — rule-based opportunity engine.

Vstup: GSC + GA4 weekly dáta (z fetch_gsc.py a fetch_ga4.py).
Výstup: zoznamy `quick_wins`, `ctr_underperformers`, `falling_pages`,
`rising_queries`, `cro_opportunities` + `top_actions_this_week`.

Žiadne AI — čistá logika na thresholdoch a benchmarkoch.
"""

from collections import defaultdict

# === Benchmarky ===
# CTR podľa pozície (Advanced Web Ranking 2024 retail medián)
CTR_BENCHMARK = {
    1: 28.5, 2: 15.7, 3: 11.0, 4: 8.0, 5: 7.2,
    6: 5.1, 7: 4.0, 8: 3.2, 9: 2.8, 10: 2.5
}

# Konverzný benchmark e-com retail (Statista 2024 SK/CZ)
CONV_BENCHMARK = 1.8  # %
BOUNCE_BENCHMARK = 55  # %


def expected_ctr_for_position(pos: float) -> float:
    """Lineárna interpolácia medzi benchmarkmi."""
    pos_int = int(pos)
    if pos_int < 1: return CTR_BENCHMARK[1]
    if pos_int >= 10: return CTR_BENCHMARK[10] * (10 / max(pos, 10))
    a, b = CTR_BENCHMARK[pos_int], CTR_BENCHMARK[pos_int + 1]
    frac = pos - pos_int
    return a + (b - a) * frac


def diff_queries(cur: list, prev: list):
    """Vráti dict query → (cur_row, prev_row) pre WoW porovnanie."""
    cur_map = {(r["query"], r["page"]): r for r in cur}
    prev_map = {(r["query"], r["page"]): r for r in prev}
    keys = set(cur_map) | set(prev_map)
    return {k: (cur_map.get(k), prev_map.get(k)) for k in keys}


# === Detekčné pravidlá ===

def find_quick_wins(gsc_diff, min_impressions=30, min_pos=4, max_pos=20):
    """Queries na pozícii 4-15 s rastom — dajú sa pushnúť do top 3."""
    wins = []
    for (query, page), (cur, prev) in gsc_diff.items():
        if not cur or cur["impressions"] < min_impressions:
            continue
        if not (min_pos <= cur["position"] <= max_pos):
            continue
        # WoW rast
        prev_impressions = prev["impressions"] if prev else 0
        wow_impressions = cur["impressions"] - prev_impressions
        wow_position = cur["position"] - (prev["position"] if prev else cur["position"])

        # Potential klikov: predpoklad že sa dostane na pos 3
        potential_ctr = expected_ctr_for_position(3)
        potential_clicks = int(cur["impressions"] * potential_ctr / 100) - cur["clicks"]

        # Priority score (vyššie = lepšie)
        priority = min(100, int(
            (cur["impressions"] / 10) +
            (max(0, wow_impressions) / 5) +
            (max(0, -wow_position) * 10) +
            (potential_clicks / 2)
        ))

        if potential_clicks > 5:
            wins.append({
                "query": query, "page": page,
                "position": round(cur["position"], 1),
                "impressions": cur["impressions"],
                "clicks": cur["clicks"],
                "ctr": round(cur["ctr"] * 100, 1),
                "wow_impressions": wow_impressions,
                "wow_position": round(wow_position, 1),
                "potential_clicks": potential_clicks,
                "priority": priority,
                "action": _suggest_quick_win_action(query, cur["position"]),
            })
    return sorted(wins, key=lambda x: -x["priority"])[:10]


def find_ctr_underperformers(gsc_diff, max_pos=5, ctr_threshold_pct=0.6):
    """Queries na top 5 pozíciach s CTR pod 60% benchmarku."""
    out = []
    for (query, page), (cur, prev) in gsc_diff.items():
        if not cur or cur["impressions"] < 40:
            continue
        if cur["position"] > max_pos:
            continue
        current_ctr_pct = cur["ctr"] * 100
        expected = expected_ctr_for_position(cur["position"])
        if current_ctr_pct < expected * ctr_threshold_pct:
            potential = int(cur["impressions"] * (expected - current_ctr_pct) / 100)
            out.append({
                "query": query, "page": page,
                "position": round(cur["position"], 1),
                "ctr": round(current_ctr_pct, 2),
                "expected_ctr": round(expected, 1),
                "impressions": cur["impressions"],
                "current_title": "—",  # doplniť z site crawl
                "suggested_title": _suggest_title(query, page),
                "potential_clicks": potential,
                "priority": min(100, int(potential / 2)),
            })
    return sorted(out, key=lambda x: -x["priority"])[:8]


def find_falling_pages(gsc_diff, min_drop_pct=20, min_prev_clicks=3):
    """Stránky čo stratili >15% klikov WoW."""
    page_cur = defaultdict(lambda: {"clicks": 0, "impressions": 0, "positions": []})
    page_prev = defaultdict(lambda: {"clicks": 0, "impressions": 0, "positions": []})
    for (q, p), (cur, prev) in gsc_diff.items():
        if cur:
            page_cur[p]["clicks"] += cur["clicks"]
            page_cur[p]["impressions"] += cur["impressions"]
            page_cur[p]["positions"].append(cur["position"])
        if prev:
            page_prev[p]["clicks"] += prev["clicks"]
            page_prev[p]["impressions"] += prev["impressions"]
            page_prev[p]["positions"].append(prev["position"])

    out = []
    for page, c in page_cur.items():
        p = page_prev.get(page)
        if not p or p["clicks"] < min_prev_clicks:
            continue
        drop = (c["clicks"] / p["clicks"] - 1) * 100
        if drop > -min_drop_pct:
            continue
        avg_pos_now = sum(c["positions"]) / len(c["positions"]) if c["positions"] else 0
        avg_pos_prev = sum(p["positions"]) / len(p["positions"]) if p["positions"] else 0
        out.append({
            "page": page,
            "clicks_now": c["clicks"], "clicks_prev": p["clicks"],
            "wow_pct": round(drop, 1),
            "position_now": round(avg_pos_now, 1),
            "position_prev": round(avg_pos_prev, 1),
            "likely_cause": _diagnose_fall(avg_pos_now, avg_pos_prev),
            "action": "Pozrieť SERP, porovnať s top 3, doplniť chýbajúci obsah",
        })
    return sorted(out, key=lambda x: x["wow_pct"])[:5]


def find_rising_queries(gsc_diff, min_growth_pct=80, min_now=15):
    """Queries s rastom >100% WoW."""
    out = []
    for (query, page), (cur, prev) in gsc_diff.items():
        if not cur or cur["impressions"] < min_now:
            continue
        prev_imp = prev["impressions"] if prev else 0
        if prev_imp == 0:
            growth = None  # nový query
        else:
            growth = (cur["impressions"] / prev_imp - 1) * 100
            if growth < min_growth_pct:
                continue
        out.append({
            "query": query,
            "impressions_now": cur["impressions"],
            "impressions_prev": prev_imp,
            "growth_pct": int(growth) if growth is not None else None,
            "page_ranked": page if page else None,
            "action": _suggest_rising_action(query, page),
        })
    return sorted(out, key=lambda x: -(x["impressions_now"]))[:6]


def find_cro_opportunities(ga4_cur, top_n=5):
    """Stránky s vysokým traffic ale konv. pod priemerom."""
    out = []
    for r in ga4_cur:
        if r["sessions"] < 20:
            continue
        conv_rate = (r["conversions"] / r["sessions"] * 100) if r["sessions"] > 0 else 0
        if conv_rate < CONV_BENCHMARK and r["bounce_rate"] > BOUNCE_BENCHMARK:
            # Lift potential (assume 1pp uplift)
            lift_eur = r["sessions"] * 0.01 * (r["revenue"] / max(r["conversions"], 1))
            out.append({
                "page": r["landing_page"],
                "sessions": r["sessions"],
                "bounce_rate": round(r["bounce_rate"]),
                "conv_rate": round(conv_rate, 1),
                "avg_session_sec": round(r["avg_session_sec"]),
                "issue": _diagnose_cro(r["bounce_rate"], conv_rate, r["avg_session_sec"]),
                "hypothesis": "Audit UX/CTA/social proof na stránke",
                "expected_lift": f"+1 pp konv. = ~{int(lift_eur)} € týždenne",
            })
    return sorted(out, key=lambda x: -x["sessions"])[:top_n]


# === Heuristics / suggestions ===

def _suggest_quick_win_action(query: str, position: float):
    if position > 10:
        return "Pridať 300+ slov technického obsahu + 3 interné linky z autoritných stránok"
    return "Pridať 200 slov + interné linky z najsilnejších stránok, optimalizovať H2/H3"


def _suggest_title(query: str, page: str) -> str:
    """Veľmi jednoduchá template-based suggestion."""
    if "rukavice" in query.lower():
        return "Pracovné rukavice 2026 — Skladom · Doručenie do 24 h"
    if "obuv" in query.lower():
        return "Pracovná obuv S1P / S3 / S5 — všetky bezpečnostné triedy"
    return f"{query.capitalize()} | Doprava zadarmo nad 50 €"


def _diagnose_fall(pos_now, pos_prev):
    drop = pos_now - pos_prev
    if drop > 2:
        return f"Pozícia padla {drop:.1f} miest — možný content drift alebo nový competitor"
    if drop > 0:
        return "Mierny pokles pozície, sledovať trend"
    return "Pozícia stabilná, ale clicks padajú — možno SERP feature alebo seasonal"


def _suggest_rising_action(query: str, page: str):
    if not page:
        return "Nová stránka alebo blog post — query zatiaľ nepokrývaš"
    return "Pridať obsah optimalizovaný na tento query na existujúcu stránku"


def _diagnose_cro(bounce, conv, sec):
    if bounce > 70:
        return "Veľmi vysoká bounce — problém s relevance alebo UX"
    if sec < 30:
        return "Krátka session — návštevník nevie čo má kliknúť"
    return "Konverzia pod benchmarkom"


# === Top action plan generator ===

def build_top_actions(quick_wins, ctr_under, falling, cro, rising):
    """Najlepších 5 akcií týždenne podľa kombinácie impact × effort."""
    actions = []

    if quick_wins:
        q = quick_wins[0]
        actions.append({
            "priority": 1, "type": "quick_win",
            "title": f"{q['query']} — push na pos 1-3",
            "impact": f"+{q['potential_clicks']} klikov/týždeň",
            "effort": "1 h",
            "details": q["action"]
        })
    if ctr_under:
        c = ctr_under[0]
        actions.append({
            "priority": 2, "type": "ctr_rewrite",
            "title": f"Title rewrite — {c['page']}",
            "impact": f"+{c['potential_clicks']} klikov/týždeň (potential)",
            "effort": "10 min",
            "details": f"Súčasný CTR {c['ctr']} % @ pos {c['position']} (benchmark {c['expected_ctr']} %). Nový návrh: '{c['suggested_title']}'"
        })
    if falling:
        f = falling[0]
        actions.append({
            "priority": 3, "type": "falling_audit",
            "title": f"Audit {f['page']} — clicks {f['wow_pct']} % WoW",
            "impact": "Stop ďalšieho prepadu",
            "effort": "30 min",
            "details": f"{f['likely_cause']}. {f['action']}"
        })
    if cro:
        c = cro[0]
        actions.append({
            "priority": 4, "type": "cro",
            "title": f"CRO — {c['page']}",
            "impact": c["expected_lift"],
            "effort": "2 h",
            "details": f"{c['issue']}. {c['hypothesis']}"
        })
    if rising:
        r = rising[0]
        actions.append({
            "priority": 5, "type": "new_content",
            "title": f"Nový obsah — {r['query']}",
            "impact": "Niche query, no competition" if not r.get("page_ranked") else "Optimize existing",
            "effort": "3 h",
            "details": r["action"]
        })
    return actions
