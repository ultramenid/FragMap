#!/bin/bash
# Mac: double-click this file.  Linux: run  bash start.command
# First run installs everything into a .venv folder (5-10 min, needs internet).
cd "$(dirname "$0")" || exit 1

ready() { .venv/bin/python -c "import pylandstats, rasterio, jupyterlab" 2>/dev/null; }

if ! ready; then
  echo "== First-time setup: installing required software (5-10 minutes) =="
  PY=""
  for c in python3.12 python3.13 python3; do
    if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info[:2] not in [(3, 12), (3, 13)])'; then
      PY="$c"; break
    fi
  done
  if [ -z "$PY" ]; then
    echo
    echo "ERROR: Python 3.12 was not found."
    echo "Install it from https://www.python.org/downloads/ (see README.md, Step 1), then try again."
    read -r -p "Press Enter to close..."; exit 1
  fi
  rm -rf .venv   # remove any broken or copied-over environment
  if ! { "$PY" -m venv .venv &&
         .venv/bin/python -m pip install --upgrade pip &&
         .venv/bin/python -m pip install -r requirements.txt; }; then
    echo
    echo "ERROR: installation failed. See 'Troubleshooting' in README.md."
    read -r -p "Press Enter to close..."; exit 1
  fi
fi

echo "== Opening the notebook in your web browser. Keep this window open while you work. =="
exec .venv/bin/python src/start.py
