@echo off
cd /d %~dp0\..
if not exist .venv (
  python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install --upgrade pip >nul
pip install -r requirements.txt
echo.
echo   Запуск Альфа-CBDC на http://127.0.0.1:8000
echo.
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
