"""采集模块：从多个 RSS / Atom 源抓取 AI 资讯。

v2.3 改进（本次）：
- 下线机器之心（官方 RSS 畸形 XML + RSSHub 路由下线，源头坏了修不好），换爱范儿补位
- 源配置降级为"能抓到几条算几条"，单源损坏不再影响整份日报

v2.2 改进：
- 请求时带上浏览器 User-Agent 伪装成浏览器，解决"网站认出我们是程序就不给数据"的问题
  （机器之心拿到 0 条的元凶：feedparser 默认身份是 UniversalFeedParser，被网站识别后返回空内容）
- 某个源解析出 0 条时，打印"体检信息"（feedparser 的 bozo 异常），一眼看出被挡的原因
- 零网络或全部源失败时，自动降级为内置示例数据，流水线不崩。
依赖：pip install feedparser
"""
import re

import feedparser

# 白名单清洗：RSS 标题偶尔混入乱码（坏掉的 emoji、不可见控制符、生僻符号块），
# 只保留常用字符（英文/数字/汉字/中英文标点），其余一律剔除。
# 代价是标题里的 emoji 也会被去掉——用一点装饰换日报干净，值得。
_SAFE_CHAR = re.compile(
    "[^\\u0020-\\u007e"   # 英文、数字、常用英文符号
    "\\u00a0-\\u024f"     # 拉丁字母扩展（拼音、欧洲字母）
    "\\u2013\\u2014\\u2018\\u2019\\u201c\\u201d\\u2026\\u00b7"  # 常见引号破折号省略号
    "\\u3000-\\u303f"     # 中文标点
    "\\u4e00-\\u9fff"     # 汉字
    "\\uff00-\\uffef]"    # 全角字母数字标点
)


def _clean(text):
    """剔除乱码/不可见字符，返回干净文本。"""
    return _SAFE_CHAR.sub("", text).strip()

# 伪装成浏览器的身份声明。网站看到这个，就当作正常访客对待
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}

# 要盯的 RSS 源，想加源就往里添一行
# 注：机器之心官方 RSS 返回畸形 XML（体检确认 not well-formed），RSSHub 路由也已下线，
#     属于"源头坏了修不好"，暂时下线，由爱范儿补位。
RSS_SOURCES = [
    {"name": "量子位", "url": "https://www.qbitai.com/feed"},
    {"name": "爱范儿", "url": "https://www.ifanr.com/feed"},
]

# 内置示例数据：故意放两条几乎一样的新闻，用来演示去重模块的效果
SAMPLE_NEWS = [
    {"title": "OpenAI 发布新一代推理模型，数学能力大幅提升", "summary": "OpenAI 发布新款推理模型，在多项数学基准测试上刷新纪录，推理成本降低一半。", "source": "示例-机器之心", "url": "https://example.com/1"},
    {"title": "OpenAI 新推理模型发布：数学成绩暴涨，成本减半", "summary": "OpenAI 推出新一代推理模型，数学基准测试刷新纪录，同时推理成本下降 50%。", "source": "示例-量子位", "url": "https://example.com/2"},
    {"title": "智元机器人完成新一轮融资", "summary": "智元机器人宣布完成新一轮融资，将用于人形机器人量产产线建设。", "source": "示例-机器之心", "url": "https://example.com/3"},
    {"title": "DeepSeek 开源新版 MoE 模型", "summary": "DeepSeek 开源最新混合专家模型，推理效率提升，支持更长上下文。", "source": "示例-量子位", "url": "https://example.com/4"},
    {"title": "谷歌发布 Agent 开发框架新版本", "summary": "谷歌更新其 Agent 开发框架，新增多智能体协作与工具调用能力。", "source": "示例-机器之心", "url": "https://example.com/5"},
    {"title": "DeepSeek 开源最新 MoE 大模型，效率大增", "summary": "DeepSeek 发布并开源新版 MoE 大模型，长上下文支持与推理效率显著提升。", "source": "示例-量子位", "url": "https://example.com/6"},
]


def fetch_feed(source, timeout=15, limit=15):
    """抓取单个 RSS/Atom 源，返回资讯列表。失败抛异常，由调用方决定跳过。"""
    parsed = feedparser.parse(source["url"], request_headers=HEADERS)
    entries = getattr(parsed, "entries", []) or []
    items = []
    for e in entries[:limit]:
        title = _clean(e.get("title") or "")
        if not title:
            continue
        summary = _clean(e.get("summary") or e.get("description") or "")
        link = (e.get("link") or "").strip()
        items.append(
            {
                "title": title,
                "summary": summary[:300],
                "source": source["name"],
                "url": link,
            }
        )
    return items


def diagnose(source):
    """某个源拿到 0 条时，打印体检信息，方便定位是网络问题还是被网站挡了。"""
    parsed = feedparser.parse(source["url"], request_headers=HEADERS)
    status = getattr(parsed, "status", None)
    bozo = getattr(parsed, "bozo", 0)
    reason = getattr(parsed, "bozo_exception", "")
    print(f"    └ 体检: HTTP状态={status}, 格式异常={bozo}, 原因={reason}")


def collect_all():
    """抓取所有源。返回 (资讯列表, 是否使用了示例数据)。"""
    all_news = []
    for src in RSS_SOURCES:
        try:
            batch = fetch_feed(src)
            all_news.extend(batch)
            print(f"[采集] {src['name']}: 拿到 {len(batch)} 条")
            if not batch:
                diagnose(src)
        except Exception as ex:
            print(f"[采集] {src['name']} 失败（{ex.__class__.__name__}: {ex}），跳过")
    used_sample = False
    if not all_news:
        print("[采集] 所有源都不可达，使用内置示例数据演示流程")
        all_news = [dict(n) for n in SAMPLE_NEWS]
        used_sample = True
    return all_news, used_sample
