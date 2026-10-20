"""AI 情报官 · 主流水线

采集 → 去重 → 摘要 → (v3) 兴趣排序 → 生成日报 → (v3) 更新记忆 → (v4) 主动推送
跑法：python main.py
      想跳过语义模型秒跑：FORCE_BIGRAM=1 python main.py
产出：reports/当天日期.md  +  memory/interests.json
"""
import os
from datetime import date

from collector import collect_all
from dedup import create_dedup_engine
from summarizer import summarize_all
from report import build_report
from memory import load_memory
from notifier import notify


def main():
    print("=" * 46)
    print("  AI 情报官 · 每日情报流水线启动")
    print("=" * 46)

    # v3：载入长期兴趣记忆（没有就自动播种你关心的方向）
    memory = load_memory()
    print(f"[记忆] 当前关心：{', '.join(t['name'] for t in memory.topics)}")

    # 第 1 步：采集
    news, used_sample = collect_all()

    # 第 2 步：去重。FORCE_BIGRAM=1 时不加载 BGE 语义模型（国内网络拉不动就秒跑）
    if os.getenv("FORCE_BIGRAM"):
        print("[去重] 已设 FORCE_BIGRAM，跳过 BGE 语义模型，用字符 bigram 去重")
        engine = create_dedup_engine(prefer="bigram")
    else:
        engine = create_dedup_engine()
    kept, duplicates, stats = engine.filter(news)
    print(f"[去重] {stats['total']} 条 → 剔除 {stats['duplicates']} 条重复 → 留 {stats['kept']} 条")

    # 第 3 步：摘要（有 Key 走 LLM，没 Key 自动降级）
    kept = summarize_all(kept)

    # 第 4 步（v3）：用兴趣记忆给新闻打分排序
    kept = memory.rank(kept)
    top = [it for it in kept if it["interest_score"] >= 0.3]
    print(f"[记忆] 命中你关心方向的新闻 {len(top)} 条")

    # 第 5 步：生成日报（含记忆变化一节）
    changes = memory.update(kept)
    md = build_report(kept, duplicates, stats, used_sample, memory_changes=changes)
    os.makedirs("reports", exist_ok=True)
    path = os.path.join("reports", f"{date.today().isoformat()}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"[报告] 已生成 {path}")

    # 第 6 步（v4）：主动推送。没配渠道会自动跳过，流水线不受影响
    sent = notify(md, f"AI 情报官 · 日报 {date.today().isoformat()}")
    if sent:
        print(f"[推送] 今日日报已送达：{', '.join(sent)}")
    print("[记忆] 兴趣权重已更新：",
          ", ".join(f"{t['name']}={t['weight']}" for t in memory.topics))
    print("=" * 46)
    print("流水线跑完。统计：", stats)


main()
