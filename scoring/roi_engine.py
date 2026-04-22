"""
scoring/roi_engine.py
=====================
Computes ROI scores for a campaign's influencer lineup.
Orchestrates:
  1. Apify scraping (if profiles not in DB or stale)
  2. Niche scoring via Gemini
  3. ROI formula per campaign goal
  4. Persist to roi_scores table
  5. Trigger dbt run (or direct SQL fallback)

Usage:
    engine = ROIEngine(db_conn, apify_token, gemini_key)
    result = engine.score_campaign(campaign_id)
"""

import logging
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

from scoring.niche_scorer import NicheScorer

logger = logging.getLogger(__name__)

PROFILE_STALENESS_HOURS = 9999  # re-scrape profiles older than this


@dataclass
class CampaignROIResult:
    campaign_id: int
    campaign_name: str
    campaign_goal: str
    influencers: list[dict]    # sorted by roi_rank asc
    gemini_summary: str
    duration_ms: int
    status: str


class ROIEngine:
    def __init__(
        self,
        db_conn,
        apify_token: str,
        gemini_api_key: str,
        run_dbt: bool = True,
    ):
        self.conn = db_conn
        self.apify_token = apify_token
        self.niche_scorer = NicheScorer(db_conn, gemini_api_key)
        self.run_dbt = run_dbt

        import google.generativeai as genai
        genai.configure(api_key=gemini_api_key)
        self._genai_model = genai.GenerativeModel("gemini-2.5-flash")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score_campaign(self, campaign_id: int) -> CampaignROIResult:
        """Full scoring pipeline for a campaign. Returns ranked results."""
        t0 = time.time()
        status = "success"
        error = None

        try:
            campaign = self._fetch_campaign(campaign_id)
            influencers = self._fetch_campaign_influencers(campaign_id)
            usernames = [i["username"] for i in influencers]

            logger.info(f"Scoring campaign {campaign_id}: {usernames}")

            # 1. Ensure profiles are fresh
            profiles = self._ensure_profiles(usernames)

            # 2. Niche scores
            niche_inputs = [
                {
                    "username": u,
                    "profile": profiles.get(u, {}),
                    "posts": self._fetch_recent_posts(u, n=5),
                }
                for u in usernames
            ]
            niche_scores = {
                r.username: r
                for r in self.niche_scorer.score_batch(niche_inputs)
            }

            # 3. Compute ROI scores
            roi_rows = []
            for inf in influencers:
                u = inf["username"]
                p = profiles.get(u, {})
                n = niche_scores.get(u)
                row = self._compute_roi_row(campaign, inf, p, n)
                roi_rows.append(row)

            # 4. Rank within campaign
            roi_rows.sort(key=lambda r: r["composite_roi_score"], reverse=True)
            for rank, row in enumerate(roi_rows, start=1):
                row["roi_rank"] = rank

            # 5. Gemini campaign-level summary
            gemini_summary = self._generate_campaign_summary(campaign, roi_rows)

            # 6. Persist
            self._persist_roi_scores(campaign_id, roi_rows, gemini_summary)

            # 7. Run dbt
            if self.run_dbt:
                self._run_dbt()

        except Exception as e:
            status = "failed"
            error = str(e)
            logger.error(f"Campaign scoring failed: {e}", exc_info=True)
            roi_rows = []
            gemini_summary = ""

        duration_ms = int((time.time() - t0) * 1000)
        self._log_audit(campaign_id, usernames if "usernames" in dir() else [],
                        duration_ms, status, error)

        return CampaignROIResult(
            campaign_id=campaign_id,
            campaign_name=campaign.get("campaign_name", ""),
            campaign_goal=campaign.get("campaign_goal", ""),
            influencers=roi_rows,
            gemini_summary=gemini_summary,
            duration_ms=duration_ms,
            status=status,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_campaign(self, campaign_id: int) -> dict:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM campaigns WHERE campaign_id = %s", (campaign_id,))
            row = cur.fetchone()
        if not row:
            raise ValueError(f"Campaign {campaign_id} not found")
        return dict(row)

    def _fetch_campaign_influencers(self, campaign_id: int) -> list[dict]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT username, allocated_budget_eur, post_count_contracted
                FROM campaign_influencers
                WHERE campaign_id = %s
            """, (campaign_id,))
            return [dict(r) for r in cur.fetchall()]

    def _ensure_profiles(self, usernames: list[str]) -> dict:
        """Return profile dicts. Scrapes via Apify if stale / missing."""
        from apify_client import ApifyClient

        profiles = {}
        to_scrape = []

        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for u in usernames:
                cur.execute("""
                    SELECT * FROM profiles
                    WHERE username = %s
                    ORDER BY scraped_at DESC
                    LIMIT 1
                """, (u,))
                row = cur.fetchone()
                if row:
                    age_hours = (
                        datetime.now(timezone.utc) - row["scraped_at"].replace(tzinfo=timezone.utc)
                    ).total_seconds() / 3600
                    if age_hours < PROFILE_STALENESS_HOURS:
                        profiles[u] = dict(row)
                        continue
                to_scrape.append(u)

        if to_scrape:
            logger.info(f"Scraping {len(to_scrape)} profiles from Apify: {to_scrape}")
            client = ApifyClient(self.apify_token)
            
            # Step 1 — scrape profiles
            run = client.actor("apify/instagram-profile-scraper").call(
                run_input={"usernames": to_scrape}
            )
            items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
            for item in items:
                u = item.get("username", "")
                profiles[u] = {
                    "username": u,
                    "followers": item.get("followersCount", 0) or 0,
                    "following": item.get("followsCount", 0) or 0,
                    "engagement_rate": 0,        # computed below from posts
                    "ghost_follower_pct": 0,     # computed below
                    "authenticity_score": 50,
                    "bio": item.get("biography", ""),
                    "is_private": item.get("isPrivate", False),
                }

            # Step 2 — scrape posts + compute ER using P01 formula
            for u in to_scrape:
                if u not in profiles:
                    continue
                posts_run = client.actor("instagram-scraper/fast-instagram-post-scraper").call(
                    run_input={"instagramUsernames": [u], "postsPerProfile": 12, "retries": 3}
                )
                post_items = list(client.dataset(posts_run["defaultDatasetId"]).iterate_items())
                if post_items:
                    likes    = [int(p.get("like_count") or 0) for p in post_items]
                    comments = [int(p.get("comment_count") or 0) for p in post_items]
                    avg_likes    = sum(likes) / len(likes)
                    avg_comments = sum(comments) / len(comments)
                    followers    = profiles[u]["followers"] or 1
                    er = round((avg_likes + avg_comments) / followers * 100, 4)
                    profiles[u]["engagement_rate"] = er / 100  # store as decimal

                    # Ghost follower estimate — P01 tiered formula
                    if followers > 10_000_000:
                        expected_rate = 0.001
                    elif followers > 1_000_000:
                        expected_rate = 0.005
                    elif followers > 100_000:
                        expected_rate = 0.015
                    else:
                        expected_rate = 0.03
                    actual_rate = avg_likes / followers
                    ghost = max(0, 1 - (actual_rate / expected_rate))
                    profiles[u]["ghost_follower_pct"] = round(min(ghost, 0.99) * 100, 2)

        logger.info(
            "Profile %s: ER=%s, ghost=%s",
            u,
            profiles[u]["engagement_rate"],
            profiles[u]["ghost_follower_pct"],
        )


        return profiles

    def _fetch_recent_posts(self, username: str, n: int = 5) -> list[dict]:
        """Pull post captions from DB for niche scorer context."""
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT post_shortcode AS caption, like_count, comment_count
                FROM post_metrics
                WHERE profile_id = (SELECT id FROM profiles WHERE username = %s)
                ORDER BY scraped_at DESC
                LIMIT %s
            """, (username, n))
            return [dict(r) for r in cur.fetchall()]

    def _compute_roi_row(
        self,
        campaign: dict,
        influencer: dict,
        profile: dict,
        niche,
    ) -> dict:
        """Single-influencer ROI computation (mirrors dbt mart logic in Python)."""
        followers = profile.get("followers", 0) or 0
        er = float(profile.get("engagement_rate", 0) or 0)
        fake_pct = float(profile.get("ghost_follower_pct", 0) or 0)
        auth_score = float(profile.get("authenticity_score", 50) or 50)
        budget = float(influencer.get("allocated_budget_eur", 0) or 0)
        post_count = int(influencer.get("post_count_contracted", 1) or 1)
        goal = campaign.get("campaign_goal", "engagement")

        real_audience = int(followers * (1 - fake_pct / 100))
        est_engagements = int(real_audience * er * post_count)

        cpe = round(budget / est_engagements, 4) if est_engagements > 0 else None
        cpm = round((budget / followers) * 1000 * (100 / max(100 - fake_pct, 1)), 4) if followers > 0 else None

        # Niche signals
        aud_fit = float(niche.audience_fit_score) if niche else 50
        brand_safe = float(niche.brand_safety_score) if niche else 50
        content_q = float(niche.content_quality_score) if niche else 50

        # Goal-adjusted score (matches dbt mart logic)
        if goal == "awareness":
            goal_score = round(
                min(followers / 100000, 1.0) * 40
                + brand_safe * 0.30
                + (1 - fake_pct / 100) * 30, 2
            )
        elif goal == "engagement":
            goal_score = round(
                min(er / 0.08, 1.0) * 45
                + content_q * 0.30
                + (1 - fake_pct / 100) * 25, 2
            )
        elif goal == "conversion":
            goal_score = round(
                aud_fit * 0.40
                + min(er / 0.06, 1.0) * 35
                + brand_safe * 0.25, 2
            )
        elif goal == "follower_growth":
            goal_score = round(
                min(followers / 50000, 1.0) * 40
                + aud_fit * 0.35
                + (1 - fake_pct / 100) * 25, 2
            )
        else:
            goal_score = 50.0

        # Budget efficiency bonus
        if cpm is None:
            eff_bonus = 0
        elif cpm <= 5:
            eff_bonus = 30
        elif cpm <= 15:
            eff_bonus = 20
        elif cpm <= 30:
            eff_bonus = 10
        else:
            eff_bonus = 5

        composite = round(goal_score * 0.70 + min(eff_bonus, 30), 2)

        return {
            "username": influencer["username"],
            "followers": followers,
            "real_audience": real_audience,
            "engagement_rate_pct": round(er * 100, 3),
            "fake_follower_pct": fake_pct,
            "authenticity_score": auth_score,
            "allocated_budget_eur": budget,
            "post_count_contracted": post_count,
            "est_engagements_per_post": int(real_audience * er),
            "est_total_engagements": est_engagements,
            "cost_per_engagement": cpe,
            "cost_per_1k_reach": cpm,
            "audience_fit_score": aud_fit,
            "brand_safety_score": brand_safe,
            "content_quality_score": content_q,
            "niche_primary": niche.niche_primary if niche else "unknown",
            "niche_secondary": niche.niche_secondary if niche else None,
            "goal_adjusted_score": goal_score,
            "composite_roi_score": composite,
            "roi_rank": 0,  # set after sorting
        }

    def _generate_campaign_summary(self, campaign: dict, roi_rows: list[dict]) -> str:
        """One Gemini call for the campaign-level narrative card."""
        try:
            top = roi_rows[0] if roi_rows else {}
            summary_data = [
                f"- @{r['username']}: ROI score {r['composite_roi_score']}, "
                f"ER {r['engagement_rate_pct']}%, {r['followers']:,} followers, "
                f"niche: {r['niche_primary']}, rank #{r['roi_rank']}"
                for r in roi_rows
            ]
            prompt = f"""
    You are a senior influencer marketing strategist.

    Campaign: "{campaign['campaign_name']}" — goal: {campaign['campaign_goal']}
    Budget: €{campaign['total_budget_eur']:,.0f}

    Influencer lineup ranked by ROI score:
    {chr(10).join(summary_data)}

    Write a 3-4 sentence executive summary recommending the best pick(s),
    explaining why, and flagging any risks. Be specific and data-driven.
    Do not use bullet points. Plain paragraph only.
    """
            response = self._genai_model.generate_content(prompt)

            return response.text.strip()
        except Exception as e:
            logger.warning(f"Campaign summary skipped: {e}")
            return "AI summary unavailable — scores computed successfully."

    def _persist_roi_scores(
        self,
        campaign_id: int,
        roi_rows: list[dict],
        gemini_summary: str,
    ):
        with self.conn.cursor() as cur:
            # Clear previous scores for this campaign
            cur.execute(
                "DELETE FROM roi_scores WHERE campaign_id = %s", (campaign_id,)
            )
            for row in roi_rows:
                cur.execute("""
                    INSERT INTO roi_scores (
                        campaign_id, username, followers,
                        engagement_rate, fake_follower_pct, authenticity_score,
                        allocated_budget_eur, cost_per_engagement, cost_per_1k_reach,
                        goal_adjusted_score, roi_rank, niche_fit_score,
                        composite_roi_score, gemini_summary, scored_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                    )
                """, (
                    campaign_id,
                    row["username"],
                    row["followers"],
                    row["engagement_rate_pct"] / 100,
                    row["fake_follower_pct"],
                    row["authenticity_score"],
                    row["allocated_budget_eur"],
                    row["cost_per_engagement"],
                    row["cost_per_1k_reach"],
                    row["goal_adjusted_score"],
                    row["roi_rank"],
                    row["audience_fit_score"],
                    row["composite_roi_score"],
                    gemini_summary,
                ))
        self.conn.commit()

    def _run_dbt(self):
        """Trigger dbt run after scoring. Fails gracefully."""
        try:
            result = subprocess.run(
                ["dbt", "run", "--models", "mart_influencer_roi mart_campaign_summary"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd="dbt",
            )
            if result.returncode != 0:
                logger.warning(f"dbt run non-zero exit: {result.stderr[:500]}")
            else:
                logger.info("dbt run completed successfully")
        except Exception as e:
            logger.warning(f"dbt run skipped: {e}")

    def _log_audit(
        self,
        campaign_id: int,
        usernames: list[str],
        duration_ms: int,
        status: str,
        error: Optional[str],
    ):
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO scoring_audit_log
                        (campaign_id, usernames, duration_ms, status, error_detail)
                    VALUES (%s, %s, %s, %s, %s)
                """, (campaign_id, usernames, duration_ms, status, error))
            self.conn.commit()
        except Exception as e:
            logger.warning(f"Audit log failed: {e}")
