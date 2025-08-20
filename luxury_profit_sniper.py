#!/usr/bin/env python3

import requests
import time
import json
import os
import threading
import re
import random
import asyncio
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from flask import Flask, jsonify
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BRANDS_FILE = "brands_luxury.json"
SEEN_FILE = "seen_luxury_items.json"
EXCHANGE_RATE_FILE = "exchange_rate.json"
LUXURY_FINDS_FILE = "luxury_finds.json"
PRICING_TIERS_FILE = "pricing_tiers.json"

# PROFIT-FOCUSED CONFIGURATION
MAX_PURCHASE_PRICE_USD = 60  # Maximum we'll spend
MIN_PURCHASE_PRICE_USD = 0   # Minimum price (catch everything)
TARGET_ROI_PERCENT = 200     # Minimum 200% ROI (3x return)

# Advanced scraping configuration
MAX_PAGES_PER_KEYWORD = 20   # Scrape deep for opportunities
KEYWORDS_PER_CYCLE = 50      # More keywords per cycle
REQUESTS_PER_MINUTE = 30     # Faster scraping

USE_DISCORD_BOT = os.environ.get('USE_DISCORD_BOT', 'false').lower() == 'true'
DISCORD_BOT_URL = os.environ.get('DISCORD_BOT_URL', 'http://localhost:8002')

# Profit-based pricing tiers (based on your chart)
PROFIT_TIERS = {
    999: 400,   # Items selling for $999+ → buy up to $400
    899: 350,   # Items selling for $899+ → buy up to $350  
    799: 310,   # Items selling for $799+ → buy up to $310
    699: 270,   # Items selling for $699+ → buy up to $270
    599: 230,   # Items selling for $599+ → buy up to $230
    499: 190,   # Items selling for $499+ → buy up to $190
    399: 140,   # Items selling for $399+ → buy up to $140
    349: 120,   # Items selling for $349+ → buy up to $120
    299: 110,   # Items selling for $299+ → buy up to $110
    249: 90,    # Items selling for $249+ → buy up to $90
    199: 70,    # Items selling for $199+ → buy up to $70
    149: 50,    # Items selling for $149+ → buy up to $50
    99: 30,     # Items selling for $99+ → buy up to $30
    79: 25,     # Items selling for $79+ → buy up to $25
    59: 20,     # Items selling for $59+ → buy up to $20
    39: 10,     # Items selling for $39+ → buy up to $10
    29: 8,      # Items selling for $29+ → buy up to $8
    23: 5,      # Items selling for $23+ → buy up to $5
    19: 4,      # Items selling for $19+ → buy up to $4
}

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15'
]

# Enhanced banned keywords (case insensitive)
BANNED_KEYWORDS = {
    'julius', 'kmrii', 'ifsixwasnine', 'groundy', 'ground y', 'fred perry', 
    'play', 'tornado', 'midas', 'civarize', 'l.g.b.', 'yeezy', 'yzy', 
    'gap', 'zara', 'uniqlo', 'ユニクロ', 'ザラ', 'ギャップ', 'フレッドペリー',
    'シュプリーム', 'supreme', 'off white', 'off-white', 'オフホワイト',
    'stone island', 'ストーンアイランド', 'cp company', 'c.p. company'
}

def load_exchange_rate():
    global exchange_rate_cache
    try:
        if os.path.exists(EXCHANGE_RATE_FILE):
            with open(EXCHANGE_RATE_FILE, 'r') as f:
                exchange_rate_cache = json.load(f)
        else:
            exchange_rate_cache = {"rate": 150.0, "last_updated": "2024-01-01"}
    except Exception as e:
        logger.error(f"Error loading exchange rate: {e}")
        exchange_rate_cache = {"rate": 150.0, "last_updated": "2024-01-01"}

def save_exchange_rate():
    try:
        with open(EXCHANGE_RATE_FILE, 'w') as f:
            json.dump(exchange_rate_cache, f)
    except Exception as e:
        logger.error(f"Error saving exchange rate: {e}")

def update_exchange_rate():
    """Fetch current USD/JPY rate"""
    try:
        response = requests.get('https://api.exchangerate-api.com/v4/latest/USD', timeout=10)
        if response.status_code == 200:
            data = response.json()
            new_rate = data['rates']['JPY']
            exchange_rate_cache["rate"] = new_rate
            exchange_rate_cache["last_updated"] = datetime.now().isoformat()
            save_exchange_rate()
            logger.info(f"💱 Updated exchange rate: $1 = ¥{new_rate:.2f}")
            return new_rate
    except Exception as e:
        logger.warning(f"Failed to update exchange rate: {e}")
    return exchange_rate_cache["rate"]

load_exchange_rate()

def load_brand_data():
    try:
        with open(BRANDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"❌ {BRANDS_FILE} not found!")
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
        # Keep only last 10000 IDs to prevent memory issues
        ids_to_save = list(seen_ids)[-10000:]
        with open(SEEN_FILE, 'w') as f:
            json.dump(ids_to_save, f)
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

def has_banned_keywords(title):
    """Check if title contains any banned keywords"""
    title_lower = title.lower()
    for banned in BANNED_KEYWORDS:
        if banned in title_lower:
            return True, banned
    return False, None

def estimate_market_value(title, brand, brand_data):
    """Estimate market value based on item type and brand"""
    title_lower = title.lower()
    
    # Base values by brand (conservative estimates)
    brand_base_values = {
        "Balenciaga": {"tee": 120, "hoodie": 280, "jacket": 450, "pants": 200},
        "Vetements": {"tee": 150, "hoodie": 350, "jacket": 500, "pants": 250},
        "Rick Owens": {"tee": 200, "hoodie": 400, "jacket": 800, "pants": 350},
        "Comme Des Garcons": {"tee": 100, "hoodie": 250, "jacket": 350, "pants": 180},
        "Junya Watanabe": {"tee": 120, "hoodie": 300, "jacket": 400, "pants": 220},
        "Issey Miyake": {"tee": 90, "hoodie": 220, "jacket": 300, "pants": 160}
    }
    
    if brand not in brand_base_values:
        return 99  # Default conservative estimate
    
    # Determine item type
    item_type = "tee"  # default
    if any(word in title_lower for word in ["hoodie", "sweatshirt", "パーカー"]):
        item_type = "hoodie"
    elif any(word in title_lower for word in ["jacket", "blazer", "coat", "ジャケット", "コート"]):
        item_type = "jacket"
    elif any(word in title_lower for word in ["pants", "jeans", "trousers", "パンツ", "ジーンズ"]):
        item_type = "pants"
    
    base_value = brand_base_values[brand].get(item_type, 99)
    
    # Archive/rare multiplier
    if any(term in title_lower for term in ["archive", "rare", "vintage", "fw", "ss", "runway"]):
        base_value *= 1.5
    
    return int(base_value)

def calculate_profit_potential(purchase_price_usd, estimated_market_value):
    """Calculate profit potential based on pricing tiers"""
    
    # Find the appropriate selling tier
    for sell_price in sorted(PROFIT_TIERS.keys(), reverse=True):
        max_buy_price = PROFIT_TIERS[sell_price]
        
        if estimated_market_value >= sell_price and purchase_price_usd <= max_buy_price:
            profit = sell_price - purchase_price_usd
            roi = (profit / purchase_price_usd) * 100
            return {
                "estimated_sell_price": sell_price,
                "purchase_price": purchase_price_usd,
                "estimated_profit": profit,
                "roi_percent": roi,
                "is_profitable": roi >= TARGET_ROI_PERCENT
            }
    
    # Fallback calculation
    estimated_profit = max(0, estimated_market_value - purchase_price_usd)
    roi = (estimated_profit / purchase_price_usd) * 100 if purchase_price_usd > 0 else 0
    
    return {
        "estimated_sell_price": estimated_market_value,
        "purchase_price": purchase_price_usd,
        "estimated_profit": estimated_profit,
        "roi_percent": roi,
        "is_profitable": roi >= TARGET_ROI_PERCENT
    }

def is_clothing_item(title, brand_data):
    """Check if item is clothing (not accessories)"""
    title_lower = title.lower()
    
    # Exclude accessories
    excluded_global = {
        'bag', 'purse', 'wallet', 'handbag', 'clutch', 'tote', 'backpack',
        'shoes', 'sneakers', 'boots', 'heels', 'sandals', 'loafers', 'slippers',
        'watch', 'jewelry', 'necklace', 'ring', 'bracelet', 'earrings',
        'perfume', 'fragrance', 'cologne', 'spray',
        'phone', 'case', 'cover', 'tech', 'electronic', 'charger',
        'poster', 'magazine', 'book', 'dvd', 'cd', 'vinyl',
        'keychain', 'pin', 'badge', 'sticker',
        'バッグ', '財布', '靴', 'スニーカー', 'ブーツ', '時計', '香水',
        'アクセサリー', 'ネックレス', '指輪', 'ブレスレット', 'キーホルダー'
    }
    
    if any(excluded in title_lower for excluded in excluded_global):
        return False
    
    # Must contain clothing indicators
    clothing_indicators = {
        'shirt', 'tee', 't-shirt', 'polo', 'blouse', 'top',
        'jacket', 'blazer', 'coat', 'hoodie', 'sweatshirt', 'sweater',
        'pants', 'jeans', 'trousers', 'shorts', 'denim',
        'cardigan', 'pullover', 'knit', 'knitwear',
        'dress', 'skirt', 'tank', 'vest', 'waistcoat',
        'cap', 'hat', 'beanie', 'scarf', 'gloves', 'socks',
        'underwear', 'tights', 'leggings',
        'シャツ', 'Tシャツ', 'ポロ', 'トップス', 'ブラウス',
        'ジャケット', 'ブレザー', 'コート', 'パーカー',
        'パンツ', 'ジーンズ', 'ショーツ', 'デニム',
        'ニット', 'セーター', 'カーディガン',
        'ワンピース', 'スカート', 'タンク', 'ベスト',
        'キャップ', '帽子', 'マフラー', '手袋', '靴下'
    }
    
    return any(indicator in title_lower for indicator in clothing_indicators)

def identify_brand(title, brand_data):
    """Identify brand from title"""
    title_lower = title.lower()
    
    for brand, data in brand_data.items():
        variants = data.get('variants', [brand])
        for variant in variants:
            if variant.lower() in title_lower:
                return brand
    
    return "Unknown"

def check_listing_type_advanced(auction_id):
    """Advanced listing type detection using multiple methods"""
    try:
        # Method 1: Check ZenMarket page
        zenmarket_url = f"https://zenmarket.jp/en/auction.aspx?itemCode={auction_id}"
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        
        response = requests.get(zenmarket_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            content = response.text.lower()
            
            # Enhanced BIN detection
            bin_indicators = [
                'buyout price', 'buy now price', 'fixed price', 'immediate purchase',
                'instant buy', 'buy it now', 'direct purchase'
            ]
            
            auction_indicators = [
                'current bid', 'highest bid', 'bidding', 'auction ends',
                'time left', 'bid now', 'place bid'
            ]
            
            bin_score = sum(1 for indicator in bin_indicators if indicator in content)
            auction_score = sum(1 for indicator in auction_indicators if indicator in content)
            
            if bin_score > auction_score:
                return 'buy_it_now'
            elif auction_score > bin_score:
                return 'auction'
            else:
                # Method 2: Check Yahoo page directly
                yahoo_url = f"https://page.auctions.yahoo.co.jp/jp/auction/{auction_id}"
                yahoo_response = requests.get(yahoo_url, headers=headers, timeout=10)
                
                if yahoo_response.status_code == 200:
                    yahoo_content = yahoo_response.text
                    
                    # Look for specific Yahoo indicators
                    if 'フリマ' in yahoo_content or 'fixed' in yahoo_content.lower():
                        return 'buy_it_now'
                    elif '入札' in yahoo_content or 'bid' in yahoo_content.lower():
                        return 'auction'
        
        return 'unknown'
        
    except Exception as e:
        logger.warning(f"Error checking listing type for {auction_id}: {e}")
        return 'unknown'

def scrape_yahoo_comprehensive(keyword, max_pages=20, listing_type_filter=None):
    """Comprehensive Yahoo Auctions scraping with profit focus"""
    headers = {'User-Agent': random.choice(USER_AGENTS)}
    items = []
    
    logger.info(f"🔍 PROFIT SCRAPING: '{keyword}' ({max_pages} pages)")
    
    for page in range(1, max_pages + 1):
        try:
            encoded_kw = keyword.replace(' ', '+')
            b_param = ((page-1) * 50) + 1
            
            # Build URL with profit-focused parameters
            max_price_jpy = int(MAX_PURCHASE_PRICE_USD * exchange_rate_cache["rate"])
            
            base_url = f'https://auctions.yahoo.co.jp/search/search?p={encoded_kw}&n=50&b={b_param}&s1=new&o1=d&minPrice=1&maxPrice={max_price_jpy}'
            
            # Add listing type filter if specified
            if listing_type_filter == 'bin':
                base_url += '&auccat=0'  # Buy It Now only
            elif listing_type_filter == 'auction':
                base_url += '&auccat=auction'  # Auctions only
            
            response = requests.get(base_url, headers=headers, timeout=15)
            
            if response.status_code != 200:
                logger.warning(f"❌ Page {page} returned status {response.status_code}")
                time.sleep(5)
                continue
            
            soup = BeautifulSoup(response.content, 'html.parser')
            listings = soup.select('li.Product')
            
            if len(listings) == 0:
                logger.info(f"   📭 Page {page}: No listings found, stopping")
                break
            
            page_processed = 0
            page_profitable = 0
            
            for item in listings:
                try:
                    title_elem = item.select_one('h3.Product__title a') or item.select_one('a.Product__titleLink')
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    page_processed += 1
                    
                    # Fast filters first
                    has_banned, banned_word = has_banned_keywords(title)
                    if has_banned:
                        continue
                    
                    if not is_clothing_item(title, BRAND_DATA):
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
                    
                    # Price filter
                    if price_usd < MIN_PURCHASE_PRICE_USD or price_usd > MAX_PURCHASE_PRICE_USD:
                        continue
                    
                    # Profit analysis
                    brand = identify_brand(title, BRAND_DATA)
                    estimated_value = estimate_market_value(title, brand, BRAND_DATA)
                    profit_analysis = calculate_profit_potential(price_usd, estimated_value)
                    
                    # Only process profitable items
                    if not profit_analysis['is_profitable']:
                        continue
                    
                    # Get listing type
                    listing_type = check_listing_type_advanced(auction_id)
                    
                    image_elem = item.select_one('img')
                    image_url = None
                    if image_elem:
                        image_url = image_elem.get('src') or image_elem.get('data-src')
                        if image_url and not image_url.startswith('http'):
                            if image_url.startswith('//'):
                                image_url = 'https:' + image_url
                            else:
                                image_url = 'https://auctions.yahoo.co.jp' + image_url
                    
                    items.append({
                        'auction_id': auction_id,
                        'title': title,
                        'brand': brand,
                        'price_jpy': price_jpy,
                        'price_usd': price_usd,
                        'image_url': image_url,
                        'keyword': keyword,
                        'listing_type': listing_type,
                        'profit_analysis': profit_analysis,
                        'estimated_market_value': estimated_value
                    })
                    
                    page_profitable += 1
                    
                    logger.info(f"💰 PROFIT FIND: {brand} ${price_usd:.2f} → Est. ${estimated_value} (ROI: {profit_analysis['roi_percent']:.0f}%)")
                    
                    time.sleep(0.5)  # Rate limiting
                    
                except Exception as e:
                    logger.error(f"   ❌ Error processing item: {e}")
                    continue
            
            logger.info(f"   📊 Page {page}: {page_processed} processed, {page_profitable} profitable")
            
            if len(listings) < 20 and page > 5:
                logger.info(f"   🔚 Page {page} has few items, stopping")
                break
            
            time.sleep(random.uniform(3, 6))
            
        except Exception as e:
            logger.error(f"❌ Error scraping page {page} for '{keyword}': {e}")
            time.sleep(10)
    
    logger.info(f"🏁 '{keyword}' complete: {len(items)} profitable items found")
    return items

def extract_auction_id_from_url(url):
    """Extract auction ID from Yahoo URL"""
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
            auction_id = auction_id.split('?')[0].split('#')[0]
            if len(auction_id) > 5:
                return auction_id
    
    try:
        auction_id = url.split('/')[-1].split('?')[0].split('#')[0]
        if len(auction_id) > 5 and auction_id.replace('_', '').replace('-', '').isalnum():
            return auction_id
    except:
        pass
    
    return None

def generate_comprehensive_keywords(brand_data):
    """Generate comprehensive keywords for maximum coverage"""
    keywords = []
    
    for brand, data in brand_data.items():
        variants = data.get('variants', [brand])
        subcategories = data.get('subcategories', [])
        
        # Main brand variants
        for variant in variants:
            keywords.append(variant)
        
        # Brand + clothing type combinations
        clothing_types = ["tee", "shirt", "jacket", "hoodie", "pants", "jeans", "sweater"]
        japanese_types = ["Tシャツ", "シャツ", "ジャケット", "パーカー", "パンツ", "ニット"]
        
        for variant in variants[:2]:  # Top 2 variants
            for clothing_type in clothing_types:
                keywords.append(f"{variant} {clothing_type}")
            
            for jp_type in japanese_types:
                keywords.append(f"{variant} {jp_type}")
        
        # Archive and seasonal terms
        archive_terms = ["archive", "vintage", "rare", "fw", "ss"]
        for variant in variants[:1]:  # Main variant only
            for term in archive_terms:
                keywords.append(f"{variant} {term}")
        
        # Size-specific searches (higher value items)
        sizes = ["S", "M", "L", "XL", "48", "50", "52"]
        for variant in variants[:1]:
            for size in sizes[:3]:  # Top sizes
                keywords.append(f"{variant} size {size}")
    
    # Remove duplicates and return
    return list(set(keywords))

def send_to_discord_bot(listing_data):
    """Send profitable finds to Discord bot"""
    if not USE_DISCORD_BOT:
        logger.info("Discord bot integration disabled")
        return False
    
    try:
        webhook_url = f"{DISCORD_BOT_URL.rstrip('/')}/webhook/listing"
        
        # Enhance listing data with profit information
        listing_data['is_luxury'] = True
        listing_data['source'] = 'luxury_profit_sniper'
        listing_data['deal_quality'] = min(1.0, listing_data['profit_analysis']['roi_percent'] / 400)
        
        # Add profit details to the data
        profit = listing_data['profit_analysis']
        listing_data['profit_summary'] = f"Buy ${profit['purchase_price']:.2f} → Sell ${profit['estimated_sell_price']} → Profit ${profit['estimated_profit']:.2f} ({profit['roi_percent']:.0f}% ROI)"
        
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
        return False

def save_profitable_find(listing_data):
    """Save profitable finds to file"""
    try:
        finds = []
        if os.path.exists(LUXURY_FINDS_FILE):
            with open(LUXURY_FINDS_FILE, 'r', encoding='utf-8') as f:
                finds = json.load(f)
        
        listing_data['found_at'] = datetime.now().isoformat()
        finds.append(listing_data)
        
        # Keep only last 500 finds
        finds = finds[-500:]
        
        with open(LUXURY_FINDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(finds, f, ensure_ascii=False, indent=2)
        
        logger.info(f"💾 Saved profitable find: ROI {listing_data['profit_analysis']['roi_percent']:.0f}%")
        return True
        
    except Exception as e:
        logger.error(f"Error saving find: {e}")
        return False

def run_health_server():
    """Run health check server"""
    app = Flask(__name__)
    
    @app.route('/health')
    def health():
        return jsonify({
            "status": "healthy",
            "service": "luxury_profit_sniper",
            "timestamp": datetime.now().isoformat(),
            "discord_enabled": USE_DISCORD_BOT,
            "brands_tracked": len(BRAND_DATA),
            "items_seen": len(seen_ids),
            "max_purchase_usd": MAX_PURCHASE_PRICE_USD,
            "target_roi_percent": TARGET_ROI_PERCENT
        })
    
    @app.route('/stats')
    def stats():
        profit_summary = {
            "total_finds": len(seen_ids),
            "target_roi": f"{TARGET_ROI_PERCENT}%",
            "price_range": f"${MIN_PURCHASE_PRICE_USD}-${MAX_PURCHASE_PRICE_USD}",
            "brands": list(BRAND_DATA.keys()),
            "exchange_rate": exchange_rate_cache["rate"]
        }
        return jsonify(profit_summary)
    
    port = int(os.environ.get('PORT', 8003))
    app.run(host='0.0.0.0', port=port, debug=False)

def main_profit_loop():
    """Main scraping loop focused on profit"""
    global seen_ids
    
    logger.info("💰 Starting LUXURY PROFIT SNIPER...")
    logger.info(f"Target brands: {', '.join(BRAND_DATA.keys())}")
    logger.info(f"Purchase range: ${MIN_PURCHASE_PRICE_USD}-${MAX_PURCHASE_PRICE_USD}")
    logger.info(f"Target ROI: {TARGET_ROI_PERCENT}%+")
    logger.info(f"Discord bot: {'Enabled' if USE_DISCORD_BOT else 'Disabled'}")
    
    # Update exchange rate on startup
    update_exchange_rate()
    
    seen_ids = load_seen_ids()
    keywords = generate_comprehensive_keywords(BRAND_DATA)
    
    logger.info(f"Generated {len(keywords)} profit-focused keywords")
    
    cycle_num = 0
    total_found = 0
    total_profitable = 0
    total_sent = 0
    
    while True:
        cycle_num += 1
        cycle_start = time.time()
        
        logger.info(f"\n💰 PROFIT CYCLE #{cycle_num} - {datetime.now().strftime('%H:%M:%S')}")
        
        cycle_found = 0
        cycle_profitable = 0
        cycle_sent = 0
        
        # Update exchange rate every 10 cycles
        if cycle_num % 10 == 0:
            update_exchange_rate()
        
        # Randomize keyword order for better coverage
        random.shuffle(keywords)
        
        for i, keyword in enumerate(keywords[:KEYWORDS_PER_CYCLE]):
            try:
                logger.info(f"\n[{i+1}/{min(len(keywords), KEYWORDS_PER_CYCLE)}] 💎 PROFIT SEARCH: '{keyword}'")
                
                # Scrape both BIN and auctions for maximum coverage
                bin_items = scrape_yahoo_comprehensive(keyword, max_pages=MAX_PAGES_PER_KEYWORD//2, listing_type_filter='bin')
                auction_items = scrape_yahoo_comprehensive(keyword, max_pages=MAX_PAGES_PER_KEYWORD//2, listing_type_filter='auction')
                
                all_items = bin_items + auction_items
                
                for item in all_items:
                    if item['auction_id'] in seen_ids:
                        continue
                    
                    seen_ids.add(item['auction_id'])
                    cycle_found += 1
                    total_found += 1
                    
                    # All items from scraper are already profitable
                    cycle_profitable += 1
                    total_profitable += 1
                    
                    profit = item['profit_analysis']
                    logger.info(f"🚀 PROFIT OPPORTUNITY: {item['brand']} - {item['title'][:60]}")
                    logger.info(f"   💰 Buy: ${profit['purchase_price']:.2f} → Sell: ${profit['estimated_sell_price']} → ROI: {profit['roi_percent']:.0f}%")
                    
                    # Save find
                    save_profitable_find(item)
                    
                    # Send to Discord
                    if send_to_discord_bot(item):
                        cycle_sent += 1
                        total_sent += 1
                
                # Rate limiting between keywords
                time.sleep(random.uniform(8, 12))
                
            except Exception as e:
                logger.error(f"Error processing keyword '{keyword}': {e}")
                time.sleep(5)
        
        cycle_time = time.time() - cycle_start
        
        logger.info(f"🏁 PROFIT CYCLE #{cycle_num} COMPLETE:")
        logger.info(f"   Found: {cycle_found} | Profitable: {cycle_profitable} | Sent: {cycle_sent}")
        logger.info(f"   Time: {cycle_time:.1f}s | Keywords: {min(len(keywords), KEYWORDS_PER_CYCLE)}")
        logger.info(f"📊 TOTAL STATS: {total_found} found, {total_profitable} profitable, {total_sent} sent")
        
        # Save progress
        save_seen_ids(seen_ids)
        
        # Calculate sleep time to maintain request rate
        sleep_time = max(180, 600 - cycle_time)  # Minimum 3 minutes between cycles
        logger.info(f"😴 Sleeping {sleep_time:.0f}s until next profit cycle...")
        time.sleep(sleep_time)

if __name__ == "__main__":
    try:
        BRAND_DATA = load_brand_data()
        
        if not BRAND_DATA:
            logger.error("❌ No brand data loaded. Exiting.")
            exit(1)
        
        seen_ids = set()
        
        # Start health server in background
        health_thread = threading.Thread(target=run_health_server, daemon=True)
        health_thread.start()
        
        logger.info("🌐 Health server started")
        
        # Run main profit loop
        main_profit_loop()
        
    except KeyboardInterrupt:
        logger.info("👋 Luxury profit sniper stopped by user")
        save_seen_ids(seen_ids)
    except Exception as e:
        logger.error(f"💥 Critical error: {e}")
        raise