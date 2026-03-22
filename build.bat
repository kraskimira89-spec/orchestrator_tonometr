@echo off
chcp 65001 > nul
echo ====================================
echo  Сборка PoverkiVSE.exe
echo ====================================

REM Очистка предыдущей сборки
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist PoverkiVSE.spec del PoverkiVSE.spec

REM Сборка (без --collect-submodules openpyxl: иначе тянется openpyxl.utils.dataframe → pandas/torch, сборка очень долгая)
pyinstaller ^
    --onefile ^
    --windowed ^
    --name PoverkiVSE ^
    --add-data "data;data" ^
    --add-data "documents;documents" ^
    --add-data "help;help" ^
    --hidden-import caldav ^
    --hidden-import caldav.elements ^
    --hidden-import openpyxl ^
    --hidden-import openpyxl.styles ^
    --hidden-import openpyxl.utils ^
    --hidden-import dotenv ^
    --hidden-import requests ^
    --collect-submodules caldav ^
    main.py

if exist dist\PoverkiVSE.exe (
    echo.
    echo ====================================
    echo  ГОТОВО: dist\PoverkiVSE.exe
    echo ====================================
) else (
    echo.
    echo  ОШИБКА: .exe не создан, проверьте вывод выше.
)
pause
