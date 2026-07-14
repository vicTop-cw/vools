@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set SCALAC="E:\Scala\scala-2.13.11\bin\scalac.BAT"
set SCALA="E:\Scala\scala-2.13.11\bin\scala.BAT"

if not exist %SCALAC% (
    echo Error: Scala compiler not found at %SCALAC%
    exit /b 1
)

set BASE_DIR=%~dp0..\..
set OPERATORS_SRC=%BASE_DIR%\vools\bridge\scala\operators\Operators.scala
set TEST_SRC=%BASE_DIR%\tests\scala\OperatorsTest.scala
set OUTPUT_DIR=%BASE_DIR%\tests\scala\target

echo ============================================
echo Scala Operators Test Suite
echo ============================================

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

echo.
echo [1/2] Compiling sources...
%SCALAC% -d "%OUTPUT_DIR%" "%OPERATORS_SRC%" "%TEST_SRC%"

if %errorlevel% neq 0 (
    echo Compilation failed!
    exit /b 1
)

echo.
echo [2/2] Running tests...
%SCALA% -cp "%OUTPUT_DIR%" com.example.operators.OperatorsTest

if %errorlevel% neq 0 (
    echo Tests failed!
    exit /b 1
)

echo.
echo All tests passed!
exit /b 0