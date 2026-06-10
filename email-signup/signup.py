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
from pathlib import Path

# ============================================
# Configuration
# ============================================
DEFAULT_PORT = 8083
EMAIL_STORAGE_DIR = os.environ.get("AEGISGATE_DEMO_DATA_DIR", "/data")
EMAIL_FILE = os.path.join(EMAIL_STORAGE_DIR, "signups", "emails.csv")
EMAIL_LOG = os.path.join(EMAIL_STORAGE_DIR, "signups", "access.log")
WEBHOOK_URL = os.environ.get("EMAIL_WEBHOOK_URL", "")

# Rate limiting (in-memory, simple)
RATE_LIMIT = {}  # email -> [timestamps]
RATE_LIMIT_WINDOW = 3600  # 1 hour
RATE_LIMIT_MAX = 5  # Max 5 signups per email per hour

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


def send_webhook(email, ip_address, user_agent):
    """Send the signup to a configured webhook (e.g., Mailgun, SendGrid, Zapier)."""
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
            # Redirect to the platform's UI (which nginx serves via /platform/)
            # The nginx /platform/ location now proxies to the dashboard port (8443)
            # which shows the actual AegisGate platform UI.
            # We do NOT redirect to localhost:8080 (the proxy port) because in
            # demo mode that would show httpbin.org's content.
            self.send_response(302)
            self.send_header("Location", "/platform/")
            self.end_headers()
        elif path == "/signup/submit":
            # GET on /signup/submit is not allowed
            self.send_response(405)
            self.send_header("Allow", "POST")
            self.end_headers()
        else:
            self.send_error(404, f"Not found: {path}")

    def do_POST(self):
        """Handle POST requests (signup submissions)."""
        path = self.path.split("?")[0]

        if path == "/signup/submit":
            self.handle_signup()
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

        # Store and notify
        record_signup(email)
        store_success = store_email(email, ip_address, user_agent)
        send_webhook(email, ip_address, user_agent)

        if not store_success:
            self.send_json_error(500, "Could not store email. Please try again.")
            return

        # Send success response
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        response = json.dumps({
            "success": True,
            "message": "Signup successful. Redirecting...",
            "redirect": "/dashboard/"
        })
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
