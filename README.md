# Aquarium — landing page

A single-page marketing site (Flask + Jinja2 + plain CSS/JS, no build step,
no frontend framework) with a working newsletter signup backed by SQLite.

## Stack

- **Backend:** Flask (Python), stdlib `sqlite3` for storage
- **Frontend:** server-rendered Jinja2 template, hand-written CSS, ~60 lines
  of vanilla JS (no npm, no bundler, no React)
- **Assets:** all imagery is hand-built inline SVG, so there are no external
  image licenses or CDNs to worry about

## Project layout

```
aquarium-site/
├── app.py                 # Flask app: routes, page content, subscribe API
├── requirements.txt
├── Procfile                # for Heroku/Railway-style platforms
├── runtime.txt              # Python version pin
├── templates/
│   └── index.html
└── static/
    ├── css/style.css
    ├── js/main.js
    └── img/*.svg           # hero art, gallery tiles, section illustrations
```

## Run it locally

Requires Python 3.10+.

```bash
cd aquarium-site
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Visit `http://localhost:5000`. The SQLite file `subscribers.db` is created
automatically on first run (in the project folder) the first time someone
subscribes.

To run it the way it'll run in production (via gunicorn, no debug reloader):

```bash
gunicorn app:app
```

## Editing content

All copy that isn't pure layout lives in `app.py` as plain Python lists/dicts
(`STATS`, `CARE_STATS`, `GALLERY`, `TESTIMONIALS`) — edit those instead of
hunting through the HTML. Gallery tiles reference SVG files named
`gallery-<slug>.svg` in `static/img/`; add a new tile by dropping in an SVG
and adding a `{"slug": ..., "name": ...}` entry.

## Receiving newsletter signups and contact messages

Every subscribe / contact submission is saved to the SQLite file
`subscribers.db` (created automatically) — that's the permanent record.
Two ways to actually see them as they come in:

### 1. Email notification on every submission
Set these environment variables before starting the app (locally, put them
in a `.env` file and load it, or export them in your shell; on a host,
use its "Environment Variables" settings screen):

```bash
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USER=you@gmail.com
export SMTP_PASS=your-16-char-app-password   # not your normal password
export NOTIFY_EMAIL=you@gmail.com            # where alerts should land
```

With Gmail, `SMTP_PASS` needs to be an
[app password](https://myaccount.google.com/apppasswords) (regular account
passwords are rejected by Google's SMTP). Any other SMTP provider (Outlook,
Zoho, SendGrid, Mailgun, your host's own mail relay) works the same way —
just point `SMTP_HOST`/`SMTP_PORT` at it.

If these variables are left unset, the app skips sending mail (and logs a
warning if sending fails) — form submissions still save to the database
either way, so nothing is ever lost even if email isn't configured.

### 1b. Phone notification by SMS
To receive a text message for every subscriber or contact enquiry, create a
Twilio account, buy or verify a Twilio phone number, and set these variables:

```bash
export TWILIO_ACCOUNT_SID=your-account-sid
export TWILIO_AUTH_TOKEN=your-auth-token
export TWILIO_FROM_NUMBER=+15551234567
export NOTIFY_PHONE=+15557654321
```

Use full international phone numbers, including the `+` country code. SMS is
optional and best-effort: if Twilio is not configured or temporarily fails,
the submission is still saved and the email notification still runs.

### 2. The `/admin` dashboard
Visit `/admin` on your deployed site (e.g. `https://yoursite.com/admin`) to
manage every subscriber and contact message. It is protected with a
username/password prompt and provides search, status filters, message
workflow states (`new`, `in_progress`, and `closed`), deletion actions, and
CSV exports for both lists. Set these credentials before deploying:

```bash
export ADMIN_USER=youradminname
export ADMIN_PASS=a-strong-password
```

If you don't set them, it falls back to `admin` / `change-me` — fine for
poking around locally, **not safe to leave as-is in production**.

### Looking at the raw data directly
You can also inspect `subscribers.db` with the `sqlite3` CLI or any SQLite
browser:

```bash
sqlite3 subscribers.db "select * from subscribers;"
sqlite3 subscribers.db "select * from messages;"
```

## Deployment

The app is a standard WSGI app (`app:app`) with no external services beyond
SQLite (a single file on disk), so it runs on any Python host. Three options:

### Option A — Render.com (free tier available, easiest)
1. Push this folder to a GitHub repo.
2. On Render: **New → Web Service**, connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Deploy. Render assigns a public URL automatically.

### Option B — Railway.app
1. `railway init` in this folder, then `railway up` (or connect the GitHub
   repo from the dashboard).
2. Railway detects the `Procfile` and `requirements.txt` automatically.
3. It sets `$PORT` for you — `app.py` already reads it via
   `os.environ.get("PORT", 5000)`.

### Option C — Any VPS (e.g. a $5 droplet) with systemd + nginx
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 app:app
```
Put nginx in front as a reverse proxy to `127.0.0.1:8000` and point your
domain's DNS at the server.

### Note on the database
SQLite is fine for a low-traffic marketing site's newsletter list. If the
host's filesystem is ephemeral (some free tiers wipe disk on redeploy),
either enable a persistent volume/disk in the platform's settings, or swap
`sqlite3` for a hosted Postgres database — the only code that would change
is `get_db()` in `app.py`.

### Environment variables to set on your host
Whichever platform you use, set these in its dashboard (Render: "Environment",
Railway: "Variables", etc.) rather than committing them to the repo:

- `ADMIN_USER`, `ADMIN_PASS` — login for `/admin` (see "Receiving newsletter
  signups and contact messages" above)
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `NOTIFY_EMAIL` —
  optional, only needed if you want email alerts on new submissions

## Notes

- No React/Vue, no Tailwind/Sass build, no Node toolchain — just Flask,
  Jinja2, CSS, and vanilla JS, so there's nothing to compile before
  deploying.
- All images are inline SVG (no external photo licensing, no broken links).
- The newsletter form works end-to-end: it posts to `/subscribe`, validates
  the email server-side, and stores it in SQLite (duplicate emails are
  handled gracefully).
