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
REM   make run    "path\to\meeting.mp4" [NAME] [DIARIZE: 0 or 1]
REM   make rerender NAME
REM   make samples  NAME
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
if /i "%TARGET%"=="samples" goto samples
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
echo   test                              Run all pytest (~1 min, 96 tests)
echo   test-verbose                      pytest with -v
echo   run "FILE" [NAME] [DIARIZE]
echo                                     Full pipeline. Quote FILE if it has spaces.
echo                                     NAME defaults to FILE basename.
echo                                     DIARIZE: 1 -^> --diarize ; 0 -^> --no-diarize
echo                                     Examples:
echo                                       make run "src\meeting.mp4"
echo                                       make run "src\x.ogg" q2_planning
echo                                       make run "src\x.mp4" q2_planning 1
echo   rerender NAME                     Re-render outputs (^~13s, no LLM)
echo   samples  NAME                     Re-generate per-speaker mp3 samples
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
set "FILE=%~2"
set "NAME=%~3"
set "DIARIZE=%~4"
if "%FILE%"=="" (
    echo ERROR: FILE is required.
    echo Usage: make run "path\to\meeting.mp4" [NAME] [DIARIZE: 0 or 1]
    exit /b 1
)
set NAME_FLAG=
if not "%NAME%"=="" set NAME_FLAG=--name %NAME%
set DIARIZE_FLAG=
if "%DIARIZE%"=="1" set DIARIZE_FLAG=--diarize
if "%DIARIZE%"=="0" set DIARIZE_FLAG=--no-diarize
%PY% -m script.main "%FILE%" %NAME_FLAG% %DIARIZE_FLAG%
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

:samples
set "NAME=%~2"
if "%NAME%"=="" (
    echo ERROR: NAME is required.
    echo Usage: make samples ^<output_folder_name^>
    exit /b 1
)
if not exist "out\%NAME%\intermediate\diarization.json" (
    echo ERROR: out\%NAME%\intermediate\diarization.json not found.
    echo Run the pipeline with --diarize first.
    exit /b 1
)
%PY% -c "import json; from pathlib import Path; from script.diarize import SpeakerSegment; from script.sample_extractor import extract_speaker_samples; b = Path('out/%NAME%'); diar = json.load(open(b/'intermediate/diarization.json', encoding='utf-8')); segs = [SpeakerSegment(**s) for s in diar]; out = extract_speaker_samples(audio_path=str(b/'intermediate/audio.wav'), speakers=segs, out_dir=str(b/'speaker_samples')); print(f'wrote {len(out)} samples to out/%NAME%/speaker_samples/')"
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
