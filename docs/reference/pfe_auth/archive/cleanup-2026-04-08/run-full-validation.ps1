$ErrorActionPreference = 'Stop'

Write-Host "[1/7] Docker service status" -ForegroundColor Cyan
docker ps --filter "name=pfe" --format "table {{.Names}}`t{{.Status}}`t{{.Ports}}"

Write-Host "[2/7] Alembic current" -ForegroundColor Cyan
Push-Location "backend"
& "$PSScriptRoot\backend\.venv\Scripts\python.exe" -m alembic current

Write-Host "[3/7] Backend pytest" -ForegroundColor Cyan
& "$PSScriptRoot\backend\.venv\Scripts\python.exe" -m pytest tests
Pop-Location

Write-Host "[4/7] Frontend vitest" -ForegroundColor Cyan
Push-Location "frontend"
npm run test

Write-Host "[5/7] Frontend Playwright E2E" -ForegroundColor Cyan
npm run test:e2e

Write-Host "[6/7] API smoke auth->quiz" -ForegroundColor Cyan
node scripts\smoke-auth-quiz.mjs
Pop-Location

Write-Host "[7/7] Complete" -ForegroundColor Green
