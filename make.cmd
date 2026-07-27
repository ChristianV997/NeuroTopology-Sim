@echo off
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m tools.make_compat %*
) else (
  python -m tools.make_compat %*
)
