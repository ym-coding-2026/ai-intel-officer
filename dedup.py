"""去重模块：判断两条资讯是不是同一件事，把重复的拦下来。

为什么要有它：同一件事各家媒体都会报，不去重日报就全是重复内容。

本文件提供两种引擎，接口完全一致（都返回 kept, duplicates, stats）：
- DedupEngine   ：v1 方案，字符 bigram 余弦相似度。纯标准库、离线可用、中文友好。
                   看「字长得像不像」——「融资」和「获得投资」字完全不同会漏判。
- BgeDedupEngine：v2 方案，BGE embedding 余弦相似度。看「意思像不像」——
                   「融资」和「获得投资」语义接近也能识别，这才是真正的语义去重。

create_dedup_engine() 工厂：优先用 BGE，装不上（缺依赖/没网）就自动降级回 bigram，
保证流水线永远能跑通——这正是 README 里吹的「可降级架构」。

升级路线（v3 待做）：接上你 C9 学的 Graph RAG，把实体关系也纳入去重判断。
"""
from collections import Counter


# ─────────────────────────────────────────────────────────────
# v1：字符 bigram 引擎（兜底用，零依赖，离线可跑）
# ─────────────────────────────────────────────────────────────
def _bigram_counts(text):
    """把文本拆成相邻两字一组，统计出现次数。例：「开源模型」→ 开源/源模/模型"""
    text = "".join(text.split())  # 去掉空白干扰
    return Counter(text[i:i + 2] for i in range(len(text) - 1))


def similarity(a, b):
    """两段文本的余弦相似度，范围 0~1，越大越像。"""
    ca, cb = _bigram_counts(a), _bigram_counts(b)
    if not ca or not cb:
        return 0.0
    dot = sum(ca[g] * cb.get(g, 0) for g in ca)
    norm_a = sum(v * v for v in ca.values()) ** 0.5
    norm_b = sum(v * v for v in cb.values()) ** 0.5
    return dot / (norm_a * norm_b)


class DedupEngine:
    """v1 去重引擎。filter() 接收今天的资讯，返回（去重后列表, 重复列表, 统计）。"""

    def __init__(self, threshold=0.5):
        # 阈值经验值：0.5 以上基本是同一件事的不同报道。调参思路见 README。
        self.threshold = threshold
        self.seen = []  # 已收录资讯的指纹（标题+摘要文本）

    def _fingerprint(self, item):
        return item["title"] + " " + item["summary"]

    def filter(self, news_list):
        kept, duplicates = [], []
        for item in news_list:
            fp = self._fingerprint(item)
            is_dup = any(similarity(fp, s) >= self.threshold for s in self.seen)
            if is_dup:
                duplicates.append(item)
            else:
                self.seen.append(fp)
                kept.append(item)
        total = len(news_list)
        stats = {
            "total": total,
            "kept": len(kept),
            "duplicates": len(duplicates),
            "dedup_rate": round(len(duplicates) / total, 2) if total else 0.0,
        }
        return kept, duplicates, stats


# ─────────────────────────────────────────────────────────────
# v2：BGE 语义引擎（核心升级，需要 sentence-transformers + torch）
# ─────────────────────────────────────────────────────────────
class BgeDedupEngine:
    """v2 去重引擎：用 BGE 把每条新闻压成向量，靠向量余弦判断是不是同一件事。

    关键区别（面试常考）：
    - v1 比的是「字频指纹」，只认字面相同；
    - v2 比的是「语义向量」，能认出「融资」≈「获得投资」这种同义改写。
    """

    def __init__(self, threshold=0.7, model_name="BAAI/bge-small-zh-v1.5"):
        # 阈值 0.7 是语义尺度的经验值：归一化向量余弦在 0~1，
        # 同一事件不同报道通常 0.6~0.85，完全不同事件通常 < 0.4。
        self.threshold = threshold
        self.model_name = model_name
        # 故意在方法内 import，缺依赖时只在真正用 BGE 时才报错，
        # 不会让整个模块在导入阶段就崩。
        from sentence_transformers import SentenceTransformer
        import numpy as np
        self._np = np
        print(f"[去重] 加载 BGE 模型 {model_name} …（首次会下载，稍等）")
        self.model = SentenceTransformer(model_name)
        print("[去重] BGE 模型就绪，启用「语义去重」v2")

    def _fingerprint(self, item):
        return item["title"] + " " + item["summary"]

    def _embed(self, text):
        # normalize_embeddings=True 让向量模长为 1，余弦相似度 = 向量点积
        vec = self.model.encode(text, normalize_embeddings=True)
        return self._np.asarray(vec, dtype=float)

    def filter(self, news_list):
        seen_vecs = []
        kept, duplicates = [], []
        for item in news_list:
            fp = self._fingerprint(item)
            vec = self._embed(fp)
            # 跟已收录的每条比点积；归一化后点积就是余弦相似度
            is_dup = any(float(self._np.dot(vec, s)) >= self.threshold
                         for s in seen_vecs)
            if is_dup:
                duplicates.append(item)
            else:
                seen_vecs.append(vec)
                kept.append(item)
        total = len(news_list)
        stats = {
            "total": total,
            "kept": len(kept),
            "duplicates": len(duplicates),
            "dedup_rate": round(len(duplicates) / total, 2) if total else 0.0,
        }
        return kept, duplicates, stats


# ─────────────────────────────────────────────────────────────
# 工厂：自动选引擎（优先 BGE，失败降级 bigram）
# ─────────────────────────────────────────────────────────────
def create_dedup_engine(prefer="bge", threshold=None):
    """返回可用的去重引擎。

    prefer="bge" 时先尝试 BGE，任何异常（没装包/没网/没显存）都自动退回 bigram，
    保证流水线永远能跑。threshold 不传则按引擎用默认值（BGE 0.7 / bigram 0.5）。
    """
    if prefer == "bge":
        try:
            return BgeDedupEngine(threshold=threshold or 0.7)
        except Exception as e:
            print(f"[去重] BGE 不可用（{e.__class__.__name__}: {e}），降级为字符 bigram 去重")
            return DedupEngine(threshold=threshold or 0.5)
    return DedupEngine(threshold=threshold or 0.5)
