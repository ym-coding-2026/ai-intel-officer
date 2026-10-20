"""v5 评测集：衡量检索召回率 + 答案命中率（基础评测）。

用法：  python eval.py
依赖：标准库 + （可选）openai。没设 DEEPSEEK_API_KEY 时只评检索，不评答案。

指标：
    - 检索召回@5：每条问题，相关关键词是否出现在检索到的前 5 条资料里；
    - 答案命中率：配了 Key 时，生成答案是否包含预期关键词（衡量「基于资料回答」）。
"""
import json
import os
import sys

from rag import _load_news, BM25, RAG


def _has_any(text, keys):
    return any(k in text for k in keys)


def main():
    with open("eval.json", encoding="utf-8") as f:
        cases = json.load(f)

    news = _load_news()
    bm25 = BM25(news)
    print(f"资料库：{len(news)} 条新闻，评测用例 {len(cases)} 条\n")

    recall_hit = 0
    ans_hit = 0
    ans_total = 0

    rag = RAG() if os.getenv("DEEPSEEK_API_KEY") else None

    for i, c in enumerate(cases, 1):
        q = c["q"]
        bs = bm25.scores(q)
        order = sorted(range(len(bs)), key=lambda j: bs[j], reverse=True)[:5]
        top_text = " ".join(
            news[j]["title"] + news[j]["brief"] for j in order)
        r_hit = _has_any(top_text, c["rel"])
        recall_hit += 1 if r_hit else 0

        ans_mark = "—"
        if rag is not None:
            ans_total += 1
            try:
                a = rag.ask(q)
                ok = _has_any(a, c["ans"])
            except Exception:
                ok = False
            ans_hit += 1 if ok else 0
            ans_mark = "✓" if ok else "✗"

        print(f"{i:2d}. {'✓' if r_hit else '✗'} 检索 | {ans_mark} 答案 | {q}")

    print("\n" + "=" * 40)
    print(f"检索召回@5 : {recall_hit}/{len(cases)} = "
          f"{recall_hit / len(cases):.0%}")
    if ans_total:
        print(f"答案命中率  : {ans_hit}/{ans_total} = "
              f"{ans_hit / ans_total:.0%}")
    else:
        print("答案命中率  : 未配置 DEEPSEEK_API_KEY，跳过")


if sys.argv and sys.argv[0].endswith("eval.py"):
    main()
