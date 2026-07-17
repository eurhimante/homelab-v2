@echo off
cd /d C:\3DPlatform\print_engine
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 8000
pause
