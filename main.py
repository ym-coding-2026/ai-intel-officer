"""AI 情报官 · 主流水线

采集 → 去重 → 摘要 → 生成日报
跑法：python main.py
产出：reports/当天日期.md
"""
import os
from datetime import date

from collector import collect_all
from dedup import create_dedup_engine
from summarizer import summarize_all
from report import build_report


def main():
    print("=" * 46)
    print("  AI 情报官 · 每日情报流水线启动")
    print("=" * 46)

    # 第 1 步：采集
    news, used_sample = collect_all()

    # 第 2 步：去重（本项目的核心亮点之一）
    # 工厂函数：优先 BGE 语义去重，装不上自动降级回 bigram，流水线不崩
    engine = create_dedup_engine()
    kept, duplicates, stats = engine.filter(news)
    print(f"[去重] {stats['total']} 条 → 剔除 {stats['duplicates']} 条重复 → 留 {stats['kept']} 条")

    # 第 3 步：摘要（有 Key 走 LLM，没 Key 自动降级）
    kept = summarize_all(kept)

    # 第 4 步：生成日报
    md = build_report(kept, duplicates, stats, used_sample)
    os.makedirs("reports", exist_ok=True)
    path = os.path.join("reports", f"{date.today().isoformat()}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"[报告] 已生成 {path}")
    print("=" * 46)
    print("流水线跑完。统计：", stats)


if __name__ == "__main__":
    main()
