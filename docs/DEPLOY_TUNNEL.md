# Run Luna from your PC with a free Cloudflare Tunnel (no card)

This runs the backend on your machine and exposes it at a public **https://** URL
the extension can use — free, no card, no account (for a quick tunnel). Your PC
must be on for Luna to work. Bonus: Whisper (hands-free STT) runs locally.

## One-time: install cloudflared

```cmd
winget install --id Cloudflare.cloudflared
```
Close and reopen your terminal afterward so `cloudflared` is on the PATH.

## Every time: start it

**Easy way:** double-click **`run_luna.bat`** in the project root. It opens two
windows (backend + tunnel).

**Manual way (two terminals):**
```cmd
REM Terminal 1 — backend
cd C:\Scalable_Project
venv\Scripts\activate
cd luna_backend
python manage.py runserver

REM Terminal 2 — tunnel
cloudflared tunnel --url http://localhost:8000
```

The tunnel window prints a line like:
```
https://random-words-1234.trycloudflare.com
```

## Point the extension at it

1. Extension → ⚙ Settings → **Server URL** = that `https://...trycloudflare.com` URL → Save.
2. Log in (`luna` / your password).
3. Test a command. Hands-free Whisper works now because the backend is on your PC.

## Notes

- **Quick-tunnel URLs change** each time you restart cloudflared, so you'll re-paste
  the Server URL. For a **stable URL**, create a free Cloudflare account and a
  **named tunnel** (still no card) — ask and I'll walk you through it.
- **Your PC must be on and running** the backend + tunnel for Luna to work.
- Nothing here needs a card or a cloud account.
