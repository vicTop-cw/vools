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
rem JAVA 优先取环境变量 JAVA_EXE，否则用 PATH 上的 java
if defined JAVA_EXE (
    set "JAVA=%JAVA_EXE%"
) else (
    set "JAVA=java"
)

if not defined KOTLINC (
    echo Error: Kotlin compiler not found. Set KOTLINC_BAT to the kotlinc-jvm.bat path.
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