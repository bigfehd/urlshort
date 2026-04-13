# Analytics Testing Quick Start Guide

Quick examples to test all the new analytics endpoints.

## Prerequisites

Start the services:
```bash
docker-compose up -d
# Or with local setup:
# python -m uvicorn app.main:app --reload
```

## Create Test Data

First, create some URLs to test with:

```bash
# Create URL 1
curl -X POST http://localhost:8000/api/shorten \
  -H "Content-Type: application/json" \
  -d '{"original_url": "https://github.com/openai/gpt-4", "description": "GPT-4 Repository"}'

# Response:
# {"short_code":"1","short_url":"http://localhost:8000/1","original_url":"..."}

# Create URL 2
curl -X POST http://localhost:8000/api/shorten \
  -H "Content-Type: application/json" \
  -d '{"original_url": "https://python.org", "description": "Python Official"}'

# Create URL 3
curl -X POST http://localhost:8000/api/shorten \
  -H "Content-Type: application/json" \
  -d '{"original_url": "https://fastapi.tiangolo.com", "description": "FastAPI Docs"}'
```

## Generate Test Clicks

Simulate clicks from different devices:

```bash
# Desktop browser
for i in {1..5}; do
  curl -s -o /dev/null -L \
    -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0" \
    http://localhost:8000/1
  sleep 1
done

# Mobile browser
for i in {1..3}; do
  curl -s -o /dev/null -L \
    -H "User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 14_0)" \
    http://localhost:8000/1
  sleep 1
done

# Bot
curl -s -o /dev/null -L \
  -H "User-Agent: curl/7.64.1" \
  http://localhost:8000/1

# More clicks on other URLs
for i in {1..10}; do
  curl -s -o /dev/null -L \
    -H "User-Agent: Mozilla/5.0 (Android)" \
    http://localhost:8000/2
  sleep 0.5
done
```

## Test New Endpoints

### 1. Top URLs (Last 24h)

```bash
# Get top 5 URLs in last 24 hours
curl http://localhost:8000/api/analytics/popular/24h?limit=5 | python -m json.tool

# Example Response:
# {
#   "period": "last_24_hours",
#   "returned_count": 3,
#   "top_urls": [
#     {
#       "short_code": "2",
#       "original_url": "https://python.org",
#       "click_count": 10,
#       "device_breakdown": {
#         "desktop": 5,
#         "mobile": 5,
#         "bot": 0
#       }
#     },
#     ...
#   ]
# }
```

### 2. Hourly Analytics (7 Days)

```bash
# Get hourly breakdown for URL "1"
curl http://localhost:8000/api/analytics/1/hourly-7d | python -m json.tool

# Example Response:
# {
#   "short_code": "1",
#   "period_days": 7,
#   "total_clicks": 9,
#   "hourly_data": [
#     {
#       "timestamp": "2024-01-15T10:00:00Z",
#       "hour": 10,
#       "clicks": 4,
#       "devices": {
#         "desktop": 3,
#         "mobile": 1,
#         "bot": 0
#       }
#     },
#     ...
#   ]
# }
```

### 3. Device Analytics

```bash
# Get device distribution for URL "1"
curl http://localhost:8000/api/analytics/1/device-analytics?days=7 | python -m json.tool

# Example Response:
# {
#   "short_code": "1",
#   "period_days": 7,
#   "total_clicks": 9,
#   "device_distribution": {
#     "desktop": {
#       "count": 5,
#       "percentage": 55.56
#     },
#     "mobile": {
#       "count": 3,
#       "percentage": 33.33
#     },
#     "bot": {
#       "count": 1,
#       "percentage": 11.11
#     }
#   }
# }
```

### 4. Real-Time Clicks Per Minute (Global)

```bash
# Get system-wide clicks per minute
curl http://localhost:8000/api/analytics/realtime/clicks-per-minute | python -m json.tool

# Example Response:
# {
#   "period_seconds": 60,
#   "clicks_per_minute": 42,
#   "short_code": null,
#   "average_clicks_per_second": 0.7
# }
```

### 5. Real-Time Clicks Per Minute (Specific URL)

```bash
# Get clicks per minute for URL "1"
curl "http://localhost:8000/api/analytics/realtime/clicks-per-minute?short_code=1" | python -m json.tool

# Example Response:
# {
#   "period_seconds": 60,
#   "clicks_per_minute": 12,
#   "short_code": "1",
#   "average_clicks_per_second": 0.2
# }
```

## View in Swagger UI

All endpoints are documented in interactive Swagger UI:

```bash
# Open in browser
http://localhost:8000/docs
```

### Swagger Path:
- Navigate to `/api/analytics/popular/24h`
- Navigate to `/api/analytics/{short_code}/hourly-7d`
- Navigate to `/api/analytics/{short_code}/device-analytics`
- Navigate to `/api/analytics/realtime/clicks-per-minute`

Click "Try it out" to test with interactive forms.

## Python Script for Testing

```python
import asyncio
import httpx
from datetime import datetime

async def test_analytics():
    async with httpx.AsyncClient() as client:
        # Top URLs
        print("=== Top URLs Last 24h ===")
        response = await client.get("http://localhost:8000/api/analytics/popular/24h?limit=5")
        data = response.json()
        for url in data["top_urls"]:
            print(f"{url['short_code']}: {url['click_count']} clicks")
            print(f"  Desktop: {url['device_breakdown']['desktop']}")
            print(f"  Mobile: {url['device_breakdown']['mobile']}")
            print(f"  Bot: {url['device_breakdown']['bot']}")
        
        # Hourly analytics
        print("\n=== Hourly Analytics (7d) ===")
        response = await client.get("http://localhost:8000/api/analytics/1/hourly-7d")
        data = response.json()
        print(f"Total clicks: {data['total_clicks']}")
        print(f"Hours with data: {len(data['hourly_data'])}")
        
        # Device analytics
        print("\n=== Device Analytics ===")
        response = await client.get("http://localhost:8000/api/analytics/1/device-analytics")
        data = response.json()
        for device, stats in data["device_distribution"].items():
            print(f"{device}: {stats['count']} ({stats['percentage']:.1f}%)")
        
        # Clicks per minute
        print("\n=== Clicks Per Minute ===")
        response = await client.get("http://localhost:8000/api/analytics/realtime/clicks-per-minute")
        data = response.json()
        print(f"Global CPM: {data['clicks_per_minute']}")
        print(f"Avg clicks/sec: {data['average_clicks_per_second']:.2f}")

if __name__ == "__main__":
    asyncio.run(test_analytics())
```

## Load Testing

Generate realistic traffic:

```bash
# Simple load test with Apache Bench
ab -n 100 -c 10 "http://localhost:8000/1"

# Or with hey
go install github.com/rakyll/hey@latest
hey -n 100 -c 10 "http://localhost:8000/1"

# Or with wrk (supports Lua scripting for User-Agent rotation)
wrk -t 4 -c 100 -d 30s \
  -s rotate-ua.lua \
  http://localhost:8000/1
```

## Check Logs

View structured redirect logs with device_type:

```bash
# Docker logs
docker logs urlshort-api 2>&1 | grep -E '"device_type"'

# Example log line:
# {"short_code":"1","cache_hit":true,"latency_ms":2.5,"user_agent":"Mozilla/5.0...","device_type":"mobile","ip_address":"127.0.0.1"}
```

## Redis Commands

Monitor Redis activity:

```bash
# Connect to Redis
redis-cli

# Watch all commands
> MONITOR

# Check sliding window counters
> KEYS clicks_per_minute:*
> ZRANGE clicks_per_minute:global 0 -1 WITHSCORES

# Check cache
> KEYS redirect:*
> GET redirect:1
```

## Database Queries

Check raw data in PostgreSQL:

```bash
# Connect to database
psql -U urlshort -d urlshort -h localhost

# Check device distribution
SELECT device_type, COUNT(*) FROM click_events GROUP BY device_type;

# Example output:
#  device_type | count
# ─────────────┼───────
#  desktop     |   542
#  mobile      |   328
#  bot         |    30

# Check hourly distribution
SELECT 
  DATE_TRUNC('hour', clicked_at) as hour,
  device_type,
  COUNT(*) as count
FROM click_events
WHERE short_url_id = 1
GROUP BY hour, device_type
ORDER BY hour DESC;

# Check top URLs
SELECT 
  su.short_code,
  SU.original_url,
  COUNT(ce.id) as recent_clicks
FROM short_urls su
LEFT JOIN click_events ce ON su.id = ce.short_url_id
  AND ce.clicked_at >= NOW() - INTERVAL '24 hours'
GROUP BY su.id, su.short_code, su.original_url
ORDER BY recent_clicks DESC
LIMIT 10;
```

## Continuous Monitoring

Run continuous load with monitoring:

```bash
#!/bin/bash

# Terminal 1: Continuous traffic
while true; do
  curl -s -H "User-Agent: Mozilla/5.0 (iPhone)" http://localhost:8000/1 > /dev/null
  sleep 2
done

# Terminal 2: Watch CPM
watch -n 1 'curl -s http://localhost:8000/api/analytics/realtime/clicks-per-minute | jq ".clicks_per_minute"'

# Terminal 3: Watch top URLs
watch -n 5 'curl -s http://localhost:8000/api/analytics/popular/24h?limit=3 | jq ".top_urls[0].click_count"'

# Terminal 4: Watch device distribution
watch -n 5 'curl -s http://localhost:8000/api/analytics/1/device-analytics | jq ".device_distribution"'
```

## Notes

- **Timing**: Some data may appear after 1-2 seconds due to Celery async processing
- **TTL**: Clicks-per-minute data expires after 60 seconds of inactivity
- **Aggregation**: Hourly data is calculated on-demand (not pre-aggregated)
- **Migration**: Run `alembic upgrade head` if using existing database

## Troubleshooting

**No data showing up?**
- Check Celery worker is running: `docker logs urlshort-celery-worker`
- Check database has device_type column: `docker exec urlshort-postgres psql -U urlshort -d urlshort -c "\\d click_events"`
- Wait 2-3 seconds for async processing

**Clicks-per-minute stuck at 0?**
- Check Redis is running: `redis-cli ping`
- Verify clicks are being processed in logs

**Device type always "desktop"?**
- Check User-Agent header is being sent: `curl -v http://localhost:8000/1`
- Check logs show received User-Agent value

For more details, see [ANALYTICS_ENHANCEMENTS.md](ANALYTICS_ENHANCEMENTS.md)
