import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
import json
from datetime import datetime

class ProfitDatabaseManager:
    def __init__(self):
        self.database_url = os.environ.get('DATABASE_URL')
        self.use_postgres = bool(self.database_url)
        
        if not self.use_postgres:
            self.db_path = 'luxury_profit_tracking.db'
            print("🗄️ Using SQLite database: luxury_profit_tracking.db")
        else:
            print("🐘 Using PostgreSQL database")
        
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """Get database connection (PostgreSQL or SQLite)"""
        if self.use_postgres:
            conn = psycopg2.connect(
                self.database_url,
                cursor_factory=RealDictCursor
            )
            try:
                yield conn
            finally:
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            try:
                yield conn
            finally:
                conn.close()
    
    def init_database(self):
        """Initialize database tables for profit tracking"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if self.use_postgres:
                self._create_postgres_profit_tables(cursor)
            else:
                self._create_sqlite_profit_tables(cursor)
            
            conn.commit()
            print("✅ Profit database tables initialized")
    
    def _create_postgres_profit_tables(self, cursor):
        """Create PostgreSQL tables with profit-focused fields"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profit_listings (
                id SERIAL PRIMARY KEY,
                auction_id VARCHAR(100) UNIQUE,
                title TEXT,
                brand VARCHAR(100),
                price_jpy INTEGER,
                price_usd REAL,
                seller_id VARCHAR(100),
                zenmarket_url TEXT,
                yahoo_url TEXT,
                image_url TEXT,
                listing_type VARCHAR(20) DEFAULT 'unknown',
                estimated_market_value REAL DEFAULT 0,
                purchase_price REAL DEFAULT 0,
                estimated_sell_price REAL DEFAULT 0,
                estimated_profit REAL DEFAULT 0,
                roi_percent REAL DEFAULT 0,
                is_profitable BOOLEAN DEFAULT FALSE,
                profit_tier VARCHAR(20) DEFAULT 'fair',
                deal_quality REAL DEFAULT 0.5,
                priority_score REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_id BIGINT,
                channel_id BIGINT,
                auction_end_time TIMESTAMP,
                keyword_used VARCHAR(100),
                source VARCHAR(50) DEFAULT 'luxury_profit_sniper'
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profit_reactions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                auction_id VARCHAR(100),
                reaction_type VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profit_user_preferences (
                user_id BIGINT PRIMARY KEY,
                proxy_service VARCHAR(50) DEFAULT 'zenmarket',
                setup_complete BOOLEAN DEFAULT FALSE,
                notifications_enabled BOOLEAN DEFAULT TRUE,
                min_roi_threshold REAL DEFAULT 200.0,
                max_price_alert REAL DEFAULT 60.0,
                bookmark_method VARCHAR(20) DEFAULT 'private_channel',
                auto_bookmark_high_roi BOOLEAN DEFAULT TRUE,
                preferred_brands TEXT,
                roi_alerts_enabled BOOLEAN DEFAULT TRUE,
                ultra_profit_alerts BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profit_user_bookmarks (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                auction_id VARCHAR(100),
                bookmark_message_id BIGINT,
                bookmark_channel_id BIGINT,
                auction_end_time TIMESTAMP,
                estimated_profit REAL DEFAULT 0,
                roi_percent REAL DEFAULT 0,
                bookmark_reason VARCHAR(50) DEFAULT 'manual',
                reminder_sent_1h BOOLEAN DEFAULT FALSE,
                reminder_sent_5m BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, auction_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profit_scraper_stats (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_found INTEGER DEFAULT 0,
                profitable_found INTEGER DEFAULT 0,
                ultra_profit_found INTEGER DEFAULT 0,
                sent_to_discord INTEGER DEFAULT 0,
                errors_count INTEGER DEFAULT 0,
                keywords_searched INTEGER DEFAULT 0,
                avg_roi_percent REAL DEFAULT 0,
                cycle_time_seconds INTEGER DEFAULT 0
            )
        ''')
        
        # Create indexes for profit optimization
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_profit_listings_brand ON profit_listings(brand)",
            "CREATE INDEX IF NOT EXISTS idx_profit_listings_roi ON profit_listings(roi_percent)",
            "CREATE INDEX IF NOT EXISTS idx_profit_listings_profit_tier ON profit_listings(profit_tier)",
            "CREATE INDEX IF NOT EXISTS idx_profit_listings_created_at ON profit_listings(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_profit_listings_is_profitable ON profit_listings(is_profitable)",
            "CREATE INDEX IF NOT EXISTS idx_profit_reactions_user_id ON profit_reactions(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_profit_reactions_auction_id ON profit_reactions(auction_id)",
            "CREATE INDEX IF NOT EXISTS idx_profit_user_bookmarks_user_id ON profit_user_bookmarks(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_profit_user_bookmarks_roi ON profit_user_bookmarks(roi_percent)",
        ]
        
        for index_sql in indexes:
            try:
                cursor.execute(index_sql)
            except Exception as e:
                if "already exists" not in str(e):
                    print(f"Index warning: {e}")
    
    def _create_sqlite_profit_tables(self, cursor):
        """Create SQLite tables with profit-focused fields"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profit_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                auction_id TEXT UNIQUE,
                title TEXT,
                brand TEXT,
                price_jpy INTEGER,
                price_usd REAL,
                seller_id TEXT,
                zenmarket_url TEXT,
                yahoo_url TEXT,
                image_url TEXT,
                listing_type TEXT DEFAULT 'unknown',
                estimated_market_value REAL DEFAULT 0,
                purchase_price REAL DEFAULT 0,
                estimated_sell_price REAL DEFAULT 0,
                estimated_profit REAL DEFAULT 0,
                roi_percent REAL DEFAULT 0,
                is_profitable BOOLEAN DEFAULT FALSE,
                profit_tier TEXT DEFAULT 'fair',
                deal_quality REAL DEFAULT 0.5,
                priority_score REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_id INTEGER,
                channel_id INTEGER,
                auction_end_time TIMESTAMP,
                keyword_used TEXT,
                source TEXT DEFAULT 'luxury_profit_sniper'
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profit_reactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                auction_id TEXT,
                reaction_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profit_user_preferences (
                user_id INTEGER PRIMARY KEY,
                proxy_service TEXT DEFAULT 'zenmarket',
                setup_complete BOOLEAN DEFAULT FALSE,
                notifications_enabled BOOLEAN DEFAULT TRUE,
                min_roi_threshold REAL DEFAULT 200.0,
                max_price_alert REAL DEFAULT 60.0,
                bookmark_method TEXT DEFAULT 'private_channel',
                auto_bookmark_high_roi BOOLEAN DEFAULT TRUE,
                preferred_brands TEXT,
                roi_alerts_enabled BOOLEAN DEFAULT TRUE,
                ultra_profit_alerts BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profit_user_bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                auction_id TEXT,
                bookmark_message_id INTEGER,
                bookmark_channel_id INTEGER,
                auction_end_time TIMESTAMP,
                estimated_profit REAL DEFAULT 0,
                roi_percent REAL DEFAULT 0,
                bookmark_reason TEXT DEFAULT 'manual',
                reminder_sent_1h BOOLEAN DEFAULT FALSE,
                reminder_sent_5m BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, auction_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profit_scraper_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_found INTEGER DEFAULT 0,
                profitable_found INTEGER DEFAULT 0,
                ultra_profit_found INTEGER DEFAULT 0,
                sent_to_discord INTEGER DEFAULT 0,
                errors_count INTEGER DEFAULT 0,
                keywords_searched INTEGER DEFAULT 0,
                avg_roi_percent REAL DEFAULT 0,
                cycle_time_seconds INTEGER DEFAULT 0
            )
        ''')
    
    def execute_query(self, query, params=None, fetch_one=False, fetch_all=False):
        """Execute a database query with proper error handling"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                if fetch_one:
                    result = cursor.fetchone()
                    return dict(result) if result and self.use_postgres else result
                elif fetch_all:
                    results = cursor.fetchall()
                    return [dict(row) for row in results] if results and self.use_postgres else results
                else:
                    conn.commit()
                    return True
                    
        except Exception as e:
            print(f"❌ Database execute_query error: {e}")
            if params:
                print(f"❌ Query: {query}")
                print(f"❌ Params: {params}")
            raise e

# Initialize the profit database manager
db_manager = ProfitDatabaseManager()

def add_profit_listing(listing_data, message_id):
    """Add profit listing to database with comprehensive profit tracking"""
    try:
        profit_analysis = listing_data.get('profit_analysis', {})
        
        # Determine profit tier
        roi_percent = profit_analysis.get('roi_percent', 0)
        if roi_percent >= 400:
            profit_tier = 'ultra'
        elif roi_percent >= 300:
            profit_tier = 'high'
        elif roi_percent >= 200:
            profit_tier = 'good'
        else:
            profit_tier = 'fair'
        
        if db_manager.use_postgres:
            result = db_manager.execute_query('''
                INSERT INTO profit_listings 
                (auction_id, title, brand, price_jpy, price_usd, seller_id, 
                 zenmarket_url, yahoo_url, image_url, listing_type,
                 estimated_market_value, purchase_price, estimated_sell_price,
                 estimated_profit, roi_percent, is_profitable, profit_tier,
                 deal_quality, priority_score, message_id, channel_id,
                 keyword_used, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (auction_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    message_id = EXCLUDED.message_id,
                    roi_percent = EXCLUDED.roi_percent,
                    profit_tier = EXCLUDED.profit_tier
            ''', (
                listing_data['auction_id'],
                listing_data['title'],
                listing_data['brand'],
                listing_data['price_jpy'],
                listing_data['price_usd'],
                listing_data.get('seller_id', 'unknown'),
                listing_data['zenmarket_url'],
                listing_data.get('yahoo_url', ''),
                listing_data.get('image_url', ''),
                listing_data.get('listing_type', 'unknown'),
                listing_data.get('estimated_market_value', 0),
                profit_analysis.get('purchase_price', listing_data['price_usd']),
                profit_analysis.get('estimated_sell_price', 0),
                profit_analysis.get('estimated_profit', 0),
                profit_analysis.get('roi_percent', 0),
                profit_analysis.get('is_profitable', False),
                profit_tier,
                listing_data.get('deal_quality', 0.5),
                listing_data.get('priority_score', roi_percent / 100),
                message_id,
                listing_data.get('channel_id'),
                listing_data.get('keyword_used', ''),
                listing_data.get('source', 'luxury_profit_sniper')
            ))
        else:
            result = db_manager.execute_query('''
                INSERT OR REPLACE INTO profit_listings 
                (auction_id, title, brand, price_jpy, price_usd, seller_id, 
                 zenmarket_url, yahoo_url, image_url, listing_type,
                 estimated_market_value, purchase_price, estimated_sell_price,
                 estimated_profit, roi_percent, is_profitable, profit_tier,
                 deal_quality, priority_score, message_id, channel_id,
                 keyword_used, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                listing_data['auction_id'],
                listing_data['title'],
                listing_data['brand'],
                listing_data['price_jpy'],
                listing_data['price_usd'],
                listing_data.get('seller_id', 'unknown'),
                listing_data['zenmarket_url'],
                listing_data.get('yahoo_url', ''),
                listing_data.get('image_url', ''),
                listing_data.get('listing_type', 'unknown'),
                listing_data.get('estimated_market_value', 0),
                profit_analysis.get('purchase_price', listing_data['price_usd']),
                profit_analysis.get('estimated_sell_price', 0),
                profit_analysis.get('estimated_profit', 0),
                profit_analysis.get('roi_percent', 0),
                profit_analysis.get('is_profitable', False),
                profit_tier,
                listing_data.get('deal_quality', 0.5),
                listing_data.get('priority_score', roi_percent / 100),
                message_id,
                listing_data.get('channel_id'),
                listing_data.get('keyword_used', ''),
                listing_data.get('source', 'luxury_profit_sniper')
            ))
        
        print(f"✅ Added profit listing: {listing_data['auction_id']} (ROI: {roi_percent:.0f}%)")
        return True
        
    except Exception as e:
        print(f"❌ Error adding profit listing: {e}")
        return False

def add_profit_user_bookmark(user_id, auction_id, bookmark_message_id, bookmark_channel_id, 
                           estimated_profit=0, roi_percent=0, reason='manual'):
    """Add user bookmark with profit tracking"""
    try:
        if db_manager.use_postgres:
            db_manager.execute_query('''
                INSERT INTO profit_user_bookmarks 
                (user_id, auction_id, bookmark_message_id, bookmark_channel_id, 
                 estimated_profit, roi_percent, bookmark_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, auction_id) DO UPDATE SET
                    bookmark_message_id = EXCLUDED.bookmark_message_id,
                    bookmark_channel_id = EXCLUDED.bookmark_channel_id,
                    estimated_profit = EXCLUDED.estimated_profit,
                    roi_percent = EXCLUDED.roi_percent
            ''', (user_id, auction_id, bookmark_message_id, bookmark_channel_id, 
                  estimated_profit, roi_percent, reason))
        else:
            db_manager.execute_query('''
                INSERT OR REPLACE INTO profit_user_bookmarks 
                (user_id, auction_id, bookmark_message_id, bookmark_channel_id,
                 estimated_profit, roi_percent, bookmark_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, auction_id, bookmark_message_id, bookmark_channel_id,
                  estimated_profit, roi_percent, reason))
        
        return True
    except Exception as e:
        print(f"❌ Error adding profit bookmark: {e}")
        return False

def get_profit_user_preferences(user_id):
    """Get user profit preferences"""
    try:
        result = db_manager.execute_query(
            'SELECT * FROM profit_user_preferences WHERE user_id = %s' if db_manager.use_postgres else 
            'SELECT * FROM profit_user_preferences WHERE user_id = ?',
            (user_id,),
            fetch_one=True
        )
        
        if result:
            if isinstance(result, dict):
                return result
            else:
                # Convert tuple to dict for SQLite
                columns = ['user_id', 'proxy_service', 'setup_complete', 'notifications_enabled',
                          'min_roi_threshold', 'max_price_alert', 'bookmark_method', 
                          'auto_bookmark_high_roi', 'preferred_brands', 'roi_alerts_enabled',
                          'ultra_profit_alerts', 'created_at', 'updated_at']
                return dict(zip(columns, result))
        else:
            return None
            
    except Exception as e:
        print(f"❌ Error getting profit user preferences: {e}")
        return None

def set_profit_user_preferences(user_id, **preferences):
    """Set user profit preferences"""
    try:
        if db_manager.use_postgres:
            db_manager.execute_query('''
                INSERT INTO profit_user_preferences (user_id, setup_complete, updated_at)
                VALUES (%s, TRUE, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id) DO UPDATE SET
                    setup_complete = TRUE,
                    updated_at = CURRENT_TIMESTAMP
            ''', (user_id,))
        else:
            db_manager.execute_query('''
                INSERT OR REPLACE INTO profit_user_preferences 
                (user_id, setup_complete, updated_at)
                VALUES (?, 1, CURRENT_TIMESTAMP)
            ''', (user_id,))
        
        return True
    except Exception as e:
        print(f"❌ Error setting profit user preferences: {e}")
        return False

def get_profit_stats():
    """Get comprehensive profit statistics"""
    try:
        stats = {}
        
        # Total listings by profit tier
        profit_tiers = db_manager.execute_query('''
            SELECT profit_tier, COUNT(*) as count, AVG(roi_percent) as avg_roi
            FROM profit_listings 
            GROUP BY profit_tier
        ''', fetch_all=True)
        
        stats['profit_tiers'] = {}
        if profit_tiers:
            for tier in profit_tiers:
                if isinstance(tier, dict):
                    stats['profit_tiers'][tier['profit_tier']] = {
                        'count': tier['count'],
                        'avg_roi': tier['avg_roi']
                    }
                else:
                    stats['profit_tiers'][tier[0]] = {
                        'count': tier[1],
                        'avg_roi': tier[2]
                    }
        
        # Overall stats
        overall = db_manager.execute_query('''
            SELECT 
                COUNT(*) as total_listings,
                AVG(roi_percent) as avg_roi,
                MAX(roi_percent) as max_roi,
                SUM(estimated_profit) as total_estimated_profit
            FROM profit_listings
        ''', fetch_one=True)
        
        if overall:
            if isinstance(overall, dict):
                stats['overall'] = overall
            else:
                stats['overall'] = {
                    'total_listings': overall[0],
                    'avg_roi': overall[1],
                    'max_roi': overall[2],
                    'total_estimated_profit': overall[3]
                }
        
        return stats
        
    except Exception as e:
        print(f"❌ Error getting profit stats: {e}")
        return {}

def add_scraper_stats(total_found=0, profitable_found=0, ultra_profit_found=0, 
                     sent_to_discord=0, errors_count=0, keywords_searched=0,
                     avg_roi_percent=0, cycle_time_seconds=0):
    """Add scraper statistics"""
    try:
        if db_manager.use_postgres:
            db_manager.execute_query('''
                INSERT INTO profit_scraper_stats 
                (total_found, profitable_found, ultra_profit_found, sent_to_discord,
                 errors_count, keywords_searched, avg_roi_percent, cycle_time_seconds)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', (total_found, profitable_found, ultra_profit_found, sent_to_discord,
                  errors_count, keywords_searched, avg_roi_percent, cycle_time_seconds))
        else:
            db_manager.execute_query('''
                INSERT INTO profit_scraper_stats 
                (total_found, profitable_found, ultra_profit_found, sent_to_discord,
                 errors_count, keywords_searched, avg_roi_percent, cycle_time_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (total_found, profitable_found, ultra_profit_found, sent_to_discord,
                  errors_count, keywords_searched, avg_roi_percent, cycle_time_seconds))
        
        return True
    except Exception as e:
        print(f"❌ Error adding scraper stats: {e}")
        return False

# Legacy function compatibility
def add_listing(listing_data, message_id):
    """Legacy compatibility function"""
    return add_profit_listing(listing_data, message_id)

def add_user_bookmark(user_id, auction_id, bookmark_message_id, bookmark_channel_id, auction_end_time=None):
    """Legacy compatibility function"""
    return add_profit_user_bookmark(user_id, auction_id, bookmark_message_id, bookmark_channel_id)

def get_user_proxy_preference(user_id):
    """Legacy compatibility function"""
    prefs = get_profit_user_preferences(user_id)
    if prefs:
        return prefs.get('proxy_service', 'zenmarket'), prefs.get('setup_complete', False)
    return 'zenmarket', False

def set_user_proxy_preference(user_id, proxy_service):
    """Legacy compatibility function"""
    return set_profit_user_preferences(user_id, proxy_service=proxy_service)

def init_subscription_tables():
    """Initialize subscription tables"""
    return db_manager.init_database()

def test_postgres_connection():
    """Test PostgreSQL connection"""
    try:
        if not db_manager.use_postgres:
            print("⚠️ Using SQLite, not PostgreSQL")
            return False
            
        result = db_manager.execute_query('SELECT version()', fetch_one=True)
        if result:
            print(f"✅ PostgreSQL connected: {result[0][:50]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ PostgreSQL connection test failed: {e}")
        return False