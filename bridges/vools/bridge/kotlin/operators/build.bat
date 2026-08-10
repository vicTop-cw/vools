@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set KOTLINC="E:\Program Files\JetBrains\IntelliJ IDEA Community Edition 2025.2.4\plugins\Kotlin\kotlinc\bin\kotlinc-jvm.bat"

if not exist %KOTLINC% (
    echo Error: Kotlin compiler not found at %KOTLINC%
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
%KOTLINC% -d "%JAR_FILE%" "%OPERATORS_SRC%"

if %errorlevel% neq 0 (
    echo Compilation failed!
    exit /b 1
)

echo.
echo JAR created: %JAR_FILE%
exit /b 0
