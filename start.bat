@echo off
chcp 65001 >nul
title Литературный сборник
cd /d "%~dp0"

echo ============================================================
echo   Литературный сборник — запуск сайта
echo ============================================================
echo.
echo Проверка зависимостей...
pip install -r requirements.txt
if errorlevel 1 goto :err

echo.
echo Запуск сайта. Браузер откроется автоматически.
echo Адрес и порт будут показаны в окне ниже.
echo Для остановки нажмите Ctrl+C в этом окне.
echo.
python app.py
goto :eof

:err
echo.
echo Ошибка установки зависимостей. Попробуйте выполнить вручную:
echo   pip install -r requirements.txt
echo.
pause