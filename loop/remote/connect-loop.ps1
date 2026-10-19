<#
.SYNOPSIS
  变更影响闭环 · Windows 侧隧道启动器（PowerShell）

.DESCRIPTION
  在 Windows 上建立到服务器的 SSH 本地端口转发（127.0.0.1:LocalPort），
  等待端口就绪后打开浏览器。服务器侧需先运行：
      bash loop/remote/serve.sh        # 或 --sandbox
  关闭隧道 ssh 窗口即断开；本脚本会打印 PID 便于停止。

.PARAMETER Server
  服务器地址（与 DeepSeekHarnessLauncher 里填的是同一台机器）。

.PARAMETER User
  服务器 SSH 用户名。

.PARAMETER LocalPort
  Windows 本地监听端口，默认 8099。

.PARAMETER RemotePort
  服务器上的服务端口，默认 8099。

.PARAMETER TimeoutSeconds
  等待本地端口就绪的秒数，默认 30。

.PARAMETER SshExe
  指定 ssh.exe（默认自动查找 OpenSSH / Git for Windows / PATH）。

.PARAMETER NoBrowser
  只建隧道，不开浏览器。

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File loop\remote\connect-loop.ps1
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File loop\remote\connect-loop.ps1 -Server 192.168.1.24 -User chenjunming -LocalPort 8099
#>
[CmdletBinding()]
param(
  [string]$Server = "192.168.1.24",
  [string]$User = "chenjunming",
  [int]$LocalPort = 8099,
  [int]$RemotePort = 8099,
  [int]$TimeoutSeconds = 30,
  [string]$SshExe = "",
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

function Find-Ssh {
  if ($SshExe -and (Test-Path $SshExe)) { return $SshExe }
  $candidates = @()
  if ($env:WINDIR) { $candidates += (Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe") }
  foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
    if ($base) { $candidates += (Join-Path $base "Git\usr\bin\ssh.exe") }
  }
  foreach ($c in $candidates) {
    if ($c -and (Test-Path $c)) { return $c }
  }
  $cmd = Get-Command ssh -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  throw "找不到 ssh.exe。请安装 Windows OpenSSH 客户端（设置 → 应用 → 可选功能），或用 -SshExe 指定。"
}

function Test-TcpPort([int]$Port) {
  try {
    $client = New-Object Net.Sockets.TcpClient
    $iar = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
    if (-not $iar.AsyncWaitHandle.WaitOne(800)) { $client.Close(); return $false }
    $client.EndConnect($iar); $client.Close(); return $true
  } catch { return $false }
}

$ssh = Find-Ssh
$target = "${User}@${Server}"
$sshArgs = @(
  "-N",
  "-o", "ExitOnForwardFailure=yes",
  "-o", "ServerAliveInterval=30",
  "-o", "ServerAliveCountMax=3",
  "-L", "${LocalPort}:127.0.0.1:${RemotePort}",
  $target
)

Write-Host "============================================================"
Write-Host " 变更影响闭环 · 隧道启动器"
Write-Host " 服务器 : $target"
Write-Host " 转发   : 127.0.0.1:$LocalPort  ->  $Server : 127.0.0.1:$RemotePort"
Write-Host " ssh    : $ssh"
Write-Host "============================================================"

if (Test-TcpPort $LocalPort) {
  Write-Host "[信息] 本地端口 $LocalPort 已经可连，可能已有隧道在跑；跳过新建。" -ForegroundColor Yellow
} else {
  Write-Host "[1/3] 启动 SSH 隧道（会弹出一个 ssh 窗口；首次连接会询问 host key）..."
  $proc = Start-Process -FilePath $ssh -ArgumentList $sshArgs -PassThru
  Write-Host "[信息] 隧道进程 PID = $($proc.Id)；关闭它的窗口即断开。"

  Write-Host "[2/3] 等待本地端口就绪（最多 $TimeoutSeconds 秒）..."
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  $ready = $false
  while ((Get-Date) -lt $deadline) {
    if (Test-TcpPort $LocalPort) { $ready = $true; break }
    if ($proc.HasExited) { break }
    Start-Sleep -Milliseconds 500
  }
  if (-not $ready) {
    Write-Host "[失败] 隧道没有就绪。可能原因：" -ForegroundColor Red
    Write-Host "  - 服务器地址/用户名不对（与 DSH Launcher 使用同一台服务器）"
    Write-Host "  - 首次连接需要接受 host key：请在弹出的 ssh 窗口里确认"
    Write-Host "  - 未配置密钥且需要密码：请在 ssh 窗口输入密码"
    Write-Host "  - 服务器上 8099 没有服务：先运行 bash loop/remote/serve.sh"
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
    exit 1
  }
}

Write-Host "[3/3] 端口就绪：http://127.0.0.1:$LocalPort/"
if (-not $NoBrowser) {
  Start-Process "http://127.0.0.1:$LocalPort/"
  Write-Host "[信息] 已尝试打开浏览器。"
}
Write-Host ""
Write-Host "停止隧道：关闭 ssh 窗口；或 Get-Process ssh | Stop-Process（会停掉所有 ssh）。"
