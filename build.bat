@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

set APP_NAME=FH6Auto
set MAIN_FILE=main.py

echo.
echo ==============================
echo 开始打包 %APP_NAME% 及其更新组件
echo ==============================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 python，请先配置环境变量
    pause
    exit /b 1
)

echo [1/4] 清理旧文件...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "*.spec" del /f /q "*.spec"
if not exist assets mkdir assets

echo [2/4] 正在编译独立更新器 (Updater.exe)...
:: 打包成无黑框的单文件
python -m PyInstaller -n "Updater" -F -w "updater.py"
if errorlevel 1 (
    echo [错误] Updater 打包失败！
    pause
    exit /b 1
)
:: 将打包好的 Updater.exe 移到 assets 文件夹备用
copy /y "dist\Updater.exe" "assets\Updater.exe" >nul

echo [3/4] 正在编译主程序 (%APP_NAME%.exe)...
:: 打包主程序，并将 assets (包含刚生成的 Updater.exe) 吞进肚子里
python -m PyInstaller ^
    -n "%APP_NAME%" ^
    -F ^
    -w ^
    --uac-admin ^
    "%MAIN_FILE%" ^
    --icon=assets/icon.ico ^
    --add-data "images;images" ^
    --add-data "assets;assets"

if errorlevel 1 (
    echo.
    echo [错误] 主程序打包失败！
    pause
    exit /b 1
)

echo.
echo [4/4] 全部打包完成！
echo 输出目录: dist\%APP_NAME%.exe
echo.
pause