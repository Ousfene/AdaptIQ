import re

fixes_status = {}

# Fix 1.2 - UUID validation
with open('backend/routers/challenge.py', 'r') as f:
    content = f.read()
    has_try_uuid = 'try:' in content[content.find('for qid in match_state'):content.find('for qid in match_state')+500] if 'for qid in match_state' in content else False
    fixes_status['Fix 1.2 (UUID)'] = 'PRESENT' if 'uuid.UUID(qid)' in content and 'except' in content[content.find('uuid.UUID'):content.find('uuid.UUID')+500] else 'MISSING'

# Fix 1.4 - Question options validation
with open('backend/routers/classic_room.py', 'r') as f:
    content = f.read()
    fixes_status['Fix 1.4 (Options)'] = 'PRESENT' if 'correct_answer not in options' in content else 'MISSING'

# Fix 1.7 - Dashboard field (we just fixed this)
with open('frontend/src/pages/Dashboard.tsx', 'r') as f:
    content = f.read()
    fixes_status['Fix 1.7 (Dashboard)'] = 'FIXED' if 'payload.days' in content else 'NEEDS FIX'

# Fix 1.8 - Array bounds check
with open('frontend/src/pages/ChallengeRoom.tsx', 'r') as f:
    content = f.read()
    fixes_status['Fix 1.8 (Bounds)'] = 'PRESENT' if 'currentIndex >= session.questions.length' in content else 'MISSING'

# Fix 2.4 - Hash truncation
with open('backend/routers/classic_room.py', 'r') as f:
    content = f.read()
    has_full_hash = '.hexdigest()' in content and '.hexdigest()[:16]' not in content
    fixes_status['Fix 2.4 (Hash)'] = 'FULL HASH' if has_full_hash else 'TRUNCATED'

# Fix 2.1 - TopicType normalization
with open('frontend/src/services/apiService.ts', 'r') as f:
    content = f.read()
    topic_calls = content.count('normalizeTopicForApi(topic)')
    fixes_status['Fix 2.1 (Topic)'] = f'{topic_calls} normalizations found' if topic_calls > 0 else 'NEEDS AUDIT'

print("STATUS OF REMAINING 6 FIXES:")
print("=" * 50)
for fix, status in fixes_status.items():
    print(f"{fix}: {status}")
