# AI 情报官（AI Intel Officer）

> 一个每天自动「看新闻 → 去重 → 提炼要点 → 生成私人日报 → 主动推送 → 你还能反过来问它」的资讯情报 Agent。
> 从 v1 到 v5.1 持续进化：采集 → 语义去重 → 兴趣记忆 → 主动送达 → 周报 → AI 摘要 → RAG 问答 → 混合检索评测。
> 我自己每天都在用的生产力工具，不是教程复刻。

## 它解决什么问题

AI 领域一天几十条新闻，同一件事七八家媒体重复报。人工刷效率极低。
本项目的流水线：**多源采集 → 相似度去重 → LLM 提炼要点 → 兴趣排序 → 生成 Markdown 日报 → 主动推送 → 可对话问答（RAG）**。

## 版本谱系

| 版本 | 能力 |
|------|------|
| v1 | 采集 → 去重 → 日报流水线雏形 |
| v2 / v2.5 | BGE 语义去重（可降级 bigram）；GitHub Actions 每日自动跑 |
| v3 / v3.5 | 兴趣记忆（会学也会忘）+ 记忆可视化 |
| v4 | 主动推送：邮箱 / 企业微信（双渠道可降级） |
| v4.5 | 今日必读 Top3 + 每条「为什么推给你」+ 邮件主题翻新 |
| v4.7 | 自动周报（读历史日报聚类汇总） |
| v4.8 | DeepSeek 真·AI 摘要（写人话要点） |
| v5 | RAG 问答：你问，它翻档案回答 |
| v5.1 | 混合检索（BM25 + 向量 RRF）、query rewrite、LLM rerank、强制引用、评测集 |

## 项目亮点（简历话术）

- **语义去重（v2 已上线）**：优先用 BGE embedding 余弦相似度识别同一事件的不同报道，连「融资」vs「获得投资」这种同义改写也能拦下；装不上 BGE 时自动降级回字符 bigram，流水线不崩。实测去重率约 40%。
- **兴趣记忆（v3 已上线）**：长期记住你关心的方向（Agent / 智能体 / 实习 …），每天用权重给新闻打分、关心置顶；跑完自动强化命中话题、衰减冷门话题——一个会学也会忘的迷你长期记忆，正是 C9 Graph RAG 长期记忆的落地版。
- **记忆可视化（v3.5 已上线）**：每天日报末尾附「📈 记忆变化」一节，标出今天强化了哪些方向（↑）、淡忘了哪些（↓），让"会学也会忘"看得见。
- **主动送达（v4 / v4.5 已上线）**：日报不再只躺在仓库里，而是主动推到邮箱（或企业微信）；并升级为「今日必读 Top3 + 为什么推给你 + 带头条标题的邮件主题」，推荐不再黑箱。
- **AI 摘要（v4.8 已上线）**：DeepSeek 把每条新闻写成通顺人话要点；无 Key 自动降级规则摘抄。
- **RAG 问答（v5 / v5.1 已上线）**：把历史日报建成可检索知识库，你问一句，它检索 Top5 → 改写 → 重排 → DeepSeek 基于真实资料生成带 `[n]` 引用的中文回答，资料没有就老实拒答。混合检索 = BM25（默认离线）+ 向量（可选）经 RRF 融合；并配评测集量化检索召回@5。
- **可降级架构**：LLM 挂了降级规则摘要，采集全挂切示例数据，BGE 缺失回退 bigram，向量缺失回退纯 BM25，流水线 7×24 不断。
- **量化统计**：每天输出采集量 / 去重率 / 收录数 / 命中兴趣条数，用数据说话。
- **定时推送（v2.5 已上线）**：用 GitHub Actions 每天云端自动跑流水线并把日报 + 记忆文件提交回仓库，彻底解放双手。

## 快速开始

```bash
pip install openai feedparser        # openai 用于 LLM 摘要/问答；feedparser 用于容错解析 RSS/Atom
pip install sentence-transformers    # 可选：启用 v2 语义去重 + v3 语义兴趣匹配（会一并装 torch，约 1~2GB）
export DEEPSEEK_API_KEY=sk-xxx       # 可选；不配则走离线规则摘要，问答降级为列标题
python main.py                       # 产出 reports/当天.md + memory/interests.json
```

常用命令：

```bash
FORCE_BIGRAM=1 python main.py        # 跳过语义模型，秒跑（适合没装 torch 时验证）
python ask.py "今天 Agent 有什么新进展"   # 问情报官（RAG 问答）
python weekly.py                     # 出本周周报
python eval.py                       # 跑评测集，看检索召回@5
```

## 项目结构

| 文件 | 职责 |
|------|------|
| collector.py | 多源 RSS 采集，失败自动跳过 |
| dedup.py | BGE 语义去重 + bigram 兜底引擎（核心亮点） |
| summarizer.py | v4.8 DeepSeek 摘要 + 自动降级（双重超时防卡死） |
| memory.py | v3 长期兴趣记忆：打分排序 + 权重更新（会学也会忘） |
| report.py | 生成带统计、按兴趣分区、含「今日必读 / 为什么推给你」的日报（v4.5） |
| notifier.py | v4 主动推送：企业微信 / 邮箱，未配置自动跳过；邮件主题自动提炼（v4.5） |
| main.py | 流水线编排 |
| weekly.py | v4.7 周报：读历史日报聚类汇总 |
| rag.py | v5.1 RAG 引擎：BM25 + 向量混合检索(RRF) + 改写 + 重排 + 强制引用 |
| ask.py | v5 问答入口：`python ask.py "问题"` |
| eval.py / eval.json | v5.1 评测集与评测脚本（检索召回@5 / 答案命中率） |
| memory/interests.json | 记忆文件（自动生成，随仓库回仓，跨天持久） |
| reports/ | 每日日报；reports/weekly/ 存放周报 |
| .github/workflows/daily.yml | 每日自动跑流水线 + 推送 |
| .github/workflows/weekly.yml | 每周六自动生成周报 |

## 定时推送（v2.5）

让日报每天自动出刊，不用你手动跑。原理：**GitHub Actions 在云端开一台临时机器 → 拉代码 → 装依赖 → 跑 `python main.py` → 把新日报 + 记忆文件 push 回仓库**。

```bash
# 本地只需做三件事（一次性的）：
# 1) 把本目录单独建一个 GitHub 仓库并 push 上去
# 2) 仓库 Settings → Secrets → Actions 新增以下 Secret（全部可选，缺哪个对应功能跳过）：
#    DEEPSEEK_API_KEY   —— 不填则摘要/问答走降级
#    SMTP_HOST/PORT/USER/PASS/MAIL_TO  —— 不填则不发邮箱
#    WECOM_WEBHOOK      —— 不填则不发企业微信
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

## v4 主动推送（重点）

v1~v3.5 的日报只是"提交回仓库"，得你自己去 GitHub 翻。v4 让它**主动找你**。

支持两个渠道，**配哪个走哪个，都不配就跳过**（不会让流水线崩）：

| 渠道 | 需要的环境变量 | 怎么拿到 |
|---|---|---|
| 企业微信群机器人 | `WECOM_WEBHOOK` | 企业微信群 → 右上角设置 → 群机器人 → 添加 → 复制 Webhook 地址 |
| 邮箱（QQ/163/Gmail 都行） | `SMTP_HOST` `SMTP_PORT` `SMTP_USER` `SMTP_PASS` `MAIL_TO` | 邮箱设置 → 开启 IMAP/SMTP → 拿到**授权码**（不是登录密码）。QQ 邮箱：`smtp.qq.com` / `465` |

本地试：

```bash
export SMTP_HOST=smtp.qq.com
export SMTP_PORT=465
export SMTP_USER=你的QQ邮箱@qq.com
export SMTP_PASS=授权码
export MAIL_TO=收件邮箱
python main.py
```

终端出现 `[推送] 今日日报已送达：邮箱` 就是成功。

云端（GitHub Actions）：仓库 Settings → Secrets → Actions，把上面几个环境变量逐个加成 secret，工作流会自动传给 `python main.py`，每天推送。

## v4.5 日报更聪明 + 邮件翻新

v4.5 让日报不再"一锅端"：

- 顶部新增 **「⭐ 今日必读（Top 3）」**，按兴趣分 + 质量分选出最值得看的 3 条，一眼看到重点；
- 每条新闻下方加 **「🏷 为什么推给你：因为你关注 …」**，推荐理由不再黑箱；
- 邮件主题自动带上 **「N 条情报 · 头条标题」**，不开邮箱也知道今天重不重要。

> 改动只在 `report.py` 与 `notifier.py`，`main.py` 未动，纯代码无密钥。

## v4.7 自动周报

`python weekly.py` 读 `reports/` 下最近 7 天的日报，按「为什么推给你」的标签聚类，输出 `reports/weekly/周报_截至日期.md`，含「按话题分区」+「来源分布统计」。兼容老格式日报（没标签的自动归「其它」）。

- 想自动化：仓库已含 `.github/workflows/weekly.yml`，每周六自动跑并把周报提交回仓库；也可在 Actions 页手动 Run workflow。

## v4.8 AI 摘要（已默认启用）

摘要逻辑在 `summarizer.py`：有 `DEEPSEEK_API_KEY` 时调 DeepSeek 把每条新闻写成通顺人话要点；无 Key 自动降级「规则摘抄」。`daily.yml` 已接入此 Secret，云端默认即用。

- v4.8 加固：给 API 调用加了**双重超时（20 秒）**，防止云端连 DeepSeek 超时卡死整条流水线；并加 `[摘要] 已启用 LLM 摘要` 提示，一眼确认当天是否真走 AI。

## v5 / v5.1 RAG 问答（重点）

v5 起，情报官从「广播员」升级成「能对话的助手」——你问它一句话，它去翻这几天攒下的所有日报，挑最相关的几条，再让 DeepSeek 基于真实资料组织成答案回你，不乱编。

```bash
python ask.py "今天 Agent 有什么新进展"   # 单次提问
python ask.py                              # 进入交互模式，连续问
```

v5.1 升级为正经 RAG 检索系统（**全程可降级，不崩**）：

- **BM25 检索（默认）**：Okapi BM25（IDF + TF + 文档长度归一化），中文按字 + bigram 切分，纯标准库离线可跑；
- **向量检索（可选）**：`USE_VECTOR=1` 时懒加载 BGE 做 embedding，不设就不下载（避免卡死）；
- **混合检索**：BM25 与向量经 **RRF（倒数排名融合）** 合并，不依赖分数量纲；
- **query rewrite**：调 DeepSeek 把口语问题扩写成检索友好的关键词串（无 Key / 失败则跳过）；
- **LLM rerank**：混合检索取候选后调 DeepSeek 精选 Top5（无 Key / 失败则跳过）；
- **强制引用**：资料编号 `[1][2]`，prompt 强制「每条事实后用 [n] 标注来源」；
- **无答案拒答**：资料没有就老实说没有，实测"Agent 有什么新进展"被正确拒答；
- **评测集**：`eval.py` + `eval.json`（12 条问答对），量化 **检索召回@5** 与 **答案命中率**。

```bash
python eval.py                  # 看检索召回@5（纯标准库可离线跑）
export USE_VECTOR=1             # 可选：开启向量混合检索（需 sentence-transformers）
python ask.py "世界模型有什么进展"
```

## 调参笔记

- 去重阈值有两套尺度（在 `dedup.py` 的 `create_dedup_engine()` 里调）：
  - **bigram 引擎**：默认 `0.5`。嫌漏重复就调低（如 0.4），嫌误杀就调高（如 0.6）。
  - **BGE 引擎**：默认 `0.7`（归一化向量余弦，同一事件通常 0.6~0.85）。嫌漏就降到 0.6，嫌误杀就升到 0.8。
  - 判断方法：看日报末尾「被拦下的重复报道」里有没有混进不同的新闻。
- 兴趣排序阈值（在 `report.py` 的 `REC_THRESHOLD`）：默认 `0.3`。调高 → 进「为你推荐」的更严格（只放最相关的）；调低 → 放得更宽。
- 兴趣权重（在 `memory/interests.json`）：单话题命中 ≈ +0.1/天，衰减 ×0.97/天，区间 `[0.2, 3.0]`。想立刻让某话题置顶，手动把它的 weight 改成 3.0。
- RAG 检索（在 `rag.py`）：BM25 参数 `k1=1.5`、`b=0.75`；混合候选数 `CANDIDATE=10`、最终取 `TOP_K=5`；`USE_VECTOR=1` 开启向量混合。
