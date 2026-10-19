@echo off
rem ============================================================
rem  变更影响闭环 · Windows 侧隧道启动器（cmd）
rem
rem  作用：把服务器上的 127.0.0.1:8099 转发到本机 8099，
rem        然后打开浏览器。关闭 "loop-tunnel" 窗口即断开。
rem
rem  前提：服务器已启动界面（bash loop/remote/serve.sh）
rem        Windows 10/11 自带 OpenSSH 客户端（ssh 命令可用）
rem ============================================================
setlocal

if "%~1"=="" (
  set SERVER=192.168.1.24
) else (
  set SERVER=%~1
)
if "%~2"=="" (
  set SUSER=chenjunming
) else (
  set SUSER=%~2
)
set LOCAL_PORT=8099
set REMOTE_PORT=8099

echo [1/3] 启动 SSH 隧道 %LOCAL_PORT% -^> %SERVER%:%REMOTE_PORT% ...
start "loop-tunnel" ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -L %LOCAL_PORT%:127.0.0.1:%REMOTE_PORT% %SUSER%@%SERVER%

echo [2/3] 等待本地端口就绪 ...
set /a N=0
:wait
timeout /t 1 >nul
set /a N+=1
powershell -NoProfile -Command "try { $c=New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1',%LOCAL_PORT%); $c.Close(); exit 0 } catch { exit 1 }"
if errorlevel 1 (
  if %N% GEQ 15 (
    echo [失败] 15 秒内未连通。检查：服务器地址/用户名、服务器上服务是否已起、ssh 是否可用。
    echo        可改用 PowerShell 脚本查看更详细错误：
    echo        powershell -ExecutionPolicy Bypass -File loop\remote\connect-loop.ps1 -Server %SERVER% -User %SUSER%
    pause
    exit /b 1
  )
  goto wait
)

echo [3/3] 打开浏览器 http://127.0.0.1:%LOCAL_PORT%/
start "" http://127.0.0.1:%LOCAL_PORT%/

echo.
echo 隧道已建立。关闭标题为 "loop-tunnel" 的窗口即断开。
echo 若浏览器已打开但页面报错，先确认服务器端 serve.sh 仍在运行。
endlocal
