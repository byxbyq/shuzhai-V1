@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title ShuZhai
chcp 65001 >nul

:: ===== 定位真 Python（跳过 Microsoft Store 假壳） =====
set PYTHON=
for /d %%d in ("%LOCALAPPDATA%\Programs\Python\*") do (
    if exist "%%d\python.exe" set "PYTHON=%%d\python.exe"
)
if "%PYTHON%"=="" (
    for %%p in (python3.11 python3 python) do (
        %%p -c "import sys; sys.exit(0 if 'WindowsApps' not in sys.executable else 1)" >nul 2>&1
        if !ERRORLEVEL! EQU 0 set "PYTHON=%%p"
        if not "!PYTHON!"=="" goto :python_found
    )
)
:python_found
if "%PYTHON%"=="" (
    echo [错误] 未找到可用的 Python。请安装 Python 3.10+ 并加入 PATH。
    pause
    exit /b 1
)
echo [ShuZhai] 使用: %PYTHON%

:: ===== 检查 requirements.txt =====
if not exist "requirements.txt" (
    echo [错误] 未找到 requirements.txt
    pause
    exit /b 1
)

:: ===== 安装依赖 =====
%PYTHON% -c "import fastapi" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ShuZhai] 正在安装依赖，请稍候...
    %PYTHON% -m pip install -r requirements.txt
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo [错误] 依赖安装失败，请截图上方输出发我排查。
        pause
        exit /b 1
    )
    echo [ShuZhai] 依赖安装完成
)

:: ===== 第三步：启动 =====
:: --lan：保持历史行为，允许同局域网手机访问（无认证，家庭/可信网络使用）
set MAX_RETRIES=5
set RETRY_COUNT=0
:loop
%PYTHON% server.py --lan
if %ERRORLEVEL% EQU 0 (
    echo [ShuZhai] 正常关闭。
    pause
    goto :eof
)
set /a RETRY_COUNT+=1
if %RETRY_COUNT% GEQ %MAX_RETRIES% (
    echo.
    echo ============================================
    echo [ShuZhai] 已达最大重试次数（%MAX_RETRIES%），退出。
    echo 请截图上方错误信息以便排查。
    echo ============================================
    pause
    goto :eof
)
echo.
echo ============================================
echo [ShuZhai] 服务崩溃，3 秒后重试... (%RETRY_COUNT%/%MAX_RETRIES%)
echo 按 Ctrl+C 取消。
echo ============================================
timeout /t 3 /nobreak >nul
goto loop
