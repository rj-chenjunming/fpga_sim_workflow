#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_lib —— 变更影响闭环 KB 的公共库（Host 确定性侧）

设计约束
    只允许 Python 3.8 标准库（本机实测 3.8.5，**无 pyyaml**）。因此：
      * 机器可读数据一律用 **JSON**（JSON 是 YAML 1.2 的子集，可直接被 YAML 解析器读）
        与 **CSV**；这是对 spec「YAML/CSV」的**有据偏离**，理由写进 kb/README.md。
      * 不使用 3.9+ 语法（`dict |`、`list[str]`），不使用 dataclasses 的 slots。

本库提供（被 n1_*/n2_*/n5_*/gate/n16 共用，**任何脚本不得自行实现这些函数**）：
    路径   : ROOT / kb_path()
    指纹   : md5_file / sha256_file / sha256_text / canon_json / sha256_obj / canon_lines_sha256
    读写   : read_json / write_json(原子) / read_jsonl / write_jsonl / write_csv / read_csv
    校验   : load_schema / validate / SchemaError
    运行   : new_run_id / run_dir / RUN_META 名
    闸门   : GATE_IDS / gate_init / gate_set / gate_get / gate_summary

所有写盘都是**原子写**（先写 .tmp 再 os.replace），避免半截文件被下游当成有效证据。
"""

import csv
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime

# ---------------------------------------------------------------- 路径

_THIS = os.path.abspath(__file__)
# kb/tools/kb_lib.py -> kb/tools -> kb -> <软件仓根>
KB_DIR = os.path.dirname(os.path.dirname(_THIS))      # <TOOL_ROOT>/kb（**软件**资产：tools/schema/README）
TOOL_ROOT = os.path.dirname(KB_DIR)                   # 软件仓根（自锚定，不需要配置）

#: 环境插件注册表。**必须 JSON**：kb/tools 只用 stdlib（环境里没有 pyyaml），
#: 自写 YAML 子集解析器会把"解析错 ⇒ 环境根解错"这种静默故障引进来。
ENV_REGISTRY = os.path.join(TOOL_ROOT, "environments.json")


def _load_registry():
    if not os.path.isfile(ENV_REGISTRY):
        return {}
    try:
        with open(ENV_REGISTRY, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except Exception as exc:
        raise RuntimeError("环境注册表不可解析：%s（%s: %s）"
                           % (ENV_REGISTRY, type(exc).__name__, exc))
    if not isinstance(doc, dict):
        raise RuntimeError("环境注册表顶层必须是对象：%s" % ENV_REGISTRY)
    return doc


def _env_id(reg):
    return os.environ.get("LOOP_ENV") or reg.get("default")


def _resolve_env_root():
    """**环境（插件）根**。优先级：$LOOP_ENV_ROOT → 注册表 → 旧布局回落 → fail closed。"""
    explicit = os.environ.get("LOOP_ENV_ROOT")
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    reg = _load_registry()
    eid = _env_id(reg)
    entry = ((reg.get("environments") or {}).get(eid) or {}) if eid else {}
    if entry.get("path"):
        return os.path.abspath(os.path.expanduser(str(entry["path"])))
    if os.path.isdir(os.path.join(TOOL_ROOT, "TESTLIB")):
        # 向后兼容：拆仓前软件就在环境仓内，行为必须逐字节不变
        return TOOL_ROOT
    raise RuntimeError(
        "无法确定环境根（ENV_ROOT）：没有 $LOOP_ENV_ROOT，%s 里也没有可用条目，"
        "且 %s 下没有 TESTLIB/（说明不是拆仓前的旧布局）。"
        "请设 LOOP_ENV_ROOT 或补全注册表 —— 见 doc/spec/ENV_PLUGIN_SPEC.md §1"
        % (ENV_REGISTRY, TOOL_ROOT))


ENV_ROOT = _resolve_env_root()
ENV_ID = _env_id(_load_registry()) or os.path.basename(ENV_ROOT.rstrip(os.sep))


def _resolve_workspace_root():
    """**该环境的数据根**。优先级：$LOOP_WORKSPACE → 注册表 workspace → 旧布局回落 → 默认。"""
    explicit = os.environ.get("LOOP_WORKSPACE")
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    reg = _load_registry()
    entry = ((reg.get("environments") or {}).get(ENV_ID) or {})
    if entry.get("workspace"):
        p = os.path.expanduser(str(entry["workspace"]))
        return p if os.path.isabs(p) else os.path.join(TOOL_ROOT, p)
    if ENV_ROOT == TOOL_ROOT:
        return os.path.join(TOOL_ROOT, "kb")     # 旧布局：数据就在 kb/ 下
    return os.path.join(TOOL_ROOT, "workspaces", ENV_ID)


WORKSPACE_ROOT = _resolve_workspace_root()

#: 向后兼容别名（拆仓前 `ROOT` == 环境仓根，所有旧调用语义都是"环境"）
ROOT = ENV_ROOT


def tool_path(*parts):
    """**软件**资产路径（schema 等）：`tool_path('schema','manifest.schema.json')`"""
    return os.path.join(KB_DIR, *parts)


def env_path(*parts):
    """**环境**（插件）路径：`env_path('RTL')`"""
    return os.path.join(ENV_ROOT, *parts)


def root_path(*parts):
    """旧名兼容：语义 = `env_path`（拆仓前的全部调用都是在找环境文件）。"""
    return env_path(*parts)


def kb_path(*parts):
    """**工作区数据**路径：`kb_path('index','segments.json')`

    拆仓前指向软件仓内的 kb/；现在指向 WORKSPACE_ROOT（每环境数据，见 workspaces/README.md）。
    旧布局下 WORKSPACE_ROOT == ENV_ROOT/kb ⇒ 行为逐字节不变。
    """
    return os.path.join(WORKSPACE_ROOT, *parts)


def data_path(rel):
    """把历史里记录的「以 kb/ 开头的相对路径」解析到工作区数据根。

    manifest / 命令行默认值里大量出现 `kb/baselines/v0/rtl_snapshot.tar` 这类字符串；
    不能直接丢给 kb_path（会变成 <ws>/kb/...），要先剥掉 `kb/` 前缀。
    """
    s = str(rel).replace(os.sep, "/")
    if os.path.isabs(s):
        return s
    if s.startswith("kb/"):
        s = s[3:]
    return kb_path(*[x for x in s.split("/") if x])


def relpath(path):
    """转成稳定的 POSIX 相对路径（写进证据）。

    先试环境根、再试工作区根 —— 旧布局下工作区根是环境根的子目录，
    因此 `kb/runs/...` 仍渲染成 `kb/runs/...`，**证据字符串与既有指纹不变**。
    """
    ap = os.path.abspath(path)
    for base in (ENV_ROOT, WORKSPACE_ROOT):
        try:
            r = os.path.relpath(ap, base)
        except ValueError:
            continue
        if not r.startswith(".."):
            return r.replace(os.sep, "/")
    return ap


#: 工作区数据根下应当存在的东西
WORKSPACE_PARTS = ("index", "conflicts", "baselines", "runs")


def check_workspace():
    """自检工作区数据根是否有内容，返回缺失项列表（空 = 齐全）。

    必须外显：工作区指错地方时，症状是"索引缺口 / 冲突清单缺失"这类**难懂的**失败，
    看起来像数据坏了，其实只是路径没指对（实测：注册表默认值指向空目录时就是这个表现）。
    """
    return [name for name in WORKSPACE_PARTS if not os.path.isdir(kb_path(name))]


def check_env():
    """自检插件面是否齐全。返回缺失项列表（空 = 齐全）。**不猜、不兜底。**"""
    reg = _load_registry()
    entry = ((reg.get("environments") or {}).get(ENV_ID) or {})
    provides = entry.get("provides") or {}
    missing = []
    for name in (entry.get("frozen") or ["RTL", "TB", "PKG", "TESTLIB"]):
        if not os.path.isdir(env_path(name)):
            missing.append(str(name) + "/")
    for key in ("sim_setup",):
        rel = provides.get(key, "uvs.setup")
        if not os.path.exists(env_path(rel)):
            missing.append(rel)
    return missing


# ---------------------------------------------------------------- 指纹

_CHUNK = 1024 * 1024


def _hash_file(path, algo):
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        while True:
            b = f.read(_CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def md5_file(path):
    return _hash_file(path, "md5")


def sha256_file(path):
    return _hash_file(path, "sha256")


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canon_json(obj):
    """规范化 JSON：键排序、无多余空白、ensure_ascii=False、换行结尾。

    这是所有"指纹"的唯一序列化口径 —— 换一个序列化就会换指纹，
    所以任何脚本都不许自己 json.dumps 出错。
    """
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), indent=None) + "\n"


def sha256_obj(obj):
    return sha256_text(canon_json(obj))


def canon_normalized(obj, time_fields):
    """把声明过的时间字段值替换成固定占位串（递归），返回规范化 JSON 文本。

    README §3.1.1 弱判据用：同一输入 + 不同 `--now` 两次 ⇒ 归一化后必须逐字节相同，
    即"时间字段是唯一的差异"。
    """
    placeholder = "<TIMESTAMP>"

    def walk(o):
        if isinstance(o, dict):
            return {k: (placeholder if k in time_fields and isinstance(v, str) else walk(v))
                    for k, v in o.items()}
        if isinstance(o, list):
            return [walk(x) for x in o]
        return o

    return canon_json(walk(obj))


def sha256_obj_normalized(obj, time_fields=("generated_at",)):
    """归一化对象指纹（README §3.1.1 弱判据）。`time_fields` 必须由脚本**显式声明**。"""
    return sha256_text(canon_normalized(obj, set(time_fields)))


_WS = re.compile(r"[ \t]+")


def normalize_line(line):
    """条目集规范化：去行尾空白、把连续空白压成一个空格、strip。

    口径固定（写入 kb/README.md §3）：
        norm(line) = ' '.join(line.strip().rstrip().split())
    即"空白无关"；大小写**不**归一（寄存器名大小写是语义的一部分）。
    """
    return " ".join(line.strip().split())


def canon_lines_sha256(lines):
    """条目集指纹：对**已规范化**的行按顺序取 sha256（'\n' 连接 + 结尾换行）。"""
    return sha256_text("".join(normalize_line(x) + "\n" for x in lines))


def md5_manifest_sha256(path):
    """对 `md5sum` 格式清单文本做整体 sha256（清单本身的指纹）。"""
    return sha256_file(path)


#: 源码文本解码候选集（**唯一口径**）：utf-8 → GB18030（GBK 超集）→ GBK → latin-1 兜底。
#: 为什么放在 kb_lib：N2（差异 hunk）与 N5（可达性/源码读取）都要解同一批 RTL；
#: 两处各写一套曾在 GB18030 独有 4 字节区上产生口径分裂（SPEC-REV-01 R3「口径唯一」）。
#: 含 NUL 的字节流视为真二进制，**不进入**本候选集（调用方须自行判 NUL）。
DECODE_ENCODINGS = ("utf-8", "gb18030", "gbk", "latin-1")


# ---------------------------------------------------------------- 读写

def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj, mode=0o644):
    """原子写 JSON（canon_json 口径，人读时可用 `python3 -m json.tool`）。"""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent, prefix=".tmp.", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2))
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    os.chmod(path, mode)
    return path


def write_text(path, text, mode=0o644):
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent, prefix=".tmp.", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    os.chmod(path, mode)
    return path


def read_jsonl(path):
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line:
                continue
            out.append(json.loads(line))
    return out


def write_jsonl(path, rows, mode=0o644):
    return write_text(path, "".join(canon_json(r) for r in rows), mode)


def write_csv(path, header, rows, mode=0o644):
    """原子写 CSV（UTF-8、LF、QUOTE_MINIMAL）。rows 为 list/tuple 序列。"""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow(["" if v is None else v for v in r])
    return write_text(path, buf.getvalue(), mode)


def read_csv(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------- 契约校验

class SchemaError(Exception):
    pass


_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "integer": int,
    "number": (int, float),
    "null": type(None),
}


def load_schema(name):
    """name 可以是 'manifest' / 'index' / 'conflicts'，或 kb/ 下的相对路径。

    **命名归一（F-SCHEMA-02）**：`gate-state` 与 `gate_state` 视为同一个 schema。
    实测踩过：任务书写的是 `check(obj,"gate-state")`，而落盘的 schema 文件是
    `kb/schema/gate_state.schema.json` ⇒ 抛出来的是 `FileNotFoundError`（像个环境问题），
    而不是"校验不通过"（真正的结论）。名字不该决定能不能校验。
    """
    if not name.endswith(".json"):
        name = name + ".schema.json"
    cand = tool_path("schema", name)
    if os.path.exists(cand):
        return read_json(cand)
    alt = name.replace("-", "_")
    if alt != name and os.path.exists(tool_path("schema", alt)):
        return read_json(tool_path("schema", alt))
    # 兼容原行为：允许 name 是 kb/ 下的相对路径
    if os.path.exists(tool_path(name)):
        return read_json(tool_path(name))
    raise FileNotFoundError(
        "找不到 schema %r（试过 kb/schema/%s、kb/schema/%s、kb/%s）"
        % (name, name, alt, name))


def validate(obj, schema, where="$", _root=None):
    """JSON Schema draft-07 的**受支持子集**校验器（stdlib 实现）。

    支持：type / properties / required / additionalProperties(bool|schema) /
          items / enum / const / oneOf / anyOf / pattern / minItems / minimum / maximum /
          $ref（**仅本文件内** `#/definitions/...`，不支持远程引用）。
    不支持（遇到即抛 SchemaError，**不静默忽略**）：allOf / not / if-then-else /
          patternProperties / dependencies。
    返回 list[str] 错误信息（空列表 = 通过）。
    """
    errs = []

    if not isinstance(schema, dict):
        raise SchemaError("%s: schema 不是对象" % where)
    if _root is None:
        _root = schema
    for k in ("allOf", "not", "if", "patternProperties", "dependencies"):
        if k in schema:
            raise SchemaError("%s: schema 关键字 %r 不受支持（不静默忽略）" % (where, k))

    if "$ref" in schema:
        ref = schema["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/"):
            raise SchemaError("%s: 只支持本地 $ref '#'/definitions/...，得到 %r" % (where, ref))
        node = _root
        for part in ref[2:].split("/"):
            if not isinstance(node, dict) or part not in node:
                raise SchemaError("%s: $ref 解析失败 %r" % (where, ref))
            node = node[part]
        return validate(obj, node, where, _root)

    def err(msg):
        errs.append("%s: %s" % (where, msg))

    if "const" in schema and obj != schema["const"]:
        err("const 不符：期望 %r 实际 %r" % (schema["const"], obj))

    if "enum" in schema and obj not in schema["enum"]:
        err("enum 不符：%r 不在 %r" % (obj, schema["enum"]))

    if "oneOf" in schema:
        ok = sum(1 for s in schema["oneOf"]
                 if not validate(obj, s, where, _root))
        if ok != 1:
            err("oneOf 命中 %d 个分支（要求恰好 1 个）" % ok)
    if "anyOf" in schema:
        if not any(not validate(obj, s, where, _root) for s in schema["anyOf"]):
            err("anyOf 一个分支都没命中")

    t = schema.get("type")
    if t is not None:
        kinds = t if isinstance(t, list) else [t]
        ok = False
        for k in kinds:
            if k not in _TYPES:
                raise SchemaError("%s: 未知 type %r" % (where, k))
            if k == "integer" and isinstance(obj, bool):
                continue
            if k == "number" and isinstance(obj, bool):
                continue
            if isinstance(obj, _TYPES[k]):
                ok = True
                break
        if not ok:
            err("type 不符：期望 %r 实际 %s" % (t, type(obj).__name__))
            return errs

    if isinstance(obj, str) and "pattern" in schema:
        if re.search(schema["pattern"], obj) is None:
            err("pattern 不匹配：%r 不含 %r" % (obj, schema["pattern"]))

    if isinstance(obj, (int, float)) and not isinstance(obj, bool):
        if "minimum" in schema and obj < schema["minimum"]:
            err("minimum：%r < %r" % (obj, schema["minimum"]))
        if "maximum" in schema and obj > schema["maximum"]:
            err("maximum：%r > %r" % (obj, schema["maximum"]))

    if isinstance(obj, list):
        if "minItems" in schema and len(obj) < schema["minItems"]:
            err("minItems：%d < %d" % (len(obj), schema["minItems"]))
        if "items" in schema:
            for i, v in enumerate(obj):
                errs += validate(v, schema["items"], "%s[%d]" % (where, i), _root)

    if isinstance(obj, dict):
        req = schema.get("required", [])
        for k in req:
            if k not in obj:
                err("缺 required 键 %r" % k)
        props = schema.get("properties", {})
        ap = schema.get("additionalProperties", True)
        for k, v in obj.items():
            if k in props:
                errs += validate(v, props[k], "%s.%s" % (where, k), _root)
            elif ap is False:
                err("多余键 %r（additionalProperties=false）" % k)
            elif isinstance(ap, dict):
                errs += validate(v, ap, "%s.%s" % (where, k), _root)
    return errs


def check(obj, schema_name, what="对象"):
    """校验通过返回 obj；否则抛 SchemaError（把全部错误一次列出）。"""
    errs = validate(obj, load_schema(schema_name))
    if errs:
        raise SchemaError("%s 不符合 %s.schema.json：\n  - %s"
                          % (what, schema_name, "\n  - ".join(errs)))
    return obj


# ---------------------------------------------------------------- run / 证据身份

_NOW_ENV = "KB_NOW"
_now_value = None


def set_now(value):
    """注入时刻（README §3.1.1）。value 为 ISO8601 字符串或 None（回落墙钟）。

    优先级：set_now() > 环境变量 KB_NOW > 墙钟。**时间是唯一的非确定性来源**，
    所以全库只允许经由 now_iso()/today() 取时刻 —— 任何脚本不许自己 datetime.now()。
    """
    global _now_value
    _now_value = value


def now_iso():
    v = _now_value if _now_value is not None else os.environ.get(_NOW_ENV)
    if v:
        return v
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def today():
    return now_iso()[:10]


def new_run_id(prefix="RUN"):
    """run_id 一律 'RUN-YYYYMMDD-HHMMSS'（一个变更一轮）。"""
    return "%s-%s" % (prefix, datetime.now().astimezone().strftime("%Y%m%d-%H%M%S"))


def run_dir(run_id, create=False):
    p = kb_path("runs", run_id)
    if create:
        os.makedirs(p, exist_ok=True)
    return p


# ---------------------------------------------------------------- 三道人工闸门

GATE_IDS = ("G1_diff_confirm", "G2_report_accept", "G3_regression_decision")
GATE_KIND = {
    "G1_diff_confirm": "diff_confirm",
    "G2_report_accept": "report_accept",
    "G3_regression_decision": "regression_decision",
}
# G1 决策枚举；G2/G3 见 spec §2
GATE_DECISIONS = {
    "G1_diff_confirm": ["confirmed", "ignored", "disputed", "pending"],
    "G2_report_accept": ["accept", "rework", "pending"],
    "G3_regression_decision": ["full_now", "subset_only", "milestone_only", "defer", "pending"],
}


def gate_init(run_id, manifest_from, manifest_to):
    st = {
        "schema": "kb/gate-state",
        "version": 1,
        "run_id": run_id,
        "manifest_from": manifest_from,
        "manifest_to": manifest_to,
        "created_at": now_iso(),
        "gates": {},
    }
    for gid in GATE_IDS:
        st["gates"][gid] = {
            "gate_id": gid, "kind": GATE_KIND[gid], "status": "pending",
            "decision": "pending", "actor": None, "actor_kind": None,
            "human_signed": False, "signed_at": None, "note": None,
            "rework_target": None, "artifacts": [],
        }
    st[_ANCHOR_KEY] = _anchor_record(st)
    check(st, "gate_state")          # 与 gate_set 同一处强制（F-SCHEMA-02）
    write_json(os.path.join(run_dir(run_id, True), "gates.json"), st)
    gate_write_anchor(run_id)
    return gate_get(run_id)


def gate_get(run_id):
    return read_json(os.path.join(run_dir(run_id), "gates.json"))


def gate_set(run_id, gate_id, decision, actor, actor_kind, note=None,
             artifacts=None, rework_target=None):
    """写闸门状态。

    **红线条（I6）**：`human_signed=true` 只在 `actor_kind == "human"` 时才会被置位。
    模型/演练一律只能写 actor_kind ∈ {"model","rehearsal","host"}，`human_signed` 强制 False。
    这道检查在库里，任何脚本都绕不过去。

    **F-GATE-02（task-19）**：每次写入都向 `g["history"]` **追加**一条记录（含 `prev` 快照），
    历史**只增不改** ⇒ 旧签署人不会因再次签署而消失。
    **F-GATE-03（task-19）**：写盘后重算并落下 `gates.sha256`（同目录）与 `state["anchor"]`。
    """
    if gate_id not in GATE_IDS:
        raise ValueError("未知闸门 %r（合法：%r）" % (gate_id, list(GATE_IDS)))
    if decision not in GATE_DECISIONS[gate_id]:
        raise ValueError("闸门 %s 的决策 %r 非法（合法：%r）"
                         % (gate_id, decision, GATE_DECISIONS[gate_id]))
    if actor_kind not in ("human", "model", "rehearsal", "host"):
        raise ValueError("actor_kind 非法：%r" % actor_kind)
    if actor_kind == "human" and not actor:
        raise ValueError("actor_kind=human 必须给 actor（谁签的）")

    path = os.path.join(run_dir(run_id), "gates.json")
    st = read_json(path)
    g = st["gates"][gate_id]

    # F-GATE-02：已由人类签署的闸门，不得被非人类主体覆盖
    if g.get("human_signed") and actor_kind != "human":
        raise GateTamperError(
            "闸门 %s 已由人（%s）签署；非人类主体（actor_kind=%s）不得覆盖（I6 / F-GATE-02）"
            % (gate_id, g.get("actor"), actor_kind))

    prev = {k: v for k, v in g.items() if k != "history"}
    hist = list(g.get("history") or [])
    hist.append({
        "at": now_iso(), "gate": gate_id,
        "decision": decision, "actor": actor, "actor_kind": actor_kind,
        "human_signed": (actor_kind == "human"),
        "note": note, "rework_target": rework_target,
        "prev": prev,
    })

    g["decision"] = decision
    g["status"] = "pending" if decision == "pending" else "signed"
    g["actor"] = actor
    g["actor_kind"] = actor_kind
    g["human_signed"] = (actor_kind == "human")
    g["signed_at"] = now_iso() if decision != "pending" else None
    g["note"] = note
    g["rework_target"] = rework_target
    g["history"] = hist
    if artifacts:
        g["artifacts"] = list(artifacts)
    st["updated_at"] = now_iso()
    # SPEC-REV-15：签署必须绑产物指纹（材料集全量 md5 + 闸门摘要）。
    # 材料不可读 ⇒ **抛 GateMaterialError**（调用方显式失败，不得跳过或当"未变"）。
    # 放在 anchor 之前：state_hash 是 gates.json 的一部分，必须被锚覆盖。
    if decision != "pending":
        g["state_hash"] = gate_state_hash_record(
            st, gate_id, gate_material_manifest(run_id))
    # **写盘前**让 schema 进闭环（F-SCHEMA-02）：此前 `gate_state.schema.json` 是个
    # **死文件** —— 没有任何脚本调用它，于是它要抓的那种错（契约常量与实际产物不符）
    # 反而不会有任何人发现（F-SCHEMA-01 就是这么漏过去的）。
    # 位置必须在写完锚之后：被漏掉的那个词正好在 `anchor.algo` 里。
    st[_ANCHOR_KEY] = _anchor_record(st)
    check(st, "gate_state")
    write_json(path, st)
    gate_write_anchor(run_id)
    return gate_get(run_id)


class GateTamperError(Exception):
    """闸门状态被外部修改，或违反 I6 的写入尝试。"""


_ANCHOR_KEY = "anchor"
#: 锚算法标识。**单一定义**（F-SCHEMA-01 的教训）：此前 `gate_write_anchor` 写字面量、
#: schema 也写了一份 `const`，两处只差 record/state 一词 ⇒ schema 对**当前脚本写的每一个**
#: gates.json 都失败。现在字面量只在这里出现，写前校验与落盘共用同一个记录构造。
_ANCHOR_ALGO = "sha256-of-canonical-state-without-anchor"


def _anchor_value(st):
    """锚值 = 去掉 anchor 字段后的规范化 JSON 的 sha256（可复算）。"""
    tmp = {k: v for k, v in st.items() if k != _ANCHOR_KEY}
    return sha256_text(canon_json(tmp))


def _anchor_record(st):
    """锚记录（写前校验与落盘共用，避免两处常量漂移）。"""
    return {"algo": _ANCHOR_ALGO, "value": _anchor_value(st), "file": "gates.sha256"}


def gate_write_anchor(run_id):
    """重算并落 `gates.sha256`（同目录）与 `state["anchor"]`（F-GATE-03）。"""
    path = os.path.join(run_dir(run_id), "gates.json")
    st = read_json(path)
    st[_ANCHOR_KEY] = _anchor_record(st)
    write_json(path, st)
    ap = os.path.join(run_dir(run_id), "gates.sha256")
    write_text(ap, st[_ANCHOR_KEY]["value"] + "  gates.json\n")
    return st[_ANCHOR_KEY]["value"]


def gate_verify_anchor(run_id):
    """校验锚。返回 (ok, detail)：ok=True 通过；False 被篡改；None = 无锚（legacy，未校验）。"""
    path = os.path.join(run_dir(run_id), "gates.json")
    st = read_json(path)
    ap = os.path.join(run_dir(run_id), "gates.sha256")
    if _ANCHOR_KEY not in st or not os.path.exists(ap):
        return None, "无锚（legacy 状态，未校验）"
    want = open(ap, "r", encoding="utf-8").read().split()[0].strip()
    got = _anchor_value(st)
    if want != got or st[_ANCHOR_KEY].get("value") != got:
        return False, ("状态被外部修改：锚期望 %s 实际 %s（gates.sha256 与内部 anchor 也需一致）"
                       % (want[:12], got[:12]))
    return True, "锚一致（%s…）" % got[:12]


# ---------------------------------------------------------------- stateHash（SPEC-REV-15）
#
# 问题：`gates.sha256` 的锚只覆盖 `gates.json` **自身** ⇒ 批准之后改件不会让批准失效。
# 本段把"签署所绑材料"做成可复算指纹：签时记全量材料 md5 + 闸门摘要，`require-signed`
# 复算并比对；变更 ⇒ STATE_HASH_MISMATCH（旧签署不再有效）。**单一实现**：遍历/md5/canon 全复用本库。

#: 材料集**排除项**：都是"签署之后会合法变化"的记录/缓存，不是材料。
#: - gates.* 是本记录自身（由 anchor 保护）；agent_* 是模型/控制审计（只增不改）；
#:   decisions/ 是逐条处置落账（签署**之后**由 Host 写）；view.json 是界面投影缓存。
GATE_MATERIAL_EXCLUDE_FILES = ("gates.json", "gates.sha256", "view.json")
GATE_MATERIAL_EXCLUDE_DIRS = ("agent_calls", "agent_controls", "decisions")

#: stateHash 的 schema/algo 标识（**单一定义**：写与校验共用，禁止字面量漂移）。
STATE_HASH_SCHEMA = "kb/gate-state-hash/1"
STATE_HASH_ALGO = "sha256-of-materials+gate-summary"


class GateMaterialError(Exception):
    """材料集不可读（权限/IO）。**不得**跳过、不得当"未变"、不得用 mtime 代替内容。"""


def gate_material_manifest(run_id):
    """`[{path,size,md5}, ...]`，按相对路径字典序；跳过符号链接；不可读 ⇒ GateMaterialError。"""
    root = run_dir(run_id)
    if not os.path.isdir(root):
        raise GateMaterialError("run 目录不存在：%s" % relpath(root))
    items = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in GATE_MATERIAL_EXCLUDE_DIRS)
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if rel in GATE_MATERIAL_EXCLUDE_FILES:
                continue
            if os.path.islink(full) or not os.path.isfile(full):
                continue
            try:
                with open(full, "rb") as fh:
                    data = fh.read()
            except OSError as exc:
                raise GateMaterialError("材料不可读：%s（%s）" % (rel, exc)) from None
            items.append({"path": rel, "size": len(data),
                          "md5": hashlib.md5(data).hexdigest()})
    items.sort(key=lambda item: item["path"])
    return items


def _gate_summary_map(st):
    """闸门摘要（**不含 history**：只增不改，不作指纹）。"""
    keys = ("decision", "status", "actor", "actor_kind", "human_signed", "signed_at")
    return {gid: {k: st["gates"][gid].get(k) for k in keys} for gid in GATE_IDS}


def gate_state_hash_record(st, gate_id, materials):
    """按当前状态 + 材料集算 stateHash 记录（被 anchor 覆盖，不另加锚）。"""
    g = st["gates"][gate_id]
    gates_map = _gate_summary_map(st)
    payload = {
        "schema": STATE_HASH_SCHEMA,
        "run_id": st["run_id"], "gate_id": gate_id,
        "decision": g.get("decision"), "actor": g.get("actor"),
        "actor_kind": g.get("actor_kind"), "signed_at": g.get("signed_at"),
        "manifest_from": st.get("manifest_from"), "manifest_to": st.get("manifest_to"),
        "materials_digest": sha256_text(canon_json(materials)),
        "gates_digest": sha256_text(canon_json(gates_map)),
    }
    return {"algo": STATE_HASH_ALGO, "value": sha256_text(canon_json(payload)),
            "computed_at": g.get("signed_at") or now_iso(),
            "materials_digest": payload["materials_digest"],
            "gates_digest": payload["gates_digest"],
            "materials": materials, "gates": gates_map}


def gate_verify_state_hash(run_id, gate_id):
    """返回 (ok, detail)：True 一致 / False 不一致（detail 含 changed/added/removed）/ None=legacy。"""
    st = read_json(os.path.join(run_dir(run_id), "gates.json"))
    rec = (st["gates"].get(gate_id) or {}).get("state_hash")
    if not isinstance(rec, dict) or not rec.get("value"):
        return None, "无 stateHash（legacy 状态：未校验签署所绑材料）"
    try:
        materials = gate_material_manifest(run_id)
    except GateMaterialError as exc:
        return False, "STATE_HASH_MISMATCH：%s" % exc

    old = {i["path"]: i for i in (rec.get("materials") or [])}
    cur = {i["path"]: i for i in materials}
    changed = sorted(p for p in set(old) & set(cur)
                     if old[p].get("md5") != cur[p].get("md5")
                     or old[p].get("size") != cur[p].get("size"))
    added = sorted(set(cur) - set(old))
    removed = sorted(set(old) - set(cur))
    fresh = gate_state_hash_record(st, gate_id, materials)
    if not (changed or added or removed) and fresh["value"] == rec.get("value"):
        return True, "stateHash 一致（%s…）" % str(rec.get("value"))[:12]

    parts = ["STATE_HASH_MISMATCH：%s 的签署所绑材料已变（旧签署不再有效，须重跑闸门）" % gate_id]

    def _fmt(label, xs):
        if xs:
            head = ", ".join(xs[:5]) + (" …" if len(xs) > 5 else "")
            parts.append("%s %d：%s" % (label, len(xs), head))

    _fmt("changed", changed)
    _fmt("added", added)
    _fmt("removed", removed)
    if not (changed or added or removed):
        parts.append("闸门摘要或签署字段已变（value 不一致）")
    return False, "；".join(parts)


def gate_summary(run_id):
    st = gate_get(run_id)
    return {
        "run_id": st["run_id"],
        "all_signed": all(st["gates"][g]["status"] == "signed" for g in GATE_IDS),
        "human_signed_all": all(st["gates"][g]["human_signed"] for g in GATE_IDS),
        "gates": {g: {"decision": st["gates"][g]["decision"],
                      "actor_kind": st["gates"][g]["actor_kind"],
                      "human_signed": st["gates"][g]["human_signed"]}
                  for g in GATE_IDS},
    }


# ---------------------------------------------------------------- 杂项

def die(msg, code=2):
    sys.stderr.write("[FAIL] %s\n" % msg)
    raise SystemExit(code)


def info(msg):
    sys.stdout.write("[kb] %s\n" % msg)


def ensure_dir(p):
    os.makedirs(p, exist_ok=True)
    return p


def copytree(src, dst):
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return dst


def git_head(repo_path):
    """读嵌套 git 的 HEAD（不执行 git 命令，避免依赖 .git 目录权限）。

    返回 (ref, parseable)。BIN/commit_id.log 里那种 40 位十六进制不可解析的
    "commit"（`06d9895b…`）在本函数里判 parseable=False。
    """
    gitdir = os.path.join(repo_path, ".git")
    if os.path.isdir(gitdir):
        head = os.path.join(gitdir, "HEAD")
    elif os.path.isfile(gitdir):
        # worktree/submodule 的 .git 是文件：gitdir: <path>
        try:
            with open(gitdir, "r", encoding="utf-8") as f:
                line = f.read().strip()
        except OSError:
            return None, False
        if not line.startswith("gitdir:"):
            return None, False
        head = os.path.join(line.split(":", 1)[1].strip(), "HEAD")
    else:
        return None, False
    try:
        with open(head, "r", encoding="utf-8") as f:
            ref = f.read().strip()
    except OSError:
        return None, False
    if ref.startswith("ref:"):
        refpath = os.path.join(os.path.dirname(head), ref.split(":", 1)[1].strip())
        try:
            with open(refpath, "r", encoding="utf-8") as f:
                ref = f.read().strip()
        except OSError:
            return None, False
    ok = bool(re.fullmatch(r"[0-9a-f]{40}", ref))
    return ref, ok
