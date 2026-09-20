#!/usr/bin/env python3
"""抖音分享链接/口令 → 本地 MP4（yt-dlp 包装）。

支持直接粘贴整段分享口令（自动提取其中的 v.douyin.com 短链）。

用法：
    python3 download_douyin.py "<分享链接或整段口令>" [-o 输出目录]

输出（stdout，JSON）：{"video_path": ..., "id": ..., "title": ..., "duration_sec": ...}
退出码：0 成功；2 yt-dlp 缺失；3 未识别到链接；4 下载失败。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

URL_RE = re.compile(r"https?://[^\s\"'，。；）)]+")


def extract_url(text: str) -> str | None:
    """从分享口令中提取 URL（口令通常形如「7.94 复制打开抖音… https://v.douyin.com/xxx/ …」）。"""
    m = URL_RE.search(text)
    return m.group(0) if m else None


def main() -> int:
    parser = argparse.ArgumentParser(description="抖音分享链接下载（yt-dlp 包装）")
    parser.add_argument("share", help="抖音分享链接或整段分享口令")
    parser.add_argument("-o", "--outdir", default="work/downloads", help="输出目录")
    args = parser.parse_args()

    if shutil.which("yt-dlp") is None:
        print(json.dumps({
            "error": "yt-dlp 未安装",
            "install": "pip install -U yt-dlp  或  brew install yt-dlp",
        }, ensure_ascii=False))
        return 2

    url = extract_url(args.share)
    if not url:
        print(json.dumps({"error": "输入中未识别到 http(s) 链接", "input": args.share[:100]},
                         ensure_ascii=False))
        return 3

    os.makedirs(args.outdir, exist_ok=True)
    outtmpl = os.path.join(args.outdir, "%(id)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-f", "bv*+ba/b",
        "--merge-output-format", "mp4",
        "--print-json",
        "-o", outtmpl,
        url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(json.dumps({
            "error": "yt-dlp 下载失败",
            "stderr_tail": proc.stderr[-800:],
            "hint": "链接可能已失效或需要登录态；可请用户改为提供本地 MP4",
        }, ensure_ascii=False))
        return 4

    # --print-json 输出在 stdout（单行 JSON）
    info = json.loads(proc.stdout.strip().splitlines()[-1])
    video_path = info.get("filepath") or os.path.join(
        args.outdir, f"{info.get('id')}.{info.get('ext', 'mp4')}")
    print(json.dumps({
        "video_path": video_path,
        "id": info.get("id"),
        "title": info.get("title"),
        "duration_sec": info.get("duration"),
        "webpage_url": info.get("webpage_url"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
