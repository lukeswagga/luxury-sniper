#!/usr/bin/env python3
"""
Queue Manager for Grizzly Jacket Scraper
Manages a queue between scraper and Discord bot to avoid rate limits
"""

import json
import os
import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to use Redis, fallback to file-based queue
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available, using file-based queue")

QUEUE_FILE = "grizzly_queue.json"
MAX_QUEUE_SIZE = 1000  # Prevent queue from growing too large

class QueueManager:
    def __init__(self):
        self.redis_client = None
        self.use_redis = False
        self.queue_key = "grizzly:queue"
        
        # Try to connect to Redis
        if REDIS_AVAILABLE:
            try:
                redis_url = os.environ.get('REDIS_URL')
                if redis_url:
                    self.redis_client = redis.from_url(redis_url, decode_responses=True)
                    self.use_redis = True
                    logger.info("✅ Connected to Redis queue")
                else:
                    # Try default localhost Redis
                    self.redis_client = redis.Redis(
                        host=os.environ.get('REDIS_HOST', 'localhost'),
                        port=int(os.environ.get('REDIS_PORT', 6379)),
                        db=0,
                        decode_responses=True
                    )
                    # Test connection
                    self.redis_client.ping()
                    self.use_redis = True
                    logger.info("✅ Connected to local Redis queue")
            except Exception as e:
                logger.warning(f"⚠️ Redis connection failed, using file queue: {e}")
                self.use_redis = False
        
        if not self.use_redis:
            logger.info("📁 Using file-based queue")
            self._ensure_queue_file()
    
    def _ensure_queue_file(self):
        """Ensure queue file exists"""
        if not os.path.exists(QUEUE_FILE):
            with open(QUEUE_FILE, 'w') as f:
                json.dump([], f)
    
    def add_listing(self, listing_data: Dict[str, Any], priority: float = 0.5) -> bool:
        """
        Add a listing to the queue
        
        Args:
            listing_data: Listing information
            priority: Priority score (0.0 to 1.0, higher = more important)
            
        Returns:
            True if added successfully, False otherwise
        """
        try:
            listing_data['queued_at'] = datetime.now().isoformat()
            listing_data['priority'] = priority
            
            if self.use_redis:
                # Use Redis sorted set for priority queue
                score = priority * 1000000 + time.time()  # Priority + timestamp
                self.redis_client.zadd(self.queue_key, {json.dumps(listing_data): score})
                
                # Keep queue size manageable
                queue_size = self.redis_client.zcard(self.queue_key)
                if queue_size > MAX_QUEUE_SIZE:
                    # Remove lowest priority items
                    self.redis_client.zremrangebyrank(self.queue_key, 0, queue_size - MAX_QUEUE_SIZE)
                
                logger.debug(f"📥 Added to Redis queue: {listing_data.get('auction_id')} (priority: {priority:.2f})")
                return True
            else:
                # File-based queue
                self._ensure_queue_file()
                with open(QUEUE_FILE, 'r') as f:
                    queue = json.load(f)
                
                # Add to queue with priority
                queue.append(listing_data)
                
                # Sort by priority (highest first)
                queue.sort(key=lambda x: x.get('priority', 0.5), reverse=True)
                
                # Limit queue size
                if len(queue) > MAX_QUEUE_SIZE:
                    queue = queue[:MAX_QUEUE_SIZE]
                
                with open(QUEUE_FILE, 'w') as f:
                    json.dump(queue, f, ensure_ascii=False, indent=2)
                
                logger.debug(f"📥 Added to file queue: {listing_data.get('auction_id')} (priority: {priority:.2f})")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error adding to queue: {e}")
            return False
    
    def get_next_listing(self) -> Optional[Dict[str, Any]]:
        """
        Get the next listing from the queue (highest priority first)
        
        Returns:
            Listing data or None if queue is empty
        """
        try:
            if self.use_redis:
                # Get highest priority item (highest score)
                items = self.redis_client.zrevrange(self.queue_key, 0, 0, withscores=False)
                if not items:
                    return None
                
                listing_data = json.loads(items[0])
                # Remove from queue
                self.redis_client.zrem(self.queue_key, items[0])
                return listing_data
            else:
                # File-based queue
                if not os.path.exists(QUEUE_FILE):
                    return None
                
                with open(QUEUE_FILE, 'r') as f:
                    queue = json.load(f)
                
                if not queue:
                    return None
                
                # Get highest priority item
                listing_data = queue.pop(0)
                
                # Save updated queue
                with open(QUEUE_FILE, 'w') as f:
                    json.dump(queue, f, ensure_ascii=False, indent=2)
                
                return listing_data
                
        except Exception as e:
            logger.error(f"❌ Error getting from queue: {e}")
            return None
    
    def get_queue_size(self) -> int:
        """Get current queue size"""
        try:
            if self.use_redis:
                return self.redis_client.zcard(self.queue_key)
            else:
                if not os.path.exists(QUEUE_FILE):
                    return 0
                with open(QUEUE_FILE, 'r') as f:
                    queue = json.load(f)
                return len(queue)
        except Exception as e:
            logger.error(f"❌ Error getting queue size: {e}")
            return 0
    
    def clear_queue(self) -> bool:
        """Clear the entire queue"""
        try:
            if self.use_redis:
                self.redis_client.delete(self.queue_key)
                logger.info("🗑️ Cleared Redis queue")
            else:
                with open(QUEUE_FILE, 'w') as f:
                    json.dump([], f)
                logger.info("🗑️ Cleared file queue")
            return True
        except Exception as e:
            logger.error(f"❌ Error clearing queue: {e}")
            return False

# Global queue manager instance
queue_manager = QueueManager()

