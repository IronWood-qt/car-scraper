#!/usr/bin/env bash
# Run this project without Poetry - plain python3 + pip + a local venv.
# Poetry is still used for dev tooling (pytest/ruff/mypy, see README's Local
# Development section) but was never actually required just to *run* things.
#
# Usage:
#   ./run.sh          # start the dashboard, http://localhost:8501 (default)
#   ./run.sh scrape   # one-off manual scrape-all run (for debugging - the
#                      # docker-compose 'scraper' container / your own cron
#                      # is what normally runs this, on a schedule)
#
# Everything else (which cars to track, max pages, Pushover, ...) is a
# Settings/Manage Targets page in the dashboard now, not a flag here.
#
# First run sets up (or reuses) .venv and installs what the chosen mode
# needs; later runs are near-instant (pip no-ops when nothing changed).

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

VENV=.venv

# Needs Python 3.10+ (pyproject.toml) - a plain `python3` on PATH is often
# an older system Python (macOS ships 3.8+ under /usr/bin), so search a few
# likely names/locations instead of assuming. First hit wins.
find_python() {
  for candidate in python3.13 python3.12 python3.11 python3.10 \
    /opt/homebrew/opt/python@3.11/bin/python3.11 \
    /opt/homebrew/opt/python@3.12/bin/python3.12 \
    python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        echo "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

if [ ! -d "$VENV" ]; then
  PYBIN="$(find_python)" || {
    echo "No Python 3.10+ found. Install one (e.g. 'brew install python@3.11')" >&2
    echo "then re-run this script." >&2
    exit 1
  }
  echo "Setting up $VENV with $PYBIN (one-time)..."
  "$PYBIN" -m venv "$VENV"
fi

if [ "${1:-}" = "scrape" ]; then
  shift
  "$VENV/bin/pip" install -q .
  exec "$VENV/bin/python" main.py "$@"
fi

"$VENV/bin/pip" install -q -r dashboard/requirements.txt
# showSidebarNavigation=false: dashboard/_nav.py renders its own Dashboard
# (top) / Settings (bottom) links instead of Streamlit's default top-only
# page list - see that module's docstring.
exec "$VENV/bin/streamlit" run "dashboard/🚗_Dashboard.py" \
  --client.showSidebarNavigation=false
