# -*- coding: utf-8 -*-
"""筛号器 —— 只做「历史关 + 前区关 + 后区关」三关筛选，不生成任何随机号。

用法：
  python filter_check.py                       # 看本期筛选概况 + 冷号/遗漏
  python filter_check.py 08,09,10,11,25,04,12  # 检查一注（前5个 + 后2个）
  python filter_check.py "08 09 10 11 25 + 04 12"
  python filter_check.py --file 我的号码.txt    # 批量检查（每行一注，格式同上）
  python filter_check.py --period 26108 08,09,10,11,25,04,12

口径：判定第 N 期时，历史 / 2026历史 / 冷号 / 上期号 全部只取第 N 期**之前**的数据。
      默认期号从 dlt_pick_one.py 的 CURRENT_PERIOD 读取。
      数据表位置见 paths.find_data_file()（可用环境变量 DLT_DATA 覆盖）。
"""
import os
import re
import sys

import openpyxl

# 允许从任意工作目录直接运行本脚本（否则同目录模块 import 会失败）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from lottery_core import current_period  # noqa: E402
from lottery_core import (  # noqa: E402
    BACK_COLD_INTERVAL, COLD_INTERVAL, PRIMES, calc_cold_backs,
    calc_cold_fronts, check_back_all, check_front_all, is_bet_safe,
)
from paths import find_data_file  # noqa: E402


def load_history(period):
    """取第 period 期之前的全部历史（与生产脚本同一读法）。"""
    ws = openpyxl.load_workbook(find_data_file(), data_only=True).active
    hist = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] in (None, ""):
            continue
        pid = str(row[0]).strip()
        if pid == period:
            break
        hist.append({"pid": pid, "dt": str(row[1]).strip()[:10],
                     "front": frozenset(int(x) for x in row[2:7]),
                     "back": frozenset(int(x) for x in row[7:9])})
    return hist


# ---------------- 逐条规则（镜像 lottery_core，仅用于展示是哪条挡住的） ----------------
def front_report(front, cold_f, last_front):
    f = sorted(front)
    odd = sum(1 for n in f if n % 2)
    z1 = sum(1 for n in f if n <= 12)
    z2 = sum(1 for n in f if 13 <= n <= 24)
    z3 = sum(1 for n in f if n >= 25)
    mc = cur = 1
    for i in range(1, 5):
        if f[i] == f[i - 1] + 1:
            cur += 1
            mc = max(mc, cur)
        else:
            cur = 1
    diffs = {f[j] - f[i] for i in range(5) for j in range(i + 1, 5)}
    r = [sum(1 for n in f if n % 3 == k) for k in (0, 1, 2)]
    return [
        ("① 奇偶 1~4奇", odd in {1, 2, 3, 4}, f"{odd}奇{5-odd}偶"),
        ("② 区间 ≥2区且单区≤4", ((z1 > 0) + (z2 > 0) + (z3 > 0)) >= 2 and max(z1, z2, z3) <= 4,
         f"区分布{z1}/{z2}/{z3}"),
        ("③ 连号 ≤3连", mc <= 3, f"最长{mc}连"),
        ("④ 和值 40~150", 40 <= sum(f) <= 150, f"{sum(f)}"),
        ("⑤ 跨度 13~33", 13 <= f[-1] - f[0] <= 33, f"{f[-1]}-{f[0]}={f[-1]-f[0]}"),
        ("⑥ 首≤20 且 尾≥21", f[0] <= 20 and f[-1] >= 21, f"首{f[0]}尾{f[-1]}"),
        ("⑦ 上期重号 ≤3", len(front & last_front) <= 3,
         f"重{sorted(front & last_front) or '无'}"),
        ("⑧ 质数 ≤4", sum(1 for n in f if n in PRIMES) <= 4,
         f"{sorted(n for n in front if n in PRIMES) or '无'}"),
        ("⑨ 012路 禁全同余", max(r) < 5, f"{r[0]}/{r[1]}/{r[2]}"),
        ("⑩ AC值 ≥2", len(diffs) - 4 >= 2, f"AC={len(diffs)-4}"),
    ]


def back_report(back, cold_b, last_back):
    return [
        ("⑪ 后区跨度（已取消）", True, f"{max(back)-min(back)}"),
        ("⑫ 后区冷号 ≤1", len(back & cold_b) <= 1,
         f"冷{sorted(back & cold_b) or '无'}"),
        ("⑬ 后区上期重号 ≤1", len(back & last_back) <= 1,
         f"重{sorted(back & last_back) or '无'}"),
    ]


def kill_reason(front, back, hist, h26):
    """复刻 is_bet_safe，并报出撞的是哪一期。"""
    for h in hist:
        fm = len(front & h["front"])
        if fm == 5:
            return f"5+* 撞 {h['pid']}({h['dt']})"
        if fm == 4 and len(back & h["back"]) == 2:
            return f"4+2 撞 {h['pid']}({h['dt']})"
    for h in h26:
        fm = len(front & h["front"])
        if fm == 4 and len(back & h["back"]) <= 1:
            return f"4+{len(back & h['back'])} 撞2026 {h['pid']}({h['dt']})"
        if fm == 3 and len(back & h["back"]) == 2:
            return f"3+2 撞2026 {h['pid']}({h['dt']})"
    return None


def parse_bet(text):
    nums = [int(x) for x in re.findall(r"\d+", text)]
    if len(nums) != 7:
        raise ValueError(f"需要 7 个数字（前区5 + 后区2），实际 {len(nums)} 个: {text!r}")
    front, back = nums[:5], nums[5:]
    if len(set(front)) != 5 or not all(1 <= n <= 35 for n in front):
        raise ValueError(f"前区不合法: {sorted(front)}")
    if len(set(back)) != 2 or not all(1 <= n <= 12 for n in back):
        raise ValueError(f"后区不合法: {sorted(back)}")
    return frozenset(front), frozenset(back)


def build_ctx(period):
    """搭出三关所需的上下文（历史 / 2026历史 / 上期号 / 冷号 / 预算好的历史元组）。"""
    hist = load_history(period)
    if not hist:
        raise SystemExit(f"❌ 数据表里找不到期号 {period}（历史为空）")
    ctx = {
        "period": period,
        "hist": hist,
        "h26": [h for h in hist if h["dt"] >= "2026-01-01"],
        "last_front": hist[-1]["front"],
        "last_back": hist[-1]["back"],
        # 预算成 (front, back) 元组：出号脚本要重抽多次，避免每次重建
        "hist_t": [(h["front"], h["back"]) for h in hist],
        "h26_t": [(h["front"], h["back"]) for h in hist
                  if h["dt"] >= "2026-01-01"],
    }
    ctx["cold_f"], _ = calc_cold_fronts(ctx["hist_t"])
    ctx["cold_b"], b_ls = calc_cold_backs(ctx["hist_t"])
    ctx["gap_b"] = {n: len(hist) - 1 - b_ls[n] for n in range(1, 13)}
    return ctx


def gates(front, back, ctx):
    """三关硬判定（引擎口径）：返回 (前区, 后区, 历史) 三个 bool。"""
    return (bool(check_front_all(front, ctx["cold_f"], ctx["last_front"], 0, 0)),
            bool(check_back_all(back, ctx["cold_b"], ctx["last_back"])),
            bool(is_bet_safe(front, back, ctx["hist_t"], ctx["h26_t"])))


def passes(front, back, ctx):
    """三关全过才算通过。"""
    return all(gates(front, back, ctx))


def check_one(front, back, ctx):
    fr = front_report(front, ctx["cold_f"], ctx["last_front"])
    br = back_report(back, ctx["cold_b"], ctx["last_back"])
    kill = kill_reason(front, back, ctx["hist"], ctx["h26"])

    mirror_front = all(ok for _, ok, _ in fr)
    mirror_back = all(ok for _, ok, _ in br)
    real_front, real_back, real_kill = gates(front, back, ctx)
    drift = (mirror_front != real_front) or (mirror_back != real_back) \
        or ((kill is None) != real_kill)

    passed = real_front and real_back and real_kill
    return passed, fr, br, kill, drift


def parse_many(text):
    """支持多种写法：分号/换行分隔，或一行里塞多注（按每 7 个数字切）。"""
    chunks = [c for c in re.split(r"[;；\n]+", text) if c.strip()]
    bets = []
    for c in chunks:
        nums = re.findall(r"\d+", c)
        if len(nums) == 7:
            bets.append(c.strip())
        elif nums and len(nums) % 7 == 0:
            for k in range(0, len(nums), 7):
                bets.append(" ".join(nums[k:k + 7]))
        else:
            bets.append(c.strip())
    return bets


def main():
    args = sys.argv[1:]
    period = current_period()
    if "--period" in args:
        i = args.index("--period")
        period = args[i + 1]
        del args[i:i + 2]
    bets = []
    if "--file" in args:
        i = args.index("--file")
        with open(args[i + 1], encoding="utf-8") as fh:
            bets = [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
    elif args:
        bets = parse_many(" ".join(args))

    ctx = build_ctx(period)
    hist, gap_b = ctx["hist"], ctx["gap_b"]

    print("=" * 72)
    print(f"筛号器 · 目标期 {period}")
    print("=" * 72)
    print(f"  数据表     : {find_data_file()}")
    print(f"  历史基准   : {len(hist)} 期，{hist[0]['pid']}({hist[0]['dt']}) "
          f"~ {hist[-1]['pid']}({hist[-1]['dt']})")
    print(f"  2026历史   : {len(ctx['h26'])} 期")
    print(f"  上期号     : {' '.join(f'{n:02d}' for n in sorted(ctx['last_front']))}"
          f"  +  {' '.join(f'{n:02d}' for n in sorted(ctx['last_back']))}")
    print(f"  前区冷号(遗漏≥{COLD_INTERVAL}): {sorted(ctx['cold_f'])}")
    print(f"  后区冷号(遗漏≥{BACK_COLD_INTERVAL}): {sorted(ctx['cold_b'])}")
    print("  后区各号遗漏: " + "  ".join(f"{n:02d}:{gap_b[n]}" for n in range(1, 13)))

    if not bets:
        print()
        print("  （把号码给我就筛，例：python filter_check.py 08,09,10,11,25,04,12）")
        print("=" * 72)
        return

    nmatch = 0
    for text in bets:
        try:
            front, back = parse_bet(text)
        except ValueError as e:
            print(f"\n  ✗ 解析失败：{e}")
            continue
        passed, fr, br, kill, drift = check_one(front, back, ctx)
        nmatch += passed
        fs = " ".join(f"{n:02d}" for n in sorted(front))
        bs = " ".join(f"{n:02d}" for n in sorted(back))
        print()
        print(f"  ── {fs} + {bs} ──  {'✅ 通过筛选' if passed else '❌ 被筛掉'}")
        for name, ok, val in fr + br:
            if not ok:
                print(f"       ✗ {name}   实算: {val}")
        if kill:
            print(f"       ✗ ⑭ 历史杀号   {kill}")
        bad = [n for n, ok, _ in fr + br if not ok]
        if not bad and not kill:
            print("       （13 条规则 + 历史杀号 全部通过）")
        if drift:
            print("       ⚠️ 镜像与 lottery_core 不一致，请检查脚本！")

    if len(bets) > 1:
        print()
        print(f"  合计：{nmatch}/{len(bets)} 注通过筛选")
    print("=" * 72)


if __name__ == "__main__":
    main()
