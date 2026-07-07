@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo Building Nim bridge libraries for Windows...

set "OUTDIR=..\..\lib\windows"

for %%F in (*.nim) do (
    set "libname=%%~nF"
    echo Building libvools_bridge_!libname!.dll ...
    nim c --app:lib --out:"%OUTDIR%\vools_bridge_!libname!.dll" "%%F"
)

echo Done! Libraries built in %OUTDIR%\
