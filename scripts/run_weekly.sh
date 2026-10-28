#!/usr/bin/env bash
# 每周文献增量的总控脚本。定时任务只需要调这一个：
#
#   bash scripts/run_weekly.sh
#
# 退出码：0 成功（含「本周 0 条」与「今天已跑过」）
#         1 失败（数据已回滚，last_run.json 未动，下次会从同一起点重来）
#         2 另一次运行正在进行
#         3 已提交但推送失败（下次运行会一并推上去）
#
# 环境变量（测试用）：LIT_NO_PULL=1 不拉取；LIT_NO_PUSH=1 不推送；
#   LIT_LIMIT / LIT_REJUDGE_LIMIT / LIT_MODEL 透传给 judge.py
#
# 每一步失败都停在原地。判断层的结果留在 work/<日期>/ 里，同一天重跑会接着判、不重复花钱。

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
DATE="$(date +%F)"
mkdir -p logs
LOG="logs/run_${DATE}_$(date +%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

# 流程会改动的受版本控制文件。失败时只回滚这些，不碰别的
TRACKED=(data/seen.json data/entries.json data/rejudge.json data/last_run.json data/runs.json
         site queries.generated.md)
WEEKLY="weekly/${DATE}.md"
APPLIED=0

step() { echo; echo "=== [$(date +%T)] $* ==="; }
rollback() {
  [[ $APPLIED == 1 ]] || return 0
  echo "回滚数据文件……"
  git checkout -- "${TRACKED[@]}" 2>/dev/null
  # site/ 整体是生成物：失败那轮新建的周页要删掉，否则下次预检会看到残页
  git clean -fdq -- site 2>/dev/null
  [[ ${WEEKLY_EXISTED:-1} == 0 ]] && rm -f "$WEEKLY"
}
fail() {
  echo; echo "RESULT: FAILED — $1"
  rollback
  echo "日志：$LOG"
  exit 1
}

# 同一时间只允许一个实例
exec 9>"logs/.run.lock"
flock -n 9 || { echo "RESULT: BUSY — 另一次运行正在进行"; exit 2; }

step "预检"
for c in git python3 claude; do
  command -v "$c" >/dev/null || fail "找不到命令 $c"
done
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  git status --short --untracked-files=no
  fail "工作区有未提交的改动——先提交或还原，自动运行不和手工改动混在一起"
fi
LAST="$(python3 -c 'import json;print(json.load(open("data/last_run.json")).get("last_success",""))')"
if [[ "$LAST" == "$DATE" ]]; then
  echo "RESULT: OK — 今天（$DATE）已经成功运行过，跳过"
  exit 0
fi
if [[ "${LIT_NO_PULL:-0}" != 1 ]]; then
  git pull --ff-only --quiet origin main || fail "git pull 失败（网络，或本地与远端分叉）"
fi
[[ -e "$WEEKLY" ]] && WEEKLY_EXISTED=1 || WEEKLY_EXISTED=0

step "1/6 抓取（fetch.py）"
# 抓取失败绝不能当成「本周无新增」——退出码非 0 就停
python3 scripts/fetch.py || fail "fetch.py 失败"

step "2/6 补摘要缓存（enrich.py）"
# 只影响页面上的摘要展示，失败不拦整轮
python3 scripts/enrich.py || echo "警告：enrich.py 失败，本周新条目暂无摘要展示，不影响收录"

step "3/6 判断（judge.py → claude -p，无工具）"
python3 scripts/judge.py --date "$DATE" || fail "judge.py 失败（已判完的批次保留在 work/$DATE/，重跑会接着判）"
# 判断层没有工具，不可能改文件；这里再核一遍，防止哪天参数被改坏
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  fail "判断阶段后受版本控制的文件被改动了——判断层不应碰任何文件"
fi

step "4/6 写入台账、清单与批次记录（apply_judgments.py）→ 校验"
APPLIED=1
python3 scripts/apply_judgments.py apply "$DATE" || fail "apply_judgments.py 失败"
# finalize 写 runs.json 与 last_run.json，要在校验和建页之前：validate 要核对每条收录都有批次，
# 周页按 runs.json 生成，页面「数据截至」读 last_run.json。
# last_run 决定下次补漏起点——它在这里写入，但只有整轮提交成功才算数：
# 之后任何一步失败，rollback 都会把它恢复原样。
python3 scripts/apply_judgments.py finalize "$DATE" || fail "写 runs.json / last_run.json 失败"
python3 scripts/validate.py || fail "validate.py 未通过——数据已回滚，不提交"

step "5/6 生成页面（build_page.py）"
python3 scripts/build_page.py --queries-md || fail "build_page.py 失败"

step "6/6 提交与推送"
MSG="$(python3 - "$DATE" <<'PY'
import json, sys
s = json.load(open(f"work/{sys.argv[1]}/summary.json"))
head = f"文献增量 {s['date']}：收录 {s['in']} 条（新候选 {s['candidates']}"
head += f"，重审 {s['rejudged']}）" if s["rejudged"] else "）"
print(head)
print()
print(f"窗口 {s['since']} → {s['until']}（{s['week']}）· 不收 {s['out']} · 跳过 {s['skip']}"
      + (f" · 重审改判收录 {s['rejudge_to_in']}" if s["rejudged"] else ""))
print("由 scripts/run_weekly.sh 自动生成。")
print()
print("Co-Authored-By: Claude Code <noreply@anthropic.com>")
PY
)"
git add "${TRACKED[@]}" "$WEEKLY" || fail "git add 失败"
git commit -q -m "$MSG" || fail "git commit 失败"
APPLIED=0   # 已提交，之后的失败不再回滚
echo "$MSG" | head -1

if [[ "${LIT_NO_PUSH:-0}" == 1 ]]; then
  echo "RESULT: OK — 已提交，按 LIT_NO_PUSH 未推送"
  exit 0
fi
if git push --quiet origin main; then
  echo "RESULT: OK — 已提交并推送"
else
  echo "RESULT: PUSH FAILED — 已在本地提交，下次运行会一并推送"
  exit 3
fi
