#!/bin/bash
# show_project_files.sh - Display all source code files in pfe_auth project

echo "=== PFE_AUTH PROJECT SOURCE FILES ==="
echo

# Colors for better readability
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Python backend files (skip pycache, venv)
echo -e "${BLUE}BACKEND PYTHON FILES:${NC}"
find backend -name "*.py" -not -path "*/__pycache__/*" -not -path "*/.venv/*" -not -path "*/.qodo/*" | while read file; do
    echo -e "${GREEN}=== $file ===${NC}"
    cat "$file"
    echo -e "\n${RED}========== END $file ==========${NC}\n"
done

echo -e "${BLUE}FRONTEND SOURCE FILES:${NC}"
# Frontend JS/TS/JSX/TSX/CSS files (skip node_modules)
find frontend/src -name "*.js" -o -name "*.jsx" -o -name "*.ts" -o -name "*.tsx" -o -name "*.css" -o -name "*.scss" | while read file; do
    echo -e "${GREEN}=== $file ===${NC}"
    cat "$file"
    echo -e "\n${RED}========== END $file ==========${NC}\n"
done

# Root level config files
echo -e "${BLUE}CONFIG & PACKAGE FILES:${NC}"
for file in package.json package-lock.json requirements.txt pyproject.toml .env* README.md; do
    if [[ -f "$file" ]]; then
        echo -e "${GREEN}=== $file ===${NC}"
        cat "$file"
        echo -e "\n${RED}========== END $file ==========${NC}\n"
    fi
done

echo -e "${GREEN}=== ALL SOURCE FILES DISPLAYED ===${NC}"
