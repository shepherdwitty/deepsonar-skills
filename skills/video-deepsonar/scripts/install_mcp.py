#!/usr/bin/env python3
"""DeepSonar MCP 一键安装器（纯原生 HTTP MCP 架构）。

直接将 DeepSonar 的原生 HTTP MCP 端点（https://api.deepsonar.help/api/mcp）
及 Authorization Bearer Key 写入宿主环境配置（Antigravity / Claude Code / Cursor），
彻底杜绝任何本地中间代理脚本，端到端直连。

用法：
    python3 install_mcp.py [--key dk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx]
    # 或预先 export DEEPSONAR_API_KEY=dk_xxxx 后直接运行：
    python3 install_mcp.py
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

MCP_ENDPOINT = "https://api.deepsonar.help/api/mcp"


def update_json_config(path: str, server_config: dict) -> bool:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    mcp_servers = data.setdefault("mcpServers", {})
    mcp_servers["deepsonar"] = server_config
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        sys.stderr.write(f"写入 {path} 失败: {e}\n")
        return False


def detect_current_client() -> str:
    """自省检测当前 Agent 宿主环境，返回 antigravity / claude / cursor 或 unknown。"""
    # 1. Antigravity 宿主特征
    if any(k.startswith("ANTIGRAVITY_") for k in os.environ):
        return "antigravity"
    # 2. Claude Code 宿主特征
    if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE") or os.environ.get("USER_TYPE") == "claude":
        return "claude"
    # 3. Cursor 宿主特征
    if any("cursor" in v.lower() for k, v in os.environ.items() if k.startswith(("CURSOR_", "VSCODE_"))):
        return "cursor"
    return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description="DeepSonar 原生 HTTP MCP 一键安装器")
    parser.add_argument("--key", help="DeepSonar API 密钥（dk_ 前缀）")
    parser.add_argument(
        "--client",
        choices=["auto", "antigravity", "claude", "cursor"],
        default="auto",
        help="目标客户端（默认 auto，仅自动检测并配置当前运行宿主）",
    )
    args = parser.parse_args()

    api_key = args.key or os.environ.get("DEEPSONAR_API_KEY")
    if not api_key:
        sys.stderr.write("错误: 请提供 API 密钥（--key dk_... 或设置 DEEPSONAR_API_KEY 环境变量）\n")
        return 1

    if not api_key.startswith("dk_"):
        sys.stderr.write("警告: API 密钥通常以 dk_ 开头，请确认密钥格式是否正确\n")

    # 确定目标客户端
    target_client = args.client
    if target_client == "auto":
        target_client = detect_current_client()
        if target_client == "unknown":
            sys.stderr.write(
                "错误: 未能识别当前运行的 Agent 宿主环境。\n"
                "为防止污染其他工具配置，请显式指定目标: --client [antigravity|claude|cursor]\n"
            )
            return 1

    # 纯原生 HTTP MCP 配置
    native_http_config = {
        "type": "http",
        "url": MCP_ENDPOINT,
        "serverUrl": MCP_ENDPOINT,
        "headers": {
            "Authorization": f"Bearer {api_key}"
        }
    }

    home = os.path.expanduser("~")
    installed_target = ""

    # 仅针对检测到的单一宿主执行精准配置，严禁跨客户端全量污染
    if target_client == "antigravity":
        # ~/.gemini/antigravity/mcp_config.json 通常为指向 ~/.gemini/config/mcp_config.json 的软链
        target_path = os.path.join(home, ".gemini", "antigravity", "mcp_config.json")
        if not os.path.exists(os.path.dirname(target_path)):
            target_path = os.path.join(home, ".gemini", "config", "mcp_config.json")
        if update_json_config(target_path, native_http_config):
            installed_target = f"Antigravity ({target_path})"
        else:
            return 1

    elif target_client == "claude":
        if not shutil.which("claude"):
            sys.stderr.write("错误: 未找到 claude 命令，请确保已安装 Claude Code CLI\n")
            return 1
        cmd = [
            "claude", "mcp", "add", "--transport", "http", "deepsonar",
            MCP_ENDPOINT,
            "--header", f"Authorization: Bearer {api_key}"
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            installed_target = "Claude Code (HTTP transport)"
        else:
            sys.stderr.write(f"Claude MCP 注册失败: {proc.stderr}\n")
            return 1

    elif target_client == "cursor":
        cursor_path = os.path.join(home, ".cursor", "mcp.json")
        if update_json_config(cursor_path, native_http_config):
            installed_target = f"Cursor ({cursor_path})"
        else:
            return 1

    print("\n" + "=" * 60)
    print("🎉 DeepSonar 原生 HTTP MCP Server 已成功安装！")
    print("=" * 60)
    print(f"端点: {MCP_ENDPOINT}（纯原生 HTTP MCP，零本地中间脚本）")
    print(f"生效宿主: {installed_target}")

    print("\n⚠️ 关键提示：")
    print("  请 **重启当前会话（Session）** 或重新打开终端/IDE。")
    print("  重启后，以下 6 个原生 MCP 工具将自动注入 Agent 工具树：")
    print("    1. search_rules     — 平台规则知识库语义/标题双通道检索")
    print("    2. diagnose_risk    — 违规归因与发布前预审主力诊断")
    print("    3. get_rule_detail   — 调阅规则清洗后全文进行孤证不立核验")
    print("    4. list_platforms   — 平台开放白名单与分类字典")
    print("    5. get_usage        — 本 key 用量自查与有效期查询（免费工具，不扣配额）")
    print("    6. get_data_version — 规则库数据更新时间与新鲜度自查（免费工具，不扣配额）")
    print("=" * 60 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
