"""记忆模块（v3）：让情报官"越用越懂你"。

v3 的核心升级：日报不再一视同仁，而是根据你长期关心的主题来排序和分区。
这其实就是一个迷你版"长期记忆"——

- 我们把你关心的话题记在一个文件里（memory/interests.json），每个话题有"权重"
- 每天跑流水线时，用这个权重给每条新闻打分：
  你关心的话题权重高，相关新闻得分就高
- 跑完后更新权重：今天真出现了的话题权重涨一点（强化记忆），
  长期没出现的话题权重慢慢衰减（会遗忘）——和人的记忆很像

降级设计（和去重模块一致的可降级哲学）：
- 打分默认用关键词匹配（零依赖、云端也能跑）
- 如果本机装了 BGE，会自动叠加一层"语义匹配"，连"实习"≈"求职"这种同义也能识别
"""
import json
import os
from datetime import date

MEMORY_DIR = "memory"
MEMORY_FILE = os.path.join(MEMORY_DIR, "interests.json")

# 没有记忆文件时，用你（用户）声明关心的方向做种子
# 这些就是你 C9 长期记忆里提到的：AI / Agent / 实习 方向
DEFAULT_TOPICS = ["Agent", "智能体", "大模型", "实习", "开源", "RAG"]


def _now():
    return date.today().isoformat()


class InterestMemory:
    def __init__(self):
        self.topics = self._load()
        self._bge = None
        self._np = None
        self._topic_vecs = None
        self._bge_ready = None  # None=未探测, True/False=探测结果

    def _load(self):
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                topics = data.get("topics")
                if topics:
                    return topics
            except Exception:
                pass
        # 种子：每个话题初始权重 1.0
        return [{"name": t, "weight": 1.0, "seen": 0} for t in DEFAULT_TOPICS]

    def save(self):
        os.makedirs(MEMORY_DIR, exist_ok=True)
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump({"updated": _now(), "topics": self.topics},
                      f, ensure_ascii=False, indent=2)

    def _text(self, item):
        return (item.get("title", "") + " " +
                item.get("summary", "") + " " +
                item.get("brief", ""))

    def _ensure_bge(self):
        if self._bge_ready is not None:
            return self._bge_ready
        if os.getenv("FORCE_BIGRAM"):
            self._bge_ready = False
            return False
        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np
            self._np = np
            self._bge = SentenceTransformer("BAAI/bge-small-zh-v1.5")
            names = [t["name"] for t in self.topics]
            self._topic_vecs = [self._np.asarray(v, dtype=float)
                                for v in self._bge.encode(names, normalize_embeddings=True)]
            self._bge_ready = True
            print("[记忆] BGE 可用，启用语义兴趣匹配")
            return True
        except Exception as e:
            print(f"[记忆] BGE 不可用（{e.__class__.__name__}），兴趣匹配走关键词")
            self._bge_ready = False
            return False

    def _semantic(self, text):
        """返回与每个话题的余弦相似度列表；无 BGE 返回 None。"""
        if not self._ensure_bge():
            return None
        vec = self._np.asarray(
            self._bge.encode(text, normalize_embeddings=True), dtype=float)
        return [float(self._np.dot(vec, tv)) for tv in self._topic_vecs]

    def score(self, item):
        """给一条新闻打"你关心程度"分。返回 (分数, 命中的话题名列表)。"""
        text = self._text(item).lower()
        sem = self._semantic(self._text(item))  # 原始大小写交给 BGE 用
        total = 0.0
        matched = []
        for i, t in enumerate(self.topics):
            w = t["weight"]
            hit = 0.0
            if t["name"].lower() in text:
                hit = 1.0
            elif sem is not None and sem[i] >= 0.6:
                hit = sem[i]
            if hit > 0:
                total += hit * w
                matched.append(t["name"])
        # 归一化：单话题命中≈1；多话题叠加略微超 1，封顶示意
        score = total if total <= 1.0 else 1.0 + (total - 1.0) * 0.2
        return round(score, 3), matched

    def rank(self, items):
        """给每条新闻算分并排序，返回带 interest_score / matched 字段的列表（高分在前）。"""
        for it in items:
            s, m = self.score(it)
            it["interest_score"] = s
            it["matched"] = m
        return sorted(items, key=lambda x: x["interest_score"], reverse=True)

    def update(self, kept_items):
        """跑完一轮后更新权重：命中的话题涨一点，全部话题轻微衰减（会忘）。
        返回变化清单（供日报 v3.5「记忆变化」一节可视化）。
        """
        before = {t["name"]: t["weight"] for t in self.topics}
        hit_names = set()
        for it in kept_items:
            for name in it.get("matched", []):
                hit_names.add(name)
        for t in self.topics:
            if t["name"] in hit_names:
                t["weight"] = min(round(t["weight"] + 0.1, 3), 3.0)
                t["seen"] = t.get("seen", 0) + 1
            else:
                t["weight"] = max(round(t["weight"] * 0.97, 3), 0.2)
        self.save()

        changes = []
        for t in self.topics:
            b = before[t["name"]]
            a = t["weight"]
            delta = round(a - b, 3)
            if delta > 0:
                direction = "up"
            elif delta < 0:
                direction = "down"
            else:
                direction = "flat"
            changes.append({
                "name": t["name"], "before": b, "after": a,
                "delta": delta, "direction": direction,
                "hit": t["name"] in hit_names,
            })
        # 涨最多的排前面，跌的最靠前，便于一眼看重点
        changes.sort(key=lambda x: x["delta"], reverse=True)
        return changes


def load_memory():
    return InterestMemory()
