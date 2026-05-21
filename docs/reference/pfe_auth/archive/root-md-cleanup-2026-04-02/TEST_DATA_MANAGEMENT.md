# Test Data Management & Clean Database Guide

**Current Database State**: ✅ **ZERO QUESTIONS** (Clean Slate)

---

## 📋 Your Options

### Option 1: Seed Production Questions (Recommended)
```bash
cd backend
python seeds/seed.py
```

**Result**:
- 29 production questions (marked source='seed')
- 6 test users with historical data
- Ready to use Classic & Challenge rooms
- ~30 seconds

### Option 2: Delete ALL Questions & Start Fresh
```bash
# Delete test questions only
python backend/scripts/cleanup_test_data.py clean --force

# Or soft reset with clean_questions script
python -m seeds.cleanup_questions --test-only --delete
```

### Option 3: Add Test Questions Manually  
```bash
# In your test code
from seeds.test_fixture import TestFixture

async with TestFixture(db) as fixture:
    q = await fixture.create_test_question(
        text="What is the capital of France?",
        topic="geography",
        options=["Paris", "London", "Berlin", "Madrid"],
        correct=0
    )
    # Test code here
    # Auto-cleanup on context exit
```

---

## 🧹 Test Data Cleanup Commands

### Check Status
```bash
python backend/scripts/cleanup_test_data.py status
```

### List Test Questions
```bash
python backend/scripts/cleanup_test_data.py show          # Show 10
python backend/scripts/cleanup_test_data.py show --limit 20   # Show 20
```

### Delete Test Questions
```bash
# With confirmation
python backend/scripts/cleanup_test_data.py clean

# Force delete (no confirmation)
python backend/scripts/cleanup_test_data.py clean --force
```

---

## 📊 Production Question Management

### View Statistics
```bash
python -m seeds.cleanup_questions --stats
```

### View Garbage Questions
```bash
python -m seeds.cleanup_questions
```

### Delete Garbage Questions
```bash
python -m seeds.cleanup_questions --delete
```

### Filter by Source
```bash
# Show all test questions
python -m seeds.cleanup_questions --by-source test

# Show all seed questions
python -m seeds.cleanup_questions --by-source seed

# Show all LLM-generated questions
python -m seeds.cleanup_questions --by-source llm
```

---

## 🔄 Recommended Workflow

### 1. Fresh Start
```bash
# Clean any test data
python backend/scripts/cleanup_test_data.py clean --force

# Seed production questions
cd backend
python seeds/seed.py

# Verify
python scripts/cleanup_test_data.py status
```

### 2. After Testing
```bash
# See what test data was created
python backend/scripts/cleanup_test_data.py show

# Clean it up
python backend/scripts/cleanup_test_data.py clean

# Verify production data intact
python -m seeds.cleanup_questions --stats
```

---

## 🎯 Quick Start

```bash
# 1. Seed 29 questions
cd backend && python seeds/seed.py

# 2. Verify
python scripts/cleanup_test_data.py status

# 3. Run tests
python comprehensive_system_test.py

# 4. Clean test data
python scripts/cleanup_test_data.py clean --force

# 5. Check production data intact
python -m seeds.cleanup_questions --stats
```

---

## 📝 Database Source Values

| Source | Created By | Cleanup Method |
|--------|-----------|-----------------|
| `seed` | seed.py script | Manual (preserve) |
| `llm` | RAG/LLM pipeline | cleanup_questions.py |
| `test` | Tests/TestFixture | cleanup_test_data.py |
| `null` | Legacy data | cleanup_questions.py |

---

**Next**: Run `python backend/seeds/seed.py` to populate 29 production questions!
