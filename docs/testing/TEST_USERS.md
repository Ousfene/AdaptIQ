# Test Users

Deterministic local-development accounts seeded by [backend/scripts/users/create_test_user.py](backend/scripts/users/create_test_user.py) or [backend/scripts/setup_test_users.py](backend/scripts/setup_test_users.py).

Run:

```bash
python scripts/users/create_test_user.py
```

This seeds users, challenge rankings, concept mastery rows, onboarding flags, and custom mastery rows. It also writes credential exports to `backend/generated/test_users.json` and `backend/generated/test_users.csv`.

To generate real gameplay history (no synthetic sample questions), run:

```bash
python scripts/generate_real_test_user_history.py
```

The real-history script is non-destructive:
- no table truncation
- no Redis flush/reset
- appends only normal room history through live APIs

## Accounts

| Email | Password | Purpose |
|-------|----------|---------|
| `admin.master@example.com` | `AdminPass123!` | Admin dashboard, all rooms, rank A |
| `challenge.e@example.com` | `TestPass123!` | Challenge rank E, onboarding new user |
| `challenge.d@example.com` | `TestPass123!` | Challenge rank D |
| `challenge.c@example.com` | `TestPass123!` | Challenge rank C, balanced progression |
| `challenge.b@example.com` | `TestPass123!` | Challenge rank B, specialist profile |
| `classic.novice@example.com` | `TestPass123!` | Classic room cold-start profile |
| `classic.expert@example.com` | `TestPass123!` | Classic room expert profile |
| `custom.fresh@example.com` | `TestPass123!` | Custom room fresh progress |
| `custom.complete@example.com` | `TestPass123!` | Custom room advanced progress |
| `pvp.grinder@example.com` | `TestPass123!` | PvP rating / matchmaking test |

## Local Links

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs
- Admin dashboard: http://localhost:9000

## Notes

- Password hashes are generated with bcrypt so they work with the live auth router.
- Re-running the profile seeder keeps the same emails and updates their seeded state.
- If you want a fresh baseline, drop the seeded rows before re-running or use a clean local database.