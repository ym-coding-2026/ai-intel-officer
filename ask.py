"""v5 · RAG 问答命令行入口。

用法：
    python ask.py "今天 Agent 有什么新进展"
    python ask.py            # 进入交互模式，连续提问

真正的检索/生成逻辑在 rag.py（BM25 + 可选向量混合 + 改写 + 重排 + 强制引用）。
本文件只是个薄封装，不写 __main__ 守卫（规避复制粘贴踩坑）。
"""
import sys
from rag import RAG


if sys.argv and sys.argv[0].endswith("ask.py"):
    rag = RAG()
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        question = input("你的问题（直接回车退出）：")
        if not question:
            sys.exit(0)
    print(rag.ask(question))
