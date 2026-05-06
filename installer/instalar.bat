@echo off
:: Lanzador del instalador STEH Chip-Assigner
:: Eleva permisos y ejecuta el script PowerShell principal

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Solicitando permisos de administrador...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

powershell -ExecutionPolicy Bypass -File "%~dp0instalar.ps1"
