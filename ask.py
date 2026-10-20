"""v5 · RAG 问答：让情报官从"广播员"变成"能对话的助手"。

用法：
    python ask.py "今天 Agent 有什么新进展"
    python ask.py            # 进入交互模式，连续提问

原理（RAG = 检索增强生成）：
    1) 检索：读 reports/*.md 里所有历史新闻，用字重叠给每条打分，取最相关的 Top5
    2) 生成：把 Top5 拼成"上下文"，连同你的问题一起交给 DeepSeek，让它基于资料回答
    3) 不乱编：prompt 里写明"资料没有就老实说没有"，避免模型瞎编

依赖：标准库 + openai（已在 requirements.txt）。没设 DEEPSEEK_API_KEY 也能跑，
      只是会降级为"只列出检索到的相关新闻标题"。
"""
import os
import re
import sys
import glob


# ---------- 第 1 步：把历史日报解析成一条条新闻 ----------

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
            # 以 ### 开头的是一条新闻的标题
            if line.startswith("### "):
                if current:
                    news.append(current)
                title = line[4:].strip()
                title = re.sub(r"^\d+\.\s*", "", title)  # 去掉 "1. " 前缀
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
                    # 形如：因为你关注 `开源` / `Agent`
                    current["tags"] = re.findall(r"`([^`]+)`", line)
        if current:
            news.append(current)
    return news


# ---------- 第 2 步：轻量检索（零依赖，不装任何大模型） ----------

def _tokenize(text):
    """中文按"相邻两字"切块（bigram），英文按单词。去掉标点和空格。"""
    text = re.sub(r"[\s\W_]+", "", text)  # 去标点空白，只留中英文数字
    grams = set()
    for i in range(len(text) - 1):
        grams.add(text[i:i + 2])          # 每两个相邻字一组
    grams.update(re.findall(r"[a-zA-Z0-9]+", text))  # 英文单词整体
    return grams


def _retrieve(question, news, topk=5):
    """给每条新闻打分，返回最相关的 topk 条。分数=标题重合×2 + 正文重合。"""
    q = _tokenize(question)
    if not q:
        return []
    scored = []
    for it in news:
        doc = it["title"] + " " + it["brief"] + " " + " ".join(it["tags"])
        d = _tokenize(doc)
        hit = len(q & d)
        if hit == 0:
            continue
        title_hit = len(q & _tokenize(it["title"]))  # 标题命中更重要
        scored.append((hit + title_hit * 2, it))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in scored[:topk]]


# ---------- 第 3 步：交给 DeepSeek 生成回答 ----------

def ask(question, api_key=None, base_url=None, model=None):
    """检索 + 生成。返回一段中文回答文字。"""
    news = _load_news()
    hits = _retrieve(question, news, topk=5)
    if not hits:
        return "资料库里没找到和这个问题相关的新闻（你可以换个说法，或等明天的日报攒多点）。"

    # 把检索到的上下文拼出来
    ctx = []
    for i, it in enumerate(hits, 1):
        tagstr = "、".join(it["tags"]) or "无"
        ctx.append(
            f"[{i}] ({it['date']}) 《{it['title']}》\n"
            f"    要点：{it['brief']}\n"
            f"    标签：{tagstr}  来源：{it['source']}"
        )
    context = "\n".join(ctx)

    api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        # 没配 Key：降级，至少把检索到的标题列出来
        listing = "\n".join(f"- 《{it['title']}》（{it['date']}）" for it in hits)
        return "（未配置 DEEPSEEK_API_KEY，仅列出检索到的相关新闻）\n" + listing

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key,
                        base_url=base_url or "https://api.deepseek.com/v1",
                        timeout=30)
        prompt = (
            "你是 AI 资讯情报助手。下面是从历史日报里检索到的相关新闻（按相关度排序）：\n\n"
            f"{context}\n\n"
            f"用户问题：{question}\n\n"
            "请只基于上面的资料，用中文简洁回答。如果资料里没有相关信息，就老实说"
            "“没找到相关报道”，不要编造任何内容。"
        )
        resp = client.chat.completions.create(
            model=model or "deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            timeout=30,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        # 调用失败也别崩，退而求其次列出原始新闻
        listing = "\n".join(f"- 《{it['title']}》（{it['date']}）" for it in hits)
        return f"（DeepSeek 调用失败：{e.__class__.__name__}，改为列出检索结果）\n{listing}"


# ---------- 命令行入口（import 时不触发，只有直接跑 python ask.py 才问答） ----------

if sys.argv and sys.argv[0].endswith("ask.py"):
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        question = input("你的问题（直接回车退出）：")
        if not question:
            sys.exit(0)
    print(ask(question))
