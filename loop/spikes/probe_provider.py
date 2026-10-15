"""探测 provider 接入：先看解析结果（不含密钥），再真发一次最小请求。"""
import asyncio, json, sys
sys.path.insert(0, ".")
from host import model_provider as MP

cfg = MP.resolve()
print("=== 解析结果（public 投影，无密钥）===")
print(json.dumps(cfg.public(), ensure_ascii=False, indent=1, default=str))
print()
print("=== 真发一次最小请求（responses family）===")
print(json.dumps(asyncio.run(MP.ping()), ensure_ascii=False, default=str)[:900])
