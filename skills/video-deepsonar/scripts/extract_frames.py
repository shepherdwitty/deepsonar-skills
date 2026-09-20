#!/usr/bin/env python3
"""标准化回退拉片管线：ffmpeg 场景抽帧 + 均匀补帧 + 音频提取。

产出帧目录与 manifest.json，供 agent 自身多模态模型配合
references/lacing_prompt.md 的固定 prompt 完成拉片。

用法：
    python3 extract_frames.py <视频路径> -o <输出目录> [--interval 2.0] [--scene-threshold 0.3]

输出（stdout，JSON）：manifest 摘要；完整 manifest 写入 <输出目录>/manifest.json：
    {"video": ..., "duration_sec": ..., "audio": "audio.wav 或 null",
     "frames": [{"file": ..., "ts": 秒, "kind": "scene|uniform"}]}
退出码：0 成功；1 ffmpeg/ffprobe 缺失；2 视频读取失败。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys

PTS_RE = re.compile(r"pts_time:([0-9.]+)")


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def probe_duration(video: str) -> float:
    proc = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video,
    ])
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe 读取失败: {proc.stderr[-300:]}")
    return float(proc.stdout.strip())


def extract_scene_frames(video: str, outdir: str, threshold: float) -> list[dict]:
    """场景切换检测抽帧；从 showinfo 日志解析每帧 pts_time。"""
    pattern = os.path.join(outdir, "scene_%04d.jpg")
    proc = run([
        "ffmpeg", "-y", "-i", video,
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-vsync", "vfr", "-q:v", "3", pattern,
    ])
    pts = [float(m.group(1)) for m in PTS_RE.finditer(proc.stderr)]
    frames = []
    files = sorted(f for f in os.listdir(outdir) if f.startswith("scene_"))
    for i, fname in enumerate(files):
        ts = pts[i] if i < len(pts) else None
        frames.append({"file": fname, "ts": round(ts, 2) if ts is not None else None,
                       "kind": "scene"})
    return frames


def extract_uniform_frames(video: str, outdir: str, duration: float,
                           interval: float, covered: list[float]) -> list[dict]:
    """按固定间隔在未被场景帧覆盖的时间点补帧（-ss 精确定位，时间戳精确）。"""
    frames = []
    n = max(1, math.floor(duration / interval))
    idx = 0
    for k in range(n):
        ts = round(k * interval + interval / 2, 2)
        if ts >= duration:
            break
        # 已有 ±interval/2 内的场景帧则跳过，避免重复
        if any(abs(ts - c) < interval / 2 for c in covered):
            continue
        fname = f"uniform_{idx:04d}.jpg"
        proc = run(["ffmpeg", "-y", "-ss", str(ts), "-i", video,
                    "-frames:v", "1", "-q:v", "3", os.path.join(outdir, fname)])
        if proc.returncode == 0 and os.path.exists(os.path.join(outdir, fname)):
            frames.append({"file": fname, "ts": ts, "kind": "uniform"})
            idx += 1
    return frames


def extract_audio(video: str, outdir: str) -> str | None:
    """提取 16kHz 单声道 wav（agent 模型支持音频输入时使用）。"""
    path = os.path.join(outdir, "audio.wav")
    proc = run(["ffmpeg", "-y", "-i", video, "-vn", "-ac", "1", "-ar", "16000", path])
    return "audio.wav" if proc.returncode == 0 and os.path.exists(path) else None


def main() -> int:
    parser = argparse.ArgumentParser(description="回退拉片管线：抽帧 + 音频提取")
    parser.add_argument("video", help="视频文件路径")
    parser.add_argument("-o", "--outdir", required=True, help="帧输出目录")
    parser.add_argument("--interval", type=float, default=2.0, help="均匀补帧间隔秒数（默认 2.0）")
    parser.add_argument("--scene-threshold", type=float, default=0.3, help="场景切换阈值（默认 0.3）")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        print(json.dumps({"error": "ffmpeg/ffprobe 未安装",
                          "install": "macOS: brew install ffmpeg"}, ensure_ascii=False))
        return 1

    os.makedirs(args.outdir, exist_ok=True)
    try:
        duration = probe_duration(args.video)
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 2

    frames = extract_scene_frames(args.video, args.outdir, args.scene_threshold)
    covered = [f["ts"] for f in frames if f["ts"] is not None]
    frames += extract_uniform_frames(args.video, args.outdir, duration,
                                     args.interval, covered)
    frames.sort(key=lambda f: (f["ts"] if f["ts"] is not None else 1e9))
    audio = extract_audio(args.video, args.outdir)

    manifest = {
        "video": os.path.abspath(args.video),
        "duration_sec": round(duration, 2),
        "audio": audio,
        "frames": frames,
    }
    manifest_path = os.path.join(args.outdir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "manifest": manifest_path,
        "duration_sec": manifest["duration_sec"],
        "frame_count": len(frames),
        "audio": audio,
        "next": "把帧（按 ts 升序）与 audio.wav（若 agent 模型支持音频）连同 "
                "references/lacing_prompt.md 的完整 prompt 喂给 agent 自身多模态模型，"
                "输出严格符合其 schema 的 JSON，落盘 work/lacing_result.json",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
