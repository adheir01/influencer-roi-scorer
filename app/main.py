"""
app/main.py — Influencer ROI Scorer
"""

import os
import sys
import logging

import streamlit as st
import pandas as pd
import plotly.express as px

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from scoring.db import get_connection
from scoring.roi_engine import ROIEngine

st.set_page_config(
    page_title="ROI Scorer",
    page_icon="ðﾟﾓﾊ",
    layout="wide",
    initial_sidebar_state="collapsed",
)

logging.basicConfig(level=logging.INFO)

# ── CSS ────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

#MainMenu, footer, header { visibility: hidden; }

.inf-card {
    background: #ffffff;
    border: 1px solid #e4e4e7;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 12px;
}
.inf-card:hover {
    border-color: #a1a1aa;
    box-shadow: 0 4px 16px rgba(0,0,0,0.06);
}
.inf-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 14px;
}
.inf-name { font-weight: 600; font-size: 0.95rem; color: #18181b; }
.inf-niche { font-size: 0.75rem; color: #71717a; margin-top: 3px; }
.score-badge {
    font-weight: 700;
    font-size: 0.88rem;
    padding: 4px 12px;
    border-radius: 999px;
    white-space: nowrap;
}
.score-hi { background: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0; }
.score-md { background: #fefce8; color: #ca8a04; border: 1px solid #fde68a; }
.score-lo { background: #fef2f2; color: #dc2626; border: 1px solid #fecaca; }
.inf-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    padding-top: 14px;
    border-top: 1px solid #f4f4f5;
}
.stat-lbl { font-size: 0.65rem; color: #a1a1aa; text-transform: uppercase; letter-spacing: 0.06em; }
.stat-val { font-weight: 600; font-size: 0.85rem; color: #18181b; margin-top: 3px; }
.ai-box {
    background: #18181b;
    color: #e4e4e7;
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 24px;
    line-height: 1.7;
    font-size: 0.9rem;
    font-family: 'Inter', sans-serif;
}
.ai-label {
    font-size: 0.62rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #71717a;
    margin-bottom: 10px;
}
.page-label {
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #a1a1aa;
    margin-bottom: 4px;
}
.page-title {
    font-size: 1.5rem;
    font-weight: 700;
    color: #ffffff !important
    margin-bottom: 2px;
    letter-spacing: -0.02em;
}
.page-sub {
    font-size: 0.85rem;
    color: #71717a;
    margin-bottom: 24px;
}
.metric-row {
    display: flex;
    gap: 16px;
    margin-bottom: 24px;
}
.metric-box {
    background: #fff;
    border: 1px solid #e4e4e7;
    border-radius: 10px;
    padding: 16px 20px;
    flex: 1;
}
.metric-box-label { font-size: 0.72rem; color: #71717a; text-transform: uppercase; letter-spacing: 0.06em; }
.metric-box-value { font-size: 1.4rem; font-weight: 700; color: #18181b; margin-top: 4px; letter-spacing: -0.02em; }
</style>
""", unsafe_allow_html=True)

# ── State ───────────────────────────────────────────────────────
if "result" not in st.session_state:
    st.session_state.result = None

# ── Top nav ─────────────────────────────────────────────────────
nav = st.segmented_control(
    "nav",
    ["New Campaign", "Last Results", "Past Campaigns"],
    default="New Campaign",
    label_visibility="collapsed",
)

st.divider()

# ── Helpers ─────────────────────────────────────────────────────
@st.cache_resource
def _db():
    return get_connection()

def get_engine():
    return ROIEngine(
        db_conn=_db(),
        apify_token=os.environ["APIFY_API_TOKEN"],
        gemini_api_key=os.environ["GEMINI_API_KEY"],
        run_dbt=True,
    )

# ═══════════════════════════════════════════════════════════════
# NEW CAMPAIGN
# ═══════════════════════════════════════════════════════════════
if nav == "New Campaign":

    st.markdown('<div class="page-title">New Campaign</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Compare up to 5 influencers by ROI for your campaign goal.</div>',
                unsafe_allow_html=True)

    col1, col2 = st.columns([3, 2], gap="large")

    with col1:
        campaign_name = st.text_input("Campaign name", placeholder="Summer Drop 2025")
        brand_name    = st.text_input("Brand / company", placeholder="FINN Auto")
        campaign_goal = st.selectbox(
            "Campaign goal",
            ["engagement", "awareness", "conversion", "follower_growth"],
            format_func=lambda x: {
                "engagement":     "Engagement — likes, comments, saves",
                "awareness":      "Awareness — reach & impressions",
                "conversion":     "Conversion — clicks & promo codes",
                "follower_growth":"Follower Growth",
            }[x],
        )
        total_budget = st.number_input("Total budget (€)", min_value=500,
                                       max_value=500_000, value=5000, step=500)

    with col2:
        st.caption("Influencer handles + budget per creator")
        usernames_raw, budgets_raw = [], []
        for i in range(1, 6):
            c1, c2 = st.columns([5, 3])
            u = c1.text_input(f"h{i}", placeholder=f"@handle_{i}", key=f"u{i}",
                              label_visibility="collapsed")
            b = c2.number_input(f"b{i}", min_value=0, max_value=200_000,
                                value=0, step=100, key=f"b{i}",
                                label_visibility="collapsed")
            if u.strip():
                usernames_raw.append(u.strip().lstrip("@"))
                budgets_raw.append(b)

        if usernames_raw:
            st.success(f"{len(usernames_raw)} influencer(s) ready")

    st.divider()

    col_btn, col_note = st.columns([1, 3])
    with col_btn:
        run_btn = st.button("Score Campaign", type="primary", use_container_width=True)
    with col_note:
        st.caption("~30–60 s per influencer. Cached profiles skip the scrape step.")

    if run_btn:
        if not campaign_name or not brand_name:
            st.warning("Enter campaign name and brand.")
        elif len(usernames_raw) < 2:
            st.warning("Add at least 2 handles.")
        elif sum(budgets_raw) == 0:
            st.warning("Allocate budget to at least one influencer.")
        else:
            conn = _db()
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO campaigns
                        (campaign_name, brand_name, campaign_goal, total_budget_eur)
                    VALUES (%s, %s, %s, %s)
                    RETURNING campaign_id
                """, (campaign_name, brand_name, campaign_goal, total_budget))
                campaign_id = cur.fetchone()[0]
                for u, b in zip(usernames_raw, budgets_raw):
                    cur.execute("""
                        INSERT INTO campaign_influencers
                            (campaign_id, username, allocated_budget_eur)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (campaign_id, username) DO NOTHING
                    """, (campaign_id, u, b))
            conn.commit()

            with st.spinner("Scraping · scoring niches · computing ROI..."):
                result = get_engine().score_campaign(campaign_id)
                st.session_state.result = result

            if result.status == "success":
                st.success(f"Done — {len(result.influencers)} influencers scored in {result.duration_ms/1000:.1f}s")
                st.balloons()
                st.rerun()
            else:
                st.error("Scoring failed. Check terminal logs.")

# ═══════════════════════════════════════════════════════════════
# LAST RESULTS
# ═══════════════════════════════════════════════════════════════
elif nav == "Last Results":

    result = st.session_state.result

    # Try loading last campaign from DB if nothing in session
    if result is None:
        try:
            conn = _db()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT campaign_id FROM campaigns
                    ORDER BY created_at DESC LIMIT 1
                """)
                row = cur.fetchone()
            if row:
                with st.spinner("Loading last campaign..."):
                    result = get_engine().score_campaign(row[0])
                    st.session_state.result = result
        except Exception:
            pass

    if result is None:
        st.info("No results yet — run a campaign first.")
        st.stop()

    influencers = result.influencers
    df = pd.DataFrame(influencers)

    goal_labels = {
        "engagement":     "Engagement",
        "awareness":      "Awareness",
        "conversion":     "Conversion",
        "follower_growth":"Follower Growth",
    }

    st.markdown(f'<div class="page-title">{getattr(result, "campaign_name", "Results")}</div>',
                unsafe_allow_html=True)
    st.markdown(f'<div class="page-sub">Goal: {goal_labels.get(result.campaign_goal, result.campaign_goal)}</div>',
                unsafe_allow_html=True)

    # Summary metrics row
    top = min(influencers, key=lambda x: x["roi_rank"])
    avg_er = sum(i["engagement_rate_pct"] for i in influencers) / len(influencers)
    total_reach = sum(i.get("real_audience", i["followers"]) for i in influencers)
    st.markdown(f"""
        <div class="metric-row">
            <div class="metric-box">
                <div class="metric-box-label">Top Pick</div>
                <div class="metric-box-value">@{top['username']}</div>
            </div>
            <div class="metric-box">
                <div class="metric-box-label">Best ROI Score</div>
                <div class="metric-box-value">{top['composite_roi_score']:.0f}/100</div>
            </div>
            <div class="metric-box">
                <div class="metric-box-label">Avg Engagement Rate</div>
                <div class="metric-box-value">{avg_er:.2f}%</div>
            </div>
            <div class="metric-box">
                <div class="metric-box-label">Total Real Reach</div>
                <div class="metric-box-value">{total_reach:,}</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # AI summary
    if result.gemini_summary:
        st.markdown(f"""
            <div class="ai-box">
                <div class="ai-label">AI Executive Summary</div>
                {result.gemini_summary}
            </div>
        """, unsafe_allow_html=True)

    # Influencer cards
    st.subheader("Ranked Results")
    sorted_infs = sorted(influencers, key=lambda x: x["roi_rank"])
    num_cols = min(len(sorted_infs), 3)
    cols = st.columns(num_cols)

    for i, inf in enumerate(sorted_infs):
        score = inf["composite_roi_score"]
        badge_cls = "score-hi" if score >= 70 else "score-md" if score >= 45 else "score-lo"
        rank_icon = {1: "🥇", 2: "🥈", 3: "🥉"}.get(inf["roi_rank"], f"#{inf['roi_rank']}")
        cpm = f"€{inf['cost_per_1k_reach']:.2f}" if inf.get("cost_per_1k_reach") else "—"
        cpe = f"€{inf['cost_per_engagement']:.3f}" if inf.get("cost_per_engagement") else "—"
        budget = inf.get("allocated_budget_eur", 0) or 0

        with cols[i % num_cols]:
            st.markdown(f"""
                <div class="inf-card">
                    <div class="inf-header">
                        <div>
                            <div class="inf-name">{rank_icon} @{inf['username']}</div>
                            <div class="inf-niche">{inf.get('niche_primary', '—')}</div>
                        </div>
                        <span class="score-badge {badge_cls}">{score:.0f} / 100</span>
                    </div>
                    <div class="inf-grid">
                        <div>
                            <div class="stat-lbl">Followers</div>
                            <div class="stat-val">{inf['followers']:,}</div>
                        </div>
                        <div>
                            <div class="stat-lbl">ER %</div>
                            <div class="stat-val">{inf['engagement_rate_pct']:.2f}%</div>
                        </div>
                        <div>
                            <div class="stat-lbl">Fake %</div>
                            <div class="stat-val">{inf['fake_follower_pct']:.1f}%</div>
                        </div>
                        <div>
                            <div class="stat-lbl">Budget</div>
                            <div class="stat-val">€{budget:,.0f}</div>
                        </div>
                        <div>
                            <div class="stat-lbl">CPM</div>
                            <div class="stat-val">{cpm}</div>
                        </div>
                        <div>
                            <div class="stat-lbl">CPE</div>
                            <div class="stat-val">{cpe}</div>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

    st.divider()

    # Charts
    st.subheader("Analytics")
    col_a, col_b = st.columns(2, gap="large")

    chart_layout = dict(
        height=300, plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(t=30, b=10, l=10, r=10),
        font=dict(family="Inter, sans-serif", size=12),
    )

    with col_a:
        fig = px.bar(
            df.sort_values("roi_rank"),
            x="username", y="composite_roi_score",
            color="composite_roi_score",
            color_continuous_scale=[[0,"#fca5a5"],[0.45,"#fde68a"],[1,"#86efac"]],
            range_color=[0, 100],
            text="composite_roi_score",
            labels={"username": "", "composite_roi_score": "ROI Score"},
            title="ROI Score Ranking",
        )
        fig.update_traces(texttemplate="%{text:.0f}", textposition="outside",
                          marker_line_width=0)
        fig.update_layout(showlegend=False, coloraxis_showscale=False, **chart_layout)
        fig.update_xaxes(showgrid=False, tickfont=dict(size=11))
        fig.update_yaxes(showgrid=True, gridcolor="#f4f4f5", zeroline=False)
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        fig2 = px.scatter(
            df, x="fake_follower_pct", y="engagement_rate_pct",
            size="followers", color="composite_roi_score",
            color_continuous_scale=[[0,"#fca5a5"],[0.45,"#fde68a"],[1,"#86efac"]],
            range_color=[0, 100],
            hover_name="username", text="username",
            labels={"fake_follower_pct": "Fake Followers %",
                    "engagement_rate_pct": "Engagement Rate %"},
            title="Engagement vs Fake Followers",
        )
        fig2.update_traces(textposition="top center", marker_line_width=0)
        fig2.update_layout(coloraxis_showscale=False, **chart_layout)
        fig2.update_xaxes(showgrid=True, gridcolor="#f4f4f5", zeroline=False)
        fig2.update_yaxes(showgrid=True, gridcolor="#f4f4f5", zeroline=False)
        st.plotly_chart(fig2, use_container_width=True)

    # Full data table
    st.subheader("Full Data")
    display_cols = ["roi_rank", "username", "composite_roi_score", "engagement_rate_pct",
                    "fake_follower_pct", "followers", "allocated_budget_eur",
                    "cost_per_engagement", "cost_per_1k_reach", "niche_primary"]
    display_cols = [c for c in display_cols if c in df.columns]
    st.dataframe(
        df[display_cols].rename(columns={
            "roi_rank": "#", "username": "Handle",
            "composite_roi_score": "ROI Score", "engagement_rate_pct": "ER %",
            "fake_follower_pct": "Fake %", "followers": "Followers",
            "allocated_budget_eur": "Budget €", "cost_per_engagement": "CPE €",
            "cost_per_1k_reach": "CPM €", "niche_primary": "Niche",
        }),
        use_container_width=True, hide_index=True,
    )

# ═══════════════════════════════════════════════════════════════
# PAST CAMPAIGNS
# ═══════════════════════════════════════════════════════════════
elif nav == "Past Campaigns":

    st.markdown('<div class="page-title">Past Campaigns</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">All scored campaigns. Select one to re-run scoring.</div>',
                unsafe_allow_html=True)

    try:
        conn = _db()
        df_hist = pd.read_sql("""
            SELECT
                c.campaign_id,
                c.campaign_name        AS "Campaign",
                c.brand_name           AS "Brand",
                c.campaign_goal        AS "Goal",
                c.total_budget_eur     AS "Budget €",
                c.created_at::date     AS "Date",
                COUNT(r.roi_id)        AS "Scored",
                ROUND(MAX(r.composite_roi_score)::numeric, 1) AS "Best ROI",
                MAX(CASE WHEN r.roi_rank = 1 THEN r.username END) AS "Top Pick"
            FROM campaigns c
            LEFT JOIN roi_scores r USING (campaign_id)
            GROUP BY c.campaign_id
            ORDER BY c.created_at DESC
        """, conn)

        if df_hist.empty:
            st.info("No campaigns scored yet. Run one from New Campaign.")
        else:
            st.dataframe(df_hist.drop(columns=["campaign_id"]),
                         use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("Re-score a Campaign")

            cid = st.selectbox(
                "Select campaign to re-run",
                df_hist["campaign_id"].tolist(),
                format_func=lambda x: (
                    df_hist[df_hist["campaign_id"] == x]["Campaign"].values[0]
                ),
            )

            if st.button("Re-score", type="primary"):
                with st.spinner("Scoring..."):
                    result = get_engine().score_campaign(cid)
                    st.session_state.result = result
                st.success("Done — switch to Last Results to view.")

    except Exception as e:
        st.error(f"DB error: {e}")
