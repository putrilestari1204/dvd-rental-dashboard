🎬 Film Performance Dashboard

An interactive business analytics dashboard built with Streamlit, designed to help DVD rental businesses understand film performance, revenue trends, and customer behavior — without needing to write a single line of SQL.

---

📌 Project Overview

This dashboard connects directly to a PostgreSQL database (DVD Rental schema) and transforms raw rental data into clear, actionable insights across four analytical dimensions: **film performance**, **customer behavior**, **genre analysis**, and **revenue breakdown**.

The goal wasn't just to build charts — it was to think like a business analyst: *what questions does a store manager actually need answered?* This dashboard answers them visually and intuitively.

---

🖥️ Dashboard Preview

Tab 1 — Overview
> KPI summary, monthly rental trend, and genre ranking at a glance.

<img width="1821" height="876" alt="image" src="https://github.com/user-attachments/assets/0f35a33a-6927-4eb7-a747-056ae3843a88" />

<img width="1585" height="693" alt="image" src="https://github.com/user-attachments/assets/1d7434ad-bc57-4d94-90e9-7f48d939c554" />


 Tab 2 — Film Performance
> Demand tiers, linear regression predictions, and film segmentation.

<img width="1821" height="785" alt="image" src="https://github.com/user-attachments/assets/1b048980-86be-481b-b520-0acfd7589a3f" />

<img width="1846" height="861" alt="image" src="https://github.com/user-attachments/assets/472c3c75-6420-4c0d-93eb-8fc16c7b45f6" />


Tab 3 — Film & Customer
> Customer reach by genre, return status analysis, and rental behavior.

<img width="1835" height="864" alt="image" src="https://github.com/user-attachments/assets/7302126d-2351-4eac-9113-d8f99f3226f6" />

Tab 4 — Film & Revenue
> Revenue by genre, top films, daily trend, and rating-based breakdown.

<img width="1807" height="887" alt="image" src="https://github.com/user-attachments/assets/612e581c-a82d-45b9-ac6e-b428f68d8069" />

<img width="1791" height="895" alt="image" src="https://github.com/user-attachments/assets/0c5981f0-371c-4e00-902f-c7c42648de60" />

---

📊 Features

**Tab 1 — Overview**
- 7 KPI Cards: Total Revenue, Total Rentals, Active Customers, Films in Catalog, Dead Stock, Late Returns, Recoverable Revenue
- Monthly Rental Trend — line chart with active vs. inactive month distinction
- Top Genres by Rentals — horizontal bar chart
- Revenue & Rental distribution by genre

**Tab 2 — Film Performance**
- Demand Tier Classification: Best Seller, Popular, Average, Low Demand, Never Rented
- Linear Regression Model — predicts expected rentals per film based on price, duration, and rental behavior
- Overperform / Underperform / Normal labeling per film
- Film Segmentation (Rule-based Quadrant): Star, Popular but Underpriced, Premium Niche, Underperformer
- Dead Stock Detection — films in inventory that were never rented, with replacement cost exposure

**Tab 3 — Film & Customer**
- Return Status Breakdown — On Time, Late, Not Returned
- Late Return Rate by Genre
- Customer Reach by Genre — unique customers who rented each category
- Geography-based rental distribution (City & Country)

**Tab 4 — Film & Revenue**
- Revenue by Genre — bar chart with revenue efficiency table
- Top 10 Films by Revenue
- Daily Revenue Trend with average baseline
- Revenue by Film Rating (G, PG, PG-13, R, NC-17)
- Business Insights: auto-generated top and bottom genre callouts

---

🗃️ Dataset

- **Source:** [DVD Rental Database](https://www.postgresqltutorial.com/postgresql-getting-started/postgresql-sample-database/) — a standard PostgreSQL sample database widely used for SQL learning and analytics
- **Database:** PostgreSQL
- **Schema includes:** film, rental, payment, customer, inventory, category, address, city, country

---

 🛠️ Tech Stack

| Layer | Tools |
|---|---|
| Frontend | Streamlit |
| Visualization | Plotly Express, Plotly Graph Objects |
| Database | PostgreSQL + SQLAlchemy + psycopg2 |
| Machine Learning | scikit-learn (Linear Regression) |
| Data Processing | Pandas |

---

⚙️ Getting Started

Prerequisites
- Python 3.10+
- PostgreSQL with DVD Rental database loaded

1. Clone the Repository
```bash
git clone https://github.com/putrilestari1204/dvd-rental-dashboard.git
cd dvd-rental-dashboard
```

 2. Install Dependencies
```bash
pip install -r requirements.txt
```

3. Set Up Environment Variables
Copy the example env file and fill in your PostgreSQL credentials:
```bash
cp .env.example .env
```

Edit `.env`:
```
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=dvdrental
```

4. Run the Dashboard
```bash
streamlit run film_dashboard.py
```

Open your browser at `http://localhost:8501`

---

💡 Key Business Insights

**Film Demand**
- Best Sellers represent the top-performing titles driving the majority of rental revenue
- Dead Stock films (never rented) represent a real financial risk — replacement cost with zero return on investment
- Late returns are a hidden revenue opportunity: recoverable through late fees

**Revenue Patterns**
- Genre revenue is uneven — a few categories dominate while others underperform despite similar inventory size
- Revenue per rental varies significantly by rating, revealing pricing inefficiencies

**Customer Behavior**
- A small group of high-frequency customers drives a disproportionate share of revenue
- Customer reach by genre reveals which categories attract the widest audience vs. niche loyalists

**ML Prediction**
- Films that significantly overperform their predicted rentals are candidates for inventory expansion
- Underperformers with high replacement cost are candidates for phaseout

---

📁 Project Structure

```
dvd-rental-dashboard/
├── film_dashboard.py     # Main Streamlit app
├── requirements.txt      # Python dependencies
├── .env.example          # Environment variable template
├── .gitignore            # Files excluded from version control
└── README.md             # Project documentation
```

---

👤 Author

**Putri Lestari Wijaya**  
GitHub: [@putrilestari1204](https://github.com/putrilestari1204)
