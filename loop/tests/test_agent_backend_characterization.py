"""后端提取前的可观察契约；受控 SDK，不调用真实模型。"""
import pytest

from test_agent_context_memory import ctx, provider, call  # noqa: F401
from host import agent_memory as AM
from prompts.node_schemas import SCHEMAS


@pytest.mark.parametrize('wrapped', [False, True])
async def test_schema_objects_keep_normalization_and_sealed_input(ctx, provider, wrapped):
    response = SCHEMAS['n3'](**provider['response'])
    provider['response'] = {'$result': response} if wrapped else response
    out = await call(ctx)
    assert out['data'] == response.model_dump()
    assert out['validation']['ok'] is True
    record = AM.verify_attempt((ctx.run_dir / out['request_ref']).parent)
    request = record['request']
    assert request['input'] == provider['inputs'][0]
    assert request['info'] == provider['info']
    assert request['instruct'] == provider['instruct']
    assert request['schema'] == provider['schema'].model_json_schema()
    assert record['result']['payload']['data'] == response.model_dump()
