# 远程访问：服务器起服务 + Windows 走 SSH 隧道

> 与 DeepSeekHarnessLauncher 访问 DSH Web 的思路一致：**服务只监听服务器本机
> `127.0.0.1`，Windows 通过 SSH 本地端口转发把「本机端口」映射到服务器端口**，
> 浏览器访问 `http://127.0.0.1:8099/`，流量走 SSH 加密通道。
>
> 这样做的前提是：本界面**没有鉴权**（单机单用户）。所以**绝不能**把服务绑到
> `0.0.0.0`，也不要在服务器防火墙上放行 8099。

```
 Windows                                       服务器（本机 s24 / 192.168.1.24）
┌──────────────────┐    SSH 加密隧道     ┌────────────────────────────────────┐
│ 浏览器            │  ───────────────▶  │ sshd（22）                          │
│ http://127.0.0.1 │   本地端口转发      │   │                               │
│      :8099        │  -L 8099:          │   ▼                               │
│                    │     127.0.0.1:8099 │ uvicorn 127.0.0.1:8099            │
│ ssh -N -L ...     │                    │   loop/remote/serve.sh            │
└──────────────────┘                     └────────────────────────────────────┘
```

---

## 1 服务器侧：启动服务

三种方式，任选其一（都在**软件仓根目录**执行）。

```bash
# A. 默认：按 environments.json 解析 ENV_ROOT / WORKSPACE_ROOT
bash loop/remote/serve.sh

# B. 沙箱演示：用可写副本 workspaces/simenv-tcs9620-64ch-sandbox/
#    （本机 ENV_ROOT 被沙箱挂成只读时用这个，权威数据不动）
bash loop/remote/seed-sandbox-workspace.sh     # 首次：复制一份数据
bash loop/remote/serve.sh --sandbox

# C. 换端口
LOOP_PORT=9000 bash loop/remote/serve.sh
```

脚本会打印监听地址、数据根、以及 Windows 侧要用的隧道命令。前台运行，`Ctrl+C` 停止。

### 让服务常驻（可选）

```bash
# 后台常驻（日志在 loop/.logs/，已被 gitignore）
nohup bash loop/remote/serve.sh > loop/.logs/serve.log 2>&1 &
curl -s http://127.0.0.1:8099/api/health | head -c 120     # 自查

# 停止
pkill -f "uvicorn services.api:app"
```

### 方式 0：从 Windows 一条命令远程启动（最接近 DSH Launcher）

如果不想先登录服务器，可以在 **Windows PowerShell** 里让服务器起服务，再建隧道：

```powershell
ssh chenjunming@192.168.1.24 "cd /home/work/chenjunming/change-impact-loop && mkdir -p loop/.logs && nohup bash loop/remote/serve.sh > loop/.logs/serve.log 2>&1 & sleep 2; curl -s http://127.0.0.1:8099/api/health | head -c 120"
```

然后再运行本目录的 `connect-loop.ps1` / `connect-loop.bat`（或手动 `ssh -N -L ...`）。
这与 DeepSeekHarnessLauncher 的「远程启动 + 本地转发」是同一套动作，只是命令拆成了两步。

> 只绑 `127.0.0.1` 是刻意的：远程访问由 SSH 隧道提供传输与认证边界。

## 2 Windows 侧：建立隧道并访问

### 方式 1：双击脚本（推荐）

把仓库同步/拷贝到 Windows 后（或只拷 `loop/remote/` 这三个文件）：

| 文件 | 用法 |
|---|---|
| `connect-loop.bat` | 双击；也可 `connect-loop.bat 192.168.1.24 chenjunming` |
| `connect-loop.ps1` | `powershell -ExecutionPolicy Bypass -File connect-loop.ps1 -Server 192.168.1.24 -User chenjunming` |

两者都会：启动 `ssh -N -L 8099:127.0.0.1:8099 用户@服务器` → 等端口就绪 → 打开
`http://127.0.0.1:8099/`。**关闭 ssh 那个窗口即断开隧道。**

### 方式 2：手动一条命令

```powershell
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 `
    -L 8099:127.0.0.1:8099 chenjunming@192.168.1.24
```

然后浏览器打开 <http://127.0.0.1:8099/>。`-N` 表示只转发不开远端 shell；
`ExitOnForwardFailure=yes` 让端口占用时立刻报错而不是假装成功。

### 方式 3：PuTTY

`Connection → SSH → Tunnels`：Source port `8099`，Destination `127.0.0.1:8099`，
类型 `Local`，`Add`，再 `Open` 连到服务器。

### Windows 上没有 ssh？

- Windows 10/11：设置 → 应用 → 可选功能 → 添加「OpenSSH 客户端」。
- 或装 Git for Windows，用 `C:\Program Files\Git\usr\bin\ssh.exe`（`connect-loop.ps1` 会自动找）。
- DeepSeekHarnessLauncher 自带一份 `portable_ssh\ssh.exe`，也可以直接拿它来跑上面的命令。

## 3 首次连接：host key 与免密

1. 第一次连接会提示 `The authenticity of host ... can't be established`，
   输入 `yes` 接受（也可先手动 `ssh 用户@服务器` 一次）。
2. 想免密（脚本不弹密码框）：在 **Windows** 上生成并部署公钥：

   ```powershell
   ssh-keygen -t ed25519 -C "win-${env:USERNAME}"
   type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh chenjunming@192.168.1.24 "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
   ```

   这一步与 DeepSeekHarnessLauncher 的「部署密钥」是同一个动作，二选一即可。

## 4 排错

| 症状 | 先查 |
|---|---|
| `bind: Address already in use` | 本机 8099 被占：换 `-L 8100:127.0.0.1:8099`，或先关旧隧道 |
| 端口通了但页面 502/空 | 服务器上 `serve.sh` 没起，或起在别的端口；`curl 127.0.0.1:8099/api/health` 自查 |
| `Permission denied (publickey,password)` | 用户名/密钥不对；先在 Windows 手动 `ssh 用户@服务器` 验证 |
| 隧道几秒就断 | 网络/NAT 空闲回收；脚本已带 `ServerAliveInterval=30`，仍断就重跑 |
| 页面能开但操作报错 | 看 `/api/health` 的 `plugin_missing` / `workspace_missing`；若是只读环境，用 `--sandbox` 模式 |

## 5 与 DSH Web 的关系

| | DSH Web | 本闭环界面 |
|---|---|---|
| 服务器监听 | `127.0.0.1:3083` | `127.0.0.1:8099` |
| Windows 连接 | DeepSeekHarnessLauncher（含隧道） | 本目录脚本 / 手写 ssh |
| 访问地址 | `http://127.0.0.1:3083/` | `http://127.0.0.1:8099/` |
| 鉴权边界 | SSH 隧道 | SSH 隧道（服务本身无鉴权） |

两者端口不同、可同时存在；互不影响。
