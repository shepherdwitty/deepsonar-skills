# 拉片模型优先级与路由规程（全模态自省优先版）

> **核心设计准则：全模态模型自省优先，禁止对多模态模型搞抽帧降级！**
>
> 现代全模态大模型（特别是 **Gemini 全系**）原生支持连续音视频输入，具备毫秒级时间感知与音画对齐能力。
> **在 Agent 具备全模态能力时，严禁使用 ffmpeg 抽帧截屏与单独 ASR 拼接！**
> 抽帧截屏只会切碎镜头连续性、造成分镜漏切/误切（因像素差误判），并导致口播与画面脱节。

---

## 一、三层路由决策树（严格按序）

```
[输入视频 MP4/MOV]
       │
       ▼
【第 1 优先级：Agent 模型能力自省 (Self-Inspection)】
   当前 Agent 是否为具备音视频理解的全模态模型？
   （包括但不限于 Gemini 全系: Gemini 1.5/2.0/3.x Flash/Pro、Claude 3.5 Sonnet 多模态、GPT-4o 等）
       ├─ 是 ──► 【原生视频直出模式】直接将 MP4 输入 Agent 自身模型，端到端直出拉片 JSON
       │
       └─ 否（纯代码/纯文本 Agent）
              │
              ▼
【第 2 优先级：自动化独立云端 API (Direct Cloud API)】
   环境是否配置了云端多模态 API Key？
   （GOOGLE_AI_API_KEY / GEMINI_API_KEY / DASHSCOPE_API_KEY / ARK_API_KEY）
       ├─ 有 ──► 调用 call_lacing_model.py 直接调用云端模型拉片
       │
       └─ 无
              │
              ▼
【第 3 优先级：极限环境回退管线 (Fallback)】
   无全模态 Agent，且无任何云端多模态 API Key
       └──► 仅在此极限条件下，允许执行 scripts/extract_frames.py 本地抽帧与转录
```

---

## 二、第 1 优先级详解：Gemini 全系原生视频直出

当宿主 Agent 运行在 Gemini 3.8 Flash、Gemini 2.5 Pro、Gemini 1.5 Pro/Flash 或同等全模态模型时：

### 1. 为什么必须使用原生视频输入？
- 🎬 **真·时序视觉剪辑切分（Visual Cut First）**：模型依据视听语言逻辑感知画面真实物理切镜（机位变换、景别推进、微距特写、主体动作突变）。**绝对禁止按口播台词断句合并镜头**，一句台词跨越多个动作时（如固定刘海发夹瞬切为旋转笔尾出液特写），必须精准切为独立镜头（切片密度达 1~2 秒级，标准电商短视频通常产出约 21 镜）；
- 🎙️ **音画解耦原生对齐**：口播台词与画面动作各自保留真实时序，允许无口播纯画面特写（如报告柱状图露出、质地推开），杜绝单独 ASR 造成的口播绑架分镜与时间戳漂移；
- 🔍 **动态视频 OCR 与证据锁定**：模型在视频流中动态锁定包装微小备案名、套盒全称、检测报告编号、页码及「仅供资质审核」等水印角标；
- ⚡ **秒级端到端零垃圾文件**：无需在磁盘生成任何中间 jpg 切片，单次端到端直出标准 21 镜拉片 JSON。

### 2. 执行规范
- 直接读取原始视频文件（如 `view_file(video_path)` 或 Agent 多模态上下文注入通道）；
- 严格携带最新版 `references/lacing_prompt.md`（时序优先版）作为 Instruction，强制输出单层合法 JSON；
- 产出后对照自查清单核验镜头密度（严防低于 16 镜的粗切合并）；立即落盘至 `work/lacing_result.json`，直接进入阶段 2 的 MCP 归因。

---

## 三、第 2 优先级：自动化直连 API（无 Agent 交互场景）

主要用于 CI/CD 流水线、Nightly 定时任务或无 Agent 介入的纯脚本环境：

```bash
# Gemini File API 直连
python3 scripts/call_lacing_model.py \
  --provider gemini --model gemini-2.5-flash \
  --video <视频路径> --prompt-file references/lacing_prompt.md \
  -o work/lacing_result.json
```

质量档参考链：
`Gemini 2.5 Flash / Qwen 3.8 Omni Flash > Doubao Seed 2.0 Lite > Gemini 3.5 Flash Lite`

---

## 四、第 3 优先级：极限回退模式（最后防线）

当且仅当满足以下**全部**条件：
1. Agent 自省判定自身**完全不具备**多模态能力（纯文本模型）；
2. 宿主环境变量中**没有任何**云端多模态 API Key；
3. 用户明确要求必须就地完成拉片。

此时方可运行：
```bash
python3 scripts/extract_frames.py <视频路径> -o work/frames
```
注意：回退模式下的分镜表与时间戳必须经过严格自查，并在 `model_used.mode` 中标注为 `fallback`。
