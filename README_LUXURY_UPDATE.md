# Luxury Sniper Update: BIN and Auction Separation

## Overview

The luxury scraper has been updated to handle **Buy It Now (BIN)** and **Auction** listings separately, with the Discord bot now posting to dedicated channels for each type.

## What's New

### 🔄 Scraper Updates
- **Separate scraping functions**: `scrape_yahoo_luxury_bin()` and `scrape_yahoo_luxury_auctions()`
- **BIN filtering**: Uses `auccat=0` parameter to get only Buy It Now listings
- **Auction filtering**: Uses `auccat=auction` parameter to get only auction listings
- **Dual-phase search**: Searches BIN first (higher priority), then auctions
- **Listing type tracking**: Each item is tagged with `listing_type: 'buy_it_now'` or `'auction'`

### 📺 Discord Bot Updates
- **Two separate channels**:
  - `#💎-luxury-under-60` - For auction listings
  - `#💎-buyitnow` - For Buy It Now listings
- **Smart routing**: Listings automatically go to the correct channel based on type
- **Different styling**: BIN listings show 🛒 emoji, auctions show 🔨 emoji
- **Enhanced embeds**: Different titles and footers for each listing type

## Channel Details

### 🔨 Auction Channel (`#💎-luxury-under-60`)
- **Purpose**: Traditional auction listings where users place bids
- **Emoji**: 🔨 (hammer for auctions)
- **Footer**: "🔨 Auction - Place your bid!"
- **Content**: Items that require bidding and have end times

### 🛒 Buy It Now Channel (`#💎-buyitnow`)
- **Purpose**: Instant purchase items with fixed prices
- **Emoji**: 🛒 (shopping cart for instant buy)
- **Footer**: "🛒 Buy It Now - Instant purchase!"
- **Content**: Items that can be purchased immediately

## Configuration

### Environment Variables
```bash
# Enable Discord integration
USE_DISCORD_BOT=true

# Discord bot URL (default: http://localhost:8002)
DISCORD_BOT_URL=http://localhost:8002

# Price limits
MAX_PRICE_USD=60
MIN_PRICE_USD=0.50
```

### Ports
- **Luxury Scraper**: Port 8003
- **Discord Bot**: Port 8002
- **Main System**: Port 8000 (if applicable)

## How It Works

### 1. Scraping Process
```
For each keyword:
  1. 🛒 Search BIN listings (auccat=0)
  2. 🔨 Search auction listings (auccat=auction)
  3. Process each type separately
  4. Tag items with listing_type
```

### 2. Discord Routing
```
Listing received → Check listing_type → Route to correct channel:
  - buy_it_now → #💎-buyitnow
  - auction → #💎-luxury-under-60
```

### 3. Channel Display
```
BIN Listings:
  🛒 ⚡ Balenciaga - $54.42
  Footer: 🛒 Buy It Now - Instant purchase!

Auction Listings:
  🔨 🖤 Rick Owens - $81.63
  Footer: 🔨 Auction - Place your bid!
```

## Testing

Run the test script to verify integration:

```bash
python3 test_luxury_integration.py
```

This will test:
- Discord bot health
- Luxury scraper health
- BIN webhook functionality
- Auction webhook functionality

## Benefits

### For Users
- **Clear separation**: Know immediately if an item is BIN or auction
- **Faster decisions**: BIN items can be purchased instantly
- **Better organization**: Each channel serves a specific purpose

### For Scraping
- **More targeted**: Separate search strategies for each type
- **Better filtering**: Yahoo's built-in category filters
- **Improved accuracy**: Dedicated parsing for each listing type

### For Management
- **Easier monitoring**: Track BIN vs auction performance separately
- **Better analytics**: Understand user preferences for each type
- **Optimized workflows**: Different handling for different listing types

## Troubleshooting

### Common Issues

1. **Channels not created**
   - Check bot permissions in Discord
   - Verify GUILD_ID is correct

2. **Listings not routing correctly**
   - Check `listing_type` field in scraper output
   - Verify webhook endpoint is `/webhook/listing`

3. **Scraping errors**
   - Check Yahoo Auctions accessibility
   - Verify price filters are working

### Logs to Check

- **Luxury Scraper**: Look for BIN/Auction phase logging
- **Discord Bot**: Check channel creation and routing logs
- **Webhook**: Monitor POST requests to `/webhook/listing`

## Future Enhancements

- **Smart scheduling**: Different search frequencies for BIN vs auctions
- **Price alerts**: Separate notification systems for each type
- **User preferences**: Allow users to follow specific channels
- **Analytics**: Track performance metrics per channel
- **Mobile optimization**: Different mobile layouts for each channel type

## Support

If you encounter issues:
1. Check the logs for both services
2. Run the test script to isolate problems
3. Verify environment variables are set correctly
4. Check Discord bot permissions and channel access
