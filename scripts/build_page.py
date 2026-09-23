#!/usr/bin/env python3
"""
第三层：确定性渲染。从 data/entries.json 生成 litmap.html。

页面里的计数、统计、编号全部自动算 —— 不手工维护，所以不会再出现
"组里 9 条却写着 8 条"这类错误。

编号策略：条目的 num 一旦分配就不再变动，新条目拿下一个全局编号。
组内按 num 升序排列，所以你正文里引"第 23 条"永远指向同一篇论文。
想看本周新增，看页面底部的更新记录。

用法:
  python3 scripts/build_page.py            # 渲染 litmap.html
  python3 scripts/build_page.py --queries-md   # 顺便重新生成 queries.md
"""
import argparse
import json
import re
from datetime import date, datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TEMPLATES = ROOT / "templates"

GROUP_CSS = {1: "sec1", 2: "sec2", 3: "sec3", 4: "sec4", 5: "sec5", 6: "sec6"}

# 组序号 → 筛选按钮短名
GROUP_CHIP = {1: "方法学", 2: "标志物", 3: "临床", 4: "建库/去宿主", 5: "背景"}


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


def render_entry(e: dict) -> str:
    g = e["group"]
    bit = []

    # 标题行
    title = escape(e["title"])
    if e.get("title_url"):
        title = f'<a href="{escape(e["title_url"])}">{title}</a>'
    marker = (f'<span class="oow">{escape(e["date"])}</span>' if e.get("out_of_window")
              else f'<span class="num">{e["num"]:02d}</span>')
    pin = '<span class="pin">必读</span>' if e.get("must_read") else ""
    bit.append(f'''    <div class="tline">
      {marker}
      <h3 class="ptitle">{title}</h3>
      {pin}
    </div>''')

    # 元数据行
    parts = [escape(e["journal"] or "")]
    if not e.get("out_of_window"):
        parts.append(escape(e.get("date") or ""))
    if e.get("authors"):
        parts.append(escape(e["authors"]))
    if e.get("doi_verified") and e.get("doi") and e.get("doi_url"):
        parts.append(f'<span class="doi"><a href="{escape(e["doi_url"])}">{escape(e["doi"])}</a></span>')
    elif e.get("pmid"):
        parts.append(f'<span class="doi"><a href="{escape(e["doi_url"])}">PMID {e["pmid"]}</a></span>')
    else:
        parts.append('<span class="unverified">未核到 DOI — 需人工核对</span>')

    sep = '<span class="sep">·</span>'
    meta = sep.join(f"<span>{p}</span>" if not p.startswith("<span") else p for p in parts)
    bit.append(f'    <div class="meta">{meta}</div>')

    # 为何相关
    bit.append(f'''    <div class="why"><span class="lbl">为何相关</span><p>{e["why_html"]}</p></div>''')

    return f'''  <article class="item" data-g="{g}" data-id="{escape(e["id"])}">
{chr(10).join(bit)}
  </article>'''


def build() -> str:
    data = load(DATA / "entries.json") or {"sections": {}, "entries": []}
    notes = load(DATA / "notes.json", {})
    queries = load(DATA / "queries.json", {}).get("queries", [])
    entries = data["entries"]
    sections = data.get("sections", {})

    assign_nums(entries)
    in_window = [e for e in entries if not e.get("out_of_window")]
    out_window = [e for e in entries if e.get("out_of_window")]

    # 窗口：起点固定，终点取最晚上线日期
    win_start = notes.get("window_start", "2026-07-01")
    win_end = max((e["date"] for e in in_window if e.get("date")), default=win_start)
    window = f"{win_start} → {win_end}"

    # --- 统计 ---
    added_dates = sorted({e.get("added") for e in entries if e.get("added")})
    stats = [
        (len(in_window), "窗口内"),
        (len(out_window), "窗口外必读"),
        (len(added_dates), "批收录"),
        (len(queries), "检索式"),
    ]
    stats_html = "\n".join(
        f'    <div class="stat"><span class="n">{n}</span><span class="k">{k}</span></div>'
        for n, k in stats)

    # --- 筛选按钮 ---
    chips = []
    for g in sorted({e["group"] for e in entries if not e.get("out_of_window")}):
        label = GROUP_CHIP.get(g, sections.get(str(g), {}).get("name", f"组 {g}"))
        chips.append(f'    <button class="chip" data-g="{g}" aria-pressed="false">'
                     f'<span class="dot"></span>{escape(label)}</button>')
    if out_window:
        chips.append('    <button class="chip" data-g="6" aria-pressed="false">'
                     '<span class="dot"></span>窗口外</button>')
    chips_html = "\n".join(chips)

    # --- 分组正文 ---
    blocks = []
    for g in sorted({e["group"] for e in entries}):
        ge = sorted([e for e in entries if e["group"] == g], key=lambda x: x["num"])
        sec = sections.get(str(g), {})
        name = sec.get("name", f"组 {g}")
        desc = sec.get("desc", "")
        count = len(ge)
        desc_html = f'\n  <p class="secdesc">{escape(desc)}</p>' if desc else ""
        body = "\n\n".join(render_entry(e) for e in ge)
        blocks.append(f'''<section class="{GROUP_CSS.get(g, 'sec1')}" data-g="{g}">
  <div class="sechead">
    <span class="well"></span>
    <h2>{escape(name)}</h2>
    <span class="count">{count} 条</span>
  </div>{desc_html}

{body}
</section>''')
    sections_html = "\n\n".join(blocks)

    # --- 更新记录（只在有过一次以上收录时显示）---
    recent_html = ""
    if len(added_dates) > 1:
        rows = []
        for d in sorted(added_dates, reverse=True):
            batch = sorted([e for e in entries if e.get("added") == d], key=lambda x: x["num"])
            for e in batch[:12]:
                gname = GROUP_CHIP.get(e["group"], "窗口外" if e.get("out_of_window") else "—")
                url = e.get("title_url") or e.get("doi_url")
                t = escape(e["title"])
                if url:
                    t = f'<a href="{escape(url)}">{t}</a>'
                rows.append(f'      <li><span class="d">{d}</span>'
                            f'<span class="g">{escape(gname)}</span><span>{t}</span></li>')
            if len(batch) > 12:
                rows.append(f'      <li><span class="d"></span><span class="g"></span>'
                            f'<span>…本批另 {len(batch)-12} 条</span></li>')
        recent_html = f'''
<div class="recent">
  <h2>收录记录</h2>
  <ol>
{chr(10).join(rows)}
  </ol>
</div>
'''

    # --- 说明 ---
    notes_html = "\n".join(f"    <li>{n}</li>" for n in notes.get("notes", []))

    eyebrow = f"文献短名单 · 检索窗口 {win_start} → {win_end}"
    lede = (f'面向 <b>{escape(notes.get("project", "PMHostX"))}</b>'
            f'（脑脊液宏转录组宿主 mRNA 分离与定量）。每条按"与项目的哪一部分相关"归组，'
            f'并注明可直接使用的点。日期均取自 PubMed <code>pubmed</code>/<code>epublish</code> '
            f'或 Europe PMC <code>firstPublicationDate</code> 字段实测值。')

    tpl = (TEMPLATES / "litmap.template.html").read_text(encoding="utf-8")
    html = (tpl
            .replace("{{EYEBROW}}", eyebrow)
            .replace("{{LEDE}}", lede)
            .replace("{{STATS}}", stats_html)
            .replace("{{CHIPS}}", chips_html)
            .replace("{{SECTIONS}}", sections_html)
            .replace("{{RECENT}}", recent_html)
            .replace("{{NOTES}}", notes_html)
            .replace("{{GENERATED_AT}}", datetime.now().strftime("%Y-%m-%d %H:%M"))
            .replace("{{WINDOW}}", window)
            .replace("{{TOTAL}}", f"{len(in_window) + len(out_window)} 条"))

    out = ROOT / "litmap.html"
    out.write_text(html, encoding="utf-8")
    print(f"→ litmap.html  ({len(html)/1024:.0f} KB)")
    print(f"  窗口内 {len(in_window)} 条 + 窗口外 {len(out_window)} 条 = {len(entries)} 条")
    for g in sorted({e["group"] for e in entries}):
        n = len([e for e in entries if e["group"] == g])
        print(f"    组 {g}: {n} 条")
    if len(added_dates) > 1:
        print(f"  收录批次: {', '.join(added_dates)}")

    # 回写分配好的编号
    data["entries"] = entries
    (DATA / "entries.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return html


def write_queries_md():
    """从 queries.json 生成 queries.md 的检索式全文部分。"""
    queries = load(DATA / "queries.json", {}).get("queries", [])
    lines = ["## 检索式全文", "",
             "以下由 `data/queries.json` 生成，勿手工编辑。", "", "```text"]
    for q in queries:
        lines.append(f"{q['key']}\n{q['term']}\n")
    lines.append("```")
    out = ROOT / "queries.generated.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"→ queries.generated.md ({len(queries)} 条检索式)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries-md", action="store_true", help="同时重新生成检索式清单")
    a = ap.parse_args()
    build()
    if a.queries_md:
        write_queries_md()
