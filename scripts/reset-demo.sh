#!/bin/bash
# AegisGate Demo - Reset Script
# ===================================
#
# Resets the demo to a clean state by:
#   1. Wiping runtime state (NOT seed data)
#   2. Re-copying seed data from /opt/aegisgate-demo/seed-data/
#   3. Logging the reset event
#
# This is run automatically every 24 hours by the entrypoint cron job.
# It can also be run manually via the Render.com shell.

set -euo pipefail

DATA_DIR="/data"
SEED_SOURCE="/opt/aegisgate-demo/seed-data"
LOG_FILE="/data/reset.log"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] AegisGate Demo - Resetting..." | tee -a "$LOG_FILE"

# 1. Wipe runtime state (everything in /data EXCEPT /data/seed)
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)]   Wiping runtime state..." | tee -a "$LOG_FILE"
find "$DATA_DIR" -mindepth 1 -maxdepth 1 -type d ! -name 'seed' -exec rm -rf {} + 2>/dev/null || true

# 2. Re-copy seed data
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)]   Re-seeding data..." | tee -a "$LOG_FILE"
mkdir -p "$DATA_DIR/seed"
cp -r "$SEED_SOURCE"/* "$DATA_DIR/seed/" 2>/dev/null || true

# 3. Re-initialize signups directory (preserves any prior signups for the day)
mkdir -p "$DATA_DIR/signups"

# 4. Verify the reset
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)]   Verifying seed data..." | tee -a "$LOG_FILE"
SEED_FILES=$(ls "$DATA_DIR/seed/" 2>/dev/null | wc -l)
if [ "$SEED_FILES" -lt 5 ]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)]   WARNING: Expected 5+ seed files, found $SEED_FILES" | tee -a "$LOG_FILE"
fi

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Reset complete" | tee -a "$LOG_FILE"
