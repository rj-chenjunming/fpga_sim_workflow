"""单一 RTL 文件夹派生：根判定 / 选择性复制 / 整棵替换 / 错目录告警（Host 确定性侧）。

契约：`doc/spec/S0_ENVIRONMENT_SPEC.md` §9.2–§9.4；接口冻结见
`doc/plans/2026-10-30-rtl-folder-one-click.md` §4（T1，不得改名/改形状）。

不变式（不读实现也能判）：

1. **根判定不猜**：只看目录名（`RTL` ⇒ `RTL/` 整棵替换；`SRC` ⇒ `RTL/SRC/` 只替换子树），
   其它名字 `ValueError` 且文案列出合法值；绝不按内容/相似度猜路径（§9.2）。
2. **复制范围显式**：排除整目录与软链必须进 `copy_plan`（`excluded_roots` / `skipped`），
   `copied` 之外的条目一律不进判据 —— 被跳过**不等于**静默忽略（§9.3）。`kb/` 下只复制
   `KB_DATA_DIRS` 四个数据子目录，其余 kb 条目进 `skipped`（`reason="kb_non_data"`）。
3. **软链不复制不跟随**：`os.readlink` 只记目标文本，防指回基线；`manifest_filtered` 遇到未登记软链
   （或 plan 与磁盘矛盾的条目）必须报错。**RTL 源**里出现软链直接拒绝（§2）。
4. **只读基线**：本模块不执行基线脚本、不写 `ENV_ROOT`、不改基线权限；只对**副本**补权限以完成替换。
5. **口径唯一**：过滤后的清单只有 `manifest_filtered` 一份实现；RTL 源的复制范围只有
   `plan_rtl_source` 一份实现（`copy`/`rtl`/`baseline` 检查与 `folder_warning` 共用它），
   因此 VCS/缓存目录（`.git`/`.svn`/`.hg`/`__pycache__`）在复制、比对、告警三处同一口径。
"""
from __future__ import annotations

import hashlib
import os
import shutil
import stat
from pathlib import Path

#: 目录名 → 仓库相对前缀（§9.2：`RTL` 整棵替换；`SRC` 只替换 `RTL/SRC/` 子树）。
RTL_NAME_PREFIX = {"RTL": "RTL", "SRC": "RTL/SRC"}

#: 整目录排除（相对基线根；`kb/runs` 是历史运行沙箱，动辄 GB 级且与派生无关）。
EXCLUDED_ROOTS = ("kb/runs", "loop", "SIMLIB_RUN", ".git", "COV", "WAVE", "LOG", "RUNS")

#: 任意深度上按目录名跳过的缓存/版本库目录（`kb/tools` 冻结目录不得写 `__pycache__`，这里也不收）。
SKIP_DIR_NAMES = ("__pycache__", ".git", ".svn", ".hg")

#: 随副本复制的 **kb 数据子集**（§9.3 原文的"数据子集"）：`kb/` 下其余条目（`kb/tools`、`kb/schema`、
#: `kb/README.md`、`kb/FIXTURE_IDENTITY.md`…）一律不复制并**落账**。理由可核：`kb/tools`/`kb/schema`
#: 的权威在软件根（软件仓 `kb/`），副本里再放一份等于"第二套冻结副本"；`kb/runs` 另在 EXCLUDED_ROOTS。
KB_DATA_DIRS = ('kb/baselines', 'kb/index', 'kb/conflicts', 'kb/adjudication')

_EXCLUDED = frozenset(EXCLUDED_ROOTS)
_SKIP_NAMES = frozenset(SKIP_DIR_NAMES)
_SYMLINK_ERROR = '未登记的符号链接：%s（软链必须显式进 copy_plan.skipped，不复制、不跟随）'
_RTL_SSYMLINK_ERROR = 'RTL 源里不允许符号链接：%s（§2：不跳过、不跟随，直接拒绝）'


# ---------------------------------------------------------------- 基础工具

def _read_regular(path: Path):
    """只读打开普通文件（`O_NOFOLLOW`：不跟随软链；特殊文件显式拒绝）。"""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    stream = os.fdopen(fd, 'rb')
    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
        stream.close()
        raise ValueError(f'拒绝特殊文件：{path}')
    return stream


def _md5(path: Path) -> str:
    with _read_regular(path) as stream:
        return hashlib.file_digest(stream, 'md5').hexdigest()


def _copy_regular(src, dst):
    with _read_regular(Path(src)) as source, open(dst, 'xb') as target:
        shutil.copyfileobj(source, target)
    shutil.copystat(src, dst, follow_symlinks=False)
    return dst


def _require_entity_dir(path: Path, label: str) -> Path:
    path = Path(path)
    if path.is_symlink():
        raise ValueError(f'{label}不允许符号链接：{path}')
    if not path.is_dir():
        raise ValueError(f'{label}必须是目录：{path}')
    return path


def _check_prefix(prefix: str) -> str:
    if prefix not in RTL_NAME_PREFIX.values():
        raise ValueError('非法 RTL 前缀：%r（合法值：%s）'
                         % (prefix, '、'.join(sorted(set(RTL_NAME_PREFIX.values())))))
    return prefix


def _grant(path: Path) -> None:
    """只对**副本**目录补 owner 读写执行权限（基线权限不改）。"""
    mode = stat.S_IMODE(path.stat().st_mode)
    path.chmod(mode | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)


def _grant_tree(path: Path) -> None:
    _grant(path)
    for child in path.rglob('*'):
        if child.is_symlink():
            raise ValueError(f'待替换的旧子目录里出现符号链接：{child}')
        if child.is_dir():
            _grant(child)


# ---------------------------------------------------------------- 根判定（§9.2）

def classify_rtl_source(path: Path) -> dict:
    """按**目录名**判定 RTL 根：`RTL` ⇒ 整棵 `RTL/`；`SRC` ⇒ 只换 `RTL/SRC/`。不猜。"""
    source = _require_entity_dir(Path(path), 'RTL 源')
    kind = source.name
    if kind not in RTL_NAME_PREFIX:
        raise ValueError('RTL 源目录名必须为 %s 之一（收到 %r）：%s'
                         % ('、'.join(RTL_NAME_PREFIX), kind, source))
    return {'kind': kind, 'prefix': RTL_NAME_PREFIX[kind], 'basename': kind}


# ---------------------------------------------------------------- 选择性复制（§9.3）

def plan_copy(baseline: Path) -> dict:
    """规划"哪些条目进副本、哪些显式跳过"（只读基线，不跟随软链）。

    - `copied`：要复制的条目（**目录与文件都列**，空目录因此不会丢）；
    - `excluded_roots`：实际存在且被整目录排除的相对路径（按 `EXCLUDED_ROOTS`）；
    - `skipped`：`{rel, reason, target}`；`reason ∈ {"symlink", "skip_dir_name", "special",
      "kb_non_data"}`（软链的 `target` 是 `os.readlink` 文本，不解析、不跟随）。

    `kb/` 下**只有** `KB_DATA_DIRS` 四个数据子目录随副本复制（§9.3），其余 kb 条目一律
    不复制并进 `skipped`（reason=`kb_non_data`），保证"跳过规则显式落账、不静默"。
    """
    root = _require_entity_dir(Path(baseline), '基线')
    copied: list[str] = []
    excluded: list[str] = []
    skipped: list[dict] = []

    def walk(directory: Path, prefix: str) -> None:
        for child in sorted(directory.iterdir(), key=lambda item: item.name):
            rel = f'{prefix}/{child.name}' if prefix else child.name
            if rel in _EXCLUDED:                      # 整目录/整条路径排除（含 .git、kb/runs）
                excluded.append(rel)
                continue
            if child.is_symlink():                    # 软链：不复制、不跟随，只记目标
                skipped.append({'rel': rel, 'reason': 'symlink', 'target': os.readlink(child)})
                continue
            if rel.startswith('kb/') and not any(
                    rel == item or rel.startswith(item + '/') for item in KB_DATA_DIRS):
                # kb 只认四个数据子目录；其权威在软件根的那批（tools/schema/README…）不进副本
                skipped.append({'rel': rel, 'reason': 'kb_non_data', 'target': None})
                continue
            if child.is_dir():
                if child.name in _SKIP_NAMES:
                    skipped.append({'rel': rel, 'reason': 'skip_dir_name', 'target': None})
                    continue
                copied.append(rel)
                walk(child, rel)
            elif child.is_file():
                copied.append(rel)
            else:                                     # fifo / socket / 设备
                skipped.append({'rel': rel, 'reason': 'special', 'target': None})

    walk(root, '')
    return {'copied': copied,
            'excluded_roots': sorted(excluded),
            'skipped': skipped}


def manifest_filtered(root: Path, plan: dict) -> dict:
    """按 `copy_plan` 过滤后的清单（目录也入清单；文件记 md5）。

    只走 `copied`；同时校验 plan 与磁盘互不矛盾：`copied` 里出现的软链、缺失条目、
    以及既没登记复制也没登记跳过的条目 —— 一律显式报错（否则等于静默忽略）。
    """
    root = _require_entity_dir(Path(root), '清单根')
    copied = [str(rel) for rel in plan.get('copied') or []]
    skipped = {str(row['rel']) for row in plan.get('skipped') or []}
    excluded = [str(rel) for rel in plan.get('excluded_roots') or []]
    copied_set = set(copied)
    result: dict = {}
    for rel in copied:
        path = root / rel
        if path.is_symlink():
            raise ValueError(_SYMLINK_ERROR % rel)
        if path.is_dir():
            result[rel] = {'kind': 'directory'}
        elif path.is_file():
            result[rel] = {'kind': 'file', 'md5': _md5(path)}
        else:
            raise ValueError(f'清单条目缺失或不是普通文件/目录：{rel}')
    # 反向核对：copied 目录下的每个子项都必须已登记（copied / skipped / excluded_roots）
    for parent in ['', *[rel for rel in copied if result[rel]['kind'] == 'directory']]:
        directory = root / parent if parent else root
        for child in directory.iterdir():
            rel = f'{parent}/{child.name}' if parent else child.name
            if rel in copied_set or rel in skipped:
                continue
            if any(rel == item or rel.startswith(item + '/') for item in excluded):
                continue
            if child.is_symlink():
                raise ValueError(_SYMLINK_ERROR % rel)
            raise ValueError(f'copy_plan 与目录不一致（未登记条目）：{rel}')
    return result


def copy_selected(baseline: Path, work: Path, plan: dict) -> dict:
    """按 plan 把一个**空的**副本目录填满（`xb` 打开：绝不覆盖已有文件）。"""
    source = _require_entity_dir(Path(baseline), '基线')
    target_dir = Path(work)
    if target_dir.is_symlink() or not target_dir.is_dir():
        raise ValueError(f'副本目标必须是已创建的目录：{target_dir}')
    if any(target_dir.iterdir()):
        raise ValueError(f'副本目标不是空目录：{target_dir}')
    copied = 0
    for rel in plan.get('copied') or []:
        src, dst = source / rel, target_dir / rel
        if src.is_symlink():
            raise ValueError(_SYMLINK_ERROR % rel)
        if src.is_dir():
            dst.mkdir()
        elif src.is_file():
            _copy_regular(src, dst)
        else:
            raise ValueError(f'清单条目缺失或不是普通文件/目录：{rel}')
        copied += 1
    return {'copied': copied, 'skipped': len(plan.get('skipped') or [])}


# ---------------------------------------------------------------- RTL 替换（§9.4）

def plan_rtl_source(rtl_source: Path) -> dict:
    """规划从 **RTL 源**复制哪些条目（与副本同一口径：VCS/缓存目录跳过并落账）。

    - 软链一律**拒绝**（`ValueError`；§2「拒绝符号链接」，不静默跳过、不跟随）；
    - `SKIP_DIR_NAMES`（`.git`/`.svn`/`.hg`/`__pycache__`）目录跳过并进 `skipped`
      （真实环境根与用户 RTL 文件夹大概率是 git 仓库：整包复制 `.git` 既污染副本又带历史体积）；
    - 特殊文件（fifo/socket/设备）同样拒绝（§2）；
    - `copied`：目录与文件都列（空目录因此不会丢）。
    返回 `{"copied": [rel...], "skipped": [{rel, reason, target}...]}`；`reason="skip_dir_name"`。
    """
    root = _require_entity_dir(Path(rtl_source), 'RTL 源')
    copied: list[str] = []
    skipped: list[dict] = []

    def walk(directory: Path, prefix: str) -> None:
        for child in sorted(directory.iterdir(), key=lambda item: item.name):
            rel = f'{prefix}/{child.name}' if prefix else child.name
            if child.is_symlink():
                raise ValueError(_RTL_SSYMLINK_ERROR % rel)
            if child.is_dir():
                if child.name in _SKIP_NAMES:
                    skipped.append({'rel': rel, 'reason': 'skip_dir_name', 'target': None})
                    continue
                copied.append(rel)
                walk(child, rel)
            elif child.is_file():
                copied.append(rel)
            else:
                raise ValueError(f'RTL 源里不允许特殊文件：{rel}')

    walk(root, '')
    return {'copied': copied, 'skipped': skipped}


def replace_rtl(work: Path, rtl_source: Path, prefix: str) -> dict:
    """整棵替换副本里的 `prefix` 子树：先删干净再放入新 RTL（旧文件零残留）。

    - `prefix="RTL"` ⇒ 删除 `work/RTL/` 后整棵放入（§9.4 第一种）；
    - `prefix="RTL/SRC"` ⇒ 只删除 `work/RTL/SRC/` 后放入（§9.4 第二种）；
    - 放入内容按 `plan_rtl_source()` 过滤：VCS/缓存目录不复制（与 copy 同一口径）；
    - 返回 `{"prefix", "replaced": [rel...]}`，`replaced` 是**被删除的旧条目**
      （相对 `work`，含目录；用来复核"旧 RTL 零残留"）。
    - 只对副本补 owner 权限；基线权限不改（§2）。
    """
    work_dir = _require_entity_dir(Path(work), '副本')
    source = _require_entity_dir(Path(rtl_source), 'RTL 源')
    prefix = _check_prefix(prefix)
    plan = plan_rtl_source(source)                    # 口径唯一：过滤 + 软链/特殊文件拒绝
    target = work_dir / prefix
    parent = target.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ValueError(f'副本缺少可写的父目录：{parent}')
    _grant(parent)                                    # 删除/新建子项需要父目录可写
    replaced: list[str] = []
    if target.is_symlink():
        raise ValueError(f'待替换目标不允许符号链接：{target}')
    if target.exists():
        _grant_tree(target)
        for child in sorted(target.rglob('*')):
            replaced.append(f'{prefix}/{child.relative_to(target).as_posix()}')
        shutil.rmtree(target)
    target.mkdir()
    for rel in plan['copied']:
        src, dst = source / rel, target / rel
        if src.is_dir():
            dst.mkdir()
        elif src.is_file():
            _copy_regular(src, dst)
        else:                                         # plan 之后源发生变化
            raise ValueError(f'清单条目缺失或不是普通文件/目录：{rel}')
    return {'prefix': prefix, 'replaced': sorted(replaced)}


# ---------------------------------------------------------------- 错目录只告警（§9.4）

def folder_warning(baseline: Path, plan: dict, rtl_source: Path, prefix: str) -> dict:
    """错目录**只告警不拦截**：同前缀文件集的重合/新增/删除与相似度（§9.4）。

    口径（唯一）：基线侧用 `manifest_filtered(baseline, plan)`；新目录侧用
    `plan_rtl_source()` + `manifest_filtered()` 的**同一份**过滤口径（VCS/缓存目录不参与统计）。
    `same` = 同名且 md5 相同的文件数；`added` = 只在新目录出现的文件名数；
    `removed` = 只在基线出现的文件名数；`ratio = same / |基线 ∪ 新目录|`（保留 4 位小数）。
    内容改了但名字还在的文件既不算 same 也不算 added/removed —— 它只会拉低 ratio。
    """
    baseline_dir = _require_entity_dir(Path(baseline), '基线')
    prefix = _check_prefix(prefix)
    snapshot = manifest_filtered(baseline_dir, plan)
    base = {key[len(prefix) + 1:]: row['md5'] for key, row in snapshot.items()
            if row['kind'] == 'file' and key.startswith(prefix + '/')}
    source_dir = Path(rtl_source)
    source = {key: row['md5']
              for key, row in manifest_filtered(source_dir, plan_rtl_source(source_dir)).items()
              if row['kind'] == 'file'}
    same = sum(1 for rel in base.keys() & source.keys() if base[rel] == source[rel])
    union = len(base.keys() | source.keys())
    return {'same': same,
            'added': len(source.keys() - base.keys()),
            'removed': len(base.keys() - source.keys()),
            'ratio': round(same / union, 4) if union else 0.0}
