#!/bin/bash

# Grizzly Jacket Scraper Startup Script

echo "🐻 Starting Grizzly Jacket Scraper..."
echo "===================================="

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed or not in PATH"
    exit 1
fi

# Check if required files exist
if [ ! -f "grizzly_jacket_sniper.py" ]; then
    echo "❌ grizzly_jacket_sniper.py not found"
    exit 1
fi

if [ ! -f "brands_grizzly.json" ]; then
    echo "❌ brands_grizzly.json not found"
    exit 1
fi

# Check environment variables
if [ -z "$DISCORD_BOT_TOKEN" ]; then
    echo "⚠️  DISCORD_BOT_TOKEN not set"
    echo "   Please set: export DISCORD_BOT_TOKEN='your_token_here'"
fi

if [ -z "$GUILD_ID" ]; then
    echo "⚠️  GUILD_ID not set"
    echo "   Please set: export GUILD_ID='your_guild_id_here'"
fi

# Set default values if not set
export USE_DISCORD_BOT=${USE_DISCORD_BOT:-true}
export DISCORD_BOT_URL=${DISCORD_BOT_URL:-http://localhost:8002}
export PORT=${PORT:-8004}

echo "📋 Configuration:"
echo "   USE_DISCORD_BOT: $USE_DISCORD_BOT"
echo "   DISCORD_BOT_URL: $DISCORD_BOT_URL"
echo "   PORT: $PORT"
echo ""

# Function to cleanup background processes
cleanup() {
    echo ""
    echo "🛑 Shutting down Grizzly Jacket Scraper..."
    kill $SCRAPER_PID 2>/dev/null
    echo "✅ Scraper stopped"
    exit 0
}

# Set trap for cleanup
trap cleanup SIGINT SIGTERM

# Start Grizzly Jacket Scraper
echo "🐻 Starting Grizzly Jacket Scraper..."
python3 grizzly_jacket_sniper.py &
SCRAPER_PID=$!
echo "   Scraper PID: $SCRAPER_PID"

# Wait a moment for scraper to start
sleep 3

# Check if scraper is running
if ! kill -0 $SCRAPER_PID 2>/dev/null; then
    echo "❌ Grizzly Jacket Scraper failed to start"
    exit 1
fi

echo "✅ Grizzly Jacket Scraper started successfully"
echo ""
echo "🎉 Grizzly Jacket Scraper is running!"
echo ""
echo "🌐 Health Check URL:"
echo "   Grizzly Scraper: http://localhost:8004/health"
echo ""
echo "📊 Stats URL:"
echo "   Grizzly Scraper: http://localhost:8004/stats"
echo ""
echo "Press Ctrl+C to stop the scraper"

# Wait for process
wait

