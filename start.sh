#!/usr/bin/env bash
# Same as Windows:  .\start.bat
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# shellcheck source=/dev/null
source "$ROOT/env.sh"

PORT="${PORT:-5001}"
if [[ -f .env ]]; then
  _p="$(grep -E '^PORT=' .env | tail -1 | cut -d= -f2- | tr -d '\r' || true)"
  [[ -n "$_p" ]] && PORT="$_p"
fi

echo "========================================"
echo "Starting Injaaz App - Development Server"
echo "========================================"
echo ""
echo "Initializing database..."
python scripts/init_db.py
echo ""
echo "Starting Flask server on http://localhost:${PORT}"
echo "Press Ctrl+C to stop"
echo ""
python Injaaz.py
