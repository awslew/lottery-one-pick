# -*- coding: utf-8 -*-
"""每期出 1 注 —— 排除池随机 + 三关过筛

流程（每期固定四步）：
    ① python update_excel.py                     更新历史开奖数据表
    ② 你给排除号：前区排除哪几个、后区排除哪几个
    ③ 本脚本在「排除后的号池」里随机组 1 注（前区 5 + 后区 2）
    ④ 过三关：历史关 + 前区关 + 后区关 → 不过就重抽，过了就交付这一注

用法：
    python dlt_pick_one.py                       # 不排除任何号
    python dlt_pick_one.py -ef 4,9,13 -eb 3,5    # 前区排除 04/09/13，后区排除 03/05
    python dlt_pick_one.py --period 26108 -ef 4,9,13
    python dlt_pick_one.py --seed 12345          # 固定随机种子 → 复现同一注
    python dlt_pick_one.py --tries 50000         # 重抽上限（默认 50000）
    python dlt_pick_one.py --outdir D:\\我的号码   # 落盘目录，默认当前目录

产出：
    屏显这一注；落盘 我的_<期号>_1注.txt；追加一行到 出号记录.txt

口径说明：这一注只与三个输入有关 —— ① 历史数据 ② 规则集（三关）③ 你给的排除号。
    没有专家号、没有频次加权、没有多注覆盖；过筛判定复用 filter_check 的 gates()，
    与筛号器（python filter_check.py "号码"）100% 同源，不会出现两套口径。
"""
CURRENT_PERIOD = "26109"   # ← 全项目唯一「主开关」：其余脚本的默认期号都读这一行

import argparse
import os
import random
import re
import sys
import time
from datetime import datetime

# 允许从任意工作目录直接运行本脚本
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from filter_check import build_ctx, check_one, gates  # noqa: E402
    from lottery_core import BACK_POOL, FRONT_POOL  # noqa: E402
except ModuleNotFoundError as e:
    raise SystemExit(
        f"✗ 缺少依赖或数据表（{e}）\n"
        "    先装依赖：pip install -r requirements.txt\n"
        "    再备数据：仓库自带 data/大乐透历史开奖数据.xlsx，"
        "或设环境变量 DLT_DATA 指向你自己的表。"
    )

LOG_NAME = "出号记录.txt"
LOG_HEADER = "# 期号\t出号时间\t号码\t前区排除\t后区排除\t尝试次数\tseed\n"


def parse_excludes(text, lo, hi, label):
    """把 '4,9,13' / '4 9 13' 这类输入解析成排除号集合，并做范围校验。"""
    if not text:
        return set()
    nums = {int(x) for x in re.findall(r"\d+", text)}
    bad = sorted(n for n in nums if not lo <= n <= hi)
    if bad:
        raise SystemExit(f"✗ {label}排除号越界（合法范围 {lo}~{hi}）：{bad}")
    return nums


def fmt(nums):
    return " ".join(f"{n:02d}" for n in sorted(nums))


def main():
    ap = argparse.ArgumentParser(
        description="每期出 1 注：排除池随机 + 历史/前区/后区三关过筛")
    ap.add_argument("-ef", "--exclude-front", default="",
                    help="前区排除号，如 4,9,13（可多个）")
    ap.add_argument("-eb", "--exclude-back", default="",
                    help="后区排除号，如 3,5（可多个）")
    ap.add_argument("--period", default=None,
                    help=f"目标期，默认取主开关 CURRENT_PERIOD = {CURRENT_PERIOD}")
    ap.add_argument("--seed", type=int, default=None,
                    help="固定随机种子（同期重跑可复现同一注）")
    ap.add_argument("--tries", type=int, default=50000,
                    help="重抽上限，默认 50000")
    ap.add_argument("--outdir", default=".",
                    help="落盘目录，默认当前目录")
    a = ap.parse_args()

    period = a.period or CURRENT_PERIOD
    ex_f = parse_excludes(a.exclude_front, 1, 35, "前区")
    ex_b = parse_excludes(a.exclude_back, 1, 12, "后区")
    front_pool = [n for n in FRONT_POOL if n not in ex_f]
    back_pool = [n for n in BACK_POOL if n not in ex_b]
    if len(front_pool) < 5 or len(back_pool) < 2:
        raise SystemExit(f"✗ 排除太多，凑不出 1 注：前区剩 {len(front_pool)} 个 / "
                         f"后区剩 {len(back_pool)} 个")

    ctx = build_ctx(period)
    hist = ctx["hist"]

    print("=" * 72)
    print(f"出号 · 目标期 {period}    （主开关 CURRENT_PERIOD = {CURRENT_PERIOD}）")
    print("=" * 72)
    print(f"  历史基准   : {len(hist)} 期，{hist[0]['pid']}({hist[0]['dt']}) "
          f"~ {hist[-1]['pid']}({hist[-1]['dt']})")
    print(f"  上期号     : {fmt(ctx['last_front'])}  +  {fmt(ctx['last_back'])}")
    if hist[-1]["pid"] >= period:
        print(f"  ⚠ 数据表里已存在 {hist[-1]['pid']}，本注按「{period} 开奖前」的历史计算")
    print(f"  前区排除   : {fmt(ex_f) or '无'}    → 池 {len(front_pool)} 个号")
    print(f"  后区排除   : {fmt(ex_b) or '无'}    → 池 {len(back_pool)} 个号")
    print("-" * 72)

    rng = random.Random(a.seed)
    t0 = time.time()
    front = back = None
    attempt = 0
    for attempt in range(1, a.tries + 1):
        f = frozenset(rng.sample(front_pool, 5))
        b = frozenset(rng.sample(back_pool, 2))
        if all(gates(f, b, ctx)):
            front, back = f, b
            break
    if front is None:
        raise SystemExit(f"✗ 重抽 {a.tries} 次仍未过筛（排除条件过严？）"
                         f"——可加大 --tries，或减少排除号")
    elapsed = time.time() - t0

    line = f"{fmt(front)} + {fmt(back)}"
    passed, fr, br, kill, drift = check_one(front, back, ctx)
    rv = {name[0]: val for name, _, val in fr + br}

    print(f"  {line}")
    print(f"  和值{rv['④']}  跨度{rv['⑤']}  {rv['①']}  区间{rv['②'].replace('区分布', '')}  "
          f"{rv['③']}  {rv['⑩']}  后跨{rv['⑪']}")
    print(f"  ✅ 三关全过（13 条规则 + 历史杀号）"
          f"　第 {attempt} 次尝试命中，用时 {elapsed:.2f}s")
    if drift:
        print("  ⚠️ 规则镜像与 lottery_core 不一致，请检查脚本！")

    outdir = os.path.abspath(a.outdir)
    os.makedirs(outdir, exist_ok=True)
    out_path = os.path.join(outdir, f"我的_{period}_1注.txt")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(line + "\n")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_path = os.path.join(outdir, LOG_NAME)
    fresh = not os.path.exists(log_path)
    with open(log_path, "a", encoding="utf-8") as fh:
        if fresh:
            fh.write(LOG_HEADER)
        fh.write(f"{period}\t{stamp}\t{line}\t{fmt(ex_f) or '-'}\t"
                 f"{fmt(ex_b) or '-'}\t{attempt}\t{a.seed if a.seed is not None else '-'}\n")
    print("-" * 72)
    print(f"  已落盘: {out_path}")
    print(f"  已记录: {log_path}")
    print("=" * 72)


if __name__ == "__main__":
    main()
