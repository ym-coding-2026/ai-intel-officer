"""用 LCEL 重写的 RAG 引擎（v6-LCEL）。

为什么重写：
    rag.py 里「检索 → 拼上下文 → 调模型 → 解析答案」是一段手工拼字符串 + 手工调
    OpenAI SDK 的代码。这正好是 LCEL（LangChain Expression Language）最擅长的场景：
    把它写成一条「管道」，数据从左流到右：

        chain = (
            {"context": retriever | format_docs, "question": RunnablePassthrough()}
            | prompt        # 把问题+上下文填进提示词模板
            | model         # 发给 DeepSeek
            | parser        # 把模型回答解析成纯文字
        )

    用 | 拼起来的好处（LCEL 白送，不用自己写）：
        - chain.invoke(q)   一次问
        - chain.stream(q)   流式输出（打字机效果）
        - chain.batch([q1,q2])  一次问多个，自动并行
        - 原生容错/重试/异步

设计原则（沿用项目「可降级」哲学）：
    - 检索部分**直接复用 rag.py 的 BM25 + 可选向量 + 改写 + 重排**，不重复造轮子；
    - 没配 DEEPSEEK_API_KEY 时，不报错，只列出检索到的相关新闻；
    - 检索结果包装成 LangChain 的 Document，方便以后换成真正的向量库 Retriever。

用法（被 ask_lcel.py 调用，本文件不写启动守卫，避免复制粘贴踩坑）：
    from rag_lcel import RAGLCEL
    rag = RAGLCEL()
    print(rag.ask("什么是多 Agent"))          # 普通回答
    rag.ask("什么是多 Agent", stream=True)     # 流式输出
"""
import os

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_openai import ChatOpenAI

# 复用原 rag.py 里已经验证过的检索逻辑（BM25/向量/改写/重排），只重写「生成」这一段
from rag import (_load_news, BM25, VectorIndex,
                 rewrite_query, rerank, _rrf)


# ---------- 第 1 步：提示词模板（LCEL 的标准写法：system + human） ----------

PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "你是 AI 资讯情报助手。下面是从历史日报中检索到的资料（已编号）：\n\n"
     "{context}"),
    ("human",
     "用户问题：{question}\n\n"
     "要求：\n"
     "1) 只基于上述资料用中文简洁回答；\n"
     "2) 每个事实后必须用对应编号标注来源，如 [1][3]；\n"
     "3) 若资料里没有相关信息，明确说「没有找到相关报道」，不要编造。"),
])


# ---------- 第 2 步：RAGLCEL 引擎 ----------

class RAGLCEL:
    def __init__(self):
        self.news = _load_news()
        self.bm25 = BM25(self.news) if self.news else None
        self.vec = VectorIndex(self.news) if self.news else None
        self.use_rewrite = bool(os.getenv("DEEPSEEK_API_KEY"))
        self.use_rerank = bool(os.getenv("DEEPSEEK_API_KEY"))
        if not self.news:
            print("[RAG] 未找到 reports/*.md，资料库为空")

    # —— 检索（复用 rag.py 的逻辑），返回 LangChain 的 Document 列表 ——
    def _retrieve_docs(self, question, topk=5):
        if not self.news or self.bm25 is None:
            return []
        q = rewrite_query(question) if self.use_rewrite else question
        if q != question:
            print(f"[改写] {question!r} -> {q!r}")

        bs = self.bm25.scores(q)
        order = sorted(range(len(bs)), key=lambda i: bs[i], reverse=True)
        rank_lists = [order]

        vs = self.vec.scores(q) if self.vec else None
        if vs:
            vorder = sorted(range(len(vs)), key=lambda i: vs[i], reverse=True)
            rank_lists.append(vorder)
            print("[混合] BM25 + 向量 RRF 融合")

        fused = _rrf(rank_lists)
        cand = [self.news[i] for i, _ in fused]
        if self.use_rerank and len(cand) > topk:
            picks = rerank(question, cand, k=topk)
            cand = [cand[p] for p in picks]
            print(f"[重排] 经 LLM 筛选出 {len(cand)} 条")
        else:
            cand = cand[:topk]

        # 包装成 Document：page_content 是正文，metadata 记来源信息
        docs = []
        for d in cand:
            tagstr = "、".join(d["tags"]) or "无"
            page = (f"《{d['title']}》 来源：{d['source']} 标签：{tagstr}\n"
                    f"要点：{d['brief']}")
            docs.append(Document(page_content=page, metadata={
                "title": d["title"], "date": d["date"], "source": d["source"],
                "tags": d["tags"],
            }))
        return docs

    # —— 把 Document 列表拼成提示词里要填的 context 字符串 ——
    def _format_docs(self, docs):
        blocks = []
        for i, d in enumerate(docs, 1):
            md = d.metadata
            tagstr = "、".join(md["tags"]) or "无"
            blocks.append(
                f"[{i}] ({md['date']}) 《{md['title']}》 来源：{md['source']}\n"
                f"    要点：{md['brief']}\n    标签：{tagstr}")
        return "\n".join(blocks)

    # —— 用 LCEL 拼出完整 chain ——
    def build_chain(self):
        model = ChatOpenAI(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE", "https://api.deepseek.com/v1"),
            temperature=0.3,
            timeout=30,
            streaming=True,   # 开启流式，配合 chain.stream 使用
        )
        retriever = RunnableLambda(self._retrieve_docs)
        chain = (
            {"context": retriever | RunnableLambda(self._format_docs),
             "question": RunnablePassthrough()}
            | PROMPT
            | model
            | StrOutputParser()
        )
        return chain

    # —— 对外问答入口 ——
    def ask(self, question, topk=5, stream=False):
        docs = self._retrieve_docs(question, topk=topk)
        if not docs:
            return ("资料库里没找到和这个问题相关的新闻（可以换个说法，"
                    "或等明天的日报攒多点）。")

        # 无 Key 降级：只列新闻，不生成回答
        if not os.getenv("DEEPSEEK_API_KEY"):
            listing = "\n".join(f"- 《{d.metadata['title']}》（{d.metadata['date']}）"
                                for d in docs)
            return "（未配置 DEEPSEEK_API_KEY，仅列出检索到的相关新闻）\n" + listing

        chain = self.build_chain()
        if stream:
            # LCEL 白送的流式输出：字一个个蹦出来
            out = []
            for chunk in chain.stream(question):
                print(chunk, end="", flush=True)
                out.append(chunk)
            print()  # 收尾换行
            return "".join(out)

        # 普通一次性回答
        return chain.invoke(question)
