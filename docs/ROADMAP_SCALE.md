# Luna — Multi-user Scale Roadmap

Turning Luna from a single-PC + ngrok setup into a reliable, maintainable,
multi-user browser assistant. Decisions locked with the owner:

- **Brain / cost model:** users can **bring their own API key** (premium quality),
  and everyone else uses a **free hosted model** so keyless users still get things done.
  Casual talk always uses the free model to conserve everyone's key.
- **Host:** Railway (managed Postgres + Redis + Celery worker).
- **STT:** wake word in-browser (Vosk) + command transcription on a Celery Whisper worker.

## Why the old setup can't scale
1. Single PC + ngrok = one point of failure, must stay on.
2. Owner's Gemini key billed for every user, no quota / abuse protection.
3. Conversation memory is an in-process `deque` — lost on restart, not shared across
   instances, so you can't run more than one web process.
4. Whisper + SQLite on the web tier choke under concurrency.

## Target architecture
```
Extension ─► Load balancer ─► Django (stateless, N instances)
                                 │            │
                                 ▼            ▼
                            Postgres        Redis  (memory, cache, quota, broker)
                                 │            │
                                 └─► Celery workers (Whisper, research, LLM) ◄─┘
```
Principles: 12-factor stateless app (horizontal scale), tool-registry pattern for the
agent (open/closed — add tools without touching the loop), web tier fast / worker tier
heavy (reliability), secrets in env + rotated.

## Phased plan
| Phase | What | Status |
|---|---|---|
| 1 | **LLM provider abstraction** — BYO key + free model + per-user quota + encrypted key storage + save endpoint | in progress |
| 2 | **Redis-backed memory** — replace in-process deque so instances share context | pending |
| 3 | **Agentic tool-loop + tool registry** — brain calls tools, gets results, iterates (replaces single-shot intent→action) | pending |
| 4 | **New tools** — `highlight_element`, `find_history` (semantic), RAG `ask_website` | pending |
| 5 | **Railway deploy** — Dockerfile, Postgres + Redis + worker services, CI/CD, key rotation | pending |

## What already exists (reused, not rebuilt)
- Celery + Redis broker + `django_celery_results` (settings.py).
- Postgres via `dj_database_url` — set `DATABASE_URL` and it switches from SQLite.
- WhiteNoise static, JWT auth (`users.User`), CORS for the extension.
- Existing tab tools + web research + Whisper worker task (`process_voice_command_task`).

## Env vars (target)
```
DATABASE_URL=postgres://...            # Railway Postgres
REDIS_URL=redis://...                  # Railway Redis (cache + memory + quota)
CELERY_BROKER_URL=${REDIS_URL}
DJANGO_SECRET_KEY=...                  # rotate
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=<railway-host>
GEMINI_API_KEY=...                     # owner key (optional fallback; rotate)
GROQ_API_KEY=...                       # free-tier model for keyless users (optional)
HF_API_TOKEN=...                       # free model fallback (existing)
FREE_LLM_DAILY_QUOTA=0                 # 0 = unlimited; set >0 to cap keyless users
ENABLE_WHISPER=true                    # only on the worker service
```
