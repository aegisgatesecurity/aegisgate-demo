#!/usr/bin/env python3
"""
AegisGate Demo - Daily Email Digest
====================================

Sends a daily summary of new signups via the Resend HTTPS API
(not SMTP — Resend's HTTPS API works on Render's free tier because
it goes out on port 443, which Render allows. SMTP ports 25/465/587
are blocked by Render on free tier).

This script is called by cron once a day (see entrypoint.sh). It:
  1. Reads /data/signups/emails.csv
  2. Filters to signups since the last successful send (or 24h)
  3. Formats an HTML table of new signups
  4. POSTs to Resend's /emails endpoint
  5. Records a timestamp so we don't re-send

Env vars (set these in Render's Environment tab):
  AEGISGATE_RESEND_API_KEY    - Resend API key (re_...)
  AEGISGATE_DIGEST_TO_EMAIL   - Where to send the digest (you@yourdomain)
  AEGISGATE_DIGEST_FROM_EMAIL - From address (must be on a verified domain)
  AEGISGATE_DIGEST_ENABLED    - "true" to enable, "false" to skip
  AEGISGATE_DIGEST_HOUR       - Hour of day to send (0-23 UTC), default 9

Usage:
  python3 send_daily_digest.py             # send today's digest
  python3 send_daily_digest.py --dry-run   # print what would be sent
  python3 send_daily_digest.py --hours 48  # send last 48h (override 24)
"""

import argparse
import csv
import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ============================================
# Configuration
# ============================================
DATA_DIR = os.environ.get("AEGISGATE_DEMO_DATA_DIR", "/data")
EMAIL_FILE = os.path.join(DATA_DIR, "signups", "emails.csv")
STATE_FILE = os.path.join(DATA_DIR, "signups", "digest_state.json")
LOG_FILE = os.path.join(DATA_DIR, "signups", "digest.log")

RESEND_API_KEY = os.environ.get("AEGISGATE_RESEND_API_KEY", "")
RESEND_URL = "https://api.resend.com/emails"
DIGEST_TO = os.environ.get("AEGISGATE_DIGEST_TO_EMAIL", "security@aegisgatesecurity.io")
DIGEST_FROM = os.environ.get("AEGISGATE_DIGEST_FROM_EMAIL", "AegisGate Demo <onresend.dev>")
DIGEST_ENABLED = os.environ.get("AEGISGATE_DIGEST_ENABLED", "false").lower() == "true"


def log(msg):
    """Log with timestamp to both stdout and the log file."""
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def read_signups(since):
    """Read signups from CSV that occurred after `since` (datetime)."""
    if not os.path.exists(EMAIL_FILE):
        return []

    signups = []
    try:
        with open(EMAIL_FILE, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ts = datetime.datetime.fromisoformat(row["timestamp"].rstrip("Z"))
                    if ts >= since:
                        signups.append({
                            "timestamp": row["timestamp"],
                            "email": row["email"],
                            "email_hash": row.get("email_hash", ""),
                            "ip_address": row.get("ip_address", ""),
                            "user_agent": row.get("user_agent", ""),
                        })
                except (ValueError, KeyError):
                    continue
    except Exception as e:
        log(f"ERROR reading signups CSV: {e}")

    return signups


def read_last_sent():
    """Read the timestamp of the last successful digest send."""
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
            ts_str = state.get("last_sent")
            if ts_str:
                return datetime.datetime.fromisoformat(ts_str.rstrip("Z"))
    except Exception as e:
        log(f"WARNING: Could not read state file: {e}")
    return None


def write_last_sent(ts):
    """Persist the timestamp of the last successful send."""
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump({"last_sent": ts.isoformat() + "Z"}, f)
    except Exception as e:
        log(f"WARNING: Could not write state file: {e}")


def format_digest_html(signups, since):
    """Format the signups as an HTML email body."""
    rows = ""
    for s in signups:
        # Truncate user agent for readability
        ua = s["user_agent"]
        if len(ua) > 60:
            ua = ua[:57] + "..."
        # Truncate email for readability in the digest
        email_display = s["email"]
        if len(email_display) > 40:
            email_display = email_display[:37] + "..."
        # HTML-escape all fields
        from html import escape
        rows += f"""
        <tr>
            <td style="padding: 8px; border-bottom: 1px solid #2a2f3a; color: #94a3b8;">{escape(s['timestamp'])}</td>
            <td style="padding: 8px; border-bottom: 1px solid #2a2f3a; color: #f8fafc;">{escape(email_display)}</td>
            <td style="padding: 8px; border-bottom: 1px solid #2a2f3a; color: #64748b; font-family: monospace; font-size: 12px;">{escape(s['ip_address'])}</td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="background: #0a0c10; color: #f8fafc; font-family: -apple-system, system-ui, sans-serif; padding: 20px;">
    <div style="max-width: 800px; margin: 0 auto; background: #161b22; border: 1px solid #2a2f3a; border-radius: 12px; overflow: hidden;">
        <div style="background: linear-gradient(135deg, #38bdf8 0%, #10b981 100%); padding: 24px;">
            <h1 style="margin: 0; color: #0a0c10; font-size: 24px;">🛡️ AegisGate Demo — Daily Digest</h1>
            <p style="margin: 8px 0 0 0; color: #0a0c10; opacity: 0.8; font-size: 14px;">
                {len(signups)} new signup{"s" if len(signups) != 1 else ""} since {since.isoformat()}Z
            </p>
        </div>
        <div style="padding: 24px;">
            {f'''
            <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                <thead>
                    <tr style="background: #1f2937;">
                        <th style="padding: 12px 8px; text-align: left; color: #38bdf8; border-bottom: 2px solid #38bdf8;">Timestamp (UTC)</th>
                        <th style="padding: 12px 8px; text-align: left; color: #38bdf8; border-bottom: 2px solid #38bdf8;">Email</th>
                        <th style="padding: 12px 8px; text-align: left; color: #38bdf8; border-bottom: 2px solid #38bdf8;">IP</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
            ''' if signups else '<p style="color: #94a3b8; text-align: center; padding: 32px 0;">No new signups in the last 24 hours.</p>'}
        </div>
        <div style="background: #0a0c10; padding: 16px 24px; border-top: 1px solid #2a2f3a; font-size: 12px; color: #64748b;">
            Sent by <code style="color: #10b981;">send_daily_digest.py</code> from the AegisGate demo container.
            Total signups: {count_total_signups()}
        </div>
    </div>
</body>
</html>"""


def count_total_signups():
    """Count total signups in the CSV (for the footer)."""
    if not os.path.exists(EMAIL_FILE):
        return 0
    try:
        with open(EMAIL_FILE, "r") as f:
            return sum(1 for _ in f) - 1  # subtract header
    except Exception:
        return 0


def send_via_resend(subject, html_body, dry_run=False):
    """Send an email via Resend's HTTPS API."""
    if dry_run:
        log(f"[DRY RUN] Would send email:")
        log(f"  From:    {DIGEST_FROM}")
        log(f"  To:      {DIGEST_TO}")
        log(f"  Subject: {subject}")
        log(f"  HTML length: {len(html_body)} chars")
        return True

    if not RESEND_API_KEY:
        log("ERROR: AEGISGATE_RESEND_API_KEY is not set")
        return False

    payload = {
        "from": DIGEST_FROM,
        "to": [DIGEST_TO],
        "subject": subject,
        "html": html_body,
    }

    try:
        req = urllib.request.Request(
            RESEND_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
                "User-Agent": "aegisgate-demo-digest/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            log(f"Email sent: id={result.get('id', 'unknown')}")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        log(f"ERROR sending email: HTTP {e.code}: {body}")
        return False
    except Exception as e:
        log(f"ERROR sending email: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Send AegisGate demo daily digest")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be sent")
    parser.add_argument("--hours", type=int, default=24, help="How many hours back to look (default 24)")
    args = parser.parse_args()

    if not DIGEST_ENABLED and not args.dry_run:
        log("Digest disabled (set AEGISGATE_DIGEST_ENABLED=true to enable). Exiting.")
        return 0

    # Determine the cutoff time
    last_sent = read_last_sent()
    now = datetime.datetime.utcnow()
    if last_sent:
        since = last_sent
        log(f"Last successful send: {since.isoformat()}Z")
    else:
        since = now - datetime.timedelta(hours=args.hours)
        log(f"No previous send found; using {args.hours}h lookback")

    # Read signups
    signups = read_signups(since)
    log(f"Found {len(signups)} signup(s) since {since.isoformat()}Z")

    # Format and send
    subject = f"🛡️ AegisGate Demo — {len(signups)} new signup{'s' if len(signups) != 1 else ''} ({now.strftime('%Y-%m-%d')})"
    html = format_digest_html(signups, since)

    if send_via_resend(subject, html, dry_run=args.dry_run):
        if not args.dry_run:
            write_last_sent(now)
        log("Digest complete.")
        return 0
    else:
        log("Digest FAILED.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
