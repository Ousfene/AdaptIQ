# AdaptIQ Local Admin Dashboard

A **simple, local-only HTML/CSS admin dashboard** for monitoring AdaptIQ system data. No fancy UI, just raw information for developers.

## What It Shows

- **System Overview**: Total users, questions, sessions, concepts
- **Top Concepts**: Most-engaged concepts ranked by tracked users
- **Recent Users**: Last 20 registered users with stats
- **Question Bank**: Cached questions with usage stats
- **System Health**: API, database connection status
- **Raw Data Inspector**: JSON view for deep inspection

## Setup & Usage

### Option 1: Direct HTML (Easiest)

1. Make sure backend is running:
   ```bash
   cd backend
   python main.py
   ```

2. Open the dashboard in your browser:
   ```
   file:///c:/Users/mns/Desktop/mw/mhd/admin_dashboard.html
   ```

3. The dashboard will auto-connect to `http://localhost:8000` and fetch data

### Option 2: Python Server (Recommended)

1. Start the dedicated admin server:
   ```bash
   python admin_server.py
   ```

2. Browser will auto-open to: `http://localhost:9000`

3. Dashboard auto-refreshes every 30 seconds

## Features

### 📊 System Overview Cards
- **Users**: Total, active, admins
- **Questions**: Total in bank, from LLM, cached
- **Sessions**: By type (Classic, Challenge, Custom, PvP)
- **Concepts**: Total and mastery tracking rows
- **PvP**: Total matches and rated players
- **Latest Activity**: Last user/question timestamps

### 🎯 Top 10 Concepts Table
Shows which concepts are most engaged:
- Concept name
- Topic (History/Geography)
- Number of users tracking it
- Average theta (ability estimate)

### 👥 Recent Users Table
Last 20 registered users:
- Email, username
- Points, level
- Admin status, active status
- Creation and last login timestamps

### 📚 Question Bank Status
First 15 questions showing:
- Question text (truncated)
- Topic
- IRT difficulty
- Times seen (reuse count)
- Usage count
- Source (llm/seed/huggingface)
- Last served timestamp

### 🏥 System Health
Quick status checks:
- Database connection
- Backend API responsiveness
- Concept tracking enable status

### 🔍 Raw Data Inspector
Click "Fetch Full Overview JSON" to see raw API response as formatted JSON

## API Endpoints Used

The dashboard queries these backend endpoints:

```
GET  /api/admin/overview           → System-wide statistics
GET  /api/admin/top-concepts?limit=10  → Most-tracked concepts
GET  /api/admin/users?page=1&per_page=20  → Paginated user list
GET  /api/admin/questions?page=1&per_page=15  → Paginated question list
```

All return JSON, no authentication required (local-only assumption).

## Configuration

### Change Backend API URL
At the top of the page, modify the input field:
```
http://localhost:8000  →  http://your-backend-url:port
```

### Auto-Refresh Interval
Edit the JavaScript (line: `setInterval(fetchData, 30000)`):
- `30000` = 30 seconds
- Change to `10000` for 10 seconds, etc.

## Dark Mode Theme

Pre-configured dark theme optimized for development monitoring:
- Background: `#1e1e1e` (dark gray)
- Primary accent: `#4ecdc4` (teal)
- Secondary accent: `#95e1d3` (light teal)
- Status colors: Green (ok), Orange (warn), Red (error)

## Local-Only Design

✅ **No authentication** - assumes local access only  
✅ **No user signup/login** - just load the HTML  
✅ **No database writes** - read-only monitoring  
✅ **No external dependencies** - vanilla HTML/CSS/JS  
✅ **No build process** - works immediately  

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Error: HTTP 503" | Backend not running, start `python main.py` |
| "Can't connect to localhost:8000" | Backend not on expected port, update API URL |
| "No data showing" | Check browser console (F12) for CORS/API errors |
| Table rows are empty | Database might be empty, seed it first |

## What's NOT Included

- User authentication (local development only)
- Fancy charts/visualizations
- Data editing/deletion UI
- Real-time WebSocket updates
- Mobile responsive design

## Quick Commands

### Start everything:
```bash
# Terminal 1: Backend
cd backend
python main.py

# Terminal 2: Admin Dashboard
python admin_server.py

# Auto-opens browser to http://localhost:9000
```

### Direct access without server:
```bash
# Just open this in browser:
file:///c:/Users/mns/Desktop/mw/mhd/admin_dashboard.html
```

## Files

- `admin_dashboard.html` - The dashboard UI (single HTML file)
- `admin_server.py` - Optional simple Python server

## Future Enhancements (Optional)

- Add real-time WebSocket connection for live updates
- Export data to CSV
- Show Redis/OTP status
- Add query builder for custom data inspection
- Performance graphs
- Error log viewer

---

**Created for local development monitoring. Keep it simple!** 🔧
