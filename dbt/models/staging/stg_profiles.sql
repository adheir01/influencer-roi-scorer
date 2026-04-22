-- models/staging/stg_profiles.sql
-- Pulls cleaned profile data from Project 01's profiles table.
-- Cast types, rename for consistency, filter out test rows.

WITH source AS (
    SELECT * FROM {{ source('public', 'profiles') }}
),

cleaned AS (
    SELECT
        id                              AS profile_id,
        username,
        full_name,
        followers_count                 AS followers,
        following_count                 AS following,
        media_count                     AS post_count,
        -- engagement rate already computed in P01 pipeline; keep as decimal
        COALESCE(engagement_rate, 0)    AS engagement_rate,
        -- ghost follower estimate: heuristic from P01
        COALESCE(ghost_follower_estimate, 0) AS ghost_follower_pct,
        bio_completeness_score,
        posting_consistency_cv,
        -- P01 rule-based authenticity score
        authenticity_score,
        is_private,
        is_verified,
        scraped_at,
        -- derived
        ROUND(
            CAST(followers_count AS NUMERIC) /
            NULLIF(following_count, 0), 2
        )                               AS follower_following_ratio
    FROM source
    WHERE username IS NOT NULL
      AND username NOT ILIKE '%test%'    -- exclude dev test rows
)

SELECT * FROM cleaned
