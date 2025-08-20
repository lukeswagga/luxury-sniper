#!/usr/bin/env python3

import discord
from discord.ext import commands
import asyncio
import json
import os
import logging
import time
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify
import threading
import re
from database_manager import (
    db_manager, add_listing, add_user_bookmark, 
    get_user_proxy_preference, set_user_proxy_preference,
    init_subscription_tables
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('luxury_profit_discord_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def load_config():
    bot_token = os.environ.get('DISCORD_BOT_TOKEN')
    guild_id = os.environ.get('GUILD_ID')
    
    if not bot_token:
        logger.error("❌ DISCORD_BOT_TOKEN environment variable not set!")
        exit(1)
    
    if not guild_id:
        logger.error("❌ GUILD_ID environment variable not set!")
        exit(1)
    
    logger.info("✅ Profit bot configuration loaded successfully")
    
    return {
        'bot_token': bot_token,
        'guild_id': int(guild_id)
    }

config = load_config()
BOT_TOKEN = config['bot_token']
GUILD_ID = config['guild_id']

# Channel configuration
LUXURY_CATEGORY_NAME = "💎 LUXURY PROFIT FINDS"
AUCTION_CHANNEL_NAME = "💎-auctions-under-60"
BIN_CHANNEL_NAME = "💎-buyitnow-steals"
PROFIT_ALERTS_CHANNEL_NAME = "🚀-profit-alerts"

# Brand styling
LUXURY_BRAND_EMOJIS = {
    "Balenciaga": "⚡",
    "Vetements": "🔥", 
    "Rick Owens": "🖤",
    "Comme Des Garcons": "❤️",
    "Junya Watanabe": "💙",
    "Issey Miyake": "🌀"
}

PROFIT_TIER_EMOJIS = {
    "ultra": "🚀",  # 400%+ ROI
    "high": "💎",   # 300-399% ROI
    "good": "✨",   # 200-299% ROI
    "fair": "📈"    # 100-199% ROI
}

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
bot = commands.Bot(command_prefix='!profit_', intents=intents)

# Batch processing for efficiency
profit_batch_buffer = []
PROFIT_BATCH_SIZE = 3
PROFIT_BATCH_TIMEOUT = 30
last_profit_batch_time = None

@bot.event
async def on_ready():
    logger.info(f'💰 Luxury Profit Discord Bot ready! Logged in as {bot.user}')
    
    try:
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            logger.error(f"❌ Could not find guild with ID {GUILD_ID}")
            return
        
        logger.info(f"✅ Connected to guild: {guild.name}")
        
        # Create channels with profit focus
        category = await ensure_profit_category_exists(guild)
        auction_channel = await ensure_auction_channel_exists(guild, category)
        bin_channel = await ensure_bin_channel_exists(guild, category)
        profit_alerts = await ensure_profit_alerts_channel_exists(guild, category)
        
        logger.info(f"✅ Auction channel ready: #{auction_channel.name}")
        logger.info(f"✅ BIN channel ready: #{bin_channel.name}")
        logger.info(f"✅ Profit alerts ready: #{profit_alerts.name}")
        
        init_subscription_tables()
        
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="luxury profit opportunities 💰"
            )
        )
        
    except Exception as e:
        logger.error(f"❌ Error in on_ready: {e}")

async def ensure_profit_category_exists(guild):
    category = discord.utils.get(guild.categories, name=LUXURY_CATEGORY_NAME)
    
    if not category:
        try:
            category = await guild.create_category(
                LUXURY_CATEGORY_NAME,
                overwrites={
                    guild.default_role: discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=False,
                        add_reactions=True
                    )
                }
            )
            logger.info(f"✅ Created profit category: {LUXURY_CATEGORY_NAME}")
        except Exception as e:
            logger.error(f"❌ Error creating profit category: {e}")
            raise
    
    return category

async def ensure_auction_channel_exists(guild, category):
    channel = discord.utils.get(guild.channels, name=AUCTION_CHANNEL_NAME)
    
    if not channel:
        try:
            channel = await guild.create_text_channel(
                AUCTION_CHANNEL_NAME,
                category=category,
                topic="🔨 High-profit auction finds - Place your bids on underpriced luxury items!",
                overwrites={
                    guild.default_role: discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=False,
                        add_reactions=True
                    )
                }
            )
            logger.info(f"✅ Created auction channel: #{AUCTION_CHANNEL_NAME}")
        except Exception as e:
            logger.error(f"❌ Error creating auction channel: {e}")
            raise
    
    return channel

async def ensure_bin_channel_exists(guild, category):
    channel = discord.utils.get(guild.channels, name=BIN_CHANNEL_NAME)
    
    if not channel:
        try:
            channel = await guild.create_text_channel(
                BIN_CHANNEL_NAME,
                category=category,
                topic="🛒 Buy It Now profit steals - Instant purchase opportunities with high ROI!",
                overwrites={
                    guild.default_role: discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=False,
                        add_reactions=True
                    )
                }
            )
            logger.info(f"✅ Created BIN channel: #{BIN_CHANNEL_NAME}")
        except Exception as e:
            logger.error(f"❌ Error creating BIN channel: {e}")
            raise
    
    return channel

async def ensure_profit_alerts_channel_exists(guild, category):
    channel = discord.utils.get(guild.channels, name=PROFIT_ALERTS_CHANNEL_NAME)
    
    if not channel:
        try:
            channel = await guild.create_text_channel(
                PROFIT_ALERTS_CHANNEL_NAME,
                category=category,
                topic="🚀 Ultra-high profit alerts - 400%+ ROI opportunities!",
                overwrites={
                    guild.default_role: discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=False,
                        add_reactions=True
                    )
                }
            )
            logger.info(f"✅ Created profit alerts channel: #{PROFIT_ALERTS_CHANNEL_NAME}")
        except Exception as e:
            logger.error(f"❌ Error creating profit alerts channel: {e}")
            raise
    
    return channel

def get_profit_tier(roi_percent):
    """Determine profit tier based on ROI"""
    if roi_percent >= 400:
        return "ultra"
    elif roi_percent >= 300:
        return "high"
    elif roi_percent >= 200:
        return "good"
    else:
        return "fair"

def get_brand_color(brand):
    """Get brand-specific colors"""
    colors = {
        "Balenciaga": 0x000000,
        "Vetements": 0xFF0000,
        "Rick Owens": 0x2C2C2C,
        "Comme Des Garcons": 0xFF69B4,
        "Junya Watanabe": 0x4169E1,
        "Issey Miyake": 0x800080
    }
    return colors.get(brand, 0x9932CC)

async def send_profit_listing_embed(channel, listing_data):
    """Send enhanced profit-focused listing embed with error handling"""
    try:
        # Debug: Print the data structure
        logger.info(f"📊 Listing data keys: {list(listing_data.keys())}")
        
        brand = listing_data.get('brand', 'Unknown')
        brand_emoji = LUXURY_BRAND_EMOJIS.get(brand, "💎")
        listing_type = listing_data.get('listing_type', 'unknown')
        
        # Get profit analysis with fallbacks
        profit_analysis = listing_data.get('profit_analysis', {})
        roi_percent = profit_analysis.get('roi_percent', 0)
        estimated_profit = profit_analysis.get('estimated_profit', 0)
        purchase_price = profit_analysis.get('purchase_price', listing_data.get('price_usd', 0))
        estimated_sell_price = profit_analysis.get('estimated_sell_price', 0)
        
        # Ensure we have valid numeric values
        try:
            roi_percent = float(roi_percent) if roi_percent else 0
            estimated_profit = float(estimated_profit) if estimated_profit else 0
            purchase_price = float(purchase_price) if purchase_price else 0
            estimated_sell_price = float(estimated_sell_price) if estimated_sell_price else 0
        except (ValueError, TypeError):
            logger.warning(f"⚠️ Invalid numeric values in profit analysis, using defaults")
            roi_percent = 0
            estimated_profit = 0
            purchase_price = listing_data.get('price_usd', 0)
            estimated_sell_price = 0
        
        # Determine profit tier
        profit_tier = get_profit_tier(roi_percent)
        profit_emoji = PROFIT_TIER_EMOJIS.get(profit_tier, "📈")
        
        # Create title based on listing type and profit
        if listing_type == 'buy_it_now':
            title_prefix = f"🛒 {profit_emoji} INSTANT PROFIT"
        elif listing_type == 'auction':
            title_prefix = f"🔨 {profit_emoji} AUCTION PROFIT"
        else:
            title_prefix = f"💎 {profit_emoji} PROFIT FIND"
        
        # Get title with fallback
        title = listing_data.get('title', 'No title available')
        title_display = title[:150] + ('...' if len(title) > 150 else '')
        
        embed = discord.Embed(
            title=f"{title_prefix} - {brand_emoji} {brand}",
            description=f"**{title_display}**",
            color=get_brand_color(brand),
            timestamp=datetime.now(timezone.utc)
        )
        
        if listing_data.get('image_url'):
            embed.set_thumbnail(url=listing_data['image_url'])
        
        # Profit calculation field (most important)
        try:
            profit_value = f"**Buy:** ${purchase_price:.2f}\n**Sell:** ${estimated_sell_price:.2f}\n**Profit:** ${estimated_profit:.2f}\n**ROI:** {roi_percent:.0f}%"
        except (ValueError, TypeError):
            profit_value = f"**Buy:** ${purchase_price:.2f}\n**Sell:** ${estimated_sell_price}\n**Profit:** ${estimated_profit:.2f}\n**ROI:** {roi_percent:.0f}%"
        
        embed.add_field(
            name="💰 PROFIT CALCULATION",
            value=profit_value,
            inline=True
        )
        
        # Price details with validation
        try:
            price_jpy = float(listing_data.get('price_jpy', 0)) if listing_data.get('price_jpy') else 0
            price_usd = float(listing_data.get('price_usd', 0)) if listing_data.get('price_usd') else 0
        except (ValueError, TypeError):
            logger.warning(f"⚠️ Invalid price values, using defaults")
            price_jpy = 0
            price_usd = 0
        
        embed.add_field(
            name="💴 Yahoo Price",
            value=f"¥{price_jpy:,.0f}\n(${price_usd:.2f})",
            inline=True
        )
        
        # ROI indicator
        if roi_percent >= 400:
            roi_indicator = "🚀 ULTRA PROFIT"
        elif roi_percent >= 300:
            roi_indicator = "💎 HIGH PROFIT"
        elif roi_percent >= 200:
            roi_indicator = "✨ GOOD PROFIT"
        else:
            roi_indicator = "📈 FAIR PROFIT"
        
        embed.add_field(
            name="📊 Opportunity Level",
            value=roi_indicator,
            inline=True
        )
        
        # Build URLs with fallbacks
        auction_id = listing_data.get('auction_id', 'unknown')
        zenmarket_url = listing_data.get('zenmarket_url') or f"https://zenmarket.jp/en/auction.aspx?itemCode={auction_id}"
        yahoo_url = listing_data.get('yahoo_url') or f"https://page.auctions.yahoo.co.jp/jp/auction/{auction_id}"
        
        # Quick purchase links
        embed.add_field(
            name="🔗 QUICK PURCHASE",
            value=f"[ZenMarket BUY NOW]({zenmarket_url})\n[Yahoo Direct]({yahoo_url})",
            inline=False
        )
        
        # Footer with listing type and timing
        if listing_type == 'buy_it_now':
            footer_text = f"🛒 Buy It Now - Instant Purchase Available!"
        elif listing_type == 'auction':
            footer_text = f"🔨 Auction - Place Your Bid Now!"
        else:
            footer_text = f"💎 Profit opportunity detected!"
        
        embed.set_footer(
            text=f"{footer_text} • Target ROI: 200%+",
            icon_url="https://images.emojiterra.com/google/noto-emoji/unicode-15/color/512px/1f4b0.png"
        )
        
        message = await channel.send(embed=embed)
        
        # Add relevant reactions for user interaction
        await message.add_reaction("💰")  # Mark as profitable
        await message.add_reaction("🔖")  # Bookmark
        
        # Store message info for database
        listing_data['message_id'] = message.id
        listing_data['channel_id'] = channel.id
        
        # Save to database
        try:
            success = add_listing(listing_data, message.id)
            if success:
                logger.info(f"✅ Saved to database: {brand} - ROI {roi_percent:.0f}%")
        except Exception as db_error:
            logger.warning(f"⚠️ Database error: {db_error}")
        
        logger.info(f"✅ Sent profit listing: {brand} - ${purchase_price:.2f} → ${estimated_sell_price} ({roi_percent:.0f}% ROI)")
        return message
        
    except Exception as e:
        logger.error(f"❌ Error sending profit listing embed: {e}")
        logger.error(f"❌ Listing data: {listing_data}")
        return None

async def route_listing_to_correct_channel(listing_data):
    """Route listing to the correct channel based on type and profit level"""
    try:
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            logger.error("Guild not found for routing")
            return False
        
        listing_type = listing_data.get('listing_type', 'unknown')
        profit_analysis = listing_data.get('profit_analysis', {})
        roi_percent = profit_analysis.get('roi_percent', 0)
        
        # Route to profit alerts for ultra-high ROI (400%+)
        if roi_percent >= 400:
            target_channel = discord.utils.get(guild.channels, name=PROFIT_ALERTS_CHANNEL_NAME)
            if target_channel:
                await send_profit_listing_embed(target_channel, listing_data)
                logger.info(f"🚀 Sent to PROFIT ALERTS: {roi_percent:.0f}% ROI")
        
        # Route based on listing type
        if listing_type == 'buy_it_now':
            target_channel = discord.utils.get(guild.channels, name=BIN_CHANNEL_NAME)
        elif listing_type == 'auction':
            target_channel = discord.utils.get(guild.channels, name=AUCTION_CHANNEL_NAME)
        else:
            # Default to auction channel for unknown types
            target_channel = discord.utils.get(guild.channels, name=AUCTION_CHANNEL_NAME)
        
        if target_channel:
            await send_profit_listing_embed(target_channel, listing_data)
            return True
        else:
            logger.error(f"Target channel not found for listing type: {listing_type}")
            return False
        
    except Exception as e:
        logger.error(f"❌ Error routing listing: {e}")
        return False

async def send_profit_batch_if_ready():
    """Send batch of profit listings if ready"""
    global profit_batch_buffer, last_profit_batch_time
    
    current_time = time.time()
    should_send = (
        len(profit_batch_buffer) >= PROFIT_BATCH_SIZE or
        (profit_batch_buffer and 
         last_profit_batch_time and 
         current_time - last_profit_batch_time >= PROFIT_BATCH_TIMEOUT)
    )
    
    if not should_send:
        return
    
    try:
        batch_to_send = profit_batch_buffer.copy()
        profit_batch_buffer.clear()
        
        logger.info(f"📦 Sending profit batch of {len(batch_to_send)} items")
        
        for listing_data in batch_to_send:
            await route_listing_to_correct_channel(listing_data)
            await asyncio.sleep(2)  # Rate limiting
        
        last_profit_batch_time = current_time
        
    except Exception as e:
        logger.error(f"❌ Error sending profit batch: {e}")

async def process_single_profit_listing(listing_data):
    """Process a single profit listing with enhanced error handling"""
    global profit_batch_buffer, last_profit_batch_time
    
    try:
        if not listing_data or 'auction_id' not in listing_data:
            logger.error("❌ Invalid profit listing data - missing auction_id")
            logger.error(f"❌ Data received: {listing_data}")
            return
        
        auction_id = listing_data['auction_id']
        
        # Ensure required fields exist with defaults
        if 'zenmarket_url' not in listing_data:
            listing_data['zenmarket_url'] = f"https://zenmarket.jp/en/auction.aspx?itemCode={auction_id}"
            
        if 'yahoo_url' not in listing_data:
            listing_data['yahoo_url'] = f"https://page.auctions.yahoo.co.jp/jp/auction/{auction_id}"
        
        # Check for duplicates
        try:
            existing = db_manager.execute_query(
                'SELECT id FROM listings WHERE auction_id = %s' if db_manager.use_postgres else 
                'SELECT id FROM listings WHERE auction_id = ?',
                (auction_id,),
                fetch_one=True
            )
            
            if existing:
                logger.info(f"🔄 Duplicate profit listing detected, skipping: {auction_id}")
                return
                
        except Exception as e:
            logger.warning(f"⚠️ Could not check duplicates: {e}")
        
        # Add to batch
        profit_batch_buffer.append(listing_data)
        last_profit_batch_time = time.time()
        
        profit_analysis = listing_data.get('profit_analysis', {})
        roi = profit_analysis.get('roi_percent', 0)
        brand = listing_data.get('brand', 'Unknown')
        
        logger.info(f"📥 Added to profit batch: {brand} - {roi:.0f}% ROI")
        
        await send_profit_batch_if_ready()
        
    except Exception as e:
        logger.error(f"❌ Error processing profit listing: {e}")
        logger.error(f"❌ Listing data: {listing_data}")

@bot.event
async def on_reaction_add(reaction, user):
    """Handle user reactions to profit listings"""
    if user.bot:
        return
    
    if reaction.emoji not in ['💰', '🔖', '🚀']:
        return
    
    channel_names = [AUCTION_CHANNEL_NAME, BIN_CHANNEL_NAME, PROFIT_ALERTS_CHANNEL_NAME]
    if reaction.message.channel.name not in channel_names:
        return
    
    try:
        embed = reaction.message.embeds[0] if reaction.message.embeds else None
        if not embed:
            return
        
        auction_id = extract_auction_id_from_embed(embed)
        if not auction_id:
            return
        
        if reaction.emoji == '🔖':
            # Bookmark the listing
            success = add_user_bookmark(
                user.id,
                auction_id,
                reaction.message.id,
                reaction.message.channel.id,
                None
            )
            
            if success:
                logger.info(f"✅ User {user.name} bookmarked profit item {auction_id}")
        
        elif reaction.emoji == '💰':
            logger.info(f"💰 User {user.name} marked profit interest in {auction_id}")
        
        elif reaction.emoji == '🚀':
            logger.info(f"🚀 User {user.name} marked ultra-profit interest in {auction_id}")
    
    except Exception as e:
        logger.error(f"❌ Error handling profit reaction: {e}")

def extract_auction_id_from_embed(embed):
    """Extract auction ID from embed"""
    try:
        for field in embed.fields:
            if "QUICK PURCHASE" in field.name and field.value:
                zenmarket_match = re.search(r'itemCode=([a-zA-Z0-9_-]+)', field.value)
                if zenmarket_match:
                    return zenmarket_match.group(1)
        return None
    except Exception as e:
        logger.error(f"❌ Error extracting auction ID from embed: {e}")
        return None

@bot.command(name='stats')
async def profit_stats(ctx):
    """Show profit statistics"""
    try:
        embed = discord.Embed(
            title="💰 Luxury Profit Statistics",
            color=0xFF6B35,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Get listing counts
        total_listings = db_manager.execute_query(
            'SELECT COUNT(*) FROM listings', 
            fetch_one=True
        )
        
        total_bookmarks = db_manager.execute_query(
            'SELECT COUNT(*) FROM user_bookmarks', 
            fetch_one=True
        )
        
        embed.add_field(
            name="📊 Total Profit Finds",
            value=f"{total_listings[0] if total_listings else 0}",
            inline=True
        )
        
        embed.add_field(
            name="💾 User Bookmarks",
            value=f"{total_bookmarks[0] if total_bookmarks else 0}",
            inline=True
        )
        
        embed.add_field(
            name="🎯 Target Brands",
            value="Balenciaga, Vetements, Rick Owens\nComme Des Garcons, Junya Watanabe, Issey Miyake",
            inline=False
        )
        
        embed.add_field(
            name="💰 Purchase Range",
            value="$0 - $60 USD",
            inline=True
        )
        
        embed.add_field(
            name="🚀 Target ROI",
            value="200%+ minimum",
            inline=True
        )
        
        embed.add_field(
            name="📦 Current Batch",
            value=f"{len(profit_batch_buffer)} pending",
            inline=True
        )
        
        embed.add_field(
            name="📺 Profit Channels",
            value=f"🔨 {AUCTION_CHANNEL_NAME}\n🛒 {BIN_CHANNEL_NAME}\n🚀 {PROFIT_ALERTS_CHANNEL_NAME}",
            inline=False
        )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error getting profit stats: {e}")

@bot.command(name='setup')
async def profit_setup(ctx):
    """Setup user for profit alerts"""
    user_id = ctx.author.id
    
    embed = discord.Embed(
        title="💰 Welcome to Luxury Profit Alerts!",
        description="This bot finds underpriced luxury items with 200%+ ROI potential.",
        color=0xFF6B35
    )
    
    embed.add_field(
        name="🎯 What We Find",
        value="• Items you can buy for $0-60\n• Resell potential $99-999+\n• 200-400%+ ROI opportunities",
        inline=False
    )
    
    embed.add_field(
        name="📺 Channels",
        value=f"🔨 {AUCTION_CHANNEL_NAME} - Auction finds\n🛒 {BIN_CHANNEL_NAME} - Instant buy deals\n🚀 {PROFIT_ALERTS_CHANNEL_NAME} - Ultra-high ROI",
        inline=False
    )
    
    embed.add_field(
        name="💎 Target Brands",
        value="Balenciaga, Vetements, Rick Owens, Comme Des Garcons, Junya Watanabe, Issey Miyake",
        inline=False
    )
    
    embed.add_field(
        name="🔖 How to Use",
        value="React with 💰 for profit interest\nReact with 🔖 to bookmark items\nReact with 🚀 for ultra-profit alerts",
        inline=False
    )
    
    await ctx.send(embed=embed)

def run_profit_flask_app():
    """Run Flask app for webhook handling"""
    app = Flask(__name__)
    
    @app.route('/health')
    def health():
        return jsonify({
            "status": "healthy",
            "service": "luxury_profit_discord_bot",
            "timestamp": datetime.now().isoformat(),
            "bot_ready": bot.is_ready(),
            "batch_size": len(profit_batch_buffer),
            "channels": {
                "auction": AUCTION_CHANNEL_NAME,
                "buy_it_now": BIN_CHANNEL_NAME,
                "profit_alerts": PROFIT_ALERTS_CHANNEL_NAME
            }
        })
    
    @app.route('/webhook/listing', methods=['POST'])
    def webhook_profit_listing():
        """Handle incoming profit listings"""
        try:
            if not request.is_json:
                return jsonify({"error": "Content-Type must be application/json"}), 400
            
            listing_data = request.get_json()
            
            if not listing_data or 'auction_id' not in listing_data:
                return jsonify({"error": "Invalid listing data"}), 400
            
            # Validate profit data
            if not listing_data.get('profit_analysis'):
                return jsonify({"error": "Missing profit analysis"}), 400
            
            if not bot.is_ready():
                return jsonify({"error": "Bot not ready"}), 503
            
            # Process the profit listing
            asyncio.run_coroutine_threadsafe(
                process_single_profit_listing(listing_data), 
                bot.loop
            )
            
            return jsonify({
                "status": "success", 
                "message": "Profit listing received",
                "auction_id": listing_data['auction_id'],
                "roi": listing_data['profit_analysis'].get('roi_percent', 0)
            }), 200
                
        except Exception as e:
            logger.error(f"❌ Profit webhook error: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route('/webhook/test', methods=['POST'])
    def webhook_test():
        """Test endpoint for profit webhook"""
        try:
            test_listing = {
                "auction_id": "test_profit_123",
                "title": "Test Balenciaga T-Shirt Archive Piece",
                "brand": "Balenciaga",
                "price_jpy": 3000,
                "price_usd": 20.00,
                "zenmarket_url": "https://zenmarket.jp/en/auction.aspx?itemCode=test_profit_123",
                "yahoo_url": "https://page.auctions.yahoo.co.jp/jp/auction/test_profit_123",
                "image_url": None,
                "listing_type": "buy_it_now",
                "profit_analysis": {
                    "purchase_price": 20.00,
                    "estimated_sell_price": 99,
                    "estimated_profit": 79.00,
                    "roi_percent": 395,
                    "is_profitable": True
                },
                "estimated_market_value": 99
            }
            
            if bot.is_ready():
                asyncio.run_coroutine_threadsafe(
                    process_single_profit_listing(test_listing), 
                    bot.loop
                )
                return jsonify({"status": "success", "message": "Test profit listing sent"}), 200
            else:
                return jsonify({"error": "Bot not ready"}), 503
                
        except Exception as e:
            logger.error(f"❌ Test webhook error: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route('/stats')
    def api_stats():
        """API endpoint for statistics"""
        return jsonify({
            "service": "luxury_profit_discord_bot",
            "bot_ready": bot.is_ready(),
            "batch_pending": len(profit_batch_buffer),
            "target_brands": ["Balenciaga", "Vetements", "Rick Owens", "Comme Des Garcons", "Junya Watanabe", "Issey Miyake"],
            "minimum_roi": "200%",
            "price_range": "$0-60 USD",
            "channels": {
                "auction": AUCTION_CHANNEL_NAME,
                "buy_it_now": BIN_CHANNEL_NAME,
                "profit_alerts": PROFIT_ALERTS_CHANNEL_NAME
            }
        })
    
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == "__main__":
    try:
        # Start Flask webhook server in background
        flask_thread = threading.Thread(target=run_profit_flask_app, daemon=True)
        flask_thread.start()
        
        logger.info(f"🌐 Profit Flask server started on port {os.environ.get('PORT', 8000)}")
        
        # Run Discord bot
        bot.run(BOT_TOKEN)
        
    except Exception as e:
        logger.error(f"💥 Critical error starting profit bot: {e}")
        exit(1)