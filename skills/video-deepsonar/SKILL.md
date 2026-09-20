---
name: video-deepsonar
description: DeepSonar（深纳）视频「拉片 + 风控归因」一体化分析。当用户提供电商短视频/直播切片文件、分享链接、口播文案或视频截图，并希望评估内容违规风险（极限词、功效宣称、价格宣传、资质缺失等）、做发布前预审、或解码处罚通知时使用。遵循两大核心准则：①「MCP管线优先」——在具备配置条件时优先安装MCP并重启会话，以原生Tool Call交互式推进归因；②「全模态模型自省优先」——Agent首先自省自身能力，Gemini全系及具备音视频理解的多模态模型直接输入原始视频端到端直出拉片，彻底杜绝机械抽帧导致的分镜失准与单独ASR脱节。最终调用DeepSonar MCP规则库做违规归因与孤证不立全文核验，用scripts/render_report.py产出单文件离线HTML风控报告（现代专业云母白/深海蓝 SaaS 显控台风格，与 demo.html 1:1 像素级拟合）。触发词：拉片、视频风控、违规检测、发布前预审、内容合规、极限词检测、video risk analysis、shot-by-shot review、deepsonar。
license: Proprietary
compatibility: python3 >= 3.9（全部脚本仅标准库）；ffmpeg + ffprobe（备用兜底抽帧及音视频探测）；网络访问（直连 DeepSonar MCP 需要）；可选环境变量：DEEPSONAR_API_KEY（DeepSonar MCP 鉴权，dk_ 前缀，官方用户社群分发）。
metadata:
  product: DeepSonar
  current_platform: douyin
  version: 2.0.0
---

# DeepSonar 视频拉片风控分析（v2.0 全模态 & 原生 MCP 架构）

把「看视频」变成「高确定性的交付报告」：
**全模态原生拉片 → 原生 DeepSonar MCP 交互归因 → 单文件离线 HTML 报告（深海声纳显控台）。**

---

## ⚡ 核心设计准则（两项铁律与超级第一原则）

### 1. 准则一：MCP 管线优先（超级第一原则：自动写入后必须暂停并要求重启会话）
- **超级第一原则（强制暂停）**：一旦 MCP 配置文件（如 `mcp_config.json`）自动写入成功，**Agent 必须立即强制暂停一切后续动作，向用户汇报已写入的配置路径，并明确要求用户重启当前会话（Session）或重启终端/IDE**。必须经历完整的「写入配置 → 强制暂停 → 用户重启会话」流程！
- **绝对禁止偷跑**：**除非用户明确说明“不允许重启”或“无法重启，授权单次脚本临时直调”，否则绝对严禁直接调用 `mcp_call.py` 这个 Python 文件绕过原生工具！** 这是最高优先级铁律，任何情况下不得擅自使用 `mcp_call.py` 代替原生重启流程。
- **最佳实践**：会话重启后，Agent 将在自身原生工具树（Toolbox）中直接获得 6 个原生 MCP 工具（4 大核心风控：`search_rules` / `diagnose_risk` / `get_rule_detail` / `list_platforms` + 2 大免费自查：`get_usage` / `get_data_version`），全流程在思考链中以原生 Tool Call 交互推进。

### 2. 准则二：全模态模型自省优先（禁止多模态模型抽帧降级）
- **最佳实践**：进入拉片阶段前，Agent **必须首先检查自身模型能力**。
- **Gemini 全系首选**：若当前 Agent 为 Gemini 全系（天然原生支持长视频连续输入）或具备音视频理解能力的多模态模型，**必须直接将原生 MP4/MOV 视频文件输入 Agent 自身**，音画同源毫秒级对齐，一次性端到端直出严格符合 Schema 的拉片 JSON！
- **彻底废除机械像素差抽帧**：严禁在 Agent 具备全模态能力时搞 `extract_frames.py` 抽帧与单独 ASR 拼接！基于像素差的抽帧不仅把主播手部晃动误判为分镜、漏切平滑转场，还会导致台词与画面严重脱节。

---

## 平台范围

当前仅开放 **抖音（douyin）** 规则库（DeepSonar 平台开放白名单以 `list_platforms` 返回的 `open` 字段为准，架构按多平台预留）。用户要求未开放平台时，显式拒绝并说明当前开放状态，严禁编造结论。

---

## 总工作流（四阶段闭环）

```
阶段 0: MCP 检查与接入 ──► 阶段 1: 模型自省与全模态拉片 ──► 阶段 2: 原生 MCP 交互归因 ──► 阶段 3: 报告渲染交付
```

---

### 阶段 0：MCP 状态检查与环境安装（开工前置，超级第一原则）

1. **检查原生工具**：检查当前会话是否存在 4 大核心工具（`search_rules`, `diagnose_risk`, `get_rule_detail`, `list_platforms`）及 2 大免费工具（`get_usage`, `get_data_version`）。
2. **若已存在**：直接进入阶段 1。
3. **若不存在**：
   - **【凭据获取铁律（严禁旁路嗅探）】**：检查环境变量 `DEEPSONAR_API_KEY`。若未配置，**必须且只能在对话中显式向用户索取**（dk_ 前缀，官方用户社群分发）。**绝对严禁**利用当前项目可能具备的 Supabase MCP、本地数据库连接、历史日志或配置文件等任何旁路手段跨系统私自查询、捞取用户的 API Key！
   - 获取到用户提供的 Key 后，运行自动安装器：
     ```bash
     python3 scripts/install_mcp.py --key dk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
     ```
   - **【超级第一原则·强制暂停】**：安装器成功写入配置后，**必须立即暂停一切后续操作，向用户明确汇报配置写入路径，并要求用户重启当前会话（Session）或重启终端**。必须经历这个暂停等待过程！
   - **【绝对红线】**：除非用户在交互中明确表示“不允许重启/无法重启，并特许本次直接调用临时脚本”，否则**绝对禁止**调用 `scripts/mcp_call.py` 这个 Python 文件偷跑！未获用户明确许可擅自调用视为严重违规。

---

### 阶段 1：模型能力自省与拉片执行

拉片 prompt 与输出 JSON schema 的唯一真源是 `references/lacing_prompt.md`。字段名不得改写、不得增删字段。

#### 1-A 首选：Agent 原生全模态直出（Gemini 全系 / 多模态模型）
- **自省判断**：若当前 Agent 模型为 Gemini 全系（如 Gemini 3.8 Flash、Gemini 2.5 Pro 等）或具备长视频理解能力：
- **执行**：
  1. 直接以原始视频文件（MP4/MOV）输入 Agent 自身；
  2. 严格携带最新版 `references/lacing_prompt.md`（时序优先版）作为 Instruction；
  3. **遵循时序视觉优先（Visual Cut First）**：以机位跳切、微距特写与动作突变为唯一切镜依据，严禁以台词断句合并分镜，高灵敏捕捉 1~2 秒级微切镜（如固定发夹、旋转出液特写、报告柱状图闪切、质地推开等，标准电商视频通常产出约 21 镜）；
  4. 利用全模态模型的音画连续感知能力，**端到端一次性输出**包含真实镜头切换、包装微小文字、口播逐字稿、宣称的严格 JSON；
  5. 将生成的 JSON 落盘保存为 `work/lacing_result.json`。

#### 1-B 次选：自动化独立云端 API（非 Agent 交互/批处理脚本）
运行脚本直接调用云端多模态 API（Gemini File API / 百炼 / 火山）：
```bash
python3 scripts/call_lacing_model.py --provider gemini --model gemini-2.5-flash \
  --video <视频路径> --prompt-file references/lacing_prompt.md \
  -o work/lacing_result.json
```

#### 1-C 极限兜底：纯文本模型无 API Key 回退管线
仅当 Agent 为纯文本模型且无任何云端 API Key 时，方可运行：
```bash
python3 scripts/extract_frames.py <视频路径> -o work/frames
```
注意：回退模式输出必须人工复核镜头数与时间戳准确性。

---

### 阶段 2：DeepSonar MCP 原生交互归因

在 Agent 自身的思考链中，以**原生 Tool Call** 的方式交互式完成归因与核验（严格遵守 `references/mcp_integration.md` 规程）：

1. **调用 `list_platforms()`**：确认平台处于开放白名单（douyin.open == true）。
2. **多维度分批调用 `diagnose_risk()`**：
   - ① **口播全文诊断**：送入口播逐字稿，排查绝对化表述与功效保证；
   - ② **品名一致性诊断**：将「口播宣称品名」与「拉片中提取的实物包装备案名」送入对比，排查私改品名、超范围宣传；
   - ③ **资质凭证核查**：排查宣称第三方检测报告、专利却未出示画面的行为；
   - ④ **高危宣称单独诊断**：对极限词、根治性描述单独送检，防止长文稀释。
3. **调用 `get_rule_detail()` 全文核验（孤证不立）**：
   - 每一条拟写入报告的违规结论，**必须**调用 `get_rule_detail(rule_id=...)` 调阅官方清洗后 Markdown 全文；
   - 核验全文是否有明确法条支持，提取处罚力度条款，并透传官方原文链接（`meta.url`）；
   - 证据不全或已下架规则降级为「疑似」，标 `verified: false`。
4. **存疑细则补充检索**：对边界模糊词汇调用 `search_rules()` 检索细则。

---

### 阶段 3：报告渲染与交付

1. **组装数据与渲染前自检（Pre-render Validation Checklist）**：
   Agent 必须按 `references/report_schema.md` 契约组装 `report_input.json`，并对照自查：
   - [ ] **根节点结构**：必须为 Object/Dict 根节点，含 `meta`, `overall`, `dimensions`, `findings`；
   - [ ] **决策依据三段式**：`overall.summary` 必须包含「`依据：`」「`约束：`」「`行动：`」三段式完整结构；
   - [ ] **分镜时间轴短编号与色带闭环**：
     - 镜头 `label` 规范使用「镜头1」「镜头2-3」等，渲染器自动格式化为两位补零 `#01`、`#02-03`；
     - 镜头 `level` 必须严格与该时段内命中的违规 `severity` 一致，杜绝色带与逐字稿高亮脱节；
   - [ ] **违规明细横向工作台**：每项均需包含清晰的违规原文（`excerpt`）、法条正文与外链（`clauses`）、整改思路（`suggestion`）与具体改后文案（`rewrite`）；
   - [ ] **评分确定性**：五维评分及 overall.score 严格按公式推导，禁止主观臆造。
2. **单文件离线 HTML 渲染与健壮性执行**：
   ```bash
   python3 scripts/render_report.py work/report_input.json -o 风控报告.html
   ```
   **容错与自愈要求**：检查执行退出码是否为 `0`；若为非零，根据 stderr 报错信息进行针对性契约修正并重跑，确保交付产物 100% 完整可用。
3. **交付规范**：
   - 交付 HTML 本地绝对路径；
   - 在对话中用 3 行以内总结：**整体风险等级与决策、最严重的一条命中、首要整改建议**；
   - 附合规口播替换稿与核心修改点说明。

---

## 🚫 核心红线

1. **MCP 管线优先（超级第一原则）**：自动写入配置后必须立即暂停，并要求用户重启会话/终端；除非用户明确不允许并特许单次直调，否则绝对禁止直接调用 `scripts/mcp_call.py` 偷跑！
2. **全模态禁止抽帧降级**：全模态模型（Gemini 全系）必须直接吃视频原生直出拉片，禁止倒退回切图拼片模式。
3. **孤证不立**：判定类结论必须通过 `get_rule_detail` 全文验证。
4. **官方链接绝对保真**：命中条款链接只能透传 MCP 返回的 `meta.url` 或 `rule_url`，严禁猜测或拼接。
5. **单文件离线交付**：报告必须完全离线可用，零外链、内联 SVG 显控台。
6. **凭据严禁旁路嗅探**：未配置 API Key 时必须由用户通过对话显式提供或通过环境变量注入，绝对严禁擅自通过数据库、内部表或系统日志等旁路手段私自捞取凭证。

---

## 📂 工具脚本索引

- `scripts/install_mcp.py` — DeepSonar MCP 一键安装器（写入各客户端配置）
- `scripts/deepsonar_stdio_mcp.py` — 标准 Stdio MCP 桥接适配器（跨客户端通用）
- `scripts/render_report.py` — 单文件离线 HTML 风控报告渲染器（声纳显控台主题）
- `scripts/call_lacing_model.py` — 独立自动化脚本直连云端多模态 API（CI/CD 或无 Agent 场景）
- `scripts/mcp_call.py` — 极限受限沙箱环境下的应急 HTTP 直连兜底
- `scripts/extract_frames.py` — 极限纯文本环境下的回退抽帧兜底
- `references/mcp_setup.md` — MCP 安装与配置指南（一键安装与多端配置）
- `references/model_priority.md` — 模型自省与全模态视频输入规范
- `references/mcp_integration.md` — 原生 Tool Call 交互归因规程
- `references/lacing_prompt.md` — 标准拉片 Prompt 与输出 JSON Schema
- `references/report_schema.md` — 报告输入 Schema 契约与五维评分公式
