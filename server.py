"""v6 雏形：把 RAG 问答挂成一个网页接口（FastAPI）。

怎么跑（在 ai-intel-officer 项目根目录里）：
    .venv/Scripts/activate
    uvicorn server:app --reload
然后浏览器开 http://127.0.0.1:8000/docs 看自动生成的接口页面，
或访问 http://127.0.0.1:8000/ask?q=什么是混合检索

注意：rag.py 是按「当前目录」找 reports/*.md 的，
所以必须在项目根目录（有 reports 文件夹那一层）下启动 uvicorn。
"""
from fastapi import FastAPI
from rag import RAG

app = FastAPI(title="AI 情报官 · 问答接口")
_rag = RAG()  # 启动时把资料库加载好（和 ask.py 一样）


@app.get("/")
def root():
    # 健康检查：浏览器打开根地址能看到这句，说明服务起来了
    return {"status": "ok", "news_count": len(_rag.news)}


@app.get("/ask")
def ask(q: str):
    """问答接口：浏览器访问 /ask?q=你的问题"""
    return {"question": q, "answer": _rag.ask(q)}
