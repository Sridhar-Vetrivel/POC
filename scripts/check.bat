@echo off
REM Thin wrapper around the cross-platform gate runner (scripts\check.py).
REM Use this on native Windows (cmd). All gate logic lives in scripts\check.py.
REM Usage: scripts\check.bat [--fast] [--fix] [--only a,b] [--skip a,b] [--bundle] [--list]
REM Requirements (installed via `pip install -e ".[dev]"`):
REM   ruff, bandit, pip-audit, pytest, reportlab
python "%~dp0check.py" %*
exit /b %ERRORLEVEL%
