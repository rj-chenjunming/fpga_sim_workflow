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
# kb/tools/kb_lib.py -> kb/tools -> kb -> <repo root>
KB_DIR = os.path.dirname(os.path.dirname(_THIS))
ROOT = os.path.dirname(KB_DIR)


def kb_path(*parts):
    """kb/ 下的绝对路径；`kb_path('index','segments.json')`"""
    return os.path.join(KB_DIR, *parts)


def root_path(*parts):
    return os.path.join(ROOT, *parts)


def relpath(path):
    """转成相对仓库根的 POSIX 相对路径（跨机器稳定，用于写进证据）。"""
    ap = os.path.abspath(path)
    try:
        r = os.path.relpath(ap, ROOT)
    except ValueError:
        return ap
    return r.replace(os.sep, "/")


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
    """name 可以是 'manifest' / 'index' / 'conflicts'，或 kb/ 下的相对路径。"""
    cand = kb_path("schema", name if name.endswith(".json") else name + ".schema.json")
    if not os.path.exists(cand):
        cand = kb_path(name) if not os.path.isabs(name) else name
    return read_json(cand)


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
    write_json(path, st)
    gate_write_anchor(run_id)
    return gate_get(run_id)


class GateTamperError(Exception):
    """闸门状态被外部修改，或违反 I6 的写入尝试。"""


_ANCHOR_KEY = "anchor"


def _anchor_value(st):
    """锚值 = 去掉 anchor 字段后的规范化 JSON 的 sha256（可复算）。"""
    tmp = {k: v for k, v in st.items() if k != _ANCHOR_KEY}
    return sha256_text(canon_json(tmp))


def gate_write_anchor(run_id):
    """重算并落 `gates.sha256`（同目录）与 `state["anchor"]`（F-GATE-03）。"""
    path = os.path.join(run_dir(run_id), "gates.json")
    st = read_json(path)
    st[_ANCHOR_KEY] = {"algo": "sha256-of-canonical-state-without-anchor",
                       "value": _anchor_value(st)}
    st[_ANCHOR_KEY]["file"] = "gates.sha256"
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
