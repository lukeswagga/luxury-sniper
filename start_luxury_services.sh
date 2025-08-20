#!/bin/bash

# Luxury Services Startup Script
# Starts both the luxury scraper and Discord bot

echo "🚀 Starting Luxury Services..."
echo "================================"

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed or not in PATH"
    exit 1
fi

# Check if required files exist
if [ ! -f "luxury_discord_bot.py" ]; then
    echo "❌ luxury_discord_bot.py not found"
    exit 1
fi

if [ ! -f "luxury_sniper.py" ]; then
    echo "❌ luxury_sniper.py not found"
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
export PORT=${PORT:-8002}

echo "📋 Configuration:"
echo "   USE_DISCORD_BOT: $USE_DISCORD_BOT"
echo "   DISCORD_BOT_URL: $DISCORD_BOT_URL"
echo "   PORT: $PORT"
echo ""

# Function to cleanup background processes
cleanup() {
    echo ""
    echo "🛑 Shutting down services..."
    kill $DISCORD_PID $SCRAPER_PID 2>/dev/null
    echo "✅ Services stopped"
    exit 0
}

# Set trap for cleanup
trap cleanup SIGINT SIGTERM

# Start Discord Bot
echo "🤖 Starting Luxury Discord Bot..."
python3 luxury_discord_bot.py &
DISCORD_PID=$!
echo "   Discord Bot PID: $DISCORD_PID"

# Wait a moment for Discord bot to start
sleep 5

# Check if Discord bot is running
if ! kill -0 $DISCORD_PID 2>/dev/null; then
    echo "❌ Discord Bot failed to start"
    exit 1
fi

echo "✅ Discord Bot started successfully"

# Start Luxury Scraper
echo "🎯 Starting Luxury Scraper..."
python3 luxury_sniper.py &
SCRAPER_PID=$!
echo "   Scraper PID: $SCRAPER_PID"

# Wait a moment for scraper to start
sleep 3

# Check if scraper is running
if ! kill -0 $SCRAPER_PID 2>/dev/null; then
    echo "❌ Luxury Scraper failed to start"
    kill $DISCORD_PID 2>/dev/null
    exit 1
fi

echo "✅ Luxury Scraper started successfully"
echo ""
echo "🎉 All services are running!"
echo ""
echo "📺 Discord Channels:"
echo "   🔨 Auctions: #💎-luxury-under-60"
echo "   🛒 Buy It Now: #💎-buyitnow"
echo ""
echo "🌐 Health Check URLs:"
echo "   Discord Bot: http://localhost:8002/health"
echo "   Luxury Scraper: http://localhost:8003/health"
echo ""
echo "🧪 Test Integration: python3 test_luxury_integration.py"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for processes
wait
