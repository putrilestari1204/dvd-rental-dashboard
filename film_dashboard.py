import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
import plotly.express as px
import plotly.graph_objects as go
from sklearn.linear_model import LinearRegression

# ─────────────────────────────────────────
#  PAGE CONFIG
# ─────────────────────────────────────────
st.set_page_config(
    page_title="Film Performance Dashboard",
    page_icon="🎬",
    layout="wide"
)

# ─────────────────────────────────────────
#  DATABASE CONFIG  ← change to your setup
# ─────────────────────────────────────────
DB_USER     = "postgres"
DB_PASSWORD = "YOUR PASSWORD"
DB_HOST     = "localhost"
DB_PORT     = "5432"
DB_NAME     = "YOUR DATABASE NAME"

DATABASE_URL = (
    f"postgresql+psycopg2://{quote_plus(DB_USER)}:{quote_plus(DB_PASSWORD)}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# ─────────────────────────────────────────
#  DB CONNECTION
# ─────────────────────────────────────────
@st.cache_resource
def get_engine():
    return create_engine(DATABASE_URL, connect_args={"client_encoding": "utf8"})

@st.cache_data(ttl=0, show_spinner=False)
def load_query(sql):
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn)

# ─────────────────────────────────────────
#  AUTO-CREATE VIEWS
# ─────────────────────────────────────────
def create_views():
    sql_rdd = """
        CREATE OR REPLACE VIEW rental_dashboard_data AS
        SELECT
            r.rental_id,
            r.rental_date,
            r.return_date,
            r.customer_id,
            c.first_name || ' ' || c.last_name     AS customer_name,
            c.active                                AS customer_active,
            i.store_id                              AS rental_store_id,
            i.film_id,
            f.title                                 AS film_title,
            f.rating                                AS film_rating,
            f.rental_duration                       AS film_rental_duration,
            f.replacement_cost,
            cat.name                                AS category_name,
            p.amount                                AS payment_amount,
            p.payment_date,
            EXTRACT(EPOCH FROM (r.return_date - r.rental_date))/86400 AS actual_rental_days,
            CASE
                WHEN r.return_date IS NULL THEN 'Not Returned'
                WHEN EXTRACT(EPOCH FROM (r.return_date - r.rental_date))/86400
                     > f.rental_duration THEN 'Late'
                ELSE 'On Time'
            END AS return_status,
            ci.city,
            co.country
        FROM rental r
        JOIN customer      c   ON c.customer_id   = r.customer_id
        JOIN inventory     i   ON i.inventory_id  = r.inventory_id
        JOIN film          f   ON f.film_id        = i.film_id
        JOIN film_category fc  ON fc.film_id       = f.film_id
        JOIN category      cat ON cat.category_id  = fc.category_id
        LEFT JOIN payment  p   ON p.rental_id      = r.rental_id
        JOIN address       a   ON a.address_id     = c.address_id
        JOIN city          ci  ON ci.city_id       = a.city_id
        JOIN country       co  ON co.country_id    = ci.country_id
    """
    sql_fp = """
        CREATE OR REPLACE VIEW film_performance AS
        SELECT
            f.film_id,
            f.title,
            f.rating,
            f.rental_duration,
            f.rental_rate,
            f.replacement_cost,
            f.length                                    AS film_length_min,
            cat.name                                    AS category,
            COUNT(r.rental_id)                          AS total_rentals,
            COALESCE(SUM(p.amount), 0)::numeric(10,2)   AS total_revenue,
            COALESCE(AVG(p.amount), 0)::numeric(6,2)    AS avg_revenue_per_rental,
            COUNT(DISTINCT r.customer_id)               AS unique_customers,
            COALESCE(
                AVG(EXTRACT(EPOCH FROM (r.return_date - r.rental_date))/86400), 0
            )::numeric(5,2) AS avg_rental_days,
            CASE
                WHEN COUNT(r.rental_id) = 0  THEN 'Never Rented'
                WHEN COUNT(r.rental_id) < 10 THEN 'Low Demand'
                WHEN COUNT(r.rental_id) < 20 THEN 'Average'
                WHEN COUNT(r.rental_id) < 28 THEN 'Popular'
                ELSE 'Best Seller'
            END AS demand_tier
        FROM film f
        LEFT JOIN film_category  fc  ON fc.film_id      = f.film_id
        LEFT JOIN category       cat ON cat.category_id = fc.category_id
        LEFT JOIN inventory      i   ON i.film_id       = f.film_id
        LEFT JOIN rental         r   ON r.inventory_id  = i.inventory_id
        LEFT JOIN payment        p   ON p.rental_id     = r.rental_id
        GROUP BY f.film_id, f.title, f.rating, f.rental_duration,
                 f.rental_rate, f.replacement_cost, f.length, cat.name
    """
    with get_engine().begin() as conn:
        conn.execute(text("DROP VIEW IF EXISTS film_performance CASCADE"))
        conn.execute(text("DROP VIEW IF EXISTS rental_dashboard_data CASCADE"))
        conn.execute(text(sql_rdd))
        conn.execute(text(sql_fp))

try:
    create_views()
except Exception as e:
    st.error(f"Failed to initialize views: {e}")
    st.stop()


# ─────────────────────────────────────────
#  LOAD BASE DATA ONCE
# ─────────────────────────────────────────
@st.cache_data(ttl=0, show_spinner=False)
def load_base_data():
    df_film = load_query("""
        SELECT film_id, title, rating, category, rental_duration, rental_rate,
               replacement_cost, total_rentals, total_revenue, avg_rental_days,
               avg_revenue_per_rental, unique_customers, demand_tier
        FROM film_performance
    """)
    df_rental = load_query("""
        SELECT rental_id, rental_date, return_date, customer_id, customer_name,
               rental_store_id, film_id, film_title, film_rating, category_name,
               payment_amount, payment_date, actual_rental_days, return_status,
               city, country
        FROM rental_dashboard_data
    """)
    # Films in inventory per store — to detect store-specific dead stock
    df_inventory = load_query("""
        SELECT DISTINCT i.film_id, i.store_id,
               f.title, f.rating, f.replacement_cost,
               cat.name AS category
        FROM inventory i
        JOIN film f ON f.film_id = i.film_id
        JOIN film_category fc ON fc.film_id = f.film_id
        JOIN category cat ON cat.category_id = fc.category_id
    """)
    df_rental["rental_date"]  = pd.to_datetime(df_rental["rental_date"])
    df_rental["payment_date"] = pd.to_datetime(df_rental["payment_date"])
    return df_film, df_rental, df_inventory

df_film_base, df_rental_base, df_inventory_base = load_base_data()

@st.cache_data
def run_linear_regression(df_film):
    df = df_film.copy()

    # Pilih fitur (simple tapi cukup kuat untuk presentasi)
    features = df[[
        "rental_rate",
        "replacement_cost",
        "rental_duration",
        "avg_rental_days"
    ]].fillna(0)

    target = df["total_rentals"]

    # Train model
    model = LinearRegression()
    model.fit(features, target)

    # Predict
    df["predicted_rentals"] = model.predict(features)

    # Hitung performance
    df["performance"] = df["total_rentals"] - df["predicted_rentals"]

    # Label
    def label_perf(x):
        if x > 5:
            return "Overperform"
        elif x < -5:
            return "Underperform"
        else:
            return "Normal"

    df["performance_label"] = df["performance"].apply(label_perf)

    return df, model


@st.cache_data
def run_segmentation(df_film):
    """
    Rule-based film segmentation using median rentals and median revenue as thresholds.
    4 quadrants: Star / Popular but Underpriced / Premium Niche / Underperformer
    """
    df = df_film.copy()
    median_rentals = df["total_rentals"].median()
    median_revenue = df["total_revenue"].median()

    def label(row):
        high_r = row["total_rentals"] >= median_rentals
        high_v = row["total_revenue"] >= median_revenue
        if high_r and high_v:
            return "Star"
        elif high_r and not high_v:
            return "Popular but Underpriced"
        elif not high_r and high_v:
            return "Premium Niche"
        else:
            return "Underperformer"

    df["segment"] = df.apply(label, axis=1)
    df["_median_rentals"] = median_rentals
    df["_median_revenue"] = median_revenue
    return df


# ─────────────────────────────────────────
#  SIDEBAR — clean & compact
# ─────────────────────────────────────────
with st.sidebar:
    st.markdown("### Film Dashboard")
    st.caption("DVD Rental · Film Performance")
    st.divider()

    all_genres  = sorted(df_film_base["category"].dropna().unique().tolist())
    all_ratings = sorted(df_film_base["rating"].dropna().unique().tolist())
    all_stores  = sorted(df_rental_base["rental_store_id"].dropna().unique().tolist())

    # ── Reset button — clears all widget keys before rerun
    if st.button("Reset Filters", use_container_width=True):
        for key in ["filter_genre_all", "filter_genre_select", "filter_rating", "filter_store"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    st.markdown("**Filters**")

    # Genre: toggle all / custom
    select_all_genre = st.checkbox("All Genres", value=True, key="filter_genre_all")
    if not select_all_genre:
        selected_genre = st.multiselect(
            "Select genres",
            options=all_genres,
            default=all_genres,
            label_visibility="collapsed",
            key="filter_genre_select"
        )
    else:
        selected_genre = all_genres

    st.divider()

    # Rating
    rating_opt = ["All Ratings"] + all_ratings
    sel_rating_raw = st.selectbox("Rating", rating_opt, key="filter_rating")

    # Store
    store_opt = ["All Stores"] + [f"Store {s}" for s in all_stores]
    selected_store = st.selectbox("Store", store_opt, key="filter_store")

    st.divider()
    st.caption("dvdrental · PostgreSQL")



# ─────────────────────────────────────────
#  APPLY FILTERS
# ─────────────────────────────────────────
active_genres  = selected_genre if selected_genre else all_genres
active_ratings = all_ratings if sel_rating_raw == "All Ratings" else [sel_rating_raw]
all_tiers      = ["Best Seller","Popular","Low Demand","Never Rented"]
active_tiers   = all_tiers

df_rental = df_rental_base[
    df_rental_base["category_name"].isin(active_genres) &
    df_rental_base["film_rating"].isin(active_ratings)
].copy()

if selected_store != "All Stores":
    sid = int(selected_store.split()[-1])
    df_rental = df_rental[df_rental["rental_store_id"] == sid].copy()

if selected_store != "All Stores":
    films_in_store = df_rental["film_id"].unique()
    df_film = df_film_base[
        df_film_base["film_id"].isin(films_in_store) &
        df_film_base["category"].isin(active_genres) &
        df_film_base["rating"].isin(active_ratings)
    ].copy()
    store_stats = (
        df_rental.groupby("film_id", as_index=False)
        .agg(
            store_rentals=("rental_id", "count"),
            store_revenue=("payment_amount", "sum"),
        )
    )
    df_film = df_film.merge(store_stats, on="film_id", how="left")
    df_film["total_rentals"] = df_film["store_rentals"].fillna(0).astype(int)
    df_film["total_revenue"] = df_film["store_revenue"].fillna(0)
    df_film.drop(columns=["store_rentals","store_revenue"], inplace=True)
else:
    df_film = df_film_base[
        df_film_base["category"].isin(active_genres) &
        df_film_base["rating"].isin(active_ratings) &
        df_film_base["demand_tier"].isin(active_tiers)
    ].copy()

# Active filter summary — only show if something is filtered
filters_active = (
    len(active_genres) < len(all_genres) or
    sel_rating_raw != "All Ratings" or
    selected_store != "All Stores"
)
if filters_active:
    st.sidebar.info(
        f"Showing {len(df_film)} of {len(df_film_base)} films · "
        f"{len(df_rental):,} transactions"
    )


# ─────────────────────────────────────────
#  COMPUTED METRICS  (recalculate on filter)
# ─────────────────────────────────────────

df_film, lr_model = run_linear_regression(df_film)
df_film_km = run_segmentation(df_film)


if df_film.empty or df_rental.empty:
    st.warning("No data for the selected filters. Please adjust the filters in the sidebar.")
    st.stop()

df_paid        = df_rental[df_rental["payment_amount"].notna()]
total_revenue  = df_paid["payment_amount"].sum()
total_rentals  = len(df_rental)
n_films        = len(df_film)
n_best_sellers = len(df_film[df_film["demand_tier"] == "Best Seller"])
n_dead         = len(df_film[df_film["demand_tier"] == "Never Rented"])
dead_cost      = df_film[df_film["demand_tier"]=="Never Rented"]["replacement_cost"].sum()
n_late         = len(df_rental[df_rental["return_status"] == "Late"])
late_pct       = n_late / total_rentals * 100 if total_rentals > 0 else 0
n_customers    = df_rental["customer_id"].nunique()


# ─────────────────────────────────────────
#  REUSABLE CHART STYLE
# ─────────────────────────────────────────
CHART_MARGIN = dict(t=10, b=10, l=10, r=10)

def bar_h(df, x, y, color=None, text=None, title=""):
    """Clean horizontal bar chart."""
    fig = px.bar(df, x=x, y=y, orientation="h", color=color,
                 text=text, title=title)
    fig.update_traces(textposition="outside")
    fig.update_layout(showlegend=bool(color), margin=CHART_MARGIN,
                      yaxis=dict(autorange="reversed"), xaxis_title="", yaxis_title="")
    return fig

def bar_v(df, x, y, color=None, text=None):
    """Clean vertical bar chart."""
    fig = px.bar(df, x=x, y=y, color=color, text=text)
    fig.update_traces(textposition="outside", showlegend=False)
    fig.update_layout(margin=CHART_MARGIN, xaxis_title="", yaxis_title="")
    fig.update_xaxes(tickangle=30)
    return fig


# ═══════════════════════════════════════════════════
#  PAGE HEADER
# ═══════════════════════════════════════════════════
st.title("Film Performance Dashboard")
st.caption("DVD Rental business analysis — film, genre, revenue, and customer behavior.")

if filters_active:
    active_labels = []
    if len(active_genres) < len(all_genres):
        active_labels.append(f"{len(active_genres)} genres")
    if sel_rating_raw != "All Ratings":
        active_labels.append(f"Rating: {sel_rating_raw}")
    if selected_store != "All Stores":
        active_labels.append(selected_store)
    st.caption(f"Active filters: {' · '.join(active_labels)}")

st.divider()


# ═══════════════════════════════════════════════════
#  TABS
# ═══════════════════════════════════════════════════
tab1, tab2, tab3, tab4 = st.tabs([
    "Overview",
    "Film Performance",
    "Film & Customer",
    "Film & Revenue",

])

 # ───────────────────────────────────────────────────
#  TAB 1 — SUMMARY
# ───────────────────────────────────────────────────
with tab1:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Revenue",     f"${total_revenue:,.2f}")
    c2.metric("Total Rentals",     f"{total_rentals:,}")
    c3.metric("Active Customers",  f"{n_customers:,}")
    c4.metric("Films in Catalog",  f"{n_films:,}")

    # ── KPI row 2
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Dead Stock",        f"{n_dead:,}",
              delta=f"${dead_cost:,.2f} cost, $0 return",
              delta_color="inverse")
    c6.metric("Late Returns",      f"{n_late:,}",
              delta=f"{late_pct:.1f}% of all rentals",
              delta_color="inverse")
    c7.metric("Recoverable Revenue", f"${n_late * 3:,.0f}")


    st.divider()

    # ── Monthly Trend + Genre Ranking
    col_l, col_r = st.columns([3, 2])

    with col_l:
        st.subheader("Monthly Rental Trend")

        monthly = (
            df_rental
            .assign(month=df_rental["rental_date"].dt.to_period("M").astype(str))
            .groupby("month", as_index=False)
            .agg(rentals=("rental_id","count"))
            .sort_values("month")
        )

        # Build complete month range May 2005 – Feb 2006 (fill gaps with 0)
        full_range = pd.period_range("2005-05", "2006-02", freq="M")
        month_map  = dict(zip(monthly["month"], monthly["rentals"]))

        import calendar as _cal2
        def fmt_month(p):
            return f"{_cal2.month_abbr[p.month]}\n{p.year}"

        all_months = [str(p) for p in full_range]
        all_labels = [fmt_month(p) for p in full_range]
        all_vals   = [month_map.get(m, 0) for m in all_months]
        has_data   = [month_map.get(m, 0) > 0 for m in all_months]

        # Two traces: blue for real data months, grey dashed for zero months
        fig_trend = go.Figure()

        # Grey dotted line for ALL months (background — shows the full timeline)
        fig_trend.add_trace(go.Scatter(
            x=all_labels,
            y=all_vals,
            mode="lines",
            line=dict(color="#d1d5db", width=1.5, dash="dot"),
            showlegend=True,
            name="No activity",
            hovertemplate="<b>%{x}</b><br>No transactions<extra></extra>"
        ))

        # Blue solid line — only months with actual data
        real_labels = [l for l, h in zip(all_labels, has_data) if h]
        real_vals   = [v for v, h in zip(all_vals,   has_data) if h]
        fig_trend.add_trace(go.Scatter(
            x=real_labels,
            y=real_vals,
            mode="lines+markers+text",
            text=real_vals,
            textposition="top center",
            textfont=dict(size=10),
            line=dict(color="#2563eb", width=2.5),
            marker=dict(size=9, color="#2563eb"),
            showlegend=True,
            name="Active rentals",
            hovertemplate="<b>%{x}</b><br>Rentals: %{y:,}<extra></extra>"
        ))

        fig_trend.update_layout(
            margin=dict(t=10, b=20, l=10, r=10),
            xaxis=dict(
                type="category",
                tickangle=0,          # flat — "May\n2005" already has the year below
                title=None,           # no axis title needed — month+year on tick itself
                tickfont=dict(size=10),
            ),
            yaxis=dict(title="Rentals"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_trend, use_container_width=True)


    with col_r:
        st.subheader("Return Status")

        ret = (
            df_rental.groupby("return_status", as_index=False)
            .agg(count=("rental_id","count"))
            .assign(pct=lambda x: (x["count"] / x["count"].sum() * 100).round(1))
        )

        # Pie chart — correct here: 3 categories, one clear majority (Late > 50%)
        # Pie shows "Late is the majority" far more powerfully than a bar
        ret_colors = {"On Time":"#22c55e","Late":"#ef4444","Not Returned":"#f59e0b"}
        # Sort so order is consistent: On Time, Late, Not Returned
        ret_sorted = ret.set_index("return_status").reindex(
            ["On Time","Late","Not Returned"]
        ).dropna().reset_index()

        late_n_val = int(ret_sorted[ret_sorted["return_status"]=="Late"]["count"].values[0]) if "Late" in ret_sorted["return_status"].values else 0

        fig_ret = go.Figure(data=[go.Pie(
            labels=ret_sorted["return_status"].tolist(),
            values=ret_sorted["count"].tolist(),
            hole=0,
            marker_colors=["#22c55e","#ef4444","#f59e0b"],
            textinfo="percent",
            textposition="inside",
            insidetextorientation="horizontal",
            textfont=dict(size=15, color="white"),
            hovertemplate="<b>%{label}</b><br>Count: %{value:,}<br>%{percent}<extra></extra>",
            showlegend=True,
        )])
        fig_ret.update_layout(
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom", y=-0.12,
                xanchor="center", x=0.5,
                font=dict(size=12)
            ),
            margin=dict(t=10, b=50, l=10, r=10),
        )
        st.plotly_chart(fig_ret, use_container_width=True)



    st.divider()

    # ── Return Status + Catalog Health
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Genre Ranking")

        genre_rank = (
            df_film.groupby("category", as_index=False)
            .agg(rentals=("total_rentals","sum"))
            .sort_values("rentals", ascending=True)
        )
        fig_genre = px.bar(
            genre_rank, x="rentals", y="category", orientation="h",
            text="rentals",
            color_discrete_sequence=["#2563eb"],
            labels={"rentals":"Rentals","category":""}
        )
        fig_genre.update_traces(textposition="outside", textfont_size=10)
        fig_genre.update_layout(showlegend=False, margin=CHART_MARGIN)
        st.plotly_chart(fig_genre, use_container_width=True)


    with col_b:
        st.subheader("Film Catalog Overview")

        # 4 tiers only — Average merged out, clean labels above chart
        tier_counts = df_film.groupby("demand_tier")["film_id"].count().to_dict()
        tier_4      = ["Best Seller","Popular","Low Demand","Never Rented"]
        tier_colors_map = {
            "Best Seller":  "#22c55e",
            "Popular":      "#60a5fa",
            "Low Demand":   "#f59e0b",
            "Never Rented": "#ef4444",
        }
        tier_desc = {
            "Best Seller":  "28+ rentals",
            "Popular":      "20–27 rentals",
            "Low Demand":   "1–9 rentals",
            "Never Rented": "0 rentals",
        }

        st.divider()

        # Bar chart — only 4 tiers
        tier_df = pd.DataFrame({
            "tier":  [t for t in tier_4 if t in tier_counts],
            "films": [tier_counts[t] for t in tier_4 if t in tier_counts],
        })
        fig_tier = px.bar(
            tier_df, x="tier", y="films",
            color="tier",
            color_discrete_map=tier_colors_map,
            text="films",
            labels={"films":"Films","tier":""}
        )
        fig_tier.update_traces(textposition="outside", showlegend=False)
        fig_tier.update_layout(margin=CHART_MARGIN, xaxis=dict(tickangle=0))
        st.plotly_chart(fig_tier, use_container_width=True)

        # Clickable film lists — 4 tiers, 2 columns
        st.markdown("**See films in each tier:**")
        tier_film_data = {
            t: df_film[df_film["demand_tier"] == t][
                ["title","category","rating","total_rentals","total_revenue"]
            ].sort_values("total_rentals", ascending=False)
            for t in tier_4
        }
        tc1, tc2 = st.columns(2)
        with tc1:
            with st.expander(f"Best Seller — {len(tier_film_data['Best Seller'])} films"):
                st.dataframe(
                    tier_film_data["Best Seller"].rename(columns={
                        "title":"Film","category":"Genre","rating":"Rating",
                        "total_rentals":"Rentals","total_revenue":"Revenue ($)"}),
                    use_container_width=True, hide_index=True, height=280,
                    column_config={"Revenue ($)":st.column_config.NumberColumn(format="$%.2f")})
            with st.expander(f"Low Demand — {len(tier_film_data['Low Demand'])} films"):
                st.dataframe(
                    tier_film_data["Low Demand"].rename(columns={
                        "title":"Film","category":"Genre","rating":"Rating",
                        "total_rentals":"Rentals","total_revenue":"Revenue ($)"}),
                    use_container_width=True, hide_index=True, height=280,
                    column_config={"Revenue ($)":st.column_config.NumberColumn(format="$%.2f")})
        with tc2:
            with st.expander(f"Popular — {len(tier_film_data['Popular'])} films"):
                st.dataframe(
                    tier_film_data["Popular"].rename(columns={
                        "title":"Film","category":"Genre","rating":"Rating",
                        "total_rentals":"Rentals","total_revenue":"Revenue ($)"}),
                    use_container_width=True, hide_index=True, height=280,
                    column_config={"Revenue ($)":st.column_config.NumberColumn(format="$%.2f")})
            with st.expander(f"Never Rented — {len(tier_film_data['Never Rented'])} films"):
                st.dataframe(
                    tier_film_data["Never Rented"].rename(columns={
                        "title":"Film","category":"Genre","rating":"Rating",
                        "total_rentals":"Rentals","total_revenue":"Revenue ($)"}),
                    use_container_width=True, hide_index=True, height=280,
                    column_config={"Revenue ($)":st.column_config.NumberColumn(format="$%.2f")})


# ───────────────────────────────────────────────────
#  TAB 2 — FILM PERFORMANCE
# ───────────────────────────────────────────────────
with tab2:
    st.subheader("Film Performance")

    col_l, col_r = st.columns([1, 1])

    with col_l:
        st.subheader("Top Most Rented Films")

        top10 = df_film.sort_values("total_rentals", ascending=False).head(10)
        fig_t10 = px.bar(
            top10, x="total_rentals", y="title", orientation="h",
            color="category", text="total_rentals",
            labels={"total_rentals":"Rentals","title":""}
        )
        fig_t10.update_traces(textposition="outside")
        fig_t10.update_layout(
            yaxis=dict(autorange="reversed"),
            legend_title="Genre",
            margin=CHART_MARGIN
        )
        st.plotly_chart(fig_t10, use_container_width=True)
    
    with col_r:
        st.subheader("Genre: Rentals vs Revenue")
 
        genre_perf = (
            df_film.groupby("category", as_index=False)
            .agg(rentals=("total_rentals","sum"),
                 revenue=("total_revenue","sum"),
                 films=("film_id","count"))
        )
        avg_rentals = genre_perf["rentals"].mean()
        avg_revenue = genre_perf["revenue"].mean()
 
        fig_sc = px.scatter(
            genre_perf, x="rentals", y="revenue",
            size="films", color="category", text="category",
            size_max=35,
            labels={"rentals":"Rentals","revenue":"Revenue ($)"}
        )
        fig_sc.update_traces(
            textposition="top center", textfont_size=9, showlegend=False
        )
 
        # Quadrant reference lines at avg rentals & avg revenue
        fig_sc.add_vline(
            x=avg_rentals, line_dash="dash", line_color="#aaaaaa", line_width=1,
            annotation_text="Avg rentals", annotation_position="top right",
            annotation_font_size=9, annotation_font_color="#aaaaaa"
        )
        fig_sc.add_hline(
            y=avg_revenue, line_dash="dash", line_color="#aaaaaa", line_width=1,
            annotation_text="Avg revenue", annotation_position="top right",
            annotation_font_size=9, annotation_font_color="#aaaaaa"
        )
 
        # Quadrant labels
        x_min = genre_perf["rentals"].min() * 0.9
        x_max = genre_perf["rentals"].max() * 1.05
        y_min = genre_perf["revenue"].min() * 0.88
        y_max = genre_perf["revenue"].max() * 1.06
 
        for label, x, y, color in [
            ("Stars",         x_max, y_max, "#22c55e"),
            ("Premium",       x_min, y_max, "#60a5fa"),
            ("Question Mark", x_max, y_min, "#f59e0b"),
            ("Low Priority",  x_min, y_min, "#ef4444"),
        ]:
            fig_sc.add_annotation(
                x=x, y=y, text=label, showarrow=False,
                font_size=8, font_color=color, opacity=0.55,
                align="center"
            )
 
        fig_sc.update_layout(margin=CHART_MARGIN)
        st.plotly_chart(fig_sc, use_container_width=True)
        st.caption(
            "Dashed lines = average rentals & average revenue. "
            "Stars quadrant (top-right) = ideal. Low Priority (bottom-left) = reduce investment."
        )
 
    st.divider()
 
    # ── Dead Stock only (avg duration removed — all genres 4.5–5.3d, no actionable gap)
    st.subheader("Dead Stock — Films Never Rented")
    st.caption(
        "These films exist in inventory, cost money to acquire, "
        "but have generated zero revenue. They should be removed and replaced."
    )
 
    dead = df_film[df_film["demand_tier"] == "Never Rented"][[
        "title","category","rating","replacement_cost"
    ]].sort_values("replacement_cost", ascending=False)
 
    if dead.empty:
        st.success("No dead stock films in the current filter selection.")
    else:
        c1, c2 = st.columns(2)
        n_never_total = len(df_film_base[df_film_base["demand_tier"] == "Never Rented"])
        c1.metric("Never Rented Films", f"{len(dead)}",
                  help="Films with total_rentals = 0. Confirmed by COUNT(rental_id) = 0 across the full data period.")
        c2.metric("Total Acquisition Cost",  f"${dead['replacement_cost'].sum():,.2f}",
                  delta="$0 revenue generated", delta_color="inverse",
                  help="Total replacement_cost of all never-rented films. This is the money spent purchasing these films — none of it was recovered through rentals.")
        
 
        st.dataframe(
            dead.rename(columns={
                "title":"Film Title",
                "category":"Genre",
                "rating":"Rating",
                "replacement_cost":"Replacement Cost ($)"
            }),
            use_container_width=True,
            hide_index=True,
            height=260,
            column_config={
                "Replacement Cost ($)": st.column_config.NumberColumn(format="$%.2f")
            }
        )
 
    st.divider()
 
    # ── Dynamic insights
    if len(genre_perf) > 0:
        best_g  = genre_perf.sort_values("rentals", ascending=False).iloc[0]
        worst_g = genre_perf.sort_values("rentals").iloc[0]
 
    with st.expander("Browse Full Film Catalog"):
        s1, s2 = st.columns([3,1])
        with s1: search = st.text_input("Search film title", "")
        with s2: sort_c = st.selectbox("Sort by", ["total_rentals","total_revenue"])
 
        disp = df_film.copy()
        if search:
            disp = disp[disp["title"].str.contains(search, case=False)]
        disp = disp.sort_values(sort_c, ascending=False)
 
        st.dataframe(
            disp[["title","category","rating","total_rentals","total_revenue","demand_tier","replacement_cost"]]
            .rename(columns={
                "title":"Film","category":"Genre","rating":"Rating",
                "total_rentals":"Rentals","total_revenue":"Revenue ($)",
                "demand_tier":"Tier","replacement_cost":"Cost ($)"
            }),
            use_container_width=True, hide_index=True, height=320,
            column_config={
                "Revenue ($)": st.column_config.NumberColumn(format="$%.2f"),
                "Cost ($)":    st.column_config.NumberColumn(format="$%.2f")
            }
        )
        st.caption(f"{len(disp):,} films shown")

    # ─── Linear Regression — Film Performance vs Expectation ───────────
    st.divider()

    st.subheader("ML Performance Analysis")
    st.subheader("Film Performance vs Expectation")

    col_lr1, col_lr2 = st.columns([2, 1])
    with col_lr1:
        max_val = max(df_film["predicted_rentals"].max(), df_film["total_rentals"].max()) * 1.05
        fig_lr = px.scatter(
            df_film,
            x="predicted_rentals", y="total_rentals",
            color="performance_label",
            color_discrete_map={
                "Overperform":  "#22c55e",
                "Normal":       "#60a5fa",
                "Underperform": "#ef4444"
            },
            hover_data=["title", "category", "rental_rate", "replacement_cost"],
            labels={
                "predicted_rentals": "Expected Rentals (Model)",
                "total_rentals":     "Actual Rentals",
                "performance_label": "Performance"
            }
        )
        # Diagonal = perfect prediction reference
        fig_lr.add_shape(
            type="line", x0=0, y0=0, x1=max_val, y1=max_val,
            line=dict(dash="dash", color="#aaaaaa", width=1.5)
        )
        fig_lr.add_annotation(
            x=max_val * 0.75, y=max_val * 0.75,
            text="Perfect prediction line",
            showarrow=False, font_size=9, font_color="#aaaaaa"
        )
        fig_lr.update_layout(margin=CHART_MARGIN)
        st.plotly_chart(fig_lr, use_container_width=True)

    with col_lr2:
        n_over  = len(df_film[df_film["performance_label"] == "Overperform"])
        n_under = len(df_film[df_film["performance_label"] == "Underperform"])
        n_norm  = len(df_film[df_film["performance_label"] == "Normal"])
        st.metric("Overperform",  f"{n_over} films")
        st.metric("Normal",       f"{n_norm} films")
        st.metric("Underperform", f"{n_under} films")

    if n_under > 0:
        with st.expander(f"🔴 {n_under} Underperforming Films"):
            under_df = df_film[df_film["performance_label"]=="Underperform"][[
                "title","category","rating","rental_rate","total_rentals","predicted_rentals","total_revenue"
            ]].sort_values("total_rentals").rename(columns={
                "title":"Film","category":"Genre","rating":"Rating",
                "rental_rate":"Rate ($)","total_rentals":"Actual Rentals",
                "predicted_rentals":"Expected Rentals","total_revenue":"Revenue ($)"
            })
            under_df["Expected Rentals"] = under_df["Expected Rentals"].round(1)
            st.dataframe(under_df, use_container_width=True, hide_index=True, height=280,
                         column_config={"Revenue ($)": st.column_config.NumberColumn(format="$%.2f"),
                                        "Rate ($)":    st.column_config.NumberColumn(format="$%.2f")})
# ───────────────────────────────────────────────────
with tab3:
    st.subheader("Film & Customer")

    col_l, col_r = st.columns([1, 1])

    with col_l:
        st.subheader("Top Genre per Country")

        geo = (
            df_rental.groupby(["country","category_name"], as_index=False)
            .agg(rentals=("rental_id","count"))
        )
        top_c = df_rental.groupby("country")["rental_id"].count().nlargest(10).index
        top_geo = (
            geo[geo["country"].isin(top_c)]
            .sort_values("rentals", ascending=False)
            .groupby("country").head(1)
            .sort_values("rentals", ascending=True)
        )
        fig_geo = px.bar(
            top_geo, x="rentals", y="country", orientation="h",
            color="category_name", text="category_name",
            labels={"rentals":"Rentals","country":""}
        )
        fig_geo.update_traces(textposition="inside", textfont_size=9)
        fig_geo.update_layout(legend_title="Genre", margin=CHART_MARGIN)
        st.plotly_chart(fig_geo, use_container_width=True)

    with col_r:
        st.subheader("Return Status by Genre")

        ret_g = (
            df_rental.groupby(["category_name","return_status"], as_index=False)
            .agg(count=("rental_id","count"))
        )
        pivot = ret_g.pivot_table(
            index="category_name", columns="return_status",
            values="count", fill_value=0
        ).reset_index()

        cols_p = [c for c in ["On Time","Late","Not Returned"] if c in pivot.columns]
        fig_rg = px.bar(
            pivot, x="category_name", y=cols_p, barmode="stack",
            color_discrete_map={"On Time":"#22c55e","Late":"#ef4444","Not Returned":"#f59e0b"},
            labels={"value":"Rentals","category_name":"","variable":"Status"}
        )
        fig_rg.update_xaxes(tickangle=35)
        fig_rg.update_layout(margin=CHART_MARGIN)
        st.plotly_chart(fig_rg, use_container_width=True)

    st.divider()

    # ── Customer Reach
    st.subheader("Customer Reach by Genre")

    reach = (
        df_rental.groupby("category_name", as_index=False)
        .agg(unique_customers=("customer_id","nunique"))
        .sort_values("unique_customers", ascending=True)
        .assign(reach_pct=lambda x: (x["unique_customers"] / n_customers * 100).round(1))
    )
    fig_reach = px.bar(
        reach, x="unique_customers", y="category_name", orientation="h",
        color="reach_pct",
        color_continuous_scale=["#dbeafe","#1d4ed8"],
        text=reach["unique_customers"].astype(str) + " (" + reach["reach_pct"].astype(str) + "%)",
        labels={"unique_customers":"Unique Customers","category_name":"",
                "reach_pct":"Customer Reach (%)"}
    )
    fig_reach.update_traces(textposition="outside")
    fig_reach.update_layout(
        coloraxis_colorbar=dict(title="Reach %"),
        margin=CHART_MARGIN
    )
    st.plotly_chart(fig_reach, use_container_width=True)

# ───────────────────────────────────────────────────
#  TAB 4— FILM & REVENUE
# ───────────────────────────────────────────────────
with tab4:
    st.title("Film & Revenue Analysis")
    st.write("Analysis of revenue performance, efficiency, and film contribution to business revenue.")
    st.divider()

    # ── KPIs (FIXED + CLEAN)
    df_paid_r = df_rental[df_rental["payment_amount"].notna()]

    total_rev      = df_paid_r["payment_amount"].sum()
    avg_rev_film   = df_film["total_revenue"].sum() / len(df_film) if len(df_film) > 0 else 0
    avg_rev_rental = total_rev / len(df_paid_r) if len(df_paid_r) > 0 else 0

    daily_revenue = (
        df_paid_r
        .groupby(df_paid_r["payment_date"].dt.date)
        .agg(daily_revenue=("payment_amount", "sum"))
        .reset_index()
        .rename(columns={"payment_date": "revenue_date"})
        .sort_values("revenue_date")
    )

    avg_daily_revenue = daily_revenue["daily_revenue"].mean() if len(daily_revenue) > 0 else 0

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Total Revenue", f"${total_rev:,.2f}")
    c2.metric("Avg Revenue per Film", f"${avg_rev_film:,.2f}")
    c3.metric("Avg Revenue per Rental", f"${avg_rev_rental:,.2f}")
    c4.metric("Avg Daily Revenue", f"${avg_daily_revenue:,.2f}")

    st.divider()

    # ── ROW 1
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.subheader("Revenue by Genre")

        genre_rev = (
            df_film.groupby("category", as_index=False)
            .agg(
                revenue=("total_revenue", "sum"),
                rentals=("total_rentals", "sum"),
                film_count=("film_id", "count")
            )
            .assign(
                rev_per_rental=lambda x: (x["revenue"] / x["rentals"].replace(0, 1)).round(2)
            )
            .sort_values("revenue", ascending=False)
        )

        fig = px.bar(
            genre_rev,
            x="category",
            y="revenue",
            color="category",
            text=genre_rev["revenue"].apply(lambda x: f"${x:,.0f}"),
            labels={"revenue": "Revenue", "category": "Genre"}
        )
        fig.update_traces(textposition="outside", showlegend=False)
        fig.update_layout(margin=CHART_MARGIN)
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            genre_rev[["category", "rev_per_rental", "film_count"]]
            .rename(columns={
                "category": "Genre",
                "rev_per_rental": "Revenue per Rental",
                "film_count": "Films"
            }),
            use_container_width=True,
            hide_index=True
        )

    with col_right:
        st.subheader("Top 10 Films by Revenue")

        top_rev_films = (
            df_film[df_film["total_revenue"] > 0]
            .sort_values("total_revenue", ascending=False)
            .head(10)
        )

        fig2 = px.bar(
            top_rev_films,
            x="total_revenue",
            y="title",
            orientation="h",
            color="category",
            text=top_rev_films["total_revenue"].apply(lambda x: f"${x:,.0f}"),
            labels={"total_revenue": "Revenue", "title": "Film"}
        )
        fig2.update_traces(textposition="outside")
        fig2.update_layout(yaxis=dict(autorange="reversed"), margin=CHART_MARGIN)
        st.plotly_chart(fig2, use_container_width=True)

        st.dataframe(
            top_rev_films[["title", "category", "rating", "total_revenue", "total_rentals"]]
            .rename(columns={
                "title": "Film",
                "category": "Genre",
                "rating": "Rating",
                "total_revenue": "Revenue",
                "total_rentals": "Rentals"
            }),
            use_container_width=True,
            hide_index=True
        )

    st.divider()

    # ── ROW 2
    col_a, col_b = st.columns([1, 1])

    with col_a:
        st.subheader("Daily Revenue Trend")

        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(
            x=daily_revenue["revenue_date"],
            y=daily_revenue["daily_revenue"],
            mode="lines+markers",
            name="Revenue"
        ))

        fig3.add_hline(
            y=avg_daily_revenue,
            line_dash="dash"
        )

        fig3.update_layout(margin=CHART_MARGIN)
        st.plotly_chart(fig3, use_container_width=True)

    with col_b:
        st.subheader("Revenue by Rating")

        rating_rev = (
            df_film.groupby("rating", as_index=False)
            .agg(
                films=("film_id", "count"),
                revenue=("total_revenue", "sum")
            )
            .assign(
                avg_rev_per_film=lambda x: x["revenue"] / x["films"]
            )
            .sort_values("revenue", ascending=False)
        )

        fig4 = px.bar(
            rating_rev,
            x="rating",
            y="revenue",
            color="rating",
            text=rating_rev["revenue"].apply(lambda x: f"${x:,.0f}")
        )

        fig4.update_traces(textposition="outside", showlegend=False)
        fig4.update_layout(margin=CHART_MARGIN)
        st.plotly_chart(fig4, use_container_width=True)

        st.dataframe(
            rating_rev.rename(columns={
                "rating": "Rating",
                "films": "Films",
                "revenue": "Revenue",
                "avg_rev_per_film": "Avg Revenue per Film"
            }),
            use_container_width=True,
            hide_index=True
        )

    st.divider()

    # ── INSIGHTS (clean text only)
    top_g = genre_rev.iloc[0]
    bot_g = genre_rev.iloc[-1]

    st.subheader("Insights")

    col1, col2 = st.columns(2)

    with col1:
        st.success(f"Top genre by revenue is {top_g['category']} with ${top_g['revenue']:,.2f}")
        st.info("Revenue efficiency varies significantly across genres and ratings.")

    with col2:
        st.warning(f"Lowest revenue genre is {bot_g['category']} with ${bot_g['revenue']:,.2f}")
        st.info("Focus optimization on low revenue per rental categories.")
