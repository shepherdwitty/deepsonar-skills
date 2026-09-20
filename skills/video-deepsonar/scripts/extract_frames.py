#!/usr/bin/env python3
"""标准化回退拉片管线：双引擎（系统 ffmpeg 或免依赖 PyAV）抽帧 + 均匀补帧 + 音频提取。

产出帧目录、manifest.json 与 16kHz 单声道 audio.wav，供后续 ASR 与多模态拉片使用。
智能环境探测：
  1. 优先使用系统 ffmpeg/ffprobe（速度最快）；
  2. 若系统无 ffmpeg，自动平滑无缝回退到 PyAV (av 库)，彻底解决无 brew/受限环境死穴；
  3. 若两者皆无，输出友好一键就绪指引：pip install av pillow numpy。

用法：
    python3 extract_frames.py <视频路径> -o <输出目录> [--interval 1.0] [--scene-threshold 0.3]

输出（stdout，JSON）：manifest 摘要；完整 manifest 写入 <输出目录>/manifest.json。
退出码：0 成功；1 依赖环境缺失；2 视频读取失败。
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


# ─────────────────────────────────────────────────────────────
# 引擎 A：系统 FFmpeg / FFprobe 路线
# ─────────────────────────────────────────────────────────────

def probe_duration_ffmpeg(video: str) -> float:
    proc = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video,
    ])
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe 读取失败: {proc.stderr[-300:]}")
    return float(proc.stdout.strip())


def extract_scene_frames_ffmpeg(video: str, outdir: str, threshold: float) -> list[dict]:
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
        frames.append({"file": fname, "ts": round(ts, 2) if ts is not None else None, "kind": "scene"})
    return frames


def extract_uniform_frames_ffmpeg(video: str, outdir: str, duration: float,
                                  interval: float, covered: list[float]) -> list[dict]:
    frames = []
    n = max(1, math.floor(duration / interval))
    idx = 0
    for k in range(n):
        ts = round(k * interval + interval / 2, 2)
        if ts >= duration:
            break
        if any(abs(ts - c) < interval / 2 for c in covered):
            continue
        fname = f"uniform_{idx:04d}.jpg"
        proc = run(["ffmpeg", "-y", "-ss", str(ts), "-i", video,
                    "-frames:v", "1", "-q:v", "3", os.path.join(outdir, fname)])
        if proc.returncode == 0 and os.path.exists(os.path.join(outdir, fname)):
            frames.append({"file": fname, "ts": ts, "kind": "uniform"})
            idx += 1
    return frames


def extract_audio_ffmpeg(video: str, outdir: str) -> str | None:
    path = os.path.join(outdir, "audio.wav")
    proc = run(["ffmpeg", "-y", "-i", video, "-vn", "-ac", "1", "-ar", "16000", path])
    return "audio.wav" if proc.returncode == 0 and os.path.exists(path) else None


# ─────────────────────────────────────────────────────────────
# 引擎 B：纯 Python PyAV (免安装系统 FFmpeg，受限环境利器)
# ─────────────────────────────────────────────────────────────

def extract_with_pyav(video: str, outdir: str, interval: float) -> tuple[float, list[dict], str | None]:
    import av
    from PIL import Image

    container = av.open(video)
    if not container.streams.video:
        raise RuntimeError("视频文件中未找到视频流")

    video_stream = container.streams.video[0]
    duration_sec = float(container.duration / av.time_base) if container.duration else 0.0

    # 1. 抽取 16kHz 单声道 WAV 音频
    audio_filename = None
    if container.streams.audio:
        audio_stream = container.streams.audio[0]
        audio_path = os.path.join(outdir, "audio.wav")
        out_c = av.open(audio_path, mode="w")
        out_s = out_c.add_stream("pcm_s16le", rate=16000)
        out_s.layout = "mono"
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)

        # 单独遍历音频帧
        audio_container = av.open(video)
        for frame in audio_container.decode(audio_container.streams.audio[0]):
            for r_frame in resampler.resample(frame):
                for packet in out_s.encode(r_frame):
                    out_c.mux(packet)
        for packet in out_s.encode(None):
            out_c.mux(packet)
        out_c.close()
        audio_container.close()
        if os.path.exists(audio_path):
            audio_filename = "audio.wav"

    # 2. 均匀抽帧
    frames: list[dict] = []
    target_times = []
    t = 0.0
    while t < duration_sec:
        target_times.append(round(t, 2))
        t += interval

    curr_target_idx = 0
    frame_idx = 0
    v_container = av.open(video)
    for frame in v_container.decode(v_container.streams.video[0]):
        if curr_target_idx >= len(target_times):
            break
        frame_time = float(frame.pts * video_stream.time_base) if frame.pts is not None else 0.0
        if frame_time >= target_times[curr_target_idx]:
            img = frame.to_image()
            fname = f"frame_{frame_idx:04d}_{frame_time:.1f}s.jpg"
            img.save(os.path.join(outdir, fname), quality=85)
            frames.append({
                "file": fname,
                "ts": round(frame_time, 2),
                "kind": "uniform"
            })
            frame_idx += 1
            curr_target_idx += 1

    v_container.close()
    container.close()
    return duration_sec, frames, audio_filename


# ─────────────────────────────────────────────────────────────
# CLI 入口与双引擎调度
# ─────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="回退拉片管线：双引擎抽帧 + 音频提取")
    parser.add_argument("video", help="视频文件路径")
    parser.add_argument("-o", "--outdir", required=True, help="帧输出目录")
    parser.add_argument("--interval", type=float, default=1.0, help="抽帧间隔秒数（默认 1.0）")
    parser.add_argument("--scene-threshold", type=float, default=0.3, help="场景切换阈值（默认 0.3，仅 ffmpeg 引擎生效）")
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    has_ffmpeg = (shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None)

    try:
        import av  # noqa: F401
        has_pyav = True
    except ImportError:
        has_pyav = False

    if not has_ffmpeg and not has_pyav:
        print(json.dumps({
            "error": "未检测到系统 ffmpeg，且 Python 环境未安装 PyAV",
            "solution": "受限环境推荐免系统依赖安装：pip install av pillow numpy faster-whisper",
            "sop_guide": "references/fallback_sop.md"
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    engine_used = "ffmpeg" if has_ffmpeg else "pyav"
    try:
        if engine_used == "ffmpeg":
            duration = probe_duration_ffmpeg(args.video)
            frames = extract_scene_frames_ffmpeg(args.video, args.outdir, args.scene_threshold)
            covered = [f["ts"] for f in frames if f["ts"] is not None]
            frames += extract_uniform_frames_ffmpeg(args.video, args.outdir, duration, args.interval, covered)
            frames.sort(key=lambda f: (f["ts"] if f["ts"] is not None else 1e9))
            audio = extract_audio_ffmpeg(args.video, args.outdir)
        else:
            duration, frames, audio = extract_with_pyav(args.video, args.outdir, args.interval)

    except Exception as e:
        print(json.dumps({"error": f"视频解包失败（引擎 {engine_used}）: {e}"}, ensure_ascii=False), file=sys.stderr)
        return 2

    manifest = {
        "video": os.path.abspath(args.video),
        "duration_sec": round(duration, 2),
        "engine_used": engine_used,
        "audio": audio,
        "frames": frames,
    }
    manifest_path = os.path.join(args.outdir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "manifest": manifest_path,
        "duration_sec": manifest["duration_sec"],
        "engine_used": engine_used,
        "frame_count": len(frames),
        "audio": audio,
        "next_step": "音频已提取为 audio.wav。请立即在后台运行 ASR，同时在前台进行画面核读（参见 references/fallback_sop.md）。"
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
