"""S2 共享基础：attempt 目录布局与资产物化（SPEC-REV-14 B1/B2/B3/B8）。

为什么需要它：bwrap 包裹把宿主 home 遮蔽（P0 实测：`AGENTS.md` 不可读、`~/.dsh` 为空），
因此**任何** patch overlay、插件源码、自检侧信道都必须落在 attempt 目录内——仓内路径在包裹内不可见。

边界：
- 只做文件搬运、patch 文本生成、home 最小化检查；**不含业务判据**、不启进程、不判完成。
- 唯一实现：`dsh.py`（候选收口）与 `dsh_selfcheck.py`（启动自检）都经本模块拿 assets，
  不各自拼路径、不各自写 patch 语法（避免第二套口径，红线 8）。
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

#: 仓内插件源码目录（本模块唯一引用点；调用方只给文件名）
PLUGIN_SOURCE_DIR = Path(__file__).resolve().with_name("dsh_plugin")

#: 插件落自检报告的侧信道目录（attempt 目录内；**只有自检报告**，没有别的产物）
SELFCHECK_DIR_ENV = "DSH_SELFCHECK_DIR"
#: 每次 attempt 的随机 nonce：插件必须把它写进自检报告，Host 逐字比对
#: （否则复用 attempt root 时，"上一次"的快照会被当成本次准入 —— 独立复核 P1-1 复现过）
SELFCHECK_NONCE_ENV = "DSH_SELFCHECK_NONCE"
#: 本次 attempt 标识：报告里回显，Host 做身份 join（同一次 attempt 的事实）
ATTEMPT_KEY_ENV = "DSH_ATTEMPT_KEY"

#: 宿主侧凭据/设置件：**不得**出现在 attempt home（DS-09；B3 禁止复制宿主 settings）
FORBIDDEN_HOME_ENTRIES = ("settings.yaml", ".credentials.yaml", ".credentials")

#: 权限档钉死值（B3：`mode` + `defaultPreset` 双钉；单钉会被用户层覆盖，P3 实测）
DEFAULT_SANDBOX_MODE = "read-only"
DEFAULT_PRESET = "read-only"

#: `permission-presets` 的**完整**档位表。
#: 为什么必须整表写：`--patch` 的 `config` 是**整块替换**（不是深合并），只写 `defaultPreset`
#: 会清空 `presets`，`permission` 条目直接激活失败（实测原文
#: `permission: unknown preset "read-only" (known: workspace-write, danger-full-access)`），
#: 于是 `ctx.get('permissionPresets')` 恒为空 ⇒ B3 自检永远拿不到回显。
PRESET_TABLE = {
    "read-only": ("read-only", "ask"),
    "workspace-write": ("workspace-write", "ask"),
    "danger-full-access": ("danger-full-access", "never"),
}


class AssetError(RuntimeError):
    """资产物化失败（缺插件源码 / attempt home 带宿主件）。调用方必须显式失败。"""


@dataclass(frozen=True)
class AttemptLayout:
    """一个 attempt 的目录布局；所有可写路径都在 `root` 之下。"""

    root: Path
    work: Path            # cwd（包裹内唯一 bind 回来的工作副本之一）
    home: Path            # DSH_HOME（最小 home；不携带宿主 settings/凭据）
    plugin_dir: Path      # 插件源码副本
    patch_dir: Path       # 生成的 patch overlay
    selfcheck_dir: Path   # 侧信道（自检报告等）

    @classmethod
    def under(cls, root: Path | str) -> "AttemptLayout":
        root = Path(root)
        return cls(root=root, work=root / "work", home=root / "dsh-home",
                   plugin_dir=root / "plugin", patch_dir=root / "patches",
                   selfcheck_dir=root / "selfcheck")

    def prepare(self) -> None:
        for path in (self.root, self.work, self.home, self.plugin_dir,
                     self.patch_dir, self.selfcheck_dir):
            path.mkdir(parents=True, exist_ok=True)

    def selfcheck_file(self) -> Path:
        return self.selfcheck_dir / "selfcheck.json"


@dataclass(frozen=True)
class Plugin:
    """要挂进 dsh 的薄插件：`entry_id` 进 patch 的 insert，`filename` 在 `dsh_plugin/` 下。"""

    entry_id: str
    filename: str


@dataclass(frozen=True)
class Pins:
    """权限档钉死（B3/DS-09）。默认 read-only：失败安全，越界写必须被拒。"""

    sandbox_mode: str = DEFAULT_SANDBOX_MODE
    default_preset: str = DEFAULT_PRESET


@dataclass(frozen=True)
class Assets:
    """物化结果：调用方拿 patch 顺序与侧信道路径，不自己拼。"""

    layout: AttemptLayout
    plugins: tuple[tuple[str, Path], ...]
    patch_files: tuple[Path, ...]
    pins: Pins | None = None
    node_modules: Path | None = None


def node_modules_for(dsh_bin: Path | str) -> Path | None:
    """从**锁定的** dsh bin 路径推出安装的 `node_modules`（插件 import 的解析根）。

    为什么需要：插件源码被复制进 attempt 目录（包裹内仓内路径不可见），
    而插件必须 `import { defineTool } from '@deepseek-ai/dsh-tools'`；
    Node 从插件所在目录向上找 `node_modules`，attempt 目录里没有 ⇒
    `ERR_MODULE_NOT_FOUND … Cannot find package '@deepseek-ai/dsh-tools'`
    （实测：插件 `did not activate`，工具清单 25 项里没有 `submit_result`）。
    """
    for parent in Path(dsh_bin).parents:
        if parent.name == "node_modules" and parent.is_dir():
            return parent
    return None


def _link_node_modules(layout: AttemptLayout, node_modules: Path) -> Path:
    """在插件目录里放 `node_modules` 软链（不复制安装树；包裹内安装树由 `--ro-bind / /` 可见）。"""
    link = layout.plugin_dir / "node_modules"
    target = Path(node_modules)
    if link.is_symlink() and link.resolve() == target.resolve():
        return link
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(target, target_is_directory=True)
    return link


def home_problems(home: Path | str) -> list[str]:
    """DS-09：attempt home 不得含宿主 settings/凭据（缺失是正常的，存在才是问题）。"""
    home = Path(home)
    problems: list[str] = []
    for name in FORBIDDEN_HOME_ENTRIES:
        path = home / name
        if path.exists() or path.is_symlink():
            problems.append("attempt home 含宿主件 %s（禁止复制宿主 settings/凭据）" % path)
    return problems


def _insert_patch(entry_id: str, source: Path) -> str:
    """`--patch` insert 语法（与 P2 探针一致）：挂一个 ESM 插件文件。"""
    return ("- insert:\n"
            "    - id: %s\n"
            "      name: '%s'\n" % (entry_id, source))


def _pins_patch(pins: Pins) -> str:
    """B3：`sandbox-policy.mode` + `permission.defaultPreset` 双钉（单钉会被覆盖）。

    `permission` 的 `config` 必须带**完整** `presets` 表：patch 的 `config` 是整块替换，
    只写 `defaultPreset` 会让 `presets` 变空、条目激活失败（见 `PRESET_TABLE` 注释）。
    """
    lines = ["- id: sandbox-policy", "  config:", "    mode: %s" % pins.sandbox_mode,
             "- id: permission", "  config:", "    presets:"]
    for name in sorted(PRESET_TABLE):
        sandbox, approval = PRESET_TABLE[name]
        lines += ["      %s:" % name,
                  "        sandbox: %s" % sandbox,
                  "        approval: %s" % approval]
    lines.append("    defaultPreset: %s" % pins.default_preset)
    return "\n".join(lines) + "\n"


def materialize(layout: AttemptLayout, *,
                plugins: tuple[Plugin, ...] = (),
                pins: Pins | None = None,
                extra_patches: tuple[Path, ...] = (),
                node_modules: Path | None = None) -> Assets:
    """把 asset 落进 attempt 目录，返回 patch 的应用顺序。

    patch 顺序固定：**钉死 → 外部 overlay（如 provider）→ 插件 insert**。
    插件 insert 的顺序即 `plugins` 的顺序（自检插件必须排在提交插件之后，才能看到它的工具）。
    `node_modules` 给出时，在插件目录里放一条软链，让插件的 `@deepseek-ai/dsh-tools`
    import 能解析（见 `node_modules_for`）。
    """
    layout.prepare()
    problems = home_problems(layout.home)
    if problems:
        raise AssetError("；".join(problems))
    # **清掉上一次 attempt 的侧信道**：复用同一 attempt root 时，旧 `selfcheck.json` 存在
    # 会让本次自检读到"上次的事实"（独立复核 P1-1 实测：进程没写报告也被放行）。
    for stale in layout.selfcheck_dir.iterdir():
        if stale.is_file() or stale.is_symlink():
            stale.unlink()

    patch_files: list[Path] = []
    if pins is not None:
        path = layout.patch_dir / "00-pins.yml"
        path.write_text(_pins_patch(pins), encoding="utf-8")
        patch_files.append(path)

    for index, extra in enumerate(extra_patches, start=1):
        source = Path(extra)
        if not source.is_file():
            raise AssetError("外部 patch 不存在：%s" % source)
        target = layout.patch_dir / ("%02d-extra-%s" % (index, source.name))
        shutil.copyfile(source, target)
        patch_files.append(target)

    plugin_paths: list[tuple[str, Path]] = []
    for plugin in plugins:
        source = PLUGIN_SOURCE_DIR / plugin.filename
        if not source.is_file():
            raise AssetError("插件源码不存在：%s（仓内应为 %s）" % (plugin.filename, PLUGIN_SOURCE_DIR))
        target = layout.plugin_dir / plugin.filename
        shutil.copyfile(source, target)
        patch_path = layout.patch_dir / ("10-plugin-%s.yml" % plugin.entry_id)
        patch_path.write_text(_insert_patch(plugin.entry_id, target), encoding="utf-8")
        patch_files.append(patch_path)
        plugin_paths.append((plugin.entry_id, target))

    linked = _link_node_modules(layout, node_modules) if node_modules is not None else None
    return Assets(layout=layout, plugins=tuple(plugin_paths),
                  patch_files=tuple(patch_files), pins=pins, node_modules=linked)
