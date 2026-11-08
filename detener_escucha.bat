@echo off
type nul > "%~dp0intercambio\detener_timer"
echo Señal enviada para detener la escucha MCP en PowerFactory.
timeout /t 2 >nul
