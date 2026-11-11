# Cloud Mode — Site hamesha online, processing laptop par

Architecture simple hai:

- **Cloud dashboard** (`cloud-vercel/` — Next.js) — Vercel par online, password-protected,
  **kabhi soti nahi** (serverless — Render wali 15-min sleep problem hi nahi).
  Yahan sirf queue, mode (Auto/Manual) aur settings rehte hain; data **Neon Postgres**
  me rehta hai. Koi heavy kaam yahan nahi hota.
- **Laptop worker** (`worker.py`) — jab laptop ON hota hai to ye cloud ke JSON API se
  jobs + settings (mode: auto/manual, sab config) leta hai, local backend khud start
  karta hai, pipeline chalata hai, best clips render karke YouTube par upload karta hai,
  aur result links dashboard me bhej deta hai.
- **Laptop OFF** = jobs cloud queue (Neon DB) me safe pade rehte hain. Laptop on hote
  hi worker wahin se resume kar leta hai. Kuch delete nahi hota.

> Purana Render version (`cloud/app.py`) bhi repo me hai backup ke roop me — dono ka
> API aur password/token system ek hi hai, worker.py dono par bina badle chalta hai.

## 1. Cloud dashboard deploy (Vercel + Neon, free)

**Pehle Neon DB (2 min):**
1. neon.tech → login (tumhara account pehle se hai) → **New Project** → naam `shorts-cloud`.
2. Project khulte hi **Connection string** dikhega — **Pooled connection** wala copy karo
   (`...-pooler...` wala). Ye string kisi ko bhejna nahi hai, seedha Vercel me paste hogi.

**Phir Vercel import (2 min):**
1. vercel.com → **Add New → Project** → repo `hybrid-shorts-generator` **Import**.
2. **Root Directory:** `cloud-vercel` select karo. Framework: Next.js (auto-detect hoga).
3. **Environment Variables** me do cheezein daalo:
   - `DASHBOARD_PASSWORD` = wahi password jo Render wale dashboard ka tha
     (worker ke liye bhi yahi chalega — kuch badalna nahi)
   - `DATABASE_URL` = Neon wali pooled connection string
4. **Deploy** → jo URL mile (e.g. `https://hybrid-shorts-cloud.vercel.app`) wahi site hai.
   Phone se kholo, password daalo — bas. Sleep problem khatam, hamesha turant khulegi.

## 2. Laptop worker start

WSL me, project folder me:

```bash
git pull
pip install -r requirements.txt        # YouTube upload wali libs ke liye
CLOUD_URL=https://<tumhara-vercel-url> DASHBOARD_PASSWORD=<wahi password> bash run-worker.sh
```

Worker khud:
- local backend (port 8000) down ho to start kar deta hai, Ollama bhi (agar installed ho)
- har 30 sec heartbeat bhejta hai (dashboard me "Laptop worker ONLINE" dikhega)
- queue se job uthata hai → process → top clips render → YouTube upload → dashboard update

**Laptop on hote hi auto-start (optional):** Windows me Task Scheduler →
"Create Basic Task" → Trigger: *When I log on* → Action: Start a program →
Program: `wsl.exe`, Arguments: `-d Ubuntu -- bash -lc "cd /root/video/hybrid-shorts-generator && CLOUD_URL=... DASHBOARD_PASSWORD=... bash run-worker.sh"` —
iske baad laptop on = worker on, kuch click nahi karna.

## 3. YouTube upload setup (ek baar, ~5 min)

Auto/Manual uploads ke liye YouTube Data API chahiye:

1. console.cloud.google.com → new project → **APIs & Services → Enable APIs** →
   **YouTube Data API v3** enable karo.
2. **Credentials → Create Credentials → OAuth client ID → Desktop app** →
   JSON download karo (`client_secret_....json`).
3. WSL me:
   ```bash
   python scripts/youtube_auth.py --client-secret ~/client_secret_....json
   ```
   Browser khulega — apne YouTube channel wale Google account se sign in karo, allow karo.
   Token `~/.hybrid-shorts/yt_token.json` me save hoga — **ye file kabhi share/commit mat karna.**

Quota note: free quota ~10,000 units/day, ek upload = ~1,600 units → roz ~6 uploads free.
Uploads default **unlisted** hote hain (dashboard Settings se badal sakte ho) —
pehle khud check karo, phir public karo.

## 4. Auto mode kaise kaam karta hai

Dashboard me **AUTO mode ON** karo:
- Worker har ~30 min tumhare **niches** (topics) par YouTube search karke sabse zyada
  views wale **long videos** (>= min duration) dhoondhta hai; **channels** list diye ho
  to unke naye long videos bhi leta hai.
- Jo video pehle kabhi process nahi hua, wo queue me **auto job** ban jata hai
  (roz ka cap dashboard se set hota hai, default 5).
- Phir pipeline: captions/Whisper → AI scoring → top clips → render → YouTube upload.

## ⚠️ Ek sachhi baat — copyright

Dusre creators ke trending videos ko download karke unke clips apne channel par
re-upload karna YouTube ki policy ke khilaf hai aur channel par **copyright strike**
aa sakta hai. Safe tareeqa:
- Auto mode sirf **apne khud ke channels** ya un creators ke liye use karo jinki
  permission/license hai, ya aise content par jisme tum apni commentary/value add karo.
- Upload privacy **unlisted** rakho, publish se pehle khud dekho.
