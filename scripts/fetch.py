#!/usr/bin/env python3
"""
第一层：确定性抓取。零判断、零编造，只做检索与过滤。

流程：
  1. 定窗口：data/last_run.json 的 last_success（补漏）→ 今天，不早于 window_start
  2. 逐条跑 data/queries.json 里的 21 条检索式（esearch）→ PMID
  3. esummary 取 DOI，与 data/seen.json 去重
  4. 幸存者用 efetch 取 PubMedPubDate，按【严格发表日期】过滤
     —— 只认 PubStatus 为 pubmed / epublish 的日期，不用 esummary 的 pubdate（那是期刊期号日期）
  5. 输出 data/candidates_<today>.json

退出码：
  0  正常（可能有 0 条候选，但抓取本身成功）
  1  任何一条检索式或接口失败 → 非零退出，绝不产出"本周无新增"

用法:
  python3 scripts/fetch.py                 # 抓取
  python3 scripts/fetch.py --since 2026-07-01   # 指定窗口起点（回填用）
  python3 scripts/fetch.py --dry-run       # 只算窗口与命中数，不抓详情
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from hashlib import sha1
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = ROOT / "raw"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
RETMAX = 1000          # 远高于单周命中量；命中数 == 此值即视为截断并报错
SLEEP = 0.4            # 无 API key 时限 3 req/s
RETRIES = 4
LOOKBACK_DAYS = 60     # edat 检索的回溯余量，覆盖 PubMed 的索引延迟


# ---------------------------------------------------------------- HTTP

def _get(url: str, params: dict) -> bytes:
    """带重试的 GET。失败抛异常，绝不静默返回空。"""
    qs = urllib.parse.urlencode(params)
    full = f"{url}?{qs}"
    last = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(full, timeout=60) as r:
                return r.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last = e
            wait = 2 ** attempt
            print(f"    ! 请求失败 ({e})，{wait}s 后重试 {attempt+1}/{RETRIES}", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"请求连续 {RETRIES} 次失败: {full[:120]} → {last}")


def esearch(term: str, mindate: str, maxdate: str) -> tuple[int, list[str]]:
    """按 edat（Entrez 收录日期）检索，不是 pdat。

    为什么不能用 pdat：pdat 是期刊期号日期。一篇 9/20 上线、被分到 10 月期号的论文，
    其 pdat 落在 maxdate 之外，会被直接漏掉。实测 9 天窗口内 pdat 只命中 55 条，
    edat 命中 85 条 —— 44 条是 pdat 找不到的。

    why edat 就够：edat 是记录进入 PubMed 的日期，约等于"何时可被检索到"，
    这正是"本周新增了什么"这个问题该用的键。真正的收录判据在 strict_pubdate 那一层。
    """
    raw = _get(f"{EUTILS}/esearch.fcgi", {
        "db": "pubmed", "term": term, "datetype": "edat",
        "mindate": mindate, "maxdate": maxdate,
        "retmax": RETMAX, "retmode": "json",
    })
    res = json.loads(raw)["esearchresult"]
    return int(res["count"]), res.get("idlist", [])


def esummary(pmids: list[str]) -> dict:
    """分批取摘要级元数据，主要是为了 DOI。"""
    out = {}
    for i in range(0, len(pmids), 200):
        chunk = pmids[i:i + 200]
        raw = _get(f"{EUTILS}/esummary.fcgi", {
            "db": "pubmed", "id": ",".join(chunk), "retmode": "json",
        })
        out.update(json.loads(raw).get("result", {}))
        time.sleep(SLEEP)
    return out


def efetch(pmids: list[str]) -> list[str]:
    """分块取 XML。**返回每块独立的字符串，不要拼成一个文档** ——
    每块都带自己的 XML 声明，拼起来就是多根元素的非法 XML，解析会直接报错。"""
    out = []
    for i in range(0, len(pmids), 100):
        chunk = pmids[i:i + 100]
        out.append(_get(f"{EUTILS}/efetch.fcgi", {
            "db": "pubmed", "id": ",".join(chunk),
            "rettype": "abstract", "retmode": "xml",
        }).decode("utf-8", "replace"))
        time.sleep(SLEEP)
    return out


def iter_articles(chunks: list[str]):
    """逐块解析，产出 PubmedArticle 元素。"""
    for c in chunks:
        try:
            root = ET.fromstring(c)
        except ET.ParseError as e:
            raise RuntimeError(f"efetch 返回的 XML 无法解析: {e}") from e
        yield from root.findall(".//PubmedArticle")


# ---------------------------------------------------------------- 解析

MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def parse_pubdate(el) -> str | None:
    """把 <PubMedPubDate> 解析成 YYYY-MM-DD。Month 可能是 'Sep' 或 '09'，Day 可能缺。"""
    y = el.findtext("Year")
    mo = el.findtext("Month")
    d = el.findtext("Day") or "1"
    if not (y and mo):
        return None
    mo = str(MONTHS.get(mo, mo)).zfill(2)
    return f"{int(y):04d}-{mo}-{int(d):02d}"


def strict_pubdate(article) -> tuple[str | None, str | None]:
    """返回 (严格发表日期, 来源状态)。只认 pubmed / epublish —— 这两个才是真实上线日期。

    绝不用 esummary 的 pubdate：那是期刊期号日期，与上线日期可差数月。
    """
    found = {}
    for p in article.findall(".//PubMedPubDate"):
        st = p.get("PubStatus")
        if st in ("pubmed", "epublish"):
            d = parse_pubdate(p)
            if d:
                found[st] = d
    # pubmed 早于 epublish 时以 pubmed 为准（更接近真实上线）
    for st in ("pubmed", "epublish"):
        if st in found:
            return found[st], st
    return None, None


def clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def make_id(doi: str | None, pmid: str | None, title: str) -> str:
    if doi and doi.startswith("10."):
        return re.sub(r"[^a-z0-9]+", "-", doi.lower()).strip("-")
    if pmid:
        return f"pmid-{pmid}"
    return f"title-{sha1(title.encode()).hexdigest()[:10]}"


def extract_doi(rec: dict) -> str | None:
    for aid in rec.get("articleids", []):
        if aid.get("idtype") == "doi":
            return aid.get("value")
    return None


def exclusion_reason(item: dict, excl: dict) -> str | None:
    """来源排除。命中返回理由，否则 None。

    在【取回之后】过滤而不是往检索式里拼 NOT —— 这样每轮排除了多少条能量出来、
    排除了哪些也留档。塞进检索式就变成隐形的了，永远看不到它拦掉了什么。
    """
    doi = item.get("doi") or ""
    for p in excl.get("exclude_doi_prefix", []):
        if doi.startswith(p):
            return f"来源排除：DOI 前缀 {p}"
    j = item.get("journal") or ""
    for p in excl.get("exclude_journal_prefix", []):
        if j.startswith(p):
            return f"来源排除：刊名以 {p} 开头"
    return None


# ---------------------------------------------------------------- 主流程

def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="窗口起点 YYYY-MM-DD，覆盖自动补漏")
    ap.add_argument("--dry-run", action="store_true", help="只打印窗口与命中数")
    args = ap.parse_args()

    notes = load_json(DATA / "notes.json", {})
    window_start = notes.get("window_start", "2026-07-01")
    queries = load_json(DATA / "queries.json", {}).get("queries", [])
    # 判断台账：凡是被判断过的候选（收录 / 不收 / 标题分诊掉）都在这里。
    # 只记收录的话，被拒的下周会原样再来一遍，流程永远不收敛。
    seen = {k: v for k, v in load_json(DATA / "seen.json", {}).items()
            if not k.startswith("_")}
    excl = load_json(DATA / "exclusions.json", {})
    last_run = load_json(DATA / "last_run.json", {})

    if not queries:
        print("错误：data/queries.json 里没有检索式", file=sys.stderr)
        return 1

    today = date.today()

    # 窗口起点：显式指定 > 上次成功运行（补漏）> window_start
    if args.since:
        since = datetime.strptime(args.since, "%Y-%m-%d").date()
        why = "命令行指定"
    elif last_run.get("last_success"):
        since = datetime.strptime(last_run["last_success"], "%Y-%m-%d").date() + timedelta(days=1)
        why = f"上次成功运行 {last_run['last_success']} 的次日（补漏）"
    else:
        since = datetime.strptime(window_start, "%Y-%m-%d").date()
        why = "首次运行，从窗口起点开始"

    win_start = datetime.strptime(window_start, "%Y-%m-%d").date()
    since = max(since, win_start)

    # 检索键是 edat（收录日期），要往前留出索引延迟的回溯余量：
    # 一篇 9/20 上线的论文可能到 10/5 才被索引，那时它的"上线日期"已早于当次 since。
    # 靠回溯余量把它捞回来，再由 seen.json 决定是否已处理过。
    search_from = since - timedelta(days=LOOKBACK_DAYS)
    mindate, maxdate = search_from.strftime("%Y/%m/%d"), today.strftime("%Y/%m/%d")

    print(f"收录窗口: {win_start} → {today}")
    print(f"检索区间: {search_from} → {today}  (edat，含 {LOOKBACK_DAYS} 天回溯余量；{why})")
    print(f"检索式: {len(queries)} 条 | 已判断: {len(seen)} 条", end="")
    rules = [f"DOI {p}*" for p in excl.get("exclude_doi_prefix", [])] + \
            [f"刊名 {p}*" for p in excl.get("exclude_journal_prefix", [])]
    print(f" | 来源排除: {'、'.join(rules)}" if rules else "")
    print()

    # --- 1. 逐条检索 ---
    hits: dict[str, set] = {}      # pmid -> 命中的检索式 key
    truncated = []
    for q in queries:
        try:
            count, ids = esearch(q["term"], mindate, maxdate)
        except Exception as e:
            print(f"检索式 {q['key']} 失败: {e}", file=sys.stderr)
            return 1
        if count >= RETMAX:
            truncated.append((q["key"], count))
        for p in ids:
            hits.setdefault(p, set()).add(q["key"])
        print(f"  {q['key']:22} 命中 {count:>5}  累计去重 {len(hits)}")
        time.sleep(SLEEP)

    if truncated:
        print("\n错误：以下检索式命中数达到 retmax 上限，结果被截断，无法保证完整性：",
              file=sys.stderr)
        for k, c in truncated:
            print(f"  {k}: {c}", file=sys.stderr)
        return 1

    if not hits:
        print("\n窗口内 21 条检索式均无命中。")
    print(f"\n合计命中 {len(hits)} 个 PMID")

    if args.dry_run:
        return 0

    # --- 2. esummary 取 DOI，做去重 ---
    print("\n取元数据并去重…")
    try:
        summ = esummary(sorted(hits))
    except Exception as e:
        print(f"esummary 失败: {e}", file=sys.stderr)
        return 1

    surviving = {}   # pmid -> (id, doi, title, journal, queries)
    already = {"in": 0, "out": 0, "skip": 0}
    for pmid in sorted(hits):
        rec = summ.get(pmid)
        if not rec or "error" in rec:
            print(f"  警告：PMID {pmid} 无 esummary 记录，跳过", file=sys.stderr)
            continue
        title = clean(rec.get("title"))
        doi = extract_doi(rec)
        eid = make_id(doi, pmid, title)
        if eid in seen:
            # 台账里的值：新格式是 {"v": ...}，旧格式是日期字符串（按已收录算）
            v = seen[eid]
            v = v.get("v", "in") if isinstance(v, dict) else "in"
            already[v if v in already else "in"] += 1
            continue
        surviving[pmid] = {
            "id": eid, "doi": doi, "title": title,
            "journal": clean(rec.get("fulljournalname") or rec.get("source")),
            "queries": sorted(hits[pmid]),
        }
    n_skipped = sum(already.values())
    print(f"  去重后新候选 {len(surviving)} 条（台账跳过 {n_skipped} 条："
          f"已收录 {already['in']} / 判断不收 {already['out']} / 标题分诊 {already['skip']}）")

    if not surviving:
        write_report(win_start, today, [], hits, already, len(queries),
                     policy_excluded=[])
        return 0

    # --- 3. efetch 取严格发表日期 ---
    print(f"\n取 {len(surviving)} 条的精确发表日期…")
    try:
        chunks = efetch(sorted(surviving))
    except Exception as e:
        print(f"efetch 失败: {e}", file=sys.stderr)
        return 1

    RAW.mkdir(exist_ok=True)
    (RAW / f"efetch_{today}.xml").write_text("\n".join(chunks), encoding="utf-8")

    candidates, out_of_window, policy_excluded = [], [], []
    try:
        for art in iter_articles(chunks):
            pmid = art.findtext(".//PMID")
            if pmid not in surviving:
                continue
            pubdate, status = strict_pubdate(art)
            meta = surviving[pmid]
            abstract = clean(" ".join(
                (t.text or "") for t in art.findall(".//Abstract/AbstractText")))
            item = {
                **meta,
                "pmid": pmid,
                "pubdate": pubdate,
                "pubdate_source": status,
                "abstract": abstract[:2000],
                "authors": clean(authors_str(art)),
            }
            # 收录判据用【整个窗口】而不是本次 since —— 去重由 seen.json 负责。
            # 这样延迟索引的论文、以及上一版按 pdat 检索时漏掉的论文都能自动补回来。
            reason = exclusion_reason(item, excl)
            if reason:
                policy_excluded.append({**item, "reason": reason})
            elif pubdate is None:
                out_of_window.append({**item, "reason": "无 pubmed/epublish 日期，无法判定"})
            elif date.fromisoformat(pubdate) < win_start:
                out_of_window.append({**item, "reason": f"上线日期 {pubdate} 早于窗口起点 {win_start}"})
            elif date.fromisoformat(pubdate) > today:
                out_of_window.append({**item, "reason": f"上线日期 {pubdate} 晚于今天"})
            else:
                candidates.append(item)
    except RuntimeError as e:
        print(f"解析 efetch 结果失败: {e}", file=sys.stderr)
        return 1

    candidates.sort(key=lambda x: (x["pubdate"], x["journal"]))
    print(f"  窗口内 {len(candidates)} 条 | 被严格日期口径排除 {len(out_of_window)} 条"
          f" | 被来源口径排除 {len(policy_excluded)} 条")

    write_report(win_start, today, candidates, hits, already, len(queries),
                 out_of_window, policy_excluded)
    return 0


def authors_str(art) -> str:
    names = []
    for a in art.findall(".//AuthorList/Author")[:3]:
        ln, fn = a.findtext("LastName"), a.findtext("Initials")
        if ln:
            names.append(f"{ln} {fn}" if fn else ln)
    s = ", ".join(names)
    total = len(art.findall(".//AuthorList/Author"))
    if total > 3:
        s += " et al."
    return s


def write_report(win_start, today, candidates, hits, already, n_queries,
                 out_of_window=None, policy_excluded=None):
    DATA.mkdir(exist_ok=True)
    out = DATA / f"candidates_{today}.json"
    out.write_text(json.dumps({
        "window": {"start": str(win_start), "until": str(today)},
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "n_queries": n_queries,
        "total_pmids_found": len(hits),
        "ledger_skipped": already,
        "already_seen": sum(already.values()),
        "candidates": candidates,
        "excluded_by_date": out_of_window or [],
        "excluded_by_policy": policy_excluded or [],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n→ {out.relative_to(ROOT)}")
    print(f"  窗口内新候选 {len(candidates)} 条，待判断。")


if __name__ == "__main__":
    sys.exit(main())
