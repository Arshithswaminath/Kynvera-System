#!/usr/bin/env bash
# Prepends Injaaz venv to PATH when you cd into the project (Windows-like: python Injaaz.py)
set -euo pipefail

MARKER="# Injaaz-App:"
ZSHRC="${HOME}/.zshrc"

touch "$ZSHRC"
if grep -qF "$MARKER" "$ZSHRC" 2>/dev/null; then
  echo "Dev shell hook already installed in $ZSHRC"
  exit 0
fi

cat >> "$ZSHRC" <<'EOF'

# Injaaz-App: put project venv on PATH when inside the repo (no recursive source)
_injaaz_auto_venv() {
  if [[ "${INJAAZ_ENV_LOADED:-}" == "$PWD" ]]; then
    return 0
  fi
  if [[ -f "$PWD/Injaaz.py" && -x "$PWD/venv/bin/python" ]]; then
    export INJAAZ_ENV_LOADED="$PWD"
    export VIRTUAL_ENV="$PWD/venv"
    export PATH="$PWD/venv/bin:$PWD/bin:${PATH}"
  else
    unset INJAAZ_ENV_LOADED VIRTUAL_ENV
  fi
}
typeset -ga chpwd_functions 2>/dev/null || true
if [[ -n "${chpwd_functions:-}" ]] && [[ "${chpwd_functions[(ie)_injaaz_auto_venv]:-0}" -eq 0 ]]; then
  chpwd_functions+=(_injaaz_auto_venv)
elif [[ -z "${chpwd_functions:-}" ]]; then
  chpwd_functions=(_injaaz_auto_venv)
fi
_injaaz_auto_venv
EOF

echo "Installed auto-venv hook in $ZSHRC"
echo "Open a new terminal, cd to the project, then run: python Injaaz.py"
