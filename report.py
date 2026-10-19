"""报告模块：把处理完的资讯拼成一份 Markdown 日报。

统计区是刻意设计的：去重率、处理耗时这些数字，
就是你以后写进简历和面试时说的「量化效果」。
"""
from datetime import datetime


def build_report(items, duplicates, stats, used_sample=False):
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# AI 情报官 · 日报 {today}",
        "",
        "## 今日概览",
        f"- 采集总量：{stats['total']} 条",
        f"- 去重剔除：{stats['duplicates']} 条（去重率 {stats['dedup_rate']:.0%}）",
        f"- 精选收录：{stats['kept']} 条",
    ]
    if used_sample:
        lines.append("- ⚠️ 本次为离线示例数据（采集源不可达）")
    lines.append("")
    lines.append("## 精选资讯")
    for i, it in enumerate(items, 1):
        lines += [
            f"### {i}. {it['title']}",
            f"- **要点**：{it['brief']}",
            f"- **来源**：{it['source']}　[原文]({it['url']})",
            "",
        ]
    if duplicates:
        lines.append("## 被去重拦下的重复报道")
        for d in duplicates:
            lines.append(f"- {d['title']}（{d['source']}）")
        lines.append("")
    lines.append(f"---\n*由 AI 情报官自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    return "\n".join(lines)
