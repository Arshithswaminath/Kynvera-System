# Source once per terminal:  source ./env.sh
# Then run like Windows:     python Injaaz.py
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
if [[ "${INJAAZ_ENV_LOADED:-}" == "$ROOT" ]]; then
  return 0 2>/dev/null || exit 0
fi
export INJAAZ_ENV_LOADED="$ROOT"

if [[ ! -x "$ROOT/venv/bin/python" ]]; then
  echo "Missing venv. Run: ./setup.sh" >&2
  return 1 2>/dev/null || exit 1
fi

# shellcheck source=/dev/null
source "$ROOT/venv/bin/activate"
export PATH="$ROOT/bin:$ROOT/venv/bin:${PATH}"
