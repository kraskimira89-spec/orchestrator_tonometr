@echo off
chcp 65001 > nul
echo ====================================
echo  Сборка OrchestratorTonometr.exe
echo ====================================

REM Очистка предыдущей сборки
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist OrchestratorTonometr.spec del OrchestratorTonometr.spec

REM Сборка (без --collect-submodules openpyxl: иначе тянется openpyxl.utils.dataframe → pandas/torch, сборка очень долгая)
pyinstaller ^
    --onefile ^
    --windowed ^
    --name OrchestratorTonometr ^
    --add-data "data;data" ^
    --add-data "documents;documents" ^
    --hidden-import caldav ^
    --hidden-import caldav.elements ^
    --hidden-import openpyxl ^
    --hidden-import openpyxl.styles ^
    --hidden-import openpyxl.utils ^
    --hidden-import dotenv ^
    --hidden-import requests ^
    --collect-submodules caldav ^
    main.py

if exist dist\OrchestratorTonometr.exe (
    echo.
    echo ====================================
    echo  ГОТОВО: dist\OrchestratorTonometr.exe
    echo ====================================
) else (
    echo.
    echo  ОШИБКА: .exe не создан, проверьте вывод выше.
)
pause
