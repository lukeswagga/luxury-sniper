#!/usr/bin/env python3

import requests
import time
import json
import os
import threading
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import re
import random
from flask import Flask, jsonify
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BRANDS_FILE = "brands_grizzly.json"
SEEN_FILE = "seen_grizzly_items.json"
EXCHANGE_RATE_FILE = "exchange_rate.json"
GRIZZLY_FINDS_FILE = "grizzly_finds.json"
CONVERSATION_LOG_FILE = "grizzly_conversation_log.json"

def check_if_grizzly_item_exists_in_db(auction_id):
    """Check if grizzly jacket item already exists in database or local storage"""
    try:
        # Check local JSON storage first (fast)
        if os.path.exists(GRIZZLY_FINDS_FILE):
            with open(GRIZZLY_FINDS_FILE, 'r', encoding='utf-8') as f:
                finds = json.load(f)
                for find in finds:
                    if find.get('auction_id') == auction_id:
                        return True
        
        return False
        
    except Exception as e:
        logger.warning(f"Error checking duplicate: {e}")
        return False

def save_grizzly_find_to_file(listing_data):
    """Save grizzly jacket finds to a JSON file for review"""
    try:
        finds = []
        if os.path.exists(GRIZZLY_FINDS_FILE):
            with open(GRIZZLY_FINDS_FILE, 'r', encoding='utf-8') as f:
                finds = json.load(f)
        
        # Add timestamp
        listing_data['found_at'] = datetime.now().isoformat()
        finds.append(listing_data)
        
        # Keep only last 100 finds
        finds = finds[-100:]
        
        with open(GRIZZLY_FINDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(finds, f, ensure_ascii=False, indent=2)
        
        logger.info(f"💾 Saved grizzly jacket find to {GRIZZLY_FINDS_FILE}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving grizzly jacket find: {e}")
        return False

USE_DISCORD_BOT = os.environ.get('USE_DISCORD_BOT', 'false').lower() == 'true'
DISCORD_BOT_URL = os.environ.get('DISCORD_BOT_URL', 'http://localhost:8002')
MAX_PRICE_USD = 500  # Higher max price for grizzly jackets
MIN_PRICE_USD = 0.50  # Very low minimum to catch everything

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
]

def load_exchange_rate():
    global exchange_rate_cache
    try:
        if os.path.exists(EXCHANGE_RATE_FILE):
            with open(EXCHANGE_RATE_FILE, 'r') as f:
                exchange_rate_cache = json.load(f)
        else:
            # Set default rate
            exchange_rate_cache = {"rate": 147.0, "last_updated": "2024-01-01"}
    except Exception as e:
        logger.error(f"Error loading exchange rate: {e}")
        exchange_rate_cache = {"rate": 147.0, "last_updated": "2024-01-01"}

def save_exchange_rate():
    try:
        with open(EXCHANGE_RATE_FILE, 'w') as f:
            json.dump(exchange_rate_cache, f)
    except Exception as e:
        logger.error(f"Error saving exchange rate: {e}")

load_exchange_rate()  # Load exchange rate on startup

class ConversationLog:
    def __init__(self):
        self.log = []
        self.load_log()
    
    def load_log(self):
        try:
            if os.path.exists(CONVERSATION_LOG_FILE):
                with open(CONVERSATION_LOG_FILE, 'r', encoding='utf-8') as f:
                    self.log = json.load(f)
                logger.info(f"Loaded {len(self.log)} conversation entries")
        except Exception as e:
            logger.error(f"Error loading conversation log: {e}")
            self.log = []
    
    def save_log(self):
        try:
            with open(CONVERSATION_LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.log[-1000:], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving conversation log: {e}")
    
    def add_entry(self, entry_type, data):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": entry_type,
            "data": data
        }
        self.log.append(entry)
        
        if len(self.log) % 10 == 0:
            self.save_log()
    
    def get_recent_hallucinations(self, hours=24):
        cutoff = datetime.now() - timedelta(hours=hours)
        return [entry for entry in self.log 
                if entry.get('type') == 'hallucination' 
                and datetime.fromisoformat(entry['timestamp']) > cutoff]

conversation_log = ConversationLog()

def load_brand_data():
    try:
        with open(BRANDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"❌ {BRANDS_FILE} not found! Please create it first.")
        return {}

def load_seen_ids():
    try:
        if os.path.exists(SEEN_FILE):
            with open(SEEN_FILE, 'r') as f:
                return set(json.load(f))
    except Exception as e:
        logger.error(f"Error loading seen IDs: {e}")
    return set()

def save_seen_ids(seen_ids):
    try:
        with open(SEEN_FILE, 'w') as f:
            json.dump(list(seen_ids), f)
    except Exception as e:
        logger.error(f"Error saving seen IDs: {e}")

def convert_jpy_to_usd(jpy_price):
    return jpy_price / exchange_rate_cache["rate"]

def extract_price_from_text(price_text):
    if not price_text:
        return None
    
    price_text = price_text.replace(',', '').replace('¥', '').replace('円', '')
    match = re.search(r'(\d+)', price_text)
    
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None

def is_grizzly_jacket(title, brand_data):
    """Check if the title contains grizzly jacket keywords"""
    title_lower = title.lower()
    
    # Must contain "grizzly" or "グリズリー"
    grizzly_keywords = ['grizzly', 'グリズリー', 'グリズリ']
    has_grizzly = any(keyword in title_lower for keyword in grizzly_keywords)
    
    if not has_grizzly:
        return False
    
    # Must contain jacket-related keywords
    jacket_keywords = ['jacket', 'ジャケット', 'coat', 'コート']
    has_jacket = any(keyword in title_lower for keyword in jacket_keywords)
    
    if not has_jacket:
        return False
    
    # Check if it matches one of our brands
    for brand, data in brand_data.items():
        variants = data.get('variants', [brand])
        for variant in variants:
            if variant.lower() in title_lower:
                return True
    
    return False

def calculate_grizzly_deal_quality(price_usd, brand, title, brand_data):
    """Calculate deal quality for grizzly jackets"""
    title_lower = title.lower()
    
    # Base price for grizzly jackets (typically expensive items)
    base_price = 200
    
    # Brand multipliers
    brand_multipliers = {
        "Y's": 1.2,
        "The Real Mccoys": 1.3,
        "Attractions": 1.1
    }
    
    brand_multiplier = brand_multipliers.get(brand, 1.0)
    market_price = base_price * brand_multiplier
    
    if price_usd >= market_price * 1.3:
        quality = 0.3
    elif price_usd >= market_price:
        quality = 0.6
    else:
        quality = min(1.0, 0.9 + (market_price - price_usd) / market_price)
    
    # Archive/vintage boost
    archive_boost = 0.1 if any(term in title_lower for term in ["archive", "rare", "vintage", "fw", "ss"]) else 0
    
    return max(0.0, min(1.0, quality + archive_boost))

def is_grizzly_quality_listing(price_usd, brand, title, brand_data):
    """Check if listing meets quality criteria for grizzly jackets"""
    if price_usd < MIN_PRICE_USD or price_usd > MAX_PRICE_USD:
        return False, f"Price ${price_usd:.2f} outside range ${MIN_PRICE_USD}-{MAX_PRICE_USD}"
    
    if not is_grizzly_jacket(title, brand_data):
        return False, "Not a grizzly jacket from target brands"
    
    deal_quality = calculate_grizzly_deal_quality(price_usd, brand, title, brand_data)
    
    if deal_quality < 0.4:
        return False, f"Low deal quality: {deal_quality:.2f}"
    
    return True, f"Quality score: {deal_quality:.2f}"

def generate_grizzly_keywords(brand_data):
    """Generate keywords specifically for Grizzly Jacket searches"""
    keywords = []
    
    # Grizzly jacket variations
    grizzly_terms = ["grizzly", "グリズリー", "グリズリ"]
    jacket_terms = ["jacket", "ジャケット"]
    
    for brand, data in brand_data.items():
        variants = data.get('variants', [brand])
        
        # Add brand + grizzly + jacket combinations
        for variant in variants[:3]:  # Top 3 variants
            for grizzly_term in grizzly_terms:
                for jacket_term in jacket_terms:
                    keywords.append(f"{variant} {grizzly_term} {jacket_term}")
                    keywords.append(f"{grizzly_term} {jacket_term} {variant}")
        
        # Add just brand + grizzly (jacket implied)
        for variant in variants[:2]:  # Top 2 variants
            for grizzly_term in grizzly_terms:
                keywords.append(f"{variant} {grizzly_term}")
                keywords.append(f"{grizzly_term} {variant}")
    
    # Remove duplicates and return
    return list(set(keywords))

BANNED_KEYWORDS = {
    'de travail', 'julius', 'kmrii', 'ifsixwasnine', 'groundy', 'fred perry', 
    'play', 'tornado', 'midas', 'civarize', 'l.g.b.', 'yeezy', 'yzy', 
    'gap', 'zara', 'uniqlo', 'ユニクロ', 'ザラ', 'ギャップ', 'フレッドペリー'
}

def has_banned_keywords(title):
    """Check if title contains any banned keywords"""
    title_lower = title.lower()
    for banned in BANNED_KEYWORDS:
        if banned in title_lower:
            return True, banned
    return False, None

def check_listing_type_enhanced(auction_id):
    """Enhanced Buy It Now detection with multiple methods and better accuracy"""
    try:
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        
        # Method 1: Direct Yahoo Auctions page check (most reliable)
        yahoo_url = f"https://page.auctions.yahoo.co.jp/jp/auction/{auction_id}"
        
        try:
            yahoo_response = requests.get(yahoo_url, headers=headers, timeout=12)
            
            if yahoo_response.status_code == 200:
                yahoo_content = yahoo_response.text
                
                # Strong BIN indicators on Yahoo
                strong_bin_indicators = [
                    'フリマ',  # Flea market (always BIN)
                    'fixedprice',  # Fixed price parameter
                    'immediate_price',  # Immediate price
                    'buynow_price',  # Buy now price
                    '即決価格',  # Immediate decision price
                    '定額',  # Fixed amount
                ]
                
                # Strong auction indicators
                strong_auction_indicators = [
                    '入札件数',  # Number of bids
                    '現在価格',  # Current price (in auctions)
                    '残り時間',  # Time remaining
                    'bidding',
                    '入札する',  # Place bid button
                    'オークション終了',  # Auction end
                ]
                
                bin_count = sum(1 for indicator in strong_bin_indicators if indicator in yahoo_content)
                auction_count = sum(1 for indicator in strong_auction_indicators if indicator in yahoo_content)
                
                logger.debug(f"Yahoo check for {auction_id}: BIN signals={bin_count}, Auction signals={auction_count}")
                
                if bin_count > 0 and auction_count == 0:
                    return 'buy_it_now'
                elif auction_count > 0 and bin_count == 0:
                    return 'auction'
                elif bin_count > auction_count:
                    return 'buy_it_now'
                elif auction_count > bin_count:
                    return 'auction'
                
        except Exception as yahoo_error:
            logger.debug(f"Yahoo check failed for {auction_id}: {yahoo_error}")
        
        # Method 2: ZenMarket page check (backup)
        time.sleep(0.5)  # Rate limiting
        
        zenmarket_url = f"https://zenmarket.jp/en/auction.aspx?itemCode={auction_id}"
        
        try:
            zenmarket_response = requests.get(zenmarket_url, headers=headers, timeout=12)
            
            if zenmarket_response.status_code == 200:
                zen_content = zenmarket_response.text.lower()
                
                # ZenMarket BIN indicators
                zen_bin_indicators = [
                    'buyout price',
                    'buy now price', 
                    'fixed price',
                    'immediate purchase',
                    'instant buy',
                    'direct purchase',
                    'fixed amount'
                ]
                
                # ZenMarket auction indicators
                zen_auction_indicators = [
                    'current bid',
                    'highest bid',
                    'bidding ends',
                    'auction ends',
                    'time left',
                    'place bid',
                    'bid now',
                    'minimum bid'
                ]
                
                zen_bin_count = sum(1 for indicator in zen_bin_indicators if indicator in zen_content)
                zen_auction_count = sum(1 for indicator in zen_auction_indicators if indicator in zen_content)
                
                logger.debug(f"ZenMarket check for {auction_id}: BIN signals={zen_bin_count}, Auction signals={zen_auction_count}")
                
                if zen_bin_count > 0 and zen_auction_count == 0:
                    return 'buy_it_now'
                elif zen_auction_count > 0 and zen_bin_count == 0:
                    return 'auction'
                elif zen_bin_count > zen_auction_count:
                    return 'buy_it_now'
                elif zen_auction_count > zen_bin_count:
                    return 'auction'
                
        except Exception as zen_error:
            logger.debug(f"ZenMarket check failed for {auction_id}: {zen_error}")
        
        # Method 3: URL pattern analysis (last resort)
        if 'fixedprice' in auction_id.lower() or 'buynow' in auction_id.lower():
            return 'buy_it_now'
        
        # Default to auction if uncertain (conservative approach)
        logger.debug(f"Could not determine listing type for {auction_id}, defaulting to auction")
        return 'auction'
        
    except Exception as e:
        logger.warning(f"Error checking listing type for {auction_id}: {e}")
        return 'auction'  # Conservative default

def scrape_yahoo_grizzly_all(keyword, max_pages=3):
    """Scrape all listings and categorize them by checking ZenMarket - IMPROVED"""
    headers = {'User-Agent': random.choice(USER_AGENTS)}
    items = []
    
    logger.info(f"🔍 Scraping {max_pages} pages for: '{keyword}'")
    
    for page in range(1, max_pages + 1):
        try:
            encoded_kw = keyword.replace(' ', '+')
            b_param = ((page-1) * 50) + 1
            url = f'https://auctions.yahoo.co.jp/search/search?p={encoded_kw}&n=50&b={b_param}&s1=new&o1=d&minPrice=1&maxPrice={int(MAX_PRICE_USD * exchange_rate_cache["rate"])}'
            
            logger.info(f"   📄 Scraping page {page}: {url}")
            
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code != 200:
                logger.warning(f"❌ Page {page} returned status {response.status_code}")
                continue
            
            soup = BeautifulSoup(response.content, 'html.parser')
            listings = soup.select('li.Product')
            
            logger.info(f"   ✅ Page {page}: Found {len(listings)} raw listings")
            
            if len(listings) == 0:
                logger.warning(f"   ⚠️ Page {page} has no listings, stopping pagination")
                break
            
            page_processed = 0
            page_quality = 0
            
            for item in listings:
                try:
                    title_elem = item.select_one('h3.Product__title a') or item.select_one('a.Product__titleLink')
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    page_processed += 1
                    
                    # Check for banned keywords first (fast filter)
                    has_banned, banned_word = has_banned_keywords(title)
                    if has_banned:
                        logger.debug(f"   🚫 Banned keyword '{banned_word}': {title[:50]}")
                        continue
                    
                    link = title_elem.get('href')
                    if not link:
                        continue
                        
                    if not link.startswith("http"):
                        link = "https://auctions.yahoo.co.jp" + link
                    
                    auction_id = extract_auction_id_from_url(link)
                    if not auction_id:
                        continue
                    
                    price_elem = item.select_one('span.Product__priceValue') or item.select_one('.Product__price')
                    if not price_elem:
                        continue
                    
                    price_jpy = extract_price_from_text(price_elem.get_text())
                    if not price_jpy:
                        continue
                    
                    price_usd = convert_jpy_to_usd(price_jpy)
                    
                    # Quick price filter
                    if price_usd < MIN_PRICE_USD or price_usd > MAX_PRICE_USD:
                        continue
                    
                    image_elem = item.select_one('img')
                    image_url = None
                    if image_elem:
                        image_url = image_elem.get('src') or image_elem.get('data-src')
                        if image_url and not image_url.startswith('http'):
                            if image_url.startswith('//'):
                                image_url = 'https:' + image_url
                            else:
                                image_url = 'https://auctions.yahoo.co.jp' + image_url
                    
                    # Check for listing type (only for quality items)
                    listing_type = check_listing_type_enhanced(auction_id)
                    
                    items.append({
                        'auction_id': auction_id,
                        'title': title,
                        'price_jpy': price_jpy,
                        'price_usd': price_usd,
                        'image_url': image_url,
                        'keyword': keyword,
                        'listing_type': listing_type
                    })
                    
                    page_quality += 1
                    
                    # Add small delay after checking ZenMarket
                    time.sleep(0.3)
                    
                except Exception as e:
                    logger.error(f"   ❌ Error processing item: {e}")
                    continue
            
            logger.info(f"   📊 Page {page}: {page_processed} processed, {page_quality} quality items")
            
            # If very few items on this page, stop pagination
            if len(listings) < 20 and page > 1:
                logger.info(f"   🔚 Page {page} has few items ({len(listings)}), stopping pagination")
                break
            
            time.sleep(random.uniform(3, 5))
            
        except Exception as e:
            logger.error(f"❌ Error scraping page {page} for '{keyword}': {e}")
    
    logger.info(f"🏁 Completed scraping '{keyword}': {len(items)} total quality items found")
    return items

def extract_auction_id_from_url(url):
    if not url:
        return None
        
    patterns = [
        r'/auction/([a-zA-Z0-9_-]+)',
        r'auction_id=([a-zA-Z0-9_-]+)',
        r'/([a-zA-Z0-9_-]+)(?:\?|$)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            auction_id = match.group(1)
            # Clean up auction ID
            auction_id = auction_id.split('?')[0].split('#')[0]
            if len(auction_id) > 5:
                return auction_id
    
    # Fallback: get last part of URL
    try:
        auction_id = url.split('/')[-1].split('?')[0].split('#')[0]
        if len(auction_id) > 5 and auction_id.replace('_', '').replace('-', '').isalnum():
            return auction_id
    except:
        pass
    
    return None

def identify_grizzly_brand(title, brand_data):
    """Identify which brand this grizzly jacket belongs to"""
    title_lower = title.lower()
    
    for brand, data in brand_data.items():
        variants = data.get('variants', [brand])
        for variant in variants:
            if variant.lower() in title_lower:
                return brand
    
    return "Unknown"

def send_to_grizzly_discord_bot(listing_data):
    if not USE_DISCORD_BOT:
        logger.info("Discord bot integration disabled")
        return False
    
    try:
        # Use the standard listing endpoint that exists in your Discord bot
        webhook_url = f"{DISCORD_BOT_URL.rstrip('/')}/webhook/listing"
        
        # Add grizzly identifier to the data
        listing_data['is_grizzly'] = True
        listing_data['source'] = 'grizzly_jacket_sniper'
        
        # Test connection first
        health_url = f"{DISCORD_BOT_URL.rstrip('/')}/health"
        try:
            health_response = requests.get(health_url, timeout=2)
            if health_response.status_code != 200:
                logger.warning("Discord bot health check failed, bot may not be ready")
        except:
            logger.warning("Cannot reach Discord bot, it may not be running yet")
            return False
        
        logger.info(f"Sending grizzly jacket listing to Discord: {listing_data['title'][:50]}...")
        
        response = requests.post(
            webhook_url,
            json=listing_data,
            timeout=10
        )
        
        if response.status_code == 200:
            logger.info("✅ Successfully sent to Discord bot")
            return True
        else:
            logger.error(f"❌ Discord bot returned status {response.status_code}: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error sending to Discord bot: {e}")
        # Don't crash, just continue without Discord
        return False

def create_grizzly_listing_data(item, brand):
    return {
        'auction_id': item['auction_id'],
        'title': item['title'],
        'brand': brand,
        'price_jpy': item['price_jpy'],
        'price_usd': round(item['price_usd'], 2),
        'zenmarket_url': f"https://zenmarket.jp/en/auction.aspx?itemCode={item['auction_id']}",
        'yahoo_url': f"https://page.auctions.yahoo.co.jp/jp/auction/{item['auction_id']}",
        'image_url': item.get('image_url'),
        'seller_id': 'unknown',
        'auction_end_time': None,
        'keyword_used': item.get('keyword', ''),
        'deal_quality': calculate_grizzly_deal_quality(item['price_usd'], brand, item['title'], BRAND_DATA),
        'is_grizzly': True
    }

def run_grizzly_health_server():
    app = Flask(__name__)
    
    @app.route('/health')
    def health():
        return jsonify({
            "status": "healthy",
            "service": "grizzly_jacket_sniper",
            "timestamp": datetime.now().isoformat(),
            "discord_enabled": USE_DISCORD_BOT,
            "brands_tracked": len(BRAND_DATA),
            "items_seen": len(seen_ids)
        })
    
    @app.route('/stats')
    def stats():
        return jsonify({
            "brands_tracked": list(BRAND_DATA.keys()),
            "total_seen": len(seen_ids),
            "recent_errors": len(conversation_log.get_recent_hallucinations(24)),
            "max_price_usd": MAX_PRICE_USD,
            "min_price_usd": MIN_PRICE_USD
        })
    
    port = int(os.environ.get('PORT', 8004))
    app.run(host='0.0.0.0', port=port, debug=False)

def main_grizzly_loop():
    global seen_ids
    
    logger.info("🐻 Starting GRIZZLY JACKET Yahoo Sniper...")
    logger.info(f"Target brands: {', '.join(BRAND_DATA.keys())}")
    logger.info(f"Price range: ${MIN_PRICE_USD}-${MAX_PRICE_USD}")
    logger.info(f"Discord bot: {'Enabled' if USE_DISCORD_BOT else 'Disabled'}")
    
    seen_ids = load_seen_ids()
    keywords = generate_grizzly_keywords(BRAND_DATA)
    
    logger.info(f"Generated {len(keywords)} grizzly jacket keywords")
    
    cycle_num = 0
    total_found = 0
    total_sent = 0
    
    while True:
        cycle_num += 1
        cycle_start = time.time()
        
        logger.info(f"\n🔄 GRIZZLY CYCLE #{cycle_num} - {datetime.now().strftime('%H:%M:%S')}")
        
        cycle_found = 0
        cycle_sent = 0
        
        for i, keyword in enumerate(keywords):
            try:
                logger.info(f"\n[{i+1}/{len(keywords)}] 🔍 SEARCHING: '{keyword}'")
                
                items = scrape_yahoo_grizzly_all(keyword, max_pages=3)
                
                for item in items:
                    if item['auction_id'] in seen_ids:
                        continue
                    
                    # Check if item already exists in database
                    if check_if_grizzly_item_exists_in_db(item['auction_id']):
                        seen_ids.add(item['auction_id'])
                        continue
                    
                    seen_ids.add(item['auction_id'])
                    brand = identify_grizzly_brand(item['title'], BRAND_DATA)
                    
                    is_quality, reason = is_grizzly_quality_listing(
                        item['price_usd'], brand, item['title'], BRAND_DATA
                    )
                    
                    cycle_found += 1
                    total_found += 1
                    
                    if is_quality:
                        listing_data = create_grizzly_listing_data(item, brand)
                        
                        # Set the correct listing type based on ZenMarket check
                        listing_type = item['listing_type']
                        if listing_type in ['buy_it_now', 'both']:
                            listing_data['listing_type'] = 'buy_it_now'
                            logger.info(f"🛒 BIN GRIZZLY FIND: {brand} - {item['title'][:60]} - ${item['price_usd']:.2f}")
                        elif listing_type == 'auction':
                            listing_data['listing_type'] = 'auction'
                            logger.info(f"🔨 AUCTION GRIZZLY FIND: {brand} - {item['title'][:60]} - ${item['price_usd']:.2f}")
                        else:
                            # Unknown type, default to auction
                            listing_data['listing_type'] = 'auction'
                            logger.info(f"🐻 GRIZZLY FIND: {brand} - {item['title'][:60]} - ${item['price_usd']:.2f}")
                        
                        # Save to file regardless of Discord status
                        save_grizzly_find_to_file(listing_data)
                        
                        if send_to_grizzly_discord_bot(listing_data):
                            cycle_sent += 1
                            total_sent += 1
                        
                        conversation_log.add_entry("grizzly_listing", {
                            "brand": brand,
                            "title": item['title'],
                            "price_usd": item['price_usd'],
                            "quality": listing_data['deal_quality'],
                            "type": listing_data['listing_type']
                        })
                    else:
                        logger.debug(f"❌ Filtered: {reason}")
                
                time.sleep(random.uniform(5, 8))
                
            except Exception as e:
                logger.error(f"Error processing keyword '{keyword}': {e}")
                conversation_log.add_entry("keyword_error", {"keyword": keyword, "error": str(e)})
        
        cycle_time = time.time() - cycle_start
        
        logger.info(f"🏁 Cycle #{cycle_num} complete:")
        logger.info(f"   Found: {cycle_found} | Sent: {cycle_sent} | Time: {cycle_time:.1f}s")
        logger.info(f"📊 Total: {total_found} found, {total_sent} sent to Discord")
        
        save_seen_ids(seen_ids)
        conversation_log.save_log()
        
        sleep_time = max(300, 600 - cycle_time)
        logger.info(f"😴 Sleeping {sleep_time:.0f}s until next cycle...")
        time.sleep(sleep_time)

if __name__ == "__main__":
    BRAND_DATA = load_brand_data()
    
    if not BRAND_DATA:
        logger.error("❌ No brand data loaded. Exiting.")
        exit(1)
    
    seen_ids = set()
    
    logger.info("🐻 Running grizzly jacket scraper in standalone mode")
    logger.info("💾 Finds will be saved to grizzly_finds.json")
    
    try:
        main_grizzly_loop()
    except KeyboardInterrupt:
        logger.info("👋 Grizzly jacket sniper stopped by user")
        save_seen_ids(seen_ids)
        conversation_log.save_log()
    except Exception as e:
        logger.error(f"💥 Critical error: {e}")
        conversation_log.add_entry("critical_error", {"error": str(e)})
        conversation_log.save_log()

