"""
scripts/seed_demo.py
====================
Inserts a demo campaign + fake profile data so you can test the
full scoring pipeline and Streamlit UI locally without burning
Apify credits.

Run:  python scripts/seed_demo.py
"""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from scoring.db import get_connection

DEMO_PROFILES = [
    {
        "username": "demo_fitness_micro",
        "followers": 18400,
        "following": 820,
        "engagement_rate": 0.062,
        "ghost_follower_estimate": 8.2,
        "authenticity_score": 81,
        "bio_completeness_score": 90,
        "posting_consistency_cv": 0.28,
        "is_private": False,
        "is_verified": False,
    },
    {
        "username": "demo_lifestyle_mid",
        "followers": 95000,
        "following": 1200,
        "engagement_rate": 0.031,
        "ghost_follower_estimate": 22.5,
        "authenticity_score": 62,
        "bio_completeness_score": 75,
        "posting_consistency_cv": 0.45,
        "is_private": False,
        "is_verified": False,
    },
    {
        "username": "demo_tech_nano",
        "followers": 6800,
        "following": 310,
        "engagement_rate": 0.091,
        "ghost_follower_estimate": 4.1,
        "authenticity_score": 88,
        "bio_completeness_score": 95,
        "posting_consistency_cv": 0.19,
        "is_private": False,
        "is_verified": True,
    },
    {
        "username": "demo_fashion_macro",
        "followers": 430000,
        "following": 900,
        "engagement_rate": 0.011,
        "ghost_follower_estimate": 38.0,
        "authenticity_score": 45,
        "bio_completeness_score": 60,
        "posting_consistency_cv": 0.70,
        "is_private": False,
        "is_verified": True,
    },
]

DEMO_POSTS = {
    "demo_fitness_micro": [
        "Morning workout done 💪 5km run + 30 min HIIT. Who's joining tomorrow?",
        "New protein shake review — honestly surprised by the taste. Link in bio.",
        "Rest day but still staying active. Walk in the park counts, right? 😄",
        "Q&A on my training plan — full video on YouTube now",
        "12 weeks in. The results speak for themselves 🔥",
    ],
    "demo_lifestyle_mid": [
        "Café hopping in Berlin this weekend ☕ Which one should I visit next?",
        "Unboxing my latest fashion haul — all links in bio!",
        "Work from home setup upgrade 🖥️ Feeling more productive already",
        "Sunday mood 🌿",
        "Partnered with @brandX — honest review dropping tomorrow",
    ],
    "demo_tech_nano": [
        "My honest take on the new M4 MacBook Pro after 2 weeks of daily use",
        "Built a RAG pipeline in under 100 lines of Python. Thread 🧵",
        "AI tools I actually use daily (not the overhyped ones)",
        "Open source contribution of the week — this repo deserves more stars",
        "Data engineering hot take: dbt is not optional anymore",
    ],
    "demo_fashion_macro": [
        "GRWM for Fashion Week 🖤",
        "New collection drop — swipe for all looks",
        "Collab with @luxurybrandY — love this piece",
        "Street style inspo from Milan",
        "Vote for your favourite look below 👇",
    ],
}


def seed():
    conn = get_connection()
    cur = conn.cursor()

    print("Inserting demo profiles into profiles table...")
    for p in DEMO_PROFILES:
        cur.execute("""
            INSERT INTO profiles (
                username, follower_count, following_count,
                post_count, is_private, is_verified
            ) VALUES (
                %(username)s, %(followers)s, %(following)s,
                10, %(is_private)s, %(is_verified)s
            )
            ON CONFLICT (username) DO UPDATE SET
                follower_count = EXCLUDED.follower_count,
                updated_at = NOW()
            RETURNING id
        """, p)
        profile_id = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO fake_signals (
                profile_id, label,
                engagement_rate, ghost_follower_estimate,
                bio_completeness_score, posting_consistency_score,
                follower_following_ratio
            ) VALUES (%s, 'real', %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (
            profile_id,
            p["engagement_rate"],
            p["ghost_follower_estimate"],
            p["bio_completeness_score"],
            p["posting_consistency_cv"],
            round(p["followers"] / max(p["following"], 1), 2),
        ))

    print("Inserting demo posts...")
    for username, captions in DEMO_POSTS.items():
        for i, caption in enumerate(captions):
            cur.execute("""
                INSERT INTO post_metrics (
                    profile_id, post_shortcode, like_count, comment_count
                )
                SELECT id, %s, %s, %s FROM profiles WHERE username = %s
                ON CONFLICT DO NOTHING
            """, (f"demo_{i}", 100 + i * 30, 10 + i * 3, username))

    print("Creating demo campaign...")
    cur.execute("""
        INSERT INTO campaigns (campaign_name, brand_name, campaign_goal, total_budget_eur)
        VALUES ('Demo — FINN Auto Spring 2025', 'FINN Auto', 'engagement', 8000)
        RETURNING campaign_id
    """)
    campaign_id = cur.fetchone()[0]

    budgets = [1500, 2500, 1000, 3000]
    for username, budget in zip([p["username"] for p in DEMO_PROFILES], budgets):
        cur.execute("""
            INSERT INTO campaign_influencers (campaign_id, username, allocated_budget_eur)
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (campaign_id, username, budget))

    conn.commit()
    cur.close()
    conn.close()

    print(f"\n✅ Seeded! Campaign ID: {campaign_id}")
    print(f"   Profiles: {[p['username'] for p in DEMO_PROFILES]}")
    print(f"\nNow run: streamlit run app/main.py")
    print(f"Or score via: python -c \"from scoring.roi_engine import *; ...\"")


if __name__ == "__main__":
    seed()
