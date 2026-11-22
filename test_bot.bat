@echo off
chcp 65001 > nul
title Metin2 Happy Hour - Telegram Test

echo ========================================================
echo    Metin2 Bot Sistem ve Bildirim Dogrulama
echo ========================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [HATA] Python bulunamadi!
    pause
    exit /b 1
)

python verify_full_chain.py
echo.
echo Telegram bildirim testi gonderiliyor...
python bot.py --test
echo.
pause
