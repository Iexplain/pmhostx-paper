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
    vague = []      # 写了"非人源"但没点名具体物种的记录（marine/soil 这类）——不报错，只统计

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
    #
    #    词表按**论文里实际怎么称呼**收录，不是按学名收。踩过的坑：
    #    只写 bovine|cattle 时，一篇通篇 "dairy cows / Holstein cows" 的
    #    牛源论文查不到任何命中，校验会误报理由造假。同类的还有
    #    flounder（牙鲆）、chicks（雏鸡）——都用俗名，不用学名。
    SPECIES = {
        "猪": r"porcine|swine|\bpigs?\b|PRRSV|hog|boar",
        "牛": r"bovine|cattle|rumen|calves?\b|\bcows?\b|dairy|heifer|Holstein",
        "鼠": r"mouse|mice|murine|rats?\b|rodent",
        "植物": r"sorghum|potato|rice|wheat|maize|tomato|cucurbit|Arabidopsis|barley|soybean|fern|Azolla|cyanobacter",
        "昆虫": r"insect|silkworm|Antheraea|bees?\b",
        "鱼": r"\bfish\b|shrimp|crab|Portunus|pompano|shellfish|flounder|Paralichthys|salmon|trout|tilapia|zebrafish",
        "蚊媒": r"mosquito|Culex|tick|Aedes|vector",
        "鸡": r"chicken|poultry|ducks?\b|avian|chicks?\b|hen",
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
        # 理由侧的物种识别要同时认中文键名和英文写法：历史台账的约定是
        # "非人源宿主（mice）"这种英文括号。只认中文键名的话，这类记录
        # claimed 为空、整条比对被静默跳过 —— 等于校验从来没跑过。
        claimed = [sp for sp, pat in SPECIES.items()
                   if sp in why or re.search(pat, why, re.I)]
        if not claimed:
            vague.append(k)          # 只说"marine/soil"这类，不点名物种；不算错，但要可见
        elif not any(re.search(SPECIES[sp], text, re.I) for sp in claimed):
            problems.append(f"{k} 的理由声称【{'/'.join(claimed)}】，但原始记录的标题与摘要里"
                            f"找不到该物种 —— 理由与记录不符\n      {rec.get('title','')[:100]}")

    # 4. 收录条目不得引 PMID/DOI 之外的东西，且标识符不能为空得离谱
    for e in entries:
        if not e.get("title"):
            problems.append(f"entries.json 编号 {e.get('num')} 无标题")
        if not (e.get("doi") or e.get("pmid")) and not e.get("no_identifier_reason"):
            problems.append(f"entries.json 编号 {e.get('num')} 既无 DOI 也无 PMID，"
                            f"且未声明 no_identifier_reason —— 要么补标识符，要么显式声明为什么没有")

    # 5. 分组的三个层面必须对齐：entries 用到的组号、sections 的定义、
    #    模板里的配色 class。少任何一层都不会报错 —— build_page 的
    #    GROUP_CSS.get(g,'sec1') 会静默回退到组 1 的配色，页面看着正常、颜色是错的。
    sys.path.insert(0, str(ROOT / "scripts"))
    from build_page import GROUP_CSS, OOW_GROUP          # 单一真相源，不重复定义
    sections = load("entries.json", {}).get("sections", {})
    tpl = (ROOT / "templates" / "litmap.template.html").read_text(encoding="utf-8")

    used_groups = {e["group"] for e in entries}
    for g in sorted(used_groups):
        if str(g) not in sections:
            problems.append(f"组 {g} 有 {sum(1 for e in entries if e['group'] == g)} 条条目，"
                            f"但 entries.json 的 sections 里没有 \"{g}\" 的定义 —— 页面上会显示「组 {g}」")
    for g in sorted(GROUP_CSS):
        if g not in used_groups:
            continue
        if f".sec{g} .well" not in tpl:
            problems.append(f"组 {g} 在用，但模板里没有 .sec{g} 的配色规则 —— "
                            f"页面会静默回退到组 1 的颜色")

    # 窗口外必须且只能是 OOW_GROUP；内容组不得占用该组号
    for e in entries:
        if e.get("out_of_window") and e["group"] != OOW_GROUP:
            problems.append(f"编号 {e.get('num')} 标了 out_of_window，组号却是 {e['group']}，"
                            f"应为 {OOW_GROUP}")
        if not e.get("out_of_window") and e["group"] == OOW_GROUP:
            problems.append(f"编号 {e.get('num')} 没标 out_of_window，却用了窗口外组号 "
                            f"{OOW_GROUP} —— 它不会出现在筛选按钮里")

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
    if vague:
        print(f"  · 物种校验实际比对 {sum(1 for k, v in led.items() if isinstance(v, dict) and '非人源' in (v.get('why') or '')) - len(vague)} 条"
              f"；另有 {len(vague)} 条只写「非人源」未点名物种，跳过比对（marine/soil 之类，不算错）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
