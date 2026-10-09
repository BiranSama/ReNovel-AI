@echo off
:: 设置编码为 UTF-8，防止中文乱码（如果乱码请去掉这一行）
chcp 65001 >nul

:: 1. 切换到当前脚本所在的目录
cd /d "%~dp0"

echo ==============================================
echo [1/3] 正在检查并安装依赖库...
echo ==============================================
:: 检查 requirements.txt 是否存在
if exist requirements.txt (
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [警告] 依赖安装似乎出错了，请检查上面的红色错误信息。
        pause
    )
) else (
    echo 未找到 requirements.txt，跳过依赖安装。
)

echo.
echo ==============================================
echo [2/3] 正在运行初始化脚本 (FirsTime.py)...
echo ==============================================
:: 检查 FirstTime.py 是否存在
if exist FirstTime.py (
    python FirstTime.py
) else (
    echo 未找到 FirstTime.py，跳过此步骤。
)

echo.
echo ==============================================
echo [3/3] 准备启动主程序 (main.py)...
echo ==============================================
:: 运行主程序
python main.py

:: 运行结束，暂停查看输出
echo.
echo ==============================================
echo 所有程序运行结束。
pause