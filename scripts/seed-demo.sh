#!/bin/bash
# AegisGate Demo - Seed Script
# ===================================
#
# Initializes the demo data from /opt/aegisgate-demo/seed-data/
# into /data/seed/. This is run once on container startup.

set -euo pipefail

DATA_DIR="/data"
SEED_SOURCE="/opt/aegisgate-demo/seed-data"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] AegisGate Demo - Seeding data..."

# Create data directory structure
mkdir -p "$DATA_DIR/seed"
mkdir -p "$DATA_DIR/signups"

# Copy seed data
if [ -d "$SEED_SOURCE" ]; then
    cp -r "$SEED_SOURCE"/* "$DATA_DIR/seed/"
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)]   Copied $(ls $SEED_SOURCE | wc -l) seed files to $DATA_DIR/seed/"
else
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)]   WARNING: Seed source not found at $SEED_SOURCE"
    exit 1
fi

# Verify
for file in threats.json mcp-tools.json compliance-eu-ai-act.json dashboard-metrics.json playground-prompts.json; do
    if [ ! -f "$DATA_DIR/seed/$file" ]; then
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)]   WARNING: Missing seed file: $file"
    fi
done

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Seeding complete"
