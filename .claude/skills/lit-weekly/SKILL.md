---
name: lit-weekly
description: 为 PMHostX / PMseq-HostProfiler 论文做每周文献增量收录。跑确定性抓取脚本、判断新增候选的相关性、写入真相源、重建文献地图页面。当用户说"跑一下本周文献""更新文献地图""lit-weekly""这周的文献"时使用。
---

# 每周文献增量

为 PMHostX（脑脊液宏转录组宿主 mRNA 分离与定量）维护一份累积文献地图。
流程分三层，**判断只发生在第二层**。

## 前置：这些是硬约束

1. **绝不编造标识符。** PMID、DOI、发表日期、期刊、作者——全部逐字复制自
   `data/candidates_<date>.json`。你不是在检索，你是在判断已有记录。
   拿不到 DOI 就留空并标 `doi_verified: false`，不要凑一个看起来对的。
2. **抓取失败 ≠ 没有新文献。** 必须看 `fetch.py` 的退出码。
   退出码非 0 时停止整个流程，报告失败原因，**绝不**产出"本周无新增"。
   PubMed 抽风被静默当成"真的没新文献"，是这套流程最危险的失效模式。
3. **日期只认 `pubdate` 字段。** 那是 `pubmed`/`epublish` 的真实上线日期。
   不要用期刊期号日期、不要用 `created`、不要自己推算。
4. **只碰 `data/entries.json`，不手改 `litmap.html`。** 页面是生成的，手改会在下次
   渲染时丢失。
5. **检索范围是 PubMed，这是硬边界。** 预印本（bioRxiv `10.64898/…`、
   Research Square `10.21203/rs.3.rs-…`）和部分 ahead-of-print 没有 PubMed 记录，
   `fetch.py` 永远找不到它们。清单里已有的这类条目（见 `entries.json` 中
   `pubmed_indexed: false` 的）只能人工维护，别指望流程会去更新它们；
   反过来，也别因为"流程没报它"就以为它不存在。

## 流程

### 1. 抓取

```bash
cd <仓库根>
python3 scripts/fetch.py
```

检查退出码。非 0 → 停下报告，不要继续。

脚本自己算窗口：`data/last_run.json` 的 `last_success` 次日 → 今天（补漏），
不早于 `data/notes.json` 的 `window_start`。所以本机 cron 在 WSL 关机期间漏掉的周，
下次会自动补上——这是设计，不要"修"成固定 7 天。

看输出里的两行关键数字：`窗口内 N 条` 和 `被严格日期口径排除 M 条`。
M 通常不为 0（期刊期号在窗口内、但上线更早的论文会被正确剔除），这是正常的。

### 2. 判断

读 `data/candidates_<今天>.json` 的 `candidates` 数组。

**先分诊，再细读。** 候选池在回填时可达数百条，绝大多数标题就能判断。
标题明显不属于 PMHostX 任何一组的（非人源宿主、纯微生物组、与 CSF/宿主反应/panel
基因三者都无关的脓毒症），直接标 `skip` 记进台账，不写 `why_html`、不进正文。
拿不准的进细读，不要用分诊把可能相关的挡掉。

细读的判断标准、分组口径、排除规则见 `references/judging.md` —— **动手前先读它**。

对每条细读的候选产出：

- 收 / 不收（不收的写一句理由，进周报）
- `must_read`: 是否必读（门槛见 references）
- `group`: 1–5 归到哪一组
- `why_html`: "为何相关"那段话

**`why_html` 是这套流程里唯一无法自动化的产物，也是最有价值的部分。**
不要写"该研究探讨了宿主反应与感染的关系"这种废话。要写清楚：它做了什么、
数字是多少、**和 PMHostX 的哪个具体环节对得上**（哪个基因、哪一步、哪个已知隐患）。
可以带 `<strong>` 强调，但它必须承载信息量。

### 3. 写入

把收录的条目追加进 `data/entries.json` 的 `entries` 数组。字段照现有条目的形状：

```json
{
  "id": "从 candidates 的 id 字段原样复制",
  "group": 1,
  "num": null,
  "title": "从 candidates 复制",
  "title_url": "https://doi.org/<doi>  或  https://pubmed.ncbi.nlm.nih.gov/<pmid>/",
  "must_read": false,
  "journal": "从 candidates 复制",
  "date": "从 candidates 的 pubdate 复制",
  "authors": "从 candidates 复制",
  "doi": "从 candidates 复制，没有就 null",
  "doi_url": "有 doi 用 https://doi.org/<doi>，否则用 pubmed 链接",
  "doi_verified": "有 10. 开头的 doi 就 true，否则 false",
  "pmid": "从 candidates 复制",
  "why_html": "你写的",
  "out_of_window": false,
  "added": "今天 YYYY-MM-DD"
}
```

`num` 留 `null`，`build_page.py` 会自动分配下一个全局编号。
**编号只增不改**，所以你正文里引"第 23 条"永远指向同一篇——不要重排已有编号。

同时把**每一条你判断过的候选**都记进 `data/seen.json`（判断台账），不只是收录的：

```json
"10-xxxx": {"v": "in",   "d": "2026-09-28"},
"10-yyyy": {"v": "out",  "d": "2026-09-28", "why": "非人源宿主（玉米）"},
"10-zzzz": {"v": "skip", "d": "2026-09-28", "why": "标题分诊：与 PMHostX 无关"}
```

`v` 三个取值：`in` 已收录 / `out` 判断后不收 / `skip` 标题分诊未过。

**不收的也必须记。** 只记收录的话，被拒的下周会原样再出现一遍；
候选池是几百条量级，那样流程永远收敛不了。`skip` 是可逆的——
以后觉得分诊太粗，把 `skip` 项挑出来重判即可。

### 4. 重建页面

```bash
python3 scripts/build_page.py --queries-md
```

计数、统计、编号全部自动算。跑完核对一下输出里的条数与你写入的是否一致。

### 5. 周报

写 `weekly/<今天>.md`：

```markdown
# 2026-09-28 周

窗口 2026-09-21 → 2026-09-28 · 21 条检索式命中 N 篇 · 去重后新候选 M 条 · 收录 K 条

## 收录

- **组 2 · 必读** — <标题>（<期刊> <日期>）
  <一句话：为何相关>
  <DOI 链接>

## 未收录

- <标题>（<期刊> <日期>）— 不收理由：非人源宿主（玉米）

## 值得注意

<如果这周出现了与已知缺口相关的发现，写在这里。
例如终于出现 FebriDx 相关文献，或某个 panel 基因有了 CSF 基质中的新证据。>
```

"未收录"这一段不是形式主义——它记录了检索的假阳性率，以后调检索式时有用。

### 6. 收尾

更新 `data/last_run.json`：

```json
{"last_success": "2026-09-28", "n_candidates": 12, "n_included": 5}
```

**只有整个流程成功走完才写这个文件。** 它决定下次的补漏起点，
写早了会永久漏掉这段时间的文献。

然后提交：

```bash
git add -A && git commit -m "文献增量 2026-09-28：收录 5 条"
```

推送按仓库约定（默认手动，除非用户明确要求自动推）。

## 常见情况

**候选为 0 条。** 正常，尤其是窗口只有一周时。写周报说明"本周无新增"，
更新 `last_run.json`，提交。这跟"抓取失败"是两件事——见硬约束 2。

**某条候选字段残缺**（无摘要、无作者）。照常判断，缺的字段留空。
`why_html` 可以基于标题与期刊写，但要标注"需核对全文"。

**候选里出现明显不相关的领域**（植物、珊瑚、鱼类、兽医）。不收，
但在"未收录"里记一笔——如果某类假阳性反复出现，说明该调 `data/queries.json` 了。

**发现需要新增检索方向。** 改 `data/queries.json`，追加新检索式（用下一个字母做 key），
然后重跑 `fetch.py`。新检索式会按当前窗口重新检索，历史上漏掉的会补进来。
