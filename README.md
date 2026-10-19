# AI 情报官（AI Intel Officer）

> 一个每天自动「看新闻 → 去重 → 提炼要点 → 生成私人日报」的资讯情报 Agent。
> 我自己每天都在用的生产力工具，不是教程复刻。

## 它解决什么问题

AI 领域一天几十条新闻，同一件事七八家媒体重复报。人工刷效率极低。
本项目的流水线：**多源采集 → 相似度去重 → LLM 提炼要点 → 生成 Markdown 日报**。

## 项目亮点（简历话术）

- **语义去重（v2 已上线）**&#8203;：优先用你学过的 **BGE embedding** 余弦相似度识别同一事件的不同报道，连「融资」vs「获得投资」这种同义改写也能拦下；装不上 BGE 时自动降级回字符 bigram，流水线不崩。实测去重率 xx%
- **可降级架构**：LLM 挂了自动降级为规则摘要，采集源全挂自动切示例数据，BGE 缺失自动回退 bigram，流水线 7×24 不断
- **量化统计**：每天输出采集量 / 去重率 / 收录数，用数据说话
- **定时推送（v2.5 已上线）**&#8203;：用 GitHub Actions 每天云端自动跑流水线并把日报提交回仓库，彻底解放双手，不用手动 `python main.py`
- **Roadmap**：兴趣记忆，越用越懂我（v3，复刻你 C9 的 Graph RAG 长期记忆）

## 快速开始

```bash
pip install openai feedparser        # openai 用于 LLM 摘要；feedparser 用于容错解析 RSS/Atom（机器之心等畸形 feed 也能吃）
pip install sentence-transformers    # 启用 v2 语义去重（会一并装 torch，约 1~2GB，留意磁盘空间）
export DEEPSEEK_API_KEY=sk-xxx       # 可选；不配则走离线规则摘要
python main.py                       # 产出 reports/2026-XX-XX.md
