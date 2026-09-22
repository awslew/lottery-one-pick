# -*- coding: utf-8 -*-
"""单元测试：python -m unittest discover -s tests -v

覆盖三块纯逻辑 + 两条端到端链路：
  ① 奖金表（2026 新规，奖池上浮/基准两档）
  ② 前区 / 后区规则：每条都用一个「只违反这条」的样本独立验证
  ③ 历史杀号（全历史杀 vs 仅杀 2026）
  ④ 随机一注必过三关 + 筛号器能复算出同一结论
  ⑤ 三关上下文不含目标期及之后的数据（不会用未来信息）
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lottery_core import (  # noqa: E402
    BACK_POOL, FRONT_POOL, calc_prize, check_back_all, check_front_all,
    is_bet_safe,
)
from paths import find_data_file  # noqa: E402


def data_available():
    try:
        find_data_file()
        return True
    except SystemExit:
        return False


class TestPrizeTable(unittest.TestCase):
    """2026 新规奖级表：5+0 与 4+2 合并为三等奖，4+0 与 3+2 合并为五等奖。"""

    def test_floating_prizes(self):
        self.assertEqual(calc_prize(5, 2), ('浮动', '一等奖'))
        self.assertEqual(calc_prize(5, 1), ('浮动', '二等奖'))

    def test_third_prize_merges_5plus0_and_4plus2(self):
        for fm, bm in ((5, 0), (4, 2)):
            self.assertEqual(calc_prize(fm, bm, pool_big=False), (5000, '三等奖'))
            self.assertEqual(calc_prize(fm, bm, pool_big=True), (6666, '三等奖'))

    def test_fifth_prize_merges_4plus0_and_3plus2(self):
        for fm, bm in ((4, 0), (3, 2)):
            self.assertEqual(calc_prize(fm, bm, pool_big=False), (150, '五等奖'))
            self.assertEqual(calc_prize(fm, bm, pool_big=True), (200, '五等奖'))

    def test_each_tier_both_pools(self):
        cases = {
            (4, 1): ('四等奖', 300, 380),
            (3, 1): ('六等奖', 15, 18),
            (2, 2): ('六等奖', 15, 18),
            (3, 0): ('七等奖', 5, 7),
            (2, 1): ('七等奖', 5, 7),
            (1, 2): ('七等奖', 5, 7),
            (0, 2): ('七等奖', 5, 7),
        }
        for (fm, bm), (tier, base, big) in cases.items():
            self.assertEqual(calc_prize(fm, bm, False), (base, tier), f"{fm}+{bm} 基准档")
            self.assertEqual(calc_prize(fm, bm, True), (big, tier), f"{fm}+{bm} 上浮档")

    def test_no_prize(self):
        for fm, bm in ((2, 0), (1, 1), (1, 0), (0, 1), (0, 0)):
            self.assertEqual(calc_prize(fm, bm), (0, '未中奖'), f"{fm}+{bm} 不该中奖")


class TestFrontRules(unittest.TestCase):
    """前区规则：每条都用一个「只违反这条」的样本，确认它能独立拦住。"""

    COLD = frozenset()
    LAST = frozenset({1, 2, 3, 4, 5})

    def ok(self, front, last=None):
        return check_front_all(frozenset(front), self.COLD,
                               self.LAST if last is None else last, 0, 0)

    def test_baseline_ticket_passes(self):
        # 和值59 跨度18 3奇2偶 区间2/0/3 最长2连 2质数 首4尾22
        self.assertTrue(self.ok({4, 5, 9, 21, 22}))

    def test_all_odd_and_all_even_rejected(self):
        self.assertFalse(self.ok({9, 11, 19, 21, 23}))    # 5奇0偶
        self.assertFalse(self.ok({4, 10, 14, 22, 34}))    # 0奇5偶

    def test_zone_count_too_few_rejected(self):
        # 只覆盖 13-24 一个区（和值88 跨度9 2奇3偶 2质数，其余规则都过）
        self.assertFalse(self.ok({14, 15, 18, 19, 22}))

    def test_single_zone_overflow_rejected(self):
        # 单区 5 个
        self.assertFalse(self.ok({1, 2, 3, 4, 5}))

    def test_four_consecutive_rejected_three_allowed(self):
        # 21 22 23 24 是 4 连；样本已避开和值/首尾等其他规则
        self.assertFalse(self.ok({9, 21, 22, 23, 24}))
        # 4 5 6 是 3 连（放宽后允许）
        self.assertTrue(self.ok({4, 5, 6, 21, 22}))

    def test_sum_bounds(self):
        self.assertFalse(self.ok({1, 2, 3, 4, 21}))       # 和值31 < 40
        self.assertFalse(self.ok({29, 30, 31, 32, 35}))   # 和值157 > 150

    def test_span_bounds(self):
        self.assertFalse(self.ok({9, 10, 11, 12, 21}))    # 跨度12 < 13
        self.assertFalse(self.ok({1, 2, 33, 34, 35}))     # 跨度34 > 33

    def test_head_tail_rule(self):
        self.assertFalse(self.ok({21, 22, 23, 24, 30}))   # 首21 > 20
        self.assertFalse(self.ok({1, 2, 3, 4, 20}))       # 尾20 < 21

    def test_prev_draw_overlap_limit(self):
        # 与上期重 2 个（22 不在上期号里），允许
        self.assertTrue(self.ok({1, 2, 22, 23, 24}, last=frozenset({1, 2, 3, 4, 5})))
        # 与上期重 4 个，拦截（样本其余规则都过）
        self.assertFalse(self.ok({1, 2, 3, 4, 22}, last=frozenset({1, 2, 3, 4, 5})))

    def test_prime_count_limit(self):
        # 02 07 13 19 是 4 个质数（和值71 跨度28 3奇2偶 区间2/2/1 首2尾30）
        self.assertTrue(self.ok({2, 7, 13, 19, 30}))
        # 02 11 13 19 23 是 5 个质数
        self.assertFalse(self.ok({2, 11, 13, 19, 23}))

    def test_012_route_all_same_rejected(self):
        self.assertFalse(self.ok({3, 6, 9, 12, 21}))      # 全是 3 的倍数
        self.assertTrue(self.ok({3, 6, 9, 12, 22}))       # 混一路

    def test_ac_value_floor(self):
        # 5 个数的 10 个差值里互异值太少 → AC < 2
        self.assertFalse(self.ok({14, 15, 16, 17, 34}))
        self.assertTrue(self.ok({1, 5, 12, 20, 31}))


class TestBackRules(unittest.TestCase):
    COLD = frozenset()
    LAST = frozenset({1, 2})

    def test_back_span_rule_removed(self):
        # 跨度 11（后区 01 + 12）也必须放行 —— 该规则已整条取消
        self.assertTrue(check_back_all(frozenset({1, 12}), self.COLD, self.LAST))

    def test_cold_limit(self):
        self.assertTrue(check_back_all(frozenset({3, 4}), frozenset({3}), self.LAST))
        self.assertFalse(check_back_all(frozenset({3, 4}), frozenset({3, 4}), self.LAST))

    def test_prev_overlap_limit(self):
        self.assertTrue(check_back_all(frozenset({1, 5}), self.COLD, self.LAST))
        self.assertFalse(check_back_all(frozenset({1, 2}), self.COLD, self.LAST))


class TestHistoryKill(unittest.TestCase):
    HIST = [
        (frozenset({1, 2, 3, 4, 5}), frozenset({1, 2})),        # 早年某期
        (frozenset({10, 11, 12, 13, 14}), frozenset({3, 4})),
    ]
    H26 = [
        (frozenset({20, 21, 22, 23, 24}), frozenset({5, 6})),   # 2026 年某期
    ]

    def test_exact_front_match_killed_for_all_history(self):
        # 撞早年期的 5 个前区 → 全历史杀（哪怕后区完全不同）
        self.assertFalse(is_bet_safe(frozenset({1, 2, 3, 4, 5}), frozenset({11, 12}),
                                     self.HIST, self.H26))

    def test_four_plus_two_killed_for_all_history(self):
        self.assertFalse(is_bet_safe(frozenset({1, 2, 3, 4, 30}), frozenset({1, 2}),
                                     self.HIST, self.H26))

    def test_four_plus_one_only_killed_in_2026(self):
        # 4+1 撞 2026 期 → 杀
        self.assertFalse(is_bet_safe(frozenset({20, 21, 22, 23, 35}), frozenset({5, 9}),
                                     self.HIST, self.H26))
        # 4+1 撞早年期 → 不杀（早年只杀 4+2，且后区无重合）
        self.assertTrue(is_bet_safe(frozenset({1, 2, 3, 4, 30}), frozenset({9, 11}),
                                    self.HIST, self.H26))

    def test_three_plus_two_only_killed_in_2026(self):
        # 3+2 撞 2026 期 → 杀
        self.assertFalse(is_bet_safe(frozenset({20, 21, 22, 33, 35}), frozenset({5, 6}),
                                     self.HIST, self.H26))
        # 3+2 撞早年期 → 不杀（后区与早年 10-14 期只有 1 个重合，不足 4+2）
        self.assertTrue(is_bet_safe(frozenset({10, 11, 12, 33, 35}), frozenset({3, 9}),
                                    self.HIST, self.H26))

    def test_fresh_ticket_is_safe(self):
        self.assertTrue(is_bet_safe(frozenset({7, 15, 23, 29, 34}), frozenset({8, 11}),
                                    self.HIST, self.H26))


@unittest.skipUnless(data_available(), "仓库内没有数据表，跳过端到端测试")
class TestEndToEnd(unittest.TestCase):
    """用真实数据表跑：随机一注必过三关，且筛号器复算结论一致。"""

    def test_pools(self):
        self.assertEqual(len(FRONT_POOL), 35)
        self.assertEqual(len(BACK_POOL), 12)

    def test_random_pick_passes_all_gates(self):
        import random

        from filter_check import build_ctx, check_one, gates, passes
        from lottery_core import current_period

        ctx = build_ctx(current_period())
        rng = random.Random(12345)
        for _ in range(50):
            f = frozenset(rng.sample(FRONT_POOL, 5))
            b = frozenset(rng.sample(BACK_POOL, 2))
            if all(gates(f, b, ctx)):
                self.assertTrue(passes(f, b, ctx))
                passed, fr, br, kill, drift = check_one(f, b, ctx)
                self.assertTrue(passed, f"{sorted(f)} + {sorted(b)} 过筛但 check_one 说不过")
                self.assertFalse(drift, "规则镜像与 lottery_core 出现口径分叉")
                return
        self.fail("50 次随机都没抽到过筛的注，规则可能过严")

    def test_ctx_only_uses_data_before_target_period(self):
        from filter_check import build_ctx
        from lottery_core import current_period

        period = current_period()
        ctx = build_ctx(period)
        self.assertTrue(all(h["pid"] < period for h in ctx["hist"]),
                        "三关上下文里混入了目标期及之后的数据（会用未来信息）")


if __name__ == "__main__":
    unittest.main(verbosity=2)
