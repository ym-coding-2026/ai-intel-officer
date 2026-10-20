"""报告模块：把处理完的资讯拼成一份 Markdown 日报。

统计区是刻意设计的：去重率、处理耗时这些数字，
就是你以后写进简历和面试时说的「量化效果」。

v3 改动：按 interest_score 把新闻分成「🔥 为你推荐」和「📰 其余资讯」两区，
关心的置顶，并在每条后面标出命中的兴趣话题。

v4.5 改动：
- 新增「⭐ 今日必读（Top 3）」置顶板块，按兴趣分取最值得看的 3 条；
- 每条新闻加一句「🏷 为什么推给你：因为你关注 X / Y」，让推荐有据可依。
"""
from datetime import datetime

REC_THRESHOLD = 0.3  # 分数达到这个就被认为"你关心"，进推荐区
TOP_N = 3            # v4.5：今日必读最多展示几条


def _reason(item):
    """根据命中的兴趣话题，生成一句"为什么推给你"。"""
    matched = item.get("matched")
    if matched:
        tags = "、".join(f"`{m}`" for m in matched)
        return f"- 🏷 为什么推给你：因为你关注 {tags}"
    return ""


def _render(lst, with_rank=False):
    out = []
    for i, it in enumerate(lst, 1):
        prefix = f"{i}. " if with_rank else ""
        reason = _reason(it)
        out += [
            f"### {prefix}{it['title']}",
            f"- **要点**：{it['brief']}",
            f"- **来源**：{it['source']}　[原文]({it['url']})",
        ]
        if reason:
            out.append(reason)
        out.append("")
    return out


def build_report(items, duplicates, stats, used_sample=False, memory_changes=None):
    today = datetime.now().strftime("%Y-%m-%d")
    recommend = [it for it in items if it.get("interest_score", 0) >= REC_THRESHOLD]
    others = [it for it in items if it.get("interest_score", 0) < REC_THRESHOLD]

    # v4.5：今日必读 = 兴趣分最高的 Top N 条（跨"推荐/其余"一起排，取最值得看的）
    top_items = sorted(items, key=lambda x: x.get("interest_score", 0), reverse=True)[:TOP_N]

    lines = [
        f"# AI 情报官 · 日报 {today}",
        "",
        "> v3 记忆上线：根据你的长期兴趣排序，关心的置顶；v4.5 新增「今日必读」精选。",
        "",
        "## 今日概览",
        f"- 采集总量：{stats['total']} 条",
        f"- 去重剔除：{stats['duplicates']} 条（去重率 {stats['dedup_rate']:.0%}）",
        f"- 精选收录：{stats['kept']} 条（其中你关心的 {len(recommend)} 条）",
    ]
    if used_sample:
        lines.append("- ⚠️ 本次为离线示例数据（采集源不可达）")
    lines.append("")

    # v4.5：今日必读置顶
    lines.append(f"## ⭐ 今日必读（Top {len(top_items)}）")
    if top_items:
        lines += _render(top_items, with_rank=True)
    else:
        lines.append("（今天没收录到资讯）")
        lines.append("")

    lines.append(f"## 🔥 为你推荐（你关心的 {len(recommend)} 条）")
    if recommend:
        lines += _render(recommend)
    else:
        lines.append("今天没有命中你关心的方向，看看下面其它资讯？")
        lines.append("")

    lines.append("## 📰 其余资讯")
    if others:
        lines += _render(others)
    else:
        lines.append("（今天收录的都是你关心的，棒！）")
        lines.append("")

    if duplicates:
        lines.append("## 被去重拦下的重复报道")
        for d in duplicates:
            lines.append(f"- {d['title']}（{d['source']}）")
        lines.append("")

    # v3.5：把"今天学到了什么"可视化出来，让"会学也会忘"看得见
    if memory_changes:
        up = [c for c in memory_changes if c["direction"] == "up"]
        down = [c for c in memory_changes if c["direction"] == "down"]
        lines.append("## 📈 记忆变化（今天学到的）")
        if up:
            lines.append("**强化了这些方向（今天有相关新闻）：**")
            for c in up:
                lines.append(f"- ↑ `{c['name']}`：权重 {c['before']} → {c['after']}")
        if down:
            lines.append("**慢慢淡忘的方向（今天没出现）：**")
            for c in down:
                lines.append(f"- ↓ `{c['name']}`：权重 {c['before']} → {c['after']}")
        if not up and not down:
            lines.append("今天记忆整体平稳，没有权重变化。")
        lines.append("")

    lines.append(f"---\n*由 AI 情报官自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    return "\n".join(lines)
