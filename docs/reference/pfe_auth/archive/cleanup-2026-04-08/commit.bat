@echo off
REM Commit script for concept-aware implementation

cd /d C:\Users\mns\Desktop\pfe_auth

echo.
echo ========== STAGING CHANGES ==========
git add -A
echo Staged all changes.

echo.
echo ========== COMMITTING ==========
git commit -m "feat: Implement concept-aware question caching with per-user ELO

- Add ConceptCacheService for smart concept selection (80/20 strategy)
- Add QuestionCacheService for Redis performance caching
- Fix dead code in auth_service.py (lines 90-98)
- Fix datetime deprecation in concept_irt.py
- Fix frontend port mapping in docker-compose.yml (5173:5173)
- Add comprehensive test suite (test_concept_awareness.py)
- Add complete system documentation (CONCEPT_AWARE_SYSTEM.md)
- Implement per-concept IRT theta tracking
- Implement per-user difficulty computation
- Implement auto-discovery logic for new concepts
- New concepts start at difficulty 3, then adapt based on performance
- Same question cached, served to multiple users with different difficulties

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"

echo.
echo ========== COMMIT LOG ==========
git log --oneline -5

echo.
echo ========== STATUS ==========
git status

pause
