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
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

logging.basicConfig(level=logging.INFO)

# ── CSS — only our own classes, never Streamlit internals ──────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* Safe: only targets our custom HTML elements */

.roi-header {
    padding: 8px 0 24px 0;
    border-bottom: 1px solid #e4e4e7;
    margin-bottom: 28px;
}
.roi-header-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.roi-logo {
    font-family: 'Inter', sans-serif;
    font-weight: 700;
    font-size: 1.1rem;
    color: #18181b;
    letter-spacing: -0.02em;
}
.roi-logo span {
    background: #18181b;
    color: #fff;
    padding: 2px 8px;
    border-radius: 5px;
    margin-right: 6px;
    font-size: 0.75rem;
    font-weight: 600;
}
.roi-tagline {
    font-size: 0.78rem;
    color: #a1a1aa;
    font-family: 'Inter', sans-serif;
}

.pg-title {
    font-family: 'Inter', sans-serif;
    font-size: 1.35rem;
    font-weight: 700;
    color: #18181b;
    letter-spacing: -0.02em;
    margin-bottom: 4px;
}
.pg-sub {
    font-family: 'Inter', sans-serif;
    font-size: 0.85rem;
    color: #71717a;
    margin-bottom: 24px;
}

.metric-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
    margin-bottom: 24px;
}
.metric-box {
    background: #fff;
    border: 1px solid #e4e4e7;
    border-radius: 10px;
    padding: 16px 18px;
}
.metric-lbl {
    font-family: 'Inter', sans-serif;
    font-size: 0.68rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #a1a1aa;
    margin-bottom: 6px;
}
.metric-val {
    font-family: 'Inter', sans-serif;
    font-size: 1.35rem;
    font-weight: 700;
    color: #18181b;
    letter-spacing: -0.02em;
}

.ai-box {
    background: #18181b;
    color: #d4d4d8;
    border-radius: 10px;
    padding: 18px 22px;
    margin-bottom: 22px;
    line-height: 1.7;
    font-size: 0.88rem;
    font-family: 'Inter', sans-serif;
}
.ai-lbl {
    font-size: 0.6rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #52525b;
    margin-bottom: 8px;
}

.inf-card {
    background: #fff;
    border: 1px solid #e4e4e7;
    border-radius: 10px;
    padding: 18px 20px;
    margin-bottom: 12px;
    font-family: 'Inter', sans-serif;
}
.inf-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 14px;
}
.inf-name {
    font-size: 0.92rem;
    font-weight: 600;
    color: #18181b;
}
.inf-niche {
    font-size: 0.72rem;
    color: #71717a;
    margin-top: 3px;
}
.badge {
    font-family: 'Inter', sans-serif;
    font-size: 0.82rem;
    font-weight: 600;
    padding: 3px 11px;
    border-radius: 999px;
    white-space: nowrap;
}
.badge-hi { background: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0; }
.badge-md { background: #fefce8; color: #ca8a04; border: 1px solid #fde68a; }
.badge-lo { background: #fef2f2; color: #dc2626; border: 1px solid #fecaca; }

.inf-stats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
    padding-top: 12px;
    border-top: 1px solid #f4f4f5;
}
.stat-l {
    font-size: 0.62rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #a1a1aa;
}
.stat-v {
    font-size: 0.82rem;
    font-weight: 600;
    color: #18181b;
    margin-top: 3px;
    font-family: 'Inter', sans-serif;
}

.section-label {
    font-family: 'Inter', sans-serif;
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #a1a1aa;
    margin-bottom: 12px;
    margin-top: 4px;
}
</style>
""", unsafe_allow_html=True)

# ── State ────────────────────────────────────────────────────
if "result" not in st.session_state:
    st.session_state.result = None

# ── Top header ───────────────────────────────────────────────
st.markdown("""
<div class="roi-header">
    <div class="roi-logo"><span>P02</span> Influencer ROI Scorer</div>
</div>
""", unsafe_allow_html=True)

# ── Nav ──────────────────────────────────────────────────────
nav = st.segmented_control(
    "nav",
    ["New Campaign", "Last Results", "Past Campaigns"],
    default="New Campaign",
    label_visibility="collapsed",
)

st.write("")  # spacer

# ── Helpers ──────────────────────────────────────────────────
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

# ═══════════════════════════════════════════════════════════
# NEW CAMPAIGN
# ═══════════════════════════════════════════════════════════
if nav == "New Campaign":

    st.markdown('<div class="pg-title">New Campaign</div>', unsafe_allow_html=True)
    st.markdown('<div class="pg-sub">Compare up to 5 influencers by ROI for your campaign goal.</div>', unsafe_allow_html=True)

    col1, col2 = st.columns([3, 2], gap="large")

    with col1:
        st.markdown('<div class="section-label">Campaign Details</div>', unsafe_allow_html=True)
        campaign_name = st.text_input("Campaign name", placeholder="Summer Body 2026")
        brand_name    = st.text_input("Brand / company", placeholder="The Body Clinic")
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
        st.markdown('<div class="section-label">Influencer Lineup</div>', unsafe_allow_html=True)
        st.caption("Handle on the left · budget on the right")
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

            with st.spinner("Scraping profiles · computing engagement rates · scoring niches · ranking ROI..."):
                result = get_engine().score_campaign(campaign_id)
                st.session_state.result = result

            if result.status == "success":
                st.success(f"✅ Campaign scored — {len(result.influencers)} influencers ranked in {result.duration_ms/1000:.1f}s")
                st.info("👉 Switch to **Last Results** to see the ranked ROI table and charts.")
            else:
                st.error("❌ Scoring failed. Check terminal logs for details.")

# ═══════════════════════════════════════════════════════════
# LAST RESULTS
# ═══════════════════════════════════════════════════════════
elif nav == "Last Results":

    result = st.session_state.result

    if result is None:
        try:
            conn = _db()
            with conn.cursor() as cur:
                cur.execute("SELECT campaign_id FROM campaigns ORDER BY created_at DESC LIMIT 1")
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
        "engagement": "Engagement",
        "awareness": "Awareness",
        "conversion": "Conversion",
        "follower_growth": "Follower Growth",
    }

    st.markdown(f'<div class="pg-title">{getattr(result, "campaign_name", "Results")}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="pg-sub">Goal: {goal_labels.get(result.campaign_goal, result.campaign_goal)}</div>', unsafe_allow_html=True)

    # Metric row
    top = min(influencers, key=lambda x: x["roi_rank"])
    avg_er = sum(i["engagement_rate_pct"] for i in influencers) / len(influencers)
    total_reach = sum(i.get("real_audience", i["followers"]) for i in influencers)
    total_budget = sum(i.get("allocated_budget_eur", 0) or 0 for i in influencers)

    st.markdown(f"""
    <div class="metric-row">
        <div class="metric-box">
            <div class="metric-lbl">Top Pick</div>
            <div class="metric-val">@{top['username']}</div>
        </div>
        <div class="metric-box">
            <div class="metric-lbl">Best ROI Score</div>
            <div class="metric-val">{top['composite_roi_score']:.0f}/100</div>
        </div>
        <div class="metric-box">
            <div class="metric-lbl">Avg Engagement Rate</div>
            <div class="metric-val">{avg_er:.2f}%</div>
        </div>
        <div class="metric-box">
            <div class="metric-lbl">Total Real Reach</div>
            <div class="metric-val">{total_reach:,}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # AI summary
    if result.gemini_summary:
        st.markdown(f"""
        <div class="ai-box">
            <div class="ai-lbl">AI Executive Summary</div>
            {result.gemini_summary}
        </div>
        """, unsafe_allow_html=True)

    # Influencer cards
    st.markdown('<div class="section-label">Ranked Results</div>', unsafe_allow_html=True)
    sorted_infs = sorted(influencers, key=lambda x: x["roi_rank"])
    num_cols = min(len(sorted_infs), 3)
    cols = st.columns(num_cols)

    for i, inf in enumerate(sorted_infs):
        score = inf["composite_roi_score"]
        badge = "badge-hi" if score >= 70 else "badge-md" if score >= 45 else "badge-lo"
        rank  = {1: "#1", 2: "#2", 3: "#3"}.get(inf["roi_rank"], f"#{inf['roi_rank']}")
        cpm   = f"€{inf['cost_per_1k_reach']:.2f}"   if inf.get("cost_per_1k_reach")   else "—"
        cpe   = f"€{inf['cost_per_engagement']:.3f}"  if inf.get("cost_per_engagement")  else "—"
        bgt   = inf.get("allocated_budget_eur", 0) or 0

        with cols[i % num_cols]:
            st.markdown(f"""
            <div class="inf-card">
                <div class="inf-top">
                    <div>
                        <div class="inf-name">{rank} @{inf['username']}</div>
                        <div class="inf-niche">{inf.get('niche_primary','—')}</div>
                    </div>
                    <span class="badge {badge}">{score:.0f}/100</span>
                </div>
                <div class="inf-stats">
                    <div><div class="stat-l">Followers</div><div class="stat-v">{inf['followers']:,}</div></div>
                    <div><div class="stat-l">ER %</div><div class="stat-v">{inf['engagement_rate_pct']:.2f}%</div></div>
                    <div><div class="stat-l">Fake %</div><div class="stat-v">{inf['fake_follower_pct']:.1f}%</div></div>
                    <div><div class="stat-l">Budget</div><div class="stat-v">€{bgt:,.0f}</div></div>
                    <div><div class="stat-l">CPM</div><div class="stat-v">{cpm}</div></div>
                    <div><div class="stat-l">CPE</div><div class="stat-v">{cpe}</div></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    # Charts
    st.markdown('<div class="section-label">Analytics</div>', unsafe_allow_html=True)
    col_a, col_b = st.columns(2, gap="large")

    chart_base = dict(
        height=300,
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        margin=dict(t=36, b=10, l=10, r=10),
        font=dict(family="Inter, sans-serif", size=11, color="#71717a"),
        title_font=dict(family="Inter, sans-serif", size=12, color="#18181b"),
    )

    with col_a:
        fig = px.bar(
            df.sort_values("roi_rank"),
            x="username", y="composite_roi_score",
            color="composite_roi_score",
            color_continuous_scale=[[0,"#fca5a5"],[0.5,"#fde68a"],[1,"#86efac"]],
            range_color=[0,100],
            text="composite_roi_score",
            labels={"username":"","composite_roi_score":"ROI Score"},
            title="ROI Score Ranking",
        )
        fig.update_traces(texttemplate="%{text:.0f}", textposition="outside", marker_line_width=0)
        fig.update_layout(showlegend=False, coloraxis_showscale=False, **chart_base)
        fig.update_xaxes(showgrid=False, tickfont=dict(size=11, color="#18181b"))
        fig.update_yaxes(showgrid=True, gridcolor="#f4f4f5", zeroline=False)
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        fig2 = px.scatter(
            df, x="fake_follower_pct", y="engagement_rate_pct",
            size="followers", color="composite_roi_score",
            color_continuous_scale=[[0,"#fca5a5"],[0.5,"#fde68a"],[1,"#86efac"]],
            range_color=[0,100],
            hover_name="username", text="username",
            labels={"fake_follower_pct":"Fake Followers %","engagement_rate_pct":"Engagement Rate %"},
            title="Engagement vs Fake Followers",
        )
        fig2.update_traces(textposition="top center", marker_line_width=0)
        fig2.update_layout(coloraxis_showscale=False, **chart_base)
        fig2.update_xaxes(showgrid=True, gridcolor="#f4f4f5", zeroline=False)
        fig2.update_yaxes(showgrid=True, gridcolor="#f4f4f5", zeroline=False)
        st.plotly_chart(fig2, use_container_width=True)

    # Data table
    st.markdown('<div class="section-label">Full Data</div>', unsafe_allow_html=True)
    display_cols = ["roi_rank","username","composite_roi_score","engagement_rate_pct",
                    "fake_follower_pct","followers","allocated_budget_eur",
                    "cost_per_engagement","cost_per_1k_reach","niche_primary"]
    display_cols = [c for c in display_cols if c in df.columns]
    st.dataframe(
        df[display_cols].rename(columns={
            "roi_rank":"#","username":"Handle","composite_roi_score":"ROI Score",
            "engagement_rate_pct":"ER %","fake_follower_pct":"Fake %",
            "followers":"Followers","allocated_budget_eur":"Budget €",
            "cost_per_engagement":"CPE €","cost_per_1k_reach":"CPM €",
            "niche_primary":"Niche",
        }),
        use_container_width=True, hide_index=True,
    )

# ═══════════════════════════════════════════════════════════
# PAST CAMPAIGNS
# ═══════════════════════════════════════════════════════════
elif nav == "Past Campaigns":

    st.markdown('<div class="pg-title">Past Campaigns</div>', unsafe_allow_html=True)
    st.markdown('<div class="pg-sub">All scored campaigns. Select one to re-run.</div>', unsafe_allow_html=True)

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
                ROUND(MAX(r.composite_roi_score)::numeric,1) AS "Best ROI",
                MAX(CASE WHEN r.roi_rank=1 THEN r.username END) AS "Top Pick"
            FROM campaigns c
            LEFT JOIN roi_scores r USING (campaign_id)
            GROUP BY c.campaign_id
            ORDER BY c.created_at DESC
        """, conn)

        if df_hist.empty:
            st.info("No campaigns yet. Run one from New Campaign.")
        else:
            st.dataframe(df_hist.drop(columns=["campaign_id"]),
                         use_container_width=True, hide_index=True)
            st.divider()
            st.markdown('<div class="section-label">Re-score a Campaign</div>', unsafe_allow_html=True)
            cid = st.selectbox(
                "Campaign",
                df_hist["campaign_id"].tolist(),
                format_func=lambda x: df_hist[df_hist["campaign_id"]==x]["Campaign"].values[0],
            )
            if st.button("Re-score", type="primary"):
                with st.spinner("Scoring..."):
                    result = get_engine().score_campaign(cid)
                    st.session_state.result = result
                st.success("Done — switch to Last Results to view.")

    except Exception as e:
        st.error(f"DB error: {e}")