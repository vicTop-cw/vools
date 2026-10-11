@echo off
setlocal

rem 由本脚本位置反推 SRC/OUT 目录，避免硬编码绝对路径（可在任意机器/CI 直接跑）
set "SRC_DIR=%~dp0"
set "OUT_DIR=%~dp0"

rem Nim 可执行文件：优先取环境变量 NIM_EXE，其次用 PATH 上的 nim，避免写死本机路径
if defined NIM_EXE (
    set "NIM=%NIM_EXE%"
) else (
    set "NIM=nim"
)

echo Compiling Nim operators to DLL...
%NIM% compile --app:lib --out:"%OUT_DIR%vools_operators.dll" "%SRC_DIR%operators.nim"

if %errorlevel% equ 0 (
    echo DLL compiled successfully: %OUT_DIR%vools_operators.dll
) else (
    echo Failed to compile DLL
    exit /b 1
)