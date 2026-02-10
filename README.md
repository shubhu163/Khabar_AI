# Khabar AI

> An agentic AI system that monitors global supply-chain risks by correlating news, stock volatility, and weather data in real time.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-Deploy-FF4B4B.svg)](https://share.streamlit.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## What It Does

Khabar AI is an **autonomous risk-monitoring pipeline** that:

1. **Ingests** real-time data from three sources (news, stock market, weather)
2. **Triages** noise using a fast LLM filter (Llama 3.3 70B via Groq) — eliminating ~90% of irrelevant articles
3. **Analyses** remaining signals with a reasoning LLM (GPT-OSS 120B via Groq) — producing structured risk assessments with severity ratings, impact estimates, and mitigation strategies
4. **Acts** by storing events in a database and visualizing them on an interactive Streamlit dashboard

The monitoring runs **continuously in the background** on a user-set interval (15 min to 6 hours), requiring zero human intervention once configured.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      STREAMLIT DASHBOARD                            │
│                   (Background Monitor Thread)                       │
│          User picks company + interval → auto-runs pipeline         │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      SENSORS (Ingestion Layer)                      │
│                                                                     │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────────┐  │
│  │  News Sensor  │  │  Finance Sensor  │  │   Weather Sensor     │  │
│  │ (Google News) │  │  (Alpha Vantage) │  │   (OpenWeatherMap)   │  │
│  └──────┬───────┘  └────────┬─────────┘  └──────────┬───────────┘  │
└─────────┼──────────────────┼────────────────────────┼──────────────┘
          │                  │                        │
          ▼                  │                        │
┌─────────────────────┐      │                        │
│   TRIAGE AGENT      │      │                        │
│   Llama 3.3 70B     │      │                        │
│   (Groq API)        │      │                        │
│                     │      │                        │
│   YES / NO filter   │      │                        │
│   ~90% noise removed│      │                        │
└────────┬────────────┘      │                        │
         │ (only relevant)   │                        │
         ▼                   ▼                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       ANALYST AGENT                                 │
│                       GPT-OSS 120B (Groq)                           │
│                                                                     │
│   Correlates: News + Stock Volatility + Weather                     │
│   Outputs:    Severity (RED/YELLOW/GREEN)                           │
│               Impact estimate, Reasoning, Mitigation strategies     │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       ACTION LAYER                                  │
│                                                                     │
│  ┌──────────────────────┐  ┌──────────────────────────────────────┐│
│  │   Database           │  │   Interactive Dashboard              ││
│  │   (Supabase/SQLite)  │  │   • Risk Event Cards                 ││
│  │                      │  │   • Knowledge Graph Viz              ││
│  │   Deduplication      │  │   • Metrics & Charts                 ││
│  │   via SHA-256 hash   │  │   • Live Monitoring Controls         ││
│  └──────────────────────┘  └──────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Backend | Python 3.11+, Threading | Multi-threaded for background monitoring |
| Database | Supabase (PostgreSQL) / SQLite fallback | Free tier, managed Postgres with REST API |
| Triage LLM | Llama 3.3 70B via Groq | Ultra-low latency (~200ms) for binary classification |
| Analyst LLM | GPT-OSS 120B via Groq | Strong reasoning for multi-signal correlation |
| News Data | Google News RSS | Free, unlimited, no API key needed |
| Stock Data | Alpha Vantage | Free tier, 25 req/day |
| Weather Data | OpenWeatherMap | Free tier, 60 req/min |
| Dashboard | Streamlit | Rapid prototyping, built-in UI components |
| Monitoring | Background thread | Runs pipeline on user-set interval (15m–6hr) |
| Graph Viz | NetworkX + PyVis | Interactive knowledge graph |

---

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/your-username/khabar-ai.git
cd khabar-ai
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
cp .env.example .env
# Edit .env with your API keys
```

**Free-tier API keys needed:**
- [Alpha Vantage](https://www.alphavantage.co/support/#api-key) — stock data
- [OpenWeatherMap](https://openweathermap.org/api) — weather data
- [Groq](https://console.groq.com/) — fast LLM inference (triage + analysis)

### 3. Launch Dashboard

```bash
streamlit run dashboard/app.py
```

The dashboard runs on `http://localhost:8501` and has:

- **Live Monitoring** — pick a company (e.g., Apple Inc) and set an interval (e.g., 60 min) to run the pipeline automatically in the background
- **Manual Analysis** — enter any company name to run the pipeline on-demand
- **Dashboard** — view all detected risk events with clickable detail sections
- **Knowledge Graph** — interactive supply-chain visualization
- **Metrics** — charts for severity distribution, timeline, and noise reduction

No terminal commands needed — everything is controlled from the UI.

### 4. Run Tests

```bash
pytest tests/ -v
```

---

## Deployment (Free)

### Streamlit Community Cloud (Recommended)

Deploy for **free** with zero server management:

1. **Push to GitHub**
   ```bash
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/your-username/khabar-ai.git
   git push -u origin main
   ```

2. **Deploy on Streamlit Cloud**
   - Go to [share.streamlit.io](https://share.streamlit.io)
   - Sign in with GitHub
   - Click **"New app"**
   - Select your repo, branch: `main`, main file: `dashboard/app.py`
   - Click **"Deploy"**

3. **Add Secrets**
   In the Streamlit Cloud dashboard, go to **Settings → Secrets** and paste:

   ```toml
   GROQ_API_KEY = "your_groq_api_key"
   ALPHA_VANTAGE_API_KEY = "your_alpha_vantage_key"
   OPENWEATHER_API_KEY = "your_openweather_key"
   DATABASE_URL = "your_supabase_postgres_url"
   ```

4. **Done** — Your app will be live at `https://your-app-name.streamlit.app`

**Notes:**
- The background monitor runs automatically when the app starts
- Pick a company and interval from the **Live Monitoring** section on the Home page
- All APIs use free tiers — no credit card needed
- SQLite fallback works if you don't set `DATABASE_URL`

### Alternative: Render / Railway

Both have free tiers and support Streamlit. Follow similar steps:
1. Connect your GitHub repo
2. Set build command: `pip install -r requirements.txt`
3. Set start command: `streamlit run dashboard/app.py --server.port $PORT`
4. Add environment variables in their dashboard

---

## Project Structure

```
khabar-ai/
├── .streamlit/
│   └── config.toml              # Streamlit Cloud deployment settings
├── app/
│   ├── config.py                # Settings & YAML loader
│   ├── database.py              # SQLAlchemy engine & session
│   ├── models.py                # ORM models (RiskEvent, KnowledgeGraphEdge, AlertHistory)
│   ├── main.py                  # Pipeline orchestrator
│   ├── sensors/
│   │   ├── news_sensor.py       # Google News RSS integration
│   │   ├── finance_sensor.py    # Alpha Vantage integration
│   │   └── weather_sensor.py    # OpenWeatherMap integration
│   ├── agents/
│   │   ├── triage_agent.py      # Fast YES/NO filter (Groq)
│   │   ├── analyst_agent.py     # Deep reasoning (Groq)
│   │   └── knowledge_graph.py   # Supply-chain graph builder
│   └── action_layer/
│       ├── alert_manager.py     # Deduplication & storage
│       └── notifiers.py         # Slack / Telegram / console
├── dashboard/
│   └── app.py                   # Streamlit UI + background monitor
├── config/
│   └── companies.yaml           # Target companies & supply nodes
├── tests/
│   └── test_sensors.py          # Unit tests
├── monitor.py                   # Standalone monitor script (optional)
├── seed_data.py                 # Demo data seeder
├── requirements.txt
├── .env.example
├── DEPLOY.md                    # Deployment checklist
└── README.md
```

---

## Key Engineering Decisions

### Why Two LLMs?

Using a **cheap, fast model for triage** and a **reasoning model for analysis** is a production pattern called the **"LLM router"**. It reduces cost by ~90% compared to sending every article to the reasoning model.

### Why SHA-256 Deduplication?

News aggregators often surface the same story from multiple publishers. Hashing the headline provides O(1) duplicate detection without needing fuzzy matching (which would require embedding storage). Good enough for 100 events/day.

### Why SQLite Fallback?

Not every recruiter reviewing this project will have a Supabase account. The SQLite fallback means `streamlit run dashboard/app.py` works out of the box with zero configuration.

### Why YAML for Company Config?

Supply-chain analysts (the intended users) can edit YAML without touching Python. It's also easy to diff in Git, making change history transparent.

---

## Free-Tier Rate Limits

| API | Limit | Our Usage | Safety Margin |
|-----|-------|-----------|---------------|
| Google News RSS | Unlimited | ~24/day (hourly, 1 company) | No limit |
| Alpha Vantage | 25 req/day | ~5/day (only after triage) | 5x headroom |
| OpenWeatherMap | 60 req/min | ~10/hour | 360x headroom |
| Groq | 30 req/min | ~50/hour (triage + analyst) | Backoff built in |

---

## Future Enhancements

- [ ] **Semantic deduplication** using sentence embeddings instead of exact hash
- [ ] **Multi-hop reasoning** across knowledge graph (e.g., "if TSMC is down, who else is affected?")
- [ ] **Email digest** with daily PDF report
- [ ] **FastAPI endpoints** for programmatic access
- [ ] **Embeddings-based triage** to replace LLM classifier for even lower latency
- [ ] **Geospatial visualisation** with Mapbox for supply-chain node locations

---

## License

MIT — see [LICENSE](LICENSE) for details.
