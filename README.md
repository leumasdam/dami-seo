# Dami SEO Dashboard

Automatizovaný týždenný SEO dashboard pre **dami-pracovne-odevy.sk**. Beží na GitHub Actions (cron každý pondelok 06:00 UTC), ťahá dáta z GSC + GA4 + PageSpeed Insights, detekuje opportunities, generuje action plan.

## Stack

- **Vstupy:** Google Search Console API, GA4 Data API, PageSpeed Insights API
- **Analýza:** rule-based opportunity detection (`analyze.py`)
- **AI:** voliteľne Claude API pre executive summary
- **Hosting:** GitHub Pages (zadarmo)
- **Cron:** GitHub Actions (zadarmo, 2000 min/mesiac)

## Čo dashboard robí

| Modul | Detekuje | Akcia |
|---|---|---|
| **Quick wins** | Queries pos 4–15 s rastom impressions | Push content + interné linky → top 3 |
| **CTR optimalizácia** | Pos 1–3 s CTR pod 70 % benchmarku | Title / meta description rewrite |
| **Falling pages** | Stránky s clicks ↓ > 15 % WoW | Audit content drift / competitor / technical |
| **Rising queries** | Nové dopyty s rastúcimi impressions | Nový content alebo H2 do existujúcej stránky |
| **CRO opportunities** | High traffic + low conversion + high bounce | UX / CTA / decision tree návrhy |
| **Core Web Vitals** | LCP / CLS / INP per top 50 URL | Performance optimalizácia |
| **Site audit** | Duplicate titles, missing meta, missing schema | On-page housekeeping |

## Setup (keď budú credentials)

### 1. Google Cloud service account

```
1. console.cloud.google.com → New Project (alebo existing)
2. Enable APIs:
   - Search Console API
   - Google Analytics Data API
   - PageSpeed Insights API
3. IAM → Service Accounts → Create
4. Download JSON key
5. V Search Console + GA4 pridaj email service accountu ako uživateľa (read-only)
```

### 2. GitHub Secrets

V repo Settings → Secrets and variables → Actions:

| Secret | Hodnota |
|---|---|
| `GOOGLE_SA_JSON` | celý obsah JSON kľúča (inline) |
| `GSC_SITE_URL` | napr. `sc-domain:dami-pracovne-odevy.sk` |
| `GA4_PROPERTY_ID` | numerické ID, napr. `123456789` |
| `PSI_API_KEY` | API key z Google Cloud (voliteľné, bez neho 25 req/deň limit) |
| `ANTHROPIC_API_KEY` | sk-ant-… (voliteľné, pre AI summary) |

### 3. Lokálne testovanie

```powershell
# Setup
pip install -r requirements.txt

# Spusti
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\path\to\sa.json"
$env:GSC_SITE_URL = "sc-domain:dami-pracovne-odevy.sk"
$env:GA4_PROPERTY_ID = "123456789"
python generate_dashboard.py

# Pozri dashboard
python -m http.server 8000
# → http://localhost:8000/dashboard.html
```

### 4. GitHub Pages

Settings → Pages → Source: `master` branch / `/ (root)` → Save.

Dashboard bude na `https://<username>.github.io/dami-seo/dashboard.html`.

## Štruktúra

```
dami-seo/
├── dashboard.html          # frontend (multi-tab UI)
├── data.json              # output z weekly run-u (mock → live)
├── fetch_gsc.py           # GSC API klient
├── fetch_ga4.py           # GA4 Data API klient
├── fetch_psi.py           # PageSpeed Insights klient
├── analyze.py             # opportunity detection (rule-based)
├── generate_dashboard.py  # orchestrator
├── requirements.txt
└── .github/workflows/weekly.yml
```

## Bez credentials (mock režim)

Aktuálne dashboard beží na mock dátach kalibrovaných pre SK workwear e-commerce. Po pridaní credentials sa všetko prepne na live — žiadne zmeny v dashboard.html netreba.

## Mesačná cena

| Položka | Cena |
|---|---|
| GitHub Actions (cron) | $0 (free tier 2000 min/mesiac) |
| GitHub Pages hosting | $0 |
| GSC + GA4 API | $0 |
| PageSpeed Insights API | $0 (25 000 req/deň free) |
| Claude API (voliteľné) | ~$2–5 |
| **Total** | **$0–5** |

## Roadmap (po MVP)

- [ ] Backlink monitoring (Ahrefs API alebo lacnejšia alternatíva)
- [ ] Competitor tracking — sledovať top 3 konkurentov v SERP
- [ ] Auto-content generation pre rising queries (cez Claude API)
- [ ] Slack / email notification pri urgentných alertoch
- [ ] Historical trends graf (12 týždňov späť)
