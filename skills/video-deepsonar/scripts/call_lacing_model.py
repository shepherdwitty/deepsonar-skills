#!/usr/bin/env python3
"""拉片模型直连统一封装（Gemini / 火山方舟 / 阿里百炼）。

仅标准库。provider 与 model 必须由 probe_models.py 的路由决策给出，不得自行指定其他组合。
各平台输入方式对齐生产实践（参考 fangtan 项目 lacing 集成）：

- gemini    ：File API 续传上传（X-Goog-Upload-URL 响应头）→ 轮询 ACTIVE →
              generateContent(fileData) → 用完删除；凭证 GOOGLE_AI_API_KEY（兼容 GEMINI_API_KEY）
- ark       ：Responses API（POST /api/v3/responses）；--video-url ≤50MB 走 input_video.video_url，
              否则 multipart 上传 /api/v3/files（preprocess_configs fps=0.3）→ input_video.file_id；
              凭证 ARK_API_KEY；模型 ID 带日期快照（如 doubao-seed-2-0-lite-260428）
- dashscope ：OpenAI 兼容 chat/completions；video_url 仅接受公网可访问 URL（--video-url），
              本地文件必须走 --frames-manifest 抽帧模式（base64 图片列表）；
              凭证 DASHSCOPE_API_KEY；modalities=["text"] + reasoning_effort="none"

用法：
    python3 call_lacing_model.py --provider gemini --model gemini-3.5-flash-lite \
        --video work/video.mp4 --prompt-file references/lacing_prompt.md -o work/lacing_result.json
    python3 call_lacing_model.py --provider dashscope --model qwen3.8-omni-flash \
        --video-url https://example.com/v.mp4 --prompt-file references/lacing_prompt.md -o out.json
    python3 call_lacing_model.py --provider dashscope --model qwen3.8-omni-flash \
        --frames-manifest work/frames/manifest.json --prompt-file references/lacing_prompt.md -o out.json

退出码：0 成功；2 凭证/输入缺失；3 请求/网络失败；4 响应不符合 schema；5 视频过大或格式不受支持。
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

REQUIRED_KEYS = ["video_meta", "transcript", "shots", "full_transcript_text",
                 "all_on_screen_text"]
MAX_VIDEO_BYTES = 500 * 1024 * 1024          # Gemini File API 上限远大于此，本地兜底
ARK_DIRECT_VIDEO_MAX_BYTES = 50 * 1024 * 1024
FRAMES_MODE_MAX = 40                          # 抽帧模式喂图上限
ARK_VIDEO_FPS = 0.3
GEMINI_POLL_INTERVAL_SEC = 2
GEMINI_POLL_MAX_SEC = 120
MAX_RETRIES = 2                               # 429/5xx 重试次数

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_UPLOAD_BASE = "https://generativelanguage.googleapis.com/upload/v1beta"
ARK_API_BASE = "https://ark.cn-beijing.volces.com/api/v3"
DASHSCOPE_CHAT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"


# ------------------------------------------------------------------ 基础

def http_request(url: str, headers: dict, data: bytes | None,
                 method: str = "POST", timeout: int = 600) -> tuple[dict, dict]:
    """返回 (响应 JSON 或 {}, 响应头)。429/5xx 由调用方按 should_retry 处理。"""
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return (json.loads(raw) if raw.strip() else {}), dict(resp.headers)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:800]
        err = RuntimeError(f"HTTP {e.code}: {detail}")
        err.status = e.code  # type: ignore[attr-defined]
        raise err from e


def should_retry(err: RuntimeError) -> bool:
    status = getattr(err, "status", 0)
    return status == 429 or status >= 500


def with_retry(fn, what: str):
    last = None
    for attempt in range(MAX_RETRIES + 1):
        if attempt:
            time.sleep(1.5 * (2 ** (attempt - 1)))
        try:
            return fn()
        except RuntimeError as e:
            last = e
            if not should_retry(e):
                raise
    raise last or RuntimeError(f"{what} 重试次数已用尽")


def extract_json(text: str) -> dict:
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("响应中未找到 JSON 对象")
    return json.loads(s[start:end + 1])


def validate_schema(obj: dict) -> list[str]:
    return [k for k in REQUIRED_KEYS if k not in obj]


def video_mime(path: str) -> str:
    return mimetypes.guess_type(path)[0] or "video/mp4"


# ---------------------------------------------------------------- Gemini

def gemini_upload(path: str, api_key: str) -> dict:
    """File API 续传上传：session → PUT 字节流 → 返回 {name, uri}。"""
    size = os.path.getsize(path)
    mime = video_mime(path)
    display = os.path.basename(path).replace("/", "-")[:100]
    _, headers = http_request(
        f"{GEMINI_UPLOAD_BASE}/files?key={api_key}",
        {
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(size),
            "X-Goog-Upload-Header-Content-Type": mime,
            "Content-Type": "application/json",
        },
        json.dumps({"file": {"display_name": display}}).encode("utf-8"),
        timeout=60,
    )
    upload_url = headers.get("X-Goog-Upload-URL") or headers.get("x-goog-upload-url")
    if not upload_url:
        raise RuntimeError("Gemini 上传 session 未返回 X-Goog-Upload-URL 响应头")
    with open(path, "rb") as f:
        data = f.read()
    resp, _ = http_request(
        upload_url,
        {
            "X-Goog-Upload-Command": "upload, finalize",
            "X-Goog-Upload-Offset": "0",
            "Content-Type": mime,
        },
        data, method="PUT", timeout=900,
    )
    file_info = resp.get("file", {})
    if not file_info.get("name"):
        raise RuntimeError(f"Gemini 上传未返回文件资源: {str(resp)[:300]}")
    return {
        "name": file_info["name"],
        "uri": file_info.get("uri") or f"{GEMINI_API_BASE}/{file_info['name']}",
    }


def gemini_wait_active(name: str, api_key: str) -> None:
    """视频上传后可能处于 PROCESSING，轮询至 ACTIVE。"""
    deadline = time.time() + GEMINI_POLL_MAX_SEC
    while time.time() < deadline:
        resp, _ = http_request(f"{GEMINI_API_BASE}/{name}?key={api_key}", {},
                               None, method="GET", timeout=30)
        state = resp.get("state", "")
        if state == "ACTIVE":
            return
        if state == "FAILED":
            raise RuntimeError(f"Gemini 文件处理失败: {str(resp.get('error'))[:300]}")
        time.sleep(GEMINI_POLL_INTERVAL_SEC)
    raise RuntimeError(f"Gemini 文件处理超时（{GEMINI_POLL_MAX_SEC}s）")


def gemini_delete(name: str, api_key: str) -> None:
    try:
        http_request(f"{GEMINI_API_BASE}/{name}?key={api_key}", {},
                     None, method="DELETE", timeout=30)
    except Exception:
        pass  # 48h 自动过期，清理失败不阻塞主流程


def call_gemini(model: str, video: str, prompt: str, api_key: str) -> dict:
    handle = with_retry(lambda: gemini_upload(video, api_key), "Gemini 上传")
    try:
        gemini_wait_active(handle["name"], api_key)

        def _call():
            resp, _ = http_request(
                f"{GEMINI_API_BASE}/models/{model}:generateContent?key={api_key}",
                {"Content-Type": "application/json"},
                json.dumps({
                    "contents": [{"parts": [
                        {"text": prompt},
                        {"fileData": {"mimeType": video_mime(video),
                                      "fileUri": handle["uri"]}},
                    ]}],
                    "generationConfig": {"temperature": 0.2},
                }).encode("utf-8"),
                timeout=600,
            )
            return resp

        resp = with_retry(_call, "Gemini generateContent")
    finally:
        gemini_delete(handle["name"], api_key)
    parts = resp.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = next((p["text"] for p in parts if isinstance(p.get("text"), str)), "")
    if not text:
        raise RuntimeError("Gemini 未返回文本")
    return extract_json(text)


# -------------------------------------------------------------------- Ark

def ark_upload(path: str, api_key: str) -> str:
    """multipart 上传至 /files，返回 file_id（24h 过期）。"""
    boundary = uuid.uuid4().hex
    mime = video_mime(path)
    filename = os.path.basename(path)
    expire_at = str(int(time.time()) + 24 * 3600)
    with open(path, "rb") as f:
        file_bytes = f.read()

    parts = []
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"expire_at\"\r\n\r\n{expire_at}\r\n".encode())
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"preprocess_configs[video][fps]\"\r\n\r\n{ARK_VIDEO_FPS}\r\n".encode())
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
        f"Content-Type: {mime}\r\n\r\n".encode() + file_bytes + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)

    resp, _ = http_request(
        f"{ARK_API_BASE}/files",
        {"Authorization": f"Bearer {api_key}",
         "Content-Type": f"multipart/form-data; boundary={boundary}"},
        body, timeout=900,
    )
    file_id = resp.get("id") or resp.get("file_id")
    if not file_id:
        raise RuntimeError(f"Ark 上传未返回 file_id: {str(resp)[:300]}")
    return file_id


def ark_delete(file_id: str, api_key: str) -> None:
    try:
        http_request(f"{ARK_API_BASE}/files/{file_id}", {"Authorization": f"Bearer {api_key}"},
                     None, method="DELETE", timeout=30)
    except Exception:
        pass


def ark_parse_text(payload: dict) -> str:
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        text = "".join(c.get("text", "") for c in item.get("content", [])
                       if c.get("type") == "output_text").strip()
        if text:
            return text
    return ""


def call_ark(model: str, video: str | None, video_url: str | None,
             prompt: str, api_key: str) -> dict:
    file_id = None
    if video_url and not video:
        media_input = {"type": "input_video", "video_url": video_url, "fps": ARK_VIDEO_FPS}
    else:
        assert video is not None
        size = os.path.getsize(video)
        if size <= ARK_DIRECT_VIDEO_MAX_BYTES and video_url:
            media_input = {"type": "input_video", "video_url": video_url, "fps": ARK_VIDEO_FPS}
        else:
            file_id = with_retry(lambda: ark_upload(video, api_key), "Ark 上传")
            media_input = {"type": "input_video", "file_id": file_id}

    body = {
        "model": model,
        "input": [{"role": "user", "content": [
            media_input,
            {"type": "input_text", "text": prompt},
        ]}],
        "temperature": 0.2,
        "thinking": {"type": "disabled"},
        "reasoning_effort": "minimal",
    }
    try:
        def _call():
            resp, _ = http_request(
                f"{ARK_API_BASE}/responses",
                {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json.dumps(body).encode("utf-8"), timeout=600,
            )
            return resp

        resp = with_retry(_call, "Ark responses")
    finally:
        if file_id:
            ark_delete(file_id, api_key)
    text = ark_parse_text(resp)
    if not text:
        raise RuntimeError("Ark 未返回拉片文本")
    return extract_json(text)


# --------------------------------------------------------------- DashScope

def call_dashscope(model: str, prompt: str, api_key: str,
                   video_url: str | None, frames_manifest: str | None) -> dict:
    if video_url:
        media_content = [{"type": "video_url", "video_url": {"url": video_url}}]
    elif frames_manifest:
        with open(frames_manifest, encoding="utf-8") as f:
            manifest = json.load(f)
        frames = manifest.get("frames", [])[:FRAMES_MODE_MAX]
        if not frames:
            raise RuntimeError("frames manifest 中无帧数据")
        media_content = []
        base_dir = os.path.dirname(os.path.abspath(frames_manifest))
        for fr in frames:
            path = os.path.join(base_dir, fr["file"])
            b64 = base64.b64encode(open(path, "rb").read()).decode("ascii")
            ts = fr.get("ts")
            label = f"[帧 {ts}s]" if ts is not None else "[帧]"
            media_content.append({"type": "text", "text": label})
            media_content.append({"type": "image_url",
                                  "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        prompt += ("\n\n【输入说明】当前为抽帧模式：输入为按时间戳标注的关键帧图片序列，无音轨。"
                   "transcript 只能依据画面字幕/口型推断，无法确认的一律填 [无法辨认]；"
                   "shots.audio 字段描述画面可见信息即可，不得臆造 BGM/音效。")
    else:
        raise RuntimeError(
            "dashscope 需要 --video-url（公网可访问 URL）或 --frames-manifest（抽帧模式）"
            "二选一；本地视频文件不能直传——先运行 extract_frames.py 再选抽帧模式")

    body = {
        "model": model,
        "messages": [{"role": "user", "content": media_content + [
            {"type": "text", "text": prompt}]}],
        "temperature": 0.2,
        "modalities": ["text"],
        "reasoning_effort": "none",
    }

    def _call():
        resp, _ = http_request(
            DASHSCOPE_CHAT_URL,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json.dumps(body).encode("utf-8"), timeout=600,
        )
        return resp

    resp = with_retry(_call, "DashScope chat")
    content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
    if isinstance(content, list):
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    if not content.strip():
        raise RuntimeError("DashScope 未返回文本")
    return extract_json(content)


# -------------------------------------------------------------------- main

def resolve_api_key(provider: str) -> tuple[str | None, str]:
    if provider == "gemini":
        for env in ("GOOGLE_AI_API_KEY", "GEMINI_API_KEY"):
            if os.environ.get(env):
                return os.environ[env], env
        return None, "GOOGLE_AI_API_KEY 或 GEMINI_API_KEY"
    env = {"ark": "ARK_API_KEY", "dashscope": "DASHSCOPE_API_KEY"}[provider]
    return os.environ.get(env), env


def main() -> int:
    parser = argparse.ArgumentParser(description="拉片模型直连统一封装")
    parser.add_argument("--provider", required=True,
                        choices=["gemini", "dashscope", "ark"])
    parser.add_argument("--model", required=True,
                        help="probe_models.py 路由给出的模型 ID（Ark 需带日期快照）")
    parser.add_argument("--video", help="本地视频路径（gemini/ark 直连可用）")
    parser.add_argument("--video-url", help="公网可访问视频 URL（dashscope 必需；ark 可选）")
    parser.add_argument("--frames-manifest",
                        help="extract_frames.py 产出的 manifest.json（dashscope 本地文件抽帧模式）")
    parser.add_argument("--prompt-file", required=True,
                        help="references/lacing_prompt.md 路径")
    parser.add_argument("-o", "--output", default="work/lacing_result.json")
    args = parser.parse_args()

    api_key, env_name = resolve_api_key(args.provider)
    if not api_key:
        print(json.dumps({"error": f"缺少 {env_name} 环境变量",
                          "hint": "重新运行 probe_models.py 获取路由决策"},
                         ensure_ascii=False))
        return 2

    if args.provider in ("gemini", "ark") and not args.video and not args.video_url:
        print(json.dumps({"error": f"{args.provider} 需要 --video 或 --video-url"},
                         ensure_ascii=False))
        return 2
    if args.video:
        size = os.path.getsize(args.video)
        if size > MAX_VIDEO_BYTES:
            print(json.dumps({"error": f"视频 {size / 1048576:.0f}MB 超过 500MB 上限",
                              "hint": "先用 ffmpeg 压缩"}, ensure_ascii=False))
            return 5

    with open(args.prompt_file, encoding="utf-8") as f:
        prompt = f.read()

    t0 = time.time()
    try:
        if args.provider == "gemini":
            if not args.video:
                raise RuntimeError("gemini 通道当前仅支持本地 --video（File API 上传）")
            result = call_gemini(args.model, args.video, prompt, api_key)
        elif args.provider == "ark":
            result = call_ark(args.model, args.video, args.video_url, prompt, api_key)
        else:
            result = call_dashscope(args.model, prompt, api_key,
                                    args.video_url, args.frames_manifest)
    except RuntimeError as e:
        msg = str(e)
        hint = ""
        if "HTTP 400" in msg:
            hint = ("视频格式/大小可能不受该模型支持：压缩视频或回退 extract_frames.py "
                    "标准化管线（禁止换用未经路由的其他模型）")
        elif "HTTP 401" in msg or "HTTP 403" in msg:
            hint = "凭证无效或额度不足，重新运行 probe_models.py 让路由降级"
        print(json.dumps({"error": msg, "hint": hint}, ensure_ascii=False))
        return 3
    latency = round(time.time() - t0, 1)

    missing = validate_schema(result)
    if missing:
        print(json.dumps({
            "error": f"模型输出缺少 schema 必需字段: {missing}",
            "hint": "重试一次；仍失败则回退 extract_frames.py 标准化管线",
        }, ensure_ascii=False))
        return 4

    result.setdefault("model_used", {})
    result["model_used"].update({
        "provider": args.provider, "model": args.model,
        "mode": "direct", "latency_sec": latency,
    })

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({"output": args.output, "latency_sec": latency,
                      "shots": len(result.get("shots", [])),
                      "transcript_lines": len(result.get("transcript", []))},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
