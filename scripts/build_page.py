#!/usr/bin/env python3
"""
第三层：确定性渲染。从 data/ 生成整个站点 site/：

  site/index.html        最新一期（默认打开）
  site/w/<批次>.html     每一期一个固定链接
  site/map.html          累积地图（全部收录，按主题分组）
  site/litmap.html       旧地址，跳转到 map.html
  site/assets/ fonts/    从 templates/site/ 原样拷入

每一页都是完整的静态 HTML：不开 JS 也能读，往期能被搜索引擎收录。
JS（templates/site/app.js）只负责筛选、周次跳转和过期提示。

页面里的计数、统计、编号全部自动算——不手工维护，所以不会再出现
「组里 9 条却写着 8 条」这类错误。编号只增不改：新条目拿下一个全局编号，
正文里引「第 23 条」永远指向同一篇。

site/ 每次整体重建，不要手改。

用法:
  python3 scripts/build_page.py                # 生成 site/
  python3 scripts/build_page.py --queries-md   # 顺便重新生成 queries.generated.md
"""
import argparse
import json
import re
import shutil
import sys
from datetime import date, datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ASSETS = ROOT / "templates" / "site"
OUT = ROOT / "site"
REPO = "https://github.com/Iexplain/pmhostx-paper"

# 内容组是 1–7，窗口外固定排在最后。组号在 apply_judgments.py、validate.py 里也要用，
# 以这里为单一真相源。加内容组时窗口外顺延（2026-09-24 加组 6、2026-10-28 加组 7 都这么做）。
OOW_GROUP = 8
GROUP_CHIP = {1: "宿主信号提取", 2: "标志物与 panel", 3: "中枢感染", 4: "建库与去宿主",
              5: "综述与背景", 6: "诊断建模", 7: "病原检测与 mNGS", 8: "窗口外"}

# 标本：PMHostX 覆盖全血 / BALF / CSF 三种，文献按标题 + 摘要自动识别，可多选。
# CSF 要排除细胞因子名（G-CSF / GM-CSF / CSF-1），台账里真踩过。
SPECIMENS = [
    ("blood", "血液", "全血、血浆、血清，以及脓毒症 / 血流感染研究",
     r"whole blood|\bblood\b|PAXgene|plasma|serum|\bPBMCs?\b|bacter(a)?emia|sepsis|septic"),
    ("resp", "下呼吸道", "BALF、气管吸出物、痰、肺炎",
     r"BALF|bronchoalveolar|lavage|lower respiratory|\bLRTIs?\b|tracheal aspirate|pneumonia|sputum|lower airway"),
    ("csf", "脑脊液", "CSF、脑膜炎、脑炎",
     r"cerebrospinal|(?<![-A-Za-z])CSF(?![-0-9A-Za-z])|meningit|encephalit|central nervous system infection|\bCNS infection"),
]
SP_NAME = {k: n for k, n, _, _ in SPECIMENS}

PUBTYPE = {
    "Review": "综述", "Systematic Review": "系统综述", "Meta-Analysis": "Meta 分析",
    "Preprint": "预印本", "Case Reports": "病例报告", "Clinical Trial": "临床试验",
    "Randomized Controlled Trial": "随机对照试验", "Multicenter Study": "多中心",
    "Observational Study": "观察性研究", "Comparative Study": "比较研究",
    "Evaluation Study": "评估研究", "Validation Study": "验证研究",
}

ABS_LABELS = (r"Background|Introduction|Objectives?|Aims?|Purpose|Overview|Rationale|"
              r"Materials and methods|Methods?|Design|Setting|Participants|"
              r"Results?|Findings|Conclusions?|Interpretation|Significance|Importance|Summary")
ABS_INLINE = re.compile(rf"(?:^|(?<=[.!?] ))({ABS_LABELS})\s*:\s*")

FAVICON = ("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
           "<text y='.9em' font-size='90'>🧬</text></svg>")


def load(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def assign_nums(entries: list) -> None:
    """给没有 num 的条目分配下一个全局编号（只增不改）。"""
    used = {e["num"] for e in entries if e.get("num")}
    nxt = max(used) + 1 if used else 1
    for e in entries:
        if not e.get("num"):
            while nxt in used:
                nxt += 1
            e["num"] = nxt
            used.add(nxt)
            nxt += 1


# ---------------------------------------------------------------- 摘要

def _sentences(text: str, lo=170, hi=320, from_end=False) -> str:
    """按句号截取，不切半句。from_end=True 时从末尾往前取。"""
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z(\[])", text)
    if from_end:
        sents = sents[::-1]
    acc = ""
    for s in sents:
        nxt = (s + " " + acc if from_end else acc + " " + s).strip()
        if len(nxt) > hi and acc:
            break
        acc = nxt
        if len(acc) >= lo:
            break
    if len(acc) > hi:
        acc = acc[:hi].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return acc


def abstract_view(meta: dict) -> tuple[list, dict | None]:
    """分段 + 预览。有结论段取结论；没有就取末段——摘要开头多是背景铺垫，发现在最后。"""
    secs = [dict(s) for s in meta.get("abstract_sections", []) if s.get("text")]
    if not secs:
        return [], None
    for s in secs:
        # 粘连写法「…syndrome.ConclusionsThe findings…」：补成内嵌标签再拆
        s["text"] = re.sub(r"([.!?])(Conclusions?|Results?|Methods?|Background)(?=[A-Z][a-z])",
                           r"\1 \2: ", s["text"])
        lab = (s.get("label") or "").strip().rstrip(":")
        s["label"] = "" if lab.lower() == "unlabelled" else lab.capitalize()
    if len(secs) == 1 and not secs[0]["label"]:
        parts = ABS_INLINE.split(secs[0]["text"])
        if len(parts) >= 3:
            secs = ([{"label": "", "text": parts[0].strip()}] if parts[0].strip() else []) + \
                   [{"label": parts[i].capitalize(), "text": parts[i + 1].strip()}
                    for i in range(1, len(parts) - 1, 2)]
    concl = next((s for s in secs if re.match(r"conclu|interpret", s["label"], re.I)), None)
    if concl:
        return secs, {"kind": "原文结论", "text": _sentences(concl["text"], lo=200, hi=340)}
    full = " ".join(s["text"] for s in secs)
    return secs, {"kind": "摘要末段", "text": _sentences(full, from_end=True)}


# ---------------------------------------------------------------- 卡片

def enrich(e: dict, cache: dict, rejudge: set) -> dict:
    """给条目算出页面要用的派生字段（不写回 entries.json）。"""
    m = cache.get(str(e.get("pmid") or ""))
    secs, preview = abstract_view(m or {})
    tags = [PUBTYPE[t] for t in (m or {}).get("pubtypes", []) if t in PUBTYPE]
    j = e.get("journal") or ""
    if re.search(r"预印本|bioRxiv|medRxiv|Research Square", j) and "预印本" not in tags:
        tags.append("预印本")
    if "会议摘要" in j:
        tags.append("会议摘要")
    text = e["title"] + " " + ((m or {}).get("abstract") or "")
    if not e.get("pmid"):
        abs_state = "no-pubmed"
    elif m is None:
        abs_state = "uncached"          # 有 PMID 但缓存里没有：不声称「无摘要」，只是不展示
    elif not secs:
        abs_state = "empty"
    else:
        abs_state = "ok"
    return {**e, "_sp": [k for k, _, _, p in SPECIMENS if re.search(p, text, re.I)],
            "_tags": tags, "_abs": secs, "_pv": preview, "_abs_state": abs_state,
            "_pmcid": (m or {}).get("pmcid"), "_recheck": e["id"] in rejudge,
            "_journal": re.sub(r"\s+\d+\(\d+\):\d+$", "", j)}


def card(e: dict, mode: str) -> str:
    num = f"{e['num']:02d}"
    if mode == "map":
        gut = f'<span class="cb-d">#{num}</span><span class="cb-y">{escape(e["date"] or "")}</span>'
    else:
        d = e["date"] or ""
        gut = f'<span class="cb-d">{escape(d[5:])}</span><span class="cb-y">{escape(d[:4])}</span>'
    if e.get("must_read"):
        gut += '<span class="cb-flag">▲ 必读</span>'
    gut += f'<span class="cb-g"><i></i>{escape(GROUP_CHIP.get(e["group"], str(e["group"])))}</span>'

    url = e.get("title_url") or e.get("doi_url")
    title = escape(e["title"])
    if url:
        title = (f'<a href="{escape(url)}" target="_blank" rel="noopener">{title}'
                 f'<span class="ext" aria-hidden="true">↗</span></a>')

    meta = [f'<span class="j">{escape(e["_journal"])}</span>']
    if mode == "map" and e.get("out_of_window"):
        meta.append("<span>窗口外</span>")
    if e.get("authors"):
        meta.append(f"<span>{escape(e['authors'])}</span>")
    if e.get("doi_verified") and e.get("doi"):
        meta.append(f'<a href="https://doi.org/{escape(e["doi"])}" target="_blank" rel="noopener">DOI</a>')
    if e.get("pmid"):
        meta.append(f'<a href="https://pubmed.ncbi.nlm.nih.gov/{escape(str(e["pmid"]))}/" '
                    f'target="_blank" rel="noopener">PubMed</a>')
    if e.get("_pmcid"):
        meta.append(f'<a href="https://pmc.ncbi.nlm.nih.gov/articles/{escape(e["_pmcid"])}/" '
                    f'target="_blank" rel="noopener">PMC 全文</a>')
    if not (e.get("doi") or e.get("pmid")):
        meta.append("<span>未核到 DOI，需人工核对</span>")
    if mode != "map":
        meta.append(f"<span>编号 {num}</span>")

    tags = [f'<span class="tag sp">{SP_NAME[k]}</span>' for k in e["_sp"]]
    tags += [f'<span class="tag">{escape(t)}</span>' for t in e["_tags"]]
    if e["_recheck"]:
        tags.append('<span class="tag warn" title="判词写于摘要缺失或口径变更之前，已排进重审队列">判词待重审</span>')
    tags_html = f'<div class="cb-tags">{"".join(tags)}</div>' if tags else ""

    st = e["_abs_state"]
    if st == "ok":
        paras = []
        for s in e["_abs"]:
            lab = f"<b>{escape(s['label'])}</b>" if s["label"] else ""
            paras.append(f"<p>{lab}{escape(s['text'])}</p>")
        n = len(e["_abs"])
        more = f"（{n} 段）" if n > 1 else ""
        abs_html = (f'<div class="abs"><span class="abs-k">{e["_pv"]["kind"]}</span>'
                    f'<p class="abs-pv">{escape(e["_pv"]["text"])}</p>'
                    f'<details><summary>完整摘要{more}</summary>'
                    f'<div class="abs-full">{"".join(paras)}</div></details></div>')
    elif st == "no-pubmed":
        abs_html = ('<div class="abs"><span class="abs-none">无摘要：这条记录不在 PubMed 里'
                    '（预印本或会议摘要），需打开原文核对。</span></div>')
    elif st == "empty":
        abs_html = '<div class="abs"><span class="abs-none">PubMed 记录里没有摘要，需打开原文核对。</span></div>'
    else:
        abs_html = ""

    must = " must-row" if e.get("must_read") else ""
    return f'''<article class="cb g{e["group"]}{must}" data-g="{e["group"]}" data-sp="{" ".join(e["_sp"])}" data-must="{1 if e.get("must_read") else 0}">
  <div class="cb-gut">{gut}</div>
  <div class="cb-body">
    <h3>{title}</h3>
    <p class="why">{e["why_html"]}</p>
    <div class="meta">{"".join(meta)}</div>
    {tags_html}
    {abs_html}
  </div>
</article>'''


def tools(pool: list, sortnote: str, map_href: str | None) -> str:
    """筛选区。初始计数在这里算好写进 HTML，交互时由 app.js 重算。"""
    gs = sorted({e["group"] for e in pool})
    theme = [f'<button class="opt" data-g="0" aria-pressed="true">全部<small>{len(pool)}</small></button>']
    theme += [f'<button class="opt g{g}" data-g="{g}" aria-pressed="false"><i></i>{escape(GROUP_CHIP[g])}'
              f'<small>{sum(1 for e in pool if e["group"] == g)}</small></button>' for g in gs]
    spec = [f'<button class="opt" data-sp="" aria-pressed="true">全部<small>{len(pool)}</small></button>']
    for k, n, tip, _ in SPECIMENS:
        c = sum(1 for e in pool if k in e["_sp"])
        spec.append(f'<button class="opt" data-sp="{k}" aria-pressed="false" title="{escape(tip)}">'
                    f'{n}<small>{c}</small></button>')
    c = sum(1 for e in pool if not e["_sp"])
    spec.append(f'<button class="opt" data-sp="none" aria-pressed="false" '
                f'title="摘要里没有指明标本：方法、工具、综述居多">未限定<small>{c}</small></button>')
    mapq = (f'<a class="btn pri" id="mapq" data-base="{map_href}" href="{map_href}" hidden></a>'
            if map_href else "")
    return f'''<div class="tools" id="tools">
  <div class="facet" role="group" aria-label="按主题筛选"><span class="fl">主题</span><div class="opts">{"".join(theme)}</div></div>
  <div class="facet" role="group" aria-label="按标本筛选"><span class="fl">标本</span><div class="opts">{"".join(spec)}</div></div>
  <div class="row2">
    <button class="toggle" id="must" aria-pressed="false">只看必读</button>
    <input class="search" id="q" type="search" placeholder="搜索标题、判词、期刊、作者、摘要…" aria-label="搜索">
    <button class="clear" id="clear" data-clear hidden>清除筛选</button>
    <span class="sortnote">{sortnote}</span>
  </div>
</div>
<p class="nomatch" id="nomatch" hidden>这一页没有符合筛选条件的文献。{mapq}<button class="btn" data-clear>清除筛选</button></p>'''


# ---------------------------------------------------------------- 批次

def run_name(r: dict) -> str:
    if r.get("kind") == "回填":
        return r.get("label") or r["id"]
    y, w = r["week"].split("-W")
    return f"{y} 第 {int(w)} 周"


def run_span(r: dict) -> int:
    a, b = r["window"]
    return (date.fromisoformat(b) - date.fromisoformat(a)).days + 1


def topbar(P: str, runs: list, cur: dict | None, counts: dict) -> str:
    opts = []
    if cur is None:
        opts.append(f'<option value="" selected>累积地图 · 全部 {sum(counts.values())} 条</option>')
    for r in runs:
        a, b = r["window"]
        txt = (f"{r.get('label', r['id'])} · 回填 · {counts.get(r['id'], 0)} 条" if r.get("kind") == "回填"
               else f"{run_name(r)} · {a[5:]}–{b[5:]} · {counts.get(r['id'], 0)} 条")
        sel = " selected" if r is cur else ""
        opts.append(f'<option value="{P}w/{r["id"]}.html"{sel}>{escape(txt)}</option>')

    def step(target, label, sym):
        if target is None:
            return f'<span class="step" aria-disabled="true" aria-label="{label}">{sym}</span>'
        return f'<a class="step" href="{P}w/{target["id"]}.html" aria-label="{label}">{sym}</a>'
    i = runs.index(cur) if cur is not None else None
    older = runs[i + 1] if i is not None and i + 1 < len(runs) else None
    newer = runs[i - 1] if i is not None and i > 0 else None
    on_map = cur is None
    return f'''<header class="top"><div class="top-in">
  <a class="brand" href="{P}index.html"><b>PMHostX 文献周报</b><span>宏转录组宿主 mRNA · 每周更新</span></a>
  <div class="stepper">
    {step(older, "较早一期", "◂")}
    <label class="pick"><select id="pick" aria-label="选择周次">{"".join(opts)}</select></label>
    {step(newer, "较新一期", "▸")}
  </div>
  <nav class="views" aria-label="视图">
    <a href="{P}index.html"{"" if on_map else ' aria-current="page"'}>周报</a>
    <a href="{P}map.html"{' aria-current="page"' if on_map else ""}>累积地图</a>
  </nav>
</div></header>'''


def rail(P: str, runs: list, cur: dict | None, counts: dict, musts: dict, total: int, n_groups: int) -> str:
    if cur is not None:
        st = cur.get("stats", {})
        n, nm = counts.get(cur["id"], 0), musts.get(cur["id"], 0)
        a, b = cur["window"]
        rows = [("收录", n, False), ("其中必读", f"▲ {nm}" if nm else 0, bool(nm)),
                ("新候选（读过摘要）", st.get("candidates", "—"), False),
                ("检索命中", st.get("hits", "—"), False), ("检索式", st.get("n_queries", "—"), False),
                ("窗口", f"{a[5:]} → {b[5:]}", False)]
        if st.get("rejudged"):
            rows.insert(3, ("重审旧判断", st["rejudged"], False))
        head = "本期结果" if cur is runs[0] else "该期结果"
    else:
        rows = [("累计收录", total, False), ("必读", f"▲ {sum(musts.values())}", True),
                ("批次", len(runs), False), ("主题分组", n_groups, False)]
        head = "累积"
    rep = "".join(f'<tr class="{"hi" if hi else ""}"><td>{k}</td><td>{escape(str(v))}</td></tr>'
                  for k, v, hi in rows)
    tl, month = [], None
    for r in runs:
        m = f"{r['run'][:4]} 年 {int(r['run'][5:7])} 月"
        if m != month:
            tl.append(f'<li class="m">{m}</li>')
            month = m
        a, b = r["window"]
        tl.append(f'<li class="{"on" if r is cur else ""}"><a href="{P}w/{r["id"]}.html">{escape(run_name(r))}'
                  f'<small>{a[5:]} → {b[5:]} · {counts.get(r["id"], 0)} 条</small></a></li>')
    tl.append(f'<li class="{"on" if cur is None else ""}"><a href="{P}map.html">累积地图'
              f'<small>全部 {total} 条</small></a></li>')
    return f'''<aside class="rail" aria-label="概览与往期">
  <div><h2>{head}</h2><table class="report"><tbody>{rep}</tbody></table></div>
  <div><h2>往期</h2><ol class="tl">{"".join(tl)}</ol></div>
</aside>'''


def page(P: str, title: str, desc: str, top: str, main: str, side: str, last: str, generated: str) -> str:
    return f'''<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{escape(title)}</title>
<meta name="description" content="{escape(desc)}">
<link rel="icon" href="{FAVICON}">
<link rel="preload" href="{P}fonts/plex-sans-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{P}assets/style.css">
<body>
{top}
<div class="stale" id="stale" data-last="{last}" hidden><div></div></div>
<div class="shell">
<main class="main">
{main}
</main>
{side}
</div>
<footer class="foot">
  <p>数据来源 PubMed（NCBI E-utilities）· 发表日期取 PubMed 记录的 pubmed / epublish 上线日 · 每周一 00:00（北京时间）自动更新</p>
  <p>页面生成于 {generated} · 最近一次成功运行 {last} · 检索式、判断台账与源码：<a href="{REPO}">github.com/Iexplain/pmhostx-paper</a></p>
</footer>
<script src="{P}assets/app.js"></script>
</body>
</html>
'''


# ---------------------------------------------------------------- 组装

def week_main(P: str, r: dict, runs: list, ents: list) -> str:
    latest = r is runs[0]
    eyebrow = "本周更新" if latest else f"往期 · {run_name(r)}"
    kind = ""
    if r.get("kind") == "回填":
        kind = f'<span class="kind" title="覆盖整个窗口而非一周">回填批次 · {escape(r.get("label", ""))}</span>'
    elif r.get("kind") == "补漏":
        kind = f'<span class="kind" title="上次成功运行之后漏跑过">补漏批次 · 覆盖 {run_span(r)} 天</span>'
    note = r.get("note") or ""
    st = r.get("stats", {})
    if not note and r.get("kind") == "补漏":
        note = "上次成功运行之后漏跑了至少一次，这一批把中间几周一并补上。"
    if st.get("rejudged"):
        note += f"另按新口径重审了 {st['rejudged']} 条旧判断，其中改判收录 {st.get('rejudge_to_in', 0)} 条。"
    a, b = r["window"]
    head = f'''<header class="wk">
  <p class="eyebrow"><b>{escape(eyebrow)}</b>{kind}</p>
  <h1 class="range">{a}<i>→</i>{b}</h1>
  {f'<p class="wk-note">{escape(note)}</p>' if note else ""}
</header>'''
    if not ents:
        i = runs.index(r)
        prev = runs[i + 1] if i + 1 < len(runs) else None
        detail = (f"抓取正常完成：{st.get('n_queries', '—')} 条检索式命中 {st.get('hits', '—')} 篇，"
                  f"去重后 {st.get('candidates', 0)} 条新候选。逐条读过摘要后都不属本论文范围"
                  f"（不收 {st.get('out', 0)} 条、跳过 {st.get('skip', 0)} 条），每条的理由记在判断台账里。")
        btn = (f'<a class="btn pri" href="{P}w/{prev["id"]}.html">看上一期（{escape(run_name(prev))}）</a>'
               if prev else "")
        return head + f'''<div class="empty">
  <span class="zero">0</span>
  <h2>这一期没有新收录</h2>
  <p>{detail}</p>
  <p class="aside">这和「没跑成」是两回事：没跑成的那周不会生成页面，顶部会出现数据过期提示。</p>
  <div class="btns">{btn}<a class="btn" href="{P}map.html">看累积地图</a></div>
</div>'''
    ents = sorted(ents, key=lambda e: (e["date"] or "", -e["num"]), reverse=True)
    return (head + tools(ents, "按发表日期，新 → 旧", f"{P}map.html")
            + '\n<div class="list">\n' + "\n".join(card(e, "week") for e in ents) + "\n</div>")


def map_main(ents: list, sections: dict, notes: dict, last: str) -> str:
    win = notes.get("window_start", "2026-07-01")
    lede = ("面向 <b>PMHostX</b>（宏转录组宿主 mRNA 分离定量，并以宿主表达建模判别感染；"
            "全血 / BALF / CSF 三种标本）。全部收录按「用在论文哪一节」分组：写某一节时从这里按主题查；"
            "想看某一周新来了什么，去周报。")
    head = f'''<header class="wk">
  <p class="eyebrow"><b>累积地图</b><span class="kind">编号只增不改</span></p>
  <h1 class="range">{win}<i>→</i>{last}</h1>
  <p class="lede">{lede}</p>
</header>'''
    secs = []
    for g in sorted({e["group"] for e in ents}):
        ge = sorted([e for e in ents if e["group"] == g], key=lambda e: e["num"])
        s = sections.get(str(g), {})
        secs.append(f'''<section class="sec g{g}" data-g="{g}">
  <div class="sec-h"><i></i><h2>{escape(s.get("name", GROUP_CHIP[g]))}</h2><small>{len(ge)} 条</small></div>
  {f'<p class="sec-d">{escape(s["desc"])}</p>' if s.get("desc") else ""}
  <div class="list">
{chr(10).join(card(e, "map") for e in ge)}
  </div>
</section>''')
    note_items = "".join(f"<li>{n}</li>" for n in notes.get("notes", []))
    notes_html = (f'<div class="notes"><h2>检索说明与已知缺口</h2><ul>{note_items}</ul></div>'
                  if note_items else "")
    return head + tools(ents, "组内按编号", None) + "\n" + "\n".join(secs) + "\n" + notes_html


def build() -> int:
    data = load(DATA / "entries.json") or {"sections": {}, "entries": []}
    runs = load(DATA / "runs.json", {}).get("runs", [])
    notes = load(DATA / "notes.json", {})
    cache = load(DATA / "meta_cache.json", None)
    last = load(DATA / "last_run.json", {}).get("last_success", "")
    rejudge = {r["id"] for r in load(DATA / "rejudge.json", {}).get("queue", [])}

    entries = data["entries"]
    assign_nums(entries)
    if cache is None:
        print("警告：data/meta_cache.json 不存在，页面不展示摘要——先跑 scripts/enrich.py", file=sys.stderr)
        cache = {}
    ents = [enrich(e, cache, rejudge) for e in entries]
    uncached = [e["num"] for e in ents if e["_abs_state"] == "uncached"]
    if uncached and cache:
        print(f"警告：{len(uncached)} 条有 PMID 但缓存里没有摘要（编号 {uncached[:8]}）——跑一下 enrich.py",
              file=sys.stderr)

    runs = sorted(runs, key=lambda r: r["run"], reverse=True)
    ids = {r["id"] for r in runs}
    orphan = sorted({e["added"] for e in entries if e.get("added") not in ids})
    if orphan:
        print(f"错误：这些收录批次在 data/runs.json 里没有记录，条目不会出现在任何周页上：{orphan}",
              file=sys.stderr)
        return 1
    counts = {r["id"]: sum(1 for e in ents if e.get("added") == r["id"]) for r in runs}
    musts = {r["id"]: sum(1 for e in ents if e.get("added") == r["id"] and e.get("must_read")) for r in runs}
    sections = data.get("sections", {})
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    n_groups = len({e["group"] for e in ents if not e.get("out_of_window")})

    # site/ 整体重建：往期页随 runs.json 增删，不留残页
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "w").mkdir(parents=True)
    shutil.copytree(ASSETS / "fonts", OUT / "fonts")
    (OUT / "assets").mkdir()
    for f in ("style.css", "app.js"):
        shutil.copy2(ASSETS / f, OUT / "assets" / f)
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    def week_page(P, r):
        mine = [e for e in ents if e.get("added") == r["id"]]
        title = ("PMHostX 文献周报" if P == "" else f"{run_name(r)} · PMHostX 文献周报")
        desc = f"PMHostX 文献周报 {run_name(r)}（{r['window'][0]} 至 {r['window'][1]}）：收录 {len(mine)} 条。"
        return page(P, title, desc, topbar(P, runs, r, counts), week_main(P, r, runs, mine),
                    rail(P, runs, r, counts, musts, len(ents), n_groups), last, generated)

    for r in runs:
        (OUT / "w" / f"{r['id']}.html").write_text(week_page("../", r), encoding="utf-8")
    if runs:
        (OUT / "index.html").write_text(week_page("", runs[0]), encoding="utf-8")
    (OUT / "map.html").write_text(page(
        "", "累积地图 · PMHostX 文献周报",
        "PMHostX 论文的累积文献地图：宏转录组宿主 mRNA 定量与感染判别建模，按主题归类，每条标注与方法的哪个环节对得上。",
        topbar("", runs, None, counts), map_main(ents, sections, notes, last),
        rail("", runs, None, counts, musts, len(ents), n_groups), last, generated), encoding="utf-8")
    # 旧地址：换成多页结构之前，文献地图挂在 /litmap.html
    (OUT / "litmap.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>PMHostX 文献周报</title>'
        '<meta http-equiv="refresh" content="0; url=map.html">'
        '<p>文献地图已移到 <a href="map.html">map.html</a>。</p>\n', encoding="utf-8")

    print(f"→ site/  首页 = {run_name(runs[0]) if runs else '（无批次）'}｜周页 {len(runs)} 个｜累积地图 {len(ents)} 条")
    for g in sorted({e["group"] for e in ents}):
        print(f"    组 {g} {GROUP_CHIP[g]}: {sum(1 for e in ents if e['group'] == g)} 条")

    # 回写分配好的编号
    data["entries"] = entries
    (DATA / "entries.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


def write_queries_md():
    """从 queries.json 生成 queries.generated.md。"""
    queries = load(DATA / "queries.json", {}).get("queries", [])
    lines = ["## 检索式全文", "",
             "以下由 `data/queries.json` 生成，勿手工编辑。", "", "```text"]
    for q in queries:
        lines.append(f"{q['key']}\n{q['term']}\n")
    lines.append("```")
    (ROOT / "queries.generated.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"→ queries.generated.md ({len(queries)} 条检索式)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries-md", action="store_true", help="同时重新生成检索式清单")
    a = ap.parse_args()
    rc = build()
    if a.queries_md:
        write_queries_md()
    sys.exit(rc)
