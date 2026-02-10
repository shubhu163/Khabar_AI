# Deployment Checklist

## ✅ Prerequisites

- [ ] GitHub account
- [ ] Free API keys obtained:
  - [Groq](https://console.groq.com/) — LLM inference
  - [Alpha Vantage](https://www.alphavantage.co/support/#api-key) — stock data
  - [OpenWeatherMap](https://openweathermap.org/api) — weather data
  - [Supabase](https://supabase.com/) — PostgreSQL (optional, SQLite fallback works)

---

## 🚀 Streamlit Community Cloud (5 minutes)

### Step 1: Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit - Khabar AI"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/khabar-ai.git
git push -u origin main
```

### Step 2: Deploy

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click **"New app"**
3. Select:
   - **Repository:** `YOUR-USERNAME/khabar-ai`
   - **Branch:** `main`
   - **Main file path:** `dashboard/app.py`
4. Click **"Advanced settings"** → **Secrets** → Paste:

```toml
GROQ_API_KEY = "gsk_..."
ALPHA_VANTAGE_API_KEY = "YOUR_KEY"
OPENWEATHER_API_KEY = "YOUR_KEY"
DATABASE_URL = "postgresql://..."  # Optional
```

5. Click **"Deploy"**

### Step 3: Test

- Wait 2-3 minutes for deployment
- Your app will be live at: `https://YOUR-APP-NAME.streamlit.app`
- Go to **Home** → **Live Monitoring** → pick a company → click "Start Monitoring"

---

## 🔧 Troubleshooting

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError` | Check `requirements.txt` is present in repo root |
| `KeyError: 'GROQ_API_KEY'` | Add all secrets in Streamlit Cloud settings |
| Database connection fails | Leave `DATABASE_URL` blank to use SQLite fallback |
| App crashes on startup | Check logs in Streamlit Cloud dashboard → "Manage app" → "Logs" |

---

## 📊 Post-Deployment

1. **Set up monitoring:**
   - Go to Home page → Live Monitoring
   - Pick company: "Apple Inc"
   - Interval: 60 min
   - Click "Start Monitoring"

2. **Run manual analysis:**
   - Scroll to "Run a Manual Analysis"
   - Enter: "Tesla Inc, NVIDIA"
   - Click "Run Analysis"

3. **Check results:**
   - Go to "Dashboard" page to see events
   - Go to "Knowledge Graph" to see supply chain
   - Go to "Metrics" to see charts

---

## 🆓 Free Tier Limits

All APIs used are **100% free tier** compatible:

- **Groq:** 30 req/min (we use ~5/hr)
- **Alpha Vantage:** 25 req/day (we use ~5/day)
- **OpenWeatherMap:** 60 req/min (we use ~10/hr)
- **Supabase:** 500 MB storage (plenty for demo)
- **Streamlit Cloud:** Unlimited for public repos

No credit card needed anywhere!
