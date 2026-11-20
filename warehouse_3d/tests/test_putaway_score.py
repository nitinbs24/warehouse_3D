from odoo.tests import TransactionCase

from ..putaway import score
from ..putaway.score import BENEFIT, WEIGHTS, height_cost, topsis, weighted_sum

PRODUCT = {'abc': 'C', 'heavy': False, 'fragile': False}


def candidate(**kw):
    return {'dispatch': 10.0, 'z': 0.9, 'has_product': False, 'free_m3': 1.0} | kw


class TestPutawayScore(TransactionCase):
    """T27 (ranking half): putaway.score, pure functions."""

    def test_weights_are_the_ahp_result(self):
        self.assertEqual(WEIGHTS, (0.53, 0.20, 0.18, 0.09))
        self.assertAlmostEqual(sum(WEIGHTS), 1.0)

    def test_topsis_worked_example(self):
        # Hand-worked: columns have norms 3 and 4, so the normalised matrix is the identity; weights 0.6 / 0.4.
        # Both benefit: ideal (0.6, 0.4), worst (0, 0); A1 is 0.4 from the ideal and 0.6 from the worst: C = 0.6.
        m = [[3, 0], [0, 4]]
        c = topsis(m, (0.6, 0.4), (True, True))
        self.assertAlmostEqual(c[0], 0.6)
        self.assertAlmostEqual(c[1], 0.4)
        # Second criterion as a cost: A1 is the ideal itself (C = 1), A2 the worst (C = 0).
        self.assertEqual([round(x, 9) for x in topsis(m, (0.6, 0.4), (True, False))], [1.0, 0.0])

    def test_topsis_is_scale_invariant(self):
        m = [[3, 7], [5, 2], [4, 4]]
        a = topsis(m, (0.5, 0.5), (False, True))
        b = topsis([[x * 100, y] for x, y in m], (0.5, 0.5), (False, True))
        self.assertEqual([round(x, 9) for x in a], [round(x, 9) for x in b])

    def test_topsis_minmax_scaling_keeps_a_sparse_column_from_dominating(self):
        # 1000 slots, one holds the product (benefit) but is the farthest (cost); both columns equally weighted.
        m = [[d, 0] for d in range(1, 1000)] + [[1000, 1]]
        vector = topsis(m, (0.5, 0.5), (False, True))
        minmax = topsis(m, (0.7, 0.3), (False, True), minmax=True)
        self.assertEqual(vector.index(max(vector)), 999)  # textbook norm: the sparse column wins outright
        self.assertEqual(minmax.index(max(minmax)), 0)    # min-max: the heavier travel weight wins

    def test_topsis_degenerate_column_contributes_nothing(self):
        with_const = topsis([[1, 5], [2, 5], [3, 5]], (0.5, 0.5), (False, False))
        without = topsis([[1], [2], [3]], (1.0,), (False,))
        self.assertEqual([round(x, 9) for x in with_const], [round(x, 9) for x in without])
        self.assertEqual(topsis([[0, 0], [0, 0]], (0.5, 0.5), (False, False)), [0.5, 0.5])  # all zero / identical
        self.assertEqual(topsis([[4, 4]], (0.5, 0.5), (False, False)), [0.5])  # a single row

    def test_weighted_sum(self):
        m = [[10, 0], [20, 1], [30, 1]]  # cost, benefit
        s = weighted_sum(m, (0.6, 0.4), (False, True))
        self.assertAlmostEqual(s[0], 0.6)   # best cost, worst benefit
        self.assertAlmostEqual(s[1], 0.3 + 0.4)
        self.assertAlmostEqual(s[2], 0.4)   # worst cost, best benefit
        self.assertEqual(weighted_sum([[1], [1]], (1.0,), (False,)), [0.0, 0.0])  # degenerate column

    def best(self, product, candidates):
        scores = score.score(product, candidates)
        return scores.index(max(scores))

    def test_closer_to_dispatch_wins(self):
        self.assertEqual(self.best(PRODUCT, [candidate(dispatch=30), candidate(dispatch=5)]), 1)

    def test_class_factor_makes_travel_matter_more_for_fast_movers(self):
        near, far_with_stock = candidate(dispatch=10), candidate(dispatch=30, has_product=True)
        self.assertEqual(self.best(dict(PRODUCT, abc='A'), [near, far_with_stock]), 0)
        self.assertEqual(self.best(dict(PRODUCT, abc='C'), [near, far_with_stock]), 1)
        self.assertEqual(score.weights_for(None), score.weights_for('C'))  # unclassified = C
        self.assertAlmostEqual(sum(score.weights_for('B')), 1.0)

    def test_heavy_goods_go_low(self):
        heavy = dict(PRODUCT, heavy=True)
        self.assertEqual(self.best(heavy, [candidate(z=2.7), candidate(z=0.9)]), 1)

    def test_fast_and_fragile_goods_go_to_waist_height(self):
        levels = [candidate(z=0.2), candidate(z=1.0), candidate(z=1.8)]
        self.assertEqual(self.best(dict(PRODUCT, abc='A'), levels), 1)
        self.assertEqual(self.best(dict(PRODUCT, fragile=True), levels), 1)
        self.assertEqual(height_cost(PRODUCT, 1.8), 0.0)  # slow ordinary goods don't care
        self.assertEqual(height_cost(dict(PRODUCT, heavy=True, fragile=True), 1.8), 1.8)  # heavy wins

    def test_same_product_already_there_is_a_benefit(self):
        self.assertEqual(self.best(PRODUCT, [candidate(), candidate(has_product=True)]), 1)
        self.assertTrue(BENEFIT[2])

    def test_less_wasted_volume_wins(self):
        self.assertEqual(self.best(PRODUCT, [candidate(free_m3=2.5), candidate(free_m3=0.2)]), 1)
