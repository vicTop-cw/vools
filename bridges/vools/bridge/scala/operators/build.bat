@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set SCALAC="E:\Scala\scala-2.13.11\bin\scalac.BAT"
set JAR="E:\Java\jdk17.0.17_10\bin\jar.exe"

if not exist %SCALAC% (
    echo Error: Scala compiler not found at %SCALAC%
    exit /b 1
)

if not exist %JAR% (
    echo Error: JAR tool not found at %JAR%
    exit /b 1
)

set OPERATORS_SRC=vools\bridge\scala\operators\Operators.scala
set OUTPUT_DIR=vools\bridge\scala\operators\target
set JAR_FILE=vools\bridge\scala\operators\vools-operators.jar

echo ============================================
echo Building Scala Operators JAR
echo ============================================

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

echo.
echo [1/2] Compiling sources...
%SCALAC% -d "%OUTPUT_DIR%" "%OPERATORS_SRC%"

if %errorlevel% neq 0 (
    echo Compilation failed!
    exit /b 1
)

echo.
echo [2/2] Creating JAR...
cd "%OUTPUT_DIR%"
%JAR% cf ..\vools-operators.jar com

if %errorlevel% neq 0 (
    echo JAR creation failed!
    exit /b 1
)

cd ..\..\..\..

echo.
echo JAR created: %JAR_FILE%
exit /b 0
