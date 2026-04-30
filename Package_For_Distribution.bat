@echo off
TITLE CorridorKey Packager
chcp 65001 >nul

echo ===================================================
echo     Packaging CorridorKey Live Studio...
echo ===================================================
echo.

:: Sjekker om uv er installert
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [FEIL] uv er ikke installert. Vennligst kjor Start_Live_Studio_Windows.bat forst for a sette opp miljoet.
    pause
    exit /b
)

uv run python build_release.py

echo.
pause
