#!/usr/bin/env python3
"""
一次性迁移脚本：把现版 litmap.html 解析成 entries.json（页面真相源）。

跑完即可删除或留作参考；日常流程不依赖它。
用法: python3 scripts/migrate_from_html.py <litmap.html> <输出目录>
"""
import json
import re
import sys
from html import unescape
from pathlib import Path

GROUP_NAMES = {
    "1": "方法学核心 · 从宏组学数据中提取宿主信号",
    "2": "标志物与 panel · 你 8 个基因的商业对标",
    "3": "脑脊液 / 中枢感染 · 宿主转录组与 mNGS 判读",
    "4": "建库、去宿主与参考库卫生",
    "5": "背景、综述与研究框架",
    "6": "窗口外，但必须知道",
}


def strip_tags(s: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", s)).strip()


def parse_meta(block: str) -> dict:
    """meta 行是一串 <span>，用 <span class="sep">·</span> 分隔。
    返回 journal / date / authors / doi / doi_url。"""
    spans = re.findall(r"<span(?:\s+class=\"([^\"]*)\")?\s*>(.*?)</span>", block, re.S)
    parts, doi, doi_url = [], None, None
    for cls, inner in spans:
        if cls == "sep":
            continue
        if cls == "doi":
            m = re.search(r'href="([^"]+)"', inner)
            doi_url = m.group(1) if m else None
            doi = strip_tags(inner)
            continue
        parts.append(strip_tags(inner))

    out = {"journal": None, "date": None, "authors": None, "doi": doi, "doi_url": doi_url}
    # 元数据里期刊与日期顺序固定：第一条含 4 位年份即为日期
    date_i = next((i for i, p in enumerate(parts) if re.search(r"\b20\d{2}-\d{2}-\d{2}\b", p)), None)
    if date_i is None and parts:
        out["journal"] = parts[0]
    else:
        out["journal"] = " · ".join(parts[:date_i]) if date_i else None
        out["date"] = parts[date_i]
        rest = parts[date_i + 1:]
        if rest:
            out["authors"] = rest[0]
    return out


def parse(html_path: Path) -> dict:
    html = html_path.read_text(encoding="utf-8")

    # 各 section 的标题与描述
    sections = {}
    for m in re.finditer(
        r'<section class="sec(\d)"[^>]*>(.*?)</section>', html, re.S
    ):
        gid, body = m.group(1), m.group(2)
        h2 = re.search(r"<h2>(.*?)</h2>", body, re.S)
        desc = re.search(r'<p class="secdesc">(.*?)</p>', body, re.S)
        sections[gid] = {
            "name": strip_tags(h2.group(1)) if h2 else GROUP_NAMES.get(gid, ""),
            "desc": strip_tags(desc.group(1)) if desc else "",
        }

    entries = []
    for m in re.finditer(r'<article class="item" data-g="(\d)">(.*?)</article>', html, re.S):
        gid, body = m.group(1), m.group(2)

        num = re.search(r'<span class="num">(.*?)</span>', body)
        oow = re.search(r'<span class="oow">(.*?)</span>', body)
        title_m = re.search(r'<h3 class="ptitle">(.*?)</h3>', body, re.S)
        title_html = title_m.group(1) if title_m else ""
        url_m = re.search(r'href="([^"]+)"', title_html)
        pin = re.search(r'<span class="pin">(.*?)</span>', body)
        meta_m = re.search(r'<div class="meta">(.*?)</div>', body, re.S)
        why_m = re.search(r'<p>(.*?)</p>', body, re.S)

        meta = parse_meta(meta_m.group(1)) if meta_m else {}
        # 窗口外条目把日期放在 oow 徽标里
        if oow and not meta.get("date"):
            meta["date"] = strip_tags(oow.group(1))

        entries.append({
            "group": int(gid),
            "num": int(strip_tags(num.group(1))) if num else None,
            "title": strip_tags(title_html),
            "title_url": url_m.group(1) if url_m else None,
            "must_read": bool(pin),
            "journal": meta.get("journal"),
            "date": meta.get("date"),
            "authors": meta.get("authors"),
            "doi": meta.get("doi"),
            "doi_url": meta.get("doi_url"),
            "why_html": why_m.group(1).strip() if why_m else "",
            "out_of_window": gid == "6",
            "added": "2026-09-23",  # 首批收录日期
        })

    return {"sections": sections, "entries": entries}


def make_id(entry: dict) -> str:
    """稳定的条目 ID：优先 DOI，其次 PMID，否则用标题哈希。
    后续每周新增条目时靠它做幂等判断，所以必须稳定。"""
    if entry.get("doi") and entry["doi"].startswith("10."):
        return re.sub(r"[^a-z0-9]+", "-", entry["doi"].lower()).strip("-")
    if entry.get("pmid"):
        return f"pmid-{entry['pmid']}"
    import hashlib
    h = hashlib.sha1(entry["title"].encode()).hexdigest()[:10]
    return f"title-{h}"


def normalize(entries: list) -> list:
    """修正解析出来的几类不规范字段，使其成为可用的真相源。

    1. 窗口外条目的 doi 字段里可能是 PubMed 链接而非 DOI → 拆成 pmid + doi_url
    2. 无法核实的 DOI → doi=null 且 doi_verified=false，禁止后续渲染成链接
    3. 补稳定 id
    """
    for e in entries:
        doi = e.get("doi") or ""
        url = e.get("doi_url") or ""

        # PubMed 链接被当成了 DOI
        m = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", doi + " " + url)
        if m and not doi.startswith("10."):
            e["pmid"] = m.group(1)
            e["doi"] = None
            e["doi_url"] = f"https://pubmed.ncbi.nlm.nih.gov/{m.group(1)}/"

        e["doi_verified"] = bool(e.get("doi") and e["doi"].startswith("10."))
        if not e["doi_verified"] and not e.get("pmid"):
            e["doi"] = None
            e["doi_url"] = None

        e.setdefault("pmid", None)
        e["id"] = make_id(e)
    return entries


def main():
    src = Path(sys.argv[1])
    outdir = Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)

    data = parse(src)
    data["entries"] = normalize(data["entries"])
    (outdir / "entries.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    n = len(data["entries"])
    by_g = {}
    for e in data["entries"]:
        by_g[e["group"]] = by_g.get(e["group"], 0) + 1
    print(f"解析出 {n} 条")
    for g in sorted(by_g):
        print(f"  组 {g} ({data['sections'].get(str(g), {}).get('name', '?')[:30]}): {by_g[g]} 条")

    ids = [e["id"] for e in data["entries"]]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        print(f"  警告：ID 重复 → {dupes}")
    unv = [e["id"] for e in data["entries"] if not e["doi_verified"] and not e.get("pmid")]
    if unv:
        print(f"  无 DOI 也无 PMID（需人工核对）→ {unv}")


if __name__ == "__main__":
    main()
