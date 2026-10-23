from odoo.tests import Form, TransactionCase, new_test_user


class TestSceneData(TransactionCase):
    """stock.warehouse.wh3d_get_scene(): everything the 3D view draws, in one call."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref('stock.warehouse0')
        stock = cls.warehouse.lot_stock_id
        cls.pr = cls.env['stock.location'].create({'name': 'PR', 'usage': 'internal', 'location_id': stock.id})
        cls.Row = cls.env['warehouse.rack.row']
        # Slot capacity: (2.7 / 2) × 1.1 × 1.8 = 2.673 m³
        cls.row = cls.Row.create(cls._row_vals('P05', 9.7))
        cls.receiving = cls.env['warehouse.layout.area'].create({
            'name': 'Receiving', 'kind': 'area', 'x': 0.5, 'y': 25.0, 'width': 19.5, 'depth': 13.5,
            'warehouse_id': cls.warehouse.id,
        })
        # 1.2 × 1.0 × 1.1 = 1.32 m³ per unit
        cls.rice = cls.env['product.product'].create({
            'name': 'Basmati rice pallet', 'default_code': 'PR-1001', 'is_storable': True,
            'wh3d_length': 1.2, 'wh3d_width': 1.0, 'wh3d_height': 1.1,
        })
        cls.oil = cls.env['product.product'].create({
            'name': 'Sunflower oil', 'default_code': 'PR-1002', 'is_storable': True,
            'wh3d_length': 0.3, 'wh3d_width': 0.3, 'wh3d_height': 0.4,
        })
        cls.no_dims = cls.env['product.product'].create({'name': 'Mystery box', 'is_storable': True})

    @classmethod
    def _row_vals(cls, code, x):
        return {
            'code': code, 'kind': 'pallet', 'x': x, 'y': 1.0, 'bays': 7, 'bay_width': 2.7,
            'depth': 1.1, 'levels': 5, 'level_height': 1.8, 'slots_per_level': 2,
            'warehouse_id': cls.warehouse.id, 'location_id': cls.pr.id,
        }

    def _slot(self, name):
        return self.env['stock.location'].search([('name', '=', name)])

    def _put(self, product, slot_name, qty):
        self.env['stock.quant']._update_available_quantity(product, self._slot(slot_name), qty)

    def _scene_slot(self, scene, name):
        return next(s for s in scene['slots'] if s['code'] == name)

    def test_scene_has_building_areas_rows_and_slots(self):
        scene = self.warehouse.wh3d_get_scene()
        self.assertEqual(scene['building'], {'length': 60.0, 'width': 40.0, 'height': 10.0})
        self.assertEqual([a['name'] for a in scene['areas']], ['Receiving'])
        self.assertEqual(scene['areas'][0]['kind'], 'area')
        self.assertEqual([r['code'] for r in scene['rows']], ['P05'])
        self.assertEqual(scene['rows'][0]['bays'], 7)
        self.assertEqual(len(scene['slots']), 70)

    def test_slot_carries_indices_and_capacity(self):
        slot = self._scene_slot(self.warehouse.wh3d_get_scene(), 'P05-03-2-A')
        self.assertEqual(slot['location_id'], self._slot('P05-03-2-A').id)
        self.assertEqual(slot['row_id'], self.row.id)
        self.assertEqual((slot['bay'], slot['level'], slot['position']), (3, 2, 1))
        self.assertAlmostEqual(slot['capacity_m3'], 2.673, places=3)
        self.assertEqual(slot['path'], 'WH/Stock/PR/P05/P05-03/P05-03-2/P05-03-2-A')

    def test_empty_slot_has_no_stock(self):
        slot = self._scene_slot(self.warehouse.wh3d_get_scene(), 'P05-01-1-A')
        self.assertIsNone(slot['stock'])

    def test_stocked_slot_reports_product_volume_and_fill(self):
        self._put(self.rice, 'P05-01-1-A', 1)
        stock = self._scene_slot(self.warehouse.wh3d_get_scene(), 'P05-01-1-A')['stock']
        self.assertEqual(stock['product_id'], self.rice.id)
        self.assertEqual(stock['name'], 'Basmati rice pallet')
        self.assertEqual(stock['default_code'], 'PR-1001')
        self.assertEqual(stock['qty'], 1)
        self.assertEqual(stock['uom'], self.rice.uom_id.name)
        self.assertAlmostEqual(stock['used_m3'], 1.32, places=3)
        self.assertAlmostEqual(stock['fill'], 1.32 / 2.673, places=3)
        self.assertFalse(stock['mixed'])

    def test_mixed_slot_names_largest_quant_and_sums_volume(self):
        self._put(self.rice, 'P05-01-1-A', 1)
        self._put(self.oil, 'P05-01-1-A', 5)  # 5 × 0.036 = 0.18 m³
        stock = self._scene_slot(self.warehouse.wh3d_get_scene(), 'P05-01-1-A')['stock']
        self.assertTrue(stock['mixed'])
        self.assertEqual(stock['product_id'], self.oil.id)  # 5 units beats 1
        self.assertAlmostEqual(stock['used_m3'], 1.32 + 0.18, places=3)

    def test_product_without_dimensions_gives_no_fill(self):
        self._put(self.no_dims, 'P05-01-1-A', 3)
        stock = self._scene_slot(self.warehouse.wh3d_get_scene(), 'P05-01-1-A')['stock']
        self.assertEqual(stock['qty'], 3)
        self.assertIsNone(stock['used_m3'])
        self.assertIsNone(stock['fill'])

    def test_archived_slots_are_left_out(self):
        self.row.bays = 6
        self.assertEqual(len(self.warehouse.wh3d_get_scene()['slots']), 60)

    def test_get_slots_returns_only_the_asked_slots(self):
        self._put(self.rice, 'P05-02-1-B', 1)
        ids = (self._slot('P05-02-1-B') | self._slot('P05-02-1-A') | self.pr).ids
        slots = self.env['stock.warehouse'].wh3d_get_slots(ids)
        self.assertEqual(sorted(s['code'] for s in slots), ['P05-02-1-A', 'P05-02-1-B'])  # PR is not a slot
        self.assertEqual(next(s for s in slots if s['code'] == 'P05-02-1-B')['stock']['qty'], 1)

    def test_layout_has_building_areas_and_rows_but_no_slots(self):
        layout = self.warehouse.wh3d_get_layout()
        self.assertEqual(set(layout), {'warehouse_id', 'building', 'areas', 'rows'})
        self.assertEqual(layout['warehouse_id'], self.warehouse.id)
        self.assertEqual(layout['rows'], self.warehouse.wh3d_get_scene()['rows'])

    def test_query_count_does_not_grow_with_slots(self):
        self._put(self.rice, 'P05-01-1-A', 1)

        def count_queries():
            self.env.invalidate_all()
            before = self.cr.sql_log_count
            self.warehouse.wh3d_get_scene()
            return self.cr.sql_log_count - before

        one_row = count_queries()
        self.assertGreater(one_row, 0, "query counter isn't counting")
        self.Row.create([self._row_vals('P06', 13.0), self._row_vals('P07', 16.0)])
        self._put(self.oil, 'P07-01-1-A', 2)
        self.assertEqual(count_queries(), one_row)

    def test_stock_user_can_load_the_scene(self):
        user = new_test_user(self.env, login='wh3d_scene_user', groups='stock.group_stock_user')
        scene = self.warehouse.with_user(user).wh3d_get_scene()
        self.assertEqual(len(scene['slots']), 70)

    def test_product_form_has_dimensions(self):
        form = Form(self.env['product.template'])
        form.name = 'Carton'
        form.wh3d_length = 0.4
        form.wh3d_width = 0.3
        form.wh3d_height = 0.2
        template = form.save()
        self.assertEqual(template.product_variant_id.wh3d_height, 0.2)
