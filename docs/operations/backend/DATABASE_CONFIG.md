# Alternative Database Configuration Guide

This document explains how to use different database backends with AdaptIQ Backend, including the new alternative SQLite configuration and reference credentials setup.

## Quick Start

### Option 1: SQLite (Recommended for Testing)
Use the in-memory SQLite configuration that requires no server:

```bash
# Copy the test configuration
cp .env.test .env

# Run tests with SQLite backend
python test_alt_db.py

# Run backend with SQLite
python main.py
```

**Advantages:**
- No server setup required
- Instant creation and teardown
- Perfect for development and CI/CD
- No external dependencies

**Disadvantages:**
- Data is lost when process exits (in-memory mode)
- Single-threaded (not suitable for production)

### Option 2: SQLite (File-based, Persistent)
For testing with data persistence between runs:

Edit `.env.test`:
```env
DATABASE_URL=sqlite+aiosqlite:///./test_adaptiq.db
```

Then run:
```bash
python test_alt_db.py
```

### Option 3: PostgreSQL with Reference Credentials
To use a PostgreSQL database matching the reference folder's setup:

#### A. Using Docker (Easiest)
```bash
docker run \
  --name adaptiq_test_postgres \
  -e POSTGRES_USER=pfe \
  -e POSTGRES_PASSWORD=change_this_postgres_password \
  -e POSTGRES_DB=adaptive_learning \
  -p 5432:5432 \
  postgres:16-alpine
```

#### B. Update `.env` for reference credentials:
```env
DATABASE_URL=postgresql+asyncpg://pfe:change_this_postgres_password@localhost:5432/adaptive_learning
REDIS_URL=redis://localhost:6379
ENVIRONMENT=development
AUTO_CREATE_TABLES=true
```

Then test:
```bash
python main.py
# In another terminal:
curl http://localhost:8000/health
```

### Option 4: PostgreSQL on Different Port
Use reference credentials but with a different database:

```env
DATABASE_URL=postgresql+asyncpg://pfe:reference_password@localhost:5433/test_db
```

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://adaptiq:adaptiq@localhost:5432/adaptiq_db` | Database connection string |
| `ENVIRONMENT` | `development` | Deployment environment |
| `AUTO_CREATE_TABLES` | `false` | Auto-create DB schema on startup (disable in Alembic-first setup) |
| `REDIS_URL` | `redis://localhost:6379` | Redis cache URL |

## Testing & Validation

### Run All Backend Tests
```bash
pytest -q
```

### Run Alternative Database Test
```bash
python test_alt_db.py
```

### Check Backend Health with Current Config
```bash
python main.py &
sleep 3
curl http://localhost:8000/health | jq .
```

## Switching Between Configs

1. **For development with PostgreSQL:**
   ```bash
   cp .env.example .env
   # Edit .env with your PostgreSQL credentials
   ```

2. **For testing without server:**
   ```bash
   cp .env.test .env
   ```

3. **For CI/CD:**
   ```bash
   cp .env.test .env
   pytest -q
   ```

## Verification Checklist

- [ ] Database connection succeeds (check `/health` endpoint)
- [ ] Tables are created (verify with DB client or logs)
- [ ] Auth endpoints respond: `/api/auth/signup`, `/api/auth/login`
- [ ] Concept endpoints respond: `/api/custom/concepts/{topic}`
- [ ] Challenge endpoints respond: `/api/challenge/user/{user_id}/rank`

## Reference Credentials

The following credentials match the reference folder (`REFRENCE/pfe_auth`) setup:

```
POSTGRES_USER=pfe
POSTGRES_PASSWORD=change_this_postgres_password
POSTGRES_DB=adaptive_learning
```

These are suitable for:
- Local development
- Testing environments
- Demo deployments

**Note:** Change these passwords in production!

## Docker Compose Stack with Reference Creds

To bring up the full stack using reference credentials, see [docker-compose.yml](docker-compose.yml). The Compose file uses environment variables that can be overridden:

```bash
POSTGRES_USER=pfe \
POSTGRES_PASSWORD=change_this_postgres_password \
POSTGRES_DB=adaptive_learning \
docker-compose up -d
```
