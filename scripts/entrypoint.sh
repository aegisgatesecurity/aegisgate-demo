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
PLATFORM_BINARY="${PLATFORM_BINARY:-/aegisgate-platform}"
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
# Initialize demo data
# ============================================
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Initializing demo data..." | tee -a "$LOG_FILE"

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
# Start the email signup server (background)
# ============================================
if [ -d "/opt/aegisgate-demo/email-signup" ]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting email signup server on port 8083..." | tee -a "$LOG_FILE"
    # Use Python's built-in HTTP server (available in most base images)
    cd /opt/aegisgate-demo/email-signup
    python3 -m http.server 8083 --bind 127.0.0.1 >/dev/null 2>&1 &
    SIGNUP_PID=$!
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Email signup server PID: $SIGNUP_PID" | tee -a "$LOG_FILE"
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
    --embedded-mcp \
    --target=http://httpbin.org:80 \
    --mode=demo \
    2>&1 | tee -a "$LOG_FILE"
