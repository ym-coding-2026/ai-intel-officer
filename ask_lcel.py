"""v6-LCEL · RAG 问答命令行入口（LCEL 版）。

对比 ask.py（手工拼 prompt + 直连 OpenAI SDK），本文件调用的 rag_lcel.RAGLCEL
把「检索→prompt→模型→解析」写成了 LCEL 管道，并额外支持流式输出。

用法：
    python ask_lcel.py "什么是多 Agent"
    python ask_lcel.py --stream "什么是多 Agent"   # 打字机式逐字输出
    python ask_lcel.py                              # 进入交互模式，连续提问
    python ask_lcel.py --stream                     # 交互模式 + 流式

真正的 LCEL 链路在 rag_lcel.py。本文件只是薄封装，不写 __main__ 守卫（规避复制粘贴踩坑）。
"""
import sys
from rag_lcel import RAGLCEL


if sys.argv and sys.argv[0].endswith("ask_lcel.py"):
    stream = "--stream" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    rag = RAGLCEL()

    if args:
        question = " ".join(args)
        answer = rag.ask(question, stream=stream)
        if not stream:          # 流式模式下 ask 内部已经打印过了
            print(answer)
    else:
        print("（交互模式，直接输入问题，空回车退出；加 --stream 可逐字输出）")
        while True:
            question = input("你的问题：")
            if not question:
                break
            answer = rag.ask(question, stream=stream)
            if not stream:
                print(answer)
