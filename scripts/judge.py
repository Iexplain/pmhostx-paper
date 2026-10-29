#!/usr/bin/env python3
"""
第二层：判断。把待判条目分批交给 `claude -p`，收回结构化判断。

判断层**没有任何工具**（--tools ""）：它读不到文件、跑不了命令、改不了数据，
只能看提示词里给的标题与摘要、回一个 JSON。写台账、建条目、提交都由后面的脚本做。
这样「编造标识符」「顺手改了别的文件」这两类错，从结构上就不可能发生。

待判条目 = 本次候选（data/candidates_<date>.json）+ 重审队列（data/rejudge.json）。
每批的回复先过一遍机械检查（序号一一对应、字段齐全、【无摘要】声明属实、不写 panel 基因），
不过就带着错误说明重试，四次都不过则整体失败。

模型**不碰 id**：每条在批内编一个序号 k（1–N），模型只回 k，再由这里映射回 id。
id 是 DOI 转出来的长串，让模型逐字照抄会抄错——2026-10-29 首轮正式运行时，
'10-1016-j-jaci-2026-08-030' 被抄成 '…-08-30'，另一批还编出过 '…-dupe-placeholder'。

可断点续跑：已经判过的条目存在 work/<date>/judged_*.json，再跑只补没判的。

用法:
  python3 scripts/judge.py                     # 今天
  python3 scripts/judge.py --date 2026-11-02
  python3 scripts/judge.py --dry-run           # 只建队列、打印分批，不调用模型

环境变量（测试用）：LIT_LIMIT 只判前 N 条新候选；LIT_REJUDGE_LIMIT 只判前 N 条重审；
LIT_MODEL 指定模型。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
WORK = ROOT / "work"
PROMPT = ROOT / "scripts" / "prompts" / "judge.md"
JUDGING = ROOT / ".claude" / "skills" / "lit-weekly" / "references" / "judging.md"

CHUNK = 20            # 每批条数：20 条摘要约 4–5 万字符，留足判断空间
ATTEMPTS = 4
BACKOFF = 30          # 调用失败（限流、接口报错）后等 30 / 60 / 90 秒再试；内容没过检查则立即重试
TIMEOUT = 1200        # 单批秒数上限
ABS_MAX = 2500        # 重审条目的摘要来自 meta_cache，不截断会比候选文件长很多

NOABS = re.compile(r"无摘要|摘要缺失|凭题录|凭标题")
PANEL_CLAIM = re.compile(r"你的? ?panel ?(里|中|成员|的基因)")


def load(p: Path, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def pool_records() -> dict:
    """历次候选文件里的原始记录，按 id 索引（新的覆盖旧的）。"""
    out = {}
    for f in sorted(DATA.glob("candidates_*.json")):
        for x in load(f, {}).get("candidates", []):
            out[x["id"]] = x
    return out


def build_queue(day: str) -> list[dict]:
    cands = load(DATA / f"candidates_{day}.json", None)
    if cands is None:
        raise SystemExit(f"找不到 data/candidates_{day}.json —— 先跑 fetch.py")
    seen = load(DATA / "seen.json", {})
    entries = {e["id"]: e for e in load(DATA / "entries.json", {}).get("entries", [])}
    cache = load(DATA / "meta_cache.json", {})
    pool = pool_records()

    queue = []
    new = cands.get("candidates", [])
    lim = os.environ.get("LIT_LIMIT")
    for x in new[: int(lim)] if lim else new:
        queue.append({"id": x["id"], "kind": "new", "title": x["title"], "journal": x["journal"],
                      "pubdate": x["pubdate"], "abstract": x.get("abstract") or "",
                      "matched_queries": x.get("queries", [])})

    rq = load(DATA / "rejudge.json", {}).get("queue", [])
    lim = os.environ.get("LIT_REJUDGE_LIMIT")
    for r in rq[: int(lim)] if lim else rq:
        i = r["id"]
        prev = seen.get(i)
        if not isinstance(prev, dict):
            raise SystemExit(f"重审队列里的 {i} 不在台账里")
        rec = pool.get(i)
        e = entries.get(i)
        if rec:
            title, journal, pub, abstract = rec["title"], rec["journal"], rec["pubdate"], rec.get("abstract") or ""
        elif e:
            title, journal, pub = e["title"], e["journal"], e["date"]
            abstract = ""
        else:
            raise SystemExit(f"重审队列里的 {i} 既不在候选池也不在清单里，拿不到记录")
        # 摘要以回填缓存为准：候选文件里的摘要可能是当时的空值
        pmid = str((e or rec or {}).get("pmid") or "")
        abstract = (cache.get(pmid, {}).get("abstract") or abstract)[:ABS_MAX]
        p = {"v": prev.get("v"), "why": prev.get("why")}
        if e:
            p.update(group=e["group"], must_read=e.get("must_read"), why_html=e["why_html"])
        queue.append({"id": i, "kind": "rejudge", "title": title, "journal": journal,
                      "pubdate": pub, "abstract": abstract, "prev": p,
                      "rejudge_reason": r.get("reason", "")})

    ids = [q["id"] for q in queue]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise SystemExit(f"队列里有重复 id（新候选与重审重叠？）：{sorted(dup)[:5]}")
    return queue


def existing_list() -> str:
    E = load(DATA / "entries.json", {}).get("entries", [])
    return "\n".join(f"#{e['num']:02d} [组{e['group']}] {e['title']}（{e['journal']} {e['date']}）"
                     for e in sorted(E, key=lambda x: x["num"] or 0))


def check(items, chunk: list[dict]) -> list[str]:
    """机械检查一批回复。返回问题列表，空 = 通过。"""
    if not isinstance(items, list):
        return ["items 不是数组"]
    errs = []
    n = len(chunk)
    got = [it.get("k") for it in items if isinstance(it, dict)]
    want = list(range(1, n + 1))
    if sorted(x for x in got if isinstance(x, int)) != want or len(got) != n:
        miss = sorted(set(want) - set(got))
        extra = sorted({x for x in got if x not in want}, key=str)
        dup = sorted({x for x in got if got.count(x) > 1}, key=str)
        errs.append(f"k 必须恰好是 1–{n} 各一次：缺 {miss}，多 {extra}，重复 {dup}")
    for it in items:
        if not isinstance(it, dict) or it.get("k") not in want:
            continue
        q, i, v = chunk[it["k"] - 1], f"k={it['k']}", it.get("v")
        why = (it.get("why") or "").strip()
        if v not in ("in", "out", "skip"):
            errs.append(f"{i}: v 必须是 in/out/skip，收到 {v!r}")
        if not why:
            errs.append(f"{i}: why 为空")
        if q["kind"] == "rejudge" and q["prev"]["v"] == "in" and v != "in":
            errs.append(f"{i}: 已收录条目重审只能输出 in（要撤下请人工处理）")
        if v == "in":
            g = it.get("group")
            if not (isinstance(g, int) and 1 <= g <= 7):
                errs.append(f"{i}: group 必须是 1–7 的整数，收到 {g!r}")
            if not isinstance(it.get("must_read"), bool):
                errs.append(f"{i}: must_read 必须是 true/false")
            if not (it.get("why_html") or "").strip():
                errs.append(f"{i}: 收录条目必须写 why_html")
        claim = NOABS.search(re.sub(r"「[^」]*」", "", why))
        if q["abstract"].strip() and claim:
            errs.append(f"{i}: 摘要明明有，理由却声称「{claim.group(0)}」")
        if not q["abstract"].strip() and "【无摘要】" not in why:
            errs.append(f"{i}: 摘要为空，理由里必须写【无摘要】")
        text = why + " " + (it.get("why_html") or "")
        if PANEL_CLAIM.search(text):
            errs.append(f"{i}: 判词写了「{PANEL_CLAIM.search(text).group(0)}」——不写 PMHostX 用了哪些基因")
    return errs


def parse_reply(text: str):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b < 0:
        raise ValueError("回复里没有 JSON 对象")
    return json.loads(t[a:b + 1])


def for_model(chunk: list[dict]) -> list[dict]:
    """交给模型的版本：去掉 id，换成批内序号 k。"""
    return [{"k": n, **{f: v for f, v in q.items() if f != "id"}} for n, q in enumerate(chunk, 1)]


def call_claude(prompt: str) -> tuple[str, float]:
    cmd = ["claude", "-p", "--tools", "", "--output-format", "json", "--no-session-persistence"]
    if os.environ.get("LIT_MODEL"):
        cmd += ["--model", os.environ["LIT_MODEL"]]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=TIMEOUT,
                       cwd="/tmp")   # 不在仓库里起会话：不加载仓库的 CLAUDE.md / 设置
    if r.returncode != 0:
        # 真正的报错（限流等）在 stdout 的 JSON 里；stderr 常常只有一行无关的模型名告警
        detail = r.stdout.strip()
        try:
            detail = str(json.loads(detail).get("result") or detail)
        except (json.JSONDecodeError, AttributeError):
            pass
        raise RuntimeError(f"claude 退出码 {r.returncode}: {(detail or r.stderr.strip())[-300:]}")
    out = json.loads(r.stdout)
    if out.get("is_error"):
        raise RuntimeError(f"claude 返回错误: {str(out.get('result'))[:300]}")
    return out.get("result") or "", float(out.get("total_cost_usd") or 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=str(date.today()))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)   # 进度行实时进日志，不等进程结束

    wd = WORK / a.date
    wd.mkdir(parents=True, exist_ok=True)
    queue = build_queue(a.date)
    (wd / "queue.json").write_text(json.dumps(queue, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    done = set()
    for f in sorted(wd.glob("judged_*.json")):
        done |= {it["id"] for it in load(f, {}).get("items", [])}
    todo = [q for q in queue if q["id"] not in done]
    n_new = sum(1 for q in queue if q["kind"] == "new")
    print(f"待判 {len(queue)} 条（新候选 {n_new} / 重审 {len(queue) - n_new}），"
          f"已判 {len(queue) - len(todo)}，本次要判 {len(todo)}")
    if not todo:
        return 0

    chunks = [todo[i:i + CHUNK] for i in range(0, len(todo), CHUNK)]
    if a.dry_run:
        print(f"分 {len(chunks)} 批，每批 ≤{CHUNK} 条（dry-run，不调用模型）")
        return 0

    tpl = PROMPT.read_text(encoding="utf-8")
    base = (tpl.replace("{{JUDGING}}", JUDGING.read_text(encoding="utf-8"))
               .replace("{{EXISTING}}", existing_list()))
    start = max([int(f.stem.split("_")[1]) for f in wd.glob("judged_*.json")] or [0]) + 1
    total_cost = 0.0
    for k, chunk in enumerate(chunks):
        prompt = base.replace("{{ITEMS}}", json.dumps(for_model(chunk), ensure_ascii=False, indent=1))
        feedback = ""
        for attempt in range(1, ATTEMPTS + 1):
            reply, call_failed = "", False
            try:
                reply, cost = call_claude(prompt + feedback)
                total_cost += cost
                obj = parse_reply(reply)
                errs = check(obj.get("items"), chunk)
            except (RuntimeError, subprocess.TimeoutExpired) as e:
                errs, call_failed = [f"调用失败：{e}"], True
            except (ValueError, json.JSONDecodeError) as e:
                errs = [f"解析失败：{e}"]
            if not errs:
                break
            # 原始回复留档，排查用（work/ 不进 git）
            (wd / f"failed_{start + k:03d}_{attempt}.txt").write_text(
                "\n".join(errs) + "\n\n----- 原始回复 -----\n" + (reply or ""), encoding="utf-8")
            print(f"  第 {k + 1}/{len(chunks)} 批第 {attempt} 次未通过：{errs[0]}"
                  + (f"（另 {len(errs) - 1} 条）" if len(errs) > 1 else ""), file=sys.stderr)
            if attempt == ATTEMPTS:
                continue
            if call_failed:
                # 限流时立刻重试只会再撞一次；内容错误才值得马上重来
                time.sleep(BACKOFF * attempt)
                feedback = ""
            else:
                feedback = ("\n\n# 上一次的输出没有通过检查，请修正后重新输出完整 JSON\n\n"
                            + "\n".join(f"- {e}" for e in errs[:20]))
        else:
            print(f"错误：第 {k + 1} 批 {ATTEMPTS} 次都没通过检查，停止。已完成的批次保留在 {wd.relative_to(ROOT)}/",
                  file=sys.stderr)
            return 1
        # 序号映射回 id：落盘的结果与以前一样以 id 为键，apply_judgments.py 不用改
        items = [{"id": chunk[it["k"] - 1]["id"], **{f: v for f, v in it.items() if f != "k"}}
                 for it in sorted(obj["items"], key=lambda it: it["k"])]
        obj["items"] = items
        out = wd / f"judged_{start + k:03d}.json"
        out.write_text(json.dumps({"items": items, "notes": obj.get("notes") or ""},
                                  ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        c = {v: sum(1 for it in obj["items"] if it["v"] == v) for v in ("in", "out", "skip")}
        print(f"  第 {k + 1}/{len(chunks)} 批 ✓  in {c['in']} / out {c['out']} / skip {c['skip']}")
    print(f"判断完成，本次花费约 ${total_cost:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
