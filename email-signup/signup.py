#!/usr/bin/env python3
"""
AegisGate Demo - Email Signup Handler
======================================

A simple Python HTTP server that handles:
  1. POST /signup/submit  - Receive email signup, store in CSV, redirect to /dashboard/
  2. GET  /               - Serve the signup form (index.html)
  3. GET  /dashboard/     - Serve the demo dashboard (after signup)
  4. GET  /playground/    - Serve the interactive playground
  5. GET  /docs/          - Serve the documentation

This is intentionally simple. For production, you'd use:
  - A real web framework (Flask, FastAPI)
  - A real database (PostgreSQL)
  - A real email service (Mailgun, SendGrid)
  - Cloudflare Turnstile for anti-bot
  - Rate limiting (Cloudflare, fail2ban)

But for a demo, this is enough to capture emails and redirect to the platform.

Usage:
  python3 signup.py [--port 8083]
"""

import argparse
import csv
import datetime
import hashlib
import http.server
import json
import os
import re
import socketserver
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# ============================================
# Configuration
# ============================================
DEFAULT_PORT = 8083
EMAIL_STORAGE_DIR = os.environ.get("AEGISGATE_DEMO_DATA_DIR", "/data")
EMAIL_FILE = os.path.join(EMAIL_STORAGE_DIR, "signups", "emails.csv")
EMAIL_LOG = os.path.join(EMAIL_STORAGE_DIR, "signups", "access.log")
WEBHOOK_URL = os.environ.get("EMAIL_WEBHOOK_URL", "")
RESEND_API_KEY = os.environ.get("AEGISGATE_RESEND_API_KEY", "")
RESEND_TO_EMAIL = os.environ.get("AEGISGATE_RESEND_TO_EMAIL", "security@aegisgatesecurity.io")
RESEND_FROM_EMAIL = os.environ.get("AEGISGATE_RESEND_FROM_EMAIL", "onboarding@resend.dev")

# Rate limiting (in-memory, simple)
RATE_LIMIT = {}  # email -> [timestamps]
RATE_LIMIT_WINDOW = 3600  # 1 hour
RATE_LIMIT_MAX = 5  # Max 5 signups per email per hour

# Access cookie (set on successful signup, checked by nginx)
ACCESS_COOKIE_NAME = os.environ.get("AEGISGATE_ACCESS_COOKIE", "aegisgate_demo_access")
ACCESS_COOKIE_MAX_AGE = int(os.environ.get("AEGISGATE_ACCESS_COOKIE_MAX_AGE", "86400"))  # 24h
ACCESS_COOKIE_REQUIRED = os.environ.get("AEGISGATE_ACCESS_COOKIE_REQUIRED", "true").lower() == "true"

# Admin endpoints (for ops: trigger digest, check status)
# Set AEGISGATE_ADMIN_TOKEN to a long random string. If not set, a random
# one is generated at startup and printed to the log.
ADMIN_TOKEN = os.environ.get("AEGISGATE_ADMIN_TOKEN", "")
if not ADMIN_TOKEN:
    import secrets as _secrets
    ADMIN_TOKEN = _secrets.token_urlsafe(32)
    # Note: log() isn't defined yet at module-load time, so use stderr directly
    import sys as _sys
    print(f"WARNING: AEGISGATE_ADMIN_TOKEN not set; generated ephemeral token: {ADMIN_TOKEN}", file=_sys.stderr)
ADMIN_TOKEN_HEADER = "X-Admin-Token"  # simpler than Authorization: Bearer for curl

# Cloudflare Turnstile (bot protection)
TURNSTILE_ENABLED = os.environ.get("AEGISGATE_TURNSTILE_ENABLED", "true").lower() == "true"
TURNSTILE_SECRET_KEY = os.environ.get("AEGISGATE_TURNSTILE_SECRET_KEY", "")
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
# Fail OPEN means: if the verification call fails (network error, missing
# config, etc.), accept the signup. Default is FAIL CLOSED (reject), which
# is the right behavior for a security feature. Set to "true" only for
# local dev/testing.
TURNSTILE_FAIL_OPEN = os.environ.get("AEGISGATE_TURNSTILE_FAIL_OPEN", "false").lower() == "true"

# Daily digest config (used by /admin/status to show digest state)
# These mirror the constants in scripts/send_daily_digest.py
RESEND_API_KEY = os.environ.get("AEGISGATE_RESEND_API_KEY", "")
DIGEST_TO = os.environ.get("AEGISGATE_DIGEST_TO_EMAIL", "security@aegisgatesecurity.io")
DIGEST_FROM = os.environ.get("AEGISGATE_DIGEST_FROM_EMAIL", "AegisGate Demo <onresend.dev>")
DIGEST_ENABLED = os.environ.get("AEGISGATE_DIGEST_ENABLED", "false").lower() == "true"
DIGEST_STATE_FILE = "/data/signups/digest_state.json"  # mirrors scripts/send_daily_digest.py:46

# Email validation regex (basic)
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# ============================================
# Helper functions
# ============================================
def log(message):
    """Log a message to stdout and to the log file."""
    timestamp = datetime.datetime.utcnow().isoformat() + "Z"
    log_line = f"[{timestamp}] {message}"
    print(log_line, flush=True)
    try:
        os.makedirs(os.path.dirname(EMAIL_LOG), exist_ok=True)
        with open(EMAIL_LOG, "a") as f:
            f.write(log_line + "\n")
    except Exception as e:
        print(f"Warning: Could not write to log file: {e}", file=sys.stderr)


def is_rate_limited(email):
    """Check if an email has hit the rate limit."""
    now = datetime.datetime.utcnow().timestamp()
    if email in RATE_LIMIT:
        # Remove old timestamps
        RATE_LIMIT[email] = [t for t in RATE_LIMIT[email] if now - t < RATE_LIMIT_WINDOW]
        if len(RATE_LIMIT[email]) >= RATE_LIMIT_MAX:
            return True
    return False


def record_signup(email):
    """Record a signup (for rate limiting)."""
    now = datetime.datetime.utcnow().timestamp()
    if email not in RATE_LIMIT:
        RATE_LIMIT[email] = []
    RATE_LIMIT[email].append(now)


def store_email(email, ip_address, user_agent):
    """Store the email signup in a CSV file."""
    try:
        os.makedirs(os.path.dirname(EMAIL_FILE), exist_ok=True)

        # Check if file exists
        file_exists = os.path.exists(EMAIL_FILE)

        # Hash the email for privacy (so we can detect duplicates without storing PII)
        email_hash = hashlib.sha256(email.lower().encode()).hexdigest()[:16]

        with open(EMAIL_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                # Header row
                writer.writerow(["timestamp", "email", "email_hash", "ip_address", "user_agent"])

            writer.writerow([
                datetime.datetime.utcnow().isoformat() + "Z",
                email,
                email_hash,
                ip_address,
                user_agent
            ])

        log(f"Signup stored: {email_hash} (from {ip_address})")
        return True
    except Exception as e:
        log(f"ERROR storing email: {e}")
        return False


def send_resend_email(email, ip_address, user_agent):
    """Send signup notification email via Resend API."""
    if not RESEND_API_KEY:
        log("WARNING: Resend API key not configured, skipping email")
        return

    # Debug: Log API key format (first 10 chars only for security)
    api_key_stripped = RESEND_API_KEY.strip()
    log(f"DEBUG: API key length={len(RESEND_API_KEY)}, stripped={len(api_key_stripped)}, starts_with={RESEND_API_KEY[:8] if len(RESEND_API_KEY) >= 8 else 'too_short'}")
    
    try:
        import urllib.request
        
        # Resend API endpoint
        url = "https://api.resend.com/emails"
        
        # Build email payload
        email_data = json.dumps({
            "from": RESEND_FROM_EMAIL,
            "to": [RESEND_TO_EMAIL],
            "subject": f"New Demo Signup: {email}",
            "html": f"""<h2>New Demo Site Signup!</h2>
<p><strong>Email:</strong> {email}</p>
<p><strong>IP Address:</strong> {ip_address}</p>
<p><strong>Time:</strong> {datetime.datetime.utcnow().isoformat()}Z</p>
<p><strong>Source:</strong> aegisgate-demo</p>
<p><strong>User Agent:</strong> {user_agent}</p>""",
            "tags": [
                {"name": "type", "value": "signup_notification"},
                {"name": "source", "value": "aegisgate-demo"}
            ]
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=email_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key_stripped}"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            log(f"Resend email sent successfully: {result.get('id', 'unknown')}")
            
    except Exception as e:
        log(f"ERROR: Resend email failed: {type(e).__name__}: {e}")


def send_webhook(email, ip_address, user_agent):
    """Send the signup to a configured webhook OR via Resend API (preferred)."""
    # Try Resend API first (if configured)
    if RESEND_API_KEY:
        send_resend_email(email, ip_address, user_agent)
        return
    
    # Fallback to webhook (legacy)
    if not WEBHOOK_URL:
        return

    try:
        import urllib.request
        data = json.dumps({
            "email": email,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "source": "aegisgate-demo",
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
        }).encode("utf-8")

        req = urllib.request.Request(
            WEBHOOK_URL,
            data=data,
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=5) as response:
            log(f"Webhook sent: HTTP {response.status}")
    except Exception as e:
        log(f"WARNING: Webhook failed: {e}")


def verify_turnstile(token, ip_address):
    """Verify a Cloudflare Turnstile token. Returns (success: bool, error: str)."""
    if not TURNSTILE_ENABLED:
        # Turnstile disabled (e.g., for local dev) — skip verification
        return True, ""

    if not TURNSTILE_SECRET_KEY:
        log("ERROR: Turnstile is enabled but no secret key is configured (set AEGISGATE_TURNSTILE_SECRET_KEY)")
        if TURNSTILE_FAIL_OPEN:
            log("WARNING: TURNSTILE_FAIL_OPEN=true — accepting signup anyway (testing mode)")
            return True, ""
        return False, "Bot challenge not configured. Please contact support."

    if not token:
        return False, "Missing bot-challenge token"

    try:
        data = urllib.parse.urlencode({
            "secret": TURNSTILE_SECRET_KEY,
            "response": token,
            "remoteip": ip_address,
        }).encode("utf-8")

        req = urllib.request.Request(
            TURNSTILE_VERIFY_URL,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "aegisgate-demo-signup/1.0",
            }
        )

        with urllib.request.urlopen(req, timeout=5) as response:
            raw_body = response.read().decode("utf-8", errors="replace")
        log(f"Turnstile siteverify response (first 200 chars): {raw_body[:200]}")

        try:
            result = json.loads(raw_body)
        except (json.JSONDecodeError, ValueError) as e:
            log(f"ERROR: Turnstile siteverify returned non-JSON body: {e}")
            log(f"  Raw body: {raw_body!r}")
            raise

        if not isinstance(result, dict):
            log(f"ERROR: Turnstile siteverify returned non-dict JSON ({type(result).__name__}): {result!r}")
            raise TypeError(f"Expected dict, got {type(result).__name__}")

        if result.get("success"):
            log(f"Turnstile verified (hostname={result.get('hostname')}, action={result.get('action')})")
            return True, ""
        else:
            error_codes = result.get("error-codes", [])
            log(f"Turnstile FAILED: {error_codes}")
            return False, f"Bot challenge failed: {', '.join(error_codes)}"

    except Exception as e:
        import traceback
        log(f"ERROR: Turnstile verification exception: {type(e).__name__}: {e}")
        log(f"  Traceback: {traceback.format_exc().replace(chr(10), ' | ')}")
        if TURNSTILE_FAIL_OPEN:
            log("WARNING: TURNSTILE_FAIL_OPEN=true — accepting signup anyway (testing mode)")
            return True, ""
        # Pass a more useful error message back (visible in browser network panel)
        return False, f"Bot challenge service unavailable ({type(e).__name__}). Please try again."



def _count_csv_rows(path):
    """Count data rows in a CSV (excluding the header)."""
    try:
        with open(path, "r") as f:
            return max(0, sum(1 for _ in f) - 1)
    except Exception:
        return 0


def serve_static(handler, filename, content_type="text/html"):
    """Serve a static file from the email-signup directory."""
    filepath = Path(__file__).parent / filename
    try:
        with open(filepath, "rb") as f:
            content = f.read()
        handler.send_response(200)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(content)))
        handler.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        handler.end_headers()
        handler.wfile.write(content)
    except FileNotFoundError:
        handler.send_error(404, f"File not found: {filename}")


# ============================================
# HTTP Request Handler
# ============================================
class SignupHandler(http.server.BaseHTTPRequestHandler):
    """Handle signup form submissions and static file serving."""

    def log_message(self, format, *args):
        """Override to use our custom logging."""
        log(f"{self.client_address[0]} - {format % args}")

    def do_GET(self):
        """Handle GET requests."""
        path = self.path.split("?")[0]  # Strip query string

        if path == "/" or path == "/index.html" or path == "/signup/":
            serve_static(self, "index.html")
        elif path == "/dashboard/" or path == "/dashboard":
            # Redirect to the static demo dashboard (served by nginx at /dashboard/).
            # The static dashboard is self-contained — it does not require the
            # platform's API. This is what we redirect to after a successful signup.
            # (We do NOT redirect to /platform/ — that path proxies to the
            # platform's dashboard server on port 8443, which only serves API
            # endpoints, not a web UI, so users get a 404.)
            self.send_response(302)
            self.send_header("Location", "/dashboard/")
            self.end_headers()
        elif path == "/signup/submit":
            # GET on /signup/submit is not allowed
            self.send_response(405)
            self.send_header("Allow", "POST")
            self.end_headers()
        elif path == "/admin/status":
            self.handle_admin_status()
        elif path == "/admin/run-digest":
            self.handle_admin_run_digest()
        else:
            self.send_error(404, f"Not found: {path}")


    def do_HEAD(self):
        """Handle HEAD requests by delegating to do_GET (suppresses body)."""
        # Just call do_GET — the base class handles body suppression
        # for HEAD requests, and our GET returns proper headers.
        self.do_GET()

    def check_admin_auth(self):
        """Check the X-Admin-Token header. Returns True if authorized."""
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        query_token = qs.get("token", [""])[0]
        header_token = self.headers.get(ADMIN_TOKEN_HEADER, "")
        return (
            header_token == ADMIN_TOKEN or query_token == ADMIN_TOKEN
        )

    def handle_admin_status(self):
        """Return a JSON status report. Useful for ops debugging."""
        if not self.check_admin_auth():
            self.send_json_error(401, "Unauthorized: missing or invalid admin token")
            return
        try:
            status = {
                "service": "aegisgate-demo",
                "turnstile": {
                    "enabled": TURNSTILE_ENABLED,
                    "secret_configured": bool(TURNSTILE_SECRET_KEY),
                    "fail_open": TURNSTILE_FAIL_OPEN,
                },
                "cookie_gate": {
                    "cookie_name": ACCESS_COOKIE_NAME,
                    "max_age_seconds": ACCESS_COOKIE_MAX_AGE,
                    "required": ACCESS_COOKIE_REQUIRED,
                },
                "digest": {
                    "enabled": DIGEST_ENABLED,
                    "to": DIGEST_TO,
                    "from": DIGEST_FROM,
                    "resend_key_configured": bool(RESEND_API_KEY),
                    "state_file": DIGEST_STATE_FILE,
                    "state_file_exists": os.path.exists(DIGEST_STATE_FILE),
                },
                "signups": {
                    "data_dir": EMAIL_STORAGE_DIR,
                    "csv_path": EMAIL_FILE,
                    "csv_exists": os.path.exists(EMAIL_FILE),
                    "csv_size_bytes": os.path.getsize(EMAIL_FILE) if os.path.exists(EMAIL_FILE) else 0,
                    "row_count": _count_csv_rows(EMAIL_FILE) if os.path.exists(EMAIL_FILE) else 0,
                },
                "request": {
                    "client_ip": self.client_address[0],
                    "user_agent": self.headers.get("User-Agent", "unknown"),
                },
            }
            self.send_json_response(200, status)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            log(f"ERROR in handle_admin_status: {type(e).__name__}: {e}")
            log(f"  Traceback: {tb.replace(chr(10), ' | ')}")
            # Return error to client (so we can see what's wrong via curl)
            self.send_json_error(500, f"{type(e).__name__}: {e}")

    def handle_admin_run_digest(self):
        """Manually trigger the daily digest script. Returns the script's stdout/stderr."""
        if not self.check_admin_auth():
            self.send_json_error(401, "Unauthorized: missing or invalid admin token")
            return

        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        hours = qs.get("hours", ["24"])[0]
        dry_run = qs.get("dry-run", ["false"])[0].lower() == "true"

        import subprocess
        script = "/opt/aegisgate-demo/scripts/send_daily_digest.py"
        args = [sys.executable, script, "--hours", str(hours)]
        if dry_run:
            args.append("--dry-run")

        log(f"Admin: manually triggering digest (hours={hours}, dry_run={dry_run})")
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=30,
                env=os.environ.copy(),
            )
            payload = {
                "ok": result.returncode == 0,
                "returncode": result.returncode,
                "hours": hours,
                "dry_run": dry_run,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-2000:],
            }
            self.send_json_response(200 if result.returncode == 0 else 500, payload)
        except subprocess.TimeoutExpired:
            self.send_json_error(500, "Digest script timed out after 30s")
        except Exception as e:
            self.send_json_error(500, f"Digest failed: {type(e).__name__}: {e}")

    def do_POST(self):
        """Handle POST requests (signup submissions)."""
        path = self.path.split("?")[0]

        if path == "/signup/submit":
            self.handle_signup()
        elif path == "/admin/run-digest":
            self.handle_admin_run_digest()
        else:
            self.send_error(404, f"Not found: {path}")

    def handle_signup(self):
        """Process a signup submission."""
        # Read the request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        try:
            data = json.loads(body)
            email = data.get("email", "").strip()
        except json.JSONDecodeError:
            self.send_json_error(400, "Invalid JSON in request body")
            return

        # Validate email
        if not email:
            self.send_json_error(400, "Email is required")
            return

        if not EMAIL_REGEX.match(email):
            self.send_json_error(400, "Please enter a valid email address")
            return

        # Rate limiting
        if is_rate_limited(email):
            self.send_json_error(429, "Too many signup attempts. Please try again in 1 hour.")
            return

        # Get client info
        ip_address = self.client_address[0]
        user_agent = self.headers.get("User-Agent", "unknown")

        # Turnstile verification (bot protection)
        if TURNSTILE_ENABLED:
            turnstile_token = data.get("cf-turnstile-response", "").strip()
            ts_ok, ts_err = verify_turnstile(turnstile_token, ip_address)
            if not ts_ok:
                self.send_json_error(403, ts_err or "Bot challenge failed")
                log(f"Turnstile REJECTED: {email_hash if 'email_hash' in dir() else email} (from {ip_address})")
                return

        # Store and notify
        record_signup(email)
        store_success = store_email(email, ip_address, user_agent)
        send_webhook(email, ip_address, user_agent)

        if not store_success:
            self.send_json_error(500, "Could not store email. Please try again.")
            return

        # Send success response WITH access cookie
        # The cookie tells nginx to let this browser through to /dashboard/
        # and /seed-data/ for the next 24 hours.
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        cookie_parts = [
            f"{ACCESS_COOKIE_NAME}=1",
            f"Path=/",
            f"Max-Age={ACCESS_COOKIE_MAX_AGE}",
            "HttpOnly",
            "SameSite=Lax",
        ]
        if self.headers.get("X-Forwarded-Proto", "http") == "https" or            self.headers.get("X-Forwarded-Proto", "").endswith("https"):
            cookie_parts.append("Secure")
        self.send_header("Set-Cookie", "; ".join(cookie_parts))
        self.end_headers()
        response = json.dumps({
            "success": True,
            "message": "Signup successful. Redirecting...",
            "redirect": "/dashboard/"
        })
        self.wfile.write(response.encode("utf-8"))

    def send_json_response(self, status_code, data):
        """Send a JSON success response."""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        # Allow cached responses for admin status (1 minute)
        # but always revalidate
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        response = json.dumps(data, default=str)
        self.wfile.write(response.encode("utf-8"))

    def send_json_error(self, status_code, message):
        """Send a JSON error response."""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        response = json.dumps({
            "success": False,
            "error": message
        })
        self.wfile.write(response.encode("utf-8"))


# ============================================
# Main
# ============================================
def main():
    parser = argparse.ArgumentParser(description="AegisGate Demo Email Signup Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (use 0.0.0.0 for external)")
    args = parser.parse_args()

    # Ensure storage directory exists
    os.makedirs(os.path.dirname(EMAIL_FILE), exist_ok=True)

    # Log startup
    log("=" * 60)
    log("AegisGate Demo - Email Signup Server")
    log("=" * 60)
    log(f"Storage:  {EMAIL_FILE}")
    log(f"Webhook:  {WEBHOOK_URL or '(not configured)'}")
    log(f"Listening: http://{args.host}:{args.port}/")
    log("=" * 60)

    # Start the server
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((args.host, args.port), SignupHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            log("Shutting down...")
            httpd.shutdown()


if __name__ == "__main__":
    main()
