# Deploying the Luna backend on Render

This hosts the "brain" so the extension works from anywhere. Files added for this:
`render.yaml` (blueprint), `build.sh` (build steps), and production settings.

## 0. Push to a Git repo

Render deploys from GitHub/GitLab. Commit everything **except** secrets:
- Confirm `.env` is git-ignored (it is). **Never commit API keys.**
- Push to a repo Render can access.

## 1. Create the services (one click)

1. In Render → **New +** → **Blueprint** → select your repo.
2. Render reads `render.yaml` and proposes a **web service** (`luna-backend`) + a
   free **Postgres** (`luna-db`). Apply.
3. It will build (this takes a while the first time — big Python deps).

## 2. Set the secret env vars

In the `luna-backend` service → **Environment**, fill the ones marked `sync: false`:

| Key | Value |
|---|---|
| `GEMINI_API_KEY` | your Gemini key |
| `HF_API_TOKEN` | your Hugging Face token |
| `DJANGO_SUPERUSER_USERNAME` | e.g. `luna` (your extension login) |
| `DJANGO_SUPERUSER_EMAIL` | your email |
| `DJANGO_SUPERUSER_PASSWORD` | a strong password |

`DJANGO_SECRET_KEY`, `DATABASE_URL`, `DJANGO_DEBUG=false`, `ENABLE_WHISPER=false`,
`CELERY_TASK_ALWAYS_EAGER=true` are set for you by the blueprint. Trigger a
**Manual Deploy → Clear build cache & deploy** after adding secrets so `build.sh`
creates the login user.

## 3. Point the extension at it

Your service gets a URL like `https://luna-backend.onrender.com`.
- In the extension: ⚙ Settings → **Server URL** = that URL → Save → log in with the
  superuser credentials above.
- For a **public** store build, also change `DEFAULT_BASE_URL` in
  `extension/background.js` and `extension/sidepanel.js` to that URL before packaging.

## Reality check on features (important)

- **Works on the Starter plan:** questions (Gemini), casual chat (Hugging Face),
  web research, news, time, tab control, YouTube, page Q&A, conversation memory,
  and the **mic button** (speech-to-text runs in the browser, not the server).
- **Disabled by default:** hands-free **server transcription** (Whisper). It needs
  ~1GB+ RAM and is slow on CPU, so `ENABLE_WHISPER=false`. To turn it on: use a
  **≥2GB plan**, set `ENABLE_WHISPER=true`, and expect a few seconds per command.
  (Or later swap in a cloud STT for speed.)
- **Reminders fire immediately, not on schedule:** with `CELERY_TASK_ALWAYS_EAGER`
  there's no Redis/worker. For real scheduling, add a Render Redis + a background
  worker service (`celery -A luna_backend worker`) and set `CELERY_BROKER_URL`.
- **Free tier sleeps:** free/starter services spin down when idle, so the first
  request after a pause is slow (cold start).

## Build slimming (optional)

`requirements.txt` still includes `awsebcli` (old AWS tooling) and the Whisper
stack (`faster-whisper`, `ctranslate2`, `onnxruntime`, `av`). With
`ENABLE_WHISPER=false` those aren't loaded at runtime (Whisper is imported lazily),
so you can drop them from `requirements.txt` for much faster builds.

## Troubleshooting

- **Build fails on a package wheel:** pin `PYTHON_VERSION` to `3.12.7` (done) — some
  deps lack 3.13 wheels.
- **DisallowedHost:** Render sets `RENDER_EXTERNAL_HOSTNAME` automatically and
  settings appends it; if you use a custom domain, add it to `DJANGO_ALLOWED_HOSTS`.
- **500 on first hit:** check the service logs; usually a missing secret env var.
- **Login fails from the extension:** confirm the Server URL is the `https://` Render
  URL and the superuser env vars were set before the deploy that ran `build.sh`.
