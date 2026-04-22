# Influencer ROI Scorer 



> A decision-support system for evaluating and ranking influencers based on campaign ROI, combining engagement signals, audience authenticity, and cost efficiency into a unified scoring framework.
 Built by [Tobi](https://github.com/adheir01).

This project is part of a larger Marketing Decision Intelligence System:

  - **Project 01:** [Instagram Fake Follower Detector](https://github.com/adheir01/instagram-fake-detector)
  - **Project 02**  Influencer ROI Scorer

---

## What it does

Input a campaign goal, budget, and 3–5 Instagram handles. The system then:
      
**Create a data pipeline**    
  - Scrapes fresh profile and post data via Apify (two actors — profile scraper + post scraper, joined on username)    
  - Computes engagement rate + authenticity signals
 
**Scoring Layer**
  - Applies goal-weighted ROI model
  - Estimates CPM, CPE, and composite ROI score
 
**Analytics layer**  
  - Stores results in PostgreSQL
  - Transforms via dbt (staging → marts)
  - Visualizes insights in a Metabase dashboard

Output: Ranked influencers with ROI scores, cost efficiency metrics, and a campaign-ready recommendation.
 
---

## Stack

| Layer | Tool |
|---|---|
| Scraping | Apify (`apify/instagram-profile-scraper` + `instagram-scraper/fast-instagram-post-scraper`) |
| Feature engineering | Python — ER, ghost follower estimate, posting consistency (mirrors P01 pipeline) |
| Niche scoring | Gemini 2.5 Flash |
| Scoring engine | Python + psycopg2 |
| Metrics layer | **dbt-postgres** — staging + mart models |
| Database | PostgreSQL 15 |
| Operational UI | Streamlit + Plotly |
| BI Dashboard | **Metabase** — connected to dbt mart tables |
| Containerisation | Docker Compose |

---

## Architecture

```
Apify (2 actors)
    ↓ profile data + post data joined on username
Feature Engineering (Python)
    ↓ ER, ghost %, posting consistency
Gemini API
    ↓ niche, brand safety, content quality scores
ROI Engine (Python)
    ↓ goal-weighted score + CPM + CPE + ranking
PostgreSQL (raw tables)
    ↓
dbt (staging → marts)
    ↓
Streamlit UI          Metabase Dashboard
(operational tool)    (BI / analytics layer)
```

---

## dbt Models

```
dbt/models/
  staging/
    stg_profiles.sql        ← cleaned P01 profiles table
    stg_campaigns.sql       ← campaign inputs
    stg_niche_scores.sql    ← LLM niche scores, deduped to current only
  marts/
    mart_influencer_roi.sql     ← core ROI mart, one row per (campaign × influencer)
                                   joins all signals, computes CPM/CPE, ranks with window function
    mart_campaign_summary.sql   ← rollup: one row per campaign
```

 Metabase reads from `mart_influencer_roi` — not raw tables.

---

## Why this architecture

This project implements a full analytics engineering workflow:
    - Raw data ingestion from external APIs
    - Transformaton and modelling using dbt (staging → marts)
    - Servng clean, analysis-ready tables to BI tools
    - Supporting repeatable campaign-level analysis

The goal is to reflect how modern data teams structure pipelines for reliable decision-making, rather than relying on ad-hoc scripts or notebooks

---

## ROI Formula

```
composite_roi_score = goal_adjusted_score × 0.70 + budget_efficiency_bonus (max 30)
```

Goal weights by campaign type:

| Goal | Signals |
|---|---|
| Engagement | ER 45% · content quality 30% · authenticity 25% |
| Awareness | Reach 40% · brand safety 30% · authenticity 30% |
| Conversion | Niche fit 40% · ER 35% · brand safety 25% |
| Follower Growth | Reach 40% · niche fit 35% · authenticity 25% |

Budget efficiency bonus: CPM ≤ €5 → +30pts, ≤ €15 → +20pts, ≤ €30 → +10pts

The model separates peformances (70%) from cost efficiency (30%) to reflect real-world campaign trade-offs: high engagement is valuable, but only if achieved ar a sustainable cost.
---

## Metabase Dashboard

Metabase runs on `http://localhost:3000` and connects directly to the dbt mart tables. Five charts:

| Chart | Table | Proves |
|---|---|---|
| ROI Score Ranking | `roi_scores` | Composite scoring logic |
| ER vs Fake Followers scatter | `roi_scores` | Fraud signal analysis |
| Cost Efficiency table (CPM/CPE) | `roi_scores` | Media buying metrics |
| Campaign Budget Utilisation | `campaigns` + `roi_scores` | Operations analytics |
| Influencer Performance Over Time | `roi_scores` | Longitudinal analysis |

---

## Local Setup

```bash
# 1. Clone
git clone https://github.com/adheir01/influencer-roi-scorer
cd influencer-roi-scorer

# 2. Install dependencies (uv recommended)
uv sync
# or: pip install -r requirements.txt

# 3. Copy env and fill in keys
cp .env.example .env

# 4. Start DB
docker-compose up -d db

# 5. Run P01 schema first, then P02 migration
# (P01 schema creates profiles + post_metrics tables)
Get-Content path/to/instagram-fake-detector/db/schema.sql | docker exec -i influencer-roi-scorer-db-1 psql -U postgres -d postgres
Get-Content db/migrations/001_roi_schema.sql | docker exec -i influencer-roi-scorer-db-1 psql -U postgres -d postgres

# 6. Seed demo data (no Apify credits needed for testing)
python scripts/seed_demo.py

# 7. Start app
streamlit run app/main.py

# 8. Start Metabase (optional)
docker-compose up -d metabase
# Open http://localhost:3000, connect to host: db, port: 5432
```

---

## Environment Variables

```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5433        # 5433 to avoid conflict with P01
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password

APIFY_API_TOKEN=your_apify_token    # same as Project 01
GEMINI_API_KEY=your_gemini_key      # requires billing for >20 req/day
```

---

## Known Limitations

- Ghost follower estimate is heuristic — uses tiered expected engagement rate model, not actual follower analysis
- Private accounts lose confidence — engagement rate cannot be computed
- Gemini niche scoring requires billing enabled — free tier is 20 requests/day
- dbt runs inside Docker container — requires dbt-postgres installed in the image
- ER varies by niche — fitness accounts naturally have higher ER than news accounts; the tiered model partially accounts for this

---

## Project Roadmap

| # | Project | Status |
|---|---|---|
| 01 | Instagram Fake Follower Detector | ✅ Done |
| **02** | **Influencer ROI Scorer** | **This repo** |

## Disclaimer

This project is for educational purposes only. All data is collected via official Apify actors interacting with publicly available Instagram data. Users are responsible for ensuring compliance with Instagram's Terms of Service and applicable data protection laws.
