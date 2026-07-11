# Permanent free URL with ngrok (no card)

A quick Cloudflare tunnel changes its URL every launch. ngrok's free plan gives you
**one permanent static domain** — no credit card — so you set the extension's Server
URL once and never touch it again. (A permanent *Cloudflare* URL would need a paid
domain; ngrok's free subdomain avoids that.)

## One-time setup

1. **Sign up** (free, no card): https://dashboard.ngrok.com/signup
2. **Install ngrok:**
   ```cmd
   winget install --id ngrok.ngrok
   ```
   (Reopen the terminal afterward.)
3. **Add your authtoken** (Dashboard → *Your Authtoken*):
   ```cmd
   ngrok config add-authtoken YOUR_AUTHTOKEN
   ```
4. **Claim your free static domain:** Dashboard → **Domains** → **+ New Domain**.
   You'll get something like `luna-ronak.ngrok-free.app`. Copy it.
5. **Put your domain in `run_luna.bat`:** edit the `NGROK_DOMAIN` line near the top:
   ```
   set NGROK_DOMAIN=luna-ronak.ngrok-free.app
   ```

## Every time

Double-click **`run_luna.bat`** — it starts the backend and the tunnel on your
permanent domain.

Or manually (note: use `--domain`, not `--url`):
```cmd
ngrok http --domain=luna-ronak.ngrok-free.app 8000
```

## Point the extension (once)

Extension → ⚙ Settings → **Server URL** = `https://luna-ronak.ngrok-free.app` → Save.
Because the domain is permanent, you never have to change this again.

## Notes

- The backend already allows `*.ngrok-free.app` hosts, so no server change is needed.
- Free ngrok runs **one** tunnel at a time — fine for this.
- Your PC still needs to be on with `run_luna.bat` running.
