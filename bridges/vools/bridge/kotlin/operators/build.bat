@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

rem KOTLINC 优先取环境变量 KOTLINC_BAT，否则自动探测常见 IntelliJ 安装位置，避免写死本机路径
if defined KOTLINC_BAT (
    set "KOTLINC=%KOTLINC_BAT%"
) else (
    set "KOTLINC="
    for /d %%d in ("C:\Program Files\JetBrains\*") do (
        if not defined KOTLINC if exist "%%d\plugins\Kotlin\kotlinc\bin\kotlinc-jvm.bat" (
            set "KOTLINC=%%d\plugins\Kotlin\kotlinc\bin\kotlinc-jvm.bat"
        )
    )
)

if not defined KOTLINC (
    echo Error: Kotlin compiler not found. Set KOTLINC_BAT to the kotlinc-jvm.bat path.
    exit /b 1
)

set OPERATORS_SRC=vools\bridge\kotlin\operators\Operators.kt
set OUTPUT_DIR=vools\bridge\kotlin\operators\target
set JAR_FILE=vools\bridge\kotlin\operators\vools-operators.jar

echo ============================================
echo Building Kotlin Operators JAR
echo ============================================

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

echo.
echo [1/1] Compiling and creating JAR...
"%KOTLINC%" -d "%JAR_FILE%" "%OPERATORS_SRC%"

if %errorlevel% neq 0 (
    echo Compilation failed!
    exit /b 1
)

echo.
echo JAR created: %JAR_FILE%
exit /b 0