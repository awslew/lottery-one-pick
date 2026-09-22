# -*- coding: utf-8 -*-
"""查期号：python show_period.py 26080 26076 ...   （按数据表里的期号查开奖号）"""
import argparse
import os
import sys

import openpyxl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from paths import find_data_file  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="按期号查历史开奖号")
    ap.add_argument("periods", nargs="+", help="一个或多个期号，如 26080 26076")
    a = ap.parse_args()

    want = {str(p).strip() for p in a.periods}
    ws = openpyxl.load_workbook(find_data_file(), data_only=True).active
    found = set()
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0] in (None, ""):
            continue
        pid = str(r[0]).strip()
        if pid in want:
            f = " ".join(f"{int(x):02d}" for x in r[2:7])
            b = " ".join(f"{int(x):02d}" for x in r[7:9])
            print(f"  {pid}  {str(r[1])[:10]}   {f}  +  {b}")
            found.add(pid)
    missing = sorted(want - found)
    if missing:
        print(f"  未找到：{' '.join(missing)}")


if __name__ == "__main__":
    main()
