#!/usr/bin/env python3
"""离线 ASR 兜底转录与定向两级纠错工具（基于 faster-whisper）。

最佳实践封装：
  1. 默认设置国内镜像 HF_ENDPOINT=https://hf-mirror.com（杜绝下载卡死）；
  2. 默认基准档位 medium（杜绝 small 档中文“痘”变“斗”的系统性灾难）；
  3. 针对 Mac 平台固定 device="cpu", compute_type="int8"（内存友好，规避 Metal 不支持异常）；
  4. 支持 --slice 定向切片 + --prompt 领域词注入，用于高精两级纠错。

用法：
    # 1. 全片后台转录：
    python3 run_asr_fallback.py work/audio.wav -o work/asr_raw.json

    # 2. 定向切片偏置纠错（如 13.5s 到 18.0s）：
    python3 run_asr_fallback.py work/audio.wav --slice 13.5 18.0 \
      --prompt "就搭配消痘肌底液全脸薄涂" -o work/asr_slice.json

退出码：0 成功；1 依赖缺失；2 转录失败。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# 默认注入 HuggingFace 镜像源
if "HF_ENDPOINT" not in os.environ:
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"


def main() -> int:
    parser = argparse.ArgumentParser(description="faster-whisper 离线 ASR 与定向切片纠错工具")
    parser.add_argument("audio", help="输入的 WAV 音频文件路径（建议 16kHz 单声道）")
    parser.add_argument("-o", "--output", default="asr_result.json", help="输出 JSON 结果路径")
    parser.add_argument("--model", default="medium", choices=["medium", "large-v3", "small"],
                        help="Whisper 模型档位（严禁在垂类电商使用 small；默认 medium）")
    parser.add_argument("--slice", nargs=2, type=float, metavar=("START", "END"),
                        help="指定定向转录的时间窗切片（秒数，如 --slice 13.5 18.0）")
    parser.add_argument("--prompt", default="", help="领域词偏置文本（initial_prompt），用于纠正音近错字")
    parser.add_argument("--beam-size", type=int, default=5, help="Beam 搜索宽度（定向切片纠错时推荐 8）")
    args = parser.parse_args()

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print(json.dumps({
            "error": "未安装 faster-whisper 库",
            "solution": "请运行：pip install faster-whisper",
            "guide": "references/fallback_sop.md"
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    if not os.path.exists(args.audio):
        print(f"错误: 音频文件不存在: {args.audio}", file=sys.stderr)
        return 2

    audio_target = args.audio
    temp_slice_file = None

    # 若指定了切片，切出临时音频切片
    if args.slice:
        start_sec, end_sec = args.slice
        try:
            import numpy as np
            import wave
            with wave.open(args.audio, "rb") as wf:
                sr = wf.getframerate()
                nchannels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                start_frame = int(start_sec * sr)
                end_frame = int(end_sec * sr)
                wf.setpos(start_frame)
                frames_to_read = max(1, end_frame - start_frame)
                data = wf.readframes(frames_to_read)

            temp_slice_file = f"_temp_slice_{start_sec:.1f}_{end_sec:.1f}.wav"
            with wave.open(temp_slice_file, "wb") as out_wf:
                out_wf.setnchannels(nchannels)
                out_wf.setsampwidth(sampwidth)
                out_wf.setframerate(sr)
                out_wf.writeframes(data)
            audio_target = temp_slice_file
        except Exception as e:
            print(f"音频切片提取失败: {e}", file=sys.stderr)
            return 2

    try:
        # 模型下载缓存目录
        cache_dir = os.path.expanduser("~/.cache/whisper-ct2")
        os.makedirs(cache_dir, exist_ok=True)

        print(f"正在加载 Whisper 模型 [{args.model}]（CPU + int8 量化）...", file=sys.stderr)
        model = WhisperModel(args.model, device="cpu", compute_type="int8", download_root=cache_dir)

        transcribe_kwargs = {
            "language": "zh",
            "beam_size": 8 if args.slice else args.beam_size,
            "temperature": 0.0,
            "condition_on_previous_text": False if args.slice else True,
        }
        if args.prompt:
            transcribe_kwargs["initial_prompt"] = args.prompt

        print(f"开始转录音频: {audio_target} ...", file=sys.stderr)
        segments, info = model.transcribe(audio_target, **transcribe_kwargs)

        results = []
        offset = args.slice[0] if args.slice else 0.0
        for seg in segments:
            results.append({
                "start": round(seg.start + offset, 2),
                "end": round(seg.end + offset, 2),
                "text": seg.text.strip(),
            })

        output_data = {
            "model": args.model,
            "language": info.language,
            "language_probability": round(info.language_probability, 3),
            "is_slice": bool(args.slice),
            "slice_range": args.slice if args.slice else None,
            "hint_prompt": args.prompt if args.prompt else None,
            "transcript": results,
            "full_text": "".join(s["text"] for s in results),
        }

        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        print(f"转录完成，已保存至: {args.output}", file=sys.stderr)
        return 0

    except Exception as e:
        print(f"ASR 转录发生异常: {e}", file=sys.stderr)
        return 2

    finally:
        if temp_slice_file and os.path.exists(temp_slice_file):
            try:
                os.remove(temp_slice_file)
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
