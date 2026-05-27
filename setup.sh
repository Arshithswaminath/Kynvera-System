#!/usr/bin/env bash
# Mac setup — same role as setup.ps1 on Windows
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "========================================"
echo "Injaaz Application - Setup Script (macOS)"
echo "========================================"
echo ""

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. Install from https://www.python.org/downloads/ or use: brew install python"
  exit 1
fi
echo "Python: $(python3 --version)"

if [[ ! -d venv ]]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
fi

# shellcheck source=/dev/null
source "$ROOT/env.sh"

python -m pip install --upgrade pip --quiet
pip install -r requirements-prods.txt

if command -v npm >/dev/null 2>&1; then
  echo "Installing Node dependencies..."
  npm install
else
  echo "npm not found — skip npm install (optional for Capacitor/mobile)"
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example — review secrets before production."
fi

python scripts/init_db.py

echo ""
echo "Installing shell hook so 'python Injaaz.py' works in this folder (like Windows)..."
bash scripts/install-dev-shell.sh

echo ""
echo "========================================"
echo "Setup complete!"
echo "========================================"
echo ""
echo "Run the app (same as Windows):"
echo "  python Injaaz.py"
echo "Or:"
echo "  ./start.sh"
echo ""
echo "Open http://localhost:5002"
echo "Login: admin / Admin@123 — change password after first login."
