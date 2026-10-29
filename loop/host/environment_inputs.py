"""现有环境的暂存输入与用例路径约定。"""
from pathlib import Path
from typing import Any

STAGED_DEFAULT_RTL = ("RTL/SRC/imports", "RTL/RTL_COMMON")


def staged_inputs(run_dir: Path) -> dict[str, Any]:
    """解析并**完整性校验** `run_dir/staged/` 约定。

    约定（本层新增，供 real 模式摄入新 RTL 包 + 新文档）：
      staged/RTL/SRC/imports/**, staged/RTL/RTL_COMMON/**   （完整镜像，缺一即失败）
      staged/doc/<唯一一份 .md> 或 staged/doc.md
      staged/regmap.json          （与 staged 文档同版本；缺则失败，防止用旧位定义索引）

    返回 `{present: False}` 表示未提供 staged（用 ENV_ROOT 现态）；
    提供了但不完整 ⇒ 抛 FileNotFoundError（调用方 node_failed，不猜、不回落）。
    """
    staged = run_dir / "staged"
    if not staged.is_dir():
        return {"present": False, "staged_dir": str(staged)}

    problems: list[str] = []
    rtl_args: list[str] = []
    for rel in STAGED_DEFAULT_RTL:
        src = staged / rel
        if not src.is_dir():
            problems.append(f"缺 {src}（staged RTL 必须是默认摄入范围的完整镜像）")
            continue
        if not any(src.iterdir()):
            problems.append(f"{src} 为空目录")
            continue
        # n1_snapshot 的映射语法：绝对路径=DEST_REL（否则 tar 里会出现绝对路径/暂存路径）
        rtl_args.append(f"{src}={rel}")

    doc_src: str | None = None
    doc_dir = staged / "doc"
    if doc_dir.is_dir():
        docs = sorted(doc_dir.glob("*.md"))
        if len(docs) == 1:
            doc_src = str(docs[0])
        elif not docs:
            problems.append(f"{doc_dir} 下没有 .md 文档")
        else:
            problems.append(f"{doc_dir} 下必须恰好 1 份 .md（实际 {len(docs)}）")
    elif doc_dir.is_file():
        doc_src = str(doc_dir)
    elif (staged / "doc.md").is_file():
        doc_src = str(staged / "doc.md")
    else:
        problems.append(f"缺 staged 文档（{doc_dir} 或 staged/doc.md）")

    regmap = staged / "regmap.json"
    if doc_src and not regmap.is_file():
        problems.append(f"staged 文档存在但缺 {regmap}（文档指纹必须与位定义索引同版本）")
    if problems:
        raise FileNotFoundError("staged 输入不完整：" + "；".join(problems))
    return {
        "present": True,
        "staged_dir": str(staged),
        "rtl_src": rtl_args,
        "doc_src": doc_src,
        "regmap": str(regmap),
    }


def source_case_path(repo_root: Path, target: dict[str, Any]) -> Path:
    rel = str(target.get("file") or "")
    case = str(target.get("case") or "")
    if rel:
        return repo_root / rel
    return repo_root / "TESTLIB" / f"{case}.sv"


def author_case_path(repo_root: Path, file_rel: str, case: str) -> Path:
    source = repo_root / file_rel
    if not source.is_file():
        source = repo_root / "TESTLIB" / f"{case}.sv"
    return source
