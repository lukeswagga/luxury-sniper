# Railway PostgreSQL Connection Issues - Troubleshooting Guide

## Current Situation ✅
Your **bot is working!** It's online and ready to receive listings. The database connection is failing, but this won't prevent the bot from functioning.

## Error Analysis
```
connection to server at "nozomi.proxy.rlwy.net" (66.33.22.249), port 43247 failed: 
server closed the connection unexpectedly
```

This means Railway's PostgreSQL service is actively refusing/closing connections.

---

## Quick Fixes to Try (In Order)

### 1. Check Railway PostgreSQL Service Status
```bash
# Go to Railway Dashboard
https://railway.app

# Navigate to:
Your Project → PostgreSQL Service → Metrics

# Look for:
- Is the service running? (green status)
- Are there connection errors?
- Is CPU/Memory maxed out?
```

### 2. Verify DATABASE_URL Environment Variable
```bash
# In Railway Dashboard:
Your Project → Bot Service → Variables

# Check:
- DATABASE_URL exists
- Format: postgresql://user:pass@host:port/dbname
- Copy the value from the PostgreSQL service
```

### 3. Restart PostgreSQL Service
```bash
# In Railway Dashboard:
PostgreSQL Service → Settings → Restart Service

# Wait 30 seconds, then check bot logs
```

### 4. Check Connection Limits
Railway free tier has connection limits:
- **Starter Plan**: 10 concurrent connections
- **Developer Plan**: 50 concurrent connections

If you're hitting limits:
- Option A: Upgrade Railway plan
- Option B: Reduce connection pool size (already set to 10)
- Option C: Use SQLite instead (see below)

---

## Alternative: Switch to SQLite (No Database Server Needed)

If Railway PostgreSQL continues to fail, you can use SQLite locally:

### Option 1: Disable PostgreSQL Temporarily
```bash
# In Railway Dashboard:
Bot Service → Variables → Remove DATABASE_URL

# This will make the bot use SQLite instead
# Note: Each deployment will start fresh (no data persistence)
```

### Option 2: Add Persistent Volume for SQLite
```bash
# In Railway Dashboard:
Bot Service → Settings → Add Volume

Volume Name: luxury-sniper-data
Mount Path: /data

# Then update database_manager.py line 18:
self.db_path = '/data/auction_tracking.db'
```

---

## Check if Database is Actually Needed

Your bot can work WITHOUT a database for basic functionality:

✅ **Works without DB:**
- Receiving webhook listings
- Posting to Discord channels
- Emoji reactions
- Bot commands (!profit_stats, !profit_setup)

❌ **Requires DB:**
- Storing user preferences
- Bookmarking listings
- Tracking seen items
- User subscription management
- Historical statistics

**If you only need basic posting, the bot works fine right now!**

---

## Advanced Debugging

### 1. Check PostgreSQL Logs
```bash
# Railway Dashboard:
PostgreSQL Service → Deployments → View Logs

# Look for:
- "too many connections"
- "max_connections"
- "connection reset"
- Memory/CPU errors
```

### 2. Test Direct Connection
```bash
# Install Railway CLI:
npm i -g @railway/cli

# Login:
railway login

# Link to project:
railway link

# Connect to database:
railway connect postgres

# If this works, the database is fine and it's a network issue
```

### 3. Check Railway Network Issues
Sometimes Railway has regional network issues:
- Check: https://railway.app/status
- Check: https://twitter.com/Railway (for outage updates)

---

## Current Bot Configuration

Your bot has these resilience features:
- ✅ 3 connection retry attempts
- ✅ 5-second delays between retries
- ✅ 10-second connection timeout
- ✅ Connection pooling (1-10 connections)
- ✅ Graceful degradation (starts without DB)
- ✅ Will retry DB operations on first use

---

## Recommended Action Plan

**Immediate (Do Now):**
1. Go to Railway dashboard
2. Check PostgreSQL service status
3. Restart PostgreSQL service
4. Check bot logs in 30 seconds

**If Still Failing (Next Steps):**
1. Verify DATABASE_URL is correct
2. Check connection limits on your plan
3. Consider temporary SQLite switch
4. Contact Railway support if database is down

**Long Term:**
1. Monitor PostgreSQL metrics regularly
2. Set up alerts for connection failures
3. Consider adding Redis for caching
4. Consider managed PostgreSQL (AWS RDS, DigitalOcean, etc.)

---

## Bot is Working Now! 

Your logs show:
```
✅ Auction channel ready: #💎-auctions-under-60
✅ BIN channel ready: #💎-buyitnow-steals
✅ Profit alerts ready: #🚀-profit-alerts
```

**The bot is live and functional!** It will just run without persistent storage until the database connection is fixed.

---

## Need Help?

1. **Railway Support**: https://railway.app/help
2. **Railway Discord**: https://discord.gg/railway
3. **Railway Status**: https://railway.app/status

---

**Created:** October 13, 2025  
**Status:** Bot is functional, database troubleshooting in progress

