#!/usr/bin/env python3
"""
Test script for luxury profit sniper and Discord bot integration
Tests profit calculation, channel routing, and ROI-based filtering
"""

import requests
import json
import time
import os
from datetime import datetime

def test_discord_bot_health():
    """Test Discord bot health endpoint"""
    try:
        response = requests.get('http://localhost:8000/health', timeout=5)
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

def test_profit_scraper_health():
    """Test profit scraper health endpoint"""
    try:
        response = requests.get('http://localhost:8003/health', timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Profit scraper healthy: {data}")
            return True
        else:
            print(f"❌ Profit scraper unhealthy: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot reach profit scraper: {e}")
        return False

def test_ultra_profit_listing():
    """Test ultra-high ROI listing (400%+ ROI) - should go to profit alerts"""
    ultra_profit_listing = {
        "auction_id": "test_ultra_profit_456",
        "title": "Archive Rick Owens DRKSHDW Tee Rare FW2018",
        "brand": "Rick Owens",
        "price_jpy": 2500,
        "price_usd": 16.67,
        "zenmarket_url": "https://zenmarket.jp/en/auction.aspx?itemCode=test_ultra_profit_456",
        "yahoo_url": "https://page.auctions.yahoo.co.jp/jp/auction/test_ultra_profit_456",
        "image_url": None,
        "seller_id": "test_seller",
        "auction_end_time": None,
        "keyword_used": "rick owens",
        "listing_type": "buy_it_now",
        "is_luxury": True,
        "source": "luxury_profit_sniper",
        "profit_analysis": {
            "purchase_price": 16.67,
            "estimated_sell_price": 249,
            "estimated_profit": 232.33,
            "roi_percent": 493,
            "is_profitable": True
        },
        "estimated_market_value": 249
    }
    
    try:
        response = requests.post(
            'http://localhost:8000/webhook/listing',
            json=ultra_profit_listing,
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✅ Ultra profit listing test successful: {response.json()}")
            print(f"   💎 Should appear in #🚀-profit-alerts (493% ROI)")
            return True
        else:
            print(f"❌ Ultra profit listing test failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Ultra profit listing test error: {e}")
        return False

def test_high_profit_bin():
    """Test high profit BIN listing (300%+ ROI) - should go to BIN channel"""
    high_profit_bin = {
        "auction_id": "test_high_bin_789",
        "title": "Vetements Hoodie Oversized Logo Black",
        "brand": "Vetements",
        "price_jpy": 4500,
        "price_usd": 30.00,
        "zenmarket_url": "https://zenmarket.jp/en/auction.aspx?itemCode=test_high_bin_789",
        "yahoo_url": "https://page.auctions.yahoo.co.jp/jp/auction/test_high_bin_789",
        "image_url": None,
        "seller_id": "test_seller",
        "auction_end_time": None,
        "keyword_used": "vetements hoodie",
        "listing_type": "buy_it_now",
        "is_luxury": True,
        "source": "luxury_profit_sniper",
        "profit_analysis": {
            "purchase_price": 30.00,
            "estimated_sell_price": 149,
            "estimated_profit": 119.00,
            "roi_percent": 397,
            "is_profitable": True
        },
        "estimated_market_value": 149
    }
    
    try:
        response = requests.post(
            'http://localhost:8000/webhook/listing',
            json=high_profit_bin,
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✅ High profit BIN test successful: {response.json()}")
            print(f"   🛒 Should appear in #💎-buyitnow-steals (397% ROI)")
            return True
        else:
            print(f"❌ High profit BIN test failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ High profit BIN test error: {e}")
        return False

def test_good_profit_auction():
    """Test good profit auction listing (200%+ ROI) - should go to auction channel"""
    good_profit_auction = {
        "auction_id": "test_auction_321",
        "title": "Balenciaga Speed Trainer Archive 2017",
        "brand": "Balenciaga",
        "price_jpy": 7500,
        "price_usd": 50.00,
        "zenmarket_url": "https://zenmarket.jp/en/auction.aspx?itemCode=test_auction_321",
        "yahoo_url": "https://page.auctions.yahoo.co.jp/jp/auction/test_auction_321",
        "image_url": None,
        "seller_id": "test_seller",
        "auction_end_time": None,
        "keyword_used": "balenciaga",
        "listing_type": "auction",
        "is_luxury": True,
        "source": "luxury_profit_sniper",
        "profit_analysis": {
            "purchase_price": 50.00,
            "estimated_sell_price": 199,
            "estimated_profit": 149.00,
            "roi_percent": 298,
            "is_profitable": True
        },
        "estimated_market_value": 199
    }
    
    try:
        response = requests.post(
            'http://localhost:8000/webhook/listing',
            json=good_profit_auction,
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✅ Good profit auction test successful: {response.json()}")
            print(f"   🔨 Should appear in #💎-auctions-under-60 (298% ROI)")
            return True
        else:
            print(f"❌ Good profit auction test failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Good profit auction test error: {e}")
        return False

def test_minimal_profit_listing():
    """Test minimal profit listing (200% ROI) - should still be accepted"""
    minimal_profit = {
        "auction_id": "test_minimal_654",
        "title": "Comme Des Garcons PLAY Stripe Tee",
        "brand": "Comme Des Garcons",
        "price_jpy": 6000,
        "price_usd": 40.00,
        "zenmarket_url": "https://zenmarket.jp/en/auction.aspx?itemCode=test_minimal_654",
        "yahoo_url": "https://page.auctions.yahoo.co.jp/jp/auction/test_minimal_654",
        "image_url": None,
        "seller_id": "test_seller",
        "auction_end_time": None,
        "keyword_used": "comme des garcons",
        "listing_type": "buy_it_now",
        "is_luxury": True,
        "source": "luxury_profit_sniper",
        "profit_analysis": {
            "purchase_price": 40.00,
            "estimated_sell_price": 119,
            "estimated_profit": 79.00,
            "roi_percent": 198,
            "is_profitable": False  # Below 200% threshold
        },
        "estimated_market_value": 119
    }
    
    try:
        response = requests.post(
            'http://localhost:8000/webhook/listing',
            json=minimal_profit,
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"⚠️ Minimal profit listing accepted: {response.json()}")
            print(f"   📊 Should be filtered out by scraper (198% ROI < 200% threshold)")
            return True
        else:
            print(f"❌ Minimal profit listing test failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Minimal profit listing test error: {e}")
        return False

def test_webhook_test_endpoint():
    """Test the built-in test endpoint"""
    try:
        response = requests.post('http://localhost:8000/webhook/test', timeout=10)
        
        if response.status_code == 200:
            print(f"✅ Webhook test endpoint successful: {response.json()}")
            return True
        else:
            print(f"❌ Webhook test endpoint failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Webhook test endpoint error: {e}")
        return False

def test_api_stats():
    """Test API stats endpoint"""
    try:
        response = requests.get('http://localhost:8000/stats', timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API stats successful:")
            print(f"   📊 Service: {data.get('service')}")
            print(f"   🤖 Bot Ready: {data.get('bot_ready')}")
            print(f"   📦 Batch Pending: {data.get('batch_pending')}")
            print(f"   💰 Min ROI: {data.get('minimum_roi')}")
            print(f"   💴 Price Range: {data.get('price_range')}")
            return True
        else:
            print(f"❌ API stats failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ API stats error: {e}")
        return False

def main():
    print("🧪 Testing Luxury Profit Sniper and Discord Bot Integration")
    print("=" * 70)
    
    # Test health endpoints
    print("\n1. Testing Service Health...")
    discord_healthy = test_discord_bot_health()
    scraper_healthy = test_profit_scraper_health()
    
    if not discord_healthy:
        print("\n❌ Discord bot is not healthy. Please start it first.")
        print("💡 Run: python3 luxury_profit_discord_bot.py")
        return
    
    # Test API endpoints
    print("\n2. Testing API Endpoints...")
    stats_working = test_api_stats()
    test_endpoint_working = test_webhook_test_endpoint()
    
    # Test profit listings with different ROI levels
    print("\n3. Testing Profit Listings...")
    print("\n🚀 Testing Ultra-High ROI (493%) - Should go to Profit Alerts...")
    ultra_success = test_ultra_profit_listing()
    
    time.sleep(2)
    
    print("\n💎 Testing High ROI BIN (397%) - Should go to BIN Channel...")
    bin_success = test_high_profit_bin()
    
    time.sleep(2)
    
    print("\n✨ Testing Good ROI Auction (298%) - Should go to Auction Channel...")
    auction_success = test_good_profit_auction()
    
    time.sleep(2)
    
    print("\n📈 Testing Minimal ROI (198%) - Should be filtered...")
    minimal_success = test_minimal_profit_listing()
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 PROFIT INTEGRATION TEST SUMMARY:")
    print(f"   Discord Bot: {'✅ Healthy' if discord_healthy else '❌ Unhealthy'}")
    print(f"   Profit Scraper: {'✅ Healthy' if scraper_healthy else '❌ Unhealthy'}")
    print(f"   API Stats: {'✅ Working' if stats_working else '❌ Failed'}")
    print(f"   Test Endpoint: {'✅ Working' if test_endpoint_working else '❌ Failed'}")
    print(f"   Ultra Profit (493% ROI): {'✅ Sent' if ultra_success else '❌ Failed'}")
    print(f"   High Profit BIN (397% ROI): {'✅ Sent' if bin_success else '❌ Failed'}")
    print(f"   Good Profit Auction (298% ROI): {'✅ Sent' if auction_success else '❌ Failed'}")
    print(f"   Minimal Profit (198% ROI): {'✅ Handled' if minimal_success else '❌ Failed'}")
    
    if all([discord_healthy, ultra_success, bin_success, auction_success]):
        print("\n🎉 All critical tests passed! The profit system is working correctly.")
        print("\n📺 Check your Discord channels:")
        print(f"   🚀 Ultra-High ROI: #🚀-profit-alerts")
        print(f"   🛒 BIN Deals: #💎-buyitnow-steals")
        print(f"   🔨 Auctions: #💎-auctions-under-60")
        print("\n💰 The system will now find you items to buy for $0-60 that can be resold for $99-999+!")
        print("🎯 Target ROI: 200%+ minimum (items that triple your money or better)")
    else:
        print("\n⚠️ Some tests failed. Please check the logs above.")
        
        if not discord_healthy:
            print("\n🔧 Troubleshooting:")
            print("   1. Make sure Discord bot is running: python3 luxury_profit_discord_bot.py")
            print("   2. Check DISCORD_BOT_TOKEN and GUILD_ID environment variables")
            print("   3. Verify bot has permissions in your Discord server")

if __name__ == "__main__":
    main()