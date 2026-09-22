# -*- coding: utf-8 -*-
"""
大乐透历史开奖数据 · 增量更新工具
=================================
用法：
    python update_excel.py              # 自动联网补齐缺口（默认，推荐）
    python update_excel.py --dry-run    # 只列出要补哪些期，不写文件
    python update_excel.py --no-fetch   # 不联网，只用 NEW_DRAWS 手工补录
    python update_excel.py --check      # 只对数据表做自检，不更新
    python update_excel.py --snapshot   # 更新后另存一份 大乐透历史开奖数据_含<期号>.xlsx

- 数据表位置见 paths.find_data_file()（依次找 $DLT_DATA → data/ → 当前目录）
- 默认从体彩官方接口（webapi.sporttery.cn）拉取缺失期次：既补表尾新期，
  也补表中间的断档（断档按期号插到正确位置，不会打乱排序）
- NEW_DRAWS 手工补录优先级高于联网结果（接口改版/停更时的保险）
- 追加行样式取自「最后一行有样式的数据行」（不是简单取末行，避免空白样式传染）
- 顺手修补丢样式的行，并把自动筛选范围拉满到整表
- 保存后自检：总行数、逐年无缺口、号码合法性、与官方总期数对账、首尾行
"""

import argparse
import json
import os
import re
import sys
import urllib.request

from copy import copy

import openpyxl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from paths import find_data_file  # noqa: E402

# ============================================================
# 手工补录（可选）：联网抓不到时在这里兜底
# 格式：(期号, 开奖日期, 前区5个升序, 后区2个升序)
# 同一期号在 NEW_DRAWS 里写了，就以手工值为准
# ============================================================
NEW_DRAWS = []

# 体彩官方历史开奖接口（gameNo=85 即超级大乐透）
API_URL = (
    "https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry"
    "?gameNo=85&provinceId=0&pageSize={page_size}&isVer=1&pageNo={page_no}"
)
API_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.lottery.gov.cn/",
}


def parse_api_record(rec):
    """把官方接口的一条记录转成 (期号, 日期, 前区list, 后区list)。"""
    pid = str(rec["lotteryDrawNum"]).strip()
    dt = str(rec["lotteryDrawTime"]).strip()
    parts = str(rec["lotteryDrawResult"]).split()
    if len(parts) < 7:
        raise ValueError(f"{pid} 号码字段异常: {rec.get('lotteryDrawResult')!r}")
    fronts = sorted(int(x) for x in parts[:5])
    backs = sorted(int(x) for x in parts[5:7])
    return pid, dt, fronts, backs


def fetch_official(page_count=3, page_size=100):
    """抓官方最近 page_count 页，返回 {期号: (日期, 前区, 后区)} 与官方总期数。"""
    draws, total = {}, None
    for page in range(1, page_count + 1):
        url = API_URL.format(page_size=page_size, page_no=page)
        req = urllib.request.Request(url, headers=API_HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read())
        value = payload["value"]
        total = value.get("total", total)
        records = value.get("list") or []
        for rec in records:
            try:
                pid, dt, fronts, backs = parse_api_record(rec)
            except ValueError as e:
                print(f"  ! 跳过异常记录: {e}")
                continue
            draws[pid] = (dt, fronts, backs)
        if len(records) < page_size:
            break
    return draws, total


def validate_draw(pid, dt, fronts, backs):
    """写入前的合法性检查。"""
    assert re.match(r"^\d{5}$", pid), f"{pid} 期号格式不对"
    assert len(fronts) == 5 and len(backs) == 2, f"{pid} 号码个数不对"
    assert len(set(fronts)) == 5 and len(set(backs)) == 2, f"{pid} 有重复号码"
    assert all(1 <= n <= 35 for n in fronts), f"{pid} 前区越界"
    assert all(1 <= n <= 12 for n in backs), f"{pid} 后区越界"
    assert fronts == sorted(fronts) and backs == sorted(backs), f"{pid} 未升序"
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", dt), f"{pid} 日期格式不对"


def row_values(pid, dt, fronts, backs):
    return [pid, dt, *fronts, *backs, " ".join(f"{n:02d}" for n in fronts + backs)]


def style_signature(cell):
    """把一个单元格的可见样式压成可比较的元组。"""
    b = cell.border
    return (
        b.left.style, b.right.style, b.top.style, b.bottom.style,
        cell.fill.fill_type, str(cell.fill.start_color.rgb),
        cell.alignment.horizontal, cell.font.b, cell.number_format,
    )


def is_unstyled(ws, row):
    """整行既无边框又无填充 → 判定为「丢样式行」。"""
    for c in range(1, 11):
        cell = ws.cell(row=row, column=c)
        b = cell.border
        if any(s is not None for s in (b.left.style, b.right.style, b.top.style, b.bottom.style)):
            return False
        if cell.fill.fill_type not in (None, "none"):
            return False
    return True


def find_style_row(ws):
    """从末行往上找最后一行「有样式」的数据行，作为样式样本。"""
    for r in range(ws.max_row, 1, -1):
        if ws.cell(row=r, column=1).value not in (None, "") and not is_unstyled(ws, r):
            return r
    return ws.max_row


def copy_style(ws, src_row, dst_row):
    for c in range(1, 11):
        src, dst = ws.cell(row=src_row, column=c), ws.cell(row=dst_row, column=c)
        dst.font = copy(src.font)
        dst.fill = copy(src.fill)
        dst.border = copy(src.border)
        dst.alignment = copy(src.alignment)
        dst.number_format = src.number_format


def repair_unstyled(ws, sample_row):
    """把丢样式的行补成样本行的样式；返回修补的行号。"""
    fixed = []
    for r in range(2, ws.max_row + 1):
        if r != sample_row and is_unstyled(ws, r):
            copy_style(ws, sample_row, r)
            fixed.append(r)
    return fixed


def read_sheet(path):
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    rows = {}
    for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if row[0] in (None, ""):
            continue
        rows[str(row[0]).strip()] = idx
    return wb, ws, rows


def sheet_rows(ws):
    """{期号: (日期, 前区, 后区)}，用于和官方数据对账。

    这里**刻意不做 sort**：排序会掩盖表里本来就乱序的行，让 validate_draw 的
    升序断言失效。保持原值，交给 validate_draw 去发现。
    """
    out = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] in (None, ""):
            continue
        pid = str(row[0]).strip()
        try:
            out[pid] = (
                str(row[1]).strip()[:10],
                [int(x) for x in row[2:7]],
                [int(x) for x in row[7:9]],
            )
        except (TypeError, ValueError):
            out[pid] = None  # 老数据里可能是字符串形式的号码
    return out


def write_rows(ws, start_row, items, style_refs):
    """从 start_row 起连续写入 items（不插入行，只覆盖/追加）。"""
    r = start_row
    for pid, dt, fronts, backs in items:
        values = row_values(pid, dt, fronts, backs)
        for c, v in enumerate(values, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell._style = copy(style_refs[c - 1])
        r += 1
    return r


def insert_rows_sorted(ws, items, style_refs):
    """把断档期次按 期号 升序插到正确位置（不会打乱原有排序）。"""
    for pid, dt, fronts, backs in items:
        target = ws.max_row + 1
        for r in range(2, ws.max_row + 1):
            v = ws.cell(row=r, column=1).value
            if v not in (None, "") and int(str(v)) > int(pid):
                target = r
                break
        ws.insert_rows(target)
        style = style_refs if target == ws.max_row else [
            ws.cell(row=target - 1, column=c)._style for c in range(1, 11)
        ]
        for c, v in enumerate(row_values(pid, dt, fronts, backs), 1):
            cell = ws.cell(row=target, column=c, value=v)
            cell._style = copy(style[c - 1])
        print(f"  + 插入断档 {pid} 于第 {target} 行")


def self_check(path, api_total=None):
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    ids = [str(r[0]).strip() for r in ws.iter_rows(min_row=2, values_only=True) if r[0] not in (None, "")]
    nums = [int(x) for x in ids if x.isdigit()]
    bad = [pid for pid in ids if not pid.isdigit()]

    # 逐年缺口
    gaps = []
    by_year = {}
    for n in nums:
        by_year.setdefault(n // 1000, []).append(n)
    for year, seq in sorted(by_year.items()):
        seq.sort()
        gaps += [(a, b) for a, b in zip(seq, seq[1:]) if b != a + 1]

    # 号码合法性
    illegal = []
    for pid, rec in sheet_rows(ws).items():
        if rec is None:
            illegal.append(f"{pid}(非数字号码)")
            continue
        dt, fronts, backs = rec
        try:
            validate_draw(pid, dt, fronts, backs)
        except AssertionError as e:
            illegal.append(str(e))

    print(f"自检: 总行数={len(ids)}  期号范围={ids[0]}~{ids[-1]}  年份={len(by_year)}个")
    print(f"      缺口={gaps or '无'}   非法行={illegal[:5] or '无'}")

    # 内部一致性：号码列必须已升序、已补零；「完整号码」列必须与号码列一致。
    # 这几条是历史遗留问题的高发区（手工录入的行容易漏），单独报出来。
    unsorted, empty_j, mismatch_j = [], [], []
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if row[0] in (None, ""):
            continue
        pid = str(row[0]).strip()
        try:
            fronts = [int(x) for x in row[2:7]]
            backs = [int(x) for x in row[7:9]]
        except (TypeError, ValueError):
            continue
        if fronts != sorted(fronts) or backs != sorted(backs):
            unsorted.append(pid)
        want = " ".join(f"{n:02d}" for n in sorted(fronts) + sorted(backs))
        if not row[9]:
            empty_j.append(pid)
        elif str(row[9]).strip() != want:
            mismatch_j.append((pid, row[9], want))
        if any(not isinstance(x, str) for x in list(row[2:9])):
            unsorted.append(f"{pid}(号码未补零)")

    if unsorted or empty_j or mismatch_j:
        print(f"      一致性: 未升序/未补零 {len(unsorted)} 行 {unsorted[:5]}")
        print(f"              完整号码列为空 {len(empty_j)} 行 {empty_j[:5]}")
        for pid, got, want in mismatch_j[:5]:
            print(f"              完整号码列不符 {pid}: {got!r} 应为 {want!r}")
    print(f"      末行={ws.cell(row=ws.max_row, column=1).value} "
          f"({ws.cell(row=ws.max_row, column=2).value}) "
          f"号码={' '.join(str(ws.cell(row=ws.max_row, column=c).value).zfill(2) for c in range(3, 10))}")
    if api_total is not None:
        flag = "✓ 对账一致" if api_total == len(ids) else f"✗ 官方总期数={api_total}，本地={len(ids)}"
        print(f"      与官方总期数对账: {flag}")
    return not gaps and not illegal and not bad and not unsorted and not empty_j and not mismatch_j


def main():
    ap = argparse.ArgumentParser(description="大乐透历史数据增量更新")
    ap.add_argument("--no-fetch", action="store_true", help="不联网，只用 NEW_DRAWS 手工补录")
    ap.add_argument("--dry-run", action="store_true", help="只列出要补的期次，不写文件")
    ap.add_argument("--check", action="store_true", help="只对数据表做自检，不更新")
    ap.add_argument("--pages", type=int, default=3, help="联网抓取页数（默认3页=300期）")
    ap.add_argument("--no-repair", action="store_true", help="不修补丢样式的行")
    ap.add_argument("--snapshot", action="store_true",
                    help="更新后另存 大乐透历史开奖数据_含<期号>.xlsx 作快照")
    args = ap.parse_args()

    data_path = find_data_file()
    print(f"数据表: {data_path}")

    if args.check:
        sys.exit(0 if self_check(data_path) else 1)

    wb, ws, existing = read_sheet(data_path)
    print(f"表内已有 {len(existing)} 期")

    # ---- 数据来源：官方接口 + 手工补录（手工优先） ----
    fetched, api_total = {}, None
    if not args.no_fetch:
        print(f"正在从体彩官方接口抓取最近 {args.pages} 页…")
        try:
            fetched, api_total = fetch_official(page_count=args.pages)
            print(f"  接口返回 {len(fetched)} 期（官方总期数 {api_total}）")
        except Exception as e:
            print(f"  ! 联网失败: {e}\n  → 本次只用 NEW_DRAWS 手工补录")

        # 已存在期次与官方数据对账，发现不一致就报警（不自动改写历史）
        local = sheet_rows(ws)
        mismatch = []
        for pid, (dt, fronts, backs) in fetched.items():
            cur = local.get(pid)
            if cur and cur != (dt, fronts, backs):
                mismatch.append(f"{pid}: 本地 {' '.join(map(str, cur[1] + cur[2]))} vs "
                                f"官方 {' '.join(map(str, fronts + backs))}")
        if mismatch:
            print(f"  ! 发现 {len(mismatch)} 期与官方不一致（未自动改写，请人工确认）:")
            for m in mismatch[:5]:
                print(f"      {m}")

    merged = {pid: (dt, f, b) for pid, (dt, f, b) in fetched.items()}
    for pid, dt, f, b in NEW_DRAWS:
        merged[pid] = (dt, sorted(f), sorted(b))

    todo = sorted(pid for pid in merged if pid not in existing)
    if not todo:
        print("✓ 没有需要补的期次，表已是最新")
        self_check(data_path, api_total)
        return

    for pid in todo:
        dt, fronts, backs = merged[pid]
        validate_draw(pid, dt, fronts, backs)

    last_pid = max(int(p) for p in existing)
    tail = [(p, *merged[p]) for p in todo if int(p) > last_pid]
    interior = [(p, *merged[p]) for p in todo if int(p) <= last_pid]

    print(f"\n待补 {len(todo)} 期: {todo[0]}~{todo[-1]}")
    for pid in todo:
        dt, fronts, backs = merged[pid]
        tag = "新期" if int(pid) > last_pid else "补断档"
        print(f"  [{tag}] {pid}  {dt}  "
              f"{' '.join(f'{n:02d}' for n in fronts)} + {' '.join(f'{n:02d}' for n in backs)}")

    if args.dry_run:
        print("\n(--dry-run 未写入任何文件)")
        return

    sample_row = find_style_row(ws)
    style_refs = [ws.cell(row=sample_row, column=c)._style for c in range(1, 11)]
    print(f"\n样式样本行: 第 {sample_row} 行（期号 {ws.cell(row=sample_row, column=1).value}）")
    if interior:
        insert_rows_sorted(ws, interior, style_refs)
    if tail:
        write_rows(ws, ws.max_row + 1, tail, style_refs)

    if not args.no_repair:
        fixed = repair_unstyled(ws, sample_row)
        if fixed:
            print(f"修补丢样式行 {len(fixed)} 行（第 {fixed[0]}~{fixed[-1]} 行，"
                  f"期号 {ws.cell(row=fixed[0], column=1).value}~{ws.cell(row=fixed[-1], column=1).value}）")

    full_range = f"A1:J{ws.max_row}"
    if ws.auto_filter.ref != full_range:
        print(f"自动筛选范围: {ws.auto_filter.ref} → {full_range}")
        ws.auto_filter.ref = full_range

    wb.save(data_path)
    print(f"\n[OK] 已保存: {data_path} （新增 {len(todo)} 期）")

    if args.snapshot:
        snap = os.path.join(os.path.dirname(data_path),
                            f"大乐透历史开奖数据_含{todo[-1]}.xlsx")
        wb.save(snap)
        print(f"[快照] 已另存: {snap}")

    ok = self_check(data_path, api_total)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
