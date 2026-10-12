@echo off
cd /d "%~dp0"
if exist ".venv-test\Scripts\python.exe" (
  ".venv-test\Scripts\python.exe" RFLink_Testprogramm.py
) else (
  python RFLink_Testprogramm.py
)
if errorlevel 1 pause
