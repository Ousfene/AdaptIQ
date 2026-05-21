#!/usr/bin/env python
import sys
sys.path.insert(0, r'c:\Users\mns\Desktop\pfe_auth\backend')

try:
    from routers.challenge import router
    print('Challenge router: OK')
    
    from services.challenge_service import *
    print('Challenge service: OK')
    
    from services.challenge_llm import *
    print('Challenge LLM: OK')
    
    from schemas import *
    print('Schemas: OK')
    
    from database.models import ChallengeSession, ChallengeAnswer
    print('Models: OK')
    
    print('\nAll imports successful!')
except Exception as e:
    print(f'Import failed: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
