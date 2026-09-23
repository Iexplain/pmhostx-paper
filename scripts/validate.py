#!/usr/bin/env python3
"""
真相源一致性检查。跑在 write 之后、commit 之前。

存在的理由：判断层会犯错，而且犯的是**看不出来**的那种错——
把 id 按"期刊+年份"的模式推出来而不是从 candidates 复制，
或者给一条记录写上和它物种不符的理由。这两种错都不会让任何脚本报错，
只会让台账变成假账。所以必须显式检查。

退出码：0 全部通过 / 1 有问题
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load(p, default):
    f = DATA / p
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else default


def main():
    led = load("seen.json", {})
    entries = load("entries.json", {}).get("entries", [])
    cands = sorted(DATA.glob("candidates_*.json"))

    problems = []

    # 1. 台账的 in 与 entries.json 必须双向一致
    led_in = {k for k, v in led.items()
              if not k.startswith("_") and (v.get("v") if isinstance(v, dict) else "in") == "in"}
    ent_ids = {e["id"] for e in entries}
    for i in sorted(ent_ids - led_in):
        problems.append(f"entries.json 有 {i}，但台账里没记 in —— 下周它会再被判断一遍")
    for i in sorted(led_in - ent_ids):
        problems.append(f"台账记了 in 的 {i} 不在 entries.json 里 —— 收录了但没进清单")

    # 2. 台账里凡是不在候选池里的键，必须是已有清单的 id（即人工维护的条目）。
    #    这条专抓【编造的 id】：编出来的 id 既不在候选池、也不在清单里。
    pool = set()
    for f in cands:
        for x in json.loads(f.read_text(encoding="utf-8")).get("candidates", []):
            pool.add(x["id"])
    for i in sorted(set(led) - {k for k in led if k.startswith("_")} - pool - ent_ids):
        problems.append(f"台账里的 {i} 既不在任何 candidates 里、也不在 entries.json 里 —— "
                        f"疑似编造的 id")

    # 3. 理由里声称的物种必须在原始记录里真的出现
    SPECIES = {
        "猪": r"porcine|swine|pig|PRRSV|pigs",
        "牛": r"bovine|cattle|rumen|calf|calves",
        "鼠": r"mouse|mice|murine|rat|rats|rodent",
        "植物": r"sorghum|potato|rice|wheat|maize|tomato|cucurbit|Arabidopsis|barley|soybean",
        "昆虫": r"insect|silkworm|Antheraea|bee|bees",
        "鱼": r"fish|shrimp|crab|Portunus|pompano|shellfish",
        "蚊媒": r"mosquito|Culex|tick|Aedes|vector",
        "鸡": r"chicken|poultry|duck|avian",
    }
    allrec = {}
    for f in cands:
        for x in json.loads(f.read_text(encoding="utf-8")).get("candidates", []):
            allrec[x["id"]] = x
    for k, v in led.items():
        if k.startswith("_") or not isinstance(v, dict):
            continue
        why = v.get("why") or ""
        if "非人源" not in why or k not in allrec:
            continue
        rec = allrec[k]
        text = (rec.get("title", "") + " " + rec.get("abstract", ""))
        claimed = [sp for sp, pat in SPECIES.items() if sp in why]
        if claimed and not any(re.search(SPECIES[sp], text, re.I) for sp in claimed):
            problems.append(f"{k} 的理由声称【{'/'.join(claimed)}】，但原始记录的标题与摘要里"
                            f"找不到该物种 —— 理由与记录不符\n      {rec.get('title','')[:100]}")

    # 4. 收录条目不得引 PMID/DOI 之外的东西，且标识符不能为空得离谱
    for e in entries:
        if not e.get("title"):
            problems.append(f"entries.json 编号 {e.get('num')} 无标题")
        if not (e.get("doi") or e.get("pmid")) and not e.get("no_identifier_reason"):
            problems.append(f"entries.json 编号 {e.get('num')} 既无 DOI 也无 PMID，"
                            f"且未声明 no_identifier_reason —— 要么补标识符，要么显式声明为什么没有")

    if problems:
        print(f"检查未通过，{len(problems)} 个问题：\n", file=sys.stderr)
        for p in problems:
            print(f"  ✗ {p}", file=sys.stderr)
        return 1

    n_led = len([k for k in led if not k.startswith("_")])
    from collections import Counter
    c = Counter((v.get("v") if isinstance(v, dict) else "in") for k, v in led.items()
                if not k.startswith("_"))
    print(f"✓ 检查通过：清单 {len(entries)} 条 | 台账 {n_led} 条"
          f"（in {c['in']} / out {c['out']} / skip {c['skip']}）| 候选池 {len(pool)} 个 id")
    return 0


if __name__ == "__main__":
    sys.exit(main())
