-- models/staging/stg_campaigns.sql

WITH source AS (
    SELECT * FROM {{ source('public', 'campaigns') }}
)

SELECT
    campaign_id,
    campaign_name,
    brand_name,
    campaign_goal,
    total_budget_eur,
    start_date,
    end_date,
    COALESCE(notes, '')     AS notes,
    created_at
FROM source
