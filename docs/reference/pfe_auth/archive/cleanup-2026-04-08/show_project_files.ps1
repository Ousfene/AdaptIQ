# show_project_files.ps1 - Display all source code files in pfe_auth project
Write-Host "=== PFE_AUTH PROJECT SOURCE FILES ===" -ForegroundColor Cyan
Write-Host ""

# Colors
$Red = "Red"
$Green = "Green" 
$Blue = "Blue"
$Yellow = "Yellow"

# Backend Python files (skip pycache, venv)
Write-Host "BACKEND PYTHON FILES:" -ForegroundColor $Blue
Get-ChildItem -Path "backend" -Recurse -Filter "*.py" -Exclude "__pycache__",".venv",".qodo" | ForEach-Object {
    Write-Host "=== $($_.FullName) ===" -ForegroundColor $Green
    Get-Content $_.FullName
    Write-Host "`n========== END $($_.Name) ==========" -ForegroundColor $Red
    Write-Host ""
}

# Frontend source files (skip node_modules)
Write-Host "FRONTEND SOURCE FILES:" -ForegroundColor $Blue
$frontendFiles = @("*.js", "*.jsx", "*.ts", "*.tsx", "*.css", "*.scss")
Get-ChildItem -Path "frontend\src" -Recurse -Include $frontendFiles | ForEach-Object {
    Write-Host "=== $($_.FullName) ===" -ForegroundColor $Green
    Get-Content $_.FullName
    Write-Host "`n========== END $($_.Name) ==========" -ForegroundColor $Red
    Write-Host ""
}

# Config files
Write-Host "CONFIG & PACKAGE FILES:" -ForegroundColor $Blue
$configFiles = @("package.json", "package-lock.json", "requirements.txt", "pyproject.toml", ".env*", "README.md")
foreach ($file in $configFiles) {
    if (Test-Path $file) {
        Write-Host "=== $file ===" -ForegroundColor $Green
        Get-Content $file
        Write-Host "`n========== END $file ==========" -ForegroundColor $Red
        Write-Host ""
    }
}

Write-Host "=== ALL SOURCE FILES DISPLAYED ===" -ForegroundColor $Green
