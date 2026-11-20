import time

from odoo.tests import TransactionCase

from ..putaway import aisles
from ..putaway.aisles import CELL, slot_distances
from .common import create_p05, create_zone, template_warehouse

# Toy building 10 × 10 m, cells of 0.5 m. Rows are (id, x, y, depth, bays, bay_width, slots_per_level);
# docks are (x, y, width, depth, role). Distances are counted cell centre to cell centre, rectilinear.
BUILDING = (10.0, 10.0)
R1 = (1, 4.0, 0.0, 1.0, 8, 1.0, 1)    # x 4–5 on a cell boundary, y 0–8
R2 = (2, 6.3, 0.0, 1.0, 4, 1.0, 1)    # x 6.3–7.3, off the boundary: blocks cells 6.0–7.5
BACK_DOOR = (0.0, 8.4, 2.0, 1.6, 'both')       # on the y = 10 wall
SIDE_DOOR = (8.4, 0.0, 1.6, 3.0, 'outbound')   # on the x = 10 wall


class TestAisles(TransactionCase):
    """T26: putaway.aisles.slot_distances(), walkable distances from each slot face to the docks."""

    def setUp(self):
        super().setUp()
        aisles.slot_distances.cache_clear()

    def test_cell_size(self):
        self.assertEqual(CELL, 0.5)

    def test_hand_checked_distances(self):
        d = slot_distances(BUILDING, (R1, R2), (BACK_DOOR, SIDE_DOOR))
        # R1 bay 1: left face cell (3.5–4.0, 0.5–1.0) → back door cell (1.5–2.0, 8.0–8.5): 4 + 15 cells.
        # Dispatch: the side door is nearer from the right face, around R2's top end: 1 + 7 + 6 + 3 cells.
        self.assertEqual(d[(1, 1, 1)], (8.0, 9.5))
        # R1 bay 8 (y 7–8): left face, 4 + 1 cells to the back door.
        self.assertEqual(d[(1, 8, 1)][1], 2.5)
        # R2 bay 1 (off-boundary row): right face is next to the side door (1 cell); receiving only via the
        # back door, from the left face over R1's top end: 15 up + 8 across.
        self.assertEqual(d[(2, 1, 1)], (0.5, 11.5))

    def test_path_never_crosses_a_rack(self):
        wall = (1, 4.0, 0.0, 1.0, 9, 1.0, 1)      # x 4–5, y 0–9: only a 1 m gap at the top
        target = (2, 7.0, 0.0, 1.0, 2, 1.0, 1)
        door = (0.0, 0.0, 1.6, 3.0, 'both')       # left wall, bottom
        d = slot_distances(BUILDING, (wall, target), (door,))
        # Straight through the wall would be 10 cells (5 m); around its top end it is 17 + 10 + 13 cells.
        self.assertEqual(d[(2, 1, 1)], (20.0, 20.0))

    def test_back_to_back_gap_is_not_an_aisle(self):
        a = (1, 4.0, 0.0, 1.1, 8, 1.0, 1)          # x 4.0–5.1
        b = (2, 5.3, 0.0, 1.1, 8, 1.0, 1)          # x 5.3–6.4: 0.2 m gap, closed
        d = slot_distances(BUILDING, (a, b), (BACK_DOOR,))
        # Bay 1 of a: left face only (the gap side would be 2 cells nearer to nothing; it isn't walkable).
        self.assertEqual(d[(1, 1, 1)][1], 9.5)
        # b's left face is the gap: it must go round by its right face.
        self.assertGreater(d[(2, 1, 1)][1], d[(1, 1, 1)][1])

    def test_strip_behind_a_row_at_a_ragged_wall_is_closed(self):
        # Building 10.3 m long: a row ending at x 9.9 leaves a 0.4 m strip to the wall, too narrow to walk.
        front = (1, 8.0, 0.0, 0.9, 8, 1.0, 1)      # x 8.0–8.9
        back = (2, 8.9, 0.0, 1.0, 8, 1.0, 1)       # x 8.9–9.9, back to back with front
        d = slot_distances((10.3, 10.0), (front, back), (BACK_DOOR,))
        self.assertEqual(d[(2, 1, 1)], (None, None))
        self.assertIsNotNone(d[(1, 1, 1)][1])

    def test_a_face_behind_a_thin_rack_is_not_reachable(self):
        # Row 1 (x 0–1.1) has only a 0.1 m gap before row 2 (x 1.2–1.5); the free cell beyond row 2 is not
        # next to row 1's face. Row 2's own right face is open.
        row1 = (1, 0.0, 1.0, 1.1, 1, 3.0, 1)
        row2 = (2, 1.2, 1.0, 0.3, 1, 3.0, 1)
        d = slot_distances((5.0, 5.0), (row1, row2), ((4.0, 0.0, 1.0, 0.5, 'both'),))
        self.assertEqual(d[(1, 1, 1)], (None, None))
        self.assertIsNotNone(d[(2, 1, 1)][0])
        self.assertIsNotNone(d[(2, 1, 1)][1])

    def test_positions_follow_the_3d_view(self):
        # Position A is the lower-y half of a bay (as slotBox in view3d/layout.js).
        row = (1, 4.0, 0.0, 1.0, 4, 2.0, 2)
        d = slot_distances(BUILDING, (row,), (BACK_DOOR,))
        self.assertLess(d[(1, 4, 2)][1], d[(1, 4, 1)][1])
        self.assertLess(d[(1, 4, 1)][1], d[(1, 1, 1)][1])

    def test_no_dock_of_that_role_means_none(self):
        d = slot_distances(BUILDING, (R1,), ((0.0, 8.4, 2.0, 1.6, 'inbound'),))
        self.assertEqual(d[(1, 1, 1)], (None, 9.5))
        self.assertEqual(slot_distances(BUILDING, (R1,), ())[(1, 1, 1)], (None, None))

    def test_unreachable_slot_means_none(self):
        # A row boxed in by four others, no way in.
        inner = (1, 4.0, 4.0, 1.0, 1, 1.0, 1)
        box = ((2, 3.0, 3.0, 1.0, 3, 1.0, 1), (3, 5.0, 3.0, 1.0, 3, 1.0, 1),
               (4, 4.0, 3.0, 1.0, 1, 1.0, 1), (5, 4.0, 5.0, 1.0, 1, 1.0, 1))
        d = slot_distances(BUILDING, (inner, *box), (BACK_DOOR,))
        self.assertEqual(d[(1, 1, 1)], (None, None))

    def test_result_is_read_only(self):
        d = slot_distances(BUILDING, (R1,), (BACK_DOOR,))
        with self.assertRaises(TypeError):
            d[(1, 1, 1)] = (0.0, 0.0)


class TestAislesWarehouse(TransactionCase):
    """T26: stock.warehouse._wh3d_slot_distances() and dock roles."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref('stock.warehouse0')
        cls.zone = create_zone(cls.env, cls.warehouse)
        cls.Area = cls.env['warehouse.layout.area']

    def setUp(self):
        super().setUp()
        aisles.slot_distances.cache_clear()

    def dock(self, **kw):
        return self.Area.create({'name': 'Dock', 'kind': 'dock', 'x': 3.0, 'y': 38.4, 'width': 3.0, 'depth': 1.6,
                                 'warehouse_id': self.warehouse.id} | kw)

    def test_dock_role_defaults_to_both(self):
        self.assertEqual(self.dock().role, 'both')

    def test_distances_per_slot_location(self):
        row = create_p05(self.env, self.warehouse, self.zone)
        self.dock()
        distances = self.warehouse._wh3d_slot_distances()
        self.assertEqual(set(distances), set(row.slot_location_ids.ids))
        slot = row.slot_location_ids.filtered(lambda s: s.name == 'P05-07-1-B')
        upper = row.slot_location_ids.filtered(lambda s: s.name == 'P05-07-5-B')
        self.assertEqual(distances[slot.id], distances[upper.id])  # levels share the aisle access point
        self.assertTrue(all(d[0] is not None for d in distances.values()))

    def test_layout_changes_are_seen(self):
        row = create_p05(self.env, self.warehouse, self.zone)
        dock = self.dock()
        slot = row.slot_location_ids[:1]
        before = self.warehouse._wh3d_slot_distances()[slot.id]
        self.env['warehouse.rack.row'].wh3d_save_layout(self.warehouse.id, {
            'areas': {'write': [{'id': dock.id, 'vals': {'x': 40.0, 'role': 'inbound'}}]}})
        after_save = self.warehouse._wh3d_slot_distances()[slot.id]
        self.assertIsNone(after_save[0])           # no dispatch dock any more
        self.assertNotEqual(after_save[1], before[1])
        row.x = 30.0                               # a plain write, not through the editor
        self.assertNotEqual(self.warehouse._wh3d_slot_distances()[slot.id][1], after_save[1])

    def test_layout_returns_dock_role(self):
        self.dock(role='outbound')
        self.assertEqual(self.warehouse.wh3d_get_layout()['areas'][0]['role'], 'outbound')

    def test_template_distances_all_finite_and_fast(self):
        warehouse = template_warehouse(self.env)
        roles = warehouse.wh3d_area_ids.filtered(lambda a: a.kind == 'dock').mapped('role')
        self.assertEqual(sorted(roles), ['inbound'] * 3 + ['outbound'] * 3)
        start = time.perf_counter()
        distances = warehouse._wh3d_slot_distances()
        self.assertLess(time.perf_counter() - start, 2.0)
        self.assertEqual(len(distances), 896 + 1360)
        self.assertTrue(all(d is not None for pair in distances.values() for d in pair))
