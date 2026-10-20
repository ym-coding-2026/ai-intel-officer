"""v5 增强版 RAG 引擎：BM25 + 向量混合检索 + query rewrite + LLM rerank + 强制引用。

设计原则（沿用项目「可降级」哲学）：
    - BM25 永远在线：纯标准库，离线、零依赖、不下载任何模型；
    - 向量检索可选：仅当设了 USE_VECTOR=1 才懒加载 BGE 做 embedding，失败自动跳过；
    - query rewrite / rerank 可选：仅当配了 DEEPSEEK_API_KEY 才调用，失败自动跳过；
    - 任一增强不可用，都平滑退回「BM25 检索 + 原始问题」，流水线绝不崩。

用法（被 ask.py 调用，不在此文件写启动守卫，避免复制粘贴踩坑）：
    from rag import RAG
    rag = RAG()
    print(rag.ask("今天 Agent 有什么新进展"))
"""
import os
import re
import glob
import math


# ---------- 第 1 步：解析历史日报 ----------

def _load_news():
    """读 reports/ 下所有 .md，解析出 (标题, 要点, 来源, 标签, 日期, 链接)。"""
    news = []
    for path in sorted(glob.glob("reports/*.md")):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path))
        date = m.group(1) if m else "未知日期"
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()

        current = None
        for line in lines:
            if line.startswith("### "):
                if current:
                    news.append(current)
                title = re.sub(r"^\d+\.\s*", "", line[4:].strip())
                current = {"title": title, "brief": "", "source": "",
                           "tags": [], "date": date, "url": ""}
            elif current is not None:
                if "**要点**" in line:
                    current["brief"] = line.split("**要点**", 1)[1].lstrip("：:").strip()
                elif "**来源**" in line:
                    current["source"] = line.split("**来源**", 1)[1].lstrip("：:").strip()
                    mm = re.search(r"\((https?://[^)]+)\)", line)
                    if mm:
                        current["url"] = mm.group(1)
                elif "为什么推给你" in line:
                    current["tags"] = re.findall(r"`([^`]+)`", line)
        if current:
            news.append(current)
    return news


def _tokenize(text):
    """中文按「单字 + 相邻两字」切块，英文按单词。这是 BM25 与向量检索共用的切分。"""
    text = re.sub(r"[\s\W_]+", "", text)
    grams = set(text)                       # 单字
    for i in range(len(text) - 1):
        grams.add(text[i:i + 2])            # 相邻两字（bigram，缓解中文无空格）
    grams.update(re.findall(r"[a-zA-Z0-9]+", text))
    return grams


# ---------- 第 2 步：BM25 检索（永远在线） ----------

class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.docs = docs
        self.tok = [_tokenize(d["title"] + " " + d["brief"] + " " + " ".join(d["tags"]))
                    for d in docs]
        self.dl = [len(t) for t in self.tok]
        self.avgdl = (sum(self.dl) / len(self.dl)) if self.dl else 1
        df = {}
        for t in self.tok:
            for term in set(t):
                df[term] = df.get(term, 0) + 1
        n = len(self.tok)
        # Okapi BM25 的 IDF（加 1 防止为 0）
        self.idf = {term: math.log((n - f + 0.5) / (f + 0.5)) + 1
                    for term, f in df.items()}

    def scores(self, query):
        q = _tokenize(query)
        out = []
        for i, doc in enumerate(self.tok):
            score = 0.0
            f = {}
            for term in doc:
                f[term] = f.get(term, 0) + 1
            for term in q:
                if term in self.idf:
                    tf = f.get(term, 0)
                    denom = tf + self.k1 * (1 - self.b + self.b * self.dl[i] / self.avgdl)
                    score += self.idf[term] * (tf * (self.k1 + 1)) / denom
            out.append(score)
        return out


# ---------- 第 3 步：向量检索（可选，USE_VECTOR=1 才启用） ----------

_VECTOR_MODEL = None

def _embed(texts):
    """懒加载 BGE 做句向量；任何失败返回 None（调用方据此降级）。"""
    if not os.getenv("USE_VECTOR"):
        return None
    try:
        from sentence_transformers import SentenceTransformer
        global _VECTOR_MODEL
        if _VECTOR_MODEL is None:
            print("[向量] 正在加载 BGE 模型（仅 USE_VECTOR=1 时）…")
            _VECTOR_MODEL = SentenceTransformer("BAAI/bge-small-zh-v1.5")
        return _VECTOR_MODEL.encode(texts, normalize_embeddings=True).tolist()
    except Exception as e:
        print(f"[向量] 不可用，降级为仅 BM25：{e.__class__.__name__}")
        return None


class VectorIndex:
    def __init__(self, docs):
        self.docs = docs
        texts = [d["title"] + "。" + d["brief"] for d in docs]
        self.matrix = _embed(texts)          # None 表示不可用

    def scores(self, query):
        if self.matrix is None:
            return None
        try:
            qv = _embed([query])[0]
        except Exception:
            return None
        return [sum(a * b for a, b in zip(qv, vec)) for vec in self.matrix]


# ---------- 第 4 步：LLM 增强（改写 / 重排，需 DEEPSEEK_API_KEY） ----------

def _llm(prompt, temperature=0.3, timeout=30):
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key,
                        base_url=os.getenv("DEEPSEEK_BASE", "https://api.deepseek.com/v1"),
                        timeout=timeout)
        resp = client.chat.completions.create(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            timeout=timeout,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[LLM] 调用失败，跳过该增强：{e.__class__.__name__}")
        return None


def rewrite_query(question):
    """把口语化问题扩写成检索友好的关键词串；失败则原样返回。"""
    out = _llm(
        "你是检索系统助手。请把用户问题改写成适合关键词检索的短语，"
        "保留核心实体，补上可能的同义词，用空格分隔，不要解释。\n问题："
        + question, temperature=0.2)
    return out if out else question


def rerank(question, docs, k=5):
    """让 DeepSeek 从候选里挑出最相关的 k 条，返回文档下标列表；失败则返回前 k 个。"""
    if len(docs) <= k:
        return list(range(len(docs)))
    numbered = "\n".join(
        f"[{i + 1}] 《{d['title']}》 {d['brief']}" for i, d in enumerate(docs))
    out = _llm(
        "下面是和用户问题可能相关的资料（已编号）。请只返回最相关的 "
        f"{k} 条编号（如 1 3 5，用空格分隔，不要其它内容）。\n"
        f"问题：{question}\n{numbered}", temperature=0.1)
    if not out:
        return list(range(k))
    picks = [int(x) - 1 for x in re.findall(r"\d+", out) if x.isdigit()]
    picks = [p for p in picks if 0 <= p < len(docs)]
    seen, uniq = set(), []
    for p in picks:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq[:k] if uniq else list(range(k))


# ---------- 第 5 步：编排（混合检索 → 重排） ----------

def _rrf(rank_lists, k=60):
    """Reciprocal Rank Fusion：把多路排名融合成一分，不依赖分数量纲。"""
    fused = {}
    for ranks in rank_lists:
        for rank, idx in enumerate(ranks):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return sorted(fused.items(), key=lambda x: x[1], reverse=True)


class RAG:
    def __init__(self):
        self.news = _load_news()
        self.bm25 = BM25(self.news) if self.news else None
        self.vec = VectorIndex(self.news) if self.news else None
        self.use_rewrite = bool(os.getenv("DEEPSEEK_API_KEY"))
        self.use_rerank = bool(os.getenv("DEEPSEEK_API_KEY"))
        if not self.news:
            print("[RAG] 未找到 reports/*.md，资料库为空")

    def retrieve(self, question, topk=5):
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
        cand_idx = [i for i, _ in fused]
        cand = [self.news[i] for i in cand_idx]

        if self.use_rerank and len(cand) > topk:
            picks = rerank(question, cand, k=topk)
            cand = [cand[p] for p in picks]
            print(f"[重排] 经 LLM 筛选出 {len(cand)} 条")
        else:
            cand = cand[:topk]
        return cand

    def _context(self, docs):
        blocks = []
        for i, d in enumerate(docs, 1):
            tagstr = "、".join(d["tags"]) or "无"
            blocks.append(
                f"[{i}] ({d['date']}) 《{d['title']}》 来源：{d['source']}\n"
                f"    要点：{d['brief']}\n    标签：{tagstr}")
        return "\n".join(blocks)

    def ask(self, question, topk=5):
        docs = self.retrieve(question, topk=topk)
        if not docs:
            return ("资料库里没找到和这个问题相关的新闻（可以换个说法，"
                    "或等明天的日报攒多点）。")

        ctx = self._context(docs)
        key = os.getenv("DEEPSEEK_API_KEY")
        if not key:
            listing = "\n".join(f"- 《{d['title']}》（{d['date']}）" for d in docs)
            return "（未配置 DEEPSEEK_API_KEY，仅列出检索到的相关新闻）\n" + listing

        prompt = (
            "你是 AI 资讯情报助手。下面是从历史日报中检索到的资料（已编号）：\n\n"
            f"{ctx}\n\n"
            f"用户问题：{question}\n\n"
            "要求：\n"
            "1) 只基于上述资料用中文简洁回答；\n"
            "2) 每个事实后必须用对应编号标注来源，如 [1][3]；\n"
            "3) 若资料里没有相关信息，明确说「没有找到相关报道」，不要编造。"
        )
        try:
            from openai import OpenAI
            client = OpenAI(api_key=key,
                            base_url=os.getenv("DEEPSEEK_BASE",
                                               "https://api.deepseek.com/v1"),
                            timeout=30)
            resp = client.chat.completions.create(
                model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3, timeout=30)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            listing = "\n".join(f"- 《{d['title']}》（{d['date']}）" for d in docs)
            return f"（DeepSeek 调用失败：{e.__class__.__name__}，改为列出检索结果）\n{listing}"
