"""
Aquarium — a small Flask site.

Single page marketing site plus a tiny newsletter signup and contact form,
both backed by SQLite. Submissions can also trigger an email notification,
and there's a small password-protected admin page to read everything back.

Run locally with `python app.py`, or serve in production with gunicorn:
    gunicorn app:app
"""
import os
import re
import smtplib
import sqlite3
import csv
import io
import base64
from datetime import datetime, timezone
from email.message import EmailMessage
from functools import wraps
from urllib.parse import quote, urlencode
from urllib.request import Request as UrlRequest, urlopen

from flask import Flask, g, jsonify, redirect, render_template, request, Response, url_for

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "subscribers.db")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

app = Flask(__name__)

# --------------------------------------------------------------------------
# Business contact details — edit these to your real details.
# --------------------------------------------------------------------------
CONTACT_EMAIL = "afaquariumsince2000@gmail.com"
CONTACT_PHONE_DISPLAY = "+91 9445487379"  # for display only, not used in links
CONTACT_ADDRESS = "Chennai 112"
CONTACT_HOURS = "Mon–Sunday, 9am–10pm"

WHATSAPP_NUMBER = "9445487379"  # digits only, no "+" or spaces
WHATSAPP_MESSAGE = "Hi! I'd like to ask about a custom pond or aquarium build."
WHATSAPP_LINK = f"https://wa.me/{WHATSAPP_NUMBER}?text={quote(WHATSAPP_MESSAGE)}"

YOUTUBE_URL = "https://youtube.com/@aquafashion-t9h?si=VHub77ghHEp2-3Yh"  # replace with your real channel

# --------------------------------------------------------------------------
# Email notifications — all read from environment variables so no secrets
# live in the code. If SMTP_HOST/SMTP_USER/SMTP_PASS aren't set, sending is
# silently skipped (the form still saves to the database either way).
#   SMTP_HOST      e.g. smtp.gmail.com
#   SMTP_PORT      e.g. 587 (default)
#   SMTP_USER      the account that sends the notification
#   SMTP_PASS      an app password (not your normal login password)
#   NOTIFY_EMAIL   where you want new subscribers/messages sent (defaults
#                  to CONTACT_EMAIL above)
# --------------------------------------------------------------------------
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", CONTACT_EMAIL)

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")
NOTIFY_PHONE = os.environ.get("NOTIFY_PHONE", "")

# --------------------------------------------------------------------------
# Admin dashboard — protected with HTTP basic auth. Set these before you
# deploy; the fallback values below are only for local testing.
# --------------------------------------------------------------------------
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "af5944")


def send_notification(subject, body):
    """Best-effort email notification. Never raises — a broken SMTP config
    should never stop a subscribe/contact submission from succeeding."""
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS):
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = NOTIFY_EMAIL
        msg.set_content(body)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
    except Exception as exc:  # noqa: BLE001 - log and move on
        app.logger.warning("Email notification failed: %s", exc)


def send_sms_notification(body):
    """Best-effort Twilio SMS notification; never blocks a form submission."""
    if not all((TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, NOTIFY_PHONE)):
        return
    try:
        endpoint = (
            f"https://api.twilio.com/2010-04-01/Accounts/"
            f"{TWILIO_ACCOUNT_SID}/Messages.json"
        )
        credentials = base64.b64encode(
            f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}".encode()
        ).decode()
        payload = urlencode(
            {
                "To": NOTIFY_PHONE,
                "From": TWILIO_FROM_NUMBER,
                "Body": body[:1500],
            }
        ).encode()
        sms_request = UrlRequest(
            endpoint,
            data=payload,
            headers={"Authorization": f"Basic {credentials}"},
            method="POST",
        )
        with urlopen(sms_request, timeout=10):
            pass
    except Exception as exc:  # noqa: BLE001 - SMS must not stop submissions
        app.logger.warning("SMS notification failed: %s", exc)


def require_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
            return Response(
                "Authentication required.",
                401,
                {"WWW-Authenticate": 'Basic realm="Admin"'},
            )
        return view(*args, **kwargs)

    return wrapped


# --------------------------------------------------------------------------
# Database helpers
# --------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.execute(
            """
            CREATE TABLE IF NOT EXISTS subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        g.db.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        message_columns = {
            row[1] for row in g.db.execute("PRAGMA table_info(messages)").fetchall()
        }
        if "status" not in message_columns:
            g.db.execute(
                "ALTER TABLE messages ADD COLUMN status TEXT NOT NULL DEFAULT 'new'"
            )
            g.db.commit()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# --------------------------------------------------------------------------
# Page content — kept here rather than hardcoded in the template so it is
# easy to edit without touching HTML.
# --------------------------------------------------------------------------
STATS = [
    #{"value": "32", "label": "Shops"},
    {"value": "25+", "label": "Years experience"},
    {"value": "Door Delivery Available", "label": "Delivery All over India"},
]

CARE_STATS = [
    {"value": "250+", "label": "Species stocked"},
    {"value": "Door step service", "label": "Aquarist at your door step"},
    {"value": "25+", "label": "Years of tank builds"},
]

GALLERY = [
    {"slug": "whale-shark", "name": "Wall Mound Tank (With Filteration system)"},
    {"slug": "black-water", "name": "Indoor koi pond(With Filteration system)"},
    {"slug": "golden-fish", "name": "Consealding Tank(With Filteration system)"},
    {"slug": "aquarium", "name": "Japanese koi Fish"},
    {"slug": "torta-koi", "name": "10x3 Fish Tank"},
    {"slug": "jelly-fish", "name": "Natural Koi pond (With Filteration system)"},
    {"slug": "coral-whale", "name": "Fish Pond(Under construction)"},
    {"slug": "betta", "name": "Ground level underglass fish pond (With Filteration system)"},
    {"slug": "fountain", "name": "Courtyard Fountain"},
    {"slug": "external-filter", "name": "External Filter"},
    {"slug": "oscar", "name": "Fish"},
    {"slug": "pond-filter", "name": "Pond Filter"},
    {"slug": "rock-fountain", "name": "Natural Rock Fountain"},
    {"slug": "fish-package", "name": "Fish Package"},
    {"slug": "continuous-fountain", "name": "Continuous Flow Fountain"},
    {"slug": "three-fountain", "name": "Three-Tier Fountain"},
    {"slug": "algae-cutter", "name": "Algae Cutter"},
    {"slug": "smart-fish-tank", "name": "Smart Fish Tank"},
    {"slug": "pond-koi1", "name": "surrounding koi pond(With Filteration system)"},
    {"slug": "outdoor-pond", "name": "Outdoor mini Koi Pond(With Filteration system)"},
]

FULL_GALLERY_IMAGES = [
    {"image": "koi.jpeg", "name": ""},
    {"image": "koi1.jpeg", "name": ""},
    {"image": "koi3.jpeg", "name": ""},
    {"image": "blood-parrot.jpeg", "name": ""},
    {"image": "yello-parrot.jpeg", "name": ""},
    {"image": "chichled.jpeg", "name": ""},
    {"image": "flowerhorn.jpeg", "name": ""},
    {"image": "arona.jpeg", "name": ""},
    {"image": "tank-setup.jpeg", "name": ""},
    {"image": "imported-tank.jpeg", "name": ""},
    {"image": "fountain.jpeg", "name": ""},
    {"image": "imported-tank1.jpeg", "name": ""},
    {"image": "imported-tank2.jpeg", "name": ""},
    {"image": "tank-making.jpeg", "name": ""},
    {"image": "smart-tank.jpeg", "name": ""},
    {"image": "smart-tank2.jpeg", "name": ""},
]
FULL_GALLERY = [
    {**item, "name": f"{item['name']} {index // len(FULL_GALLERY_IMAGES) + 1}"}
    for index, item in enumerate(FULL_GALLERY_IMAGES)
][:30]

POND_PROJECTS = [
    {
        "image": "pond-koi.jpeg",
        "alt": "Custom backyard koi pond with stone edging and planted margins",
        "kicker": "Koi Pond",
        "title": "First floor koi fish pond(with filteration system), full build",
        "description": "Excavation, liner, sump filtration system, constructed on first floor.",
        "specs": ["1,200+ gal", "Complete filteration system"],
    },
    {
        "image": "pond-waterfall.jpeg",
        "alt": "Multi-tier natural stone waterfall feature built into a garden slope, with koi fish pond(with filteration system) at the base",
        "kicker": "Waterfall",
        "title": "Natural stone waterfall wall",
        "description": "A three-tier rock waterfall built into an existing slope, "
        "engineered so the sound carries into the patio without pump noise.",
        "specs": ["with koi fish pond", "Recirculating pump"],
    },
    {
        "image": "pond-fountain.jpeg",
        "alt": "Tiered courtyard fountain with basin lighting",
        "kicker": "Fountain",
        "title": "Tiered courtyard fountain",
        "description": "A three-tier cast basin fountain with submerged lighting and a "
        "quiet-flow pump, built to anchor a small courtyard entrance.",
        "specs": ["3-tier basin", "LED lit"],
    },
]

TESTIMONIALS = [
    {
        "quote": "They sized the filtration correctly the first time. Two years in, "
        "my existing out door fish pond.",
        "name": "Priya Nathan",
        #"role": "koi fish keeper, 3 years",
        "initials": "PN",
    },
    {
        "quote": "Setup, stocking, and a maintenance visit every month — "
        "I don't think about the setup, I just enjoy it.",
        "name": "Gokul Nath",
        #"role": "Home aquarist",
        "initials": "GN",
    },
    {
        "quote": "Our office lobby tank gets more comments than anything else in "
        "the building. Worth every visit.",
        "name": "Stephen Varghese",
        #"role": "Facilities manager",
        "initials": "SV",
    },
]


@app.route("/")
def index():
    return render_template(
        "index.html",
        stats=STATS,
        care_stats=CARE_STATS,
        pond_projects=POND_PROJECTS,
        gallery=GALLERY,
        testimonials=TESTIMONIALS,
        year=datetime.now(timezone.utc).year,
        message=None,
        contact_email=CONTACT_EMAIL,
        contact_phone=CONTACT_PHONE_DISPLAY,
        contact_address=CONTACT_ADDRESS,
        contact_hours=CONTACT_HOURS,
        whatsapp_link=WHATSAPP_LINK,
        youtube_url=YOUTUBE_URL,
    )


@app.route("/gallery")
def gallery():
    return render_template(
        "gallery.html",
        gallery=FULL_GALLERY,
        year=datetime.now(timezone.utc).year,
        contact_email=CONTACT_EMAIL,
        contact_phone=CONTACT_PHONE_DISPLAY,
        whatsapp_link=WHATSAPP_LINK,
        youtube_url=YOUTUBE_URL,
    )


@app.route("/subscribe", methods=["POST"])
def subscribe():
    data = request.get_json(silent=True) or request.form
    email = (data.get("email") or "").strip().lower()

    if not email or not EMAIL_RE.match(email):
        return jsonify({"ok": False, "error": "Enter a valid email address."}), 400

    db = get_db()
    try:
        db.execute(
            "INSERT INTO subscribers (email, created_at) VALUES (?, ?)",
            (email, datetime.now(timezone.utc).isoformat()),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"ok": True, "message": "You're already on the list."})

    send_notification(
        "New newsletter subscriber",
        f"New subscriber: {email}\nAt: {datetime.now(timezone.utc).isoformat()}",
    )
    send_sms_notification(f"New aquarium newsletter subscriber: {email}")

    return jsonify({"ok": True, "message": "You're subscribed — welcome aboard."})


@app.route("/contact", methods=["POST"])
def contact():
    data = request.get_json(silent=True) or request.form
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    text = (data.get("message") or "").strip()

    if not name:
        return jsonify({"ok": False, "error": "Enter your name."}), 400
    if not email or not EMAIL_RE.match(email):
        return jsonify({"ok": False, "error": "Enter a valid email address."}), 400
    if not text:
        return jsonify({"ok": False, "error": "Add a short message so we know how to help."}), 400

    db = get_db()
    db.execute(
        "INSERT INTO messages (name, email, phone, message, created_at) VALUES (?, ?, ?, ?, ?)",
        (name, email, phone, text, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()

    send_notification(
        f"New contact form message from {name}",
        f"Name: {name}\nEmail: {email}\nPhone: {phone or '—'}\n\nMessage:\n{text}",
    )
    send_sms_notification(
        f"New aquarium enquiry from {name} ({email}). "
        f"{text}"
    )

    return jsonify({"ok": True, "message": "Thanks — we'll get back to you within a day."})


@app.route("/admin")
@require_admin
def admin():
    db = get_db()
    query = request.args.get("q", "").strip()
    status = request.args.get("status", "all").strip().lower()
    if status not in {"all", "new", "in_progress", "closed"}:
        status = "all"

    subscribers = db.execute(
        "SELECT id, email, created_at FROM subscribers ORDER BY id DESC"
    ).fetchall()
    filters = []
    params = []
    if query:
        filters.append("(name LIKE ? OR email LIKE ? OR phone LIKE ? OR message LIKE ?)")
        params.extend([f"%{query}%"] * 4)
    if status != "all":
        filters.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    messages = db.execute(
        f"SELECT id, name, email, phone, message, created_at, status "
        f"FROM messages {where} ORDER BY id DESC",
        params,
    ).fetchall()
    message_counts = dict(
        db.execute("SELECT status, COUNT(*) FROM messages GROUP BY status").fetchall()
    )
    return render_template(
        "admin.html",
        subscribers=subscribers,
        messages=messages,
        message_counts=message_counts,
        query=query,
        status=status,
    )


@app.route("/admin/messages/<int:message_id>/status", methods=["POST"])
@require_admin
def update_message_status(message_id):
    new_status = request.form.get("status", "").strip().lower()
    if new_status not in {"new", "in_progress", "closed"}:
        return jsonify({"ok": False, "error": "Invalid message status."}), 400
    db = get_db()
    cursor = db.execute(
        "UPDATE messages SET status = ? WHERE id = ?", (new_status, message_id)
    )
    db.commit()
    if cursor.rowcount == 0:
        return jsonify({"ok": False, "error": "Message not found."}), 404
    return redirect(url_for("admin"))


@app.route("/admin/messages/<int:message_id>/delete", methods=["POST"])
@require_admin
def delete_message(message_id):
    db = get_db()
    db.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    db.commit()
    return redirect(url_for("admin"))


@app.route("/admin/subscribers/<int:subscriber_id>/delete", methods=["POST"])
@require_admin
def delete_subscriber(subscriber_id):
    db = get_db()
    db.execute("DELETE FROM subscribers WHERE id = ?", (subscriber_id,))
    db.commit()
    return redirect(url_for("admin"))


@app.route("/admin/export/<string:record_type>")
@require_admin
def export_records(record_type):
    db = get_db()
    output = io.StringIO()
    writer = csv.writer(output)
    if record_type == "messages":
        writer.writerow(["Name", "Email", "Phone", "Message", "Received", "Status"])
        rows = db.execute(
            "SELECT name, email, phone, message, created_at, status "
            "FROM messages ORDER BY id DESC"
        ).fetchall()
        filename = "aquarium-messages.csv"
    elif record_type == "subscribers":
        writer.writerow(["Email", "Subscribed"])
        rows = db.execute(
            "SELECT email, created_at FROM subscribers ORDER BY id DESC"
        ).fetchall()
        filename = "aquarium-subscribers.csv"
    else:
        return Response("Not found", status=404)
    writer.writerows(rows)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
