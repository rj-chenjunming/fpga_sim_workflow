"""F06：模型请求机制与节点语义分层的结构断言（保持行为重构）。

这些断言固定「谁拥有什么」，防止将来把节点判据复制回机制层：
- 机制模块不含 Host 校验实现；校验器由调用方注入；
- 节点语义模块单一存在，`model_steps` 只做兼容导出；
- TriggerFlow 拓扑使用的入口仍从 `model_steps` 可取。
"""
from __future__ import annotations

import inspect

from workflows.chunks import (
    model_request as MR,
    model_steps as M,
    n6_facts,
    n10_semantics,
    n11_guard,
)


def test_mechanism_module_does_not_own_node_validation():
    mech = inspect.getsource(MR)
    assert "def _validate" not in mech
    assert "def validate" not in mech, "机制层不得重新实现 Host 校验"
    assert "validate" in inspect.signature(MR.run_attempt).parameters
    assert "validate" in inspect.signature(MR.run_model_node).parameters


def test_model_steps_keeps_the_single_validator():
    source = inspect.getsource(M)
    assert source.count("def _validate(") == 1


def test_node_semantics_live_in_their_modules_and_are_reexported():
    assert M.build_n6_targets is n6_facts.build_n6_targets
    assert M.PENDING_CLASSES is n10_semantics.PENDING_CLASSES
    assert M._host_identity is n11_guard._host_identity
    # 兼容导出必须仍是可调用对象（TriggerFlow 入口与既有消费者不变）
    for name in ("run_model_node", "n3_digest", "n6_author", "n8_check", "n10_reconcile",
                 "n11_review", "n12_report", "build_sandbox_cases"):
        assert callable(getattr(M, name)), name


def test_mechanics_no_longer_read_prompts_from_a_private_copy():
    """提示词读取唯一在 model_common；机制层只 import。"""
    assert "PROMPTS_FILE" not in inspect.getsource(M)
    assert "PROMPTS_FILE" in inspect.getsource(__import__(
        "workflows.chunks.model_common", fromlist=["model_common"]))
