# 浏览器验证离线交付 · 证据

日期：2026-10-22（Asia/Shanghai）。用户确认目标 Rocky Linux 8.10 / x86_64 / glibc 2.28；仓库记录 CPython 3.11。本轮新增验证工具、离线资源及安装说明，未修上轮业务复核问题。源码基线 `a19107c`，期间先归档前轮复核文档为 `d861ca3`。同一执行者分阶段验证，不冒充独立终验。

成果：[使用说明](../../loop/offline/README.md)、[资源清单](../../loop/offline/browser-linux-x86_64/manifest.json)、[切片计划](../plans/2026-10-22-browser-offline.md)、[工具](../../loop/spikes/browser_offline.py)。汇总见 [STATUS §36](../STATUS.md#36-rocky-浏览器验证离线交付2026-10-22)。

## 来源与构建

Python wheel 从 PyPI 下载，分别指定 CPython 3.11/3.12、manylinux2014_x86_64 / manylinux_2_17_x86_64，版本固定在清单中。两份 lock 各含完整增量依赖闭包与 wheel 哈希。Playwright 官方浏览器 CDN 下载返回 `403 Domain forbidden`，未绕过策略；改从允许访问的 Google 官方地址取得 Linux Chrome 发行包，原包 SHA-256、版本和来源都在 manifest。

浏览器部分直接保存原 `.deb` 内 `data.tar.xz` 的分片；运行时只提取 opt/google/chrome，不调用包管理器。普通 Git 文件，不使用 LFS。资源核验实际输出：

```text
PASS: offline bundle platform and SHA-256 verification
PASS: all vendor resources are listed; every Git object is below 50 MiB.
bundle_bytes=194484143
```

核心 ELF 静态检查：Playwright driver/node 的最高 GLIBC 符号版本为 GLIBC_2.28，Chrome 主程序为 GLIBC_2.25。只说明这些核心 ELF 的符号要求，不能代替所有系统共享库和字体的运行验证。

## 工具边界断言

命令（loop 目录）：`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q tests/test_browser_offline.py --tb=short`。

实现前：

```text
7 errors in 0.57s
```

原因是新工具文件尚不存在（FileNotFoundError），不是已存在业务用例回归。实现后 CPython 3.12：

```text
.......                                                                  [100%]
7 passed in 0.53s
```

相同用例在新建 CPython 3.11 venv：

```text
.......                                                                  [100%]
7 passed in 0.59s
```

覆盖资源损坏、平台/glibc/Python 不兼容、归档越界/链接、只解开运行时、不静默回退显式错误浏览器路径。

## 干净环境安装与启动

临时 CPython 3.11.17 / 3.12.14 venv 起始没有 Playwright；安装工具强制 pip `--isolated --no-index --require-hashes --no-deps --only-binary=:all:`。命令中的脚本来自本仓，cache-root 指向自动验证目录，未改项目已有 venv。

CPython 3.11：先执行 `browser_offline.py install --bundled --cache-root /tmp/browser-offline-build/runtime`。原始输出：

```text
PASS: offline bundle platform and SHA-256 verification
Looking in links: /workspace/fpga_sim_workflow/loop/offline/browser-linux-x86_64/wheels
Processing ./loop/offline/browser-linux-x86_64/wheels/playwright-1.64.0-py3-none-manylinux1_x86_64.whl (from -r /workspace/fpga_sim_workflow/loop/offline/browser-linux-x86_64/requirements-cp311.lock (line 2))
Processing ./loop/offline/browser-linux-x86_64/wheels/greenlet-3.2.5-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.whl (from -r /workspace/fpga_sim_workflow/loop/offline/browser-linux-x86_64/requirements-cp311.lock (line 3))
Processing ./loop/offline/browser-linux-x86_64/wheels/pyee-13.0.1-py3-none-any.whl (from -r /workspace/fpga_sim_workflow/loop/offline/browser-linux-x86_64/requirements-cp311.lock (line 4))
Processing ./loop/offline/browser-linux-x86_64/wheels/typing_extensions-4.16.0-py3-none-any.whl (from -r /workspace/fpga_sim_workflow/loop/offline/browser-linux-x86_64/requirements-cp311.lock (line 5))
Installing collected packages: typing_extensions, pyee, playwright, greenlet
Successfully installed greenlet-3.2.5 playwright-1.64.0 pyee-13.0.1 typing_extensions-4.16.0
PASS: local browser smoke; version=156.0.8078.47; executable=/tmp/browser-offline-build/runtime/pw1.64.0-chrome156.0.8078.47-linux-x86_64/chrome
```

CPython 3.12：执行 `browser_offline.py install --executable /usr/bin/chromium`。原始输出：

```text
PASS: offline bundle platform and SHA-256 verification
Looking in links: /workspace/fpga_sim_workflow/loop/offline/browser-linux-x86_64/wheels
Processing ./loop/offline/browser-linux-x86_64/wheels/playwright-1.64.0-py3-none-manylinux1_x86_64.whl (from -r /workspace/fpga_sim_workflow/loop/offline/browser-linux-x86_64/requirements-cp312.lock (line 2))
Processing ./loop/offline/browser-linux-x86_64/wheels/greenlet-3.2.5-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl (from -r /workspace/fpga_sim_workflow/loop/offline/browser-linux-x86_64/requirements-cp312.lock (line 3))
Processing ./loop/offline/browser-linux-x86_64/wheels/pyee-13.0.1-py3-none-any.whl (from -r /workspace/fpga_sim_workflow/loop/offline/browser-linux-x86_64/requirements-cp312.lock (line 4))
Processing ./loop/offline/browser-linux-x86_64/wheels/typing_extensions-4.16.0-py3-none-any.whl (from -r /workspace/fpga_sim_workflow/loop/offline/browser-linux-x86_64/requirements-cp312.lock (line 5))
Installing collected packages: typing_extensions, pyee, playwright, greenlet
Successfully installed greenlet-3.2.5 playwright-1.64.0 pyee-13.0.1 typing_extensions-4.16.0
PASS: local browser smoke; version=154.0.8037.57; executable=/usr/bin/chromium
```

均退出 0；后者证明复用已有系统浏览器的路径。CPython 3.11 的项目基础 requirements 随后在联网构建阶段安装，**不包含在离线增量包中**；pip check 输出 `No broken requirements found.`。完整 browser 回归使用已装项目依赖和离线 UI 依赖的该 venv。

## 随包 Chrome 的浏览器回归

仓库根执行：

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/browser-offline-build/venv311/bin/python loop/spikes/browser_offline.py run --bundled --cache-root /tmp/browser-offline-build/runtime
```

实际输出，退出码 0：

```text
PASS: offline bundle platform and SHA-256 verification
PASS: local browser smoke; version=156.0.8078.47; executable=/tmp/browser-offline-build/runtime/pw1.64.0-chrome156.0.8078.47-linux-x86_64/chrome
.........................................                                [100%]
41 passed in 55.22s
```

受控本地静态网页/API，不连接真实 provider 或仿真。工具先做启动冒烟，测试中出现跳过或零用例不会按成功返回。未将 skip 当作浏览器已验证。

## Rocky 8.10 容器的真正断网检查

使用官方 `rockylinux/rockylinux:8.10`，digest `sha256:e8a49c5403b687db05d4d67333fa45808fbe74f36e683cec7abb1f7d0f2338c6`。Docker `--network none`，源码/离线包/Python 运行时只读挂载；在容器新建空 venv 后执行 install，显式指定已解开的随包 Chrome。Python 安装无需任何网络，完整输出：

```text
PASS: offline bundle platform and SHA-256 verification
Looking in links: /workspace/fpga_sim_workflow/loop/offline/browser-linux-x86_64/wheels
Processing /workspace/fpga_sim_workflow/loop/offline/browser-linux-x86_64/wheels/playwright-1.64.0-py3-none-manylinux1_x86_64.whl (from -r /workspace/fpga_sim_workflow/loop/offline/browser-linux-x86_64/requirements-cp311.lock (line 2))
Processing /workspace/fpga_sim_workflow/loop/offline/browser-linux-x86_64/wheels/greenlet-3.2.5-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.whl (from -r /workspace/fpga_sim_workflow/loop/offline/browser-linux-x86_64/requirements-cp311.lock (line 3))
Processing /workspace/fpga_sim_workflow/loop/offline/browser-linux-x86_64/wheels/pyee-13.0.1-py3-none-any.whl (from -r /workspace/fpga_sim_workflow/loop/offline/browser-linux-x86_64/requirements-cp311.lock (line 4))
Processing /workspace/fpga_sim_workflow/loop/offline/browser-linux-x86_64/wheels/typing_extensions-4.16.0-py3-none-any.whl (from -r /workspace/fpga_sim_workflow/loop/offline/browser-linux-x86_64/requirements-cp311.lock (line 5))
Installing collected packages: typing_extensions, pyee, playwright, greenlet
Successfully installed greenlet-3.2.5 playwright-1.64.0 pyee-13.0.1 typing_extensions-4.16.0
FAIL: RuntimeError: missing host libraries (use Rocky 8 RPMs): libnspr4.so => not found; libnss3.so => not found; libnssutil3.so => not found; libsmime3.so => not found; libatk-1.0.so.0 => not found; libatk-bridge-2.0.so.0 => not found; libcups.so.2 => not found; libxcb.so.1 => not found; libxkbcommon.so.0 => not found; libasound.so.2 => not found; libgbm.so.1 => not found; libX11.so.6 => not found; libXext.so.6 => not found; libcairo.so.2 => not found; libpango-1.0.so.0 => not found; libXcomposite.so.1 => not found; libXdamage.so.1 => not found; libXfixes.so.3 => not found; libXrandr.so.2 => not found; libatspi.so.0 => not found
```

该检查退出码 1：**wheel 安装成功，Chrome 因最小镜像缺系统库而未通过启动**。工具如实列出缺件，没有把它记为通过，也没有联网安装系统 RPM。使用同一容器、同样 `--network none` 单独核验已装 wheel 和 Playwright driver：

```text
ldd (GNU libc) 2.28
PASS: CPython 3.11 / greenlet / Playwright imports on Rocky 8.10
v24.21.0
```

该 driver 检查退出码 0。这证明 Rocky/glibc 的 Python 包与 Node 驱动可运行，不能证明目标内网主机的共享库/字体已齐全。内网已有 Chrome 可优先复用；缺件时需用匹配 Rocky 8 RPM 补齐，禁止复制 Debian 系统库或替换 glibc。

## 归档与限制

未运行完整业务单测、kb 自测、真实 provider、端到端或内网主机浏览器测试。当前内网主机共享库是否齐全须在该主机运行 check；既有 F08 等业务问题继续保持未修复。

本轮文件链接、脚本语法、哈希与补丁检查记录于 STATUS。旧冻结证据只读；本文冻结后不回填，MD5 记在 STATUS。
