#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt
echo
echo "  Запуск Альфа-CBDC на http://127.0.0.1:8000  "
echo
exec uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
