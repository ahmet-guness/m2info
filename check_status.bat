@echo off
chcp 65001 > nul
title Metin2 Bagjanamu Canlı Durum Kontrolü

echo ========================================================
echo    Metin2 Bagjanamu Canli Durum Sorgusu (G-Status)
echo ========================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [HATA] Python bulunamadi!
    pause
    exit /b 1
)

python bot.py --check-status
echo.
pause
