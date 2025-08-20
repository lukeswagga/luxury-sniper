#!/usr/bin/env python3
"""
Test script for luxury scraper and Discord bot integration
Tests both BIN and auction listing handling
"""

import requests
import json
import time
import os

def test_discord_bot_health():
    """Test Discord bot health endpoint"""
    try:
        response = requests.get('http://localhost:8002/health', timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Discord bot healthy: {data}")
            return True
        else:
            print(f"❌ Discord bot unhealthy: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot reach Discord bot: {e}")
        return False

def test_luxury_scraper_health():
    """Test luxury scraper health endpoint"""
    try:
        response = requests.get('http://localhost:8003/health', timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Luxury scraper healthy: {data}")
            return True
        else:
            print(f"❌ Luxury scraper unhealthy: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot reach luxury scraper: {e}")
        return False

def test_webhook_listing():
    """Test sending a sample listing to the Discord bot"""
    sample_listing = {
        "auction_id": "test_bin_123",
        "title": "Test Balenciaga T-Shirt - Luxury Fashion Item",
        "brand": "Balenciaga",
        "price_jpy": 8000,
        "price_usd": 54.42,
        "zenmarket_url": "https://zenmarket.jp/en/auction.aspx?itemCode=test_bin_123",
        "yahoo_url": "https://page.auctions.yahoo.co.jp/jp/auction/test_bin_123",
        "image_url": None,
        "seller_id": "test_seller",
        "auction_end_time": None,
        "keyword_used": "balenciaga",
        "deal_quality": 0.8,
        "listing_type": "buy_it_now",
        "is_luxury": True,
        "source": "luxury_sniper"
    }
    
    try:
        response = requests.post(
            'http://localhost:8002/webhook/listing',
            json=sample_listing,
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✅ Webhook test successful: {response.json()}")
            return True
        else:
            print(f"❌ Webhook test failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Webhook test error: {e}")
        return False

def test_auction_listing():
    """Test sending a sample auction listing"""
    sample_auction = {
        "auction_id": "test_auction_456",
        "title": "Test Rick Owens Jacket - Archive Piece",
        "brand": "Rick Owens",
        "price_jpy": 12000,
        "price_usd": 81.63,
        "zenmarket_url": "https://zenmarket.jp/en/auction.aspx?itemCode=test_auction_456",
        "yahoo_url": "https://page.auctions.yahoo.co.jp/jp/auction/test_auction_456",
        "image_url": None,
        "seller_id": "test_seller",
        "auction_end_time": None,
        "keyword_used": "rick owens",
        "deal_quality": 0.9,
        "listing_type": "auction",
        "is_luxury": True,
        "source": "luxury_sniper"
    }
    
    try:
        response = requests.post(
            'http://localhost:8002/webhook/listing',
            json=sample_auction,
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✅ Auction webhook test successful: {response.json()}")
            return True
        else:
            print(f"❌ Auction webhook test failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Auction webhook test error: {e}")
        return False

def main():
    print("🧪 Testing Luxury Scraper and Discord Bot Integration")
    print("=" * 60)
    
    # Test health endpoints
    print("\n1. Testing Discord Bot Health...")
    discord_healthy = test_discord_bot_health()
    
    print("\n2. Testing Luxury Scraper Health...")
    scraper_healthy = test_luxury_scraper_health()
    
    if not discord_healthy:
        print("\n❌ Discord bot is not healthy. Please start it first.")
        return
    
    # Test webhooks
    print("\n3. Testing Buy It Now Webhook...")
    bin_success = test_webhook_listing()
    
    print("\n4. Testing Auction Webhook...")
    auction_success = test_auction_listing()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY:")
    print(f"   Discord Bot: {'✅ Healthy' if discord_healthy else '❌ Unhealthy'}")
    print(f"   Luxury Scraper: {'✅ Healthy' if scraper_healthy else '❌ Unhealthy'}")
    print(f"   BIN Webhook: {'✅ Working' if bin_success else '❌ Failed'}")
    print(f"   Auction Webhook: {'✅ Working' if auction_success else '❌ Failed'}")
    
    if all([discord_healthy, bin_success, auction_success]):
        print("\n🎉 All tests passed! The integration is working correctly.")
        print("\n📺 Check your Discord channels:")
        print(f"   🔨 Auctions: #💎-luxury-under-60")
        print(f"   🛒 Buy It Now: #💎-buyitnow")
    else:
        print("\n⚠️ Some tests failed. Please check the logs above.")

if __name__ == "__main__":
    main()
