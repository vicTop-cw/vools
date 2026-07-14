@echo off
setlocal

set "NIM=E:\Dowloads\nim-2.2.10_x64\nim-2.2.10\bin\nim.exe"
set "BASE_DIR=%~dp0..\.."
set "OPERATORS_SRC=%BASE_DIR%\vools\bridge\nim\operators\operators.nim"
set "TEST_SRC=%BASE_DIR%\tests\nim\operators_test.nim"

echo ============================================
echo Nim Operators Test Suite
echo ============================================

echo.
echo [1/2] Compiling and running tests...
"%NIM%" compile --run "%OPERATORS_SRC%" "%TEST_SRC%"

if %errorlevel% equ 0 (
    echo.
    echo All tests passed!
) else (
    echo.
    echo Tests failed!
    exit /b 1
)