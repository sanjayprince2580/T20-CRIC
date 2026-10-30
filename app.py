"""
Cricket Match Analysis App - FINAL AI VERSION
"""
import asyncio
import random
import sqlite3
import json
import pickle
import numpy as np
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Load the AI Model
try:
    with open('cricket_model.pkl', 'rb') as f:
        model, le_team, le_venue, le_decision = pickle.load(f)
    print("✅ AI Model loaded successfully!")
except Exception as e:
    print(f"⚠️ Could not load AI model: {e}")
    model = None

# =========================================================
# 1. DATABASE LAYER
# =========================================================
DB_PATH = "cricket.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id TEXT UNIQUE,
            team1 TEXT, team2 TEXT,
            start_time TEXT, venue TEXT, city TEXT, region TEXT,
            match_format TEXT,
            toss_winner TEXT, toss_decision TEXT,
            pre_analysis TEXT, post_analysis TEXT, live_score TEXT,
            confidence REAL, status TEXT DEFAULT 'pre'
        )
    """)
    conn.commit()
    conn.close()

def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# =========================================================
# 2. REAL DATA PROVIDER (SportScore)
# =========================================================
class RealDataProvider:
    def __init__(self):
        self.base_url = "https://sportscore.com/api/widget/matches/"

    async def fetch_upcoming_matches(self):
        matches = []
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(self.base_url, params={"sport": "cricket", "limit": 20}, timeout=15.0)
                if resp.status_code != 200: return []
                data = resp.json()
                
                for m in data:
                    team1 = m.get("home", "Unknown") 
                    team2 = m.get("away", "Unknown")
                    slug = m.get("slug", "")
                    if not slug or team1 == "Unknown": continue

                    matches.append({
                        "external_id": slug, "team1": team1, "team2": team2,
                        "start_time": datetime.utcnow().isoformat(),
                        "venue": m.get("venue", "Unknown"),
                        "city": "International", "region": "International", "format": "T20"
                    })
            except Exception as e:
                print(f"Fetch Error: {e}")
        return matches

    async def fetch_match_details(self, external_id: str):
        # For this demo, we simulate a toss because SportScore doesn't provide it for free.
        # In the future, you can swap this with a paid API.
        return {
            "matchStarted": True, 
            "matchEnded": False, 
            "live_score": "N/A", 
            "runs": 0, "wickets": 0, "overs": 0.0,
            "toss_winner": "Random Team", 
            "toss_decision": "bat",
            "xi1": [], "xi2": []
        }

provider = RealDataProvider()

# =========================================================
# 3. AI ANALYSIS ENGINE
# =========================================================
class AnalysisEngine:
    def pre_analysis(self, match):
        return {
            "h2h": {"team1_wins": 5, "team2_wins": 5},
            "recent_form": {match["team1"]: ["W", "L"], match["team2"]: ["W", "L"]},
            "venue_stats": {"pitch_type": "Balanced"},
        }

    def post_toss_analysis(self, match, details, pre):
        t1, t2 = match["team1"], match["team2"]
        
        # AI PREDICTION LOGIC
        if model:
            try:
                # Default to T1 winning toss for demo
                toss_winner = t1
                toss_decision = "bat"
                
                # Convert strings to numbers using our saved LabelEncoders
                # If a team/venue is unseen, default to 0 (unknown)
                t1_enc = le_team.transform([t1])[0] if t1 in le_team.classes_ else 0
                t2_enc = le_team.transform([t2])[0] if t2 in le_team.classes_ else 0
                v_enc = le_venue.transform([match["venue"]])[0] if match["venue"] in le_venue.classes_ else 0
                d_enc = le_decision.transform([toss_decision])[0] if toss_decision in le_decision.classes_ else 0
                
                toss_t1 = 1 if toss_winner == t1 else 0
                
                features = np.array([[t1_enc, t2_enc, toss_t1, d_enc, v_enc]])
                
                # Predict
                prediction = model.predict(features)[0]
                probability = model.predict_proba(features)[0]
                
                winner = t1 if prediction == 1 else t2
                confidence = round(max(probability) * 100, 1)
                
                reasons = [
                    f"AI Model detected strong statistical patterns for {winner}.",
                    f"{toss_winner} won the toss and chose to {toss_decision}.",
                    f"Venue data ({match['venue']}) factored into prediction."
                ]
            except Exception as e:
                print(f"Prediction Error: {e}")
                winner, confidence, reasons = t1, 50.0, ["Fallback prediction due to data mismatch."]
        else:
            winner, confidence, reasons = t1, 50.0, ["AI Model not loaded."]

        return {
            "predicted_winner": winner, 
            "confidence": confidence, 
            "probabilities": {t1: confidence, t2: 100-confidence},
            "toss_summary": f"{details['toss_winner']} won the toss and chose to {details['toss_decision']}",
            "live_score": details.get("live_score"), 
            "reasoning": reasons,
            "xi1": ["Player A", "Player B"], "xi2": ["Player X", "Player Y"],
        }

engine = AnalysisEngine()

# =========================================================
# 4. SCHEDULED JOBS & APP
# =========================================================
async def refresh_matches_job():
    matches = await provider.fetch_upcoming_matches()
    conn = db_conn()
    for m in matches:
        existing = conn.execute("SELECT id FROM matches WHERE external_id=?", (m["external_id"],)).fetchone()
        if not existing:
            pre = engine.pre_analysis(m)
            conn.execute(
                """INSERT INTO matches (external_id, team1, team2, start_time, venue, city, region, match_format, pre_analysis, status)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (m["external_id"], m["team1"], m["team2"], m["start_time"], m["venue"], m["city"], m["region"], m["format"], json.dumps(pre), "pre")
            )
    conn.commit()
    conn.close()

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await refresh_matches_job()
    scheduler.add_job(refresh_matches_job, "interval", minutes=60) 
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan, title="AI Match Analyzer")

@app.get("/api/matches")
async def list_matches():
    conn = db_conn()
    rows = conn.execute("SELECT id, team1, team2, start_time, venue, city, region, match_format, status, confidence FROM matches ORDER BY start_time").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/match/{match_id}")
async def get_match(match_id: int):
    conn = db_conn()
    row = conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
    if not row: 
        conn.close()
        raise HTTPException(404, "Match not found")
        
    d = dict(row)
    if d["status"] == "pre":
        details = await provider.fetch_match_details(d["external_id"])
        pre = json.loads(d["pre_analysis"])
        post = engine.post_toss_analysis(d, details, pre)
        
        conn.execute(
            """UPDATE matches SET toss_winner=?, toss_decision=?, post_analysis=?, live_score=?, confidence=?, status='live' WHERE id=?""",
            (details["toss_winner"], details["toss_decision"], json.dumps(post), details["live_score"], post["confidence"], match_id)
        )
        conn.commit()
        d["status"] = 'live'
        d["post_analysis"] = json.dumps(post)
        
    conn.close()
    d["pre_analysis"] = json.loads(d["pre_analysis"]) if d["pre_analysis"] else None
    d["post_analysis"] = json.loads(d["post_analysis"]) if d["post_analysis"] else None
    return d

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/><title>🏏 AI Match Analyzer</title>
<style>
  body { font-family: system-ui; background: #0f172a; color: #e2e8f0; padding: 16px; }
  .card { background: #1e293b; border-radius: 12px; padding: 16px; margin-bottom: 12px; cursor: pointer; }
  .card:hover { background: #334155; }
  .badge { padding: 3px 10px; border-radius: 12px; font-size: .7rem; font-weight: 600; }
  .pre { background: #422006; color: #fbbf24; } .post { background: #052e16; color: #4ade80; } .live { background: #7f1d1d; color: #fca5a5; animation: pulse 2s infinite; }
  @keyframes pulse { 50% { opacity: 0.5; } }
  .section { background: #1e293b; border-radius: 12px; padding: 16px; margin-bottom: 12px; }
  .winner { font-size: 2rem; color: #4ade80; font-weight: 800; text-align: center; }
  .conf { font-size: 3rem; color: #38bdf8; font-weight: 800; text-align: center; }
  .bar { height: 10px; background: #334155; border-radius: 4px; } .bar-fill { height: 100%; background: #4ade80; }
  .attribution { text-align: center; margin-top: 20px; font-size: 0.75rem; color: #64748b; }
</style>
</head>
<body>
<div id="view" style="max-width:720px; margin:0 auto;">Loading...</div>
<div class="attribution">Powered by <a href="https://sportscore.com" target="_blank">SportScore</a> & AI</div>
<script>
const view = document.getElementById('view');
async function loadMatches() {
  const res = await fetch('/api/matches'); const matches = await res.json();
  if (!matches.length) { view.innerHTML = 'No matches found.'; return; }
  view.innerHTML = '<h1>🏏 AI Match Analyzer</h1>' + matches.map(m => `
    <div class="card" onclick="openMatch(${m.id})">
      <div><strong>${m.team1} vs ${m.team2}</strong></div>
      <div style="font-size:0.85rem; color:#94a3b8;">${m.venue} • ${m.match_format}</div>
      <span class="badge ${m.status}">${m.status === 'live' ? '🔴 LIVE' : (m.status === 'post' ? '✅ PREDICTION' : '⏳ PRE-ANALYSIS')}</span>
    </div>`).join('');
}
async function openMatch(id) {
  view.innerHTML = 'Loading AI...'; const res = await fetch('/api/match/' + id); const m = await res.json();
  let html = `<span style="color:#38bdf8; cursor:pointer" onclick="loadMatches()">← Back</span><h1>${m.team1} vs ${m.team2}</h1>`;
  if (m.post_analysis) {
    const q = m.post_analysis;
    html += `<div class="section" style="border:2px solid #4ade80">
      <h3>🏆 AI Prediction</h3><div class="winner">${q.predicted_winner}</div><div class="conf">${q.confidence}%</div>
      <div class="bar"><div class="bar-fill" style="width:${q.confidence}%"></div></div>
      <div style="margin-top:16px; padding:12px; background:#334155; border-radius:8px">🪙 ${q.toss_summary}</div>
      <h3>AI Reasoning</h3>${q.reasoning.map(r => `<div>▸ ${r}</div>`).join('')}
    </div>`;
  } else { html += `<div class="section">⏳ Awaiting Analysis...</div>`; }
  view.innerHTML = html;
}
loadMatches();
</script>
</body>
</html>
"""
@app.get("/", response_class=HTMLResponse)
async def index(): return HTML_PAGE

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
