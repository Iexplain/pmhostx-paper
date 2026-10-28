#!/usr/bin/env python3
"""
把判断层的结果写进真相源，并生成周报。全程确定性，不调用模型。

  apply    <date>   judged_*.json → data/seen.json + data/entries.json + weekly/<date>.md
  finalize <date>   全部成功后写 data/last_run.json 与 data/runs.json（决定下次补漏起点）

收录条目的标题、期刊、日期、作者、DOI、PMID **全部从候选记录复制**，判断层只给
id + 判断 + 判词。所以 SKILL 里「绝不编造标识符」这条，现在由代码保证，不靠自觉。

覆盖检查：work/<date>/queue.json 里的每一条都必须恰好有一个判断；
并且队列必须包含本次全部候选（测试时用 LIT_LIMIT 截断的除外）——
「读过了但忘了写回」的条目会被拦下，而不是静默漏掉。
"""
import html
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
WORK = ROOT / "work"
WEEKLY = ROOT / "weekly"

sys.path.insert(0, str(ROOT / "scripts"))
from build_page import GROUP_CHIP, OOW_GROUP          # 组名单一真相源


def load(p: Path, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def dump(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def md_from_html(s: str) -> str:
    s = re.sub(r"</?(strong|b)>", "**", s)
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def entry_from(rec: dict, j: dict, day: str) -> dict:
    """从候选记录建清单条目。只有 group / must_read / why_html 来自判断层。"""
    doi = rec.get("doi")
    ok = bool(doi and doi.startswith("10."))
    pm = f"https://pubmed.ncbi.nlm.nih.gov/{rec['pmid']}/" if rec.get("pmid") else None
    return {
        "id": rec["id"], "group": j["group"], "num": None,
        "title": rec["title"], "title_url": f"https://doi.org/{doi}" if ok else pm,
        "must_read": j["must_read"], "journal": rec["journal"], "date": rec["pubdate"],
        "authors": rec.get("authors") or "", "doi": doi if ok else None,
        "doi_url": f"https://doi.org/{doi}" if ok else pm, "doi_verified": ok,
        "pmid": rec.get("pmid"), "why_html": j["why_html"].strip(),
        "out_of_window": False, "added": day, "pubmed_indexed": True,
    }


def iso_week(until: str) -> str:
    # 周一 00:00 跑的那次负责的是上一周，所以按 until 的前一天定周次
    y, w, _ = (date.fromisoformat(until) - timedelta(days=1)).isocalendar()
    return f"{y}-W{w:02d}"


def apply(day: str) -> int:
    wd = WORK / day
    queue = load(wd / "queue.json", None)
    if queue is None:
        print(f"找不到 {wd.relative_to(ROOT)}/queue.json —— 先跑 judge.py", file=sys.stderr)
        return 1
    cands = load(DATA / f"candidates_{day}.json", {})
    J, notes = {}, []
    for f in sorted(wd.glob("judged_*.json")):
        d = load(f, {})
        for it in d.get("items", []):
            if it["id"] in J:
                print(f"错误：{it['id']} 被判断了两次（{f.name}）", file=sys.stderr)
                return 1
            J[it["id"]] = it
        if (d.get("notes") or "").strip():
            notes.append(d["notes"].strip())

    qids = [q["id"] for q in queue]
    missing = [i for i in qids if i not in J]
    if missing:
        print(f"错误：队列里 {len(missing)} 条没有判断结果（如 {missing[:3]}）—— judge.py 没跑完",
              file=sys.stderr)
        return 1
    cand_ids = {c["id"] for c in cands.get("candidates", [])}
    unq = cand_ids - set(qids)
    if unq and not os.environ.get("LIT_LIMIT"):
        print(f"错误：本次有 {len(unq)} 条候选不在判断队列里 —— 它们会被静默漏掉", file=sys.stderr)
        return 1

    seen = load(DATA / "seen.json", {})
    ent = load(DATA / "entries.json", {})
    E = {e["id"]: e for e in ent["entries"]}
    pool = {}
    for f in sorted(DATA.glob("candidates_*.json")):
        for x in load(f, {}).get("candidates", []):
            pool[x["id"]] = x
    cmap = {c["id"]: c for c in cands.get("candidates", [])}

    rows = {"in": [], "out": [], "skip": [], "re": []}
    for q in queue:
        j, i = J[q["id"]], q["id"]
        if q["kind"] == "new":
            seen[i] = {"v": j["v"], "d": day, "why": j["why"].strip()}
            if j["v"] == "in":
                e = entry_from(cmap[i], j, day)
                ent["entries"].append(e)
                E[i] = e
                rows["in"].append((e, j))
            else:
                rows[j["v"]].append((cmap[i], j))
            continue
        # 重审
        prev = q["prev"]["v"]
        # 重审原因用「」括起来：它是在【引用】队列里的说明，不是这条判断的声称。
        # 不括的话，原因里的「无摘要」会被 validate.py 当成声称（真踩过）
        reason = q.get("rejudge_reason") or "口径变更"
        if prev == "in":
            e = E[i]
            if not e.get("out_of_window"):
                e["group"] = j["group"]
            e["must_read"], e["why_html"] = j["must_read"], j["why_html"].strip()
            seen[i] = {"v": "in", "d": day, "why": f"重审「{reason}」：{j['why'].strip()}"}
        else:
            seen[i] = {"v": j["v"], "d": day, "why": f"重审「{reason}」：{j['why'].strip()}"}
            if j["v"] == "in":
                if i not in pool:
                    print(f"错误：{i} 重审改判收录，但候选池里没有它的原始记录，无法建条目", file=sys.stderr)
                    return 1
                e = entry_from(pool[i], j, day)
                ent["entries"].append(e)
                E[i] = e
        rows["re"].append((q, j))

    dump(DATA / "seen.json", seen)
    dump(DATA / "entries.json", ent)

    # 处理过的条目移出重审队列
    rj = load(DATA / "rejudge.json", {"queue": []})
    done = {q["id"] for q in queue if q["kind"] == "rejudge"}
    rj["queue"] = [r for r in rj.get("queue", []) if r["id"] not in done]
    dump(DATA / "rejudge.json", rj)

    w = cands.get("window", {})
    since, until = w.get("since") or w.get("start"), w.get("until") or day
    summary = {
        "date": day, "since": since, "until": until, "week": iso_week(until),
        "n_queries": cands.get("n_queries"), "hits": cands.get("total_pmids_found"),
        "already_seen": cands.get("already_seen"), "candidates": len(cand_ids),
        "excluded_by_date": len(cands.get("excluded_by_date", [])),
        "excluded_by_policy": len(cands.get("excluded_by_policy", [])),
        "in": len(rows["in"]), "out": len(rows["out"]), "skip": len(rows["skip"]),
        "must_read": sum(1 for e, _ in rows["in"] if e["must_read"]),
        "rejudged": len(rows["re"]),
        "rejudge_to_in": sum(1 for q, j in rows["re"] if q["prev"]["v"] != "in" and j["v"] == "in"),
    }
    (wd / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n",
                                     encoding="utf-8")
    write_weekly(day, summary, rows, notes)
    print(f"已写入：收录 {summary['in']} / 不收 {summary['out']} / 跳过 {summary['skip']}"
          f"｜重审 {summary['rejudged']} 条，其中改判收录 {summary['rejudge_to_in']}")
    return 0


def gname(g: int) -> str:
    return "窗口外" if g == OOW_GROUP else GROUP_CHIP.get(g, f"组 {g}")


def write_weekly(day, s, rows, notes):
    y, w = s["week"].split("-W")
    span = (date.fromisoformat(s["until"]) - date.fromisoformat(s["since"])).days
    title = f"# {day} · {y} 第 {int(w)} 周" + ("（补漏批次）" if span > 9 else "")
    L = [title, "",
         f"窗口 {s['since']} → {s['until']} · {s['n_queries']} 条检索式命中 {s['hits']} 篇 · "
         f"台账已判断 {s['already_seen']} 篇 · 新候选 **{s['candidates']} 条** · 收录 **{s['in']} 条**"
         + (f" · 重审 {s['rejudged']} 条" if s["rejudged"] else ""), "",
         f"另有 {s['excluded_by_date']} 条被日期口径挡下（期号在窗口内、上线更早），"
         f"{s['excluded_by_policy']} 条被来源口径挡下（`data/exclusions.json`）。", ""]
    if span > 9:
        L += [f"本批覆盖 {span + 1} 天：上次成功运行之后漏跑了至少一次，这一批把中间的几周一并补上。", ""]
    early = sum(1 for k in ("in", "out", "skip") for r, _ in rows[k]
                if (r.get("pubdate") or r.get("date") or "9999") < s["since"])
    if early:
        L += [f"候选里有 {early} 条上线日期早于本批起点 {s['since']}：来自新加检索式的补抓，"
              f"或 PubMed 收录晚于上线（索引延迟）。它们此前从未被判断过，所以归在本批。", ""]

    L += ["## 收录", ""]
    if not rows["in"]:
        L += ["本周没有新收录。抓取正常完成，候选逐条读过摘要，均不属本论文范围——理由见下方「未收录」与判断台账。", ""]
    for g in sorted({e["group"] for e, _ in rows["in"]}):
        L += [f"**组 {g} · {gname(g)}**", ""]
        for e, j in [(e, j) for e, j in rows["in"] if e["group"] == g]:
            pin = " · 必读" if e["must_read"] else ""
            L += [f"- **{e['title']}**{pin}（*{e['journal']}* {e['date']}）",
                  f"  {md_from_html(e['why_html'])}",
                  f"  {e['doi_url'] or ''}"]
        L.append("")

    if rows["re"]:
        L += ["## 重审", ""]
        for q, j in rows["re"]:
            p = q["prev"]["v"]
            change = "维持收录，判词按摘要更新" if p == "in" else (
                f"{p} → **{j['v']}**" if j["v"] != p else f"维持 {p}")
            L.append(f"- {q['title']}（{q['journal']} {q['pubdate']}）— {change}：{j['why'].strip()}")
        L.append("")

    L += ["## 未收录", ""]
    rest = [("不收", r, j) for r, j in rows["out"]] + [("跳过", r, j) for r, j in rows["skip"]]
    if not rest:
        L += ["（无）", ""]
    for tag, r, j in rest:
        L.append(f"- {r['title']}（{r['journal']} {r['pubdate']}）— {tag}：{j['why'].strip()}")
    L += ["", "## 值得注意", ""]
    L += ([f"- {n}" for n in notes] if notes else ["（本周判断层没有标注）"])
    WEEKLY.mkdir(exist_ok=True)
    (WEEKLY / f"{day}.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def finalize(day: str) -> int:
    s = load(WORK / day / "summary.json", None)
    if s is None:
        print("找不到 summary.json —— apply 没跑成功，不能写 last_run", file=sys.stderr)
        return 1
    seen = load(DATA / "seen.json", {})
    led = {"in": 0, "out": 0, "skip": 0}
    for k, v in seen.items():
        if not k.startswith("_") and isinstance(v, dict) and v.get("v") in led:
            led[v["v"]] += 1
    dump(DATA / "last_run.json", {
        "last_success": day, "n_candidates": s["candidates"], "n_included": s["in"],
        "_note": "补漏起点 = last_success 的次日。由 scripts/apply_judgments.py finalize 在整轮成功后写入。",
        "window": {"since": s["since"], "until": s["until"]},
        "ledger": led, "excluded_by_date": s["excluded_by_date"],
        "excluded_by_policy": s["excluded_by_policy"], "weekly_report": f"weekly/{day}.md",
    })
    runs = load(DATA / "runs.json", {"runs": []})
    span = (date.fromisoformat(s["until"]) - date.fromisoformat(s["since"])).days
    rec = {"id": day, "run": day, "week": s["week"], "kind": "补漏" if span > 9 else "周更",
           "window": [s["since"], s["until"]],
           "stats": {k: s[k] for k in ("n_queries", "hits", "candidates", "in", "out", "skip",
                                       "must_read", "rejudged", "rejudge_to_in")}}
    runs["runs"] = [r for r in runs["runs"] if r["id"] != day] + [rec]
    runs["runs"].sort(key=lambda r: r["run"], reverse=True)
    dump(DATA / "runs.json", runs)
    print(f"last_run.json → {day}；runs.json 共 {len(runs['runs'])} 批")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("apply", "finalize"):
        print("用法: apply_judgments.py apply|finalize <YYYY-MM-DD>", file=sys.stderr)
        sys.exit(2)
    sys.exit(apply(sys.argv[2]) if sys.argv[1] == "apply" else finalize(sys.argv[2]))
