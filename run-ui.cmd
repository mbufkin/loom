@echo off
REM Loom Run Review - open the review UI in a native desktop window (no browser).
REM Usage: run-ui.cmd [--project <curriculum-id>] [--no-spawn] [--api-port N]
REM Example: run-ui.cmd --project disd-aas-icev-smoke
REM Windows has no "python3" command, so call "python" here; window.py itself
REM uses sys.executable for the API child, which keeps both platforms honest.
setlocal
python "%~dp0ui\window.py" %*
endlocal
