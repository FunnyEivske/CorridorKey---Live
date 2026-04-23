@echo off
TITLE CorridorKey Live Studio Starter
chcp 65001 >nul

echo ===================================================
echo     CorridorKey Live Studio - Starter
echo ===================================================
echo.

:: Sørg for at uv kan bli funnet
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

:: Sjekker om uv er installert
where uv >nul 2>&1
if %errorlevel% neq 0 (
    goto :prompt_install
)

:: Sjekker om det virtuelle miljøet (.venv) finnes
if not exist ".venv" (
    goto :prompt_install
)

:: Sjekker om CorridorKey-modellen finnes
if not exist "CorridorKeyModule\checkpoints\CorridorKey_v1.0.pth" if not exist "CorridorKeyModule\checkpoints\CorridorKey.safetensors" if not exist "CorridorKeyModule\checkpoints\CorridorKey.pth" (
    goto :prompt_install
)

:: Alt ser bra ut, start programmet
goto :start_program


:prompt_install
echo [Advarsel] Det ser ut til at nødvendige verktøy, pakker eller AI-modeller mangler.
echo For å kjøre Live Studio må vi installere dette.
set /p DO_INSTALL="Vil du laste ned og installere alt som mangler nå? (J/N): "

if /i "%DO_INSTALL%"=="N" goto :cancel
if /i "%DO_INSTALL%"=="NEI" goto :cancel
if /i "%DO_INSTALL%"=="NO" goto :cancel

echo.
echo Starter oppsett...

:: 1. Installer uv hvis det mangler
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Laster ned og installerer pakkebehandleren 'uv'...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

:: 2. Installer Python-pakker for live og cuda
echo.
echo [INFO] Installerer avhengigheter (OpenCV, NDI, PyTorch, osv.)...
uv sync --extra live --extra cuda
if %errorlevel% neq 0 (
    echo [FEIL] Installasjon av avhengigheter feilet. Prøv igjen.
    pause
    exit /b
)

:: 3. Last ned CorridorKey-vekter hvis de mangler
echo.
echo [INFO] Sjekker AI-modeller...
if not exist "CorridorKeyModule\checkpoints" mkdir "CorridorKeyModule\checkpoints"
set "CKPT_DIR=CorridorKeyModule\checkpoints"
set "SAFETENSORS_PATH=%CKPT_DIR%\CorridorKey.safetensors"
set "PTH_PATH=%CKPT_DIR%\CorridorKey_v1.0.pth"
set "HF_BASE=https://huggingface.co/nikopueringer/CorridorKey_v1.0/resolve/main"

if exist "%SAFETENSORS_PATH%" (
    echo CorridorKey modell safetensors funnet.
) else (
    if exist "%PTH_PATH%" (
        echo CorridorKey modell pth funnet.
    ) else (
        echo [INFO] Laster ned CorridorKey modell ^(dette kan ta litt tid^)...
        curl.exe -L --fail -o "%SAFETENSORS_PATH%" "%HF_BASE%/CorridorKey_v1.0.safetensors"
        if errorlevel 1 (
            if exist "%SAFETENSORS_PATH%" del "%SAFETENSORS_PATH%"
            curl.exe -L -o "%PTH_PATH%" "%HF_BASE%/CorridorKey_v1.0.pth"
        )
    )
)

echo.
echo [INFO] Oppsett fullført!
echo.
goto :start_program


:cancel
echo.
echo Avbryter oppstarten. Du må ha disse filene for å kunne kjøre programmet.
pause
exit /b


:start_program
echo ===================================================
echo     Starter Live Studio...
echo ===================================================
uv run live_studio.py
if %errorlevel% neq 0 (
    echo.
    echo [FEIL] Programmet avsluttet med en feil.
    pause
)
