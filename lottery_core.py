# -*- coding: utf-8 -*-
"""大乐透核心逻辑模块 — 纯函数 + 常量，无副作用

筛选链路只有三关，全部在这里实现：
  历史关  is_bet_safe()       撞历史开奖号的杀号条款
  前区关  check_front_all()   10 条前区规则
  后区关  check_back_all()    2 条后区规则（后区跨度已取消）

主程序 dlt_pick_one.py（每期出 1 注）与筛号器 filter_check.py 均 import 本模块，
确保筛选逻辑 100% 同步。其余脚本一律用 current_period() 跟随主开关，不写死期号。
"""

from paths import MAIN_SWITCH_FILE_NAME


# ============================================================
# 常量
# ============================================================
FRONT_POOL = list(range(1, 36))
BACK_POOL = list(range(1, 13))
COLD_INTERVAL = 5  # 前区冷号阈值（前区冷号规则已停用，此常量现仅在概况里做冷号统计用）
BACK_COLD_INTERVAL = 8  # 后区冷号阈值（后区仅12个号，阈值5误杀13.96%，放宽至8）
PRIMES = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31}  # 1~35中的质数


# ============================================================
# 当前期号 · 全项目唯一「主开关」
# ============================================================
# 每期只需要改一处：dlt_pick_one.py 里的 CURRENT_PERIOD。
# 其余所有脚本（筛号器 / 逐注体检 / 选号 / 批量分析 / 对账）一律调用本函数跟随，
# 不要再把期号写死在各自文件里 —— 写死了就会出现「主开关已翻、某个脚本还在算上期」。
MAIN_SWITCH_FILE = MAIN_SWITCH_FILE_NAME  # 文件名，读取实现在 paths.read_main_switch()


def current_period():
    """读取主开关 dlt_pick_one.py 里的 CURRENT_PERIOD。"""
    from paths import read_main_switch
    return read_main_switch()


# ============================================================
# 冷号计算
# ============================================================
def calc_cold_fronts(history_all, interval=COLD_INTERVAL):
    """计算前区冷号集合 + last_seen 字典。

    Returns (cold_fronts, front_last_seen)
    """
    FP = list(range(1, 36))
    front_last_seen = {n: -1 for n in FP}
    latest_idx = len(history_all) - 1
    for idx, (hfront, _) in enumerate(history_all):
        for n in FP:
            if n in hfront:
                front_last_seen[n] = idx
    cold_fronts = {n for n in FP
                   if latest_idx - front_last_seen[n] >= interval}
    return cold_fronts, front_last_seen


def calc_cold_backs(history_all, interval=BACK_COLD_INTERVAL):
    """计算后区冷号集合 + last_seen 字典。

    Returns (cold_backs, back_last_seen)
    """
    BP = list(range(1, 13))
    back_last_seen = {n: -1 for n in BP}
    latest_idx = len(history_all) - 1
    for idx, (_, hback) in enumerate(history_all):
        for n in BP:
            if n in hback:
                back_last_seen[n] = idx
    cold_backs = {n for n in BP
                  if latest_idx - back_last_seen[n] >= interval}
    return cold_backs, back_last_seen


# ============================================================
# 前区全部规则检查
# ============================================================
def check_front_all(front, cold_fronts, last_front, cold_min, cold_max):
    """前区全部规则检查（奇偶 / 区间 / 连号 / 和值 / 冷号 / 跨度 / 首尾 / 重号 / 质数 / 012路 / AC值）。

    front   — 前区号码集合（5个）
    Returns True=通过
    """
    # ① 奇偶比：1~4个奇数（禁全奇全偶）
    odd = sum(1 for n in front if n % 2 == 1)
    if odd not in {1, 2, 3, 4}:
        return False

    # ② 区间分布：至少覆盖两区，单区最多4个
    z1 = sum(1 for n in front if 1 <= n <= 12)
    z2 = sum(1 for n in front if 13 <= n <= 24)
    z3 = sum(1 for n in front if 25 <= n <= 35)
    if not ((z1 > 0) + (z2 > 0) + (z3 > 0) >= 2
            and z1 <= 4 and z2 <= 4 and z3 <= 4):
        return False

    # ③ 连号：最多3连号（只砍4连以上）
    sf = sorted(front)
    mc = 1
    cur = 1
    for i in range(1, 5):
        if sf[i] == sf[i - 1] + 1:
            cur += 1
            mc = max(mc, cur)
        else:
            cur = 1
    if mc > 3:
        return False

    # ④ 前区和值 40~150
    if not (40 <= sum(front) <= 150):
        return False

    # ⑤ 前区冷号：动态范围（已移除，经8期验证E值预测不可靠，26076的5冷组合曾被此规则堵死）
    # if not (cold_min <= len(front & cold_fronts) <= cold_max):
    #     return False

    # ⑥ 前区跨度 13~33
    if not (13 <= sf[-1] - sf[0] <= 33):
        return False

    # ⑦ 首尾号：首≤20 且 尾≥21（「尾≥21」保留——它能排除"全小号/全生日号"堆）
    if sf[0] > 20 or sf[-1] < 21:
        return False

    # ⑧ 上期重号：0~3个
    if len(front & last_front) > 3:
        return False

    # ⑨ 质数个数：0~4个
    if sum(1 for n in front if n in PRIMES) > 4:
        return False

    # ⑩ 012路：禁止全同一余数（历史覆盖率99.6%）
    r0 = sum(1 for n in front if n % 3 == 0)
    r1 = sum(1 for n in front if n % 3 == 1)
    r2 = sum(1 for n in front if n % 3 == 2)
    if r0 == 5 or r1 == 5 or r2 == 5:
        return False

    # ⑪ AC值（算术复杂性）：≥2
    sf = sorted(front)
    diffs = set()
    for i in range(5):
        for j in range(i + 1, 5):
            diffs.add(sf[j] - sf[i])
    if len(diffs) - 4 < 2:
        return False

    return True


# ============================================================
# 后区全部规则检查
# ============================================================
def check_back_all(back, cold_backs, last_back):
    """后区全部规则检查（冷号 / 上期重号）。后区跨度规则已取消。

    back    — 后区号码集合（2个）
    Returns True=通过
    """
    # 后区跨度：已取消（原阈值 ≤7）。依据：跨度>7 在全历史误杀 428 期（14.6%），
    # 是全部规则里最狠的一条；后区仅 66 种组合且大众后区选号接近均匀分布，
    # 砍掉 15.2% 换不来任何避分奖收益。
    # （原代码）
    # sb = sorted(back)
    # if sb[-1] - sb[0] > 7:
    #     return False

    # ⑫ 后区冷号 ≤1
    if len(back & cold_backs) > 1:
        return False

    # ⑬ 后区上期重号 ≤1
    if len(back & last_back) > 1:
        return False

    return True


# ============================================================
# 历史杀号
# ============================================================
def is_bet_safe(front, back, history_all, history_2026):
    """历史杀号检查。

    True  = 安全，未被任何历史期命中（可以出号）
    False = 被历史中的某期杀掉了（不能出号）

    规则：
      - 5+* / 4+2      → 全历史杀
      - 4+1 / 4+0 / 3+2 → 仅杀撞 2026 年
    """
    # 5+* 和 4+2：全历史杀
    for hfront, hback in history_all:
        fm = len(front & hfront)
        if fm == 5:
            return False
        if fm == 4 and len(back & hback) == 2:
            return False

    # 3+2 / 4+0 / 4+1：仅 2026 杀
    for hfront, hback in history_2026:
        fm = len(front & hfront)
        if fm == 4 and len(back & hback) <= 1:
            return False
        if fm == 3 and len(back & hback) == 2:
            return False

    return True


# ============================================================
# 奖金计算
# ============================================================
# 表依据：超级大乐透 2026 新规（自第 26014 期 / 2026-02-02 起施行）。
#   官方原文：「新规则将原有奖级合并优化，'5+0'与'4+2'合并为三等奖，
#   '4+0'与'3+2'合并为五等奖」；「奖池低于8亿元，三至七等奖单注奖金分别为
#   5000/300/150/15/5 元；奖池达到或超过8亿元时提升至 6666/380/200/18/7 元」。
def calc_prize(front_match, back_match, pool_big=False):
    """计算单注奖金。

    front_match — 前区命中个数(0-5)
    back_match  — 后区命中个数(0-2)
    pool_big    — True=奖池>=8亿, False=奖池<8亿

    返回: (奖金金额, 奖级名称)
    """
    fm, bm = front_match, back_match
    if fm == 5 and bm == 2:
        return ('浮动', '一等奖')
    if fm == 5 and bm == 1:
        return ('浮动', '二等奖')

    tbl = {True: 6666, False: 5000}
    if (fm == 5 and bm == 0) or (fm == 4 and bm == 2):
        return (tbl[pool_big], '三等奖')

    tbl = {True: 380, False: 300}
    if fm == 4 and bm == 1:
        return (tbl[pool_big], '四等奖')

    tbl = {True: 200, False: 150}
    if (fm == 4 and bm == 0) or (fm == 3 and bm == 2):
        return (tbl[pool_big], '五等奖')

    tbl = {True: 18, False: 15}
    if (fm == 3 and bm == 1) or (fm == 2 and bm == 2):
        return (tbl[pool_big], '六等奖')

    tbl = {True: 7, False: 5}
    if (fm == 3 and bm == 0) or (fm == 2 and bm == 1) \
       or (fm == 1 and bm == 2) or (fm == 0 and bm == 2):
        return (tbl[pool_big], '七等奖')

    return (0, '未中奖')
