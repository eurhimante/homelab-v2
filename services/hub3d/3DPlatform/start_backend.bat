@echo off
cd /d %~dp0print_engine
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
pause
