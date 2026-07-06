# Deploying Luna (extension + desktop buddy)

Luna is **one brain, two faces**:

```
                         ┌──────────────────────────────┐
                         │   Django backend = the BRAIN  │
   Chrome extension ───▶ │  intent → { speak, actions }  │ ◀─── Desktop buddy
   (browser-open,        │  Gemini key stays server-side │      (PC-boot,
    tab control)         └──────────────────────────────┘       the character)
```

Both faces call the **same** backend, so you deploy the brain once and point both
at it. The single most important rule (the lesson from apps like Clicky): **the AI
key lives on the server, never in the client.** Your Django backend already plays
that role — keep `GEMINI_API_KEY` server-side and both clients stay safe to share.

---

## 0. Host the brain (do this first for "live to other people")

For personal use you can keep running `python manage.py runserver` locally and
point both faces at `http://127.0.0.1:8000`. To make Luna usable by others, host it:

1. Deploy the Django app (Render / Railway / Fly.io / a VPS). Use Postgres, and set:
   - `DEBUG=False`
   - `DJANGO_ALLOWED_HOSTS=your-domain.com`
   - `DJANGO_SECRET_KEY=…` (new, secret)
   - `GEMINI_API_KEY=…` (server-side only)
   - `CELERY_BROKER_URL=…` if you run reminders (else it's optional)
2. Note the public URL, e.g. `https://luna-brain.example.com`.
3. Point both faces at it (extension ⚙ Settings → Server URL; buddy `config.json` → `baseUrl`).

> ⚠️ Rotate the Gemini key and `SECRET_KEY` currently in `.env` before going public,
> and make sure `.env` is git-ignored.

---

## 1. The extension — live when the browser opens

**Liveness:** once you tick **Always listen** a single time, the extension resumes
headless listening automatically on every browser start (`chrome.runtime.onStartup`).
That is your original goal — live-listening whenever Chrome is open.

**Ship it:**
- **Personal / now:** `chrome://extensions` → Developer mode → **Load unpacked** →
  `extension/`. Done. (Icons + model are already bundled.)
- **Chrome Web Store:**
  1. Zip the **contents** of `extension/` (manifest at the zip root).
  2. Create a Chrome Web Store developer account (one-time \$5) at
     https://chrome.google.com/webstore/devconsole
  3. Upload the zip, fill store listing (the 128px icon is at `icons/icon128.png`),
     submit for review (usually a few days).
  4. Note: the bundled Vosk model is ~40 MB — allowed, just a larger package.
- After publishing, set each user's **Server URL** to your hosted brain.

---

## 2. The desktop buddy — live when the PC boots

**Liveness:** when packaged, the app registers itself to **launch at login**
(`app.setLoginItemSettings({ openAtLogin: true })`, only in the packaged build), so
the character is available from the moment you turn on your PC.

**Build the installer:**
```bash
cd desktop-buddy
npm install
npm run dist          # → dist/Luna Setup 0.1.0.exe  (NSIS installer)
```
(`asar` is disabled in `package.json` so the Vosk model/vendor load correctly at
runtime — packing them inside an asar archive breaks the model fetch.)

**Config after install:** the app reads `config.json` from its **userData** folder
so it survives updates and users can edit it:
- Windows: `%APPDATA%\Luna\config.json`

Create it with:
```json
{ "baseUrl": "https://luna-brain.example.com", "username": "…", "password": "…", "userName": "Your Name" }
```
(In dev, it falls back to `desktop-buddy/config.json`.)

**Backend must be reachable** from the machine (local or hosted URL above).

**Code signing (recommended):** unsigned Windows installers trigger SmartScreen
"unknown publisher" warnings. For wide distribution, sign the `.exe` with an
Authenticode certificate (configure `win.certificateFile`/`certificatePassword` or
a signing service in electron-builder). Fine to skip for personal use.

---

## Liveness cheat-sheet

| | Extension | Desktop buddy |
|---|---|---|
| Becomes live | when **Chrome opens** (auto-resumes listening) | when the **PC boots** (launch at login) |
| Character on screen | ❌ | ✅ mini-you |
| Tab control | ✅ precise | ⚠️ opens default browser |
| Distribute via | Chrome Web Store / unpacked | NSIS `.exe` installer |
| Points at brain via | ⚙ Settings → Server URL | `config.json` → `baseUrl` |
