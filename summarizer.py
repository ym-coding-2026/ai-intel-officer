"""摘要模块：把每条资讯浓缩成一句话「情报要点」。

优先走 LLM（OpenAI 兼容接口，DeepSeek / Kimi 都行）；
没有 Key 或网络不通时，自动降级为规则摘要（取内容前 40 字），流水线不断。

升级路线（v2）：一次请求批量总结所有资讯 + 生成整份日报的「今日导读」。
"""
import os

FALLBACK_NOTE = "（离线模式：未调用 LLM）"


def _rule_based_brief(item):
    """降级方案：不做真摘要，截取内容开头凑合用。"""
    text = item["summary"] or item["title"]
    return text[:40] + "…" + FALLBACK_NOTE


def summarize_all(items, api_key=None, base_url=None, model=None):
    """给每条资讯生成 brief 字段。LLM 挂了不影响流程，逐条降级。"""
    api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
    base_url = base_url or "https://api.deepseek.com/v1"
    model = model or "deepseek-chat"

    client = None
    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url)
        except Exception as e:
            print(f"[摘要] LLM 客户端初始化失败（{e.__class__.__name__}），使用规则摘要")

    for it in items:
        if client is None:
            it["brief"] = _rule_based_brief(it)
            continue
        try:
            prompt = (
                "用一句中文概括这条 AI 资讯的核心信息，不超过 40 字，"
                "不要套话，直接说事实：\n"
                f"标题：{it['title']}\n内容：{it['summary'][:300]}"
            )
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            it["brief"] = resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"[摘要] 单条失败（{e.__class__.__name__}），降级：{it['title'][:20]}")
            it["brief"] = _rule_based_brief(it)
    return items
