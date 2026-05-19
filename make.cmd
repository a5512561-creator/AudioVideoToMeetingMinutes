@echo off
REM Windows-native wrapper for the same workflows as the Makefile.
REM Use this if you don't have GNU make installed.
REM
REM Note: Uses POSITIONAL args (Windows CMD's KEY=VALUE parsing is fragile
REM with quoted paths containing spaces / non-ASCII). The Linux Makefile
REM keeps the GNU make standard NAME=value style.
REM
REM Usage:
REM   make help
REM   make install
REM   make install-dev
REM   make test
REM   make run    "path\to\transcript.txt" [NAME]
REM   make rerender NAME
REM   make open     NAME
REM   make clean | clean-out | clean-logs | clean-all

setlocal enabledelayedexpansion

set PY=.venv\Scripts\python.exe
set PIP=.venv\Scripts\pip.exe
set PYTEST=.venv\Scripts\pytest.exe

set TARGET=%~1

if "%TARGET%"=="" goto help
if /i "%TARGET%"=="help" goto help
if /i "%TARGET%"=="install" goto install
if /i "%TARGET%"=="install-dev" goto install-dev
if /i "%TARGET%"=="test" goto test
if /i "%TARGET%"=="test-verbose" goto test-verbose
if /i "%TARGET%"=="run" goto run
if /i "%TARGET%"=="rerender" goto rerender
if /i "%TARGET%"=="open" goto open
if /i "%TARGET%"=="clean" goto clean
if /i "%TARGET%"=="clean-out" goto clean-out
if /i "%TARGET%"=="clean-logs" goto clean-logs
if /i "%TARGET%"=="clean-all" goto clean-all

echo ERROR: unknown target "%TARGET%"
goto help

:help
echo.
echo Meeting Minutes pipeline -- make.cmd targets (positional args)
echo.
echo Setup:
echo   install         Create .venv and install runtime deps
echo   install-dev     Install runtime + test deps
echo.
echo Run:
echo   test                              Run all pytest
echo   test-verbose                      pytest with -v
echo   run "FILE" [NAME]
echo                                     Full pipeline. Quote FILE if it has spaces.
echo                                     NAME defaults to FILE basename.
echo                                     Examples:
echo                                       make run "src\transcript.txt"
echo                                       make run "src\transcript.txt" q2_planning
echo   rerender NAME                     Re-render outputs (no LLM)
echo   open     NAME                     Open out\^<NAME^>\minutes.html in browser
echo.
echo Clean (DESTRUCTIVE):
echo   clean        Remove pycache + .pytest_cache
echo   clean-out    Remove out\
echo   clean-logs   Remove log\
echo   clean-all    All three above
echo.
exit /b 0

:install
python -m venv .venv
%PIP% install -U pip
%PIP% install -r requirements.txt
exit /b %ERRORLEVEL%

:install-dev
python -m venv .venv
%PIP% install -U pip
%PIP% install -r requirements-dev.txt
exit /b %ERRORLEVEL%

:test
%PYTEST% --tb=short
exit /b %ERRORLEVEL%

:test-verbose
%PYTEST% -v
exit /b %ERRORLEVEL%

:run
REM Delegate parsing to a Python helper — CMD's argv handling with quoted
REM paths containing spaces and CJK breaks every batch-side parser I tried.
REM helper is in scripts\_make_run.py and just builds + execs the python
REM command with the right --name flags.
%PY% scripts\_make_run.py %*
exit /b %ERRORLEVEL%

:rerender
set "NAME=%~2"
if "%NAME%"=="" (
    echo ERROR: NAME is required.
    echo Usage: make rerender ^<output_folder_name^>
    exit /b 1
)
%PY% -m script.main "(rerender)" --name %NAME% --rerender
exit /b %ERRORLEVEL%

:open
set "NAME=%~2"
if "%NAME%"=="" (
    echo ERROR: NAME is required.
    echo Usage: make open ^<output_folder_name^>
    exit /b 1
)
if not exist "out\%NAME%\minutes.html" (
    echo ERROR: out\%NAME%\minutes.html not found. Run the pipeline first.
    exit /b 1
)
start "" "out\%NAME%\minutes.html"
exit /b %ERRORLEVEL%

:clean
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
if exist .pytest_cache rd /s /q .pytest_cache
if exist .mypy_cache rd /s /q .mypy_cache
if exist .ruff_cache rd /s /q .ruff_cache
echo Removed __pycache__ + .pytest_cache + .mypy_cache + .ruff_cache
exit /b 0

:clean-out
if exist out rd /s /q out
echo Removed out\  (all meeting results gone)
exit /b 0

:clean-logs
if exist log rd /s /q log
echo Removed log\
exit /b 0

:clean-all
call "%~f0" clean
call "%~f0" clean-out
call "%~f0" clean-logs
exit /b 0
