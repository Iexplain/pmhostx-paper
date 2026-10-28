#!/usr/bin/env python3
"""
元数据回填：给清单里的每一条补上摘要、文献类型、PMC 全文号。

为什么单独一个缓存文件而不是写进 entries.json：
  entries.json 是判断层手写的记录（why_html、group、must_read 都是人的判断）。
  往里塞抓取字段会混掉"哪些是人判的、哪些是机器抓的"这条界线，
  而且每次重抓都会改动作业区、让 diff 变得没法看。
  缓存按 PMID 存，跨周复用、可随时重建、与 entries.json 互不干扰。

为什么要回填：
  2026-10 实测，86 条收录里有 43 条拿不到摘要（全部集中在 09-23 首批，
  且全部不在候选池里，是早期人工维护的条目）。它们都有 PMID，
  efetch 能取回——只是当时没写进任何文件。缺摘要的卡片等于让读者
  只能凭标题判断值不值得读，而这正是这套流程已经封死的做法。

用法:
  python3 scripts/enrich.py            # 只补缓存里缺的
  python3 scripts/enrich.py --refresh  # 强制重抓全部
  python3 scripts/enrich.py --check    # 只报告覆盖率，不写文件
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = DATA / "meta_cache.json"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
BATCH = 100
SLEEP = 0.4
RETRIES = 4


def _get(url: str, params: dict) -> bytes:
    qs = urllib.parse.urlencode(params)
    full = f"{url}?{qs}"
    last = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(full, timeout=90) as r:
                return r.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last = e
            wait = 2 ** attempt
            print(f"    ! 请求失败 ({e})，{wait}s 后重试 {attempt+1}/{RETRIES}", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"请求连续 {RETRIES} 次失败: {full[:120]} → {last}")


def clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def parse_article(a) -> dict:
    """从 PubmedArticle 元素抽出卡片要用的字段。"""
    # 摘要必须用 itertext()，不能用 .text —— PubMed 的结构化摘要里到处是
    # <i>（学名）、<sup>（如 CD45RB<sup>low</sup>）这类行内标记，.text 只取
    # 第一个子标签【之前】的文字，之后的全在 .tail 里被丢掉。fetch.py 踩过这个坑
    # （134 条摘要断在开括号处），这里不重复。
    sections = []
    for t in a.findall(".//Abstract/AbstractText"):
        sections.append({
            "label": clean(t.get("Label") or t.get("NlmCategory") or ""),
            "text": clean("".join(t.itertext())),
        })
    sections = [s for s in sections if s["text"]]
    full = clean(" ".join(s["text"] for s in sections))

    pmcid = next((x.text for x in a.findall(".//ArticleId") if x.get("IdType") == "pmc"), None)
    # 'Journal Article' 是默认值、没有区分度，去掉；剩下的才是"综述""预印本"这类有用标签
    pubtypes = [x.text for x in a.findall(".//PublicationType")
                if x.text and x.text != "Journal Article"]

    return {
        "abstract": full,
        "abstract_sections": sections,
        "pubtypes": pubtypes,
        "pmcid": pmcid,
    }


def load_json(p: Path, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def target_pmids() -> list[str]:
    """清单 + 候选池里出现过的全部 PMID。"""
    out = []
    for e in load_json(DATA / "entries.json", {}).get("entries", []):
        if e.get("pmid"):
            out.append(str(e["pmid"]))
    for f in sorted(DATA.glob("candidates_*.json")):
        for x in load_json(f, {}).get("candidates", []):
            if x.get("pmid"):
                out.append(str(x["pmid"]))
    return sorted(set(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="忽略缓存，全部重抓")
    ap.add_argument("--check", action="store_true", help="只报告覆盖率")
    args = ap.parse_args()

    cache = {} if args.refresh else load_json(CACHE, {})
    pmids = target_pmids()
    todo = [p for p in pmids if p not in cache]

    entries = load_json(DATA / "entries.json", {}).get("entries", [])
    need = [str(e["pmid"]) for e in entries if e.get("pmid")]

    if args.check:
        have = [p for p in need if cache.get(p, {}).get("abstract")]
        print(f"清单 {len(entries)} 条 | 有 PMID {len(need)} 条 | 缓存里有摘要 {len(have)} 条")
        print(f"缓存文件 {CACHE.relative_to(ROOT)}：{len(cache)} 个 PMID")
        return 0

    print(f"缓存已有 {len(cache)} 个 PMID，待抓 {len(todo)} 个")
    if not todo:
        print("无需抓取。")
        return 0

    ok = bad = 0
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        try:
            raw = _get(f"{EUTILS}/efetch.fcgi", {
                "db": "pubmed", "id": ",".join(chunk),
                "rettype": "abstract", "retmode": "xml",
            }).decode("utf-8", "replace")
        except Exception as e:
            # 抓取失败绝不能静默当成"这些记录没有摘要"——那正是 validate.py
            # 要抓的假账。直接非零退出。
            print(f"efetch 失败: {e}", file=sys.stderr)
            return 1
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as e:
            print(f"efetch 返回的 XML 无法解析: {e}", file=sys.stderr)
            return 1
        for a in root.findall(".//PubmedArticle"):
            pmid = a.findtext(".//PMID")
            if not pmid:
                continue
            cache[pmid] = parse_article(a)
            ok += 1
        got = {a.findtext(".//PMID") for a in root.findall(".//PubmedArticle")}
        bad += len([p for p in chunk if p not in got])
        print(f"  抓取 {min(i+BATCH, len(todo))}/{len(todo)}")
        time.sleep(SLEEP)

    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                     encoding="utf-8")
    print(f"\n→ {CACHE.relative_to(ROOT)}  ({len(cache)} 个 PMID，本次取得 {ok}，未返回 {bad})")

    have = [p for p in need if cache.get(p, {}).get("abstract")]
    print(f"  清单摘要覆盖 {len(have)}/{len(need)}"
          + (f"（{len(need)-len(have)} 条无 PMID，无法回填）" if len(have) < len(need) else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
