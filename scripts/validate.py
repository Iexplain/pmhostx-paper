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
    # 物种校验跳过比对的三类原因。分开计数，否则报告里那句"只写非人源未点名物种"
    # 会把"摘要缺失""记录里查不到"也算进去 —— 统计行本身说了假话。
    vague = {"未点名物种": 0, "无摘要": 0, "记录里查不到": 0}

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

    # 3. 理由里声称的物种不得与原始记录矛盾
    #
    #    判据的方向很重要，这里返工过三次才定下来。一开始写的是
    #    「理由声称的物种必须在记录里【出现】，否则算造假」，结果一路误报：
    #    词表收了 bovine|cattle 却漏了 dairy cows / Holstein cows；
    #    收了 \bfish\b 却漏了 Finfish；收了 sorghum|rice 却漏了
    #    plant / grape / legume / rhizosphere / mycorrhiza。每次都把**正确**
    #    的理由判成造假——因为「论文里实际怎么称呼」是个开不完的清单。
    #
    #    真正的教训是：【查不到】只说明拿不出证据，不等于【证据矛盾】。
    #    所以现在只抓矛盾——理由声称 A 类，而记录明确命中另一类、
    #    且完全不命中 A。查不到任何一类则归入 vague（可见、可统计、不拦）。
    #
    #    "人"这一类的存在理由最硬：「理由说非人源、实际是人类研究」是最严重的
    #    错法（2026-09-24 真踩过：一条写「非人源宿主（mouse）」的记录，
    #    摘要原文是 "macrophages from people with type 1 diabetes"）。
    SPECIES = {
        # 键名必须是"人类"而不是"人"：理由侧的匹配用的是子串（`sp in why`），
        # 而每条非人源理由里都写着"非**人**源宿主"，单字"人"会把它们全部
        # 误判成"声称人类宿主"——一开就报了 39 条假问题。
        "人类": r"human|patient|people|person|volunteer|donor|clinical sample|cohort|informed consent",
        "猪": r"porcine|swine|\bpigs?\b|PRRSV|hog|boar",
        "牛": r"bovine|cattle|rumen|calves?\b|\bcows?\b|dairy|heifer|Holstein",
        "鼠": r"mouse|mice|murine|rats?\b|rodent",
        "植物": r"plant|root|leaf|leaves|foliar|grass|tree|pine|conifer|grape|vine|coffee|legume|"
                r"rhizosphere|mycorrhiz|crop|seedling|floral|pollen|turfgrass|endophyt|forest|"
                r"sorghum|potato|rice|wheat|maize|tomato|cucurbit|Arabidopsis|barley|soybean|fern|Azolla|cyanobacter",
        "昆虫": r"insect|silkworm|Antheraea|bees?\b|termite|Coptotermes|locust|Ceracris|bed bug|Cimex|"
                r"beetle|moth|butterfly|Drosophila|wasp|aphid|mayfly|Ephemera",
        "鱼": r"\bfish\b|finfish|fishmeal|shellfish|shrimp|crab|Portunus|pompano|flounder|Paralichthys|"
              r"salmon|trout|tilapia|zebrafish|eel|Anguilla|carps?\b|Oncorhynchus|Larimichthys|croaker|"
              r"taimen|Hucho|loach|Triplophysa|crayfish|Cherax|prawn|lobster|mussel|oyster|scallop",
        "蚊媒": r"mosquito|Culex|tick|Aedes|vector",
        "鸡": r"chicken|poultry|ducks?\b|avian|chicks?\b|hen|broiler",
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
        abstract = rec.get("abstract") or ""
        text = rec.get("title", "") + " " + abstract
        # 理由侧的物种识别要同时认中文键名和英文写法：历史台账的约定是
        # "非人源宿主（mice）"这种英文括号。只认中文键名的话，这类记录
        # claimed 为空、整条比对被静默跳过 —— 等于校验从来没跑过。
        # 匹配前先把否定词和【引用】剥掉，两处都是"理由在谈论物种"而不是
        # "理由在声称物种"：
        #   否定词 —— 「非人源宿主（…），非**人类**临床样本」里的"人类"命中的
        #             是自己那句否定，会把正确的理由判成矛盾；
        #   「」引用 —— 写更正说明时必然要引用被删掉的旧判词（"原判词写
        #              「非人源宿主（mouse）」，无据，已删"），检查却把这段
        #              引用当成了声称。声称一律用（）写，引用一律用「」写。
        why_pos = re.sub(r"「[^」]*」", "", re.sub(r"非(人源|人类|人)", "", why))
        claimed = [sp for sp, pat in SPECIES.items()
                   if sp in why_pos or re.search(pat, why_pos, re.I)]
        # 没有摘要时证据只剩标题，而标题常常不含物种词（"草地螟肠道菌群"
        # 的英文标题里并没有 insect）。这种情况是【拿不出证据】，不是
        # 【证据矛盾】——按"不符"报错会把正确的理由判成造假。
        if not claimed:
            vague["未点名物种"] += 1
            continue
        if not abstract:
            vague["无摘要"] += 1
            continue
        if any(re.search(SPECIES[sp], text, re.I) for sp in claimed):
            continue                     # 声称的物种在记录里确有出现，通过
        hit = [sp for sp in SPECIES if sp not in claimed
               and re.search(SPECIES[sp], text, re.I)]
        if hit:
            problems.append(f"{k} 的理由声称【{'/'.join(claimed)}】，但原始记录命中的是"
                            f"【{'/'.join(hit)}】—— 理由与记录矛盾\n"
                            f"      {rec.get('title','')[:100]}")
        else:
            vague["记录里查不到"] += 1      # 哪一类都没命中：拿不出证据，不算错

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

    # 6. 分诊口径已改为「必须看摘要」，所以台账里不该再有任何凭标题分诊的理由。
    #    这条抓的是【漏交代】：重审时读完一批、却漏把其中若干条写回台账，
    #    它们会静默保留旧理由——脚本全绿，但台账没真的更新过。
    stale = sorted(k for k, v in led.items()
                   if not k.startswith("_") and isinstance(v, dict)
                   and (v.get("why") or "").startswith("标题分诊"))
    if stale:
        problems.append(f"台账里还有 {len(stale)} 条是「标题分诊」的旧理由 —— "
                        f"摘要重审还没写完，或写完时漏了它们。前几条：\n      "
                        + "\n      ".join(stale[:6]))

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
    if any(vague.values()):
        n_claim = sum(1 for v in led.values()
                      if isinstance(v, dict) and "非人源" in (v.get("why") or ""))
        print(f"  · 物种校验实际比对 {n_claim - sum(vague.values())} 条；"
              f"跳过 {sum(vague.values())} 条（"
              + " / ".join(f"{r} {n}" for r, n in vague.items() if n) + "）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
