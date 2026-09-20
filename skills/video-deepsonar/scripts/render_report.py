#!/usr/bin/env python3
"""风控报告渲染器：report_input.json → 单文件离线 HTML。

纯标准库、零外链、零 JS 依赖（动画为纯 CSS，可断网打开发送客户）。
视觉方向：现代专业云母白/深海蓝 SaaS 仪表盘风格（与 assets/demo.html 严格 1:1 像素级拟合）：
  · hero = 现代声纳显控台（PPI 渐变底盘 + 4道同心射程环 + 12方位角刻度齿 + 6s严格声纳物理同步扫描与回波）
  · timeline = 分镜全景时间轴（高密度三阶自适应编号 + 悬浮纯白微阴影浮层 + 磁吸交互）
  · findings = 1:1 左右横向工作台（左栏违规事实与规则裁决 + 右栏整改思路与改后可用文案对比）
  · 支持五维合规条形图、整改执行清单、合规改写口播稿、待人工核实清单、孤证不立全文核验

用法：
    python3 render_report.py report_input.json -o 风控报告.html

退出码：0 成功；1 输入 JSON 不合法或缺关键字段。
"""
from __future__ import annotations

import argparse
import html
import json
import math
import re
import sys

# ── 语义化色彩体系（来自 SaaS 现代仪表盘：深海声纳蓝 / 饱和温和风险色） ──
BRAND_BLUE = "#0284c7"
BRAND_BLUE_DEEP = "#0369a1"
RISK_HIGH = "#e11d48"
RISK_HIGH_BG = "#fff1f2"
RISK_HIGH_BORDER = "#fecdd3"
RISK_HIGH_TEXT = "#9f1239"

RISK_MED = "#d97706"
RISK_MED_BG = "#fffbeb"
RISK_MED_BORDER = "#fde68a"
RISK_MED_TEXT = "#92400e"

RISK_LOW = "#65a30d"
RISK_LOW_BG = "#f7fee7"
RISK_LOW_BORDER = "#d9f99d"
RISK_LOW_TEXT = "#3f6212"

RISK_SAFE = "#059669"
RISK_SAFE_BG = "#ecfdf5"
RISK_SAFE_BORDER = "#a7f3d0"
RISK_SAFE_TEXT = "#065f46"

LEVEL_COLOR = {
    "safe": RISK_SAFE,
    "low": RISK_LOW,
    "medium": RISK_MED,
    "high": RISK_HIGH,
}
LEVEL_LABEL = {
    "safe": "安全",
    "low": "低风险",
    "medium": "中风险",
    "high": "高风险",
}
PLATFORM_LABEL = {
    "douyin": "抖音",
    "kuaishou": "快手",
    "shipinhao": "视频号",
    "xiaohongshu": "小红书",
}


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def to_f(value, default: float = 0.0) -> float:
    """脏数据强制转 float：None/空串/非法字符串一律回退 default，不崩模板。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_url(value) -> str:
    """只放行 http(s) 链接，阻断 javascript: 等伪协议注入。"""
    s = str(value or "").strip()
    if s.startswith(("http://", "https://")):
        return esc(s)
    return "#"


def has_valid_url(value) -> bool:
    return str(value or "").strip().startswith(("http://", "https://"))


def score_color(score) -> str:
    sc = to_f(score, 100)
    if sc >= 85:
        return RISK_SAFE
    if sc >= 60:
        return RISK_MED
    return RISK_HIGH


def score_level(score) -> str:
    sc = to_f(score, 100)
    if sc >= 85:
        return "safe"
    if sc >= 60:
        return "medium"
    return "high"


def fmt_ts(sec) -> str:
    s = max(0, to_f(sec))
    return f"{int(s // 60):02d}:{int(s % 60):02d}"


def format_summary(raw: str) -> str:
    """智能将单行或多行 summary 格式化为现代 SaaS 仪表盘的三段式结构化展示。
    自动对「依据：」「约束：」「行动：」注入 <b> 标签并换行。
    """
    s = esc(raw.strip())
    s = s.replace("\n", "<br>")
    for prefix in ("约束：", "行动："):
        if f"<br>{prefix}" not in s and prefix in s:
            s = s.replace(prefix, f"<br><b>{prefix}</b>")
        else:
            s = s.replace(prefix, f"<b>{prefix}</b>")
    if "依据：" in s and "<b>依据：</b>" not in s:
        s = s.replace("依据：", "<b>依据：</b>")
    return s


# 品牌 Logo SVG（现代声纳显控标识，纯天蓝底色 + 纯白声纳波形）
LOGO_SVG = (
    '<svg viewBox="0 0 64 64" width="34" height="34" aria-label="DeepSonar">'
    '<rect width="64" height="64" rx="14" fill="#0284c7"/>'
    '<circle cx="32" cy="32" r="22" fill="none" stroke="#ffffff" stroke-width="2" opacity="0.3"/>'
    '<circle cx="32" cy="32" r="14" fill="none" stroke="#ffffff" stroke-width="1.8" opacity="0.5"/>'
    '<path d="M32 32 L32 10 A22 22 0 0 1 47.5 16.4 Z" fill="#ffffff" opacity="0.35"/>'
    '<line x1="32" y1="32" x2="47.5" y2="16.4" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round"/>'
    '<circle cx="41.5" cy="23.5" r="2.8" fill="#ffffff"/>'
    '<circle cx="32" cy="32" r="3.2" fill="#ffffff"/>'
    '</svg>'
)


# ---------------------------------------------------------------- 声纳显控屏 SVG

def sonar_screen_svg(dimensions: list[dict], size: int = 320) -> str:
    """现代专业声纳显控雷达图：
    - PPI 显控屏冷调渐变底盘
    - 4 道真实的同心射程环（Range Rings）
    - 12 方位角刻度齿（Tick Marks）
    - 5 条径向方位轴线
    - 多边形参考骨架（25/50/75/100）
    - 数据多边形
    - 6s 周期严格声纳物理同步动画（顺时针扫描线，扫过瞬间依次激活发光与扩散回波环，余辉后方拖曳）
    - 外圈大号加粗标签与得分
    """
    clean_dims = [d for d in dimensions if isinstance(d, dict)]
    n = len(clean_dims)
    if n < 3:
        return (
            f'<svg viewBox="-48 -14 416 348" width="350" height="295" class="sonar-svg" role="img" aria-label="声纳图">'
            f'<circle cx="160" cy="160" r="122" fill="#f0f7ff" stroke="#cbd5e1" stroke-width="1"/>'
            f'<text x="160" y="156" text-anchor="middle" fill="#64748b" font-size="13">评分维度数据不足 ({n}/3)</text>'
            f'<text x="160" y="176" text-anchor="middle" fill="#94a3b8" font-size="11">至少需要 3 个评估维度</text>'
            f'</svg>'
        )

    c = 160.0
    r = 122.0

    def point(i: int, ratio: float) -> tuple[float, float]:
        # 从 12 点钟（-pi/2）开始顺时针分布
        ang = -math.pi / 2 + 2 * math.pi * i / n
        return c + r * ratio * math.cos(ang), c + r * ratio * math.sin(ang)

    def dim_score(d: dict) -> float:
        return max(0.0, min(100.0, to_f(d.get("score"), 0.0)))

    lines = [
        '<svg viewBox="-48 -14 416 348" width="350" height="295" class="sonar-svg" role="img" aria-label="合规五维声纳显控图">',
        '<defs>',
        '  <radialGradient id="sonarDiscGrad" cx="50%" cy="50%" r="50%">',
        '    <stop offset="0%" stop-color="#f0f7ff" />',
        '    <stop offset="85%" stop-color="#e2eeff" />',
        '    <stop offset="100%" stop-color="#d6e8ff" />',
        '  </radialGradient>',
        '  <linearGradient id="sonarSweepGrad" x1="0%" y1="70%" x2="90%" y2="0%">',
        '    <stop offset="0%" stop-color="#0284c7" stop-opacity="0.0" />',
        '    <stop offset="50%" stop-color="#0284c7" stop-opacity="0.06" />',
        '    <stop offset="85%" stop-color="#0284c7" stop-opacity="0.18" />',
        '    <stop offset="100%" stop-color="#0284c7" stop-opacity="0.25" />',
        '  </linearGradient>',
        '</defs>',
        f'<circle cx="{c:.1f}" cy="{c:.1f}" r="{r:.1f}" fill="url(#sonarDiscGrad)" stroke="#0284c7" stroke-width="1.8" stroke-opacity="0.35"/>',
    ]

    # 4 道同心射程环
    for frac in (0.25, 0.50, 0.75, 1.00):
        radius = r * frac
        dash = ' stroke-dasharray="2 2"' if frac < 1.0 else ''
        width = "1.2" if frac == 1.0 else "1"
        op = "0.3" if frac == 1.0 else "0.2"
        lines.append(f'<circle cx="{c:.1f}" cy="{c:.1f}" r="{radius:.1f}" fill="none" stroke="#0284c7" stroke-width="{width}" stroke-opacity="{op}"{dash}/>')

    # 12 方位角刻度齿
    for k in range(12):
        deg = k * 30
        rad = math.radians(deg) - math.pi / 2
        is_cardinal = (k % 3 == 0)
        tick_len = 8.0 if is_cardinal else 5.0
        w = "1.8" if is_cardinal else "1.2"
        op = "0.5" if is_cardinal else "0.35"
        x1 = c + (r - tick_len) * math.cos(rad)
        y1 = c + (r - tick_len) * math.sin(rad)
        x2 = c + r * math.cos(rad)
        y2 = c + r * math.sin(rad)
        lines.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#0284c7" stroke-width="{w}" stroke-opacity="{op}"/>')

    # 多边形刻度骨架（25/50/75/100）
    for frac in (0.25, 0.50, 0.75, 1.00):
        pts = " ".join(f"{point(i, frac)[0]:.1f},{point(i, frac)[1]:.1f}" for i in range(n))
        op = "0.25" if frac == 1.0 else ("0.15" if frac == 0.75 else "0.12")
        w = "1.2" if frac == 1.0 else "0.8"
        lines.append(f'<polygon points="{pts}" fill="none" stroke="#0284c7" stroke-width="{w}" stroke-opacity="{op}"/>')

    # N 条径向方位轴线
    for i in range(n):
        x, y = point(i, 1.0)
        lines.append(f'<line x1="{c:.1f}" y1="{c:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke="#0284c7" stroke-width="1" stroke-opacity="0.25" stroke-dasharray="2 2"/>')

    # 声纳扇形旋转扫掠（6s 周期，柔和半透 1.4px 扫描光束 + 后方 -45° 衰减余辉拖尾）
    # 在 12 点钟位置（未旋转状态）：扫描线从 (160, 160) 到 (160, 38)
    # -45° 尾迹点：x = 160 - 122*sin(45°) = 73.7, y = 160 - 122*cos(45°) = 73.7
    lines.append(
        '<g class="sweep">'
        '  <path d="M 160.0 160.0 L 73.7 73.7 A 122.0 122.0 0 0 1 160.0 38.0 Z" fill="url(#sonarSweepGrad)"/>'
        '  <line x1="160.0" y1="160.0" x2="160.0" y2="38.0" stroke="rgba(2, 132, 199, 0.65)" stroke-width="1.4" stroke-linecap="round"/>'
        '</g>'
    )

    # 声纳中心换能器发射源
    lines.append(f'<circle cx="{c:.1f}" cy="{c:.1f}" r="9.0" fill="none" stroke="#0284c7" stroke-width="1.2" stroke-opacity="0.4"/>')
    lines.append(f'<circle cx="{c:.1f}" cy="{c:.1f}" r="4.5" fill="#0284c7"/>')

    # 数据多边形
    poly_pts = " ".join(f"{point(i, dim_score(d) / 100.0)[0]:.1f},{point(i, dim_score(d) / 100.0)[1]:.1f}" for i, d in enumerate(clean_dims))
    lines.append(f'<polygon points="{poly_pts}" fill="rgba(2,132,199,0.18)" stroke="#0284c7" stroke-width="2.5" stroke-linejoin="round"/>')

    # 目标接触点（严格 6.0s 周期，扫描线扫过时依次激发 ping 与 blip 动画）
    for i, d in enumerate(clean_dims):
        sc = dim_score(d)
        x, y = point(i, sc / 100.0)
        col = score_color(sc)
        delay = (i / n) * 6.0
        lines.append(
            f'<circle class="blip-dot" cx="{x:.1f}" cy="{y:.1f}" r="4.2" fill="{col}" '
            f'stroke="#ffffff" stroke-width="1.5" style="color:{col}; animation-delay:{delay:.2f}s;"/>'
        )
        lines.append(
            f'<circle class="ping" cx="{x:.1f}" cy="{y:.1f}" r="4.2" fill="none" '
            f'stroke="{col}" stroke-width="1.8" style="animation-delay:{delay:.2f}s;"/>'
        )

    # 维度标签与得分（大字号深黑，高对比醒目）
    for i, d in enumerate(clean_dims):
        sc = dim_score(d)
        col = score_color(sc)
        lx, ly = point(i, 1.20)
        # 优化标签文本对齐
        anchor = "middle"
        if lx - c > 12:
            anchor = "start"
            lx += 8
        elif c - lx > 12:
            anchor = "end"
            lx -= 8
        if ly < c - 60:
            ly -= 6
        elif ly > c + 60:
            ly += 16
        lines.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}">{esc(d.get("label", "?"))} '
            f'<tspan fill="{col}">{int(sc)}</tspan></text>'
        )

    lines.append("</svg>")
    return "\n".join(lines)


# -------------------------------------------------------------- HTML 片段与辅助

def collect_risk_phrases(findings: list[dict]) -> list[tuple[str, str]]:
    """从 findings 提取需高亮的风险原文（长句优先去重）。"""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        sev = f.get("severity", "low")
        phrase = (f.get("excerpt") or "").strip()
        if phrase and phrase not in seen:
            seen.add(phrase)
            out.append((phrase, sev))
        for kw in f.get("keywords", []):
            kw = (kw or "").strip()
            if kw and kw not in seen:
                seen.add(kw)
                out.append((kw, sev))
    out.sort(key=lambda x: -len(x[0]))
    return out


def highlight_html(text: str, phrases: list[tuple[str, str]]) -> str:
    """转义文本并把命中风险原文的位置包成 <mark class="rw {sev}">（非重叠、最左最长优先）。"""
    res: list[str] = []
    i = 0
    while i < len(text):
        best = None
        for phrase, sev in phrases:
            if not phrase:
                continue
            idx = text.find(phrase, i)
            if idx != -1 and (best is None or idx < best[0]
                              or (idx == best[0] and len(phrase) > len(best[1]))):
                best = (idx, phrase, sev)
        if best is None:
            res.append(esc(text[i:]))
            break
        idx, phrase, sev = best
        res.append(esc(text[i:idx]))
        res.append(f'<mark class="rw {esc(sev)}">{esc(phrase)}</mark>')
        i = idx + len(phrase)
    return "".join(res)


def seg_tooltip(start: float, end: float, level: str, label: str,
                transcript: list[dict], phrases: list[tuple[str, str]],
                align: str) -> str:
    """分镜悬浮浮层：该时间窗内的口播逐字稿（风险词高亮）。纯白卡片，纯 CSS，无 JS。"""
    clean_ts = [ln for ln in transcript if isinstance(ln, dict)]
    lines = [ln for ln in clean_ts
             if to_f(ln.get("start"), 0) < end and to_f(ln.get("end"), 0) > start]
    level_cls = esc(level) if level in LEVEL_LABEL else "safe"
    head = (
        f'<div class="pop-header">'
        f'<b>{esc(label)} · {fmt_ts(start)}–{fmt_ts(end)}</b>'
        f'<span class="pop-level-tag {level_cls}">{LEVEL_LABEL.get(level, level)}</span>'
        f'</div>'
    )
    if not lines:
        body = '<div class="pop-body"><div class="muted">（该时段无口播内容）</div></div>'
    else:
        rows = "".join(
            f'<div class="ln"><b>{fmt_ts(ln.get("start", 0))}</b>'
            f'{highlight_html(str(ln.get("text", "")), phrases)}</div>'
            for ln in lines
        )
        body = f'<div class="pop-body">{rows}</div>'
    return f'<div class="tl-popover tip-{align}">{head}{body}</div>'


def render_timeline(timeline: list[dict], duration,
                    transcript: list[dict] | None = None,
                    findings: list[dict] | None = None) -> str:
    duration = to_f(duration, 0)
    clean_tl = [s for s in (timeline or []) if isinstance(s, dict)]
    if not clean_tl or duration <= 0:
        return '<p class="muted" style="padding:16px;text-align:center">无分镜时间轴数据</p>'

    transcript = transcript or []
    phrases = collect_risk_phrases(findings or [])
    segs = []
    cursor = 0.0

    sorted_timeline = sorted(clean_tl, key=lambda s: to_f(s.get("start")))

    # 首个镜头起点微隙归零钳制，防止总宽度不足 100%
    if sorted_timeline and 0 < to_f(sorted_timeline[0].get("start")) < 0.5:
        sorted_timeline[0]["start"] = 0.0

    for seg in sorted_timeline:
        start, end = to_f(seg.get("start")), to_f(seg.get("end"))
        if start > cursor:
            if start - cursor >= 0.5:
                segs.append((cursor, start, "safe", "过渡"))
            elif segs:
                prev_start, _, prev_level, prev_label = segs[-1]
                segs[-1] = (prev_start, start, prev_level, prev_label)
            else:
                start = 0.0  # 首段微隙补齐
        segs.append((start, end, seg.get("level", "safe"), seg.get("label", "")))
        cursor = max(cursor, end)

    if cursor < duration:
        if duration - cursor >= 0.5:
            segs.append((cursor, duration, "safe", "片尾"))
        elif segs:
            prev_start, _, prev_level, prev_label = segs[-1]
            segs[-1] = (prev_start, duration, prev_level, prev_label)

    slices = []
    for start, end, level, label in segs:
        w = max(0.4, (end - start) / duration * 100)
        center = (start + end) / 2 / duration
        align = "left" if center < 0.25 else ("right" if center > 0.75 else "center")
        tip = seg_tooltip(start, end, level, label, transcript, phrases, align)

        # 自适应分镜标签与纯数字提取（支持大分镜密集场景平滑降级）
        short_label = label
        pure_num = ""
        if label.startswith("镜头"):
            num = label.replace("镜头", "").strip()
            if num.isdigit():
                short_label = f"#{int(num):02d}"
                pure_num = str(int(num))
            elif "-" in num:
                parts = num.split("-", 1)
                if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                    short_label = f"#{int(parts[0]):02d}-{int(parts[1]):02d}"
                    pure_num = f"{int(parts[0])}-{int(parts[1])}"
                else:
                    short_label = f"#{num}"
                    pure_num = num
        else:
            pure_num = label

        # 自适应三阶渲染（杜绝生硬 display:none 导致的部分有数字、部分空白斑驳）：
        # 1. w >= 4.2%: 宽切片，展示规范全称（如 #02, #05）
        # 2. 1.6% <= w < 4.2%: 中窄切片，精简展示纯数字（如 1, 3, 4, 11，字符宽度减半，15~25镜下全量数字可见）
        # 3. w < 1.6%: 极窄闪切，渲染纯白居中微圆点（Micro Pip），赋予触碰点指引
        if w >= 4.2:
            tier_class = "tier-wide"
            inner_html = f'<span>{esc(short_label)}</span>'
        elif w >= 1.6:
            tier_class = "tier-mid"
            inner_html = f'<span class="pure-num">{esc(pure_num)}</span>'
        else:
            tier_class = "tier-micro"
            inner_html = f'<i class="tl-pip" title="{esc(short_label)}"></i>'

        bg = LEVEL_COLOR.get(level, RISK_SAFE)
        slices.append(
            f'<div class="tl-slice {tier_class}" tabindex="0" style="width:{w:.2f}%;background:{bg}">'
            f'{inner_html}{tip}</div>'
        )

    # 刻度计算（约 7~9 个刻度）
    ticks = []
    step = max(1, round(duration / 7))
    t = 0
    while t <= duration:
        ticks.append(f'<span style="left:{t / duration * 100:.2f}%">{fmt_ts(t)}</span>')
        t += step
    if (t - step) < duration and (duration - (t - step)) > (step * 0.5):
        ticks.append(f'<span style="left:100.00%">{fmt_ts(duration)}</span>')

    legend = "".join(
        f'<span class="legend-item"><i style="background:{LEVEL_COLOR[k]}"></i>'
        f'{("安全合规" if k == "safe" else LEVEL_LABEL[k])}</span>'
        for k in ("safe", "low", "medium", "high")
    )
    hint = (
        '逐字稿高亮色标：'
        '<mark class="rw high">高风险</mark> '
        '<mark class="rw medium">中风险</mark> '
        '<mark class="rw low">低风险</mark>'
    )

    return (
        f'<div class="tl-track">{"".join(slices)}</div>\n'
        f'<div class="tl-ticks">{"".join(ticks)}</div>\n'
        f'<div class="tl-footer">\n'
        f'  <div class="tl-legend">{legend}</div>\n'
        f'  <div class="tl-legend-hint">{hint}</div>\n'
        f'</div>'
    )


def render_findings(findings: list[dict]) -> str:
    """违规命中明细（1:1 左右横向铺陈工作台）：
    - 顶部高质感细色标线（告别粗笨的单侧竖线）
    - 顶栏：等级、序号、时段与类别元信息胶囊、全文核验状态
    - 左栏：违规事实依据（加粗原文带左色彩条）+ 规则依据（规则名带外链、扣分罚则、条款内容）
    - 右栏：整改行动思路（浅蓝卡片）+ 改后文案（浅绿卡片带直接可用徽章）
    """
    clean_findings = [f for f in findings if isinstance(f, dict)]
    if not clean_findings:
        return (
            '<div class="card-panel" style="text-align:center;padding:36px;color:#059669">'
            '<div style="font-size:16px;font-weight:700;margin-bottom:6px">✓ 扫描完成：未检出明确违规命中</div>'
            '<div style="font-size:13px;color:#64748b">规则库每日增量同步更新，视频发布后仍建议关注平台审核通知。</div>'
            '</div>'
        )

    cards = []
    for i, f in enumerate(clean_findings, 1):
        sev = f.get("severity", "low")
        sev_cls = "high" if sev == "high" else ("medium" if sev == "medium" else "low")

        # 规则条款
        clauses_html = []
        for c in f.get("clauses", []):
            if not isinstance(c, dict):
                continue
            name = esc(c.get("rule_name", "未知规则"))
            rule_url = str(c.get("rule_url") or "").strip()
            if has_valid_url(rule_url):
                name_link = (
                    f'<a href="{esc(rule_url)}" target="_blank" rel="noopener" class="rule-name-link">'
                    f'《{name}》↗</a>'
                )
            else:
                name_link = f'<span class="rule-name-link" style="color:#475569">《{name}》</span>'

            penalty_badge = ""
            if c.get("penalty"):
                penalty_style = ""
                if sev_cls == "medium":
                    penalty_style = ' style="color:var(--risk-med);background:var(--risk-med-bg);border-color:var(--risk-med-border)"'
                elif sev_cls == "low":
                    penalty_style = ' style="color:var(--risk-low);background:var(--risk-low-bg);border-color:var(--risk-low-border)"'
                penalty_badge = f'<span class="rule-penalty-badge"{penalty_style}>{esc(c["penalty"])}</span>'

            clauses_html.append(
                f'<div class="rule-info">'
                f'  <div class="rule-header">{name_link}{penalty_badge}</div>'
                f'  <div class="rule-clause-body">{esc(c.get("clause_text", ""))}</div>'
                f'</div>'
            )

        verified = (
            '<span class="f-status-tag verified">✓ 已规则库全文核验</span>'
            if f.get("verified")
            else '<span class="f-status-tag pending">待补充画面凭据</span>'
        )

        # 违规事实原文渲染：优先使用 highlight_html 避免 replace 破坏标签
        kw_list = [str(kw).strip() for kw in f.get("keywords", []) if kw and str(kw).strip()]
        if kw_list:
            phrases = [(kw, sev_cls) for kw in kw_list]
            excerpt_rendered = highlight_html(str(f.get("excerpt", "")), phrases)
        else:
            excerpt_rendered = esc(f.get("excerpt", ""))

        # 左右两栏边框与彩条色彩映射（支持 high, medium, low）
        SEV_QUOTE_CLASS = {"high": "quote-text", "medium": "quote-text med", "low": "quote-text low"}
        quote_cls = SEV_QUOTE_CLASS.get(sev_cls, "quote-text")

        prob_caption_style = ""
        prob_bar_style = ""
        if sev_cls == "medium":
            prob_caption_style = ' style="color:var(--risk-med)"'
            prob_bar_style = ' style="background:var(--risk-med)"'
        elif sev_cls == "low":
            prob_caption_style = ' style="color:var(--risk-low)"'
            prob_bar_style = ' style="background:var(--risk-low)"'

        # 右栏：整改思路与改后文案（解决双重引号问题）
        suggestion_text = esc(f.get("suggestion", "建议按照平台规则规范优化表述。"))
        rewrite_raw = str(f.get("rewrite") or "").strip()
        rewrite_box = ""
        if rewrite_raw:
            # 智能剔除已有的首尾直角引号或双引号，确保渲染出标准单一「」
            clean_rewrite = rewrite_raw.strip("「」\"'“”")
            rewrite_box = (
                f'<div class="action-item script">'
                f'  <div class="act-title">'
                f'    <span>✅ 改后参考（建议直接采用）</span>'
                f'    <span class="copy-hint">直接可用</span>'
                f'  </div>'
                f'  <div class="script-quote">「{esc(clean_rewrite)}」</div>'
                f'</div>'
            )

        cards.append(f"""
      <article class="finding-card sev-{sev_cls}">
        <div class="finding-head">
          <div class="f-head-left">
            <span class="f-badge {sev_cls}"><span class="f-dot"></span>{LEVEL_LABEL.get(sev, sev)}</span>
            <span class="f-idx">{i:02d}</span>
            <span class="f-meta-pill"><b>{esc(f.get("time_range", ""))}</b> · {esc(f.get("source", "口播"))} · {esc(f.get("category", "未分类"))}</span>
          </div>
          {verified}
        </div>

        <div class="finding-split">
          <!-- 左栏：违规事实与规则裁决 -->
          <div class="finding-col">
            <div class="col-caption problem"{prob_caption_style}><span class="bar"{prob_bar_style}></span>违规原文与事实依据</div>
            <div class="fact-box">
              <div class="{quote_cls}">
                “{excerpt_rendered}”
              </div>
              {"".join(clauses_html)}
            </div>
          </div>

          <!-- 右栏：整改行动与改后参考 -->
          <div class="finding-col">
            <div class="col-caption solution"><span class="bar"></span>整改方案与改后参考</div>
            <div class="action-box-wrap">
              <div class="action-item guide">
                <div class="act-title">💡 整改思路</div>
                {suggestion_text}
              </div>
              {rewrite_box}
            </div>
          </div>
        </div>
      </article>""")

    return f'<div class="finding-list">{"".join(cards)}</div>'


# ── CSS 统一样式表（直接移植自 assets/demo.html，确保 1:1 像素级拟合） ──
CSS = """
:root {
  --bg-app: #f8fafc;
  --bg-card: #ffffff;
  --bg-card-hover: #fafafa;
  --bg-inset: #f1f5f9;
  --bg-subtle: #f8fafc;

  --text-main: #0f172a;
  --text-body: #334155;
  --text-muted: #64748b;
  --text-light: #94a3b8;

  --border: #e2e8f0;
  --border-strong: #cbd5e1;
  --shadow-xs: 0 1px 2px rgba(15, 23, 42, 0.04);
  --shadow-sm: 0 1px 3px rgba(15, 23, 42, 0.06), 0 1px 2px rgba(15, 23, 42, 0.04);
  --shadow-md: 0 4px 6px -1px rgba(15, 23, 42, 0.06), 0 2px 4px -2px rgba(15, 23, 42, 0.04);
  --shadow-lg: 0 10px 15px -3px rgba(15, 23, 42, 0.07), 0 4px 6px -4px rgba(15, 23, 42, 0.03);
  --shadow-xl: 0 20px 25px -5px rgba(15, 23, 42, 0.08), 0 8px 10px -6px rgba(15, 23, 42, 0.04);

  --brand-blue: #0284c7;
  --brand-blue-deep: #0369a1;
  --brand-blue-light: #e0f2fe;
  --brand-blue-glow: rgba(2, 132, 199, 0.12);

  --risk-high: #e11d48;
  --risk-high-bg: #fff1f2;
  --risk-high-border: #fecdd3;
  --risk-high-text: #9f1239;

  --risk-med: #d97706;
  --risk-med-bg: #fffbeb;
  --risk-med-border: #fde68a;
  --risk-med-text: #92400e;

  --risk-low: #65a30d;
  --risk-low-bg: #f7fee7;
  --risk-low-border: #d9f99d;
  --risk-low-text: #3f6212;

  --risk-safe: #059669;
  --risk-safe-bg: #ecfdf5;
  --risk-safe-border: #a7f3d0;
  --risk-safe-text: #065f46;

  --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  --font-mono: ui-monospace, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
}

* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: var(--font-sans);
  background-color: var(--bg-app);
  color: var(--text-body);
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  background-image: radial-gradient(at 100% 0%, rgba(224, 242, 254, 0.4) 0px, transparent 50%),
                    radial-gradient(at 0% 100%, rgba(241, 245, 249, 0.6) 0px, transparent 50%);
  background-attachment: fixed;
}

.mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.wrap { max-width: 1040px; margin: 0 auto; padding: 32px 24px 80px; position: relative; }

/* ── 顶部导航栏 ── */
.top-nav {
  display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px;
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px;
  padding: 16px 22px; box-shadow: var(--shadow-sm); margin-bottom: 24px;
}
.brand { display: flex; align-items: center; gap: 12px; text-decoration: none; color: inherit; }
.brand-text .t1 { font-size: 15px; font-weight: 800; letter-spacing: -0.01em; color: var(--text-main); display: flex; align-items: center; gap: 4px; }
.brand-text .t1 span { color: var(--brand-blue); }
.brand-text .t2 { font-family: var(--font-mono); font-size: 10.5px; color: var(--text-muted); letter-spacing: 0.08em; text-transform: uppercase; margin-top: 1px; }
.top-meta { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; font-size: 12.5px; color: var(--text-muted); }
.status-pill {
  display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 9999px;
  background: var(--risk-safe-bg); color: var(--risk-safe-text); font-family: var(--font-mono);
  font-size: 11.5px; font-weight: 600; border: 1px solid var(--risk-safe-border);
}
.status-pill .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--risk-safe); box-shadow: 0 0 6px var(--risk-safe); }
.source-tag { display: inline-flex; align-items: center; gap: 4px; color: var(--text-body); font-size: 12px; }
.source-tag a { color: var(--brand-blue); text-decoration: none; max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.source-tag a:hover { text-decoration: underline; }

/* ── HERO 决策中枢展台 ── */
.hero-card {
  display: grid; grid-template-columns: 360px 1fr; gap: 32px; align-items: center;
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px;
  padding: 32px; box-shadow: var(--shadow-sm); margin-bottom: 32px; position: relative;
  overflow: hidden;
}
.hero-card::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0; height: 4px;
  background: linear-gradient(90deg, #e11d48, #f59e0b, #0284c7);
}
@media (max-width: 860px) {
  .hero-card { grid-template-columns: 1fr; gap: 28px; padding: 24px; }
}

/* 声纳雷达图 */
.sonar-box { display: flex; flex-direction: column; align-items: center; justify-content: center; position: relative; }
.sonar-svg { overflow: visible; }
.sonar-svg text {
  font-family: var(--font-sans);
  font-size: 13.5px;
  font-weight: 700;
  fill: #0f172a;
}
.sonar-svg text tspan {
  font-family: var(--font-mono);
  font-size: 15px;
  font-weight: 800;
}
.sweep { transform-origin: 160px 160px; animation: sweep 6s linear infinite; }
@keyframes sweep { to { transform: rotate(360deg); } }

/* 声纳回波脉冲：与 6s 扫描周期严格物理同步 */
.ping {
  animation: sonarPing 6s cubic-bezier(0, 0, 0.2, 1) infinite;
  transform-box: fill-box;
  transform-origin: center;
  opacity: 0;
}
@keyframes sonarPing {
  0% { opacity: 0.95; transform: scale(1); stroke-width: 2px; }
  16% { opacity: 0; transform: scale(3.5); stroke-width: 0.5px; }
  16.1%, 100% { opacity: 0; transform: scale(1); }
}

/* 接触点本体荧光余辉 */
.blip-dot {
  animation: blipGlow 6s ease-out infinite;
  transform-box: fill-box;
  transform-origin: center;
}
@keyframes blipGlow {
  0% { filter: drop-shadow(0 0 5px currentColor); opacity: 1; }
  18% { filter: drop-shadow(0 0 1px currentColor); opacity: 0.95; }
  30%, 100% { filter: none; opacity: 0.9; }
}

@media (prefers-reduced-motion: reduce) {
  .sweep, .ping, .blip-dot { animation: none !important; }
}

/* 决策与分数侧 */
.hero-side { display: flex; flex-direction: column; }
.badge-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
.decision-badge {
  display: inline-flex; align-items: center; gap: 6px; padding: 6px 14px; border-radius: 8px;
  font-size: 13.5px; font-weight: 700; letter-spacing: 0.02em;
}
.decision-badge.danger { background: var(--risk-high-bg); color: var(--risk-high-text); border: 1px solid var(--risk-high-border); }
.decision-badge.warning { background: var(--risk-med-bg); color: var(--risk-med-text); border: 1px solid var(--risk-med-border); }
.decision-badge.success { background: var(--risk-safe-bg); color: var(--risk-safe-text); border: 1px solid var(--risk-safe-border); }
.risk-tag {
  display: inline-flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 700;
  font-family: var(--font-mono); text-transform: uppercase; letter-spacing: 0.06em;
  padding: 5px 10px; border-radius: 6px;
}
.risk-tag.danger { background: #fff1f2; color: #e11d48; }
.risk-tag.warning { background: #fffbeb; color: #d97706; }
.risk-tag.success { background: #ecfdf5; color: #059669; }
.risk-tag .dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }

.score-panel { display: flex; align-items: baseline; gap: 20px; margin-bottom: 12px; }
.score-num {
  font-family: var(--font-mono); font-size: 64px; font-weight: 800; line-height: 1;
  letter-spacing: -0.04em;
}
.score-num small { font-size: 18px; color: var(--text-light); font-weight: 500; margin-left: 2px; }
.risk-counts-chips { display: inline-flex; gap: 8px; align-items: center; }
.count-chip {
  display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; border-radius: 6px;
  font-size: 12px; font-family: var(--font-mono); font-weight: 600;
}
.count-chip.high { background: var(--risk-high-bg); color: var(--risk-high-text); border: 1px solid var(--risk-high-border); }
.count-chip.med { background: var(--risk-med-bg); color: var(--risk-med-text); border: 1px solid var(--risk-med-border); }
.count-chip.low { background: var(--risk-low-bg); color: var(--risk-low-text); border: 1px solid var(--risk-low-border); }
.count-chip b { font-size: 15px; font-weight: 700; }

.video-title { font-size: 20px; font-weight: 800; color: var(--text-main); margin-bottom: 10px; line-height: 1.4; letter-spacing: -0.01em; }
.summary-box {
  background: var(--bg-inset); border: 1px solid var(--border); border-radius: 10px;
  padding: 14px 16px; font-size: 13.5px; color: var(--text-body); line-height: 1.7; margin-bottom: 18px;
}
.summary-box b { color: var(--text-main); font-weight: 700; }

/* 视频微元数据栅格 */
.meta-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 10px;
}
.meta-card {
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px;
  padding: 8px 12px; display: flex; flex-direction: column;
}
.meta-card .mk { font-size: 11px; color: var(--text-muted); font-family: var(--font-mono); }
.meta-card .mv { font-size: 13.5px; font-weight: 700; color: var(--text-main); margin-top: 2px; font-family: var(--font-mono); }

/* ── 模块通用标题 ── */
.sec { margin-top: 36px; }
.sec-header {
  display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 16px;
}
.sec-title-wrap { display: flex; align-items: center; gap: 10px; }
.sec-idx {
  font-family: var(--font-mono); font-size: 12px; font-weight: 700; color: var(--brand-blue);
  background: var(--brand-blue-light); padding: 2px 8px; border-radius: 4px;
}
.sec-title { font-size: 17px; font-weight: 800; color: var(--text-main); letter-spacing: -0.01em; }
.sec-hint { font-size: 12.5px; color: var(--text-muted); font-family: var(--font-mono); }

.card-panel {
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 14px;
  padding: 24px; box-shadow: var(--shadow-sm);
}

/* ── 01. 五维合规条形评分 ── */
.dim-grid { display: flex; flex-direction: column; gap: 16px; }
.dim-row { display: grid; grid-template-columns: 140px 1fr 60px; gap: 16px; align-items: center; }
.dim-info .dname { font-size: 14px; font-weight: 700; color: var(--text-main); }
.dim-info .dnote { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
.dim-track-wrap { position: relative; width: 100%; height: 10px; background: var(--bg-inset); border-radius: 9999px; overflow: visible; }
.dim-fill { height: 100%; border-radius: 9999px; transition: width 0.4s ease; }
.dim-pass-line {
  position: absolute; left: 85%; top: -4px; bottom: -4px; width: 2px; background: var(--border-strong);
  border-radius: 1px; z-index: 2;
}
.dim-score-val { font-family: var(--font-mono); font-size: 15px; font-weight: 800; text-align: right; }

/* ── 02. 分镜时间轴 ── */
.timeline-container { position: relative; }
.tl-track {
  display: flex; height: 38px; border-radius: 8px; background: var(--bg-inset);
  padding: 2px; border: 1px solid var(--border); box-shadow: inset 0 1px 2px rgba(0,0,0,0.04);
}
.tl-slice {
  position: relative; cursor: pointer; display: flex; align-items: center; justify-content: center;
  border-right: 1px solid rgba(255, 255, 255, 0.75);
  transition: filter 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
  outline: none; user-select: none;
}
.tl-slice:first-child { border-radius: 6px 0 0 6px; }
.tl-slice:last-child { border-radius: 0 6px 6px 0; border-right: none; }
.tl-slice:hover {
  filter: brightness(1.12);
  transform: translateY(-1px);
  box-shadow: 0 3px 8px rgba(0,0,0,0.14);
  z-index: 20;
}
.tl-slice:focus-visible { box-shadow: 0 0 0 2px #fff, 0 0 0 4px var(--brand-blue); z-index: 21; }
.tl-slice span {
  font-family: var(--font-mono); font-size: 10px; font-weight: 700; color: rgba(255,255,255,0.98);
  text-shadow: 0 1px 2px rgba(0,0,0,0.3); white-space: nowrap; overflow: hidden; text-overflow: clip;
  padding: 0 1px; pointer-events: none;
}
.tl-slice.tier-mid span.pure-num {
  font-size: 9px;
  letter-spacing: -0.4px;
  font-weight: 800;
  opacity: 0.95;
}
/* 极窄切片微圆点 (Micro Pip) 锚点 */
.tl-pip {
  display: block; width: 3.5px; height: 3.5px; border-radius: 50%;
  background: rgba(255, 255, 255, 0.9); box-shadow: 0 0 2px rgba(0,0,0,0.3);
  pointer-events: none; transition: transform 0.15s ease;
}
.tl-slice.tier-micro:hover .tl-pip {
  transform: scale(1.6);
  background: #ffffff;
}

/* 悬停浮层 Tooltip（现代高质感纯白卡片） */
.tl-slice:hover .tl-popover { display: block; }
.tl-slice:focus .tl-popover { display: block; }
.tl-popover {
  display: none; position: absolute; bottom: calc(100% + 12px); z-index: 50;
  width: max-content; min-width: 220px; max-width: 380px; text-align: left;
  background: #ffffff; border: 1px solid var(--border-strong); border-radius: 10px;
  padding: 12px 14px; box-shadow: var(--shadow-xl); pointer-events: none;
}
.tl-popover.tip-center { left: 50%; transform: translateX(-50%); }
.tl-popover.tip-left { left: 0; }
.tl-popover.tip-right { right: 0; }
.tl-popover::after {
  content: ""; position: absolute; top: 100%; border: 6px solid transparent;
  border-top-color: #ffffff;
}
.tl-popover.tip-center::after { left: 50%; transform: translateX(-50%); }
.tl-popover.tip-left::after { left: 16px; }
.tl-popover.tip-right::after { right: 16px; }

.pop-header {
  display: flex; justify-content: space-between; align-items: center;
  font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);
  padding-bottom: 6px; margin-bottom: 8px; border-bottom: 1px solid var(--border);
}
.pop-header b { color: var(--text-main); font-weight: 700; }
.pop-level-tag { padding: 2px 6px; border-radius: 4px; font-weight: 700; font-size: 10px; }
.pop-level-tag.high { background: var(--risk-high-bg); color: var(--risk-high-text); }
.pop-level-tag.medium { background: var(--risk-med-bg); color: var(--risk-med-text); }
.pop-level-tag.low { background: var(--risk-low-bg); color: var(--risk-low-text); }
.pop-level-tag.safe { background: var(--risk-safe-bg); color: var(--risk-safe-text); }
.pop-body { font-size: 13px; line-height: 1.6; color: var(--text-main); }
.pop-body .ln b { font-family: var(--font-mono); font-size: 11px; color: var(--text-light); margin-right: 6px; }
.pop-body .muted { color: var(--text-light); font-size: 12px; }

/* 逐字稿高亮 Mark 样式 */
mark.rw { border-radius: 3px; padding: 1px 4px; font-weight: 600; }
mark.rw.high { background: #ffe4e6; color: #be123c; border-bottom: 1.5px solid #f43f5e; }
mark.rw.medium { background: #fef3c7; color: #b45309; border-bottom: 1.5px solid #f59e0b; }
mark.rw.low { background: #ecfccb; color: #4d7c0f; border-bottom: 1.5px solid #84cc16; }

.tl-ticks { position: relative; height: 22px; margin-top: 8px; }
.tl-ticks span {
  position: absolute; transform: translateX(-50%); font-family: var(--font-mono);
  font-size: 10.5px; color: var(--text-light);
}
.tl-footer {
  display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;
  margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--border); font-size: 12px;
}
.tl-legend { display: flex; gap: 16px; font-family: var(--font-mono); color: var(--text-muted); }
.legend-item { display: inline-flex; align-items: center; gap: 6px; }
.legend-item i { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
.tl-legend-hint { color: var(--text-muted); font-size: 12px; }

/* ── 03. 违规命中明细卡片（现代横向铺陈工作台） ── */
.finding-list { display: flex; flex-direction: column; gap: 24px; }
.finding-card {
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px;
  padding: 22px 24px; box-shadow: var(--shadow-sm); position: relative; overflow: hidden;
  transition: box-shadow 0.2s ease, border-color 0.2s ease;
}
.finding-card:hover {
  box-shadow: var(--shadow-md); border-color: var(--border-strong);
}

/* 顶部高质感细色标线 */
.finding-card::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3.5px;
}
.finding-card.sev-high::before {
  background: linear-gradient(90deg, #e11d48, #f43f5e, #fda4af);
}
.finding-card.sev-medium::before {
  background: linear-gradient(90deg, #d97706, #f59e0b, #fde68a);
}
.finding-card.sev-low::before {
  background: linear-gradient(90deg, #65a30d, #84cc16, #d9f99d);
}

/* 卡片顶栏元信息 */
.finding-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; flex-wrap: wrap; margin-bottom: 18px; padding-bottom: 14px;
  border-bottom: 1px solid var(--border);
}
.f-head-left { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.f-badge {
  display: inline-flex; align-items: center; gap: 5px; font-family: var(--font-mono);
  font-size: 11.5px; font-weight: 700; padding: 4px 10px; border-radius: 9999px; letter-spacing: 0.04em;
}
.f-badge.high { background: var(--risk-high-bg); color: var(--risk-high-text); border: 1px solid var(--risk-high-border); }
.f-badge.high .f-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--risk-high); }
.f-badge.medium { background: var(--risk-med-bg); color: var(--risk-med-text); border: 1px solid var(--risk-med-border); }
.f-badge.medium .f-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--risk-med); }
.f-badge.low { background: var(--risk-low-bg); color: var(--risk-low-text); border: 1px solid var(--risk-low-border); }
.f-badge.low .f-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--risk-low); }

.f-idx {
  font-family: var(--font-mono); font-size: 13px; font-weight: 800; color: var(--text-main);
  background: var(--bg-inset); padding: 3px 8px; border-radius: 6px; border: 1px solid var(--border);
}
.f-meta-pill {
  display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-muted);
  background: var(--bg-inset); padding: 3px 10px; border-radius: 6px;
}
.f-meta-pill b { color: var(--text-main); font-weight: 600; }
.f-status-tag {
  display: inline-flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 600;
  padding: 4px 10px; border-radius: 9999px;
}
.f-status-tag.verified { background: var(--risk-safe-bg); color: var(--risk-safe-text); border: 1px solid var(--risk-safe-border); }
.f-status-tag.pending { background: var(--risk-med-bg); color: var(--risk-med-text); border: 1px solid var(--risk-med-border); }

/* 横向两栏铺陈栅格 */
.finding-split {
  display: grid; grid-template-columns: 1fr 1fr; gap: 20px; align-items: stretch;
}
@media (max-width: 860px) {
  .finding-split { grid-template-columns: 1fr; gap: 16px; }
}

.finding-col { display: flex; flex-direction: column; gap: 10px; }
.col-caption {
  display: flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 700;
  color: var(--text-muted); letter-spacing: 0.04em;
}
.col-caption .bar { width: 3px; height: 12px; border-radius: 2px; }
.col-caption.problem .bar { background: var(--risk-high); }
.col-caption.solution .bar { background: var(--risk-safe); }

/* 左栏：事实与法条 */
.fact-box {
  background: var(--bg-inset); border: 1px solid var(--border); border-radius: 10px;
  padding: 14px; flex: 1; display: flex; flex-direction: column; justify-content: space-between; gap: 12px;
}
.quote-text {
  font-size: 14px; font-weight: 700; color: var(--text-main); line-height: 1.6;
  position: relative; padding-left: 12px; border-left: 3px solid var(--risk-high);
}
.quote-text.med { border-left-color: var(--risk-med); }
.quote-text.low { border-left-color: var(--risk-low); }

.rule-info {
  background: #ffffff; border: 1px solid var(--border); border-radius: 8px;
  padding: 12px 14px; font-size: 12.5px;
}
.rule-header {
  display: flex; justify-content: space-between; align-items: baseline; gap: 8px; margin-bottom: 6px;
}
.rule-name-link {
  font-weight: 700; color: var(--brand-blue-deep); text-decoration: none; font-size: 13px;
  display: inline-flex; align-items: center; gap: 4px;
}
.rule-name-link:hover { text-decoration: underline; }
.rule-clause-body { color: var(--text-body); line-height: 1.6; margin-bottom: 8px; }
.rule-penalty-badge {
  display: inline-flex; align-items: center; gap: 4px; font-family: var(--font-mono);
  font-size: 11.5px; font-weight: 700; color: var(--risk-high); background: var(--risk-high-bg);
  padding: 3px 8px; border-radius: 4px; border: 1px solid var(--risk-high-border);
}

/* 右栏：建议与改写文案 */
.action-box-wrap { display: flex; flex-direction: column; gap: 10px; flex: 1; }
.action-item {
  border-radius: 10px; padding: 13px 15px; font-size: 13px; line-height: 1.6; flex: 1;
}
.action-item.guide {
  background: #f0f9ff; border: 1px solid #bae6fd; color: #0369a1;
}
.action-item.guide .act-title {
  font-weight: 800; font-size: 11.5px; color: #0284c7; letter-spacing: 0.04em;
  margin-bottom: 5px; display: flex; align-items: center; gap: 4px;
}
.action-item.script {
  background: #f0fdf4; border: 1px solid #bbf7d0; color: #14532d;
}
.action-item.script .act-title {
  font-weight: 800; font-size: 11.5px; color: #15803d; letter-spacing: 0.04em;
  margin-bottom: 5px; display: flex; align-items: center; justify-content: space-between;
}
.action-item.script .copy-hint {
  font-size: 10.5px; font-weight: 600; color: #16a34a; background: #dcfce7;
  padding: 1px 6px; border-radius: 4px;
}
.script-quote {
  font-weight: 700; color: #166534; font-size: 13.5px; line-height: 1.6;
}

/* ── 04. 整改清单 ── */
.fix-list { list-style: none; display: flex; flex-direction: column; gap: 10px; }
.fix-item {
  display: flex; align-items: baseline; gap: 14px; background: var(--bg-inset);
  border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; font-size: 14px;
  color: var(--text-main); font-weight: 500;
}
.fix-item .fno {
  font-family: var(--font-mono); font-size: 12px; font-weight: 800; color: var(--brand-blue);
  background: #ffffff; border: 1px solid var(--border); width: 24px; height: 24px;
  border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}

/* ── 05. 合规改写文案 ── */
.script-card {
  background: #f8fafc; border: 1px solid var(--border); border-radius: 12px; padding: 22px;
}
.script-text {
  font-size: 15px; line-height: 2.1; color: var(--text-main); padding: 4px; font-weight: 500;
}
.script-notes {
  margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--border);
  font-size: 13px; color: var(--text-muted); line-height: 1.8;
}
.script-notes b { color: var(--brand-blue); font-weight: 700; margin-right: 6px; }

/* ── 06. 待人工核实表格 ── */
.table-wrap { overflow-x: auto; }
.verify-table { width: 100%; border-collapse: collapse; font-size: 13.5px; text-align: left; }
.verify-table th {
  background: var(--bg-inset); color: var(--text-muted); font-weight: 600; font-size: 12px;
  padding: 10px 14px; border-bottom: 1px solid var(--border); font-family: var(--font-mono);
}
.verify-table td { padding: 14px; border-bottom: 1px solid var(--border); vertical-align: top; color: var(--text-body); }
.verify-table tr:last-child td { border-bottom: none; }
.verify-table tr:hover td { background: var(--bg-subtle); }
.verify-table .v-no { font-family: var(--font-mono); font-weight: 700; color: var(--text-muted); width: 40px; }
.verify-table .v-owner span {
  display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11.5px; font-weight: 600;
  background: var(--brand-blue-light); color: var(--brand-blue-deep); white-space: nowrap;
}

/* ── 页脚 ── */
footer {
  margin-top: 48px; padding-top: 20px; border-top: 1px solid var(--border);
  font-size: 12px; color: var(--text-light); line-height: 1.8; text-align: center;
}

@media print {
  body { background: #ffffff !important; }
  .top-nav, .hero-card, .card-panel, .finding-card { box-shadow: none !important; border: 1px solid #cbd5e1 !important; }
}
"""


def build_html(data: dict) -> str:
    if not isinstance(data, dict):
        raise ValueError("输入数据必须为 dict 结构")

    meta = data.get("meta", {}) if isinstance(data.get("meta"), dict) else {}
    overall = data.get("overall", {}) if isinstance(data.get("overall"), dict) else {}
    score = max(0.0, min(100.0, to_f(overall.get("score"), 0.0)))
    raw_findings = data.get("findings", []) if isinstance(data.get("findings"), list) else []
    findings = [f for f in raw_findings if isinstance(f, dict)]

    # 风险构成统计
    counts = {"high": 0, "medium": 0, "low": 0}
    for f in findings:
        sev = f.get("severity", "low")
        if sev in counts:
            counts[sev] += 1

    # 发布决策：缺省按标准公式推导
    decision = overall.get("decision")
    has_verified_high = any(f.get("verified") and f.get("severity") == "high" for f in findings)
    has_medium_plus = any(f.get("severity") in ("medium", "high") for f in findings)
    if decision not in ("暂缓投放", "整改后发布", "可发布"):
        decision = ("暂缓投放" if (score < 60 or has_verified_high)
                    else "整改后发布" if (score < 85 or has_medium_plus) else "可发布")

    DECISION_CLASS = {"暂缓投放": "danger", "整改后发布": "warning", "可发布": "success"}
    dec_cls = DECISION_CLASS.get(decision, "warning")

    risk = overall.get("risk_level")
    if not risk or risk not in LEVEL_LABEL:
        risk = "high" if score < 60 else ("medium" if score < 85 else "safe")
    RISK_TAG_CLASS = {"high": "danger", "medium": "warning", "low": "warning", "safe": "success"}
    risk_tag_cls = RISK_TAG_CLASS.get(risk, "warning")

    platform = meta.get("platform", "douyin")
    platform_label = PLATFORM_LABEL.get(platform, platform)
    digits = "".join(ch for ch in str(meta.get("generated_at", "")) if ch.isdigit())
    report_id = f"DSR-{digits[:14] or '202609201504'}"

    # 视频来源处理
    vsource_raw = str(meta.get("video_source", "")).strip()
    source_tag_html = ""
    if vsource_raw:
        # 优先提取 URL
        words = vsource_raw.split()
        link_url = ""
        link_text = vsource_raw
        for w in words:
            if has_valid_url(w):
                link_url = w
                break
        if link_url:
            source_tag_html = f'<div class="source-tag">来源: <a href="{safe_url(link_url)}" target="_blank" rel="noopener">{esc(link_text)}</a></div>'
        else:
            source_tag_html = f'<div class="source-tag">来源: <span>{esc(vsource_raw)}</span></div>'

    # 五维合规条形评分
    clean_dims = [d for d in data.get("dimensions", []) if isinstance(d, dict)]
    dim_rows = []
    for d in clean_dims:
        d_sc = max(0.0, min(100.0, to_f(d.get("score"), 0.0)))
        d_col = score_color(d_sc)
        d_note = esc(d.get("note", ""))
        note_html = f'<div class="dnote">{d_note}</div>' if d_note else ''
        dim_rows.append(f"""
        <div class="dim-row">
          <div class="dim-info">
            <div class="dname">{esc(d.get("label", "?"))}</div>
            {note_html}
          </div>
          <div class="dim-track-wrap">
            <div class="dim-pass-line" title="85分合格线"></div>
            <div class="dim-fill" style="width:{d_sc:.0f}%;background:{d_col}"></div>
          </div>
          <div class="dim-score-val" style="color:{d_col}">{int(d_sc)}</div>
        </div>""")
    dims_html = "\n".join(dim_rows)

    # 整改清单
    fixes_list = [str(f).strip() for f in data.get("fixes", []) if str(f).strip()]
    if fixes_list:
        fix_items = "".join(
            f'<li class="fix-item"><span class="fno">{idx}</span><span>{esc(fix)}</span></li>'
            for idx, fix in enumerate(fixes_list, 1)
        )
        fixes_html = f'<ul class="fix-list">{fix_items}</ul>'
    else:
        fixes_html = '<p class="muted" style="text-align:center;padding:16px">暂无整改项</p>'

    # 待人工核实清单（可选）
    pending_rows = []
    for idx, x in enumerate([v for v in data.get("pending_verifications", []) if v], 1):
        if isinstance(x, dict):
            item = str(x.get("item") or x.get("text") or "").strip()
            owner = str(x.get("owner") or "").strip()
            method = str(x.get("method") or "").strip()
        else:
            item, owner, method = str(x).strip(), "", ""
        if not item:
            continue
        pending_rows.append(f"""
            <tr>
              <td class="v-no">{idx:02d}</td>
              <td>{esc(item)}</td>
              <td class="v-owner"><span>{esc(owner) or "—"}</span></td>
              <td>{esc(method) or "—"}</td>
            </tr>""")
    pending_section = ""
    if pending_rows:
        pending_section = f"""
  <!-- 06. 待人工核实事项 -->
  <section class="sec">
    <div class="sec-header">
      <div class="sec-title-wrap">
        <span class="sec-idx">06</span>
        <h2 class="sec-title">待人工核实清单</h2>
      </div>
      <span class="sec-hint">涉及资质证据链核查，需相关部门协同</span>
    </div>
    <div class="card-panel" style="padding:0;overflow:hidden">
      <div class="table-wrap">
        <table class="verify-table">
          <thead>
            <tr>
              <th>序号</th>
              <th>待核验事项</th>
              <th>责任主体</th>
              <th>核实方式与依据</th>
            </tr>
          </thead>
          <tbody>
            {"".join(pending_rows)}
          </tbody>
        </table>
      </div>
    </div>
  </section>"""

    # 合规改写口播稿（可选）
    rs = data.get("rewritten_script") or {}
    rs_text = str(rs.get("text") or "").strip() if isinstance(rs, dict) else ""
    rs_notes = str(rs.get("notes") or "").strip() if isinstance(rs, dict) else ""
    script_section = ""
    if rs_text:
        notes_formatted = esc(rs_notes).replace("\n", "<br>")
        notes_html = f'<div class="script-notes"><b>核心优化要点：</b>{notes_formatted}</div>' if notes_formatted else ''
        script_section = f"""
  <!-- 05. 合规改写口播稿 -->
  <section class="sec">
    <div class="sec-header">
      <div class="sec-title-wrap">
        <span class="sec-idx">05</span>
        <h2 class="sec-title">合规改写口播脚本</h2>
      </div>
      <span class="sec-hint">主播录制与配音可直接采用</span>
    </div>
    <div class="card-panel script-card">
      <div class="script-text">“{esc(rs_text)}”</div>
      {notes_html}
    </div>
  </section>"""

    # 分镜数与时长展示
    duration_val = to_f(meta.get("duration_sec"), 0.0)
    shot_cnt = meta.get("shot_count", "—")
    duration_shot_str = f"{fmt_ts(duration_val)} · {shot_cnt}镜" if shot_cnt != "—" else fmt_ts(duration_val)

    # 规则引用与命中数
    rules_cited = meta.get("deepsonar_rules_cited", 0)
    findings_count = len(findings)

    # 决策依据总结文本（三段式优雅格式化）
    summary_formatted = format_summary(str(overall.get("summary", "")))

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(meta.get("title", "视频拉片风控报告 · DeepSonar 深纳"))}</title>
<style>{CSS}</style>
</head>
<body>

<div class="wrap">
  <!-- 顶部状态栏 -->
  <header class="top-nav">
    <a href="#" class="brand">
      {LOGO_SVG}
      <div class="brand-text">
        <div class="t1">Deep<span>Sonar</span> 深纳</div>
        <div class="t2">Video Compliance &amp; Attribution Engine</div>
      </div>
    </a>
    <div class="top-meta">
      <div class="status-pill">
        <span class="dot"></span>扫描完成 · {esc(report_id)}
      </div>
      {source_tag_html}
    </div>
  </header>

  <!-- HERO 核心决策展台 -->
  <section class="hero-card">
    <!-- 左侧：现代专业声纳显控雷达 -->
    <div class="sonar-box">
      {sonar_screen_svg(clean_dims)}
    </div>

    <!-- 右侧：决策总览 -->
    <div class="hero-side">
      <div class="badge-row">
        <span class="decision-badge {dec_cls}">发布决策 · {esc(decision)}</span>
        <span class="risk-tag {risk_tag_cls}"><span class="dot"></span>{LEVEL_LABEL.get(risk, risk)}</span>
      </div>

      <div class="score-panel">
        <div class="score-num" style="color:{score_color(score)}">{int(score)}<small>/100</small></div>
        <div class="risk-counts-chips">
          <span class="count-chip high"><b>{counts['high']}</b> 高风险</span>
          <span class="count-chip med"><b>{counts['medium']}</b> 中风险</span>
          <span class="count-chip low"><b>{counts['low']}</b> 低风险</span>
        </div>
      </div>

      <h1 class="video-title">{esc(meta.get("title", "视频拉片风控报告"))}</h1>

      <div class="summary-box">
        {summary_formatted}
      </div>

      <div class="meta-grid">
        <div class="meta-card">
          <span class="mk">电商平台</span>
          <span class="mv" style="color:#0284c7">{esc(platform_label)}</span>
        </div>
        <div class="meta-card">
          <span class="mk">视频时长 / 分镜</span>
          <span class="mv">{esc(duration_shot_str)}</span>
        </div>
        <div class="meta-card">
          <span class="mk">全模态模型</span>
          <span class="mv" style="font-size:11.5px">{esc(meta.get("model_used", "—"))}</span>
        </div>
        <div class="meta-card">
          <span class="mk">规则引用 / 命中</span>
          <span class="mv">{esc(rules_cited)}条 · <span style="color:{score_color(score)}">{findings_count}项违规</span></span>
        </div>
      </div>
    </div>
  </section>

  <!-- 01. 五维合规评分 -->
  <section class="sec">
    <div class="sec-header">
      <div class="sec-title-wrap">
        <span class="sec-idx">01</span>
        <h2 class="sec-title">五维合规评分</h2>
      </div>
      <span class="sec-hint">合格基准阈值线：85 分</span>
    </div>
    <div class="card-panel">
      <div class="dim-grid">
        {dims_html}
      </div>
    </div>
  </section>

  <!-- 02. 分镜时间轴 -->
  <section class="sec">
    <div class="sec-header">
      <div class="sec-title-wrap">
        <span class="sec-idx">02</span>
        <h2 class="sec-title">分镜风险时间轴</h2>
      </div>
      <span class="sec-hint">鼠标悬停色带可查看分镜台词与违规高亮</span>
    </div>
    <div class="card-panel timeline-container">
      {render_timeline(data.get("timeline", []), duration_val,
                       data.get("transcript"), findings)}
    </div>
  </section>

  <!-- 03. 违规命中明细 -->
  <section class="sec">
    <div class="sec-header">
      <div class="sec-title-wrap">
        <span class="sec-idx">03</span>
        <h2 class="sec-title">违规命中明细与归因</h2>
      </div>
      <span class="sec-hint">共检出 {findings_count} 项合规风险</span>
    </div>
    {render_findings(findings)}
  </section>

  <!-- 04. 整改清单 -->
  <section class="sec">
    <div class="sec-header">
      <div class="sec-title-wrap">
        <span class="sec-idx">04</span>
        <h2 class="sec-title">整改执行清单</h2>
      </div>
      <span class="sec-hint">按优先级逐项闭环</span>
    </div>
    <div class="card-panel">
      {fixes_html}
    </div>
  </section>

  {script_section}

  {pending_section}

  <!-- 页脚 -->
  <footer>
    <b>DeepSonar 深纳</b> · 视频拉片风控归因系统 · 本报告基于全模态模型理解与电商平台动态规则库自动生成<br>
    报告仅供内容合规自查与发布前预审参考，不构成平台判罚免责保证。最终解释权归属电商平台监管规则。
  </footer>
</div>

</body>
</html>"""


def validate_report_data(data: dict) -> list[str]:
    """对 report_input 数据做契约健康度与逻辑一致性诊断，返回警告与建议列表。"""
    warnings = []
    # 1. 检查 summary 三段式完整度
    summary = str(data.get("overall", {}).get("summary", ""))
    missing_parts = [p for p in ("依据：", "约束：", "行动：") if p not in summary]
    if missing_parts:
        warnings.append(f"overall.summary 建议补充标准三段式前缀: 缺失 {missing_parts}")

    # 2. 检查 duration_sec
    duration = to_f(data.get("meta", {}).get("duration_sec"), 0.0)
    if duration <= 0:
        warnings.append("meta.duration_sec 缺失或小于等于 0")

    # 3. 检查维度评分
    dims = data.get("dimensions", [])
    if len(dims) < 3:
        warnings.append(f"dimensions 维度数不足 ({len(dims)}/5)，声纳雷达图将降级显示")

    # 4. 检查分镜与违规等级逻辑闭环
    findings = data.get("findings", [])
    high_findings = [f for f in findings if f.get("severity") == "high"]
    timeline = data.get("timeline", [])
    high_segs = [s for s in timeline if s.get("level") == "high"]
    if high_findings and not high_segs:
        warnings.append("存在 high 违规命中，但 timeline 中未标记任何 high 风险分镜（时序逻辑脱节）")

    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="风控报告渲染器（单文件离线 HTML · 现代声纳显控台）")
    parser.add_argument("input", help="report_input.json（契约见 references/report_schema.md）")
    parser.add_argument("-o", "--output", default="risk_report.html")
    parser.add_argument("--validate-only", action="store_true", help="仅执行契约校验与逻辑健康检查，不输出 HTML")
    args = parser.parse_args()

    try:
        with open(args.input, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"输入 JSON 读取失败: {e}", file=sys.stderr)
        return 1

    # 根类型校验（P0 级防护）
    if not isinstance(data, dict):
        print("输入 JSON 格式不合法：根节点必须为 Object/Dict 结构（契约见 references/report_schema.md）",
              file=sys.stderr)
        return 1

    missing = [k for k in ("meta", "overall", "dimensions", "findings") if k not in data]
    if missing:
        print(f"输入缺少必需字段: {missing}（契约见 references/report_schema.md）",
              file=sys.stderr)
        return 1

    warnings = validate_report_data(data)
    if warnings:
        for w in warnings:
            print(f"[契约健康提示] {w}", file=sys.stderr)

    if args.validate_only:
        print("契约与必需字段校验通过！")
        return 0

    rendered = build_html(data)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(rendered)
    print(f"报告已生成: {args.output}（单文件离线 HTML，可直接转发）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

