# Deploy Luna to Railway (multi-user, scalable)

This runs the Luna backend as a real service so **many users** can use the extension
without your PC being on. Architecture: a **web** service + a **Celery worker** service,
sharing **Postgres** and **Redis**.

```
Extension ─► web (gunicorn, N replicas) ─► Postgres
                     │                  └─► Redis (cache + memory + quota + broker)
                     └─► Celery worker (Whisper, research, LLM) ◄─ Redis
```

## 0. Before you start — rotate secrets
Your old `GEMINI_API_KEY` / `HF_API_TOKEN` were in a local `.env`. **Rotate them now**
(generate new keys) and only ever set them as Railway variables — never commit them.

## 1. Create the project
1. Push this repo to GitHub.
2. Railway → **New Project → Deploy from GitHub repo** → pick this repo.
   Railway detects `railway.json` + `Dockerfile` and builds the **web** service.
3. In the project, **+ New → Database → Postgres**, then again **→ Redis**.

## 2. Web service variables
Open the web service → **Variables** and set:

| Variable | Value |
|---|---|
| `DJANGO_DEBUG` | `false` |
| `DJANGO_SECRET_KEY` | a long random string |
| `LUNA_ENCRYPTION_KEY` | a second long random string (encrypts users' BYO keys) |
| `DATABASE_URL` | reference Postgres → `${{Postgres.DATABASE_URL}}` |
| `REDIS_URL` | reference Redis → `${{Redis.REDIS_URL}}` |
| `CELERY_BROKER_URL` | `${{Redis.REDIS_URL}}` |
| `CELERY_RESULT_BACKEND` | `django-db` |
| `HF_API_TOKEN` | your (rotated) Hugging Face token — powers the free model |
| `GROQ_API_KEY` | *(optional)* a free Groq key — faster/better free model |
| `GEMINI_API_KEY` | *(optional)* your rotated Gemini key — owner fallback |
| `FREE_LLM_DAILY_QUOTA` | `0` to start (set e.g. `40` to cap keyless users) |
| `ENABLE_WHISPER` | `false` on web (STT runs on the worker) |
| `ASSISTANT_TIMEZONE` | e.g. `Asia/Kolkata` |

Railway injects `PORT` and `RAILWAY_PUBLIC_DOMAIN` automatically — the app already
trusts them (`ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS`). Health check: `/healthz/`.

## 3. Worker service
**+ New → GitHub Repo → (same repo)** to add a second service. Then:
- Settings → **Start Command:** `bash bin/start-worker.sh`
- Give it the **same variables** as the web service (reference the same Postgres/Redis).
- Set `ENABLE_WHISPER` = `true` here only if you want server-side speech-to-text
  (needs a plan with ~1GB+ RAM; the extension mic still does client-side STT otherwise).

## 4. First login user (for the extension)
Migrations run automatically on web start. Create a login:
- Web service → **⋯ → Shell** (or `railway run`): `python manage.py createsuperuser`
- Or set `DJANGO_SUPERUSER_USERNAME` / `_EMAIL` / `_PASSWORD` and run
  `python manage.py createsuperuser --no-input` once.

## 5. Point the extension
Extension → ⚙ Settings → **Server URL** = `https://<your-web-domain>.up.railway.app`
→ Save. (Find the domain under the web service → Settings → Networking → Public Domain.)

## 6. Scale & verify
- `GET https://<domain>/healthz/` → `{"status":"ok"}`.
- Scale the **web** service replicas up when traffic grows — it's stateless
  (memory/quota live in Redis, data in Postgres), so replicas share everything.
- Keep **one** worker to start; add more for heavier Whisper/research load.

## Cost model recap
- Keyless users → free model (Groq → HF → owner Gemini), capped by `FREE_LLM_DAILY_QUOTA`.
- Users who paste their own key in Settings → their model, unlimited, zero cost to you.
- Casual chat always uses the free model, conserving everyone's key.

## Notes
- `requirements.txt` includes heavy Whisper deps (faster-whisper, ctranslate2, av). They
  only load when `ENABLE_WHISPER=true`; fine to keep in the shared image.
- For many web replicas, move `migrate` out of `start-web.sh` into a one-off deploy step.
