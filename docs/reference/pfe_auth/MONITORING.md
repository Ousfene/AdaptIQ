# 🔍 AdaptIQ Monitoring & Debugging Guide

## Overview

A complete monitoring and logging infrastructure has been added to help debug issues, track abuse patterns, and monitor API health in real-time.

**Last Updated**: April 1, 2026
**Commit**: 107611f - "feat: Add comprehensive monitoring and error logging for debugging"

---

## 🏗 Architecture

### Backend Monitoring Stack

```
┌─────────────────────────────────────────────────────┐
│ HTTP Request/Response                               │
├─────────────────────────────────────────────────────┤
│ ↓                                                   │
│ [Middleware] → Generate request_id                  │
│ ↓                                                   │
│ [Process Request]                                   │
│ ↓                                                   │
│ [Rate Limit Check] → Record hit if exceeded         │
│ ↓                                                   │
│ [Response] → Add X-Request-ID header                │
│ ↓                                                   │
│ [MonitoringService] → Record event                  │
└─────────────────────────────────────────────────────┘

MonitoringService In-Memory Store:
├── rate_limits: deque[max 200 events]
├── errors: deque[max 200 events]
└── request_stats:
    ├── total_requests
    ├── total_errors
    └── total_rate_limits
```

### Frontend Error Tracking Stack

```
┌──────────────────────────────────────────────────┐
│ API Call (generateQuestion, submitAnswer, etc.)  │
├──────────────────────────────────────────────────┤
│ ↓                                                │
│ [fetch() response]                               │
│ ↓                                                │
│ [Response not ok] → handleApiError()             │
│ ↓                                                │
│ [Extract request_id from X-Request-ID header]   │
│ ↓                                                │
│ [Log to ErrorTracker] → Store in memory          │
│ ↓                                                │
│ [Throw error to component] → Show to user        │
└──────────────────────────────────────────────────┘

ErrorTracker In-Memory Store:
├── logs: deque[max 100 events]
└── Each event:
    ├── timestamp
    ├── endpoint
    ├── status_code
    ├── errorType (categorized)
    ├── requestId (links to backend)
    └── message
```

---

## 📊 Monitoring Endpoints

### 1. Overall API Statistics

**Endpoint**: `GET /api/system/monitoring/stats`

**Response**:
```json
{
  "total_requests": 1247,
  "total_errors": 12,
  "total_rate_limits": 3,
  "error_rate": 0.0096,
  "rate_limit_count": 3,
  "recent_errors": [
    {
      "timestamp": "2026-04-01T14:32:10.450Z",
      "path": "/api/rooms/classic/questions",
      "method": "POST",
      "status_code": 503,
      "error_type": "ServerError",
      "error_message": "LLM service unavailable",
      "duration_ms": 45.2,
      "endpoint": "POST /api/rooms/classic/questions"
    }
  ],
  "recent_rate_limits": [
    {
      "timestamp": "2026-04-01T14:31:05.123Z",
      "client_ip": "192.168.1.100",
      "path": "/api/rooms/classic/questions",
      "method": "POST",
      "endpoint": "POST /api/rooms/classic/questions"
    }
  ]
}
```

**Use Cases**:
- Monitor overall API health
- Track error rate trends
- Identify if rate limiting is working
- Alert on high error rates (> 1%)

---

### 2. Recent Rate Limit Hits

**Endpoint**: `GET /api/system/monitoring/rate-limits?limit=20`

**Response**:
```json
[
  {
    "timestamp": "2026-04-01T14:31:05.123Z",
    "client_ip": "192.168.1.105",
    "path": "/api/rooms/classic/questions",
    "method": "POST",
    "endpoint": "POST /api/rooms/classic/questions"
  }
]
```

**Use Cases**:
- Identify which clients are hitting rate limits
- Detect abuse patterns (same IP repeatedly)
- Monitor endpoint popularity
- Validate rate limit effectiveness

**Example Analysis**:
```bash
# See which endpoints are rate limited most
curl http://localhost:8000/api/system/monitoring/rate-limits?limit=50 \
  | jq '[.[].endpoint] | group_by(.) | map({endpoint: .[0], count: length})'

# Result:
# [
#   { "endpoint": "POST /api/rooms/classic/questions", "count": 12 },
#   { "endpoint": "POST /api/rooms/classic/hints", "count": 5 }
# ]
```

---

### 3. Recent API Errors

**Endpoint**: `GET /api/system/monitoring/errors?limit=20`

**Response**:
```json
[
  {
    "timestamp": "2026-04-01T14:30:45.235Z",
    "path": "/api/rooms/classic/questions",
    "method": "POST",
    "status_code": 500,
    "error_type": "ServerError",
    "error_message": "Failed to parse options for question",
    "duration_ms": 1250.4,
    "endpoint": "POST /api/rooms/classic/questions"
  },
  {
    "timestamp": "2026-04-01T14:30:42.100Z",
    "path": "/api/auth/login",
    "method": "POST",
    "status_code": 401,
    "error_type": "AuthenticationError",
    "error_message": "Invalid credentials",
    "duration_ms": 45.2,
    "endpoint": "POST /api/auth/login"
  }
]
```

**Use Cases**:
- Debug endpoint failures
- Identify performance issues (slow endpoints)
- Categorize error types for root cause analysis
- Monitor error trends over time

**Example Analysis**:
```bash
# Find slowest endpoints
curl http://localhost:8000/api/system/monitoring/errors?limit=100 \
  | jq 'sort_by(.duration_ms) | reverse[:5]'

# Find most common error types
curl http://localhost:8000/api/system/monitoring/errors?limit=100 \
  | jq '[.[].error_type] | group_by(.) | map({type: .[0], count: length})'
```

---

### 4. Request Tracing

Every response includes a unique `X-Request-ID` header:

```bash
curl -i http://localhost:8000/api/system/health

# Response headers:
# HTTP/1.1 200 OK
# x-request-id: 550e8400-e29b-41d4-a716-446655440000
# ...
```

**Use Case**: Correlate frontend errors with backend logs
- When frontend errorTracker logs error, it captures X-Request-ID
- Use that ID to search backend logs for exact same request
- Trace full request lifecycle from client to server

---

## 🖥 Frontend Error Tracking

### Access Error Tracker in Browser Console

```javascript
// Get current error statistics
window.errorTracker.getStats()
// Output:
// {
//   totalErrors: 5,
//   recentErrors: [...],
//   errorsByType: {
//     "RateLimitError": 2,
//     "ServerError": 2,
//     "ValidationError": 1
//   }
// }

// View recent errors (last 10)
window.errorTracker.getRecentErrors(10)

// Export all logs as JSON for debugging
console.log(window.errorTracker.exportAsJson())

// Clear all stored errors
window.errorTracker.clear()
```

### Error Log Entry Structure

```json
{
  "timestamp": "2026-04-01T14:30:45.123Z",
  "message": "Invalid question format: missing/invalid id",
  "endpoint": "/api/rooms/classic/questions",
  "status": 200,
  "errorType": "ValueError",
  "duration_ms": 234.5,
  "requestId": "550e8400-e29b-41d4-a716-446655440000",
  "context": {}
}
```

---

## 🔧 Common Debugging Scenarios

### Scenario 1: User Reports "Too Many Requests" Error

**Steps**:
1. Check rate limit activity:
   ```bash
   curl http://localhost:8000/api/system/monitoring/rate-limits?limit=50
   ```
2. Find all rate limits for problematic IP:
   ```bash
   # Find IP hitting limits
   curl http://localhost:8000/api/system/monitoring/rate-limits?limit=50 \
     | jq '.[] | select(.client_ip == "192.168.1.100")'
   ```
3. Check if they're using our endpoints or external service:
   - Look at `endpoint` field to see which endpoint
   - Check `method` to see if it's POST (submission) or GET (read)
   - If rapid sequential calls, likely frontend bug
   - If from one IP repeatedly, likely abuse or bot

**Example Output**:
```json
[
  {"timestamp": "...", "client_ip": "192.168.1.100", "endpoint": "POST /api/rooms/classic/questions"},
  {"timestamp": "...", "client_ip": "192.168.1.100", "endpoint": "POST /api/rooms/classic/questions"},
  {"timestamp": "...", "client_ip": "192.168.1.100", "endpoint": "POST /api/rooms/classic/questions"}
]
```
→ Same IP, same endpoint, rapid fire = frontend bug (fix rate limit in rate limiter decorator)

---

### Scenario 2: API Returns 500 Error Intermittently

**Steps**:
1. Check recent errors:
   ```bash
   curl http://localhost:8000/api/system/monitoring/errors?limit=20
   ```
2. Filter for 500 errors (ServerError type):
   ```bash
   curl http://localhost:8000/api/system/monitoring/errors?limit=100 \
     | jq '.[] | select(.status_code == 500)'
   ```
3. Check error messages:
   ```bash
   curl http://localhost:8000/api/system/monitoring/errors?limit=100 \
     | jq '[.[].error_message] | unique'
   ```
4. Check if it's a specific endpoint or all endpoints:
   ```bash
   curl http://localhost:8000/api/system/monitoring/errors?limit=100 \
     | jq '.[] | select(.status_code == 500) | .endpoint' | sort | uniq -c
   ```

**Example Investigation**:
- If all `/questions` errors: Issue with question generation
- If random endpoints intermittent: Database or Redis connection issue
- If specific error message repeats: Code bug that needs fixing

---

### Scenario 3: Slow Endpoint Performance

**Steps**:
1. Get slowest endpoints:
   ```bash
   curl http://localhost:8000/api/system/monitoring/errors?limit=100 \
     | jq 'sort_by(.duration_ms) | reverse[:10]'
   ```
2. Check context:
   - Is it a specific endpoint consistently slow?
   - Is it fast sometimes, slow other times (resource contention)?
   - Is it getting slower over time (memory leak)?

**Example Output** (slow endpoints):
```json
[
  {
    "endpoint": "POST /api/rooms/classic/questions",
    "duration_ms": 5234.2,
    "error_type": "Timeout"
  }
]
```
→ MCQ generation timeout - likely LLM API slow or overloaded

---

### Scenario 4: Frontend Error Pattern Analysis

**In Browser Console**:
```javascript
// See what types of errors user is hitting
const stats = window.errorTracker.getStats()
console.table(stats.errorsByType)

// See if errors are from same endpoint
const recent = window.errorTracker.getRecentErrors(20)
recent.forEach(e => console.log(`${e.endpoint}: ${e.errorType}`))

// Export for sharing with team
const json = window.errorTracker.exportAsJson()
// Save to file and share for debugging
```

---

## 📈 Monitoring Dashboard (Future)

Once this infrastructure is in place, you could build a dashboard to:
- Real-time error rate graph
- Rate limit hits per endpoint
- Response time histogram
- Error type pie chart
- Slowest endpoint ranking
- Client IP abuse detection

All data is available via the `/api/system/monitoring/*` endpoints.

---

## 🚨 Alert Thresholds (Recommended)

Set up alerts for:
- **Error Rate > 1%**: Something is broken
- **Any 500 error**: Immediate investigation
- **Same IP > 5 rate limits/min**: Likely abuse or bug
- **Any endpoint > 5s**: Performance issue
- **LLM errors**:  API quota exceeded or service down

---

## 📝 Structured Logging

All logs use structlog for easy parsing:

**Backend Request Log**:
```
request_started path=/api/rooms/classic/questions method=POST
request_completed status=200 duration_ms=1234.5 path=/api/rooms/classic/questions
```

**Backend Error Log**:
```
request_failed error_type=JSONDecodeError error="Failed to parse options"
rate_limit_exceeded client_ip=192.168.1.100 path=/api/rooms/classic/questions
```

In production, these logs can be shipped to ELK, Splunk, CloudWatch, etc. for centralized monitoring.

---

## 🔐 Security Note

The monitoring endpoints are **read-only** and **public** (not protected by auth).
Consider:
- Adding rate limiting to monitoring endpoints themselves
- Wrapping in admin auth in production
- Not exposing error details in production (truncate messages)

---

**Next Step**: Set up log aggregation (ELK Stack, Splunk, or CloudWatch) to persist monitoring data beyond the in-memory queue.
