# 浏览器验证离线包

目标：Rocky Linux 8.10、x86_64、glibc 2.28，CPython 3.11；也提供 CPython 3.12 的 wheel。仅补浏览器依赖，项目原有 `.venv` 和 requirements 需要已经可用。实际验证和限制见 [STATUS §36](../../doc/STATUS.md#36-rocky-浏览器验证离线交付2026-10-22)。

## 内网拉取后运行

从仓库根执行：

```bash
git pull --ff-only
cd loop
.venv/bin/python spikes/browser_offline.py install
.venv/bin/python spikes/browser_offline.py run
```

`install` 先校验本地文件，再以 `--no-index --require-hashes --no-deps` 安装锁定 wheel，不访问 PyPI。随后检查并真实启动浏览器；`run` 冒烟通过后运行现有浏览器测试，出现 skip 或零用例不会记为通过。

默认优先读取 `LOOP_BROWSER_EXECUTABLE`，再查系统 Google Chrome/Chromium，找不到则解开随包 Chrome。也可指定已有 Chrome：

```bash
LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome .venv/bin/python spikes/browser_offline.py install
LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome .venv/bin/python spikes/browser_offline.py run
```

强制使用随包版本（运行前清除原有浏览器变量，避免配置冲突）：

```bash
env -u LOOP_BROWSER_EXECUTABLE .venv/bin/python spikes/browser_offline.py install --bundled
env -u LOOP_BROWSER_EXECUTABLE .venv/bin/python spikes/browser_offline.py run --bundled
```

默认缓存为软件目录下的 `.browser-cache`（Git 忽略），可用 `--cache-root /可写路径` 指定；不安装系统包、不写系统目录、不需要 root。`verify` 只校验平台与随包文件，`check` 校验后只做浏览器启动冒烟。

## 系统库与字体

Python wheels 和浏览器可执行文件均随 Git 提供，安装时无需外网。**主机共享库和字体仍由 Rocky 系统提供**，不会把 Debian 的系统 `.so` 复制覆盖到 Rocky。已装 Chrome 的内网主机通常已具备其库；最小服务器镜像可能缺少它们。工具会报告 `lib*.so => not found`，这时需要通过内网 Rocky 8 RPM 源或管理员提供的匹配 RPM 补齐，再重跑。不能把 wheel 安装成功等同于浏览器验收通过。

常见对应包包括 `nss`、`nspr`、`atk`、`at-spi2-atk`、`alsa-lib`、`cups-libs`、`libXcomposite`、`libXdamage`、`libXrandr`、`libxkbcommon`、`mesa-libgbm`、`pango`；按实际报错补件。中文截图建议主机安装中文字体；DOM 断言通过不证明字体已齐全。

如果系统低于 glibc 2.28、不是 x86_64 或 Python 小版本不匹配，工具会在安装前拒绝。不要为运行浏览器替换系统 glibc。

## 资源、来源与更新

[清单](browser-linux-x86_64/manifest.json) 记录版本、来源 URL、原始发行包 SHA-256、分片整体 SHA-256 和全部 wheel/lock/分片的独立 SHA-256。普通 `git pull` 即获得完整资源，不使用 Git LFS、子模块或安装时下载。

- Playwright 1.64.0；greenlet 3.2.5（分别提供 CPython 3.11/3.12）；pyee 13.0.1；typing_extensions 4.16.0。均从 PyPI 下载 wheel，未改包内文件；许可信息保留在 wheel 的 dist-info 中。
- Google Chrome 156.0.8078.47，来源为 Google 官方 Linux 发行包；归档直接取其 `data.tar.xz` 并分片，不改浏览器文件。安装只提取其 `opt/google/chrome` 内容，忽略 cron、系统 symlink、包管理配置；保留运行时自带的许可文件。Chrome 条款及开源许可可在浏览器 `chrome://terms` / `chrome://credits` 查阅。
- Playwright 官方下载 CDN 在打包环境被网络策略拒绝，因此本包使用 Playwright 支持的 `executable_path` 接口，不依赖 `playwright install`。不会将该下载失败伪装成内网 PyPI 问题。
- 复验/更新时应先在联网构建机下载目标平台 wheel 和官方发行包，记录完整版本、来源与摘要，替换独立版本的资源并重建两个 lock 和 manifest，按计划重跑离线安装、启动及交互测试。不要只换分片不更新整体指纹。

为避免改变已有 venv，第一次可先在其可回退副本验证；锁文件会将 UI 依赖固定到上面版本。移除独立缓存不会修改系统 Chrome 或业务基线。
