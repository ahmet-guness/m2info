@echo off
chcp 65001 > nul
title Metin2 Happy Hour Bildirim Botu

echo ========================================================
echo    Metin2 Happy Hour Telegram Bildirim Botu
echo ========================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [HATA] Python bulunamadi! Lutfen Python 3'un kurulu oldugundan ve PATH'e eklendiginden emin olun.
    pause
    exit /b 1
)

python bot.py
if %errorlevel% neq 0 (
    echo.
    echo [BILGI] Bot durduruldu veya bir hata olustu.
    pause
)
