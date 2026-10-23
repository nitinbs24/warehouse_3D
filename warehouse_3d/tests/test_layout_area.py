from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import Form, TransactionCase, new_test_user
from odoo.tools import mute_logger


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
