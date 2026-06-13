@echo off
set PATH=%USERPROFILE%\.cargo\bin;%PATH%
echo StockInsight Pro — A股量化分析桌面端
echo.
echo 正在启动...
npm run tauri dev
pause
