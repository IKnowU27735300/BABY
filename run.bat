@echo off
REM BABY - Local AI Desktop Assistant launcher
setlocal
set "BABY_DIR=%~dp0"
cd /d "%BABY_DIR%"

if not exist ".venv\Scripts\activate.bat" (
    echo [BABY] Virtual environment not found at .venv\Scripts\activate.bat
    echo [BABY] Create it with:  py -3.11 -m venv .venv
    echo [BABY] Then:              .venv\Scripts\activate.bat ^&^& pip install -r requirements.txt
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo [BABY] Starting BABY ...

REM Load Gemini TTS key from a local .env file (git-ignored).
REM Create .env next to run.bat with a line: GEMINI_API_KEY=your-key-here
REM If unset here, main.py also reads tts.gemini_api_key from config.yaml.
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do set "ENV_%%A=%%B"
    if defined ENV_GEMINI_API_KEY set "GEMINI_API_KEY=%ENV_GEMINI_API_KEY%"
)

python main.py
if errorlevel 1 (
    echo.
    echo [BABY] BABY exited with an error. Check data\logs\ for details.
    pause
)
endlocal




