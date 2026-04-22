-- models/marts/mart_campaign_summary.sql
-- One row per campaign — used for the campaign-level header card in Streamlit

SELECT
    campaign_id,
    campaign_name,
    brand_name,
    campaign_goal,
    total_budget_eur,

    COUNT(username)                                AS influencer_count,
    ROUND(AVG(composite_roi_score), 2)             AS avg_roi_score,
    MAX(composite_roi_score)                       AS best_roi_score,
    MIN(composite_roi_score)                       AS worst_roi_score,

    -- Budget utilisation
    SUM(allocated_budget_eur)                      AS total_allocated_eur,
    ROUND(SUM(allocated_budget_eur) / NULLIF(total_budget_eur, 0) * 100, 1)
                                                   AS budget_utilisation_pct,

    -- Aggregate reach
    SUM(real_audience)                             AS total_real_audience,
    SUM(est_total_engagements)                     AS total_est_engagements,

    -- Cost efficiency
    ROUND(
        SUM(allocated_budget_eur) /
        NULLIF(SUM(est_total_engagements), 0), 4
    )                                              AS blended_cpe,

    -- Top pick
    MAX(CASE WHEN roi_rank = 1 THEN username END)  AS top_roi_influencer

FROM {{ ref('mart_influencer_roi') }}
GROUP BY
    campaign_id,
    campaign_name,
    brand_name,
    campaign_goal,
    total_budget_eur
