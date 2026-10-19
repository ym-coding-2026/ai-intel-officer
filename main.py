"""AI 情报官 · 主流水线

采集 → 去重 → 摘要 → (v3) 兴趣排序 → 生成日报 → (v3) 更新记忆
跑法：python main.py
产出：reports/当天日期.md  +  memory/interests.json（记忆文件，会随仓库回仓）
"""
import os
from datetime import date

from collector import collect_all
from dedup import create_dedup_engine
from summarizer import summarize_all
from report import build_report
from memory import load_memory


def main():
    print("=" * 46)
    print("  AI 情报官 · 每日情报流水线启动")
    print("=" * 46)

    # v3：载入长期兴趣记忆（没有就自动播种你关心的方向）
    memory = load_memory()
    print(f"[记忆] 当前关心：{', '.join(t['name'] for t in memory.topics)}")

    # 第 1 步：采集
    news, used_sample = collect_all()

    # 第 2 步：去重（核心亮点之一：优先 BGE，失败降级 bigram）
    engine = create_dedup_engine()
    kept, duplicates, stats = engine.filter(news)
    print(f"[去重] {stats['total']} 条 → 剔除 {stats['duplicates']} 条重复 → 留 {stats['kept']} 条")

    # 第 3 步：摘要（有 Key 走 LLM，没 Key 自动降级）
    kept = summarize_all(kept)

    # 第 4 步（v3）：用兴趣记忆给新闻打分排序
    kept = memory.rank(kept)
    top = [it for it in kept if it["interest_score"] >= 0.3]
    print(f"[记忆] 命中你关心方向的新闻 {len(top)} 条")

    # 第 5 步：生成日报（含 v3.5 记忆变化一节，需要先把今天学到的兴趣更新出来）
    changes = memory.update(kept)
    md = build_report(kept, duplicates, stats, used_sample, memory_changes=changes)
    os.makedirs("reports", exist_ok=True)
    path = os.path.join("reports", f"{date.today().isoformat()}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"[报告] 已生成 {path}")
    print("[记忆] 兴趣权重已更新：",
          ", ".join(f"{t['name']}={t['weight']}" for t in memory.topics))
    print("=" * 46)
    print("流水线跑完。统计：", stats)


if __name__ == "__main__":
    main()
