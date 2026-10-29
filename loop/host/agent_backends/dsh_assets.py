"""S2 共享基础：attempt 目录布局与资产物化（SPEC-REV-14 B1/B2/B3/B8）。

为什么需要它：bwrap 包裹把宿主 home 遮蔽（P0 实测：`AGENTS.md` 不可读、`~/.dsh` 为空），
因此**任何** patch overlay、插件源码、自检侧信道都必须落在 attempt 目录内——仓内路径在包裹内不可见。

边界：
- 只做文件搬运、patch 文本生成、home 最小化检查；**不含业务判据**、不启进程、不判完成。
- 唯一实现：`dsh.py`（候选收口）与 `dsh_selfcheck.py`（启动自检）都经本模块拿 assets，
  不各自拼路径、不各自写 patch 语法（避免第二套口径，红线 8）。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml

#: 仓内插件源码目录（本模块唯一引用点；调用方只给文件名）
PLUGIN_SOURCE_DIR = Path(__file__).resolve().with_name("dsh_plugin")

#: 插件落自检报告的侧信道目录（attempt 目录内；**只有自检报告**，没有别的产物）
SELFCHECK_DIR_ENV = "DSH_SELFCHECK_DIR"
#: 每次 attempt 的随机 nonce：插件必须把它写进自检报告，Host 逐字比对
#: （否则复用 attempt root 时，"上一次"的快照会被当成本次准入 —— 独立复核 P1-1 复现过）
SELFCHECK_NONCE_ENV = "DSH_SELFCHECK_NONCE"
#: 本次 attempt 标识：报告里回显，Host 做身份 join（同一次 attempt 的事实）
ATTEMPT_KEY_ENV = "DSH_ATTEMPT_KEY"

#: 宿主侧凭据/设置件：**不得**出现在 attempt home（DS-09；B3 禁止复制宿主 settings）。
#: **语义不改**（REV-14 §4-B3 / §9.1 不变量 1）：三个名字仍**全部**列在这里；S8b 没有把任何名字
#: 移出去，只新增"逐条判来源"的判据（`home_provenance`，见 REV-14 §9）。
FORBIDDEN_HOME_ENTRIES = ("settings.yaml", ".credentials.yaml", ".credentials")

#: DS-09 来源四档（REV-14 §9.1）。**只有 `dsh_generated` 是放行档**，其余三档一律拒绝。
HOME_SOURCE_HOST_SETTINGS_COPY = "host_settings_copy"
HOME_SOURCE_HOST_CREDENTIAL_VALUE = "host_credential_value"
HOME_SOURCE_DSH_GENERATED = "dsh_generated"
HOME_SOURCE_UNKNOWN = "unknown"
HOME_SOURCES = (HOME_SOURCE_HOST_SETTINGS_COPY, HOME_SOURCE_HOST_CREDENTIAL_VALUE,
                HOME_SOURCE_DSH_GENERATED, HOME_SOURCE_UNKNOWN)

#: `dsh` 自己为本次实例生成的 `.credentials.yaml` 的**键路径登记**（"形态"判据）。
#: 真机实测（2026-10-29，`dsh` 0.2.1-rc.2，`loop/.logs/s7c/home{,2,3}/.credentials.yaml` 三份同形，
#: 每份 161 B / 0600）：
#: `version: 1` + `records.client-connection/browser-session.{kind: grant, payload.{version, secret}}`。
#: **值**不入常量、不入证据（零回显）；只有键路径。换 dsh 版本多/少键 ⇒ 形态判定转 `unknown`
#: 并**拒绝**（fail-closed），由 `tests/test_ds09_home_provenance.py` 的"常量漂移"用例钉住：
#: 改常量而不重新录制实测形态 ⇒ 用例红。
DSH_GENERATED_CREDENTIAL_KEYS = frozenset({
    "version",
    "records",
    "records.client-connection/browser-session",
    "records.client-connection/browser-session.kind",
    "records.client-connection/browser-session.payload",
    "records.client-connection/browser-session.payload.version",
    "records.client-connection/browser-session.payload.secret",
})
#: 自生成形态里**必须存在**的键路径（缺任一 ⇒ 没有判据可用 ⇒ `unknown` ⇒ 拒绝）。
DSH_GENERATED_CREDENTIAL_REQUIRED = frozenset({
    "version",
    "records.client-connection/browser-session.kind",
    "records.client-connection/browser-session.payload.secret",
})
#: 放行档的 `basis` 文案里点名的记录路径（可审计"按哪条形态放行"）
DSH_GENERATED_RECORD_PATH = "records.client-connection/browser-session"

#: attempt 隔离工作区在 run 内的固定位置（REV-13 §5.4 / S5-C2a）。
#: **不放进 `agent_calls/**`**：那是封存记录目录（`verify_attempt` 只认 request/result 两种文件名，
#: 多出目录会让"记录目录"混进执行现场）。
WORKSPACE_DIRNAME = "agent_workspaces"

#: attempt 内**生成式** provider overlay 的文件名（Host 生成，不落静态仓文件：避免"仓里再抄一份
#: 内部端点"与漂移；密钥值**永不**进该文件，只写环境变量名）。
PROVIDER_PATCH_FILE = "01-provider.yml"
#: dsh 的 provider 插件 id / 默认模型插件 id（与锁定版本 `--dump-config` 同形；换版本要重核）
PROVIDER_PLUGIN_ID = "llm-pi-ai"
DEFAULT_MODEL_PLUGIN_ID = "agent-default-model"
#: 生成 overlay 里使用的 provider 名（只是标签；不承载凭据，凭据靠 `apiKeyEnv` 的环境变量名）
PROVIDER_NAME = "loop"
#: `model_provider` 的 api family → dsh provider 的 `api` 取值。
#: **`openai-responses` 已实测**（P0/P2/P7）；`chat*` 映射为未验证（用前需真机确认，别默认它能跑）。
FAMILY_TO_DSH_API = {"openai-responses": "openai-responses", "responses": "openai-responses",
                     "chat": "chat", "chat/completions": "chat", "completions": "chat"}

#: 允许进入 attempt `input/` 的**只读材料白名单**（Host 显式常量；不许整目录拷贝）。
#: 新增一项是评审动作（它决定模型能读到哪份 run 产物）：不许 `kb/**`、`ENV_ROOT`、绝对路径、
#: 符号链接或"目录里最新那个"。缺失的材料不补、不猜（真需要补读走工具，见 S5 的冷材料缺口）。
INPUT_MATERIALS = ("n1_manifest_new.json", "n2_diff.json", "n2_diff.md",
                   "n3_digest.md", "n5_impact.json", "n5_impact.md",
                   "doc_entries.jsonl", "case_states.json")


#: attempt `input/` 里"外部只读源件"的子目录（N6 目标用例源件等）：与 run 产物白名单分开，
#: 便于审计"哪些是 Host 从环境只读拷进来的"（`input/TESTLIB/<case>.sv`）。
SOURCE_SUBDIR = "TESTLIB"


#: N6 的**派生材料名**（S7a）。为什么不给 `n5_impact.json` 全文：S5/S6 真机实测（345638 B）
#: 诱导模型反复解析影响面、300 s 没进入写候选；而 N6 真正需要的事实已由 `build_n6_targets`
#: 有界签发进任务文本（excerpts / rtl_change / api_semantics / doc_bitdef）。
N6_SUMMARY_NAME = "n6_impact_summary.json"
#: 派生摘要的 schema 标签（与 Host 业务 schema 无关，仅用于识别"这是派生物"）。
N6_SUMMARY_SCHEMA = "loop/n6_impact_summary"
#: 派生物 → 源件名（Host 从 run 产物派生进 `input/`，不塞原文）。
#: 新增一项 = 评审动作：它决定模型看到哪份派生事实，且必须在记录里留"派生自哪个源件 + md5"。
DERIVED_MATERIALS: dict[str, str] = {N6_SUMMARY_NAME: "n5_impact.json"}

#: 每节点进 `input/` 的材料名（**单一来源**；`dsh.prepare_attempt` 只调本函数，不各自拼）。
#: 未列节点 ⇒ `INPUT_MATERIALS`（默认白名单，行为不变）。
NODE_MATERIALS: dict[str, tuple[str, ...]] = {}


def materials_for(node: str) -> tuple[str, ...]:
    """一次 attempt 该进 `input/` 的材料名（唯一实现）。"""
    key = str(node or "").strip()
    return NODE_MATERIALS.get(key, INPUT_MATERIALS)


def derive_material(name: str, payload: bytes) -> bytes:
    """按 `DERIVED_MATERIALS` 把源件字节**投影**成派生物字节（纯函数，确定性输出）。

    判据：
    1. 只接受登记过的派生物名（未登记 ⇒ `AssetError`，不猜）；
    2. 源件必须是 JSON 对象（否则 `AssetError`：不生成空摘要糊过去）；
    3. 只投影 `build_n6_targets` 实际消费的字段（case/file/line/entry_id/segment/offset/
       rtl_files）+ 计数，**不复制原文 hunk、不复制文档正文、不做任何判定**（不是第二套判据）。
    输出按键排序 + 固定缩进 ⇒ 同源件同 md5（证据可复算）。
    """
    if name != N6_SUMMARY_NAME:
        raise AssetError("未登记的派生物名：%r（只认 %r）"
                        % (name, sorted(DERIVED_MATERIALS)))
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssetError("%s 的源件不是 UTF-8 JSON：%s" % (name, exc)) from None
    if not isinstance(document, dict):
        raise AssetError("%s 的源件不是 JSON 对象（实际 %s）"
                         % (name, type(document).__name__))
    items = [item for item in (document.get("must_change") or []) if isinstance(item, dict)]
    cases: list[dict[str, object]] = []
    for item in items:
        case = str(item.get("case") or "").strip()
        if not case:
            continue
        projected: dict[str, object] = {"case": case,
                                        "file": str(item.get("file") or ""),
                                        "line": item.get("line"),
                                        "entry_id": str(item.get("entry_id") or ""),
                                        "segment": str(item.get("segment") or ""),
                                        "offset": str(item.get("offset") or ""),
                                        "rtl_files": [str(x) for x in (item.get("rtl_files") or [])]}
        cases.append(projected)
    count = document.get("must_change_count")
    summary = {"schema": N6_SUMMARY_SCHEMA, "version": 1,
               "source": DERIVED_MATERIALS[name],
               "must_change_count": count if isinstance(count, int) else len(cases),
               "cases": cases}
    return (json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode("utf-8")


NODE_MATERIALS["N6"] = (N6_SUMMARY_NAME,)
N6_MATERIALS: tuple[str, ...] = NODE_MATERIALS["N6"]


def check_layout(layout: AttemptLayout) -> None:
    """布局不变式：候选落点**必须在工作区内**（dsh `workspace-write` 边界 = cwd）。

    越界/符号链接 ⇒ `AssetError`（显式失败，不回退）。这条是不变式而不是"建议"：
    S6 第 3 次真机证明，候选在兄弟目录时 dsh 应用层会要求 `danger-full-access` 审批，
    headless 无审批人 ⇒ 候选写不出去、整轮超时。
    """
    work = Path(layout.work)
    candidate = Path(layout.candidate)
    if candidate.is_symlink() or work.is_symlink():
        raise AssetError("attempt 布局含符号链接：work=%s candidate=%s" % (work, candidate))
    if not candidate.is_relative_to(work) or candidate == work:
        raise AssetError("candidate 必须是工作区内的子目录（实际 %s，work=%s）"
                         % (candidate, work))


def workspace_root(run_dir: Path | str, node: str, sequence: int) -> Path:
    """一次 attempt 的隔离工作区根：`<run>/agent_workspaces/<node>/attempt-00000N/`。

    形状固定（`work`/`dsh-home`/`candidate`/`input` 由 `AttemptLayout` 给出）：
    `candidate` 是本片之外（S6）唯一允许模型写业务产物的落点，本片不往里写任何东西。
    """
    return Path(run_dir) / WORKSPACE_DIRNAME / node / ("attempt-%06d" % int(sequence))

#: **无 attempt 归属**的保守默认档（B3：`mode` + `defaultPreset` 双钉；单钉会被用户层覆盖，P3 实测）。
#: 为什么仍留 read-only：它是"不知道该不该写"时的失败安全默认，也是既有用例钉住的可观察行为；
#: **生产 attempt 用 `ATTEMPT_PINS`（workspace-write）**，不是本常量。
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
    #: 候选落点（attempt 内唯一允许模型写业务产物的目录；S6 导入只读它）。
    #: **必须在工作区内**（`work/candidate`）：dsh 的应用层 `workspace-write` 边界 = 工作区（cwd），
    #: 兄弟目录写要 `danger-full-access` 升级审批；headless 无审批人 ⇒ `outcome="unavailable"`
    #: ⇒ 模型写候选被拒（S6 第 3 次真机决定性证据，2026-10-29）。只改 OS 绑定不够。
    candidate: Path
    input_dir: Path       # 只读材料（Host 按白名单拷入；包裹内以 `--ro-bind` 只读可见）

    @classmethod
    def under(cls, root: Path | str) -> "AttemptLayout":
        root = Path(root)
        work = root / "work"
        return cls(root=root, work=work, home=root / "dsh-home",
                   plugin_dir=root / "plugin", patch_dir=root / "patches",
                   selfcheck_dir=root / "selfcheck", candidate=work / "candidate",
                   input_dir=root / "input")

    def prepare(self) -> None:
        for path in (self.root, self.work, self.home, self.plugin_dir,
                     self.patch_dir, self.selfcheck_dir, self.candidate, self.input_dir):
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


#: **生产 attempt 的钉死档位**（人工裁决 2026-10-28：写权只在每 attempt 隔离工作区内）。
#: 与 `Pins()` 的 read-only 默认分开：改默认会放大暴露面、也会把既有可观察行为悄悄换掉；
#: attempt 路径显式用本常量，并由启动自检把**实际回显**逐字比对回它（不符即拒，DS-09）。
ATTEMPT_SANDBOX_MODE = "workspace-write"
ATTEMPT_PRESET = "workspace-write"
ATTEMPT_PINS = Pins(sandbox_mode=ATTEMPT_SANDBOX_MODE, default_preset=ATTEMPT_PRESET)


def stage_sources(layout: AttemptLayout, sources: tuple[tuple[Path, str], ...], *,
                  subdir: str = SOURCE_SUBDIR) -> tuple[dict[str, Any], ...]:
    """把**显式声明的外部只读源件**拷进 attempt `input/<subdir>/`（N6 目标用例源件用）。

    判据（显式失败，不降级）：
    1. 只接受 `(root, 相对路径)` 对：**绝对路径 / `..` / 空** 一律拒；
    2. 解析后必须在 `root` 之内（不吃符号链接逃逸，源件本身是 symlink 也拒）；
    3. **不整目录**：调用方逐个声明（N6 只声明 `targets[].file`）；
    4. 每件算 md5+size，随 attempt 记录封存（便于 DS-04/DS-06 复核"模型读到的是什么版本"）。
    """
    sub = str(subdir or "").strip()
    if not sub or sub.startswith("/") or ".." in Path(sub).parts:
        raise AssetError("input 源件子目录非法：%r" % (subdir,))
    target_dir = layout.input_dir / sub
    target_dir.mkdir(parents=True, exist_ok=True)
    staged: list[dict[str, Any]] = []
    for root, relative in sources:
        rel = str(relative or "").strip()
        if not rel or rel.startswith("/") or ".." in Path(rel).parts:
            raise AssetError("input 源件路径非法（只接受 root 内相对路径）：%r" % (relative,))
        base = Path(root)
        if not base.is_dir():
            raise AssetError("input 源件根不存在或不是目录：%s" % base)
        source = base / rel
        if source.is_symlink():
            raise AssetError("input 源件是符号链接（拒绝逃逸）：%s" % source)
        if not source.is_file():
            raise AssetError("input 源件不存在：%s" % source)
        try:
            resolved = source.resolve()
            if resolved != (base / rel).resolve() or base.resolve() not in resolved.parents:
                raise AssetError("input 源件越界：%s" % source)
            payload = source.read_bytes()
        except OSError as exc:
            raise AssetError("input 源件不可读（%s）：%s" % (source, exc)) from None
        destination = target_dir / Path(rel).name
        destination.write_bytes(payload)
        staged.append({"name": "%s/%s" % (sub, Path(rel).name),
                       "source": str(source), "present": True,
                       "md5": hashlib.md5(payload).hexdigest(), "size": len(payload)})
    return tuple(staged)


@dataclass(frozen=True)
class ProviderOverlay:
    """一次 attempt 的 **provider overlay**（Host 生成；内容可审计，**不含密钥值**）。"""

    text: str
    filename: str = PROVIDER_PATCH_FILE


def provider_overlay(*, family: str | None, base_url: str | None, model: str | None,
                     api_key_env: str | None,
                     model_options: dict[str, object] | None = None) -> ProviderOverlay:
    """由 `host.model_provider` 已解析的配置**生成** dsh 的 provider overlay。

    为什么生成而不是静态文件：SETTINGS 纪律明确反对"仓里再抄一份内部端点"（迟早与宿主配置
    漂移）；生成式还能保证只写**环境变量名**、不写密钥值。
    输入只有四样：api family / baseURL / model / apiKeyEnv 名；任一缺失或不认识的 family
    ⇒ `AssetError`（显式失败，不猜、不生成半个 overlay）。
    """
    api = FAMILY_TO_DSH_API.get(str(family or "").strip().lower())
    if api is None:
        raise AssetError("生成 provider overlay 失败：不认识的 api family %r" % (family,))
    if not base_url or not str(base_url).strip():
        raise AssetError("生成 provider overlay 失败：缺 baseURL（model_provider 未解析出端点）")
    if not model or not str(model).strip():
        raise AssetError("生成 provider overlay 失败：缺 model 名")
    if not api_key_env or not str(api_key_env).strip():
        raise AssetError("生成 provider overlay 失败：缺 apiKeyEnv 名")
    entry = ["- id: %s" % PROVIDER_PLUGIN_ID,
             '  name: "@deepseek-ai/dsh-%s"' % PROVIDER_PLUGIN_ID,
             "  config:", "    providers:", "      %s:" % PROVIDER_NAME,
             "        displayName: %s" % PROVIDER_NAME,
             "        apiKeyEnv: %s" % api_key_env,
             "        api: %s" % api,
             "        baseURL: %s" % base_url,
             "        models:", "          - id: %s" % model,
             "            name: %s" % model]
    for key in sorted(model_options or {}):
        entry.append("            %s: %s" % (key, (model_options or {})[key]))
    entry += ["- id: %s" % DEFAULT_MODEL_PLUGIN_ID,
              '  name: "@deepseek-ai/dsh-%s"' % DEFAULT_MODEL_PLUGIN_ID,
              "  config:", "    provider: %s" % PROVIDER_NAME, "    model: %s" % model]
    return ProviderOverlay(text="\n".join(entry) + "\n")


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


@dataclass(frozen=True)
class HomeEntry:
    """attempt home 里**一个**禁止件条目的来源判定结论（`name`/`source`/`basis`）。

    **零回显**（REV-14 §9.1 不变量 4）：本结构只承载文件名、来源枚举与"不含值"的描述，
    **不含**凭据值或 secret 片段 ⇒ 可以安全进准入记录/日志/证据。
    """

    name: str
    source: str
    basis: str

    @property
    def allowed(self) -> bool:
        """只有 `dsh_generated` 放行；其余（含 `unknown`）一律拒绝。"""
        return self.source == HOME_SOURCE_DSH_GENERATED


@dataclass(frozen=True)
class HomeProvenance:
    """DS-09 来源判定的**完整结论**（判据唯一实现；调用方只消费，不重算）。

    对齐 REV-14 §9.2：准入记录新增 `home_provenance[]` = `record()` 的形状
    `[{name, source, basis}]`；缺失 = 未判定（**不等于通过**）。
    """

    entries: tuple[HomeEntry, ...] = ()
    problems: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.problems

    def record(self) -> list[dict[str, str]]:
        """准入记录投影（不含凭据值：每个字段都不是值本身）。"""
        return [{"name": entry.name, "source": entry.source, "basis": entry.basis}
                for entry in self.entries]


def _read_entry_bytes(path: Path) -> bytes | None:
    """读一个禁止件条目的字节；目录/断链/特殊文件/读失败 ⇒ `None`（由调用方判 `unknown`）。

    符号链接**跟随读**：指向宿主凭据的链接读出来就会命中宿主凭据值 ⇒ 判 `host_credential_value`
    拒绝（比"链接一律 unknown"更强，且不引入第二档判据）。
    """
    try:
        if not path.is_file():
            return None
        return path.read_bytes()
    except OSError:
        return None


def _flatten_key_paths(document: object, prefix: str = "",
                       out: dict[str, object] | None = None) -> dict[str, object]:
    """把 YAML 文档摊平成"键路径 → 值"（形态判据的唯一摊平实现）。

    列表也摊平带下标：否则 `a: [secret1, secret2]` 这种形态能靠一个键名混过键集合判据。
    """
    result: dict[str, object] = {} if out is None else out

    def walk(node: object, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                name = "%s.%s" % (path, key) if path else str(key)
                result[name] = value
                walk(value, name)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                name = "%s[%d]" % (path, index)
                result[name] = value
                walk(value, name)

    walk(document, prefix)
    return result


def _credential_hit(raw: bytes, secrets: tuple[str, ...]) -> int | None:
    """内容里第一个命中的宿主凭据值序号（1-based）；空值不进比对集合。**只在内存比对**。"""
    for index, value in enumerate(secrets, start=1):
        if not isinstance(value, str) or not value:
            continue
        try:
            needle = value.encode("utf-8")
        except UnicodeError:                      # 不可编码的值不算判据（不猜）
            continue
        if needle in raw:
            return index
    return None


def _classify_entry(name: str, path: Path, secrets: tuple[str, ...]) -> HomeEntry:
    """单个禁止件条目的来源判定（DS-09 四档；顺序本身是契约，别重排）。"""
    if name == "settings.yaml":
        # 不变量 1：**无例外**。Host 侧不存在任何写入路径，dsh 也不生成该名 ⇒ 不看向容直接拒。
        return HomeEntry(name=name, source=HOME_SOURCE_HOST_SETTINGS_COPY,
                         basis="文件名命中 settings.yaml（Host 侧无写入路径，dsh 不生成该名）")
    raw = _read_entry_bytes(path)
    if raw is None:
        return HomeEntry(name=name, source=HOME_SOURCE_UNKNOWN,
                         basis="读不到内容（不是可读普通文件）")
    hit = _credential_hit(raw, secrets)
    if hit is not None:
        # 不变量 2：凭据值**优先于形态**（形态再像自生成也照拒）。
        return HomeEntry(name=name, source=HOME_SOURCE_HOST_CREDENTIAL_VALUE,
                         basis="宿主凭据第 %d 条命中（值不回显）" % hit)
    try:
        document = yaml.safe_load(raw.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError):
        return HomeEntry(name=name, source=HOME_SOURCE_UNKNOWN, basis="内容不是 UTF-8 YAML")
    if not isinstance(document, dict):
        return HomeEntry(name=name, source=HOME_SOURCE_UNKNOWN, basis="内容不是 mapping")
    keys = frozenset(_flatten_key_paths(document))
    extra = keys - DSH_GENERATED_CREDENTIAL_KEYS
    if extra:
        return HomeEntry(name=name, source=HOME_SOURCE_UNKNOWN,
                         basis="键集合不在 dsh 自生成登记内（多出 %d 个键路径）" % len(extra))
    missing = DSH_GENERATED_CREDENTIAL_REQUIRED - keys
    if missing:
        return HomeEntry(name=name, source=HOME_SOURCE_UNKNOWN,
                         basis="缺 dsh 自生成登记的必需键（%d 个）" % len(missing))
    return HomeEntry(name=name, source=HOME_SOURCE_DSH_GENERATED,
                     basis="键集合符合 dsh 自生成登记：%s" % DSH_GENERATED_RECORD_PATH)


def _entry_problem(entry: HomeEntry) -> str:
    """拒绝档的可读原因（**零回显**：只有文件名 / source 枚举 / 不含值的描述）。"""
    if entry.source == HOME_SOURCE_HOST_SETTINGS_COPY:
        return ("attempt home 含宿主件 %s（source=host_settings_copy：Host 侧没有任何写入路径、"
                "dsh 也不生成该名；B3 无例外）" % entry.name)
    if entry.source == HOME_SOURCE_HOST_CREDENTIAL_VALUE:
        return ("attempt home 含宿主件 %s（source=host_credential_value：%s；拒绝）"
                % (entry.name, entry.basis))
    return ("attempt home 含宿主件 %s（source=unknown：%s ⇒ fail-closed 拒绝）"
            % (entry.name, entry.basis))


def host_credential_values() -> tuple[str, ...]:
    """Host 在**内存中**持有的宿主凭据值集合（DS-09 逐条子串比对用；不落盘、不打印、不回显）。

    来源只有一处：`host/model_provider`（它已经是 provider/凭据的**唯一**解析实现）：解析出的
    `_api_key` + 其 `api_key_env` 指向的进程 env 值；再补 `LOOP_LLM_API_KEY`（同一实现的
    优先级链里它就排第一）。顺序稳定（provider 值在前）⇒ "第 N 条命中"可复算。
    """
    values: list[str] = []

    def add(value: object) -> None:
        if isinstance(value, str) and value and value not in values:
            values.append(value)

    try:
        from host import model_provider as MP

        config = MP.resolve()
    except Exception:                            # 凭据层异常不影响"判定仍要 fail-closed"
        config = None
    if config is not None:
        add(getattr(config, "_api_key", None))
        name = getattr(config, "api_key_env", None)
        if isinstance(name, str) and name:
            add(os.environ.get(name))
    add(os.environ.get("LOOP_LLM_API_KEY"))
    return tuple(values)


def home_provenance(home: Path | str, *,
                    host_secrets: tuple[str, ...] | None = None) -> HomeProvenance:
    """DS-09 来源判定（**唯一实现**，REV-14 §9；红线 8：调用方只消费结论，不重算）。

    逐条判定 attempt home 里出现的每个 `FORBIDDEN_HOME_ENTRIES` 条目（缺失是正常的，出现才判）：
    `host_settings_copy` / `host_credential_value` / `dsh_generated` / `unknown`，
    只有 `dsh_generated` 放行；`unknown` 一律拒绝（fail-closed）。

    `host_secrets` 缺省走 `host_credential_values()`（Host 内存里的凭据值集合）；
    显式传入只用于用例/诊断，生产调用方不自己拼这份集合（避免第二套凭据来源，红线 8）。
    """
    home = Path(home)
    secrets = host_credential_values() if host_secrets is None else tuple(host_secrets)
    entries: list[HomeEntry] = []
    for name in FORBIDDEN_HOME_ENTRIES:
        path = home / name
        if path.exists() or path.is_symlink():
            entries.append(_classify_entry(name, path, secrets))
    problems = tuple(_entry_problem(entry) for entry in entries if not entry.allowed)
    return HomeProvenance(entries=tuple(entries), problems=problems)


def home_problems(home: Path | str, *,
                  host_secrets: tuple[str, ...] | None = None) -> list[str]:
    """DS-09 的**兼容外壳**：只要拒绝原因（判据本身在 `home_provenance`，不在这里重算）。

    既有调用方（`materialize`、`dsh_selfcheck.verify_home`）用的就是这个形状；需要
    `{name, source, basis}` 准入记录的调用方读 `home_provenance(...).record()`。
    """
    return list(home_provenance(home, host_secrets=host_secrets).problems)


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


def pins_patch(pins: Pins) -> str:
    """钉死 patch 的**公开**文本（唯一生成实现仍是 `_pins_patch`）。

    为什么要有公开入口：准入自检要在**不起进程**的前提下判定"双钉确实是期望值"，
    它读这一份文本而不是自己拼第二套 YAML（红线 8）。
    """
    return _pins_patch(pins)


def materialize(layout: AttemptLayout, *,
                plugins: tuple[Plugin, ...] = (),
                pins: Pins | None = None,
                provider: ProviderOverlay | None = None,
                extra_patches: tuple[Path, ...] = (),
                node_modules: Path | None = None) -> Assets:
    """把 asset 落进 attempt 目录，返回 patch 的应用顺序。

    patch 顺序固定：**钉死 → 生成的 provider overlay → 外部 overlay → 插件 insert**。
    （provider overlay 必须早于外部 overlay：后者可以覆盖 provider 的模型参数，例如 P7 的
    小窗口阈值；插件 insert 最后，自检的 deferred 快照才看得到 `submit_result`。）
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

    if provider is not None:
        path = layout.patch_dir / provider.filename
        path.write_text(provider.text, encoding="utf-8")
        patch_files.append(path)

    for index, extra in enumerate(extra_patches, start=2 if provider is not None else 1):
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
