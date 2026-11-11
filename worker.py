"""Laptop worker for the Hybrid Shorts Generator cloud queue.

Run this on the laptop (WSL). While it runs, the laptop is "online":
it heartbeats to the cloud dashboard, claims queued jobs, runs them
through the LOCAL backend (started automatically if needed), renders
the best clips and uploads them to YouTube. When the laptop is off,
jobs simply wait in the cloud queue — nothing is lost.

Usage:
    CLOUD_URL=https://<your-cloud>.onrender.com \
    DASHBOARD_PASSWORD=<same password as the dashboard> \
    python worker.py [--simulate]

--simulate skips all local processing (fake stages + fake clip links)
so the cloud wiring can be tested anywhere.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
LOCAL_API = os.environ.get("LOCAL_API", "http://127.0.0.1:8000")
OUT_DIR = os.path.join(ROOT, "cloud_outputs")
WORKER_ID = os.environ.get("WORKER_ID", "laptop-1")
POLL_SEC = int(os.environ.get("WORKER_POLL_SEC", "15"))
DISCOVERY_EVERY_MIN = int(os.environ.get("DISCOVERY_EVERY_MIN", "30"))

_stop = False
_current_job: str | None = None


# ---------------------------------------------------------------- http utils

def http_json(method: str, url: str, body: dict | None = None,
              headers: dict | None = None, timeout: int = 30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}


def worker_token() -> str:
    explicit = os.environ.get("WORKER_TOKEN")
    if explicit:
        return explicit
    pw = os.environ.get("DASHBOARD_PASSWORD", "")
    if not pw:
        print("ERROR: WORKER_TOKEN ya DASHBOARD_PASSWORD env set karo "
              "(dashboard wala hi password).")
        sys.exit(2)
    secret = hashlib.sha256(("hsg-cloud:" + pw).encode()).hexdigest()
    return hmac.new(secret.encode(), b"worker", hashlib.sha256).hexdigest()


class Cloud:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.h = {"X-Worker-Token": worker_token()}

    def heartbeat(self, info=""):
        return http_json("POST", self.base + "/api/worker/heartbeat",
                         {"worker_id": WORKER_ID, "info": info}, self.h, timeout=90)

    def claim(self):
        return http_json("POST", self.base + "/api/worker/claim",
                         {"worker_id": WORKER_ID}, self.h, timeout=90)

    def discover(self, videos):
        return http_json("POST", self.base + "/api/worker/discover",
                         {"videos": videos}, self.h, timeout=90)

    def report(self, job_id, **fields):
        fields["job_id"] = job_id
        try:
            return http_json("POST", self.base + "/api/worker/report",
                             fields, self.h, timeout=60)
        except Exception as exc:  # reporting must never kill the worker
            print(f"  [report failed: {exc}]")
            return {}


# ------------------------------------------------------------- local backend

def local_alive() -> bool:
    try:
        http_json("GET", LOCAL_API + "/health", timeout=3)
        return True
    except Exception:
        return False


def _tail(path: str, chars: int = 2500) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - chars))
            return f.read().decode("utf-8", "replace")
    except Exception:
        return "(log nahi mila)"


def ensure_local_backend():
    """Start the local FastAPI backend (and Ollama if present) when down,
    so 'laptop on = sab apne aap chalu'. Heavy model imports can take a
    while on first start — wait up to 120s before giving up."""
    if local_alive():
        return True
    print("Local backend down hai — start kar raha hu...")
    log_path = os.path.join(ROOT, "worker-backend.log")
    log = open(log_path, "ab")
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app",
         "--host", "127.0.0.1", "--port", "8000"],
        cwd=ROOT, stdout=log, stderr=log)
    if shutil.which("ollama"):
        try:
            http_json("GET", "http://127.0.0.1:11434/api/tags", timeout=2)
        except Exception:
            subprocess.Popen(["ollama", "serve"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        if local_alive():
            print("Local backend up ✓")
            return True
        time.sleep(2)
    print("WARNING: local backend start nahi hua. Log ki aakhri lines:")
    print("-" * 60)
    print(_tail(log_path))
    print("-" * 60)
    return False


def frontend_alive() -> bool:
    try:
        req = urllib.request.Request("http://127.0.0.1:3000")
        urllib.request.urlopen(req, timeout=3)
        return True
    except urllib.error.HTTPError:
        return True  # koi HTTP response aaya = server zinda hai
    except Exception:
        return False


def ensure_frontend():
    """Start the local Next.js dashboard (localhost:3000) so processing
    status local UI me bhi dikhe. Non-fatal: na chale to worker ka
    kaam nahi rukta."""
    if frontend_alive():
        return True
    fe_dir = os.path.join(ROOT, "frontend")
    if not os.path.isdir(fe_dir):
        return False
    print("Local dashboard (frontend) start kar raha hu — localhost:3000 ...")
    log = open(os.path.join(ROOT, "worker-frontend.log"), "ab")
    built = os.path.exists(os.path.join(fe_dir, ".next", "BUILD_ID"))
    cmd = ["npm", "run", "start"] if built else ["npm", "run", "dev"]
    try:
        subprocess.Popen(cmd, cwd=fe_dir, stdout=log, stderr=log)
    except Exception as exc:
        print(f"Frontend start nahi hua ({exc}) — cloud dashboard se kaam chalega")
        return False
    for _ in range(20):
        if frontend_alive():
            print("Local dashboard up ✓  →  http://localhost:3000")
            return True
        time.sleep(2)
    print("Frontend abhi tak up nahi — worker-frontend.log dekho (kaam nahi rukega)")
    return False


# ---------------------------------------------------------------- discovery

def yt_search(query: str, n: int = 12) -> list[dict]:
    try:
        out = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--flat-playlist", "-J",
             "--no-warnings", f"ytsearch{n}:{query}"],
            capture_output=True, text=True, timeout=120)
        data = json.loads(out.stdout or "{}")
        return data.get("entries") or []
    except Exception as exc:
        print(f"  [search failed '{query}': {exc}]")
        return []


def yt_channel(url: str, n: int = 20) -> list[dict]:
    url = url.strip()
    if not url:
        return []
    if "/videos" not in url and url.count("/") <= 4:
        url = url.rstrip("/") + "/videos"
    try:
        out = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--flat-playlist", "-J",
             "--playlist-items", f"1:{n}", "--no-warnings", url],
            capture_output=True, text=True, timeout=120)
        data = json.loads(out.stdout or "{}")
        return data.get("entries") or []
    except Exception as exc:
        print(f"  [channel failed {url}: {exc}]")
        return []


def run_discovery(cloud: Cloud, settings: dict):
    min_dur = int(settings.get("min_duration", "240"))
    candidates: dict[str, dict] = {}
    for line in (settings.get("niches") or "").splitlines():
        q = line.strip()
        if not q:
            continue
        for e in yt_search(q):
            vid = e.get("id")
            dur = e.get("duration") or 0
            if vid and dur >= min_dur:
                candidates[vid] = {
                    "video_id": vid,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "title": e.get("title", ""),
                    "view_count": e.get("view_count") or 0,
                    "duration": dur}
    for line in (settings.get("channels") or "").splitlines():
        for e in yt_channel(line):
            vid = e.get("id")
            dur = e.get("duration") or 0
            if vid and dur >= min_dur and vid not in candidates:
                candidates[vid] = {
                    "video_id": vid,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "title": e.get("title", ""),
                    "view_count": e.get("view_count") or 0,
                    "duration": dur}
    videos = sorted(candidates.values(),
                    key=lambda v: v["view_count"], reverse=True)[:20]
    if not videos:
        print("Discovery: koi naya long video nahi mila")
        return
    res = cloud.discover(videos)
    print(f"Discovery: {len(videos)} candidates bheje, "
          f"{res.get('enqueued', 0)} queue me gaye")


# ---------------------------------------------------------------- processing

def wait_job(jid: str, cloud: Cloud, cloud_job_id: str, label: str,
             timeout_min: int = 180) -> dict:
    deadline = time.time() + timeout_min * 60
    last_msg = ""
    while time.time() < deadline:
        job = http_json("GET", f"{LOCAL_API}/jobs/{jid}", timeout=15)
        msg = f"{job.get('stage', '')} — {job.get('message', '')}"
        if msg != last_msg:
            last_msg = msg
            cloud.report(cloud_job_id, status="processing",
                         stage=label, message=str(job.get("message", ""))[:200])
        if job.get("status") in ("done", "failed", "cancelled"):
            return job
        time.sleep(5)
    raise TimeoutError(f"{label} timeout ({timeout_min} min)")


def process_job(cloud: Cloud, job: dict, settings: dict) -> list[dict]:
    """Drive the local backend end-to-end; returns clip result dicts."""
    url = job["source_url"]
    cloud.report(job["id"], status="processing", stage="project",
                 message="local project bana raha hu")
    proj = http_json("POST", LOCAL_API + "/projects/youtube",
                     {"url": url}, timeout=60)
    pid = proj["id"]
    started = http_json("POST", f"{LOCAL_API}/projects/{pid}/process",
                        {}, timeout=30)
    done = wait_job(started["id"], cloud, job["id"], "pipeline")
    if done.get("status") != "done":
        raise RuntimeError(f"pipeline failed: {done.get('message')}")

    detail = http_json("GET", f"{LOCAL_API}/projects/{pid}", timeout=30)
    clips = sorted(detail.get("clips") or [],
                   key=lambda c: c.get("score") or 0, reverse=True)
    per = max(1, int(settings.get("clips_per_video", "3")))
    chosen = clips[:per]
    if not chosen:
        raise RuntimeError("koi clip candidate nahi mila (min score zyada ho sakta hai)")

    cloud.report(job["id"], status="processing", stage="render",
                 message=f"top {len(chosen)} clips approve + render kar raha hu")
    for c in chosen:
        http_json("PATCH", f"{LOCAL_API}/clips/{c['id']}",
                  {"status": "approved"}, timeout=15)
    rjob = http_json("POST", f"{LOCAL_API}/projects/{pid}/render", {}, timeout=30)
    rdone = wait_job(rjob["id"], cloud, job["id"], "render")
    if rdone.get("status") != "done":
        raise RuntimeError(f"render failed: {rdone.get('message')}")

    os.makedirs(OUT_DIR, exist_ok=True)
    results = []
    do_upload = bool(job.get("auto_upload"))
    privacy = settings.get("upload_privacy", "unlisted")
    for c in chosen:
        req = urllib.request.Request(
            f"{LOCAL_API}/projects/{pid}/clips/{c['id']}/download")
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = resp.read()
        name = f"{job['id']}_{c['id']}.mp4"
        path = os.path.join(OUT_DIR, name)
        with open(path, "wb") as f:
            f.write(data)
        entry = {"title": c.get("title") or "Short", "file": name,
                 "score": c.get("score"), "youtube_url": ""}
        if do_upload:
            cloud.report(job["id"], status="processing", stage="upload",
                         message=f"YouTube upload: {entry['title'][:60]}")
            try:
                from backend.upload.youtube import is_configured, upload_video
                if is_configured():
                    entry["youtube_url"] = upload_video(
                        path, entry["title"],
                        (c.get("description") or "") + "\n#Shorts",
                        privacy_status=privacy)
                else:
                    entry["note"] = ("YouTube upload setup nahi hai "
                                     "(scripts/youtube_auth.py चलाना बाकी)")
            except Exception as exc:
                entry["note"] = f"upload failed: {exc}"
        results.append(entry)
    return results


def process_simulated(cloud: Cloud, job: dict) -> list[dict]:
    for stage, msg in [("download", "simulate: video mil gaya"),
                       ("transcribe", "simulate: captions/whisper ho gaya"),
                       ("candidates", "simulate: clips score ho gaye"),
                       ("render", "simulate: render ho gaya")]:
        cloud.report(job["id"], status="processing", stage=stage, message=msg)
        time.sleep(2)
    return [{"title": "Simulated Short #1", "file": "", "score": 71,
             "youtube_url": ""},
            {"title": "Simulated Short #2", "file": "", "score": 68,
             "youtube_url": ""}]


# ------------------------------------------------------------------- main loop

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--simulate", action="store_true")
    args = ap.parse_args()

    cloud_url = os.environ.get("CLOUD_URL", "")
    if not cloud_url:
        print("ERROR: CLOUD_URL env set karo (e.g. https://xyz.onrender.com)")
        sys.exit(2)
    cloud = Cloud(cloud_url)
    print(f"Worker '{WORKER_ID}' start — cloud: {cloud_url} "
          f"({'SIMULATE' if args.simulate else 'REAL'} mode)")

    settings: dict = {}
    last_discovery = 0.0

    def heartbeat_loop():
        while not _stop:
            try:
                res = cloud.heartbeat(
                    "simulate" if args.simulate else "real")
                if res.get("settings"):
                    settings.update(res["settings"])
            except Exception as exc:
                print(f"[heartbeat fail: {exc}] (cloud so raha hoga — retry hoga)")
            time.sleep(30)

    threading.Thread(target=heartbeat_loop, daemon=True).start()

    while not _stop:
        try:
            # Backend pehle up karo — down ho to job claim hi mat karo,
            # warna achhe jobs bina wajah FAILED mark ho jayenge.
            if not args.simulate:
                if not ensure_local_backend():
                    print("Backend up nahi hua — 60s ruk kar phir try karunga "
                          "(koi job claim nahi hoga, queue safe hai)")
                    time.sleep(60)
                    continue
                ensure_frontend()

            # auto discovery (only when auto mode ON in the dashboard)
            if (settings.get("auto_enabled") == "1"
                    and time.time() - last_discovery > DISCOVERY_EVERY_MIN * 60):
                last_discovery = time.time()
                if not args.simulate:
                    run_discovery(cloud, settings)

            res = cloud.claim()
            if res.get("settings"):
                settings.update(res["settings"])
            job = res.get("job")
            if not job:
                time.sleep(POLL_SEC)
                continue
            _set_current(job["id"])
            print(f"Job mila: [{job['kind']}] {job['source_url']}")
            try:
                if args.simulate:
                    clips = process_simulated(cloud, job)
                else:
                    if not local_alive():
                        raise RuntimeError("local backend beech me band ho gaya")
                    clips = process_job(cloud, job, settings)
                uploaded = sum(1 for c in clips if c.get("youtube_url"))
                cloud.report(job["id"], status="done", stage="done",
                             message=(f"{len(clips)} clips ready"
                                      + (f", {uploaded} YouTube par upload"
                                         if uploaded else "")),
                             title=job.get("title") or clips[0]["title"] if clips else "",
                             clips=clips)
                print(f"Job done ✓ {len(clips)} clips")
            except Exception as exc:
                if not args.simulate and not local_alive():
                    # Infrastructure gira hai, job ki galti nahi —
                    # failed ki jagah wapas queue me daal do.
                    cloud.report(job["id"], status="queued", stage="waiting",
                                 message="local backend issue — auto requeue")
                    print(f"Job requeue ho gaya (backend down tha): {exc}")
                else:
                    cloud.report(job["id"], status="failed", stage="error",
                                 message=str(exc)[:300])
                    print(f"Job FAILED: {exc}")
            finally:
                _set_current(None)
        except KeyboardInterrupt:
            break
        except Exception as exc:
            print(f"[loop error: {exc}] — 20s baad retry")
            time.sleep(20)


def _set_current(jid):
    global _current_job
    _current_job = jid


if __name__ == "__main__":
    main()
