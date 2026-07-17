@echo off
cd /d %~dp0print_engine_front
if not exist node_modules (
  npm install
)
npm.cmd run dev -- --host 0.0.0.0
pause
