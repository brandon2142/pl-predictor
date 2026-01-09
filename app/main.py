import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeSerializer, BadSignature
from sqlalchemy import select, delete
from sqlalchemy.orm import joinedload

from .db import Base, engine, SessionLocal
from .models import Person, Fixture, Result, Prediction
from .football_data import get_pl_matches, FootballDataError
from .scoring import points

Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

APP_USERNAME = os.getenv("APP_USERNAME", "admin")
APP_PASSWORD = os.getenv("APP_PASSWORD", "changeme")
APP_SECRET   = os.getenv("APP_SECRET", "change-this-secret")

serializer = URLSafeSerializer(APP_SECRET, salt="pl-predictor-session")

def get_user(request: Request) -> str | None:
    cookie = request.cookies.get("session")
    if not cookie:
        return None
    try:
        data = serializer.loads(cookie)
        return data.get("u")
    except BadSignature:
        return None

def require_login(request: Request):
    if not get_user(request):
        return RedirectResponse("/login", status_code=302)
    return None

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    if username == APP_USERNAME and password == APP_PASSWORD:
        session = serializer.dumps({"u": username})
        resp = RedirectResponse("/", status_code=302)
        resp.set_cookie("session", session, httponly=True, samesite="lax")
        return resp
    return templates.TemplateResponse("login.html", {"request": Request, "error": "Invalid login"}, status_code=401)

@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("session")
    return resp

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    redir = require_login(request)
    if redir:
        return redir
    return templates.TemplateResponse("dashboard.html", {"request": request})

# ---- People (name list) ----
@app.get("/people", response_class=HTMLResponse)
def people_page(request: Request):
    redir = require_login(request)
    if redir:
        return redir
    with SessionLocal() as db:
        people = db.execute(select(Person).order_by(Person.name)).scalars().all()
    return templates.TemplateResponse("people.html", {"request": request, "people": people, "error": None})

@app.post("/people/add")
def people_add(request: Request, name: str = Form(...)):
    redir = require_login(request)
    if redir:
        return redir
    name = name.strip()
    with SessionLocal() as db:
        if name:
            exists = db.execute(select(Person).where(Person.name == name)).scalar_one_or_none()
            if not exists:
                db.add(Person(name=name))
                db.commit()
    return RedirectResponse("/people", status_code=302)

# ---- Fixtures sync ----
@app.get("/fixtures", response_class=HTMLResponse)
def fixtures_page(request: Request, gw: int = 1, msg: str | None = None):
    redir = require_login(request)
    if redir:
        return redir
    with SessionLocal() as db:
        fixtures = db.execute(select(Fixture).where(Fixture.gameweek == gw).order_by(Fixture.kickoff_utc)).scalars().all()
    return templates.TemplateResponse("fixtures.html", {"request": request, "gw": gw, "fixtures": fixtures, "msg": msg})

@app.post("/fixtures/sync")
async def fixtures_sync(request: Request, gw: int = Form(...)):
    redir = require_login(request)
    if redir:
        return redir
    try:
        data = await get_pl_matches(gw)
    except FootballDataError as e:
        return RedirectResponse(f"/fixtures?gw={gw}&msg={str(e)}", status_code=302)

    matches = data.get("matches", [])
    with SessionLocal() as db:
        # clear existing fixtures for gw (safe to re-sync)
        existing = db.execute(select(Fixture).where(Fixture.gameweek == gw)).scalars().all()
        for fx in existing:
            # also clear results tied to these fixtures
            db.execute(delete(Result).where(Result.fixture_id == fx.id))
        db.execute(delete(Fixture).where(Fixture.gameweek == gw))
        db.commit()

        for m in matches:
            home = m["homeTeam"]["name"]
            away = m["awayTeam"]["name"]
            kickoff = m.get("utcDate")
            api_id = m["id"]
            db.add(Fixture(gameweek=gw, api_match_id=api_id, kickoff_utc=kickoff, home=home, away=away))
        db.commit()

    return RedirectResponse(f"/fixtures?gw={gw}&msg=Fixtures synced", status_code=302)

# ---- Enter predictions ----
@app.get("/entry", response_class=HTMLResponse)
def entry_page(request: Request, gw: int = 1, person: str | None = None, msg: str | None = None):
    redir = require_login(request)
    if redir:
        return redir
    with SessionLocal() as db:
        people = [p.name for p in db.execute(select(Person).order_by(Person.name)).scalars().all()]
        fixtures = db.execute(select(Fixture).where(Fixture.gameweek == gw).order_by(Fixture.kickoff_utc)).scalars().all()

        existing = {}
        if person:
            rows = db.execute(
                select(Prediction).where(Prediction.gameweek == gw, Prediction.person_name == person)
            ).scalars().all()
            existing = {r.fixture_id: r for r in rows}

    return templates.TemplateResponse("entry.html", {
        "request": request,
        "gw": gw,
        "people": people,
        "person": person,
        "fixtures": fixtures,
        "existing": existing,
        "msg": msg
    })

@app.post("/entry/save")
def entry_save(request: Request, gw: int = Form(...), person: str = Form(...)):
    redir = require_login(request)
    if redir:
        return redir

    with SessionLocal() as db:
        # ensure person exists
        if not db.execute(select(Person).where(Person.name == person)).scalar_one_or_none():
            db.add(Person(name=person))
            db.commit()

        fixtures = db.execute(select(Fixture).where(Fixture.gameweek == gw)).scalars().all()
        # upsert each fixture prediction
        for fx in fixtures:
            ph = request._form.get(f"ph_{fx.id}")
            pa = request._form.get(f"pa_{fx.id}")
            if ph is None or pa is None or ph == "" or pa == "":
                continue
            ph_i = int(ph); pa_i = int(pa)

            existing = db.execute(
                select(Prediction).where(Prediction.fixture_id == fx.id, Prediction.person_name == person)
            ).scalar_one_or_none()

            if existing:
                existing.pred_home = ph_i
                existing.pred_away = pa_i
            else:
                db.add(Prediction(fixture_id=fx.id, gameweek=gw, person_name=person, pred_home=ph_i, pred_away=pa_i))

        db.commit()

    return RedirectResponse(f"/entry?gw={gw}&person={person}&msg=Saved", status_code=302)

# ---- Results sync ----
@app.post("/results/sync")
async def results_sync(request: Request, gw: int = Form(...)):
    redir = require_login(request)
    if redir:
        return redir
    try:
        data = await get_pl_matches(gw)
    except FootballDataError as e:
        return RedirectResponse(f"/leaderboard?gw={gw}&msg={str(e)}", status_code=302)

    matches = data.get("matches", [])
    # Build map: api_match_id -> (home, away)
    score_map = {}
    for m in matches:
        ft = (m.get("score", {}) or {}).get("fullTime", {}) or {}
        # only store if final scores exist
        if ft.get("home") is None or ft.get("away") is None:
            continue
        score_map[m["id"]] = (int(ft["home"]), int(ft["away"]))

    with SessionLocal() as db:
        fixtures = db.execute(select(Fixture).where(Fixture.gameweek == gw)).scalars().all()
        for fx in fixtures:
            if fx.api_match_id in score_map:
                h, a = score_map[fx.api_match_id]
                existing = db.execute(select(Result).where(Result.fixture_id == fx.id)).scalar_one_or_none()
                if existing:
                    existing.act_home = h
                    existing.act_away = a
                else:
                    db.add(Result(fixture_id=fx.id, act_home=h, act_away=a))
        db.commit()

    return RedirectResponse(f"/leaderboard?gw={gw}&msg=Results synced", status_code=302)

# ---- Leaderboards ----
@app.get("/leaderboard", response_class=HTMLResponse)
def leaderboard(request: Request, gw: int = 1, msg: str | None = None):
    redir = require_login(request)
    if redir:
        return redir

    with SessionLocal() as db:
        fixtures = db.execute(select(Fixture).where(Fixture.gameweek == gw)).scalars().all()
        results = {r.fixture_id: r for r in db.execute(select(Result)).scalars().all()}
        preds = db.execute(select(Prediction).where(Prediction.gameweek == gw)).scalars().all()

    # calculate totals
    totals = {}
    for p in preds:
        r = results.get(p.fixture_id)
        pts = points(p.pred_home, p.pred_away, r.act_home if r else None, r.act_away if r else None)
        if pts is None:
            continue
        totals[p.person_name] = totals.get(p.person_name, 0) + pts

    weekly = sorted(totals.items(), key=lambda x: x[1], reverse=True)

    return templates.TemplateResponse("leaderboard.html", {"request": request, "gw": gw, "weekly": weekly, "msg": msg})
