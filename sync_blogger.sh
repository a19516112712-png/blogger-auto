#!/bin/bash
# Sync from Blogger — Quick script to run the sync pipeline
# Requires: BLOG_ID, CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN env vars

set -e

cd "$(dirname "$0")"

export PYTHONPATH="${PYTHONPATH}:$(pwd)"

echo "=============================================="
echo "  Blogger Sync Pipeline"
echo "=============================================="
echo ""

# Step 1: Check credentials
echo "[1/3] Checking credentials..."
if [ -z "$BLOG_ID" ] || [ -z "$CLIENT_ID" ] || [ -z "$CLIENT_SECRET" ] || [ -z "$REFRESH_TOKEN" ]; then
    echo "ERROR: Missing required environment variables."
    echo "Set: BLOG_ID, CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN"
    echo ""
    echo "Or copy .env.example to .env and fill in values:"
    echo "  cp .env.example .env"
    exit 1
fi
echo "  All credentials present."

# Step 2: Run sync
echo ""
echo "[2/3] Running sync_from_blogger.py..."
python3 sync_from_blogger.py

# Step 3: Summary
echo ""
echo "[3/3] Sync complete!"
echo ""
echo "Local articles: $(ls posts/*.md 2>/dev/null | wc -l | tr -d ' ')"
echo "Database: database/topic_queue.db"
