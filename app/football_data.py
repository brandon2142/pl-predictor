import os
import httpx

BASE = "https://api.football-data.org/v4"
TOKEN = os.getenv("FOOTBALL_DATA_API_KEY", "")

class FootballDataError(Exception):
    pass

async def get_pl_matches(matchday: int):
    if not TOKEN:
        raise FootballDataError("FOOTBALL_DATA_API_KEY is not set")
    url = f"{BASE}/competitions/PL/matches?matchday={matchday}"
    headers = {"X-Auth-Token": TOKEN}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, headers=headers)
        if r.status_code != 200:
            raise FootballDataError(f"football-data.org error {r.status_code}: {r.text}")
        return r.json()
