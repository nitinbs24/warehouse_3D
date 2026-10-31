from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import Form, TransactionCase, new_test_user
from odoo.tools import mute_logger

from .common import create_p05, create_zone


class TestLayoutArea(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref('stock.warehouse0')
        cls.Area = cls.env['warehouse.layout.area']

    def _area(self, **overrides):
        vals = {'name': 'Receiving', 'kind': 'area', 'x': 0.5, 'y': 25.0, 'width': 19.5, 'depth': 13.5,
                'warehouse_id': self.warehouse.id}
        vals.update(overrides)
        return self.Area.create(vals)

    def test_building_defaults_to_template_size(self):
        self.assertEqual((self.warehouse.wh3d_length, self.warehouse.wh3d_width, self.warehouse.wh3d_height),
                         (60.0, 40.0, 10.0))

    def test_create_receiving_area_and_dock(self):
        area = self._area()
        dock = self._area(name='Inbound 1', kind='dock', x=3.0, y=38.4, width=3.0, depth=1.6)
        self.assertEqual(area.kind, 'area')
        self.assertEqual(dock.kind, 'dock')

    def test_rejects_non_positive_size(self):
        for field in ('width', 'depth'):
            with self.subTest(field=field), self.assertRaises(IntegrityError), \
                    mute_logger('odoo.sql_db'), self.cr.savepoint():
                self._area(**{field: 0})

    def test_rejects_area_outside_building(self):
        cases = {'past the right wall': {'x': 50.0, 'width': 11.0},
                 'past the far wall': {'y': 30.0, 'depth': 11.0},
                 'negative x': {'x': -1.0}}
        for label, overrides in cases.items():
            with self.subTest(label), self.assertRaises(ValidationError):
                self._area(**overrides)

    def test_area_touching_the_walls_is_allowed(self):
        self._area(x=0.0, y=0.0, width=60.0, depth=40.0)

    def test_shrinking_building_below_an_area_is_refused(self):
        self._area(name='Shipping', x=40.0, width=19.5)
        with self.assertRaises(ValidationError):
            self.warehouse.wh3d_length = 55.0

    def test_building_size_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self.warehouse.wh3d_height = 0

    def test_warehouse_form_shows_building_size(self):
        form = Form(self.warehouse)
        form.wh3d_length = 80.0
        form.save()
        self.assertEqual(self.warehouse.wh3d_length, 80.0)

    def test_stock_user_reads_areas_but_cannot_write(self):
        area = self._area()
        user = new_test_user(self.env, login='wh3d_area_user', groups='stock.group_stock_user')
        self.assertEqual(area.with_user(user).name, 'Receiving')
        with self.assertRaises(AccessError):
            area.with_user(user).write({'width': 10.0})

    def test_color_defaults_to_grey_and_must_be_hex(self):
        self.assertEqual(self._area().color, '#c3d0dc')
        self.assertEqual(self._area(color='#1A2b3C').color, '#1A2b3C')
        for bad in ('red', '#12345', '#12345g', 'url(x)'):
            with self.subTest(color=bad), self.assertRaisesRegex(ValidationError, 'color'):
                self._area(color=bad)

    def test_dock_must_touch_a_wall(self):
        walls = {'front': dict(x=3.0, y=0.0, width=3.0, depth=1.6), 'back': dict(x=3.0, y=38.4, width=3.0, depth=1.6),
                 'left': dict(x=0.0, y=5.0, width=1.6, depth=3.0), 'right': dict(x=58.4, y=5.0, width=1.6, depth=3.0)}
        for wall, pos in walls.items():
            with self.subTest(wall=wall):
                self.assertTrue(self._area(name=f'Door {wall}', kind='dock', **pos))
        with self.assertRaisesRegex(ValidationError, 'wall'):
            self._area(name='Floating', kind='dock', x=10.0, y=10.0, width=3.0, depth=1.6)

    def test_floor_area_may_be_anywhere_inside(self):
        self.assertTrue(self._area(name='Middle', x=10.0, y=10.0, width=3.0, depth=3.0))

    def test_area_must_not_overlap_a_rack_row(self):
        row = create_p05(self.env, self.warehouse, create_zone(self.env, self.warehouse))  # x 9.7–10.8, y 1–19.9
        with self.assertRaisesRegex(ValidationError, 'P05'):
            self._area(x=10.0, y=5.0, width=3.0, depth=3.0)
        self.assertTrue(self._area(x=10.8, y=5.0, width=3.0, depth=3.0))  # touching is fine
        self.assertTrue(self._area(kind='dock', x=3.0, y=0.0, width=3.0, depth=1.6, name='Door'))
        self.assertTrue(row)

    def test_area_overlap_is_not_checked_between_areas(self):
        self._area(name='Receiving', x=0.0, y=0.0, width=10.0, depth=10.0)
        self.assertTrue(self._area(name='Staging', x=2.0, y=2.0, width=3.0, depth=3.0))

    def test_row_must_not_move_onto_an_area(self):
        row = create_p05(self.env, self.warehouse, create_zone(self.env, self.warehouse))
        self._area(x=20.0, y=5.0, width=3.0, depth=3.0)
        with self.assertRaisesRegex(ValidationError, 'Receiving'):
            row.x = 19.5
