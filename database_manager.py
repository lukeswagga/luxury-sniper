import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
import json
from datetime import datetime

class DatabaseManager:
    def __init__(self):
        self.database_url = os.environ.get('DATABASE_URL')
        self.use_postgres = bool(self.database_url)
        
        if not self.use_postgres:
            self.db_path = 'auction_tracking.db'
            print("🗄️ Using SQLite database: auction_tracking.db")
        else:
            print("🐘 Using PostgreSQL database")
        
        self.init_database_with_retry()
    
    def init_database_with_retry(self, max_retries=3, retry_delay=5):
        """Initialize database with retry logic for Railway deployments"""
        import time
        
        for attempt in range(1, max_retries + 1):
            try:
                print(f"🔄 Database initialization attempt {attempt}/{max_retries}")
                self.init_database()
                print(f"✅ Database initialized successfully on attempt {attempt}")
                return
            except Exception as e:
                print(f"⚠️ Database connection attempt {attempt} failed: {e}")
                if attempt < max_retries:
                    print(f"⏳ Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    print(f"❌ All {max_retries} database connection attempts failed")
                    print(f"❌ Final error: {e}")
                    # Don't raise exception, allow app to start but log the error
                    print("⚠️ Starting app without database connection - will retry on first use")
    
    @contextmanager
    def get_connection(self):
        """Get database connection (PostgreSQL or SQLite)"""
        if self.use_postgres:
            conn = psycopg2.connect(
                self.database_url,
                cursor_factory=RealDictCursor,
                connect_timeout=10  # Add 10 second connection timeout
            )
            try:
                yield conn
            finally:
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            # Don't use Row factory for SQLite to maintain tuple compatibility
            try:
                yield conn
            finally:
                conn.close()
    
    def init_database(self):
        """Initialize database tables (works for both PostgreSQL and SQLite)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if self.use_postgres:
                self._create_postgres_tables(cursor)
            else:
                self._create_sqlite_tables(cursor)
            
            conn.commit()
            print("✅ Database tables initialized")
    
    def _create_postgres_tables(self, cursor):
        """Create PostgreSQL tables with all required columns"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS listings (
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
                deal_quality REAL DEFAULT 0.5,
                priority_score REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_id BIGINT,
                auction_end_time TIMESTAMP,
                reminder_1h_sent BOOLEAN DEFAULT FALSE,
                reminder_5m_sent BOOLEAN DEFAULT FALSE
            )
        ''')

        # Ensure new columns exist for legacy installations
        extra_columns = [
            ("auction_end_time", "TIMESTAMP"),
            ("reminder_1h_sent", "BOOLEAN DEFAULT FALSE"),
            ("reminder_5m_sent", "BOOLEAN DEFAULT FALSE"),
        ]
        for col_name, col_def in extra_columns:
            cursor.execute(
                f"ALTER TABLE listings ADD COLUMN IF NOT EXISTS {col_name} {col_def}"
            )
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reactions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                auction_id VARCHAR(100),
                reaction_type VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id BIGINT PRIMARY KEY,
                proxy_service VARCHAR(50) DEFAULT 'zenmarket',
                setup_complete BOOLEAN DEFAULT FALSE,
                notifications_enabled BOOLEAN DEFAULT TRUE,
                min_quality_threshold REAL DEFAULT 0.3,
                max_price_alert REAL DEFAULT 1000.0,
                bookmark_method VARCHAR(20) DEFAULT 'private_channel',
                auto_bookmark_likes BOOLEAN DEFAULT TRUE,
                preferred_sizes TEXT,
                size_alerts_enabled BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_bookmarks (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                auction_id VARCHAR(100),
                bookmark_message_id BIGINT,
                bookmark_channel_id BIGINT,
                auction_end_time TIMESTAMP,
                reminder_sent_1h BOOLEAN DEFAULT FALSE,
                reminder_sent_5m BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, auction_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scraper_stats (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_found INTEGER DEFAULT 0,
                quality_filtered INTEGER DEFAULT 0,
                sent_to_discord INTEGER DEFAULT 0,
                errors_count INTEGER DEFAULT 0,
                keywords_searched INTEGER DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_subscriptions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT UNIQUE,
                tier VARCHAR(20) DEFAULT 'free',
                upgraded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                payment_provider VARCHAR(50),
                subscription_id VARCHAR(100),
                status VARCHAR(20) DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Add missing columns if they don't exist
        self._add_missing_columns_postgres(cursor)
        
        # Create indexes
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_listings_brand ON listings(brand)",
            "CREATE INDEX IF NOT EXISTS idx_listings_created_at ON listings(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_listings_auction_end ON listings(auction_end_time)",
            "CREATE INDEX IF NOT EXISTS idx_reactions_user_id ON reactions(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_reactions_auction_id ON reactions(auction_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_bookmarks_user_id ON user_bookmarks(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_bookmarks_auction_id ON user_bookmarks(auction_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_bookmarks_end_time ON user_bookmarks(auction_end_time)",
        ]
        
        for index_sql in indexes:
            try:
                cursor.execute(index_sql)
            except Exception as e:
                if "already exists" not in str(e):
                    print(f"Index warning: {e}")
    
    def _add_missing_columns_postgres(self, cursor):
        """Add missing columns to existing PostgreSQL tables"""
        missing_columns = [
            ("listings", "auction_end_time", "TIMESTAMP"),
            ("listings", "reminder_1h_sent", "BOOLEAN DEFAULT FALSE"),
            ("listings", "reminder_5m_sent", "BOOLEAN DEFAULT FALSE"),
            ("user_preferences", "size_alerts_enabled", "BOOLEAN DEFAULT FALSE"),
            ("user_preferences", "preferred_sizes", "TEXT"),
            ("user_preferences", "auto_bookmark_likes", "BOOLEAN DEFAULT TRUE"),
        ]
        
        for table_name, column_name, column_type in missing_columns:
            try:
                # Validate table and column names to prevent SQL injection
                if table_name not in ['listings', 'user_preferences', 'user_bookmarks', 'reactions', 'scraper_stats']:
                    print(f"⚠️ Skipping invalid table name: {table_name}")
                    continue
                if not column_name.replace('_', '').isalnum():
                    print(f"⚠️ Skipping invalid column name: {column_name}")
                    continue
                if not column_type.replace(' ', '').replace('(', '').replace(')', '').replace('DEFAULT', '').replace('FALSE', '').replace('TRUE', '').replace('NOT', '').replace('NULL', '').isalnum():
                    print(f"⚠️ Skipping invalid column type: {column_type}")
                    continue
                
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_type}")
                print(f"✅ Added missing column: {table_name}.{column_name}")
            except Exception as e:
                if "already exists" not in str(e):
                    print(f"⚠️ Column add warning for {table_name}.{column_name}: {e}")
    
    def _create_sqlite_tables(self, cursor):
        """Create SQLite tables with all required columns"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS listings (
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
                deal_quality REAL DEFAULT 0.5,
                priority_score REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_id INTEGER,
                auction_end_time TIMESTAMP,
                reminder_1h_sent BOOLEAN DEFAULT FALSE,
                reminder_5m_sent BOOLEAN DEFAULT FALSE
            )
        ''')

        # Ensure new columns exist for legacy installations
        extra_columns = [
            ("auction_end_time", "TIMESTAMP"),
            ("reminder_1h_sent", "BOOLEAN DEFAULT FALSE"),
            ("reminder_5m_sent", "BOOLEAN DEFAULT FALSE"),
        ]
        for col_name, col_def in extra_columns:
            try:
                # Validate column name to prevent SQL injection
                if not col_name.replace('_', '').isalnum():
                    print(f"⚠️ Skipping invalid column name: {col_name}")
                    continue
                if not col_def.replace(' ', '').replace('(', '').replace(')', '').replace('DEFAULT', '').replace('FALSE', '').replace('TRUE', '').replace('NOT', '').replace('NULL', '').isalnum():
                    print(f"⚠️ Skipping invalid column definition: {col_def}")
                    continue
                
                cursor.execute(
                    f"ALTER TABLE listings ADD COLUMN {col_name} {col_def}"
                )
            except Exception as e:
                if "duplicate column name" not in str(e).lower():
                    print(f"Column addition warning: {e}")
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                auction_id TEXT,
                reaction_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id INTEGER PRIMARY KEY,
                proxy_service TEXT DEFAULT 'zenmarket',
                setup_complete BOOLEAN DEFAULT FALSE,
                notifications_enabled BOOLEAN DEFAULT TRUE,
                min_quality_threshold REAL DEFAULT 0.3,
                max_price_alert REAL DEFAULT 1000.0,
                bookmark_method TEXT DEFAULT 'private_channel',
                auto_bookmark_likes BOOLEAN DEFAULT TRUE,
                preferred_sizes TEXT,
                size_alerts_enabled BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                auction_id TEXT,
                bookmark_message_id INTEGER,
                bookmark_channel_id INTEGER,
                auction_end_time TIMESTAMP,
                reminder_sent_1h BOOLEAN DEFAULT FALSE,
                reminder_sent_5m BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, auction_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scraper_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_found INTEGER DEFAULT 0,
                quality_filtered INTEGER DEFAULT 0,
                sent_to_discord INTEGER DEFAULT 0,
                errors_count INTEGER DEFAULT 0,
                keywords_searched INTEGER DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                tier TEXT DEFAULT 'free',
                upgraded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                payment_provider TEXT,
                subscription_id TEXT,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

# Initialize the database manager
db_manager = DatabaseManager()

def add_listing(auction_data, message_id):
    """Add listing to database with proper error handling"""
    try:
        if db_manager.use_postgres:
            result = db_manager.execute_query('''
                INSERT INTO listings 
                (auction_id, title, brand, price_jpy, price_usd, seller_id, 
                 zenmarket_url, yahoo_url, image_url, deal_quality, priority_score, message_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (auction_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    message_id = EXCLUDED.message_id
            ''', (
                auction_data['auction_id'],
                auction_data['title'],
                auction_data['brand'],
                auction_data['price_jpy'],
                auction_data['price_usd'],
                auction_data.get('seller_id', 'unknown'),
                auction_data['zenmarket_url'],
                auction_data.get('yahoo_url', ''),
                auction_data.get('image_url', ''),
                auction_data.get('deal_quality', 0.5),
                auction_data.get('priority', 0.0),
                message_id
                # REMOVED: auction_end_time
            ))
        else:
            result = db_manager.execute_query('''
                INSERT OR REPLACE INTO listings 
                (auction_id, title, brand, price_jpy, price_usd, seller_id, 
                 zenmarket_url, yahoo_url, image_url, deal_quality, priority_score, message_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                auction_data['auction_id'],
                auction_data['title'],
                auction_data['brand'],
                auction_data['price_jpy'],
                auction_data['price_usd'],
                auction_data.get('seller_id', 'unknown'),
                auction_data['zenmarket_url'],
                auction_data.get('yahoo_url', ''),
                auction_data.get('image_url', ''),
                auction_data.get('deal_quality', 0.5),
                auction_data.get('priority', 0.0),
                message_id
                # REMOVED: auction_end_time
            ))
        
        print(f"✅ Added listing to database: {auction_data['auction_id']}")
        return True
        
    except Exception as e:
        print(f"❌ Error adding listing to database: {e}")
        print(f"❌ Full traceback: {e}")
        return False

def add_user_bookmark(user_id, auction_id, bookmark_message_id, bookmark_channel_id, auction_end_time=None):
    """Add user bookmark with proper conflict handling"""
    try:
        if db_manager.use_postgres:
            db_manager.execute_query('''
                INSERT INTO user_bookmarks 
                (user_id, auction_id, bookmark_message_id, bookmark_channel_id, auction_end_time)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, auction_id) DO UPDATE SET
                    bookmark_message_id = EXCLUDED.bookmark_message_id,
                    bookmark_channel_id = EXCLUDED.bookmark_channel_id,
                    auction_end_time = EXCLUDED.auction_end_time
            ''', (user_id, auction_id, bookmark_message_id, bookmark_channel_id, auction_end_time))
        else:
            db_manager.execute_query('''
                INSERT OR REPLACE INTO user_bookmarks 
                (user_id, auction_id, bookmark_message_id, bookmark_channel_id, auction_end_time)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, auction_id, bookmark_message_id, bookmark_channel_id, auction_end_time))
        
        return True
    except Exception as e:
        print(f"❌ Error adding bookmark: {e}")
        return False

def get_user_proxy_preference(user_id):
    """Get user proxy preference with fallback"""
    try:
        result = db_manager.execute_query(
            'SELECT proxy_service, setup_complete FROM user_preferences WHERE user_id = %s' if db_manager.use_postgres else 'SELECT proxy_service, setup_complete FROM user_preferences WHERE user_id = ?',
            (user_id,),
            fetch_one=True
        )
        
        if result:
            # Handle dict results properly
            if isinstance(result, dict):
                proxy_service = result.get('proxy_service', 'zenmarket')
                setup_complete = result.get('setup_complete', False)
            else:
                # Handle tuple results
                proxy_service = result[0] if len(result) > 0 else 'zenmarket'
                setup_complete = result[1] if len(result) > 1 else False
            
            # Ensure setup_complete is boolean
            setup_complete = bool(setup_complete)
            
            return proxy_service, setup_complete
        else:
            return "zenmarket", False
            
    except Exception as e:
        print(f"❌ Error getting user preference: {e}")
        return "zenmarket", False

def set_user_proxy_preference(user_id, proxy_service):
    """Set user proxy preference with proper upsert"""
    try:
        if db_manager.use_postgres:
            db_manager.execute_query('''
                INSERT INTO user_preferences (user_id, proxy_service, setup_complete, updated_at)
                VALUES (%s, %s, TRUE, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id) DO UPDATE SET
                    proxy_service = EXCLUDED.proxy_service,
                    setup_complete = TRUE,
                    updated_at = CURRENT_TIMESTAMP
            ''', (user_id, proxy_service))
        else:
            db_manager.execute_query('''
                INSERT OR REPLACE INTO user_preferences 
                (user_id, proxy_service, setup_complete, updated_at)
                VALUES (?, ?, 1, CURRENT_TIMESTAMP)
            ''', (user_id, proxy_service))
        
        print(f"✅ Set user {user_id} setup_complete = TRUE")  # Debug line
        return True
    except Exception as e:
        print(f"❌ Error setting user preference: {e}")
        return False

def get_user_size_preferences(user_id):
    """Get user size preferences with proper column handling"""
    try:
        result = db_manager.execute_query(
            'SELECT preferred_sizes, size_alerts_enabled FROM user_preferences WHERE user_id = %s' if db_manager.use_postgres else 'SELECT preferred_sizes, size_alerts_enabled FROM user_preferences WHERE user_id = ?',
            (user_id,),
            fetch_one=True
        )
        
        if result and result[0]:
            sizes = result[0].split(',') if result[0] else []
            enabled = result[1] if result[1] is not None else False
            return sizes, enabled
        return [], False
    except Exception as e:
        print(f"❌ Error getting size preferences: {e}")
        return [], False

def set_user_size_preferences(user_id, sizes):
    """Set user size preferences with proper upsert"""
    try:
        sizes_str = ','.join(sizes) if sizes else ''
        
        if db_manager.use_postgres:
            db_manager.execute_query('''
                INSERT INTO user_preferences (user_id, preferred_sizes, size_alerts_enabled, updated_at)
                VALUES (%s, %s, TRUE, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id) DO UPDATE SET
                    preferred_sizes = EXCLUDED.preferred_sizes,
                    size_alerts_enabled = TRUE,
                    updated_at = CURRENT_TIMESTAMP
            ''', (user_id, sizes_str))
        else:
            db_manager.execute_query('''
                INSERT OR REPLACE INTO user_preferences 
                (user_id, preferred_sizes, size_alerts_enabled, updated_at)
                VALUES (?, ?, TRUE, CURRENT_TIMESTAMP)
            ''', (user_id, sizes_str))
        return True
    except Exception as e:
        print(f"❌ Error setting size preferences: {e}")
        return False

def fix_missing_columns():
    """Fix missing columns in existing database"""
    try:
        if db_manager.use_postgres:
            # Add missing size_alerts_enabled column
            db_manager.execute_query('''
                ALTER TABLE user_preferences 
                ADD COLUMN IF NOT EXISTS size_alerts_enabled BOOLEAN DEFAULT FALSE
            ''')
            print("✅ Added size_alerts_enabled column")
        else:
            # For SQLite, we need to check if column exists first
            try:
                db_manager.execute_query('''
                    ALTER TABLE user_preferences 
                    ADD COLUMN size_alerts_enabled BOOLEAN DEFAULT FALSE
                ''')
                print("✅ Added size_alerts_enabled column")
            except Exception as e:
                if "duplicate column name" not in str(e).lower():
                    print(f"⚠️ Column add warning: {e}")
    except Exception as e:
        if "already exists" not in str(e):
            print(f"⚠️ Column add warning: {e}")

def mark_reminder_sent(user_id, auction_id, reminder_type='1h'):
    """Mark reminder as sent with proper query syntax"""
    try:
        if reminder_type == '1h':
            if db_manager.use_postgres:
                query = 'UPDATE user_bookmarks SET reminder_sent_1h = TRUE WHERE user_id = %s AND auction_id = %s'
            else:
                query = 'UPDATE user_bookmarks SET reminder_sent_1h = TRUE WHERE user_id = ? AND auction_id = ?'
        else:
            if db_manager.use_postgres:
                query = 'UPDATE user_bookmarks SET reminder_sent_5m = TRUE WHERE user_id = %s AND auction_id = %s'
            else:
                query = 'UPDATE user_bookmarks SET reminder_sent_5m = TRUE WHERE user_id = ? AND auction_id = ?'
        
        db_manager.execute_query(query, (user_id, auction_id))
        return True
    except Exception as e:
        print(f"❌ Error marking reminder sent: {e}")
        return False

def clear_user_bookmarks(user_id):
    """Clear user bookmarks with proper count"""
    try:
        count_result = db_manager.execute_query(
            'SELECT COUNT(*) FROM user_bookmarks WHERE user_id = %s' if db_manager.use_postgres else 'SELECT COUNT(*) FROM user_bookmarks WHERE user_id = ?',
            (user_id,),
            fetch_one=True
        )
        
        count = count_result[0] if count_result else 0
        
        if count > 0:
            db_manager.execute_query(
                'DELETE FROM user_bookmarks WHERE user_id = %s' if db_manager.use_postgres else 'DELETE FROM user_bookmarks WHERE user_id = ?',
                (user_id,)
            )
        
        return count
    except Exception as e:
        print(f"❌ Error clearing bookmarks: {e}")
        return 0

def test_postgres_connection():
    """Test PostgreSQL connection and show table status"""
    try:
        if not db_manager.use_postgres:
            print("⚠️ Using SQLite, not PostgreSQL")
            return False
            
        result = db_manager.execute_query('SELECT version()', fetch_one=True)
        if result:
            print(f"✅ PostgreSQL connected: {result[0][:50]}...")
        
        tables = db_manager.execute_query('''
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public'
        ''', fetch_all=True)
        
        print(f"📊 Existing tables: {[table[0] for table in tables] if tables else 'None'}")
        
        for table_name, in (tables or []):
            try:
                count = db_manager.execute_query(f'SELECT COUNT(*) FROM {table_name}', fetch_one=True)
                print(f"   {table_name}: {count[0] if count else 0} rows")
            except Exception as e:
                print(f"   {table_name}: Error counting rows - {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ PostgreSQL connection test failed: {e}")
        return False

def init_subscription_tables():
    """Initialize subscription tables"""
    try:
        print("🔧 Initializing subscription tables...")
        db_manager.init_database()
        
        # Fix any missing columns
        fix_missing_columns()
        
        print("✅ Subscription tables initialized successfully")
        return True
    except Exception as e:
        print(f"❌ Error initializing subscription tables: {e}")
        return False