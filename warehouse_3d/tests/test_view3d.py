import random
from unittest.mock import patch

from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tests.common import ChromeBrowser

from .common import create_p05, create_zone, template_rows


class TestView3dAssets(TransactionCase):

    def test_three_js_is_not_in_the_backend_bundle(self):
        # Three.js (~600 KB) loads only when the 3D view opens, not on every Odoo page.
        paths = [asset[0] for asset in self.env['ir.asset']._get_asset_paths('web.assets_backend', {})]
        self.assertTrue(any('warehouse_3d/static/src/view3d' in p for p in paths), "3D view code missing from bundle")
        self.assertFalse([p for p in paths if 'static/lib/three' in p])


@tagged('post_install', '-at_install')
class TestView3dTour(HttpCase):

    def test_view3d_opens_leaves_and_reopens(self):
        warehouse = self.env['stock.warehouse'].search([], limit=1)  # the one the view opens by default
        create_p05(self.env, warehouse)
        self.env['warehouse.layout.area'].create([
            {'name': 'Receiving', 'kind': 'area', 'x': 0.5, 'y': 25.0, 'width': 19.5, 'depth': 13.5,
             'warehouse_id': warehouse.id},
            {'name': 'Inbound 1', 'kind': 'dock', 'x': 3.0, 'y': 38.4, 'width': 3.0, 'depth': 1.6,
             'warehouse_id': warehouse.id},
        ])
        self.start_tour('/odoo', 'warehouse_3d_view3d', login='admin')


    def test_stock_panel_find_pick_and_open(self):
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        create_p05(self.env, warehouse)
        rice = self.env['product.product'].create({
            'name': 'Basmati rice pallet', 'is_storable': True,
            'wh3d_length': 1.2, 'wh3d_width': 1.0, 'wh3d_height': 1.1,  # 1.32 m³ of a 2.673 m³ slot = 49 %
        })
        slot = self.env['stock.location'].search([('name', '=', 'P05-03-2-A'), ('warehouse_id', '=', warehouse.id)])
        self.env['stock.quant']._update_available_quantity(rice, slot, 1)
        self.start_tour('/odoo', 'warehouse_3d_stock', login='admin')


    def test_live_update_without_reload(self):
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        create_p05(self.env, warehouse)
        self.env['product.product'].create({
            'name': 'Basmati rice pallet', 'is_storable': True,
            'wh3d_length': 1.2, 'wh3d_width': 1.0, 'wh3d_height': 1.1,
        })
        self.start_tour('/odoo', 'warehouse_3d_live', login='admin')


    def test_editor_draw_select_and_view_in_3d(self):
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        create_p05(self.env, warehouse)
        self.env['warehouse.layout.area'].create({
            'name': 'Receiving', 'kind': 'area', 'x': 0.5, 'y': 25.0, 'width': 19.5, 'depth': 13.5,
            'warehouse_id': warehouse.id})
        self.start_tour('/odoo', 'warehouse_3d_editor', login='admin')


    def test_walk_mode(self):
        create_p05(self.env, self.env['stock.warehouse'].search([], limit=1))  # lone row at x 9.7
        self.start_tour('/odoo', 'warehouse_3d_walk', login='admin')


    def test_editor_move_add_refuse_and_guard(self):
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        zone = create_zone(self.env, warehouse)
        create_p05(self.env, warehouse, zone)                          # x 9.7
        create_p05(self.env, warehouse, zone, code='P06', x=20.5)
        product = self.env['product.product'].create({'name': 'Rice', 'is_storable': True})
        slot = self.env['stock.location'].search([('name', '=', 'P05-07-1-A'), ('warehouse_id', '=', warehouse.id)])
        self.env['stock.quant']._update_available_quantity(product, slot, 3)
        self.start_tour('/odoo', 'warehouse_3d_editor_edit', login='admin')


    def test_editor_areas_add_move_resize_refuse_delete(self):
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        create_p05(self.env, warehouse, create_zone(self.env, warehouse))  # x 9.7–10.8, y 1–19.9
        self.start_tour('/odoo', 'warehouse_3d_editor_areas', login='admin')


    def test_editor_docks_add_drag_to_wall_resize_delete(self):
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        create_p05(self.env, warehouse, create_zone(self.env, warehouse))
        self.start_tour('/odoo', 'warehouse_3d_editor_docks', login='admin')


@tagged('wh3d_screenshot', '-standard')
class TestView3dScreenshot(HttpCase):
    """Opt-in: ./run_tests.sh wh3d_screenshot — renders the handoff layout and saves a PNG for review."""

    def _screenshot(self, url, tour, prefix):
        # Odoo closes the browser right after a tour; grab the picture just before that.
        original = ChromeBrowser._wait_code_ok

        def wait_then_screenshot(browser, *args, **kwargs):
            result = original(browser, *args, **kwargs)
            browser.take_screenshot(prefix).result(timeout=30)
            return result

        with patch.object(ChromeBrowser, '_wait_code_ok', wait_then_screenshot):
            self.start_tour(url, tour, login='admin')

    def test_screenshot_demo_warehouse(self):
        # Nothing created here: the 3D view as it opens on a fresh demo database (Warehaven DC).
        self._screenshot('/odoo/action-warehouse_3d.action_wh3d_view3d', 'warehouse_3d_screenshot', 'wh3d_demo_')

    def test_screenshot_editor(self):
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        self._template_layout(warehouse)
        self._screenshot('/odoo/action-warehouse_3d.action_wh3d_editor', 'warehouse_3d_editor_screenshot', 'wh3d_editor_')

    def _template_layout(self, warehouse):
        Location = self.env['stock.location']
        pr = Location.create({'name': 'PR', 'usage': 'internal', 'location_id': warehouse.lot_stock_id.id})
        sh = Location.create({'name': 'SH', 'usage': 'internal', 'location_id': warehouse.lot_stock_id.id})
        self.env['warehouse.rack.row'].create([
            dict(r, warehouse_id=warehouse.id, location_id=(pr if r['kind'] == 'pallet' else sh).id)
            for r in template_rows()])
        areas = [('Receiving', 0.5, 25, 19.5, 13.5), ('Charging', 21, 25, 8, 5.5), ('Office', 21, 31.5, 8, 8),
                 ('Packing', 30, 25, 9, 8), ('Shipping', 40, 25, 19.5, 13.5)]
        docks = [3, 8, 13, 44, 49, 54]
        self.env['warehouse.layout.area'].create(
            [{'name': n, 'kind': 'area', 'x': x, 'y': y, 'width': w, 'depth': d, 'warehouse_id': warehouse.id}
             for n, x, y, w, d in areas]
            + [{'name': f'Dock {i + 1}', 'kind': 'dock', 'x': x, 'y': 38.4, 'width': 3, 'depth': 1.6,
                'warehouse_id': warehouse.id} for i, x in enumerate(docks)])

    def _seed_stock(self, warehouse):
        # Seeded stock across all fill bands, plus one product without dimensions.
        rng = random.Random(20261023)
        Product = self.env['product.product']
        products = [
            Product.create({'name': 'Rice pallet', 'is_storable': True,
                            'wh3d_length': 1.2, 'wh3d_width': 1.0, 'wh3d_height': 0.9}),   # 1.08 m³ → ~40 %
            Product.create({'name': 'Oil pallet', 'is_storable': True,
                            'wh3d_length': 1.2, 'wh3d_width': 1.0, 'wh3d_height': 1.6}),   # 1.92 m³ → ~72 %
            Product.create({'name': 'Water pallet', 'is_storable': True,
                            'wh3d_length': 1.3, 'wh3d_width': 1.1, 'wh3d_height': 1.7}),   # 2.43 m³ → ~91 %
            Product.create({'name': 'Unmeasured pallet', 'is_storable': True}),
        ]
        bins = [Product.create({'name': f'Small part {i}', 'is_storable': True,
                                'wh3d_length': 0.3, 'wh3d_width': 0.2, 'wh3d_height': 0.1}) for i in range(3)]
        Quant = self.env['stock.quant']
        for slot in self.env['stock.location'].search([('wh3d_node', '=', 'slot'), ('warehouse_id', '=', warehouse.id)]):
            if rng.random() < 0.65:
                if slot.name.startswith('P'):
                    Quant._update_available_quantity(rng.choice(products), slot, 1)
                else:
                    Quant._update_available_quantity(rng.choice(bins), slot, rng.randint(2, 12))

    def test_screenshot_walk(self):
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        self._template_layout(warehouse)
        self._seed_stock(warehouse)
        self._screenshot('/odoo/action-warehouse_3d.action_wh3d_view3d', 'warehouse_3d_walk_screenshot', 'wh3d_walk_')

    def test_screenshot_template_layout(self):
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        self._template_layout(warehouse)
        self._seed_stock(warehouse)
        self._screenshot('/odoo/action-warehouse_3d.action_wh3d_view3d', 'warehouse_3d_screenshot', 'wh3d_view3d_')
