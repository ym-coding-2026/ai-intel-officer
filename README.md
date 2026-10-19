# AI 情报官（AI Intel Officer）

> 一个每天自动「看新闻 → 去重 → 提炼要点 → 生成私人日报」的资讯情报 Agent。
> 我自己每天都在用的生产力工具，不是教程复刻。

## 它解决什么问题

AI 领域一天几十条新闻，同一件事七八家媒体重复报。人工刷效率极低。
本项目的流水线：**多源采集 → 相似度去重 → LLM 提炼要点 → 兴趣排序 → 生成 Markdown 日报**。

## 项目亮点（简历话术）

- **语义去重（v2 已上线）**：优先用你学过的 **BGE embedding** 余弦相似度识别同一事件的不同报道，连「融资」vs「获得投资」这种同义改写也能拦下；装不上 BGE 时自动降级回字符 bigram，流水线不崩。实测去重率 xx%
- **兴趣记忆（v3 已上线）**：长期记住你关心的方向（Agent / 智能体 / 实习 …），每天用权重给新闻打分、关心置顶；跑完自动强化命中话题、衰减冷门话题——一个会学也会忘的迷你长期记忆，正是 C9 Graph RAG 长期记忆的落地版
- **记忆可视化（v3.5 已上线）**：每天日报末尾附「📈 记忆变化」一节，标出今天强化了哪些方向（↑）、淡忘了哪些（↓），让"会学也会忘"看得见，也方便你判断兴趣画像准不准
- **可降级架构**：LLM 挂了自动降级为规则摘要，采集源全挂自动切示例数据，BGE 缺失自动回退 bigram，兴趣匹配无 BGE 时走关键词，流水线 7×24 不断
- **量化统计**：每天输出采集量 / 去重率 / 收录数 / 命中兴趣条数，用数据说话
- **定时推送（v2.5 已上线）**：用 GitHub Actions 每天云端自动跑流水线并把日报 + 记忆文件提交回仓库，彻底解放双手，不用手动 `python main.py`

## 快速开始

```bash
pip install openai feedparser        # openai 用于 LLM 摘要；feedparser 用于容错解析 RSS/Atom
pip install sentence-transformers    # 启用 v2 语义去重 + v3 语义兴趣匹配（会一并装 torch，约 1~2GB，留意磁盘空间）
export DEEPSEEK_API_KEY=sk-xxx       # 可选；不配则走离线规则摘要
python main.py                       # 产出 reports/2026-XX-XX.md + memory/interests.json
```

> 想看「语义去重」到底比 bigram 强在哪？终端加一句 `export FORCE_BIGRAM=1` 再跑，
> 对比两次日报末尾「被拦下的重复报道」数量，差异一眼可见。

## 项目结构

| 文件 | 职责 |
|------|------|
| collector.py | 多源 RSS 采集，失败自动跳过 |
| dedup.py | BGE 语义去重 + bigram 兜底引擎（核心亮点） |
| summarizer.py | LLM 摘要 + 自动降级 |
| memory.py | v3 长期兴趣记忆：打分排序 + 权重更新（会学也会忘） |
| report.py | 生成带统计、按兴趣分区的 Markdown 日报 |
| main.py | 流水线编排 |
| memory/interests.json | 记忆文件（自动生成，随仓库回仓，跨天持久） |

## 定时推送（v2.5）

让日报每天自动出刊，不用你手动跑。原理：**GitHub Actions 在云端开一台临时机器 → 拉代码 → 装依赖 → 跑 `python main.py` → 把新日报 + 记忆文件 push 回仓库**。

```bash
# 本地只需做三件事（一次性的）：
# 1) 把本目录单独建一个 GitHub 仓库并 push 上去
# 2) 仓库 Settings → Secrets → Actions 新增 DEEPSEEK_API_KEY（没有就跳过，走降级）
# 3) 仓库 Settings → Actions 确认 Allow all actions 已开
# 之后每天北京时间 09:00 自动跑；也可在 Actions 页面点 Run workflow 手动触发
```

文件清单：`.github/workflows/daily.yml`（定时任务本体）、`requirements.txt`（云端依赖）。

> 想让云端也用上 BGE 语义去重 / 兴趣匹配？编辑 `requirements.txt` 取消 `sentence-transformers` 注释即可（install 会变慢）。
> 注：云端默认走 bigram / 关键词兜底，因为装 torch 太大太慢；你本机装过 sentence-transformers 的话本地仍能用 BGE。

## v3 兴趣记忆（重点）

普通日报「一视同仁」，v3 让系统记住你关心什么，把相关新闻置顶。

- **记忆文件**：`memory/interests.json`，存着你关心的话题和权重。第一跑没有它，会自动播种 `Agent / 智能体 / 大模型 / 实习 / 开源 / RAG`（你的方向）。
- **打分**：每条新闻和你的话题比对，命中的话题权重越高、得分越高；本机有 BGE 再叠加语义匹配（同义也能认）。
- **学习 & 遗忘**：每天跑完，命中的话题权重 +0.1（强化），没出现的话题 ×0.97（衰减，最低 0.2），权重写回 `interests.json`，并被 GitHub Actions 提交回仓库 → **真正的跨天记忆**。
- **想改关心方向？** 直接编辑 `memory/interests.json`，把 `name` 改成你关心的词、`weight` 调大一点即可，下次跑就生效。

## v3.5 记忆可视化

从 v3.5 起，每日日报末尾多一节 **「📈 记忆变化（今天学到的）」**：

- **↑ 强化**：今天真实出现的新闻命中的话题，权重 `+0.1`，这里会列出来「权重 a → b」
- **↓ 淡忘**：今天没出现的话题，权重 `×0.97`，这里也会标出

这一节既是「系统真的在学」的证据，也是给你看的**反馈仪表盘**：如果某天你明明关心某方向却看到它在 ↓，就说明需要去 `interests.json` 手动调高它的 `weight`。

## 调参笔记

- 去重阈值有两套尺度（在 `dedup.py` 的 `create_dedup_engine()` 里调）：
  - **bigram 引擎**：默认 `0.5`。嫌漏重复就调低（如 0.4），嫌误杀就调高（如 0.6）。
  - **BGE 引擎**：默认 `0.7`（归一化向量余弦，同一事件通常 0.6~0.85）。嫌漏就降到 0.6，嫌误杀就升到 0.8。
  - 判断方法：看日报末尾「被拦下的重复报道」里有没有混进不同的新闻。
- 兴趣排序阈值（在 `report.py` 的 `REC_THRESHOLD`）：默认 `0.3`。调高 → 进「为你推荐」的更严格（只放最相关的）；调低 → 放得更宽。
- 兴趣权重（在 `memory/interests.json`）：单话题命中 ≈ +0.1/天，衰减 ×0.97/天，区间 `[0.2, 3.0]`。想立刻让某话题置顶，手动把它的 weight 改成 3.0。
