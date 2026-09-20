# 报告输入 JSON 契约（render_report.py 的唯一输入格式）

> `scripts/render_report.py` 对该契约做严格校验与强鲁棒性容错。
> 输入必须为 **JSON Object/Dict 根节点**（缺少 `meta` / `overall` / `dimensions` / `findings` 将阻断并返回退出码 1）。
> 评分必须按本文公式计算，禁止拍脑袋给分。

---

## 一、完整契约 Schema

```json
{
  "meta": {
    "title": "报告标题（建议：账号/素材名 + 日期）",
    "video_source": "本地文件 xxx.mp4 或抖音链接 https://v.douyin.com/xxx/",
    "platform": "douyin",
    "duration_sec": 46.2,
    "shot_count": 21,
    "generated_at": "2026-09-20 15:04",
    "model_used": "qwen3-omni-flash (direct) 或 <agent模型> (fallback)",
    "deepsonar_rules_cited": 3
  },
  "overall": {
    "score": 59,
    "risk_level": "high | medium | low | safe",
    "decision": "暂缓投放 | 整改后发布 | 可发布",
    "summary": "依据：一句话点最硬证据；约束：一句话点监管/平台约束；行动：一句话给首要动作"
  },
  "risk_counts": {"high": 2, "medium": 1, "low": 0},
  "dimensions": [
    {"key": "speech",        "label": "口播合规",   "score": 50, "note": "命中 2 处绝对化用语 (high×2)"},
    {"key": "onscreen",      "label": "画面文字",   "score": 90, "note": "包装宣称 1 处疑似 (low)"},
    {"key": "extreme_words", "label": "极限词密度", "score": 50, "note": "最低 / 第一 各 1 处"},
    {"key": "price_promo",   "label": "价格促销",   "score": 75, "note": "全网最低价 1 处 (high)"},
    {"key": "evidence",      "label": "资质证据",   "score": 60, "note": "“检测报告认证”无对应画面镜头 (medium×2)"}
  ],
  "timeline": [
    {"start": 0.0, "end": 3.0, "level": "safe", "label": "镜头1"},
    {"start": 3.0, "end": 7.0, "level": "high", "label": "镜头2-3"}
  ],
  "transcript": [
    {"start": 0.0, "end": 3.0, "text": "口播原句（直接取 lacing_result.transcript）"}
  ],
  "findings": [
    {
      "time_range": "00:03–00:07",
      "severity": "high | medium | low",
      "category": "极限词 / 功效宣称 / 资质与数据引证 / 比较性宣传 / 名称一致性 / 表达与效果暗示 / 价格宣传 / 其他",
      "excerpt": "触发违规的原文（口播或屏幕文字原句）",
      "keywords": ["全网最低价"],
      "source": "口播 或 画面文字",
      "clauses": [
        {
          "rule_name": "规则名（透传 cited_sources[].rule_name / get_rule_detail meta.title，禁止改写）",
          "rule_url": "官方原文链接（只能透传 cited_sources[].rule_url 或 get_rule_detail meta.url；禁止编造/拼接。缺失时整个 finding 降级 verified=false）",
          "clause_text": "get_rule_detail 全文中支撑判定的条款原文摘录",
          "penalty": "惩罚力度（全文中的处罚标准，如“扣信用分 2 分 / 限制投放”，无则省略该字段）"
        }
      ],
      "suggestion": "可执行的整改建议（给出合规替换思路）",
      "rewrite": "改后文案：该条对应的具体替换句（纯文本，无论是否自带引号，渲染器均会规范包裹单一「」）",
      "verified": true
    }
  ],
  "fixes": [
    "【高风险】将“全网最低价”替换为可证实的真实价格对比表述...",
    "【高风险】删除“效果第一”等绝对化用语..."
  ],
  "rewritten_script": {
    "text": "整合全部修改建议后的合规版完整口播稿（保持原稿种草力度，可直接替换配音脚本）",
    "notes": "核心修改点对照说明（多行文本，渲染器自动换行保留排版）"
  },
  "pending_verifications": [
    {
      "item": "待核验事项（如检测报告原件真实性与对外授权）",
      "owner": "责任方（法规 / 品控 / 品牌运营 / 投放）",
      "method": "核实方式与依据（如核对报告原件、CMA 资质认证及药监局备案公示）"
    }
  ]
}
```

---

## 二、关键字段排版与鲁棒性规程（与渲染器严格对齐）

### 1. `overall.summary` 三段式铁律
- 必须严格遵循 **依据 / 约束 / 行动** 三段式结构：
  - `依据：` 最硬的核心违规证据（如「口播含『全网最低价』『效果第一』绝对化用语，且检测报告带内部审核水印」）
  - `约束：` 平台或法规刚性底线（如「祛痘类功效宣称须有人体功效评价报告并按规定公开摘要」）
  - `行动：` 首要可执行动作（如「完成 2 项高风险整改、核验检测报告原件与备案名称后再行投放」）
- 渲染器已内建智能识别：会自动将 `依据：`、`约束：`、`行动：` 结构化加粗并分行呈现，确保专业 SaaS 仪表盘的严谨层次。

### 2. 分镜时间轴（Timeline）色带与逐字稿高亮逻辑一致性
- **镜头切分与短编号规范**：
  - `label` 必须采用 `镜头N` 或 `镜头A-B`（如 `镜头1`、`镜头2-3`、`镜头4-8`）；
  - 渲染器自动格式化为规范的两位补零短编号（`#01`、`#02-03`、`#04-08`），保证等宽对齐美感；
  - **高密度密集分镜三阶自适应**：宽切片（\(\ge 4.2\%\)）呈现 `#01` 全称；中窄切片（\(1.6\% \sim 4.2\%\)）自适应精简为纯数字 `1`、`3`、`4`，杜绝生硬隐藏导致的部分切片空白残缺；极窄闪切（\(<1.6\%\)）呈现纯白中心微圆点（Micro Pip），赋予可触碰交互点。
- **色带等级与台词高亮的一一对应原则（杜绝色带乱闪）**：
  - **逻辑闭环**：镜头的 `level`（safe/low/medium/high）必须**严格**由该时间窗内命中的违规 `severity` 推导决定！
  - 若某分镜为 `high`，其对应的口播或画面在该时段内**必须且必定存在**对应的违规事实；
  - 严禁出现“分镜色带标红，但悬浮浮层逐字稿内全是白字、无任何违规高亮”的逻辑断层！
  - 若该分镜为安全镜头，色带必须为绿色（`safe`）。

### 3. 改后参考文案 `rewrite` 引号规范
- `rewrite` 字段可以直接输入纯文本，或者输入带引号的文本；
- 渲染器内置了首尾引号清洗机制，自动过滤多余的外层直角引号，保证最终生成的 HTML 始终展现优雅的单一 `「...」` 包装，杜绝 `「「...」」` 视觉瑕疵。

### 4. 03 违规命中明细（1:1 左右横向工作台）
- 违规事实卡片采用左右两栏工作台布局：
  - **左栏**：违规原文（`excerpt`，支持 `keywords` 精准色标高亮）+ 官方规则依据（`clauses`：规则名超链接、处罚力度胶囊、法条正文）；
  - **右栏**：整改思路（`suggestion`）+ 改后参考文案（`rewrite`）；
  - 官方链接 `rule_url` 必须通过 `safe_url` 校验，只能透传官方真实链接，杜绝伪协议。

---

## 三、五维定义与确定性评分公式

### 维度 → findings 归属映射

| 维度 key | 维度名称 | 归属的 finding | 初始分 |
| --- | --- | --- | --- |
| `speech` | 口播合规 | source=口播 且 category∉价格宣传 | 100 |
| `onscreen` | 画面文字 | source=画面文字 | 100 |
| `extreme_words` | 极限词密度 | category=极限词（不论来源） | 100 |
| `price_promo` | 价格促销 | category=价格宣传（最低价/比价/促销话术） | 100 |
| `evidence` | 资质证据 | category=资质缺失 或 功效宣称无画面佐证 | 100 |

### 扣分规则

对归属到某维度的每条 finding，按 severity 扣分：
- **high −25 分**
- **medium −10 分**
- **low −5 分**
疑似未核验（`verified: false`）扣分减半（high −12 / medium −5 / low −2，取整）。
维度得分 = `max(0, 100 − Σ扣分)`。无 finding 归属的维度为 100 分。

### 整体分、风险等级与发布决策公式

```
overall.score = round(0.5 × min(五维) + 0.5 × mean(五维))
risk_level:
  score < 60  → high（高风险）
  60 ≤ score < 85 → medium（中风险）
  score ≥ 85  → safe / low（安全合规 / 低风险）

decision（发布决策）：
  暂缓投放   —— score < 60，或存在任一 verified 的 high 命中
  整改后发布 —— 60 ≤ score < 85，或存在 medium 及以上命中
  可发布     —— score ≥ 85 且无 medium 及以上命中
```

---

## 四、渲染前自检清单（Agent 必须逐项核对）

在调用 `render_report.py` 之前，Agent 必须对照本清单自查 `report_input.json`：
- [ ] **根节点结构**：根节点必须为 Dict，且包含 `meta`, `overall`, `dimensions`, `findings` 四大必需字段；
- [ ] **决策三段式完整性**：`overall.summary` 必须包含 `依据：`、`约束：`、`行动：` 完整内容；
- [ ] **分镜与色带逻辑对齐**：检查时间轴每个镜头的 `level` 是否与实际违规命中的时间窗严格对应，杜绝色带与逐字稿高亮脱节；
- [ ] **时间单调性**：`duration_sec` > 0，分镜起止时间单调递增，首个分镜 `start=0.0`；
- [ ] **法条原文与外链保真**：`clauses[].rule_url` 必须为有效 HTTP(S) 链接，无官方链接则留空，由渲染器降级显示；
- [ ] **执行与退出码**：运行 `python3 scripts/render_report.py <input> -o <output>`，必须确认返回码为 0，报告文件成功生成。
