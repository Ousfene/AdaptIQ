Set-Location "$PSScriptRoot\backend"
& "$PSScriptRoot\backend\.venv\Scripts\Activate.ps1"
# GROQ_API_KEY should be set in backend/.env or system environment
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
