@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set "KOTLINC=E:\Program Files\JetBrains\IntelliJ IDEA Community Edition 2025.2.4\plugins\Kotlin\kotlinc\bin\kotlinc-jvm.bat"
set "JAVA=E:\Java\jdk17.0.17_10\bin\java.exe"

if not exist "%KOTLINC%" (
    echo Error: Kotlin compiler not found at %KOTLINC%
    exit /b 1
)

set "BASE_DIR=%~dp0..\.."
set "OPERATORS_SRC=%BASE_DIR%\vools\bridge\kotlin\operators\Operators.kt"
set "TEST_SRC=%BASE_DIR%\tests\kotlin\OperatorsTest.kt"
set "OUTPUT_DIR=%BASE_DIR%\tests\kotlin\target"

echo ============================================
echo Kotlin Operators Test Suite
echo ============================================

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

echo.
echo [1/2] Compiling sources...
call "%KOTLINC%" -d "%OUTPUT_DIR%" "%OPERATORS_SRC%" "%TEST_SRC%"

if %errorlevel% neq 0 (
    echo Compilation failed!
    exit /b 1
)

echo.
echo [2/2] Running tests...
"%JAVA%" -cp "%OUTPUT_DIR%" com.example.operators.OperatorsTestKt

if %errorlevel% neq 0 (
    echo Tests failed!
    exit /b 1
)

echo.
echo All tests passed!
exit /b 0