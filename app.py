"""
T20 Cricket Match Analysis App - All-in-One
Run: python app.py
Open: http://localhost:8000
"""
import asyncio
import random
import sqlite3
import json
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# =========================================================
# 1. DATABASE LAYER (SQLite)
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
            start_time TEXT, venue TEXT, city TEXT,
            toss_winner TEXT, toss_decision TEXT,
            xi1 TEXT, xi2 TEXT,
            pre_analysis TEXT,
            post_analysis TEXT,
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
# 2. MOCK DATA PROVIDER (swap with real API here)
# =========================================================
class MockDataProvider:
    """Replace this class with a real licensed provider."""
    TEAMS = ["India", "Australia", "England", "Pakistan", "South Africa",
             "New Zealand", "Sri Lanka", "Bangladesh", "West Indies", "Afghanistan"]
    VENUES = [
        ("Wankhede Stadium", "Mumbai"),
        ("Eden Gardens", "Kolkata"),
        ("M. Chinnaswamy Stadium", "Bengaluru"),
        ("Melbourne Cricket Ground", "Melbourne"),
        ("Lord's", "London"),
        ("Dubai International Stadium", "Dubai"),
    ]
    PLAYERS = {
        "India": ["Rohit Sharma", "Virat Kohli", "Suryakumar Yadav", "Hardik Pandya",
                  "Rishabh Pant", "Jasprit Bumrah", "Kuldeep Yadav", "Axar Patel",
                  "Arshdeep Singh", "Shivam Dube", "Sanju Samson"],
        "Australia": ["David Warner", "Travis Head", "Steve Smith", "Glenn Maxwell",
                      "Marcus Stoinis", "Tim David", "Matthew Wade", "Pat Cummins",
                      "Mitchell Starc", "Adam Zampa", "Josh Hazlewood"],
        "England": ["Jos Buttler", "Phil Salt", "Joe Root", "Harry Brook",
                    "Liam Livingstone", "Moeen Ali", "Sam Curran", "Jofra Archer",
                    "Adil Rashid", "Mark Wood", "Jonny Bairstow"],
        "Pakistan": ["Babar Azam", "Mohammad Rizwan", "Fakhar Zaman", "Saim Ayub",
                     "Iftikhar Ahmed", "Shadab Khan", "Mohammad Nawaz", "Shaheen Afridi",
                     "Haris Rauf", "Naseem Shah", "Usman Khan"],
    }

    async def fetch_upcoming_matches(self):
        """Returns list of matches for the next 3 days."""
        random.seed(42)  # reproducible demo
        matches = []
        now = datetime.utcnow()
        for i in range(6):
            t1, t2 = random.sample(self.TEAMS[:6], 2)
            venue, city = random.choice(self.VENUES)
            start = now + timedelta(hours=random.randint(2, 70))
            matches.append({
                "external_id": f"MATCH{1000+i}",
                "team1": t1, "team2": t2,
                "start_time": start.isoformat(),
                "venue": venue, "city": city,
            })
        return matches

    async def fetch_toss_and_xi(self, external_id: str):
        """
        Simulates toss detection. In real life, call your API and check
        if toss info is available (only happens ~30 min before match).
        """
        conn = db_conn()
        row = conn.execute("SELECT * FROM matches WHERE external_id=?", (external_id,)).fetchone()
        conn.close()
        if not row:
            return None
        start = datetime.fromisoformat(row["start_time"])
        # Reveal toss only within 30 min of start (for demo: random chance)
        if datetime.utcnow() >= start - timedelta(minutes=30):
            winner = random.choice([row["team1"], row["team2"]])
            decision = random.choice(["bat", "bowl"])
            xi1 = self._build_xi(row["team1"])
            xi2 = self._build_xi(row["team2"])
            return {"toss_winner": winner, "toss_decision": decision,
                    "xi1": xi1, "xi2": xi2}
        return None

    def _build_xi(self, team):
        pool = self.PLAYERS.get(team, [f"{team} Player {i}" for i in range(1, 12)])
        return random.sample(pool, min(11, len(pool)))

provider = MockDataProvider()

# =========================================================
# 3. ANALYSIS ENGINE
# =========================================================
class AnalysisEngine:
    def pre_analysis(self, match):
        """Rule-based pre-toss analysis."""
        t1, t2 = match["team1"], match["team2"]
        h2h = {"team1_wins": random.randint(4, 9), "team2_wins": random.randint(3, 8)}
        form = {
            t1: [random.choice(["W", "L"]) for _ in range(5)],
            t2: [random.choice(["W", "L"]) for _ in range(5)],
        }
        venue_stats = {
            "avg_1st_innings": random.randint(150, 190),
            "avg_2nd_innings": random.randint(140, 180),
            "toss_win_chooses_bowl_pct": random.randint(55, 80),
            "pitch_type": random.choice(["Batting paradise", "Balanced", "Bowling friendly", "Slow & low"]),
        }
        key_players = {
            t1: {"top_scorer": random.choice(provider.PLAYERS.get(t1, ["Player A"])),
                 "top_wicket_taker": random.choice(provider.PLAYERS.get(t1, ["Bowler A"]))},
            t2: {"top_scorer": random.choice(provider.PLAYERS.get(t2, ["Player B"])),
                 "top_wicket_taker": random.choice(provider.PLAYERS.get(t2, ["Bowler B"]))},
        }
        weather = random.choice([
            "Clear, 28°C, 15% rain chance",
            "Partly cloudy, 25°C, 30% rain chance",
            "Humid, 31°C, 10% rain chance",
        ])
        return {
            "h2h": h2h, "recent_form": form, "venue_stats": venue_stats,
            "key_players": key_players, "weather": weather,
            "team_composition_trend": f"{t1} prefers 3 pacers + 2 spinners; "
                                       f"{t2} leans 2 pacers + 3 spinners.",
        }

    def post_toss_analysis(self, match, toss_data, pre):
        """Deeper post-toss analysis."""
        toss_winner = toss_data["toss_winner"]
        decision = toss_data["toss_decision"]
        t1, t2 = match["team1"], match["team2"]

        # Scoring model (rule-based)
        base = {"team1": 50.0, "team2": 50.0}

        # Venue toss impact
        bowl_pct = pre["venue_stats"]["toss_win_chooses_bowl_pct"]
        if decision == "bowl":
            chaser = t2 if toss_winner == t1 else t1
            base["team1" if chaser == t1 else "team2"] += bowl_pct / 10

        # Form factor
        form1 = pre["recent_form"][t1].count("W")
        form2 = pre["recent_form"][t2].count("W")
        base["team1"] += (form1 - form2) * 2
        base["team2"] += (form2 - form1) * 2

        # Normalize
        total = base["team1"] + base["team2"]
        p1 = round(base["team1"] / total * 100, 1)
        p2 = round(100 - p1, 1)

        winner = t1 if p1 > p2 else t2
        confidence = max(p1, p2)

        # Build reasoning list
        reasons = []
        reasons.append(f"{toss_winner} won the toss and elected to {decision}.")
        if decision == "bowl" and bowl_pct > 65:
            reasons.append(f"At {match['venue']}, {bowl_pct}% of toss winners who bowl go on to win.")
        form_leader = t1 if form1 > form2 else t2
        reasons.append(f"{form_leader} enters with stronger recent form ({max(form1, form2)}W in last 5).")
        reasons.append(f"Pitch is {pre['venue_stats']['pitch_type']}, avg 1st innings {pre['venue_stats']['avg_1st_innings']}.")
        reasons.append("Death-over bowling depth gives the edge in final 4 overs.")

        # Matchup matrix (bowling vs batting)
        matchups = {
            "powerplay": f"{t1} pacers vs {t2} openers — edge to {random.choice([t1, t2])}",
            "middle_overs": f"Spin duel in overs 7-15 — key to the game.",
            "death_overs": f"{random.choice([t1, t2])} have superior death specialists.",
        }

        return {
            "predicted_winner": winner,
            "confidence": confidence,
            "probabilities": {t1: p1, t2: p2},
            "toss_summary": f"{toss_winner} chose to {decision}",
            "reasoning": reasons,
            "matchups": matchups,
            "xi1": toss_data["xi1"],
            "xi2": toss_data["xi2"],
        }

engine = AnalysisEngine()

# =========================================================
# 4. SCHEDULED JOBS
# =========================================================
async def refresh_matches_job():
    print("[CRON] Refreshing match list...")
    matches = await provider.fetch_upcoming_matches()
    conn = db_conn()
    for m in matches:
        existing = conn.execute(
            "SELECT id FROM matches WHERE external_id=?", (m["external_id"],)
        ).fetchone()
        if existing:
            continue
        pre = engine.pre_analysis(m)
        conn.execute(
            """INSERT INTO matches
               (external_id, team1, team2, start_time, venue, city, pre_analysis, status)
               VALUES (?,?,?,?,?,?,?,?)""",
            (m["external_id"], m["team1"], m["team2"], m["start_time"],
             m["venue"], m["city"], json.dumps(pre), "pre")
        )
    conn.commit()
    conn.close()
    print(f"[CRON] Match list refreshed ({len(matches)} matches).")

async def check_toss_job():
    print("[CRON] Checking for toss updates...")
    conn = db_conn()
    pending = conn.execute("SELECT * FROM matches WHERE status='pre'").fetchall()
    for row in pending:
        toss = await provider.fetch_toss_and_xi(row["external_id"])
        if toss:
            pre = json.loads(row["pre_analysis"])
            match_dict = dict(row)
            post = engine.post_toss_analysis(match_dict, toss, pre)
            conn.execute(
                """UPDATE matches SET toss_winner=?, toss_decision=?, xi1=?, xi2=?,
                   post_analysis=?, confidence=?, status='post' WHERE id=?""",
                (toss["toss_winner"], toss["toss_decision"],
                 json.dumps(toss["xi1"]), json.dumps(toss["xi2"]),
                 json.dumps(post), post["confidence"], row["id"])
            )
    conn.commit()
    conn.close()

# =========================================================
# 5. FASTAPI APP
# =========================================================
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await refresh_matches_job()
    scheduler.add_job(refresh_matches_job, "interval", minutes=45)
    scheduler.add_job(check_toss_job, "interval", minutes=1)  # 1 min for demo
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan, title="T20 Analyzer")

@app.get("/api/matches")
async def list_matches():
    conn = db_conn()
    rows = conn.execute(
        "SELECT id, team1, team2, start_time, venue, city, status, confidence FROM matches ORDER BY start_time"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/match/{match_id}")
async def get_match(match_id: int):
    conn = db_conn()
    row = conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Match not found")
    d = dict(row)
    d["pre_analysis"] = json.loads(d["pre_analysis"]) if d["pre_analysis"] else None
    d["post_analysis"] = json.loads(d["post_analysis"]) if d["post_analysis"] else None
    return d

# =========================================================
# 6. FRONTEND (served as single HTML page)
# =========================================================
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>🏏 T20 Analyzer</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #e2e8f0; padding: 16px; }
  h1 { font-size: 1.5rem; margin-bottom: 16px; color: #38bdf8; }
  .card { background: #1e293b; border-radius: 12px; padding: 16px; margin-bottom: 12px; cursor: pointer; transition: .2s; }
  .card:hover { background: #334155; transform: translateY(-2px); }
  .teams { font-size: 1.1rem; font-weight: 600; margin-bottom: 6px; }
  .meta { font-size: .85rem; color: #94a3b8; }
  .badge { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: .7rem; font-weight: 600; margin-top: 8px; }
  .badge.pre { background: #422006; color: #fbbf24; }
  .badge.post { background: #052e16; color: #4ade80; }
  .back { color: #38bdf8; cursor: pointer; margin-bottom: 16px; display: inline-block; }
  .section { background: #1e293b; border-radius: 12px; padding: 16px; margin-bottom: 12px; }
  .section h3 { font-size: .95rem; color: #38bdf8; margin-bottom: 10px; text-transform: uppercase; letter-spacing: .5px; }
  .row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #334155; font-size: .9rem; }
  .row:last-child { border: none; }
  .winner { font-size: 1.8rem; color: #4ade80; font-weight: 700; text-align: center; margin: 12px 0; }
  .conf { font-size: 2.4rem; color: #38bdf8; font-weight: 700; text-align: center; }
  .conf-label { text-align: center; color: #94a3b8; font-size: .8rem; }
  .bar { height: 8px; background: #334155; border-radius: 4px; overflow: hidden; margin-top: 8px; }
  .bar-fill { height: 100%; background: linear-gradient(90deg,#38bdf8,#4ade80); }
  .reason { font-size: .85rem; padding: 6px 0 6px 16px; position: relative; color: #cbd5e1; }
  .reason:before { content: "▸"; position: absolute; left: 0; color: #38bdf8; }
  .xi-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: .8rem; }
  .loading { text-align: center; padding: 40px; color: #94a3b8; }
  #view { max-width: 720px; margin: 0 auto; }
</style>
</head>
<body>
<div id="view"><div class="loading">Loading matches...</div></div>
<script>
const view = document.getElementById('view');

async function loadMatches() {
  const res = await fetch('/api/matches');
  const matches = await res.json();
  if (!matches.length) { view.innerHTML = '<div class="loading">No matches found.</div>'; return; }
  view.innerHTML = '<h1>🏏 Upcoming T20 Matches</h1>' + matches.map(m => {
    const dt = new Date(m.start_time + 'Z');
    return `
    <div class="card" onclick="openMatch(${m.id})">
      <div class="teams">${m.team1} vs ${m.team2}</div>
      <div class="meta">${m.venue}, ${m.city} • ${dt.toLocaleString()}</div>
      <span class="badge ${m.status}">${m.status === 'post' ? '✅ Prediction Ready' : '⏳ Pre-Analysis'}</span>
    </div>`;
  }).join('');
}

async function openMatch(id) {
  view.innerHTML = '<div class="loading">Loading analysis...</div>';
  const res = await fetch('/api/match/' + id);
  const m = await res.json();
  let html = `<span class="back" onclick="loadMatches()">← Back to matches</span>`;
  html += `<h1>${m.team1} vs ${m.team2}</h1>`;
  html += `<div class="meta" style="margin-bottom:16px">${m.venue}, ${m.city}</div>`;

  // Pre-analysis (always shown)
  const p = m.pre_analysis;
  if (p) {
    html += `<div class="section"><h3>Head-to-Head</h3>
      <div class="row"><span>${m.team1} wins</span><span>${p.h2h.team1_wins}</span></div>
      <div class="row"><span>${m.team2} wins</span><span>${p.h2h.team2_wins}</span></div>
    </div>`;

    html += `<div class="section"><h3>Recent Form (Last 5)</h3>
      <div class="row"><span>${m.team1}</span><span>${p.recent_form[m.team1].join(' ')}</span></div>
      <div class="row"><span>${m.team2}</span><span>${p.recent_form[m.team2].join(' ')}</span></div>
    </div>`;

    const v = p.venue_stats;
    html += `<div class="section"><h3>Venue Stats</h3>
      <div class="row"><span>Pitch</span><span>${v.pitch_type}</span></div>
      <div class="row"><span>Avg 1st Innings</span><span>${v.avg_1st_innings}</span></div>
      <div class="row"><span>Avg 2nd Innings</span><span>${v.avg_2nd_innings}</span></div>
      <div class="row"><span>Toss-winner bowls %</span><span>${v.toss_win_chooses_bowl_pct}%</span></div>
    </div>`;

    html += `<div class="section"><h3>Key Players</h3>
      <div class="row"><span>${m.team1} top scorer</span><span>${p.key_players[m.team1].top_scorer}</span></div>
      <div class="row"><span>${m.team1} top bowler</span><span>${p.key_players[m.team1].top_wicket_taker}</span></div>
      <div class="row"><span>${m.team2} top scorer</span><span>${p.key_players[m.team2].top_scorer}</span></div>
      <div class="row"><span>${m.team2} top bowler</span><span>${p.key_players[m.team2].top_wicket_taker}</span></div>
    </div>`;

    html += `<div class="section"><h3>Weather</h3>
      <div class="row"><span>Forecast</span><span>${p.weather}</span></div>
    </div>`;
  }

  // Post-toss analysis
  if (m.status === 'post' && m.post_analysis) {
    const q = m.post_analysis;
    html += `<div class="section" style="border:2px solid #4ade80">
      <h3>🏆 Final Prediction</h3>
      <div class="winner">${q.predicted_winner}</div>
      <div class="conf">${q.confidence}%</div>
      <div class="conf-label">Confidence</div>
      <div class="bar"><div class="bar-fill" style="width:${q.confidence}%"></div></div>
      <div style="margin-top:16px;font-size:.85rem;color:#94a3b8">${q.toss_summary}</div>
    </div>`;

    html += `<div class="section"><h3>Reasoning</h3>
      ${q.reasoning.map(r => `<div class="reason">${r}</div>`).join('')}
    </div>`;

    html += `<div class="section"><h3>Matchups</h3>
      ${Object.entries(q.matchups).map(([k,v]) => `<div class="row"><span>${k}</span><span>${v}</span></div>`).join('')}
    </div>`;

    html += `<div class="section"><h3>Playing XI</h3>
      <div class="xi-grid">
        <div><strong style="color:#38bdf8">${m.team1}</strong><br>${q.xi1.join('<br>')}</div>
        <div><strong style="color:#38bdf8">${m.team2}</strong><br>${q.xi2.join('<br>')}</div>
      </div>
    </div>`;
  } else {
    html += `<div class="section" style="text-align:center;color:#fbbf24">
      ⏳ Awaiting toss & playing XI. Prediction will auto-refresh.
    </div>`;
  }

  view.innerHTML = html;

  // Auto-refresh if not yet post-toss
  if (m.status !== 'post') {
    setTimeout(() => openMatch(id), 30000);
  }
}

loadMatches();
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)