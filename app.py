"""
Cricket Match Analysis App - APIFY STANDBY VERSION (All Formats)
"""
import asyncio
import random
import sqlite3
import json
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

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
            xi1 TEXT, xi2 TEXT,
            pre_analysis TEXT,
            post_analysis TEXT,
            live_score TEXT,
            confidence REAL,
            status TEXT DEFAULT 'pre'
        )
    """)
    conn.commit()
    conn.close()

def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# =========================================================
# 2. REAL DATA PROVIDER (Apify Standby)
# =========================================================
class RealDataProvider:
    def __init__(self):
        # ⚠️ PASTE YOUR APIFY TOKEN HERE ⚠️
        self.apify_token = "https://superapis--cricbuzz.apify.actor?token=apify_api_xSfcYmyrvLM5wlJUG6sUOgpPn9KAoL1igA7s"
        self.base_url = "https://superapis--cricbuzz.apify.actor"

    async def fetch_upcoming_matches(self):
        matches = []
        url = f"{self.base_url}/v1/matches/live?token={self.apify_token}"
        
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, timeout=30.0)
                data = resp.json()
                
                for type_match in data.get("typeMatches", []):
                    for series in type_match.get("seriesMatches", []):
                        series_data = series.get("seriesAdWrapper", {})
                        if not series_data: continue
                        
                        for m in series_data.get("matches", []):
                            match_info = m.get("matchInfo", {})
                            if not match_info: continue

                            start_time = datetime.utcfromtimestamp(match_info["startDate"] / 1000.0)
                            
                            matches.append({
                                "external_id": str(match_info["matchId"]),
                                "team1": match_info["team1"]["teamName"],
                                "team2": match_info["team2"]["teamName"],
                                "start_time": start_time.isoformat(),
                                "venue": match_info.get("venueInfo", {}).get("ground", "Unknown"),
                                "city": match_info.get("venueInfo", {}).get("city", "Unknown"),
                                "region": "International",
                                "format": match_info.get("matchFormat", "Unknown")
                            })
            except Exception as e:
                print(f"Apify Fetch Error: {e}")
                
        return matches

    async def fetch_match_details(self, external_id: str):
        url = f"{self.base_url}/v1/matches/{external_id}/scorecard?token={self.apify_token}"
        
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, timeout=30.0)
                data = resp.json()
                
                toss_info = data.get("tossResults")
                if toss_info:
                    score = data.get("score", [])
                    runs, wkts, overs = 0, 0, 0.0
                    if score and len(score) > 0:
                        runs = score[0].get("r", 0)
                        wkts = score[0].get("w", 0)
                        overs = score[0].get("o", 0.0)
                        
                    return {
                        "matchStarted": True,
                        "matchEnded": data.get("isMatchEnded", False),
                        "live_score": f"{runs}/{wkts} ({overs} ov)" if runs > 0 else None,
                        "runs": runs,
                        "wickets": wkts,
                        "overs": overs,
                        "toss_winner": toss_info.get("tossWinner", "Unknown"),
                        "toss_decision": toss_info.get("decision", "bat"),
                        "xi1": [], 
                        "xi2": []
                    }
            except Exception as e:
                print(f"Apify Details Error: {e}")
        return None

provider = RealDataProvider()

# =========================================================
# 3. ANALYSIS ENGINE
# =========================================================
class AnalysisEngine:
    def pre_analysis(self, match):
        t1, t2 = match["team1"], match["team2"]
        return {
            "h2h": {"team1_wins": random.randint(5, 12), "team2_wins": random.randint(2, 8)},
            "recent_form": {t1: ["W", "W", "W", "L", "W"], t2: ["L", "L", "W", "L", "W"]},
            "venue_stats": {
                "avg_1st_innings": random.randint(160, 200),
                "avg_2nd_innings": random.randint(150, 185),
                "toss_win_chooses_bowl_pct": random.randint(60, 85),
                "pitch_type": random.choice(["Batting paradise", "Balanced", "Bowling friendly"]),
            },
            "weather": random.choice(["Clear, 28°C", "Humid, 31°C"]),
        }

    def post_toss_analysis(self, match, details, pre):
        toss_winner = details["toss_winner"]
        decision = details["toss_decision"]
        t1, t2 = match["team1"], match["team2"]
        live_score = details.get("live_score")
        
        base_score = {t1: 50.0, t2: 50.0}
        
        if decision == "bowl" and pre["venue_stats"]["pitch_type"] == "Batting paradise":
            chaser = t2 if toss_winner == t1 else t1
            base_score[chaser] += 15.0
            
        form1 = pre["recent_form"][t1].count("W")
        form2 = pre["recent_form"][t2].count("W")
        base_score[t1] += (form1 - form2) * 3
        base_score[t2] += (form2 - form1) * 3

        reasons = [f"{toss_winner} won the toss and chose to {decision}."]
        
        if live_score and details["runs"] > 0:
            runs, wkts, overs = details["runs"], details["wickets"], details["overs"]
            if overs > 0:
                current_rr = runs / overs
                batting_team = toss_winner if decision == "bat" else (t2 if toss_winner == t1 else t1)
                bowling_team = t1 if batting_team == t2 else t2

                if overs > 15:
                    projected_score = current_rr * 20
                    if projected_score > 190:
                        base_score[batting_team] += 25
                        reasons.append(f"Massive projected score of {int(projected_score)}.")
                    elif projected_score < 140:
                        base_score[bowling_team] += 25
                        reasons.append(f"Struggling. Projected score only {int(projected_score)}.")
                
                if runs < 200 and overs > 5: 
                    target = random.randint(170, 195) 
                    balls_left = (20 - overs) * 6
                    if balls_left > 0:
                        rrr = ((target - runs) / balls_left) * 6
                        if rrr > 14:
                            base_score[bowling_team] += 35 
                            reasons.append(f"Required run rate is a massive {rrr:.2f}. Bowling team heavily favored.")
                        elif rrr < 8:
                            base_score[batting_team] += 25
                            reasons.append(f"Chasing team is cruising. Needs just {rrr:.2f} RPO.")

        total = base_score[t1] + base_score[t2]
        p1 = round((base_score[t1] / total) * 100, 1)
        p2 = round(100 - p1, 1)

        winner = t1 if p1 > p2 else t2
        confidence = max(p1, p2)

        if confidence > 70 and (details.get("wickets", 0) > 6 or "massive" in "".join(reasons)):
            confidence = max(confidence, 80.5) 

        return {
            "predicted_winner": winner, "confidence": confidence, "probabilities": {t1: p1, t2: p2},
            "toss_summary": f"{toss_winner} won the toss and chose to {decision}",
            "live_score": live_score, "reasoning": reasons,
            "matchups": {"powerplay": "Early wickets crucial.", "death_overs": f"{winner} edge."},
            "xi1": ["Player A", "Player B", "Player C"], "xi2": ["Player X", "Player Y", "Player Z"],
        }

engine = AnalysisEngine()

# =========================================================
# 4. SCHEDULED JOBS
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

async def check_toss_job():
    conn = db_conn()
    pending = conn.execute("SELECT * FROM matches WHERE status='pre' OR status='post' OR status='live'").fetchall()
    for row in pending:
        details = await provider.fetch_match_details(row["external_id"])
        if details and details["matchStarted"]:
            pre = json.loads(row["pre_analysis"])
            post = engine.post_toss_analysis(dict(row), details, pre)
            
            new_status = 'live' if details.get("live_score") and not details.get("matchEnded") else 'post'
            
            conn.execute(
                """UPDATE matches SET toss_winner=?, toss_decision=?, xi1=?, xi2=?,
                   post_analysis=?, live_score=?, confidence=?, status=? WHERE id=?""",
                (details["toss_winner"], details["toss_decision"], json.dumps(details["xi1"]), json.dumps(details["xi2"]),
                 json.dumps(post), details.get("live_score"), post["confidence"], new_status, row["id"])
            )
    conn.commit()
    conn.close()

# =========================================================
# 5. FASTAPI APP & FRONTEND
# =========================================================
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await refresh_matches_job()
    scheduler.add_job(refresh_matches_job, "interval", minutes=60) 
    scheduler.add_job(check_toss_job, "interval", minutes=60) 
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan, title="Match Analyzer")

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
    conn.close()
    if not row: raise HTTPException(404, "Match not found")
    d = dict(row)
    d["pre_analysis"] = json.loads(d["pre_analysis"]) if d["pre_analysis"] else None
    d["post_analysis"] = json.loads(d["post_analysis"]) if d["post_analysis"] else None
    return d

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/><title>🏏 Match Analyzer</title>
<style>
  body { font-family: system-ui; background: #0f172a; color: #e2e8f0; padding: 16px; }
  .filter-bar { display: flex; gap: 10px; margin-bottom: 16px; overflow-x: auto; padding-bottom: 8px; }
  .filter-btn { background: #1e293b; color: #94a3b8; border: 1px solid #334155; padding: 8px 16px; border-radius: 20px; cursor: pointer; font-size: 0.85rem; white-space: nowrap; }
  .filter-btn.active { background: #38bdf8; color: #0f172a; font-weight: bold; border-color: #38bdf8; }
  .card { background: #1e293b; border-radius: 12px; padding: 16px; margin-bottom: 12px; cursor: pointer; }
  .card:hover { background: #334155; }
  .badge { padding: 3px 10px; border-radius: 12px; font-size: .7rem; font-weight: 600; }
  .pre { background: #422006; color: #fbbf24; } .post { background: #052e16; color: #4ade80; } .live { background: #7f1d1d; color: #fca5a5; animation: pulse 2s infinite; }
  @keyframes pulse { 50% { opacity: 0.5; } }
  .section { background: #1e293b; border-radius: 12px; padding: 16px; margin-bottom: 12px; }
  .winner { font-size: 2rem; color: #4ade80; font-weight: 800; text-align: center; }
  .conf { font-size: 3rem; color: #38bdf8; font-weight: 800; text-align: center; }
  .bar { height: 10px; background: #334155; border-radius: 4px; } .bar-fill { height: 100%; background: #4ade80; }
  .live-box { margin-top: 12px; padding: 12px; background: #7f1d1d; border: 1px solid #ef4444; border-radius: 8px; text-align: center; }
</style>
</head>
<body>
<div id="view" style="max-width:720px; margin:0 auto;">Loading...</div>
<script>
const view = document.getElementById('view');
let allMatches = [];
let currentFilter = 'All';

async function loadMatches() {
  const res = await fetch('/api/matches'); allMatches = await res.json();
  renderFilters();
  renderMatches();
}

function renderFilters() {
  const regions = ['All', 'International', 'Australia', 'India', 'England', 'South Africa'];
  let html = '<h1>🏏 All Matches</h1><div class="filter-bar">';
  regions.forEach(r => {
    html += `<button class="filter-btn ${currentFilter === r ? 'active' : ''}" onclick="setFilter('${r}')">${r}</button>`;
  });
  html += '</div><div id="match-list"></div>';
  view.innerHTML = html;
}

function setFilter(region) {
  currentFilter = region;
  renderFilters();
  renderMatches();
}

function renderMatches() {
  const list = document.getElementById('match-list');
  const filtered = currentFilter === 'All' ? allMatches : allMatches.filter(m => m.region === currentFilter);
  
  if (!filtered.length) { list.innerHTML = '<div style="color:#94a3b8; text-align:center; margin-top:20px;">No matches found.</div>'; return; }
  
  list.innerHTML = filtered.map(m => `
    <div class="card" onclick="openMatch(${m.id})">
      <div><strong>${m.team1} vs ${m.team2}</strong></div>
      <div style="font-size:0.85rem; color:#94a3b8;">${m.venue} • ${m.match_format}</div>
      <span class="badge ${m.status}">${m.status === 'live' ? '🔴 LIVE' : (m.status === 'post' ? '✅ PREDICTION' : '⏳ PRE-ANALYSIS')}</span>
    </div>`).join('');
}

async function openMatch(id) {
  view.innerHTML = 'Loading...'; const res = await fetch('/api/match/' + id); const m = await res.json();
  let html = `<span style="color:#38bdf8; cursor:pointer" onclick="loadMatches()">← Back</span><h1>${m.team1} vs ${m.team2}</h1>`;
  if ((m.status === 'post' || m.status === 'live') && m.post_analysis) {
    const q = m.post_analysis;
    html += `<div class="section" style="border:2px solid ${m.status === 'live' ? '#ef4444' : '#4ade80'}">
      <h3>🏆 Prediction</h3><div class="winner">${q.predicted_winner}</div><div class="conf">${q.confidence}%</div>
      <div class="bar"><div class="bar-fill" style="width:${q.confidence}%"></div></div>
      ${q.live_score ? `<div class="live-box"><div>🔴 LIVE SCORE</div><div style="font-size:1.5rem; font-weight:bold">${q.live_score}</div></div>` : ''}
      <div style="margin-top:16px; padding:12px; background:#334155; border-radius:8px">🪙 ${q.toss_summary}</div>
      <h3>Reasoning</h3>${q.reasoning.map(r => `<div>▸ ${r}</div>`).join('')}
    </div>`;
  } else { html += `<div class="section">⏳ Awaiting Toss...</div>`; }
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
