-- models/marts/mart_influencer_roi.sql
-- ============================================================
-- Core ROI Mart — THE deliverable that addresses FINN-type roles.
-- 
-- Computes cost-efficiency metrics per influencer per campaign,
-- applies goal-weighting, ranks influencers within each campaign.
--
-- Output: one row per (campaign_id, username)
-- Materialized as TABLE so Streamlit queries are fast.
-- ============================================================

WITH profiles AS (
    SELECT * FROM {{ ref('stg_profiles') }}
),

campaigns AS (
    SELECT * FROM {{ ref('stg_campaigns') }}
),

niche AS (
    SELECT * FROM {{ ref('stg_niche_scores') }}
),

-- Campaign_influencers joins campaigns to the specific accounts being compared
ci AS (
    SELECT
        ci.campaign_id,
        ci.username,
        ci.allocated_budget_eur,
        ci.post_count_contracted
    FROM {{ source('public', 'campaign_influencers') }} ci
),

-- Join everything
joined AS (
    SELECT
        ci.campaign_id,
        c.campaign_name,
        c.brand_name,
        c.campaign_goal,
        c.total_budget_eur,
        ci.username,
        ci.allocated_budget_eur,
        ci.post_count_contracted,

        -- Profile signals (latest scrape for this username)
        p.followers,
        p.following,
        p.engagement_rate,
        p.ghost_follower_pct          AS fake_follower_pct,
        p.authenticity_score,
        p.is_private,
        p.follower_following_ratio,

        -- Niche signals
        COALESCE(n.audience_fit_score, 50)   AS audience_fit_score,
        COALESCE(n.brand_safety_score, 50)   AS brand_safety_score,
        COALESCE(n.content_quality_score, 50) AS content_quality_score,
        n.niche_primary,
        n.niche_secondary

    FROM ci
    JOIN campaigns c USING (campaign_id)
    -- Latest profile snapshot for this username
    LEFT JOIN LATERAL (
        SELECT *
        FROM profiles
        WHERE username = ci.username
        ORDER BY scraped_at DESC
        LIMIT 1
    ) p ON TRUE
    LEFT JOIN niche n USING (username)
),

-- ---------------------------------------------------------------
-- Cost metrics
-- ---------------------------------------------------------------
cost_metrics AS (
    SELECT
        *,
        -- Real audience = followers minus estimated fake
        ROUND(followers * (1.0 - fake_follower_pct / 100.0)) AS real_audience,

        -- Estimated engagements per post (using engagement_rate on real audience)
        ROUND(
            followers * (1.0 - fake_follower_pct / 100.0) * engagement_rate
        ) AS est_engagements_per_post,

        -- Total estimated engagements across contracted posts
        ROUND(
            followers * (1.0 - fake_follower_pct / 100.0)
            * engagement_rate
            * post_count_contracted
        ) AS est_total_engagements,

        -- CPE: cost per engagement
        CASE
            WHEN followers * (1.0 - fake_follower_pct / 100.0)
                 * engagement_rate * post_count_contracted > 0
            THEN ROUND(
                allocated_budget_eur /
                (followers * (1.0 - fake_follower_pct / 100.0)
                 * engagement_rate * post_count_contracted), 4
            )
            ELSE NULL
        END AS cost_per_engagement,

        -- CPM: cost per 1k real reach
        CASE
            WHEN followers > 0
            THEN ROUND(
                (allocated_budget_eur / followers) * 1000.0 *
                (100.0 / NULLIF(100.0 - fake_follower_pct, 0)), 4
            )
            ELSE NULL
        END AS cost_per_1k_reach

    FROM joined
),

-- ---------------------------------------------------------------
-- Goal-adjusted score (0-100)
-- Different campaigns weight signals differently
-- ---------------------------------------------------------------
goal_scores AS (
    SELECT
        *,
        CASE campaign_goal

            -- Awareness: raw reach + brand safety matter most
            WHEN 'awareness' THEN
                ROUND(
                    (LEAST(followers / 100000.0, 1.0) * 40)   -- reach weight 40%
                    + (brand_safety_score * 0.30)              -- safety 30%
                    + ((1.0 - fake_follower_pct / 100.0) * 30) -- authenticity 30%
                , 2)

            -- Engagement: ER + content quality + authenticity
            WHEN 'engagement' THEN
                ROUND(
                    (LEAST(engagement_rate / 0.08, 1.0) * 45) -- ER (8% = perfect) 45%
                    + (content_quality_score * 0.30)           -- quality 30%
                    + ((1.0 - fake_follower_pct / 100.0) * 25) -- authenticity 25%
                , 2)

            -- Conversion: niche fit + engagement + low CPE
            WHEN 'conversion' THEN
                ROUND(
                    (audience_fit_score * 0.40)                -- niche fit 40%
                    + (LEAST(engagement_rate / 0.06, 1.0) * 35) -- ER 35%
                    + (brand_safety_score * 0.25)              -- safety 25%
                , 2)

            -- Follower growth: reach + authenticity
            WHEN 'follower_growth' THEN
                ROUND(
                    (LEAST(followers / 50000.0, 1.0) * 40)
                    + (audience_fit_score * 0.35)
                    + ((1.0 - fake_follower_pct / 100.0) * 25)
                , 2)

            ELSE 50  -- fallback
        END AS goal_adjusted_score

    FROM cost_metrics
),

-- ---------------------------------------------------------------
-- Composite ROI score = goal score + cost efficiency bonus
-- ---------------------------------------------------------------
composite AS (
    SELECT
        *,
        ROUND(
            goal_adjusted_score * 0.70
            -- Budget efficiency: lower CPM = higher score; cap at 30 pts
            + LEAST(
                CASE
                    WHEN cost_per_1k_reach IS NULL THEN 0
                    WHEN cost_per_1k_reach <= 5    THEN 30
                    WHEN cost_per_1k_reach <= 15   THEN 20
                    WHEN cost_per_1k_reach <= 30   THEN 10
                    ELSE 5
                END,
                30
            )
        , 2) AS composite_roi_score
    FROM goal_scores
),

-- ---------------------------------------------------------------
-- Rank within campaign (1 = best ROI)
-- ---------------------------------------------------------------
ranked AS (
    SELECT
        *,
        RANK() OVER (
            PARTITION BY campaign_id
            ORDER BY composite_roi_score DESC
        ) AS roi_rank
    FROM composite
)

-- Final select — clean column order for mart
SELECT
    campaign_id,
    campaign_name,
    brand_name,
    campaign_goal,
    total_budget_eur,
    username,
    allocated_budget_eur,
    post_count_contracted,
    followers,
    real_audience,
    ROUND(engagement_rate * 100, 3)        AS engagement_rate_pct,
    fake_follower_pct,
    authenticity_score,
    est_engagements_per_post,
    est_total_engagements,
    cost_per_engagement,
    cost_per_1k_reach,
    audience_fit_score,
    brand_safety_score,
    content_quality_score,
    niche_primary,
    niche_secondary,
    goal_adjusted_score,
    composite_roi_score,
    roi_rank
FROM ranked
