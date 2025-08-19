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
    init_subscription_tables, test_postgres_connection
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('luxury_discord_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Duplicate detection tracking
duplicate_detection_stats = {
    "duplicates_by_auction_id": 0,
    "duplicates_by_title_similarity": 0,
    "duplicates_by_price_brand_title": 0,
    "total_duplicates_detected": 0,
    "total_listings_received": 0
}

class LuxuryInputValidator:
    @staticmethod
    def sanitize_username(username: str) -> str:
        if not username:
            return "user"
        safe_username = re.sub(r'[^a-zA-Z0-9\-_]', '', username)
        return safe_username[:20] or "user"
    
    @staticmethod
    def validate_auction_id(auction_id: str) -> bool:
        if not auction_id or len(auction_id) > 50:
            return False
        return bool(re.match(r'^[a-zA-Z0-9_-]+$', auction_id))

def check_luxury_duplicate_in_database(auction_id):
    """Check if luxury item already exists in database by auction ID"""
    try:
        existing = db_manager.execute_query(
            'SELECT id, title, brand, price_usd FROM listings WHERE auction_id = %s' if db_manager.use_postgres else 
            'SELECT id, title, brand, price_usd FROM listings WHERE auction_id = ?',
            (auction_id,),
            fetch_one=True
        )
        return existing
    except Exception as e:
        logger.warning(f"⚠️ Could not check duplicates in database: {e}")
        return None

def check_luxury_duplicate_by_title_similarity(title, brand, price_usd):
    """Check for potential duplicates by title similarity"""
    try:
        # Get recent listings with similar characteristics
        recent_listings = db_manager.execute_query(
            'SELECT title, brand, price_usd FROM listings WHERE brand = %s AND price_usd BETWEEN %s AND %s ORDER BY created_at DESC LIMIT 50' if db_manager.use_postgres else 
            'SELECT title, brand, price_usd FROM listings WHERE brand = ? AND price_usd BETWEEN ? AND ? ORDER BY created_at DESC LIMIT 50',
            (brand, price_usd * 0.8, price_usd * 1.2),
            fetch_one=False
        )
        
        if not recent_listings:
            return False, None
        
        title_lower = title.lower()
        for listing in recent_listings:
            existing_title = listing[0].lower()
            
            # Simple similarity check - if titles are very similar
            if calculate_title_similarity(title_lower, existing_title) > 0.85:
                return True, existing_title
        
        return False, None
        
    except Exception as e:
        logger.warning(f"⚠️ Could not check title similarity: {e}")
        return False, None

def calculate_title_similarity(title1, title2):
    """Calculate similarity between two titles using word overlap"""
    if not title1 or not title2:
        return 0.0
    
    # Convert to sets of words for better comparison
    words1 = set(title1.split())
    words2 = set(title2.split())
    
    if not words1 or not words2:
        return 0.0
    
    # Calculate Jaccard similarity
    intersection = len(words1.intersection(words2))
    union = len(words1.union(words2))
    
    if union == 0:
        return 0.0
    
    return intersection / union

def is_luxury_duplicate(listing_data):
    """Enhanced duplicate detection using multiple criteria"""
    auction_id = listing_data.get('auction_id')
    title = listing_data.get('title', '')
    brand = listing_data.get('brand', '')
    price_usd = listing_data.get('price_usd', 0)
    
    duplicate_detection_stats["total_listings_received"] += 1
    
    # Primary check: auction_id (most reliable)
    existing_listing = check_luxury_duplicate_in_database(auction_id)
    if existing_listing:
        duplicate_detection_stats["duplicates_by_auction_id"] += 1
        duplicate_detection_stats["total_duplicates_detected"] += 1
        logger.info(f"🔄 Duplicate by auction_id: {auction_id} - {title[:50]}...")
        return True, "auction_id", existing_listing
    
    # Secondary check: title similarity for same brand
    if brand and title and price_usd:
        is_similar, existing_title = check_luxury_duplicate_by_title_similarity(title, brand, price_usd)
        if is_similar:
            duplicate_detection_stats["duplicates_by_title_similarity"] += 1
            duplicate_detection_stats["total_duplicates_detected"] += 1
            logger.info(f"🔄 Duplicate by title similarity: {title[:50]}... vs {existing_title[:50]}...")
            return True, "title_similarity", {"title": existing_title}
    
    # Tertiary check: price + brand + title start combination
    if brand and title and price_usd:
        try:
            similar_listings = db_manager.execute_query(
                'SELECT title FROM listings WHERE brand = %s AND ABS(price_usd - %s) < 1.0 AND title LIKE %s LIMIT 5' if db_manager.use_postgres else 
                'SELECT title FROM listings WHERE brand = ? AND ABS(price_usd - ?) < 1.0 AND title LIKE ? LIMIT 5',
                (brand, price_usd, f"{title[:20]}%"),
                fetch_one=False
            )
            
            if similar_listings:
                duplicate_detection_stats["duplicates_by_price_brand_title"] += 1
                duplicate_detection_stats["total_duplicates_detected"] += 1
                logger.info(f"🔄 Duplicate by price+brand+title: {title[:50]}...")
                return True, "price_brand_title", {"similar_titles": [l[0] for l in similar_listings]}
                
        except Exception as e:
            logger.warning(f"⚠️ Could not check price+brand+title similarity: {e}")
    
    return False, None, None

def get_duplicate_detection_stats():
    """Get current duplicate detection statistics"""
    return {
        **duplicate_detection_stats,
        "duplicate_rate": (duplicate_detection_stats["total_duplicates_detected"] / 
                          max(duplicate_detection_stats["total_listings_received"], 1)) * 100
    }

def load_luxury_config():
    bot_token = os.environ.get('DISCORD_BOT_TOKEN')
    guild_id = os.environ.get('GUILD_ID')
    
    if not bot_token:
        logger.error("❌ DISCORD_BOT_TOKEN environment variable not set!")
        exit(1)
    
    if not guild_id:
        logger.error("❌ GUILD_ID environment variable not set!")
        exit(1)
    
    if len(bot_token) < 50 or not bot_token.startswith(('M', 'N', 'O')):
        logger.error("❌ Invalid Discord bot token format!")
        exit(1)
    
    logger.info("✅ Luxury bot configuration loaded successfully")
    
    return {
        'bot_token': bot_token,
        'guild_id': int(guild_id)
    }

try:
    config = load_luxury_config()
    BOT_TOKEN = config['bot_token']
    GUILD_ID = config['guild_id']
except Exception as e:
    logger.error(f"❌ Failed to load config: {e}")
    exit(1)

LUXURY_CATEGORY_NAME = "💎 LUXURY STEALS"
LUXURY_CHANNEL_NAME = "💎-luxury-under-60"

LUXURY_PROXIES = {
    "zenmarket": {
        "name": "ZenMarket",
        "emoji": "🛒",
        "url_template": "https://zenmarket.jp/en/auction.aspx?itemCode={auction_id}",
        "description": "Popular proxy with English support"
    },
    "buyee": {
        "name": "Buyee", 
        "emoji": "📦",
        "url_template": "https://buyee.jp/item/yahoo/auction/{auction_id}",
        "description": "Official Yahoo Auctions partner"
    },
    "yahoo_japan": {
        "name": "Yahoo Japan Direct",
        "emoji": "🇯🇵", 
        "url_template": "https://page.auctions.yahoo.co.jp/jp/auction/{auction_id}",
        "description": "Direct access (requires Japanese address)"
    }
}

LUXURY_BRAND_EMOJIS = {
    "Balenciaga": "⚡",
    "Vetements": "🔥", 
    "Rick Owens": "🖤",
    "Comme Des Garcons": "❤️",
    "Junya Watanabe": "💙"
}

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
bot = commands.Bot(command_prefix='!luxury_', intents=intents)

luxury_batch_buffer = []
LUXURY_BATCH_SIZE = 5
LUXURY_BATCH_TIMEOUT = 45
last_luxury_batch_time = None

luxury_input_validator = LuxuryInputValidator()

@bot.event
async def on_ready():
    logger.info(f'🤖 Luxury Discord Bot ready! Logged in as {bot.user}')
    
    try:
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            logger.error(f"❌ Could not find guild with ID {GUILD_ID}")
            return
        
        logger.info(f"✅ Connected to guild: {guild.name}")
        
        luxury_category = await ensure_luxury_category_exists(guild)
        luxury_channel = await ensure_luxury_channel_exists(guild, luxury_category)
        
        logger.info(f"✅ Luxury channel ready: #{luxury_channel.name}")
        
        init_subscription_tables()
        
        # Log duplicate detection system status
        logger.info("🔄 Enhanced duplicate detection system enabled")
        logger.info("   - Auction ID checking")
        logger.info("   - Title similarity detection (85%+ threshold)")
        logger.info("   - Price+Brand+Title combination checking")
        
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="luxury fashion steals under $60"
            )
        )
        
    except Exception as e:
        logger.error(f"❌ Error in on_ready: {e}")

async def ensure_luxury_category_exists(guild):
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
            logger.info(f"✅ Created luxury category: {LUXURY_CATEGORY_NAME}")
        except Exception as e:
            logger.error(f"❌ Error creating luxury category: {e}")
            raise
    
    return category

async def ensure_luxury_channel_exists(guild, category):
    channel = discord.utils.get(guild.channels, name=LUXURY_CHANNEL_NAME)
    
    if not channel:
        try:
            channel = await guild.create_text_channel(
                LUXURY_CHANNEL_NAME,
                category=category,
                topic="High-end fashion finds under $60 - React with 👍 to bookmark!",
                overwrites={
                    guild.default_role: discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=False,
                        add_reactions=True
                    )
                }
            )
            logger.info(f"✅ Created luxury channel: #{LUXURY_CHANNEL_NAME}")
        except Exception as e:
            logger.error(f"❌ Error creating luxury channel: {e}")
            raise
    
    return channel

async def send_luxury_listing_embed(channel, listing_data):
    brand = listing_data.get('brand', 'Unknown')
    brand_emoji = LUXURY_BRAND_EMOJIS.get(brand, "💎")
    
    embed = discord.Embed(
        title=f"{brand_emoji} {brand} - ${listing_data['price_usd']:.2f}",
        description=listing_data['title'][:200] + ("..." if len(listing_data['title']) > 200 else ""),
        color=get_luxury_brand_color(brand),
        timestamp=datetime.now(timezone.utc)
    )
    
    if listing_data.get('image_url'):
        embed.set_thumbnail(url=listing_data['image_url'])
    
    embed.add_field(
        name="💰 Price",
        value=f"¥{listing_data['price_jpy']:,} (~${listing_data['price_usd']:.2f})",
        inline=True
    )
    
    quality_score = listing_data.get('deal_quality', 0.5)
    quality_text = get_quality_indicator(quality_score)
    
    embed.add_field(
        name="📊 Deal Quality",
        value=quality_text,
        inline=True
    )
    
    embed.add_field(
        name="🔗 Quick Buy",
        value=f"[ZenMarket]({listing_data['zenmarket_url']}) | [Yahoo Direct]({listing_data['yahoo_url']})",
        inline=False
    )
    
    embed.set_footer(
        text="React with 👍 to bookmark • 💎 Luxury steals under $60",
        icon_url="https://images.emojiterra.com/google/noto-emoji/unicode-15/color/512px/1f48e.png"
    )
    
    try:
        message = await channel.send(embed=embed)
        
        # Don't add any automatic reactions - let users react naturally
        
        listing_data['message_id'] = message.id
        listing_data['channel_id'] = channel.id
        
        # Fix the add_listing call - use correct parameters
        try:
            add_listing(
                listing_data['auction_id'],
                listing_data['title'],
                listing_data['brand'],
                listing_data['price_jpy'],
                listing_data['price_usd'],
                listing_data.get('seller_id', 'unknown'),
                listing_data['zenmarket_url'],
                listing_data['yahoo_url'],
                listing_data.get('image_url'),
                listing_data['deal_quality'],
                message.id,
                listing_data.get('auction_end_time')
            )
        except Exception as db_error:
            logger.warning(f"⚠️ Database error (non-critical): {db_error}")
        
        logger.info(f"✅ Sent luxury listing: {brand} - ${listing_data['price_usd']:.2f}")
        return message
        
    except Exception as e:
        logger.error(f"❌ Error sending luxury listing: {e}")
        return None

def get_luxury_brand_color(brand):
    colors = {
        "Balenciaga": 0x000000,
        "Vetements": 0xFF0000,
        "Rick Owens": 0x2C2C2C,
        "Comme Des Garcons": 0xFF69B4,
        "Junya Watanabe": 0x4169E1
    }
    return colors.get(brand, 0x9932CC)

def get_quality_indicator(quality_score):
    if quality_score >= 0.8:
        return "🔥 STEAL"
    elif quality_score >= 0.6:
        return "✨ Good Deal"
    elif quality_score >= 0.4:
        return "📈 Fair Price"
    else:
        return "💸 Pricey"

async def send_luxury_batch_if_ready():
    global luxury_batch_buffer, last_luxury_batch_time
    
    current_time = time.time()
    should_send = (
        len(luxury_batch_buffer) >= LUXURY_BATCH_SIZE or
        (luxury_batch_buffer and 
         last_luxury_batch_time and 
         current_time - last_luxury_batch_time >= LUXURY_BATCH_TIMEOUT)
    )
    
    if not should_send:
        return
    
    try:
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            return
        
        channel = discord.utils.get(guild.channels, name=LUXURY_CHANNEL_NAME)
        if not channel:
            return
        
        batch_to_send = luxury_batch_buffer.copy()
        luxury_batch_buffer.clear()
        
        logger.info(f"📦 Sending luxury batch of {len(batch_to_send)} items")
        
        for listing_data in batch_to_send:
            await send_luxury_listing_embed(channel, listing_data)
            await asyncio.sleep(2)
        
        last_luxury_batch_time = current_time
        
    except Exception as e:
        logger.error(f"❌ Error sending luxury batch: {e}")

async def send_single_luxury_listing(listing_data):
    global luxury_batch_buffer, last_luxury_batch_time
    
    if not listing_data or 'auction_id' not in listing_data:
        logger.error("❌ Invalid luxury listing data")
        return
    
    auction_id = listing_data['auction_id']
    if not luxury_input_validator.validate_auction_id(auction_id):
        logger.error(f"❌ Invalid auction ID: {auction_id}")
        return
    
    # Enhanced duplicate detection
    is_duplicate, reason, existing_data = is_luxury_duplicate(listing_data)
    
    if is_duplicate:
        logger.info(f"🔄 Duplicate luxury listing detected and skipped: {auction_id} - {listing_data.get('title', 'Unknown')[:50]}... (Reason: {reason})")
        
        # Log duplicate details for monitoring
        if existing_data:
            if reason == "auction_id":
                logger.debug(f"   Existing: {existing_data[1]} - {existing_data[2]} - ${existing_data[3]:.2f}")
            elif reason == "title_similarity":
                logger.debug(f"   Similar to: {existing_data['title']}")
            elif reason == "price_brand_title":
                logger.debug(f"   Similar titles: {', '.join(existing_data['similar_titles'][:3])}")
        
        return
    
    # Not a duplicate, add to batch
    luxury_batch_buffer.append(listing_data)
    last_luxury_batch_time = time.time()
    
    logger.info(f"📥 Added to luxury batch: {listing_data.get('brand', 'Unknown')} - ${listing_data.get('price_usd', 0):.2f}")
    
    await send_luxury_batch_if_ready()

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return
    
    if reaction.emoji not in ['👍', '👎', '💎']:
        return
    
    if reaction.message.channel.name != LUXURY_CHANNEL_NAME:
        return
    
    try:
        embed = reaction.message.embeds[0] if reaction.message.embeds else None
        if not embed:
            return
        
        auction_id = extract_auction_id_from_luxury_embed(embed)
        if not auction_id:
            return
        
        if reaction.emoji == '👍':
            success = add_user_bookmark(
                user.id,
                auction_id,
                reaction.message.id,
                reaction.message.channel.id,
                None
            )
            
            if success:
                logger.info(f"✅ User {user.name} bookmarked luxury item {auction_id}")
            else:
                logger.warning(f"⚠️ Failed to bookmark luxury item {auction_id} for {user.name}")
        
        elif reaction.emoji == '💎':
            logger.info(f"💎 User {user.name} marked luxury item {auction_id} as premium")
    
    except Exception as e:
        logger.error(f"❌ Error handling luxury reaction: {e}")

def extract_auction_id_from_luxury_embed(embed):
    try:
        for field in embed.fields:
            if "Quick Buy" in field.name and field.value:
                zenmarket_match = re.search(r'itemCode=([a-zA-Z0-9_-]+)', field.value)
                if zenmarket_match:
                    return zenmarket_match.group(1)
        return None
    except Exception as e:
        logger.error(f"❌ Error extracting auction ID from luxury embed: {e}")
        return None

@bot.command(name='setup')
async def luxury_setup(ctx):
    user_id = ctx.author.id
    
    existing_preference = get_user_proxy_preference(user_id)
    if existing_preference:
        embed = discord.Embed(
            title="⚙️ Already Set Up!",
            description=f"You're already using **{existing_preference}**",
            color=0x00ff00
        )
        await ctx.send(embed=embed)
        return
    
    embed = discord.Embed(
        title="💎 Welcome to Luxury Fashion Alerts!",
        description="Choose your preferred proxy service to buy from Yahoo Auctions:",
        color=0x9932CC
    )
    
    for proxy_key, proxy_info in LUXURY_PROXIES.items():
        embed.add_field(
            name=f"{proxy_info['emoji']} {proxy_info['name']}",
            value=proxy_info['description'],
            inline=False
        )
    
    embed.set_footer(text="React with the emoji of your preferred service")
    
    message = await ctx.send(embed=embed)
    
    for proxy_info in LUXURY_PROXIES.values():
        await message.add_reaction(proxy_info['emoji'])

@bot.command(name='stats')
async def luxury_stats(ctx):
    try:
        total_listings = db_manager.execute_query(
            'SELECT COUNT(*) FROM listings WHERE brand IN (%s, %s, %s, %s, %s)' if db_manager.use_postgres else 
            'SELECT COUNT(*) FROM listings WHERE brand IN (?, ?, ?, ?, ?)',
            ('Balenciaga', 'Vetements', 'Rick Owens', 'Comme Des Garcons', 'Junya Watanabe'),
            fetch_one=True
        )
        
        total_bookmarks = db_manager.execute_query(
            'SELECT COUNT(*) FROM user_bookmarks', 
            fetch_one=True
        )
        
        # Get duplicate detection stats
        duplicate_stats = get_duplicate_detection_stats()
        
        embed = discord.Embed(
            title="💎 Luxury Channel Statistics",
            color=0x9932CC,
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="📊 Total Luxury Listings",
            value=f"{total_listings[0] if total_listings else 0}",
            inline=True
        )
        
        embed.add_field(
            name="💾 Total Bookmarks",
            value=f"{total_bookmarks[0] if total_bookmarks else 0}",
            inline=True
        )
        
        embed.add_field(
            name="🎯 Target Brands",
            value="Balenciaga, Vetements, Rick Owens\nComme Des Garcons, Junya Watanabe",
            inline=False
        )
        
        embed.add_field(
            name="💰 Price Range",
            value="$15 - $60 USD",
            inline=True
        )
        
        embed.add_field(
            name="📦 Batch Size",
            value=f"{len(luxury_batch_buffer)} pending",
            inline=True
        )
        
        # Add duplicate detection stats
        if duplicate_stats["total_listings_received"] > 0:
            embed.add_field(
                name="🔄 Duplicate Detection",
                value=f"Rate: {duplicate_stats['duplicate_rate']:.1f}%\nTotal: {duplicate_stats['total_duplicates_detected']}",
                inline=True
            )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error getting stats: {e}")

@bot.command(name='duplicates')
async def luxury_duplicates(ctx):
    """Show detailed duplicate detection statistics"""
    try:
        duplicate_stats = get_duplicate_detection_stats()
        
        embed = discord.Embed(
            title="🔄 Luxury Duplicate Detection Statistics",
            color=0xFF6B6B,
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="📊 Overall Stats",
            value=f"**Total Received:** {duplicate_stats['total_listings_received']}\n**Total Duplicates:** {duplicate_stats['total_duplicates_detected']}\n**Duplicate Rate:** {duplicate_stats['duplicate_rate']:.1f}%",
            inline=False
        )
        
        embed.add_field(
            name="🔍 Detection Methods",
            value=f"**By Auction ID:** {duplicate_stats['duplicates_by_auction_id']}\n**By Title Similarity:** {duplicate_stats['duplicates_by_title_similarity']}\n**By Price+Brand+Title:** {duplicate_stats['duplicates_by_price_brand_title']}",
            inline=False
        )
        
        embed.add_field(
            name="💡 How It Works",
            value="1. **Auction ID Check** - Most reliable\n2. **Title Similarity** - 85%+ word overlap\n3. **Price+Brand+Title** - Combination check",
            inline=False
        )
        
        embed.set_footer(text="🔄 Duplicate detection prevents spam and ensures quality")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error getting duplicate stats: {e}")

@bot.command(name='reset_duplicates')
async def reset_duplicate_stats(ctx):
    """Reset duplicate detection statistics (Admin only)"""
    try:
        # Check if user has admin permissions
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ You need administrator permissions to reset duplicate statistics.")
            return
        
        global duplicate_detection_stats
        duplicate_detection_stats = {
            "duplicates_by_auction_id": 0,
            "duplicates_by_title_similarity": 0,
            "duplicates_by_price_brand_title": 0,
            "total_duplicates_detected": 0,
            "total_listings_received": 0
        }
        
        embed = discord.Embed(
            title="🔄 Duplicate Detection Statistics Reset",
            description="All duplicate detection statistics have been reset to zero.",
            color=0x00FF00,
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="📊 New Stats",
            value="All counters reset to 0",
            inline=False
        )
        
        embed.set_footer(text="Statistics will start counting from this point forward")
        
        await ctx.send(embed=embed)
        logger.info(f"🔄 Duplicate detection statistics reset by {ctx.author.name}")
        
    except Exception as e:
        await ctx.send(f"❌ Error resetting duplicate stats: {e}")

def run_luxury_flask_app():
    app = Flask(__name__)
    
    @app.route('/health')
    def health():
        duplicate_stats = get_duplicate_detection_stats()
        return jsonify({
            "status": "healthy",
            "service": "luxury_discord_bot",
            "timestamp": datetime.now().isoformat(),
            "bot_ready": bot.is_ready(),
            "batch_size": len(luxury_batch_buffer),
            "duplicate_detection": {
                "enabled": True,
                "total_received": duplicate_stats["total_listings_received"],
                "total_duplicates": duplicate_stats["total_duplicates_detected"],
                "duplicate_rate": duplicate_stats["duplicate_rate"]
            }
        })
    
    @app.route('/webhook/luxury_listing', methods=['POST'])
    def webhook_luxury_listing():
        try:
            if not request.is_json:
                return jsonify({"error": "Content-Type must be application/json"}), 400
            
            listing_data = request.get_json()
            
            if not listing_data or 'auction_id' not in listing_data:
                return jsonify({"error": "Invalid listing data"}), 400
            
            if bot.is_ready():
                asyncio.run_coroutine_threadsafe(
                    send_single_luxury_listing(listing_data), 
                    bot.loop
                )
                return jsonify({"status": "success", "message": "Luxury listing received"}), 200
            else:
                return jsonify({"error": "Bot not ready"}), 503
                
        except Exception as e:
            logger.error(f"❌ Luxury webhook error: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route('/webhook/health')
    def webhook_health():
        return jsonify({
            "status": "healthy",
            "webhook": "luxury_listing",
            "bot_ready": bot.is_ready()
        })
    
    @app.route('/duplicates')
    def duplicates():
        """Detailed duplicate detection information via API"""
        duplicate_stats = get_duplicate_detection_stats()
        return jsonify({
            "duplicate_detection": {
                "enabled": True,
                "stats": duplicate_stats,
                "methods": {
                    "auction_id": "Primary method - checks if auction ID already exists",
                    "title_similarity": "Secondary method - fuzzy title matching (85%+ similarity)",
                    "price_brand_title": "Tertiary method - combination of price, brand, and title start"
                },
                "thresholds": {
                    "title_similarity": 0.85,
                    "price_tolerance": 1.0,
                    "title_start_length": 20
                }
            }
        })
    
    port = int(os.environ.get('PORT', 8002))
    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == "__main__":
    try:
        test_postgres_connection()
        
        flask_thread = threading.Thread(target=run_luxury_flask_app, daemon=True)
        flask_thread.start()
        
        logger.info(f"🌐 Luxury Flask server started on port {os.environ.get('PORT', 8002)}")
        
        bot.run(BOT_TOKEN)
        
    except Exception as e:
        logger.error(f"💥 Critical error starting luxury bot: {e}")
        exit(1)