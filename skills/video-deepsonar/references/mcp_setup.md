# DeepSonar MCP 安装与配置指南（超级第一原则：配置后强制暂停重启版）

> **超级第一原则：配置写入后强制暂停，必须由用户重启会话！**
> 
> 任何能够安装或配置 MCP 的 Agent 环境，**自动写入配置后，必须立即强制暂停一切后续动作，向用户明确汇报配置写入路径，并要求用户重启当前会话（Session）或重启终端/IDE**。
> **必须经历完整的「写入配置 → 强制暂停 → 用户重启会话」流程！**
> **除非用户在交互中明确表示“不允许重启/无法重启，特许本次临时直调”，否则绝对严禁擅自调用 `scripts/mcp_call.py` 这个 Python 文件偷跑！**
> 
> **凭据获取铁律（严禁旁路越权嗅探）**：
> 密钥的唯一合法来源是**用户在对话中显式提供**或**系统预置环境变量**。即使当前运行环境具备数据库读取能力（如挂载了 Supabase MCP 或具备本地 DB 连接），Agent 也**绝对不允许**私自执行 SQL 查询 `api_keys` 等表去捞取密钥凭证，必须严格在对话中向用户索要！

---

## 一、一键自动安装（推荐首选）

在具备 Python 环境的终端或 Agent 对话中运行一键安装器：

```bash
# 方式 1：传参安装
python3 scripts/install_mcp.py --key dk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 方式 2：读取环境变量安装
export DEEPSONAR_API_KEY=dk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
python3 scripts/install_mcp.py
```

该脚本会自动自省当前运行的 Agent 宿主环境（Antigravity、Claude Code、Cursor 等），**仅对当前检测到的单一宿主精准注入配置**，严禁跨客户端全量污染其他软件；也可通过 `--client [antigravity|claude|cursor]` 显式指定目标。

**【超级第一原则】安装后关键动作（强制暂停流程）**：
1. **立即暂停**：安装器写入成功后，Agent 必须停下后续所有分析、拉片或归因动作，不得擅自执行。
2. **要求重启**：向用户明确提示已成功写入的配置文件路径，要求用户 **重启当前会话（Session）** 或重新打开终端/IDE。
3. **激活原生工具**：会话重启后，Agent 将自动在原生工具树中挂载 6 个原生 MCP 工具：
   1. `search_rules` — 跨平台风控规则知识库语义/标题检索
   2. `diagnose_risk` — 违规归因与发布前预审主力诊断
   3. `get_rule_detail` — 调阅清洗后官方规则全文（孤证不立核验必经）
   4. `list_platforms` — 平台开放状态与分类字典
   5. `get_usage` 🆓 — API Key 剩余额度与有效期自查（不扣配额）
   6. `get_data_version` 🆓 — 规则库数据更新时间与新鲜度自查（不扣配额）

---

## 二、主流客户端手动配置指南

若需手动维护配置，可按当前使用的客户端任选其一：

### 1. Antigravity / Gemini CLI
在全局配置文件 `~/.gemini/antigravity/mcp_config.json` 或 `~/.gemini/config/mcp_config.json` 的 `mcpServers` 中添加：

```json
{
  "mcpServers": {
    "deepsonar": {
      "type": "http",
      "url": "https://api.deepsonar.help/api/mcp",
      "serverUrl": "https://api.deepsonar.help/api/mcp",
      "headers": {
        "Authorization": "Bearer dk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

### 2. Claude Code
运行 Claude 官方 MCP 注册命令（直接支持 Streamable HTTP 传输）：

```bash
claude mcp add --transport http deepsonar https://api.deepsonar.help/api/mcp \
  --header "Authorization: Bearer dk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

### 3. Cursor / VS Code (Roo Code)
在 `~/.cursor/mcp.json` 或项目级 `.cursor/mcp.json` 中配置：

```json
{
  "mcpServers": {
    "deepsonar": {
      "type": "http",
      "url": "https://api.deepsonar.help/api/mcp",
      "headers": {
        "Authorization": "Bearer dk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

---

## 三、调试三连（原生工具冒烟）

重启 Session 后，在对话中或通过原生 tool call 直接验证：

1. **平台闸门**：调用 `list_platforms()`，确认返回 `douyin.open == true`。
2. **语义检索**：调用 `search_rules(query="发货超时处罚标准", platform="douyin", limit=3)`，应返回高相关度的规则 chunk。
3. **归因冒烟**：调用 `diagnose_risk(content="全场最低价，宇宙第一", platform="douyin")`，应返回命中极限词及相关细则。

三步全绿即证明 MCP 原生接入完美生效，后续全流程一律直接在思考链中通过原生 Tool Call 交互式完成！

---

## 四、极限应急兜底通道（严禁擅自偷跑，仅限用户明确特许）

**当且仅当同时满足以下条件且获得用户明确书面授权时，才允许使用 `scripts/mcp_call.py`**：
1. 运行环境为只读沙箱，或用户在 Agent 暂停提醒后明确指令：“不允许/无法重启会话，特许本次单次临时直调”；
2. **严禁在未征得用户明确许可前由 Agent 自行决定调用**。

用法：
```bash
export DEEPSONAR_API_KEY=dk_xxxxxxxx
python3 scripts/mcp_call.py list_platforms '{}'
```
