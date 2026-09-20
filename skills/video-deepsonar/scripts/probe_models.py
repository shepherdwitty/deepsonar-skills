#!/usr/bin/env python3
"""拉片模型路由探针。

检测环境变量中的直连模型凭证与本地依赖，按 references/model_priority.md 的
优先级链输出唯一路由决策 JSON。Agent 必须严格按输出执行，不得自行另选模型。

用法：
    python3 probe_models.py [--prefer quality|speed]

输出（stdout，JSON）：
    direct 模式: {"mode": "direct", "provider": ..., "model": ..., "reason": ..., "chain": [...]}
    fallback 模式: {"mode": "fallback", "pipeline": "extract_frames", "reason": ..., "missing": {...}}
退出码：0 成功；1 参数错误。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

# 质量档降级链（依据 references/model_priority.md，顺序即优先级）。
# 注：gemini-3-flash-preview 已于 2026-09-20 移出路由链——Gemini 3.5 Flash Lite
# 速度更快且资费低 40%，全面覆盖其场景。
QUALITY_CHAIN = [
    {
        "provider": "dashscope",
        "model": "qwen3.8-omni-flash",
        "env": ["DASHSCOPE_API_KEY"],
        "note": "拉片质量/台词提取冠军：近300字口播逐句高精度听写，微观细节极敏锐（包装字样/检测图表）",
    },
    {
        "provider": "ark",
        "model": "doubao-seed-2-0-lite-260428",
        "env": ["ARK_API_KEY"],
        "note": "画面细腻度国内首选：1~2s 级密集切片，镜头动作描述细腻",
    },
    {
        "provider": "gemini",
        "model": "gemini-3.5-flash-lite",
        "env": ["GOOGLE_AI_API_KEY", "GEMINI_API_KEY"],
        "note": "高频/快速响应首选：纯推理 8.6s 全场最快之一，分镜 5 星",
    },
    {
        "provider": "ark",
        "model": "doubao-seed-2-0-mini-260428",
        "env": ["ARK_API_KEY"],
        "note": "低成本极速初筛：17.7s 端到端，分镜较粗（8~13s 粗切）仅作兜底",
    },
]

# 速度/成本档降级链（用户明确要求快/便宜时使用）。
SPEED_CHAIN = [
    {
        "provider": "ark",
        "model": "doubao-seed-2-0-mini-260428",
        "env": ["ARK_API_KEY"],
        "note": "极速初筛：17.7s 端到端，最低价档",
    },
    {
        "provider": "gemini",
        "model": "gemini-3.5-flash-lite",
        "env": ["GOOGLE_AI_API_KEY", "GEMINI_API_KEY"],
        "note": "快速响应首选：23.8s 端到端，分镜质量仍达 5 星",
    },
    {
        "provider": "dashscope",
        "model": "qwen3.8-omni-flash",
        "env": ["DASHSCOPE_API_KEY"],
        "note": "质量冠军但含深度思考，47.3s",
    },
    {
        "provider": "ark",
        "model": "doubao-seed-2-0-lite-260428",
        "env": ["ARK_API_KEY"],
        "note": "画面细腻但含深度思考，51.4s",
    },
]

ALL_ENVS = sorted({e for c in QUALITY_CHAIN for e in c["env"]})


def first_available_env(envs: list[str]) -> str | None:
    return next((e for e in envs if os.environ.get(e)), None)


def main() -> int:
    parser = argparse.ArgumentParser(description="拉片模型路由探针")
    parser.add_argument(
        "--prefer",
        choices=["quality", "speed"],
        default="quality",
        help="路由偏好：quality（默认，质量档降级链）/ speed（速度成本档降级链）",
    )
    args = parser.parse_args()

    chain = QUALITY_CHAIN if args.prefer == "quality" else SPEED_CHAIN
    chain_view = [
        {"rank": i + 1, "provider": c["provider"], "model": c["model"],
         "env": c["env"], "available": first_available_env(c["env"]) is not None}
        for i, c in enumerate(chain)
    ]

    for entry in chain:
        hit = first_available_env(entry["env"])
        if hit:
            print(json.dumps({
                "mode": "direct",
                "provider": entry["provider"],
                "model": entry["model"],
                "credential_env": hit,
                "reason": f"按 {args.prefer} 档降级链命中首个可用凭证 {hit}：{entry['note']}",
                "chain": chain_view,
            }, ensure_ascii=False, indent=2))
            return 0

    missing = {
        "api_keys": ALL_ENVS,
        "ffmpeg": shutil.which("ffmpeg") is None,
        "ffprobe": shutil.which("ffprobe") is None,
    }
    print(json.dumps({
        "mode": "fallback",
        "pipeline": "extract_frames",
        "reason": f"未检测到任何直连模型凭证（{' / '.join(ALL_ENVS)}），"
                  "走标准化回退：extract_frames.py 抽帧 + 固定 prompt 喂 agent 自身多模态模型",
        "chain": chain_view,
        "missing": missing,
        "hint": "ffmpeg/ffprobe 缺失时先安装（macOS: brew install ffmpeg），否则无法处理视频",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
