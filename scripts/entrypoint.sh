#!/bin/bash
# AegisGate Demo - Container Entrypoint
# ========================================
#
# This script:
#   1. Verifies the platform binary is present
#   2. Sets up demo data (seeds the database with sample content)
#   3. Starts a daily reset cron job
#   4. Starts the email signup server (a simple Python HTTP server)
#   5. Starts the AegisGate platform in demo mode
#   6. Handles graceful shutdown
#
# This is the entrypoint for the Docker container.

set -euo pipefail

# ============================================
# Configuration
# ============================================
PLATFORM_BINARY="${PLATFORM_BINARY:-/usr/local/bin/aegisgate-platform}"
SEED_DIR="/opt/aegisgate-demo/seed-data"
DATA_DIR="/data"
RESET_HOURS="${AEGISGATE_DEMO_RESET_HOURS:-24}"
LOG_FILE="/data/demo.log"

# ============================================
# Pre-flight checks
# ============================================
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] AegisGate Demo - Starting..." | tee -a "$LOG_FILE"

if [ ! -x "$PLATFORM_BINARY" ]; then
    echo "ERROR: Platform binary not found at $PLATFORM_BINARY" | tee -a "$LOG_FILE"
    exit 1
fi

# Show platform version
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Platform version:" | tee -a "$LOG_FILE"
"$PLATFORM_BINARY" --version 2>&1 | tee -a "$LOG_FILE" || true

# ============================================
# Storage directory setup
# ============================================
# On free tier, we don't have a persistent disk. The /data directory
# is still created but it lives in the container's filesystem, which
# means it's lost on container restart.
#
# In production (with a paid Render plan), you would mount a real disk:
#   disk:
#     name: demo-data
#     mountPath: /data
#     sizeGB: 1
#
# For now (free tier), we:
#   1. Create /data as a regular directory
#   2. The seed data is re-loaded from the image on every startup
#   3. The signup CSV is ephemeral (regenerated on every restart)
#   4. The daily reset still works (it re-copies seed data)

# ============================================
# Initialize demo data
# ============================================
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Initializing demo data..." | tee -a "$LOG_FILE"

# Ensure /data exists (might be missing if disk wasn't mounted)
mkdir -p "$DATA_DIR/seed" "$DATA_DIR/signups" "$DATA_DIR/audit"
chmod 777 "$DATA_DIR" "$DATA_DIR/seed" "$DATA_DIR/signups" "$DATA_DIR/audit" 2>/dev/null || true

# Copy seed data to runtime directory (if not already there)
if [ -d "$SEED_DIR" ] && [ -z "$(ls -A $DATA_DIR/seed 2>/dev/null)" ]; then
    cp -r "$SEED_DIR"/* "$DATA_DIR/seed/" 2>/dev/null || true
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Seed data copied to $DATA_DIR/seed/" | tee -a "$LOG_FILE"
fi

# ============================================
# Run the seed loader to translate JSON → AuditEntry format
# ============================================
# The platform's persistence layer (opsec.FileStorageBackend) expects
# individual JSON files per audit entry, with the AuditEntry schema.
# The seed_loader.py translates our marketing-friendly JSON into that format.
SEED_LOADER="/opt/aegisgate-demo/scripts/seed_loader.py"
AUDIT_DIR="/data/audit"

if [ -x "$SEED_LOADER" ] || [ -f "$SEED_LOADER" ]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Running seed loader to populate audit log..." | tee -a "$LOG_FILE"
    python3 "$SEED_LOADER" \
        --source "$DATA_DIR/seed" \
        --target "$AUDIT_DIR" \
        2>&1 | tee -a "$LOG_FILE" || true
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Seed loader complete" | tee -a "$LOG_FILE"
fi

# ============================================
# Set up daily reset cron job
# ============================================
# Reset demo state every $RESET_HOURS hours
RESET_SECONDS=$((RESET_HOURS * 3600))

# Create a background process that resets state on a timer
(
    while true; do
        sleep "$RESET_SECONDS"
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Demo reset: clearing runtime state..." | tee -a "$LOG_FILE"
        # Clear runtime state (not seed data)
        find "$DATA_DIR" -mindepth 1 -maxdepth 1 -type d ! -name 'seed' -exec rm -rf {} + 2>/dev/null || true
        mkdir -p "$DATA_DIR/seed"
        cp -r "$SEED_DIR"/* "$DATA_DIR/seed/" 2>/dev/null || true
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Demo reset complete" | tee -a "$LOG_FILE"
    done
) &
RESET_PID=$!

# Graceful shutdown handler
trap 'echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Shutting down..." | tee -a "$LOG_FILE"; kill $RESET_PID 2>/dev/null || true; exit 0' SIGTERM SIGINT

# ============================================
# Start nginx reverse proxy (background)
# ============================================
if [ -d "/opt/aegisgate-demo/nginx" ] && [ -f "/opt/aegisgate-demo/nginx/nginx.conf" ]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting nginx reverse proxy on port 80..." | tee -a "$LOG_FILE"
    # Check if nginx is installed (it may not be in the distroless base image)
    if command -v nginx >/dev/null 2>&1; then
        # Test the config first
        nginx -t -c /opt/aegisgate-demo/nginx/nginx.conf 2>&1 | tee -a "$LOG_FILE" || \
            echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] WARNING: nginx config test failed" | tee -a "$LOG_FILE"
        # Start nginx in the background
        nginx -c /opt/aegisgate-demo/nginx/nginx.conf 2>&1 | tee -a "$LOG_FILE" &
        NGINX_PID=$!
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] nginx PID: $NGINX_PID" | tee -a "$LOG_FILE"
    else
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] WARNING: nginx is not installed in this image" | tee -a "$LOG_FILE"
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Without nginx, the platform will be exposed directly on port 8080" | tee -a "$LOG_FILE"
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] For full demo features (signup, banner injection), use a different image with nginx" | tee -a "$LOG_FILE"
    fi
fi

# ============================================
# Start the email signup server (background)
# ============================================
# IMPORTANT: We use the custom signup.py server (not python3 -m http.server)
# because the custom one handles POST /signup/submit. The built-in
# http.server only supports GET/HEAD and returns 501 on POST.
if [ -d "/opt/aegisgate-demo/email-signup" ]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting email signup server on port 8083..." | tee -a "$LOG_FILE"
    # Check if signup.py exists
    if [ -f "/opt/aegisgate-demo/email-signup/signup.py" ]; then
        cd /opt/aegisgate-demo/email-signup
        # Run the custom signup server (handles POST /signup/submit)
        # NOTE: signup.py uses argparse with --port flag, not positional argument
        python3 signup.py --port 8083 >/dev/null 2>&1 &
        SIGNUP_PID=$!
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Email signup server PID: $SIGNUP_PID (custom handler)" | tee -a "$LOG_FILE"
    else
        # Fallback: built-in static server (won't handle POSTs)
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] WARNING: signup.py not found, using static file server (POSTs will fail)" | tee -a "$LOG_FILE"
        cd /opt/aegisgate-demo/email-signup
        python3 -m http.server 8083 --bind 127.0.0.1 >/dev/null 2>&1 &
        SIGNUP_PID=$!
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Email signup server PID: $SIGNUP_PID (static fallback)" | tee -a "$LOG_FILE"
    fi
fi

# ============================================
# Start the AegisGate platform in demo mode (foreground)
# ============================================
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting AegisGate in demo mode..." | tee -a "$LOG_FILE"

# The platform binary supports --mode=demo starting in v3.3.0-beta.2.
# In demo mode, the platform:
#   - Skips license enforcement (runs as Community tier)
#   - Forces the target to httpbin.org (mock upstream, no real LLM)
#   - Applies read-only safety restrictions to the admin dashboard
#   - Sets stricter rate limits (100 req/hour per visitor)
#
# We pass the --mode flag last so the help text in case of an unknown flag
# is still readable. We also pass --target explicitly to be defensive
# in case --mode=demo doesn't fully override the target (older versions).
exec "$PLATFORM_BINARY" \
    --config=/opt/aegisgate-demo/demo-config.yaml \
    --tier=community \
    --embedded-mcp=false \
    --proxy-port=9090   \
    --mcp-port=9091   \
    --target=http://httpbin.org:80 \
    --mode=demo \
    2>&1 | tee -a "$LOG_FILE"
