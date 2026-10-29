import httpx
import asyncio

class RealDataProvider:
    def __init__(self):
        # ⚠️ PASTE YOUR APIFY TOKEN HERE ⚠️
        self.apify_token = "https://api.apify.com/v2/webhooks?token=apify_api_xSfcYmyrvLM5wlJUG6sUOgpPn9KAoL1igA7s"
        # The Standby URL for the superapis/cricbuzz actor
        self.base_url = "https://superapis--cricbuzz.apify.actor"

    async def fetch_upcoming_matches(self):
        matches = []
        # We request the 'matches' endpoint to get all live/upcoming matches
        # No T20 filter here, so we get Test, ODI, T20, etc.
        url = f"{self.base_url}/matches?token={self.apify_token}"
        
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, timeout=30.0)
                data = resp.json()
                
                # The exact JSON structure depends on the actor's response
                # We assume it returns a list of match objects
                for m in data.get("matches", []): # Adjust key if needed
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
                        "format": match_info.get("matchFormat", "Unknown") # Store the format
                    })
            except Exception as e:
                print(f"Apify Fetch Error: {e}")
        return matches

    async def fetch_match_details(self, external_id: str):
        # Fetch the scorecard to get toss info and live score
        url = f"{self.base_url}/scorecard?matchId={external_id}&token={self.apify_token}"
        
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, timeout=30.0)
                data = resp.json()
                
                # Look for toss results in the response
                # You might need to print 'data' once to see the exact structure
                toss_info = data.get("tossResults") 
                if toss_info:
                    # Extract live score details (structure may vary)
                    score = data.get("score", [])
                    runs, wkts, overs = 0, 0, 0.0
                    if score:
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
                        "xi1": [], # Add parsing if available
                        "xi2": []
                    }
            except Exception as e:
                print(f"Apify Details Error: {e}")
        return None
