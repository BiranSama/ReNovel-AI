@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║       Re:Novel 文境重塑 - 环境安装脚本                      ║
echo ║       Re:Novel AI - Environment Setup Script               ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.11 或更高版本
    echo [Error] Python not found. Please install Python 3.11 or newer
    echo.
    echo 下载地址 / Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYTHON_VERSION=%%v
echo [信息] 检测到 Python 版本: %PYTHON_VERSION%

echo %PYTHON_VERSION% | findstr /r "^3\.1[1-9]\." >nul
if errorlevel 1 (
    echo [警告] 需要 Python 3.11 或更高版本，当前版本无法安装部分依赖
    echo [Warning] Python 3.11 or newer is required
    echo.
    choice /c yn /m "是否继续安装？ / Continue anyway? (y/n)"
    if errorlevel 2 exit /b 0
)

echo.
echo [步骤 1/4] 创建虚拟环境...
if exist "venv" (
    echo [信息] 虚拟环境已存在，跳过创建
) else (
    python -m venv venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo [完成] 虚拟环境创建成功
)

echo.
echo [步骤 2/4] 激活虚拟环境...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [错误] 激活虚拟环境失败
    pause
    exit /b 1
)
echo [完成] 虚拟环境已激活

echo.
echo [步骤 3/4] 升级 pip...
python -m pip install --upgrade pip -q
echo [完成] pip 已升级

echo.
echo [步骤 4/4] 安装项目依赖...
echo [信息] 这可能需要几分钟，请耐心等待...
pip install -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败
    echo [提示] 如果是 chromadb 安装失败，请确保已安装 Visual C++ Build Tools
    echo       下载地址: https://visualstudio.microsoft.com/visual-cpp-build-tools/
    pause
    exit /b 1
)
echo [完成] 依赖安装成功

echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║                    安装完成！                              ║
echo ║                 Installation Complete!                     ║
echo ╚════════════════════════════════════════════════════════════╝
echo.
echo 使用方法 / Usage:
echo   1. 激活虚拟环境 / Activate venv:
echo      venv\Scripts\activate
echo.
echo   2. 启动程序 / Run the app:
echo      python main.py
echo.
echo   3. 退出虚拟环境 / Deactivate:
echo      deactivate
echo.
pause
