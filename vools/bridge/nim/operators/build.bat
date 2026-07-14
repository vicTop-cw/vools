@echo off
setlocal

set NIM=E:\Dowloads\nim-2.2.10_x64\nim-2.2.10\bin\nim.exe
set SRC_DIR=E:\IDEProjects\AI\vools\vools\bridge\nim\operators
set OUT_DIR=E:\IDEProjects\AI\vools\vools\bridge\nim\operators

echo Compiling Nim operators to DLL...
%NIM% compile --app:lib --out:%OUT_DIR%\vools_operators.dll %SRC_DIR%\operators.nim

if %errorlevel% equ 0 (
    echo DLL compiled successfully: %OUT_DIR%\vools_operators.dll
) else (
    echo Failed to compile DLL
    exit /b 1
)
