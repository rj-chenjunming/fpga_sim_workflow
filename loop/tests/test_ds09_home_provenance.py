"""S8b：DS-09 **来源判定**（SPEC-REV-14 §9，四档 + 四条不变量；裁决 B1 = 治 (i)）。

为什么需要这一片：`dsh --profile web` 会在 home 里**自生成** `.credentials.yaml`（会话签名
secret，真机实测 161 B），而 `FORBIDDEN_HOME_ENTRIES` 把它一律判成"attempt home 含宿主件"。
S7c 靠"web home 与 attempt home 并列"绕开，代价是人在 GUI 里**看不到该 attempt 的会话**
（D3 未落地）。S8b 回到 D3 的"共用同一实例 home"，判据改成**逐条判来源**。

本文件固定住的判据（不读实现也应成立）：

1. `settings.yaml` **无例外**拒绝（`host_settings_copy`）——即使它的内容长得像 dsh 自生成形态；
2. 凭据件内容含**任一宿主凭据值** ⇒ `host_credential_value` 拒绝，且**优先于形态**
   （形态像 dsh 自生成也照拒）；
3. 形态符合 dsh 自生成登记（键集合 ⊆ `DSH_GENERATED_CREDENTIAL_KEYS`）⇒ `dsh_generated` **放行**，
   并在准入记录里登记 `source` + `basis`；
4. 形态不认识 / 读失败 / 非 mapping / 多出未登记键 ⇒ `unknown` **拒绝**（fail-closed，没有"看不清就放行"）；
5. **零回显**：判定结论、错误消息、异常文本、准入记录里**不得**出现凭据值或 secret 片段；
6. **常量漂移**：真机实测登记形态的键集合必须**逐字等于**常量；改了常量而没重录 ⇒ 本文件红；
7. `FORBIDDEN_HOME_ENTRIES` 的历史语义**不改**（仍是那三个名字，没把任何名字移出去）；
8. 判定入口只有 `dsh_assets.home_provenance` 一处（`home_problems` 只是它的兼容外壳，红线 8）。
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from host.agent_backends import dsh_assets as A
from host.agent_backends import dsh_selfcheck as SC

#: 假的"宿主凭据值"（够长，避免偶然子串命中；真值绝不进仓库/证据）
SECRET = "host-secret-value-0123456789abcdef"

#: 真机实测（2026-10-29，`dsh` 0.2.1-rc.2，`loop/.logs/s7c/home{,...}/.credentials.yaml` ×3 同形）
#: 的**键形态**。secret 值用假的固定串（不抄真值）。
#: 注意：这是"形态"样本，不是"值"样本 —— 判定只看键集合 + 是否含宿主凭据值。
DSH_GENERATED_SAMPLE = """\
version: 1
records:
  client-connection/browser-session:
    kind: grant
    payload:
      version: 1
      secret: dsh-generated-secret-0123456789abcdefXYZ
"""
#: 样本里那个（假的）secret 值：零回显断言要连它也不许出现
SAMPLE_SECRET = "dsh-generated-secret-0123456789abcdefXYZ"


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "dsh-home"
    home.mkdir(parents=True, exist_ok=True)
    return home


def _write(home: Path, name: str, text: str) -> Path:
    path = home / name
    path.write_text(text, encoding="utf-8")
    return path


def _record(provenance: A.HomeProvenance) -> list[dict[str, str]]:
    return provenance.record()


# ================================================================ 不变量 1：settings.yaml 无例外

def test_host_settings_copy_is_rejected_regardless_of_content(tmp_path: Path) -> None:
    """`settings.yaml` 任何来源都拒绝 —— 连"内容像 dsh 自生成形态"也照拒（B3 语义不变）。"""
    home = _home(tmp_path)
    _write(home, "settings.yaml", DSH_GENERATED_SAMPLE)
    provenance = A.home_provenance(home, host_secrets=())
    assert provenance.problems
    assert [(entry.name, entry.source) for entry in provenance.entries] == [
        ("settings.yaml", "host_settings_copy")]
    assert [item["source"] for item in _record(provenance)] == ["host_settings_copy"]


def test_forbidden_home_entries_semantics_are_unchanged() -> None:
    """B3 的历史语义不改：三个名字仍都列在常量里（S8b 只加"来源"，没把任何名字移出去）。"""
    assert A.FORBIDDEN_HOME_ENTRIES == ("settings.yaml", ".credentials.yaml", ".credentials")
    assert A.HOME_SOURCE_DSH_GENERATED in A.HOME_SOURCES
    assert set(A.HOME_SOURCES) == {"host_settings_copy", "host_credential_value",
                                   "dsh_generated", "unknown"}


# ================================================================ 不变量 2：凭据值优先于形态

def test_host_credential_value_wins_over_generated_shape(tmp_path: Path) -> None:
    """形态像 dsh 自生成，但内容含宿主凭据值 ⇒ `host_credential_value` 拒绝（不因形态放行）。"""
    home = _home(tmp_path)
    _write(home, ".credentials.yaml", DSH_GENERATED_SAMPLE.replace(SAMPLE_SECRET, SECRET))
    provenance = A.home_provenance(home, host_secrets=(SECRET,))
    assert provenance.problems
    entry = provenance.entries[0]
    assert (entry.name, entry.source) == (".credentials.yaml", "host_credential_value")
    assert not entry.allowed


def test_host_credential_value_in_opaque_content_is_rejected(tmp_path: Path) -> None:
    """内容既不是 dsh 形态、又含宿主凭据值 ⇒ 仍按凭据值拒（不是"形态不认识"那一档）。"""
    home = _home(tmp_path)
    _write(home, ".credentials", "refs:\n  PUBLIC_API_KEY: %s\nother: 1\n" % SECRET)
    provenance = A.home_provenance(home, host_secrets=(SECRET, ""))
    assert provenance.entries[0].source == "host_credential_value"
    assert provenance.problems
    # 空的"凭据值"不算命中（不进比对集合）
    clean = _home(tmp_path / "clean")
    _write(clean, ".credentials", "x: y\n")
    assert [entry.source for entry in A.home_provenance(
        clean, host_secrets=("",)).entries] == ["unknown"]


# ================================================================ 第三档：dsh 自生成 ⇒ 放行 + 记录

def test_dsh_generated_credentials_are_allowed_and_recorded(tmp_path: Path) -> None:
    """`dsh --profile web` 自生成的 `.credentials.yaml` ⇒ 放行，记录 source + basis（不含值）。"""
    home = _home(tmp_path)
    _write(home, ".credentials.yaml", DSH_GENERATED_SAMPLE)
    provenance = A.home_provenance(home, host_secrets=(SECRET,))
    assert provenance.problems == ()
    assert provenance.ok
    record = _record(provenance)
    assert record == [{"name": ".credentials.yaml", "source": "dsh_generated",
                       "basis": provenance.entries[0].basis}]
    assert "records.client-connection/browser-session" in record[0]["basis"]


def test_dsh_generated_shape_is_accepted_for_dot_credentials_too(tmp_path: Path) -> None:
    """两个凭据文件名同一条内容判据（不按文件名猜来源）。"""
    home = _home(tmp_path)
    _write(home, ".credentials", DSH_GENERATED_SAMPLE)
    assert A.home_problems(home, host_secrets=()) == []


# ================================================================ 不变量 3：unknown ⇒ 拒绝（fail-closed）

@pytest.mark.parametrize("name,body", [
    (".credentials.yaml", "x: y\n"),                                  # 形态没登记过
    (".credentials.yaml", ""),                                        # 空文件 = 无判据可用
    (".credentials.yaml", "x: [1,\n"),                                # 坏 YAML
    (".credentials.yaml", "- 1\n- 2\n"),                              # 不是 mapping
    (".credentials.yaml", DSH_GENERATED_SAMPLE + "records:\n  other: 1\n"),  # 未登记键
])
def test_unknown_shapes_are_rejected_fail_closed(tmp_path: Path, name: str, body: str) -> None:
    home = _home(tmp_path)
    _write(home, name, body)
    provenance = A.home_provenance(home, host_secrets=(SECRET,))
    assert provenance.problems, "unknown 必须拒绝（没有'看不清就放行'的档）"
    assert [entry.source for entry in provenance.entries] == ["unknown"]
    assert [item["source"] for item in _record(provenance)] == ["unknown"]


def test_unreadable_entry_is_unknown_and_rejected(tmp_path: Path) -> None:
    """目录/读失败同样落 `unknown` 并拒绝（不是"没这条"⇒凭空放行）。"""
    home = _home(tmp_path)
    (home / ".credentials.yaml").mkdir()
    provenance = A.home_provenance(home, host_secrets=())
    assert [entry.source for entry in provenance.entries] == ["unknown"]
    assert provenance.problems


# ================================================================ 不变量 4：零回显

def test_judgement_never_echoes_credential_values(tmp_path: Path) -> None:
    """判定结论/错误消息/异常文本/准入记录里都不得出现凭据值或 secret 片段。"""
    home = _home(tmp_path)
    _write(home, ".credentials.yaml", "refs:\n  k: %s\n" % SECRET)
    _write(home, "settings.yaml", "llm-pi-ai: {}\n")
    provenance = A.home_provenance(home, host_secrets=(SECRET,))
    blob = json.dumps(_record(provenance), ensure_ascii=False) + "\n".join(provenance.problems) \
        + repr(provenance) + str(provenance)
    assert SECRET not in blob
    assert SECRET[:12] not in blob, "连 secret 片段也不许出现"
    # 准入记录里只允许 source 枚举 / 文件名 / 不含值的描述
    assert {item["source"] for item in _record(provenance)} <= set(A.HOME_SOURCES)


def test_materialize_rejects_host_settings_without_echoing_secret(tmp_path: Path) -> None:
    """`materialize` 的显式失败文本同样零回显（异常会被落进 attempt 记录）。"""
    layout = A.AttemptLayout.under(tmp_path / "attempt")
    layout.prepare()
    _write(layout.home, ".credentials.yaml", "refs:\n  k: %s\n" % SECRET)
    with pytest.raises(A.AssetError) as info:
        A.materialize(layout)
    assert SECRET not in str(info.value)
    assert SECRET[:12] not in str(info.value)


# ================================================================ 不变量 5：常量漂移被钉住

def _flatten(document: object, prefix: str = "", out: dict[str, object] | None = None
             ) -> dict[str, object]:
    """把 YAML 文档摊平成"键路径 → 值"（与实现无关的独立摊平，用于钉常量）。"""
    import yaml

    out = {} if out is None else out

    def walk(node: object, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                name = "%s.%s" % (path, key) if path else str(key)
                out[name] = value
                walk(value, name)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                name = "%s[%d]" % (path, index)
                out[name] = value
                walk(value, name)

    walk(document, prefix)
    return out


def test_generated_credential_keys_constant_matches_recorded_shape() -> None:
    """常量漂移用例：实测登记形态的键集合必须**逐字等于**常量（改常量不重录 ⇒ 本条红）。"""
    import yaml

    keys = frozenset(_flatten(yaml.safe_load(DSH_GENERATED_SAMPLE)))
    assert keys == frozenset(A.DSH_GENERATED_CREDENTIAL_KEYS), (
        "DSH_GENERATED_CREDENTIAL_KEYS 与实测登记形态不一致：换 dsh 版本必须重新录制"
        "（起 `dsh --profile web` 看它自生成的 .credentials.yaml 键集合）再改常量")
    assert A.DSH_GENERATED_CREDENTIAL_REQUIRED <= frozenset(A.DSH_GENERATED_CREDENTIAL_KEYS)
    # 必需键必须真的出现在实测形态里（否则"必需"是空话）
    assert A.DSH_GENERATED_CREDENTIAL_REQUIRED <= keys


def test_new_unregistered_key_turns_shape_into_unknown(tmp_path: Path) -> None:
    """dsh 换版本多写一个键 ⇒ 形态不在登记内 ⇒ `unknown` 拒绝（fail-closed，等重录常量）。"""
    home = _home(tmp_path)
    _write(home, ".credentials.yaml",
           DSH_GENERATED_SAMPLE.replace("    kind: grant\n",
                                        "    kind: grant\n    issuedAt: 1\n"))
    assert [entry.source for entry in A.home_provenance(
        home, host_secrets=()).entries] == ["unknown"]


# ================================================================ 单一判据入口（红线 8）+ 默认凭据来源

def test_home_problems_delegates_to_the_single_judgement(tmp_path: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    """红线 8：判定只有一处实现；`home_problems` 只是它的兼容外壳（不重算）。"""
    home = _home(tmp_path)
    calls: list[object] = []

    def fake(home_arg, *, host_secrets=None):
        calls.append((Path(home_arg), host_secrets))
        return A.HomeProvenance(entries=(), problems=("sentinel",))

    monkeypatch.setattr(A, "home_provenance", fake)
    assert A.home_problems(home) == ["sentinel"]
    assert calls and calls[0][0] == home


def test_default_credential_source_is_the_host_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """不给 `host_secrets` 时，凭据值来自 Host（`host/model_provider` 与进程 env），只在内存比对。"""
    import host.model_provider as MP

    monkeypatch.setenv("PUBLIC_API_KEY", SECRET)
    monkeypatch.setattr(MP, "resolve", lambda **kwargs: SimpleNamespace(
        _api_key=SECRET, api_key_env="PUBLIC_API_KEY"))
    assert A.host_credential_values() == (SECRET,)
    # 去重：env 与 provider 解析到同一个值时只留一条（"第 N 条命中"要可复算）
    assert len(A.host_credential_values()) == 1


def test_preflight_side_channel_still_passes_for_shared_home(tmp_path: Path) -> None:
    """D3 收口的关键回归：共用 home 里那份 dsh 自生成件**不得**让下一次 attempt 的 DS-09 失败。"""
    home = _home(tmp_path)
    _write(home, ".credentials.yaml", DSH_GENERATED_SAMPLE)
    assert SC.verify_home(home) == []
    (home / "settings.yaml").write_text("x: 1\n", encoding="utf-8")
    assert SC.verify_home(home), "真宿主件仍必须被挡住"
