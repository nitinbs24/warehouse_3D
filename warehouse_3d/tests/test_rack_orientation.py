from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase

from ..putaway import aisles
from ..putaway.aisles import slot_distances
from .common import create_p05, create_zone

BACK_DOOR = (0.0, 8.4, 2.0, 1.6, 'both')  # toy 10 × 10 m building, on the y = 10 wall


class TestRackOrientation(TransactionCase):
    """T31: a rack row runs along y (default) or along x; everything that uses its footprint follows."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref('stock.warehouse0')  # 60 × 40 m
        cls.zone = create_zone(cls.env, cls.warehouse)
        cls.Row = cls.env['warehouse.rack.row']

    def setUp(self):
        super().setUp()
        aisles.slot_distances.cache_clear()

    def _row(self, **kw):
        return create_p05(self.env, self.warehouse, self.zone, **kw)

    def test_existing_rows_run_along_y(self):
        row = self._row()
        self.assertEqual(row.orientation, 'y')
        for got, want in zip(row._wh3d_footprint(), (9.7, 1.0, 10.8, 19.9)):
            self.assertAlmostEqual(got, want)

    def test_x_row_footprint_runs_along_x(self):
        row = self._row(orientation='x', x=10.0, y=30.0)
        x0, y0, x1, y1 = row._wh3d_footprint()
        self.assertAlmostEqual(x1 - x0, 18.9)
        self.assertAlmostEqual(y1 - y0, 1.1)

    def test_x_row_must_lie_inside_the_building(self):
        with self.assertRaisesRegex(ValidationError, 'inside'):
            self._row(orientation='x', x=45.0, y=30.0)  # 45 + 18.9 > 60

    def test_rotating_onto_another_row_is_refused(self):
        self._row(code='P06', x=15.0, y=1.0)              # y row, x 15–16.1
        p05 = self._row(x=9.7, y=1.0)                     # y row, x 9.7–10.8
        with self.assertRaisesRegex(ValidationError, 'overlap'):
            p05.orientation = 'x'                          # now x 9.7–28.6, y 1–2.1: crosses P06

    def test_rotation_keeps_the_locations(self):
        row = self._row()
        before = sorted(row.slot_location_ids.mapped('name'))
        row.write({'orientation': 'x', 'x': 5.0, 'y': 30.0})
        self.assertEqual(sorted(row.slot_location_ids.mapped('name')), before)

    def test_editor_save_round_trip(self):
        row = self._row()
        result = self.Row.wh3d_save_layout(self.warehouse.id, {'write': [{'id': row.id, 'vals': {
            'orientation': 'x', 'x': 5.0, 'y': 30.0}}]})
        saved = next(r for r in result['layout']['rows'] if r['id'] == row.id)
        self.assertEqual(saved['orientation'], 'x')

    def test_distances_for_an_x_row_hand_checked(self):
        # x row along x 2–8, y 4–5. Bay 1 (x 2–3) is reached from the cell above its face (x 2.5–3, y 5–5.5):
        # 2 cells left + 6 up to the door's nearest cell (1.5–2, 8–8.5) = 8 cells. Bay 6: 12 + 6 = 18 cells.
        row = (1, 2.0, 4.0, 1.0, 6, 1.0, 1, 'x')
        d = slot_distances((10.0, 10.0), (row,), (BACK_DOOR,))
        self.assertEqual(d[(1, 1, 1)], (4.0, 4.0))
        self.assertEqual(d[(1, 6, 1)], (9.0, 9.0))

    def test_x_row_blocks_the_floor(self):
        # A wall of an x row across the building (x 0–9.5, y 4–5) forces a slot below it to go round its end.
        wall = (1, 0.0, 4.0, 1.0, 19, 0.5, 1, 'x')
        target = (2, 0.0, 0.0, 1.0, 2, 1.0, 1, 'x')         # x 0–2, y 0–1, reached from y 1–1.5
        d = slot_distances((10.0, 10.0), (wall, target), (BACK_DOOR,))
        # From cell (x 0.5–1, y 1–1.5) right to x 9.5–10, up past the wall, back left to the door: 18 + 14 + 16 cells.
        self.assertEqual(d[(2, 1, 1)][1], 24.0)

    def test_putaway_ranks_and_hard_rules_check_an_x_row(self):
        row = self._row(orientation='x', x=10.0, y=30.0)
        self.env['warehouse.layout.area'].create({'name': 'Dock', 'kind': 'dock', 'x': 3.0, 'y': 38.4,
                                                  'width': 3.0, 'depth': 1.6, 'warehouse_id': self.warehouse.id})
        Product = self.env['product.product']
        rice = Product.create({'name': 'Rice', 'is_storable': True, 'weight': 100.0,
                               'wh3d_length': 1.2, 'wh3d_width': 1.0, 'wh3d_height': 1.1})
        glass = Product.create({'name': 'Glass', 'is_storable': True, 'weight': 5.0, 'wh3d_fragile': True,
                                'wh3d_length': 0.5, 'wh3d_width': 0.5, 'wh3d_height': 0.5})
        Rule = self.env['stock.putaway.rule']
        ranked, _removed = Rule._wh3d_rank_slots(rice, 1, row.slot_location_ids, self.warehouse.lot_stock_id)
        self.assertEqual(len(ranked), 70)
        self.assertTrue(all(r['distance'] is not None for r in ranked))
        # Fragile never directly below heavy: same rule, same neighbours, whichever way the row runs.
        above = row.slot_location_ids.filtered(lambda s: s.name == 'P05-01-2-A')
        below = row.slot_location_ids.filtered(lambda s: s.name == 'P05-01-1-A')
        self.env['stock.quant']._update_available_quantity(rice, above, 1)
        ok, reason = Rule._wh3d_check_slots(glass, 1, below, self.warehouse.lot_stock_id)[below.id]
        self.assertFalse(ok)
        self.assertEqual(reason.code, 'fragile')
