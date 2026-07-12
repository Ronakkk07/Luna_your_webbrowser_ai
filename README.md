# Luna Browser Assistant (Chrome / Edge extension)

An Alexa/FRIDAY-style voice assistant that lives in your browser. Talk to it
hands-free to set reminders, hear the news and the time, control your tabs
(open, search, switch, close, list), play things on YouTube, answer questions,
research the live web, **highlight things on the page**, **find pages from your
history by meaning**, and answer questions about the current page.

**Design in one line:** the extension is the **ears + hands + voice**; the Django
backend (`luna_backend`) is the **brain** that turns your speech into an *action
plan* the extension executes.

**Multi-user ready.** The brain uses a **free model out of the box** (so anyone can
use it with no setup) and lets each user **bring their own API key** in Settings for
unlimited, higher-quality answers. You can run it locally behind a tunnel for testing,
or deploy it to the cloud (Railway) for many users — see
[docs/ROADMAP_SCALE.md](docs/ROADMAP_SCALE.md) and
[docs/DEPLOY_RAILWAY.md](docs/DEPLOY_RAILWAY.md).

> Deep dives: the scale/architecture plan is in
> [docs/ROADMAP_SCALE.md](docs/ROADMAP_SCALE.md), how Luna compares to a fully on-device
> assistant is in [docs/COMPARISON_GEMMA4.md](docs/COMPARISON_GEMMA4.md), and cloud
> deployment is in [docs/DEPLOY_RAILWAY.md](docs/DEPLOY_RAILWAY.md).

---

## Architecture at a glance

```
  ┌─────────────────────────── Chrome / Edge extension ───────────────────────────┐
  │                                                                                │
  │   Side panel (UI)          Background service worker         Offscreen doc     │
  │   • login / settings  ───▶  • auth + calls backend    ◀────  • Vosk WASM STT   │
  │   • conversation log       • runs action plan (tabs)         • mic capture     │
  │   • manual mic (Web        • speaks via chrome.tts           • wake-word gate   │
  │     Speech one-shot)       • daily greeting (onStartup)      (works panel-closed)│
  │                                    │                                           │
  └────────────────────────────────────┼──────────────────────────────────────────┘
                                        │ JSON over HTTPS (JWT)
                                        ▼
                        ┌────────────────────────────────────────────┐
                        │  Django backend  (the brain)                │
                        │  POST /api/assistant/command/               │
                        │  text ─▶ local intent (fast, no LLM)        │
                        │       └▶ LLM via provider layer:            │
                        │          • keyless → free model (Groq/HF)   │
                        │          • BYO key → your Gemini/OpenAI      │
                        │  router / agent ─▶ { speak, actions }       │
                        │  + reminders / shopping / news / research   │
                        │  + RAG page Q&A · semantic history · memory │
                        └────────────────────────────────────────────┘
```

The brain never hardcodes one model: `services/providers.py` routes every LLM call —
keyless users share a **free** model (subject to a daily quota), users with their own
key use it (encrypted at rest), and casual chat always uses the free model to conserve
keys. Conversation **memory** and the quota live in a cache (local in dev, Redis in
production) so the backend can scale to many instances.

---

## Prerequisites

1. Run the backend:
   ```bash
   python manage.py migrate               # creates the new UserSettings table too
   python manage.py runserver             # http://127.0.0.1:8000
   ```
   (Optional, for scheduled reminders / async voice: run Redis + `celery -A luna_backend worker -l info`.)
2. Create a login:
   ```bash
   python manage.py createsuperuser
   ```
   Environment (`.env`) — the free model works with just an `HF_API_TOKEN`. All optional:
   | Var | Purpose |
   |-----|---------|
   | `HF_API_TOKEN` | Free Hugging Face model (default free tier) |
   | `GROQ_API_KEY` | Faster/better free tier than HF (used first if set) |
   | `GEMINI_API_KEY` | Owner Gemini key — final free fallback / your own use |
   | `LUNA_ENCRYPTION_KEY` | Encrypts users' bring-your-own keys (falls back to `SECRET_KEY`) |
   | `FREE_LLM_DAILY_QUOTA` | Cap free-model calls per user (`0` = unlimited) |
   | `ENABLE_AGENT` | `true` to enable the multi-step agent (off = fast single-shot path) |
3. Fetch the offline speech assets (one-time, ~46 MB, git-ignored):
   ```bash
   python scripts/build_vosk_vendor.py
   ```
   This downloads + patches the Vosk WASM engine into `extension/vendor/` and the
   model into `extension/models/`. (See the journey doc for *why* it needs patching.)

## Load the extension

1. Open `chrome://extensions` (or `edge://extensions`) and enable **Developer mode**.
2. **Load unpacked** → select this `extension/` folder.
3. Click the Luna toolbar icon to open the side panel.
4. (⚙ Settings) confirm the Server URL is `http://127.0.0.1:8000`, then **Log in**.
5. **Microphone:** the first time you use voice, Luna opens a small permission tab
   (a Chrome side panel can't show the mic prompt itself). Click **Enable
   microphone → Allow**, close that tab, and come back.

> After changing extension files, prefer **Remove + Load unpacked** over the reload
> ↻ button. A plain reload may leave the previous **offscreen document running old
> code** (see Troubleshooting).

## Using it

- **Tap the mic** for a single command, or tick **“Always listen (offline) for
  Luna”** and just say `Luna, …` any time — even with the side panel closed.
- Try: *"open YouTube"*, *"open youtube and play lofi beats"*, *"search for weather
  in London"*, *"what time is it"*, *"give me the news"*, *"list my tabs"*, *"switch
  to the gmail tab"*, *"close this tab"*, *"summarize this page"*, *"remind me to
  call mom in 10 minutes"*, *"add milk and eggs to my shopping list"*.
- **New tools:** *"what's the refund policy on this page?"* (RAG page Q&A — pulls the
  relevant part of the page), *"highlight the total price"* (marks it and scrolls to
  it), *"find that article about GPUs I read"* (semantic search of your history — opens
  the best match), *"who won the last match?"* (live web research).
- **Interrupt her:** while Luna is speaking, say `Luna, …` again — she stops and
  takes the new command. Or click **Stop talking**.

## Always-on listening (headless, offline) & greeting

- **Listening** runs in a hidden **offscreen document** using an on-device **Vosk**
  speech engine (WebAssembly). It keeps working with the side panel **closed**.
  Nothing is uploaded — audio is transcribed locally; only the command *text* is
  sent to your backend.
- **First enable** loads the ~40 MB model (*“Loading speech model…”*), a few seconds.
- It **resumes on browser start** (if it was on and you're logged in), and Luna
  greets you by name for the time of day with a question that rotates daily —
  *"Hi Ronak, good morning… What's the plan for today?"*
- **Speaking** uses the `chrome.tts` engine from the background worker, so the
  greeting and replies work even with no page open.
- **Chrome always shows a microphone-in-use indicator** while listening. That's a
  privacy guarantee and can't be hidden — but it needs no open panel or screen space.

## Voice (⚙ Settings)

- Pick a **Voice** and adjust **Speed / Pitch**, then **Test voice**.
- The default auto-picks the most FRIDAY-like voice available — a British female
  voice (e.g. *Microsoft Sonia / Hazel* on Windows, *Google UK English Female* in
  Chrome). Edge's online "Natural" voices sound closest to FRIDAY.

## Your own AI key (⚙ Settings)

- Leave the **"Your own AI key"** field blank to use the **free model** (good enough
  for everyday tasks, subject to a daily limit).
- Or pick a provider (Gemini / Groq / OpenAI), paste your key, and **Save** for
  **unlimited, higher-quality** answers. The key is stored **encrypted** on the
  backend and is never shown again; casual chit-chat still uses the free model to
  conserve it. Use **Remove my key** to go back to the free model.

---

## Running & deploying the backend

**Local / testing (tunnel — no cloud needed):** run the backend on your PC and expose
it with a permanent ngrok tunnel, then set the extension's Server URL to the tunnel
once. `run_luna.bat` starts the backend + tunnel together. See
[docs/STABLE_URL_NGROK.md](docs/STABLE_URL_NGROK.md). Everything here — the free model,
BYO keys, new tools, conversation memory — works this way with **no Redis/Postgres**
(memory falls back to a local cache; Celery is only needed for async voice).

**Multi-user (cloud):** deploy to Railway (web + Celery worker + Postgres + Redis) so
users don't need your PC on. See [docs/DEPLOY_RAILWAY.md](docs/DEPLOY_RAILWAY.md).
Rotate any keys that were ever in a local `.env` before deploying publicly.

---

## File map

| Path | Role |
|------|------|
| `manifest.json` | MV3 config: permissions, CSP (`wasm-unsafe-eval`), web-accessible assets |
| `background.js` | Controller: auth, backend calls, action executor, `chrome.tts`, greeting, offscreen lifecycle |
| `offscreen.html/js` | Hidden page: mic capture + Vosk STT + wake-word gating |
| `sidepanel.html/js/css` | UI: login, settings, voice picker, transcript log, manual mic |
| `permission.html/js` | One-shot page to grant the microphone (side panels can't prompt) |
| `vendor/vosk.js` | Vosk loader, patched to load its worker from a packaged file |
| `vendor/vosk-worker.js` | Vosk WASM engine + model glue, patched to be **eval-free** |
| `models/model.tar.gz` | `vosk-model-small-en-us-0.15` (~40 MB, git-ignored) |

---

## Troubleshooting

- **`EvalError … 'unsafe-eval' is not an allowed source`** in `vosk-worker.js`:
  you're running **stale worker code**. Remove the extension and Load unpacked
  again. Confirm the offscreen console prints `[vosk-worker] … eval-free loaded`
  (open `chrome://extensions` → Luna → **Inspect views: offscreen.html**).
- **"Microphone is blocked"**: open the side panel and use the permission tab it
  offers; or set the mic to *Allow* for the extension in Chrome site settings.
- **No transcript when you speak**: check the offscreen console for the model-load
  logs; make sure `models/model.tar.gz` exists (run the build script).
- **Nothing happens on a command**: check the background service-worker console
  (`chrome://extensions` → Luna → **Inspect views: service worker**) and that the
  Django server is running at the configured Server URL.

## Privacy

- Audio is processed **locally** (Vosk WASM). Only the recognized command text —
  and, for “summarize this page” / page Q&A, the page's visible text — is sent to
  your own backend. No third-party speech service is used for always-on listening.
- **History search** happens on demand only: when you ask Luna to *find* a page, the
  extension gathers candidate titles/URLs from your browser history and sends them to
  your backend to rank by meaning; it isn't tracked or stored otherwise.
- **Bring-your-own API keys** are stored **encrypted** on the backend (Fernet) and are
  never returned to the client or logged.
