"""v6-LCEL：把 LangChain 版 RAG 引擎挂成一个端到端文档问答 API（FastAPI）。

这就是「整合 FastAPI + LangChain，完成端到端文档问答 API」这句话的字面目标：
    - FastAPI  = 前台/服务员：负责收 HTTP 请求、回 JSON 响应
    - LangChain = 厨房：rag_lcel.py 里用 LCEL 把「检索 → 拼 prompt → 调模型 → 解析」写成一条管道
    - 端到端   = 你发一个问题，系统自动检索资料 + 生成带引用的答案，全程不用人插手

怎么跑（必须在项目根目录，有 reports 文件夹那一层）：
    .venv\\Scripts\\activate
    uvicorn server_lcel:app --reload
然后：
    - 浏览器开 http://127.0.0.1:8000/docs  看自动生成的接口页面
    - 普通问答：http://127.0.0.1:8000/ask?q=什么是多 Agent
    - 流式问答（打字机效果）：http://127.0.0.1:8000/ask/stream?q=什么是多 Agent

注意：本文件是 server.py 的「LangChain 版对照」，原 server.py（接手写版 rag.py）保留不动。
"""
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from rag_lcel import RAGLCEL

app = FastAPI(title="AI 情报官 · LCEL 文档问答 API")
_rag = RAGLCEL()  # 启动时加载资料库（和 ask_lcel.py 一样）


@app.get("/")
def root():
    # 健康检查：浏览器打开根地址能看到这句，说明服务起来了
    return {"status": "ok", "news_count": len(_rag.news),
            "engine": "LangChain LCEL"}


@app.get("/ask")
def ask(q: str):
    """非流式问答：返回完整 JSON。

    内部走 LCEL 管道 chain.invoke(q)：
        检索 Document → 填进 Prompt 模板 → ChatOpenAI(DeepSeek) → StrOutputParser
    """
    answer = _rag.ask(q)  # 默认 stream=False，一次性返回字符串
    return {"question": q, "answer": answer, "engine": "LangChain LCEL"}


@app.get("/ask/stream")
def ask_stream(q: str):
    """流式问答：用 LCEL 白送的 chain.stream 逐字返回（打字机效果）。

    想看「字一个个蹦出来」就访问这个端点；普通程序调用用上面的 /ask 即可。
    """
    chain = _rag.build_chain()

    def event_stream():
        try:
            for chunk in chain.stream(q):
                yield chunk
        except Exception as e:  # 流式里出错也要给客户端一个收尾，别静默挂死
            yield f"\n[流式生成中断：{type(e).__name__}]"

    return StreamingResponse(event_stream(), media_type="text/plain; charset=utf-8")
