"""Cloud control plane for the Hybrid Shorts Generator.

A tiny password-protected dashboard + job queue that lives online 24x7
(Render free tier is fine — it does no heavy work). The heavy lifting
(transcription, AI scoring, rendering, YouTube upload) happens on the
user's laptop via worker.py, which polls this service:

  laptop ON  -> worker heartbeats, claims queued jobs, processes them
  laptop OFF -> jobs simply stay queued here; nothing is lost

Modes
-----
manual : the user pastes a video URL in the dashboard; it queues.
auto   : the worker periodically discovers trending long videos for the
         configured niches/channels and offers them here; unseen ones
         are enqueued automatically and processed end-to-end.

Storage: SQLite by default (fine locally); set DATABASE_URL to a
Postgres URL (e.g. Neon free) on Render so the queue survives restarts
and redeploys — Render's own disk is ephemeral.

Auth: one shared dashboard password (env DASHBOARD_PASSWORD). The
worker authenticates with a token derived from the same password
(HMAC), or an explicit WORKER_TOKEN env var on both sides.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

# --------------------------------------------------------------------------
# config / auth primitives
# --------------------------------------------------------------------------

PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")
if not PASSWORD:
    PASSWORD = "shorts123"
    print("WARNING: DASHBOARD_PASSWORD not set — using default 'shorts123'. "
          "Set it in the service environment!")

SECRET_HEX = hashlib.sha256(("hsg-cloud:" + PASSWORD).encode()).hexdigest()
SESSION_TOKEN = hmac.new(SECRET_HEX.encode(), b"session", hashlib.sha256).hexdigest()
WORKER_TOKEN = os.environ.get("WORKER_TOKEN") or hmac.new(
    SECRET_HEX.encode(), b"worker", hashlib.sha256).hexdigest()

STALE_SECONDS = 600          # claimed job with no update for 10 min -> requeue
WORKER_ONLINE_SECONDS = 120  # heartbeat fresher than this = worker online

DEFAULT_SETTINGS: dict[str, str] = {
    "auto_enabled": "0",
    "niches": "funny storytelling podcast\nmotivation speech hindi\ntech explained",
    "channels": "",
    "clips_per_video": "3",
    "upload_privacy": "unlisted",
    "min_duration": "240",
    "daily_auto_cap": "5",
    "upload_schedule_enabled": "0",
    "upload_times": "10:00,15:00,20:00",
    "daily_upload_limit": "3",
}

# --------------------------------------------------------------------------
# storage layer (sqlite3 locally, Postgres via DATABASE_URL)
# --------------------------------------------------------------------------

DATABASE_URL = os.environ.get("DATABASE_URL", "")
_pg = None
if DATABASE_URL.startswith("postgres"):
    try:
        import psycopg  # type: ignore

        _pg = psycopg
    except Exception:  # pragma: no cover
        print("WARNING: DATABASE_URL is Postgres but psycopg is not installed; "
              "falling back to SQLite.")

DATA_DIR = os.environ.get("CLOUD_DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
os.makedirs(DATA_DIR, exist_ok=True)
SQLITE_PATH = os.path.join(DATA_DIR, "cloud.db")

_lock = threading.Lock()

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)""",
    """CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY, kind TEXT, source_url TEXT, title TEXT,
        status TEXT, stage TEXT, message TEXT, clips TEXT,
        auto_upload INTEGER, created_at REAL, updated_at REAL,
        claimed_by TEXT, video_id TEXT)""",
    """CREATE TABLE IF NOT EXISTS seen (
        video_id TEXT PRIMARY KEY, title TEXT, at REAL)""",
    """CREATE TABLE IF NOT EXISTS workers (
        id TEXT PRIMARY KEY, last_seen REAL, info TEXT)""",
]


@contextmanager
def db():
    if _pg is not None:
        conn = _pg.connect(DATABASE_URL)
        try:
            yield _PgConn(conn)
            conn.commit()
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield _SqConn(conn)
            conn.commit()
        finally:
            conn.close()


class _SqConn:
    def __init__(self, conn):
        self.c = conn

    def execute(self, sql, params=()):
        cur = self.c.execute(sql, params)
        return cur

    def fetchone(self, sql, params=()):
        row = self.c.execute(sql, params).fetchone()
        return dict(row) if row else None

    def fetchall(self, sql, params=()):
        return [dict(r) for r in self.c.execute(sql, params).fetchall()]


class _PgConn:
    def __init__(self, conn):
        self.c = conn

    def _t(self, sql):  # qmark -> psycopg placeholder
        return sql.replace("?", "%s")

    def execute(self, sql, params=()):
        return self.c.execute(self._t(sql), params)

    def fetchone(self, sql, params=()):
        cur = self.c.execute(self._t(sql), params)
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d.name for d in cur.description]
        return dict(zip(cols, row))

    def fetchall(self, sql, params=()):
        cur = self.c.execute(self._t(sql), params)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def init_db():
    with db() as d:
        for stmt in SCHEMA:
            d.execute(stmt)
        for k, v in DEFAULT_SETTINGS.items():
            row = d.fetchone("SELECT v FROM kv WHERE k=?", (k,))
            if row is None:
                d.execute("INSERT INTO kv (k, v) VALUES (?, ?)", (k, v))


def get_settings(d) -> dict[str, str]:
    out = dict(DEFAULT_SETTINGS)
    for row in d.fetchall("SELECT k, v FROM kv"):
        out[row["k"]] = row["v"]
    return out


def _job_out(row: dict) -> dict:
    row = dict(row)
    try:
        row["clips"] = json.loads(row.get("clips") or "[]")
    except Exception:
        row["clips"] = []
    row["auto_upload"] = bool(row.get("auto_upload"))
    return row


def _requeue_stale(d):
    cutoff = time.time() - STALE_SECONDS
    d.execute(
        "UPDATE jobs SET status='queued', claimed_by=NULL, stage='waiting', "
        "message='worker offline — queue me wapas' "
        "WHERE status IN ('claimed','processing') AND updated_at < ?",
        (cutoff,))


# --------------------------------------------------------------------------
# app
# --------------------------------------------------------------------------

app = FastAPI(title="Hybrid Shorts — Cloud")
init_db()


def _authed(request: Request) -> bool:
    return request.cookies.get("hsg_session") == SESSION_TOKEN


def _worker_ok(request: Request) -> bool:
    return request.headers.get("x-worker-token") == WORKER_TOKEN or _authed(request)


def _need_auth(request: Request):
    if not _authed(request):
        raise HTTPException(401, "login required")


def _need_worker(request: Request):
    if not _worker_ok(request):
        raise HTTPException(401, "bad worker token")


@app.get("/health")
def health():
    return {"ok": True, "service": "hybrid-shorts-cloud", "time": time.time()}


# --------------------------------------------------------------- dashboard

LOGIN_HTML = """<!doctype html><meta charset="utf-8"><title>Shorts Cloud — Login</title>
<body style="background:#0b0e14;color:#e6e6e6;font-family:system-ui;display:flex;
align-items:center;justify-content:center;height:100vh;margin:0">
<form method="post" action="/login" style="background:#141926;padding:28px;border-radius:14px;width:300px">
<h2 style="margin:0 0 6px">🎬 Shorts Cloud</h2>
<p style="color:#8b93a7;font-size:13px;margin:0 0 16px">Sirf tumhare liye — password daalo</p>
<input type="password" name="password" placeholder="Password" autofocus
 style="width:100%;padding:10px;border-radius:8px;border:1px solid #2a3247;background:#0b0e14;color:#fff;box-sizing:border-box">
<button style="width:100%;margin-top:12px;padding:10px;border:0;border-radius:8px;
background:#e5484d;color:#fff;font-weight:600;cursor:pointer">Login</button>
<p style="color:#e5484d;font-size:12px">{error}</p></form></body>"""


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return LOGIN_HTML.replace("{error}", "")


@app.post("/login")
async def login(request: Request):
    form = await request.form()
    if hmac.compare_digest(str(form.get("password", "")), PASSWORD):
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie("hsg_session", SESSION_TOKEN, max_age=60 * 60 * 24 * 30,
                        httponly=True, samesite="lax")
        return resp
    return HTMLResponse(LOGIN_HTML.replace("{error}", "Galat password — phir try karo"),
                        status_code=401)


@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie("hsg_session")
    return resp


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    if not _authed(request):
        return RedirectResponse("/login", status_code=303)
    return DASHBOARD_HTML


# --------------------------------------------------------------- user APIs

@app.get("/api/state")
def state(request: Request):
    _need_auth(request)
    with _lock, db() as d:
        _requeue_stale(d)
        settings = get_settings(d)
        jobs = [_job_out(r) for r in d.fetchall(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT 100")]
        workers = d.fetchall("SELECT * FROM workers ORDER BY last_seen DESC")
    now = time.time()
    worker_online = any(now - (w["last_seen"] or 0) < WORKER_ONLINE_SECONDS for w in workers)
    return {"settings": settings, "jobs": jobs,
            "worker_online": worker_online,
            "workers": [{"id": w["id"], "last_seen": w["last_seen"],
                         "ago_sec": round(now - (w["last_seen"] or now))} for w in workers]}


@app.post("/api/settings")
async def save_settings(request: Request):
    _need_auth(request)
    body = await request.json()
    with _lock, db() as d:
        for k, v in body.items():
            if k in DEFAULT_SETTINGS:
                d.execute("INSERT INTO kv (k, v) VALUES (?, ?) "
                          "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))
    return {"ok": True}


@app.post("/api/jobs")
async def add_job(request: Request):
    _need_auth(request)
    body = await request.json()
    url = str(body.get("url", "")).strip()
    if not url:
        raise HTTPException(400, "url required")
    jid = secrets.token_hex(6)
    now = time.time()
    with _lock, db() as d:
        d.execute(
            "INSERT INTO jobs (id, kind, source_url, title, status, stage, message,"
            " clips, auto_upload, created_at, updated_at, claimed_by, video_id)"
            " VALUES (?, 'manual', ?, '', 'queued', 'waiting', '', '[]', ?, ?, ?, NULL, '')",
            (jid, url, 1 if body.get("auto_upload") else 0, now, now))
    return {"ok": True, "id": jid}


@app.post("/api/jobs/{jid}/{action}")
def job_action(jid: str, action: str, request: Request):
    _need_auth(request)
    with _lock, db() as d:
        if action == "cancel":
            d.execute("UPDATE jobs SET status='cancelled', updated_at=? WHERE id=?",
                      (time.time(), jid))
        elif action == "retry":
            d.execute("UPDATE jobs SET status='queued', claimed_by=NULL, stage='waiting',"
                      " message='', updated_at=? WHERE id=?", (time.time(), jid))
        elif action == "delete":
            d.execute("DELETE FROM jobs WHERE id=?", (jid,))
        else:
            raise HTTPException(404, "unknown action")
    return {"ok": True}


# --------------------------------------------------------------- worker APIs

@app.post("/api/worker/heartbeat")
async def heartbeat(request: Request):
    _need_worker(request)
    body = await request.json()
    wid = str(body.get("worker_id", "laptop"))
    with _lock, db() as d:
        d.execute("INSERT INTO workers (id, last_seen, info) VALUES (?, ?, ?) "
                  "ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen,"
                  " info=excluded.info",
                  (wid, time.time(), str(body.get("info", ""))[:200]))
        settings = get_settings(d)
    return {"ok": True, "settings": settings}


@app.post("/api/worker/claim")
async def claim(request: Request):
    _need_worker(request)
    body = await request.json()
    wid = str(body.get("worker_id", "laptop"))
    with _lock, db() as d:
        _requeue_stale(d)
        row = d.fetchone(
            "SELECT * FROM jobs WHERE status='queued' "
            "ORDER BY (kind='manual') DESC, created_at ASC LIMIT 1")
        settings = get_settings(d)
        if not row:
            return {"job": None, "settings": settings}
        now = time.time()
        d.execute("UPDATE jobs SET status='claimed', claimed_by=?, stage='claimed',"
                  " updated_at=? WHERE id=?", (wid, now, row["id"]))
        row = d.fetchone("SELECT * FROM jobs WHERE id=?", (row["id"],))
    return {"job": _job_out(row), "settings": settings}


@app.post("/api/worker/discover")
async def discover(request: Request):
    """Worker offers candidate trending videos; unseen ones enqueue as
    auto jobs up to the daily cap. Returns how many were enqueued."""
    _need_worker(request)
    body = await request.json()
    videos = body.get("videos") or []
    enqueued = 0
    with _lock, db() as d:
        settings = get_settings(d)
        if settings.get("auto_enabled") != "1":
            return {"enqueued": 0, "reason": "auto mode off"}
        cap = int(settings.get("daily_auto_cap", "5"))
        today = time.strftime("%Y-%m-%d")
        rows = d.fetchall("SELECT created_at FROM jobs WHERE kind='auto'")
        made_today = sum(1 for r in rows
                         if time.strftime("%Y-%m-%d", time.localtime(r["created_at"])) == today)
        for v in videos:
            if made_today + enqueued >= cap:
                break
            vid = str(v.get("video_id", "")).strip()
            url = str(v.get("url", "")).strip()
            if not vid or not url:
                continue
            if d.fetchone("SELECT video_id FROM seen WHERE video_id=?", (vid,)):
                continue
            d.execute("INSERT INTO seen (video_id, title, at) VALUES (?, ?, ?)",
                      (vid, str(v.get("title", ""))[:200], time.time()))
            jid = secrets.token_hex(6)
            now = time.time()
            d.execute(
                "INSERT INTO jobs (id, kind, source_url, title, status, stage, message,"
                " clips, auto_upload, created_at, updated_at, claimed_by, video_id)"
                " VALUES (?, 'auto', ?, ?, 'queued', 'waiting',"
                " 'auto-discovered (trending)', '[]', 1, ?, ?, NULL, ?)",
                (jid, url, str(v.get("title", ""))[:200], now, now, vid))
            enqueued += 1
    return {"enqueued": enqueued}


@app.get("/api/worker/uploads/pending")
def uploads_pending(request: Request):
    """Render ho chuki clips jo scheduled upload ka wait kar rahi hain,
    + aaj kitni upload ho chuki (daily limit ke liye)."""
    _need_worker(request)
    pending = []
    uploaded_today = 0
    today = time.strftime("%Y-%m-%d", time.gmtime())
    with _lock, db() as d:
        rows = d.fetchall("SELECT * FROM jobs ORDER BY created_at ASC")
    for r in rows:
        try:
            clips = json.loads(r.get("clips") or "[]")
        except Exception:
            clips = []
        for c in clips:
            if c.get("upload_status") == "pending":
                pending.append({"job_id": r["id"], "job_title": r.get("title"),
                                "clip": c, "job_clips": clips})
            ua = c.get("uploaded_at")
            if ua and time.strftime("%Y-%m-%d", time.gmtime(ua)) == today:
                uploaded_today += 1
    return {"pending": pending, "uploaded_today": uploaded_today}


@app.post("/api/worker/report")
async def report(request: Request):
    _need_worker(request)
    body = await request.json()
    jid = str(body.get("job_id", ""))
    if not jid:
        raise HTTPException(400, "job_id required")
    fields = {"updated_at": time.time()}
    for k in ("status", "stage", "message", "title"):
        if k in body:
            fields[k] = str(body[k])[:500]
    if "clips" in body:
        fields["clips"] = json.dumps(body["clips"])[:20000]
    sets = ", ".join(f"{k}=?" for k in fields)
    with _lock, db() as d:
        d.execute(f"UPDATE jobs SET {sets} WHERE id=?",
                  (*fields.values(), jid))
    return {"ok": True}


# --------------------------------------------------------------- dashboard UI

DASHBOARD_HTML = r"""<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Shorts Cloud — Dashboard</title>
<style>
body{background:#0b0e14;color:#e6e6e6;font-family:system-ui;margin:0;padding:16px;max-width:860px;margin:auto}
.card{background:#141926;border:1px solid #232b3f;border-radius:14px;padding:16px;margin:14px 0}
h1{font-size:20px;margin:4px 0} h3{margin:0 0 10px}
input,textarea,select{background:#0b0e14;color:#fff;border:1px solid #2a3247;border-radius:8px;padding:9px;width:100%;box-sizing:border-box;margin:4px 0}
button{background:#e5484d;color:#fff;border:0;border-radius:8px;padding:9px 14px;font-weight:600;cursor:pointer}
button.ghost{background:#232b3f} button.sm{padding:4px 9px;font-size:12px}
.chip{padding:2px 9px;border-radius:99px;font-size:11px;font-weight:700}
.q{background:#3a3f2a;color:#d7e08a}.p{background:#2a3a5f;color:#9ec1ff}.d{background:#23402c;color:#8ae0a3}.f{background:#5f2a2a;color:#ff9e9e}.c{background:#333;color:#aaa}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;vertical-align:middle}
.on{background:#3fb950}.off{background:#e5484d}
.job{border-top:1px solid #232b3f;padding:10px 0}.job:first-of-type{border-top:0}
a{color:#9ec1ff} small{color:#8b93a7} label{font-size:13px;color:#c6cbda}
.switch{transform:scale(1.5);margin-right:10px;vertical-align:middle}
.row{display:flex;gap:10px;flex-wrap:wrap}.row>*{flex:1;min-width:140px}
</style>
<h1>🎬 Shorts Cloud <small id="wstat"></small></h1>
<small>Phone se control karo — processing tumhare laptop par hoti hai jab wo on ho.
Laptop off = jobs queue me safe rehte hain.</small>

<div class="card"><h3>🤖 Mode</h3>
<label><input type="checkbox" class="switch" id="auto_enabled"> <b>AUTO mode</b> —
trending long videos khud dhoondhe, clips banaye, YouTube par upload kare</label>
<div class="row" style="margin-top:10px">
<div><label>Niches (ek line = ek topic)</label><textarea id="niches" rows="3"></textarea></div>
<div><label>Channels (URLs, ek line = ek — optional)</label><textarea id="channels" rows="3"></textarea></div>
</div>
<div class="row">
<div><label>Clips per video</label><input id="clips_per_video" type="number" min="1" max="10"></div>
<div><label>Min video length (sec)</label><input id="min_duration" type="number" min="60"></div>
<div><label>Auto jobs per day (cap)</label><input id="daily_auto_cap" type="number" min="1" max="50"></div>
<div><label>Upload privacy</label><select id="upload_privacy">
<option value="unlisted">unlisted (pehle check karne ke liye best)</option>
<option value="public">public</option><option value="private">private</option></select></div>
</div>
<button onclick="saveSettings()">Settings save karo</button> <small id="saved"></small>
<div style="border-top:1px solid #232b3f;margin-top:12px;padding-top:10px">
<label><input type="checkbox" class="switch" id="upload_schedule_enabled"> <b>📅 Upload schedule</b> —
bani hui clips turant nahi, set time par upload hon</label>
<div class="row" style="margin-top:8px">
<div><label>Upload times (har time par 1 clip)</label><input id="upload_times" placeholder="10:00,15:00,20:00"></div>
<div><label>Roz kitni uploads (limit)</label><input id="daily_upload_limit" type="number" min="1" max="20"></div>
</div>
<small>YouTube API free quota roz ~6 uploads hai. Laptop us time on hona chahiye,
warna on hote hi due uploads ek-ek karke jayengi.</small></div>
</div>

<div class="card"><h3>✋ Manual mode — video add karo</h3>
<input id="murl" placeholder="YouTube video URL paste karo">
<label><input type="checkbox" id="mupload" checked style="width:auto"> Render ke baad YouTube par upload bhi kar de</label><br>
<button onclick="addJob()">Queue me daalo</button>
<small>Laptop on hoga to worker ise khud utha lega.</small></div>

<div class="card"><h3>📋 Queue / Jobs</h3><div id="jobs"></div></div>
<p><a href="/logout">Logout</a></p>

<script>
const $=id=>document.getElementById(id);
async function api(p,o){const r=await fetch(p,o);if(!r.ok)throw new Error(await r.text());return r.json()}
async function refresh(){
 const s=await api('/api/state');
 const w=$('wstat'); w.innerHTML=(s.worker_online?'<span class="dot on"></span> Laptop worker ONLINE':'<span class="dot off"></span> Laptop worker offline — jobs queue me safe hain');
 const st=s.settings;
 if(document.activeElement.tagName!=='TEXTAREA'&&document.activeElement.tagName!=='INPUT'){
   $('auto_enabled').checked=st.auto_enabled==='1'; $('niches').value=st.niches||'';
   $('channels').value=st.channels||''; $('clips_per_video').value=st.clips_per_video;
   $('min_duration').value=st.min_duration; $('daily_auto_cap').value=st.daily_auto_cap;
   $('upload_privacy').value=st.upload_privacy;
   $('upload_schedule_enabled').checked=st.upload_schedule_enabled==='1';
   $('upload_times').value=st.upload_times||''; $('daily_upload_limit').value=st.daily_upload_limit;}
 const chip={queued:'<span class="chip q">QUEUED</span>',claimed:'<span class="chip p">CLAIMED</span>',
  processing:'<span class="chip p">PROCESSING</span>',done:'<span class="chip d">DONE</span>',
  failed:'<span class="chip f">FAILED</span>',cancelled:'<span class="chip c">CANCELLED</span>'};
 $('jobs').innerHTML=s.jobs.length?s.jobs.map(j=>`<div class="job">
  ${chip[j.status]||j.status} <b>${j.kind==='auto'?'🤖 AUTO':'✋ MANUAL'}</b>
  <a href="${j.source_url}" target="_blank">${(j.title||j.source_url).slice(0,80)}</a><br>
  <small>${j.stage||''} ${j.message?'— '+j.message:''}</small>
  ${(j.clips||[]).map(c=>`<br>🎬 ${c.title||'clip'} ${c.youtube_url?`— <a href="${c.youtube_url}" target="_blank">YouTube par dekho</a>`:c.upload_status==='pending'?'— ⏳ upload scheduled':''}`).join('')}
  <br><button class="sm ghost" onclick="act('${j.id}','retry')">Retry</button>
  <button class="sm ghost" onclick="act('${j.id}','cancel')">Cancel</button>
  <button class="sm ghost" onclick="act('${j.id}','delete')">Delete</button></div>`).join('')
  :'<small>Abhi koi job nahi hai.</small>';
}
async function saveSettings(){
 await api('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
  auto_enabled:$('auto_enabled').checked?'1':'0',niches:$('niches').value,channels:$('channels').value,
  clips_per_video:$('clips_per_video').value,min_duration:$('min_duration').value,
  daily_auto_cap:$('daily_auto_cap').value,upload_privacy:$('upload_privacy').value,
  upload_schedule_enabled:$('upload_schedule_enabled').checked?'1':'0',
  upload_times:$('upload_times').value,daily_upload_limit:$('daily_upload_limit').value})});
 $('saved').textContent='Saved ✓'; setTimeout(()=>$('saved').textContent='',2000);}
async function addJob(){
 const url=$('murl').value.trim(); if(!url)return alert('URL daalo pehle');
 await api('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({url,auto_upload:$('mupload').checked})});
 $('murl').value=''; refresh();}
async function act(id,a){await api(`/api/jobs/${id}/${a}`,{method:'POST'});refresh();}
refresh(); setInterval(refresh,5000);
</script>"""
