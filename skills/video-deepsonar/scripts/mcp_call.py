#!/usr/bin/env python3
"""DeepSonar MCP 直连工具（无 MCP 客户端环境的标准化回退通道）。

通过 Streamable HTTP 直接调用 dsapi.solohub.art 的 MCP 工具，避免 agent
自行拼装协议细节。鉴权读环境变量 DEEPSONAR_API_KEY（dk_ 前缀）。

用法：
    export DEEPSONAR_API_KEY=dk_xxxxxxxx
    python3 mcp_call.py list_platforms '{}'
    python3 mcp_call.py search_rules '{"query": "发货超时处罚标准", "platform": "douyin"}'
    python3 mcp_call.py diagnose_risk '{"content": "全场最低价！", "platform": "douyin"}'
    python3 mcp_call.py get_rule_detail '{"rule_id": 101}'

输出（stdout，JSON）：{"tool": ..., "is_error": ..., "content": [...]}
退出码：0 成功；2 业务错误（isError，如平台未开放）；3 鉴权/网络/协议错误。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

ENDPOINT = "https://dsapi.solohub.art/api/mcp"

HEADERS_BASE = {
    "Content-Type": "application/json",
    # Streamable HTTP 要求同时接受 JSON 与 SSE
    "Accept": "application/json, text/event-stream",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 video-deepsonar-skill/1.0.0",
}


import time

def post(payload: dict, api_key: str) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT, data=body,
        headers={**HEADERS_BASE, "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
            if raw.lstrip().startswith("{"):
                return json.loads(raw)
            for line in raw.splitlines():
                if line.startswith("data:"):
                    return json.loads(line[5:].strip())
            raise RuntimeError(f"无法解析响应: {raw[:300]}")
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError) as e:
            last_err = e
            if attempt < 2:
                time.sleep(1.0)
                continue
    if isinstance(last_err, urllib.error.HTTPError):
        detail = last_err.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {last_err.code}: {detail}") from last_err
    if isinstance(last_err, urllib.error.URLError):
        raise RuntimeError(f"网络错误: {last_err.reason}") from last_err
    raise RuntimeError(str(last_err))


def rpc(method: str, params: dict | None, api_key: str, req_id: int) -> dict:
    payload = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        payload["params"] = params
    return post(payload, api_key)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 3
    tool, args_json = sys.argv[1], sys.argv[2]
    api_key = os.environ.get("DEEPSONAR_API_KEY")
    if not api_key:
        print(json.dumps({
            "error": "缺少 DEEPSONAR_API_KEY 环境变量",
            "hint": "密钥在管理工作台 dsc.solohub.art 的 API Keys 模块签发（dk_ 前缀）",
        }, ensure_ascii=False))
        return 3

    try:
        tool_args = json.loads(args_json)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"参数 JSON 解析失败: {e}"}, ensure_ascii=False))
        return 3

    try:
        # stateless 服务：直接请求 tools/call
        resp = rpc("tools/call", {"name": tool, "arguments": tool_args}, api_key, 1)
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 3

    if "error" in resp:
        print(json.dumps({"tool": tool, "is_error": True,
                          "content": [{"type": "text", "text": json.dumps(resp["error"],
                                       ensure_ascii=False)}]}, ensure_ascii=False))
        return 2

    result = resp.get("result", {})
    is_error = bool(result.get("isError"))
    print(json.dumps({"tool": tool, "is_error": is_error,
                      "content": result.get("content", [])},
                     ensure_ascii=False, indent=2))
    return 2 if is_error else 0


if __name__ == "__main__":
    sys.exit(main())
