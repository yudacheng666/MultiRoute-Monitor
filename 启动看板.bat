@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo 未检测到 Python。请安装 Python 3.10 或更高版本，并勾选 Add Python to PATH。
  pause
  exit /b 1
)
echo 正在启动 MultiRoute Monitor...
python app.py --open-browser
if errorlevel 1 (
  echo.
  echo 启动失败。请检查 8876 端口是否被占用，或在 PowerShell 中运行 python app.py 查看错误。
  pause
)
