-- models/staging/stg_niche_scores.sql
-- Only current (latest) niche score per username

WITH source AS (
    SELECT * FROM {{ source('public', 'niche_scores') }}
    WHERE is_current = TRUE
),

deduped AS (
    -- safety dedup: one row per username even if is_current had duplicates
    SELECT DISTINCT ON (username)
        niche_score_id,
        username,
        niche_primary,
        COALESCE(niche_secondary, 'none') AS niche_secondary,
        audience_fit_score,
        brand_safety_score,
        content_quality_score,
        gemini_rationale,
        scored_at
    FROM source
    ORDER BY username, scored_at DESC
)

SELECT * FROM deduped
