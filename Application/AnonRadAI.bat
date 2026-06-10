@echo off
setlocal

cd /d "%~dp0"

if not exist ".anonrad_env" (
  py -3 -m venv .anonrad_env
  .anonrad_env\Scripts\python.exe -m pip install --upgrade pip
  .anonrad_env\Scripts\python.exe -m pip install -r requirements.txt
)

.anonrad_env\Scripts\python.exe src\app.py
