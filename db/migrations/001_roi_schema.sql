-- =============================================================
-- Project 02: Influencer ROI Scorer
-- Migration 001 — extends instagram_fake_detector schema
-- Run after Project 01 migrations are applied
-- =============================================================

-- ---------------------------------------------------------------
-- campaigns — one row per brand campaign
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id     SERIAL PRIMARY KEY,
    campaign_name   TEXT NOT NULL,
    brand_name      TEXT NOT NULL,
    campaign_goal   TEXT NOT NULL CHECK (campaign_goal IN (
                        'awareness',      -- reach / impressions
                        'engagement',     -- likes, comments, saves
                        'conversion',     -- clicks, promo code usage
                        'follower_growth' -- new followers for brand
                    )),
    total_budget_eur NUMERIC(12, 2) NOT NULL,
    start_date      DATE,
    end_date        DATE,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------
-- campaign_influencers — the 3-5 accounts being compared
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS campaign_influencers (
    ci_id           SERIAL PRIMARY KEY,
    campaign_id     INT NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
    username        TEXT NOT NULL,
    allocated_budget_eur NUMERIC(12, 2),  -- slice of total budget for this creator
    post_count_contracted INT DEFAULT 1,
    -- FK back to Project 01 profile snapshots (nullable — scraped on demand)
    profile_snapshot_id INT,              -- references profiles.id in P01 DB
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (campaign_id, username)
);

-- ---------------------------------------------------------------
-- niche_scores — LLM-generated niche / audience fit scores
-- cached per username, refreshed weekly
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS niche_scores (
    niche_score_id  SERIAL PRIMARY KEY,
    username        TEXT NOT NULL,
    niche_primary   TEXT,                 -- e.g. "fitness", "tech", "fashion"
    niche_secondary TEXT,
    audience_fit_score NUMERIC(5, 2),     -- 0-100
    brand_safety_score NUMERIC(5, 2),     -- 0-100
    content_quality_score NUMERIC(5, 2),  -- 0-100
    gemini_rationale TEXT,                -- raw LLM reasoning
    scored_at       TIMESTAMPTZ DEFAULT NOW(),
    -- keep 1 active row per username, archive old ones
    is_current      BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_niche_scores_username ON niche_scores(username);
CREATE INDEX IF NOT EXISTS idx_niche_scores_current ON niche_scores(username, is_current);

-- ---------------------------------------------------------------
-- roi_scores — computed ROI per influencer per campaign
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS roi_scores (
    roi_id          SERIAL PRIMARY KEY,
    campaign_id     INT NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
    username        TEXT NOT NULL,

    -- input signals (pulled from Project 01 profiles table)
    followers               BIGINT,
    engagement_rate         NUMERIC(6, 4),
    fake_follower_pct       NUMERIC(5, 2),  -- ghost follower estimate from P01
    authenticity_score      NUMERIC(5, 2),  -- P01 rule-based score (0-100)

    -- budget math
    allocated_budget_eur    NUMERIC(12, 2),
    cost_per_engagement     NUMERIC(10, 4),
    cost_per_1k_reach       NUMERIC(10, 4),

    -- goal-adjusted ROI (formula depends on campaign_goal)
    goal_adjusted_score     NUMERIC(6, 2),  -- 0-100
    roi_rank                INT,            -- 1 = best in this campaign

    -- niche fit (from niche_scores table)
    niche_fit_score         NUMERIC(5, 2),

    -- final composite score
    composite_roi_score     NUMERIC(6, 2),  -- weighted blend: 0-100

    gemini_summary          TEXT,           -- Gemini narrative for this influencer
    scored_at               TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (campaign_id, username)
);

-- ---------------------------------------------------------------
-- audit_log — track every scoring run (good for portfolio demos)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scoring_audit_log (
    log_id          SERIAL PRIMARY KEY,
    campaign_id     INT REFERENCES campaigns(campaign_id),
    usernames       TEXT[],
    scoring_version TEXT DEFAULT '0.1.0',
    duration_ms     INT,
    status          TEXT CHECK (status IN ('success','partial','failed')),
    error_detail    TEXT,
    run_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------
-- View: roi_comparison_view — the main query the Streamlit app uses
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW roi_comparison_view AS
SELECT
    c.campaign_name,
    c.brand_name,
    c.campaign_goal,
    c.total_budget_eur,
    r.username,
    r.followers,
    ROUND(r.engagement_rate * 100, 2)       AS engagement_rate_pct,
    ROUND(r.fake_follower_pct, 1)           AS fake_follower_pct,
    r.authenticity_score,
    r.allocated_budget_eur,
    r.cost_per_engagement,
    r.cost_per_1k_reach,
    r.niche_fit_score,
    r.goal_adjusted_score,
    r.composite_roi_score,
    r.roi_rank,
    r.gemini_summary,
    r.scored_at,
    ns.niche_primary,
    ns.niche_secondary,
    ns.brand_safety_score
FROM roi_scores r
JOIN campaigns c USING (campaign_id)
LEFT JOIN niche_scores ns ON ns.username = r.username AND ns.is_current = TRUE
ORDER BY c.campaign_id, r.roi_rank;

COMMENT ON VIEW roi_comparison_view IS
    'Main read model for Streamlit ROI comparison table — joins campaigns + scores + niche';
