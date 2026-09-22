# -*- coding: utf-8 -*-
"""开奖对账 —— 把实际开奖号与你的注单逐注比对，算命中与奖金。

用法：
    python check_result.py "02 05 07 14 22 + 04 10" --file 我的_26108_1注.txt
    python check_result.py "02 05 07 14 22 + 04 10" --file 注单1.txt 注单2.txt
    python check_result.py "02 05 07 14 22 + 04 10" --file 我的.txt --pool-big

    --pool-big  奖池 >= 8 亿时的固定奖上浮口径（三至七等 6666/380/200/18/7）；
                不加则按基准口径（5000/300/150/15/5）。
"""
import argparse
import os
import sys

# 允许从任意工作目录直接运行本脚本
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from filter_check import parse_bet  # noqa: E402
from lottery_core import calc_prize  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="开奖对账：判每注中了几等奖")
    ap.add_argument("winning", help='开奖号，如 "02 05 07 14 22 + 04 10"')
    ap.add_argument("--file", "-f", nargs="+", required=True,
                    help="注单文件（每行一注，前5+后2；# 开头为注释）")
    ap.add_argument("--pool-big", action="store_true",
                    help="奖池>=8亿，固定奖上浮（三至七等 6666/380/200/18/7）")
    a = ap.parse_args()

    win_f, win_b = parse_bet(a.winning)
    pool_big = a.pool_big
    POOL_TXT = "奖池>=8亿，固定奖上浮（三至七等 6666/380/200/18/7）" if pool_big \
        else "奖池<8亿，固定奖基准（三至七等 5000/300/150/15/5）"

    print("=" * 88)
    print(f"开奖号：{' '.join(f'{n:02d}' for n in sorted(win_f))}"
          f"  +  {' '.join(f'{n:02d}' for n in sorted(win_b))}")
    print(f"固定奖口径：{POOL_TXT}")
    print("=" * 88)

    for path in a.file:
        if not os.path.isfile(path):
            print(f"\n✗ 找不到注单文件：{path}")
            continue
        bets = []
        with open(path, encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if ln and not ln.startswith("#"):
                    bets.append((parse_bet(ln), ln))
        total = 0
        nwin = 0
        floats = []
        hits = []
        print(f"\n【{path}】{len(bets)} 注，成本 {len(bets) * 2} 元")
        print(f"  {'#':>2} {'号码':<28}{'前中':>5}{'后中':>5}  {'奖级':<8}{'奖金':>8}")
        for i, ((f, b), raw) in enumerate(bets, 1):
            fm, bm = len(f & win_f), len(b & win_b)
            prize, tier = calc_prize(fm, bm, pool_big)
            won = tier != "未中奖"
            amt = prize if isinstance(prize, int) else 0
            if won:
                nwin += 1
                total += amt
                if not isinstance(prize, int):
                    floats.append((i, tier))
            cell = str(amt) if (won and isinstance(prize, int)) else ("浮动" if won else "-")
            if fm or bm:
                hits.append((i, fm, bm, tier))
            print(f"  {i:>2} {raw:<28}{fm:>5}{bm:>5}  {tier:<8}{cell:>8}"
                  f"{'  ←' if won else ''}")
        net = total - len(bets) * 2
        print(f"  ── 中奖 {nwin} 注，合计 {total} 元"
              + (f"（另有浮动奖 {len(floats)} 注未计入）" if floats else "")
              + f"，净 {'+' if net >= 0 else ''}{net} 元")
        if hits:
            print("  ── 有命中的注：" + "；".join(
                f"第{i}注 {fm}+{bm}({t})" for i, fm, bm, t in hits))
        else:
            print(f"  ── {len(bets)} 注没有任何一注命中前区或后区")
        best = max((len(f & win_f) + len(b & win_b) for (f, b), _ in bets), default=0)
        nb = sum(1 for (f, b), _ in bets if b & win_b == win_b)
        print(f"  ── 单注最高命中：{best} 个号（前区+后区）"
              f"　后区两号全中的注：{nb} 注")


if __name__ == "__main__":
    main()
