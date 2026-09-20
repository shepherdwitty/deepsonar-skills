# DeepSonar Skills 官方开源技能库

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![DeepSonar MCP](https://img.shields.io/badge/DeepSonar-MCP%20v2.0-0284c7.svg)](https://deepsonar.help)

DeepSonar（深纳）是面向电商平台（当前落地抖音电商）的专业规则风控归因系统。本仓库是 **DeepSonar 官方 Agent Skills 开源集合**，为各类主流 AI 编程助手与 Agent（Antigravity、Claude Code、Cursor、Gemini CLI 等）提供标准化、高精度的垂直领域内容风控与归因能力。

---

## 📦 技能矩阵 (Skills Index)

| 技能名称 | 核心定位 | 核心能力 | 支持客户端 |
| :--- | :--- | :--- | :--- |
| [`video-deepsonar`](skills/video-deepsonar/) | **短视频「拉片 + 风控归因」一体化** | • **全模态端到端直出拉片**（1~2秒级微视觉切镜，告别机械抽帧与ASR拼接脱节）<br>• **受限/纯文本 Agent 极限回退保障**（免 ffmpeg 双引擎抽帧、faster-whisper medium 离线 ASR、偏置纠错与音画互证 SOP，无缝兼容 Workbody/DeepSeek 等国产 Agent）<br>• **DeepSonar 原生 MCP 交互归因**（孤证不立全文核验、平台开放闸门）<br>• **单文件离线 HTML 显控台报告**（深海声纳主题、全分镜三阶自适应高亮、合规改写口播稿） | Antigravity, Claude Code, Cursor, Gemini CLI, Workbody |

*更多电商风控场景技能（直播切片预审、商品标题合规诊断、图文挂车排查等）正在持续同步中……*

---

## 🚀 快速安装与使用

### 方式 1：一键 Clone 到当前 Agent 技能目录

根据你所使用的 Agent 客户端，将本仓库克隆至对应 skills 目录：

```bash
# Antigravity 全局技能目录：
git clone https://github.com/shepherdwitty/deepsonar-skills.git ~/.gemini/antigravity/skills/deepsonar-skills

# 或当前项目级技能目录：
git clone https://github.com/shepherdwitty/deepsonar-skills.git .agents/skills/deepsonar-skills
```

### 方式 2：单技能即插即用

如仅需 `video-deepsonar` 技能：
1. 下载 `skills/video-deepsonar` 文件夹；
2. 放入你的 Agent 技能目录（如 `~/.gemini/antigravity/skills/video-deepsonar` 或项目目录）；
3. 在对话中直接输入指令即可唤起：
   ```bash
   /video-deepsonar <视频绝对路径或URL>
   ```

---

## ⚡ 配套 DeepSonar MCP 服务

本技能库深度联动 **DeepSonar 开放规则库 MCP 服务**（`https://api.deepsonar.help/api/mcp`），提供 6 大原生 MCP 工具：

- **4 大风控主力工具**：
  - `list_platforms` — 平台开放状态与分类字典
  - `search_rules` — 跨平台风控规则知识库语义/标题双通道检索
  - `diagnose_risk` — 违规归因与发布前预审主力诊断
  - `get_rule_detail` — 调阅清洗后官方规则全文（孤证不立核验必经）
- **2 大免费自查工具（🆓不扣减配额）**：
  - `get_usage` — API Key 剩余额度与有效期自查
  - `get_data_version` — 规则库数据更新时间与新鲜度自查

> **获取 API Key**：由 DeepSonar 官方社群分发（`dk_` 前缀）。

---

## 📄 开源许可证

本项目采用 [MIT License](LICENSE) 许可证。
