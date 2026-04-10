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
    copy /Y "README.txt" "dist\README.txt" > nul 2>&1
    copy /Y "Инструкция_пользователю.txt" "dist\Инструкция_пользователю.txt" > nul 2>&1
    echo.
    echo ====================================
    echo  ГОТОВО: dist\PoverkiVSE.exe
    echo  + README.txt, Инструкция_пользователю.txt
    echo ====================================
) else (
    echo.
    echo  ОШИБКА: .exe не создан, проверьте вывод выше.
)
pause
