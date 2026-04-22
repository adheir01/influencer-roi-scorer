"""
scoring/niche_scorer.py
=======================
Scores influencer niche fit, brand safety, and content quality
using Gemini. Results are cached in the niche_scores table
(refreshed if older than 7 days).

Usage:
    scorer = NicheScorer(db_conn, gemini_api_key)
    result = await scorer.score(username, profile_data, posts_sample)
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Optional
import asyncio

import google.generativeai as genai

logger = logging.getLogger(__name__)

CACHE_TTL_DAYS = 7


@dataclass
class NicheScoreResult:
    username: str
    niche_primary: str
    niche_secondary: Optional[str]
    audience_fit_score: float       # 0-100
    brand_safety_score: float       # 0-100
    content_quality_score: float    # 0-100
    gemini_rationale: str
    scored_at: datetime


NICHE_PROMPT_TEMPLATE = """
You are an expert influencer marketing analyst. Analyze the following Instagram profile
and return a JSON object with your assessment.

PROFILE DATA:
Username: {username}
Followers: {followers:,}
Engagement Rate: {engagement_rate_pct:.2f}%
Bio: {bio}
Recent caption samples (last 5 posts):
{captions}

Respond ONLY with valid JSON — no markdown, no preamble, no explanation outside the JSON.

Required JSON structure:
{{
  "niche_primary": "<single word category e.g. fitness, tech, fashion, food, travel, beauty, gaming, finance, sustainability, parenting>",
  "niche_secondary": "<optional second category or null>",
  "audience_fit_score": <0-100 integer: how well this account reaches its intended niche audience>,
  "brand_safety_score": <0-100 integer: how safe for brand partnerships — 100 = no controversy, clean content>,
  "content_quality_score": <0-100 integer: production quality, consistency, originality>,
  "rationale": "<2-3 sentences explaining the scores>"
}}

Scoring guidance:
- audience_fit_score: penalise if content is scattered across many unrelated niches
- brand_safety_score: penalise for political controversy, crude language, inconsistent values
- content_quality_score: reward originality, clear visual style, consistent posting rhythm
"""


class NicheScorer:
    def __init__(self, db_conn, gemini_api_key: str):
        self.conn = db_conn
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel("gemini-2.5-flash")

    def _is_cached(self, username: str) -> Optional[NicheScoreResult]:
        """Return cached score if fresh, else None."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=CACHE_TTL_DAYS)
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT niche_primary, niche_secondary,
                       audience_fit_score, brand_safety_score,
                       content_quality_score, gemini_rationale, scored_at
                FROM niche_scores
                WHERE username = %s
                  AND is_current = TRUE
                  AND scored_at > %s
            """, (username, cutoff))
            row = cur.fetchone()
        if not row:
            return None
        return NicheScoreResult(
            username=username,
            niche_primary=row[0],
            niche_secondary=row[1],
            audience_fit_score=float(row[2]),
            brand_safety_score=float(row[3]),
            content_quality_score=float(row[4]),
            gemini_rationale=row[5],
            scored_at=row[6],
        )

    def _invalidate_cache(self, username: str):
        """Mark previous scores as not current before inserting new one."""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE niche_scores
                SET is_current = FALSE
                WHERE username = %s AND is_current = TRUE
            """, (username,))
        self.conn.commit()

    def _persist(self, result: NicheScoreResult):
        self._invalidate_cache(result.username)
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO niche_scores
                    (username, niche_primary, niche_secondary,
                     audience_fit_score, brand_safety_score,
                     content_quality_score, gemini_rationale,
                     scored_at, is_current)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)
            """, (
                result.username,
                result.niche_primary,
                result.niche_secondary,
                result.audience_fit_score,
                result.brand_safety_score,
                result.content_quality_score,
                result.gemini_rationale,
                result.scored_at,
            ))
        self.conn.commit()

    def score(
        self,
        username: str,
        profile: dict,
        posts: list[dict],
        force_refresh: bool = False,
    ) -> NicheScoreResult:
        """
        Score a username. Uses cache unless force_refresh=True or cache stale.

        Args:
            username:  Instagram handle
            profile:   dict with keys: followers, engagement_rate, bio
            posts:     list of dicts with key: caption (last N posts)
            force_refresh: bypass cache

        Returns:
            NicheScoreResult
        """
        if not force_refresh:
            cached = self._is_cached(username)
            if cached:
                logger.info(f"Cache hit for niche score: {username}")
                return cached

        captions = "\n".join(
            f"- {p.get('caption', '')[:200]}"
            for p in posts[:5]
            if p.get("caption")
        ) or "(no captions available)"

        prompt = NICHE_PROMPT_TEMPLATE.format(
            username=username,
            followers=profile.get("followers", 0),
            engagement_rate_pct=float(profile.get("engagement_rate", 0)) * 100,
            bio=profile.get("bio", "(no bio)"),
            captions=captions,
        )

        logger.info(f"Calling Gemini for niche score: {username}")
        response = self.model.generate_content(prompt)
        raw = response.text.strip()

        # Strip markdown fences if model adds them anyway
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        data = json.loads(raw)

        result = NicheScoreResult(
            username=username,
            niche_primary=data.get("niche_primary", "unknown"),
            niche_secondary=data.get("niche_secondary"),
            audience_fit_score=float(data.get("audience_fit_score", 50)),
            brand_safety_score=float(data.get("brand_safety_score", 50)),
            content_quality_score=float(data.get("content_quality_score", 50)),
            gemini_rationale=data.get("rationale", ""),
            scored_at=datetime.now(timezone.utc),
        )

        self._persist(result)
        return result

    def score_batch(
        self,
        accounts: list[dict],
        force_refresh: bool = False,
    ) -> list[NicheScoreResult]:
        """
        Score multiple accounts. 
        accounts: list of dicts with keys: username, profile, posts
        """
        results = []
        for account in accounts:
            try:
                r = self.score(
                    username=account["username"],
                    profile=account["profile"],
                    posts=account.get("posts", []),
                    force_refresh=force_refresh,
                )
                results.append(r)
            except Exception as e:
                logger.error(f"Niche scoring failed for {account['username']}: {e}")
                # Fallback neutral score so campaign scoring can continue
                results.append(NicheScoreResult(
                    username=account["username"],
                    niche_primary="unknown",
                    niche_secondary=None,
                    audience_fit_score=50.0,
                    brand_safety_score=50.0,
                    content_quality_score=50.0,
                    gemini_rationale=f"Scoring failed: {str(e)}",
                    scored_at=datetime.now(timezone.utc),
                ))
        return results
