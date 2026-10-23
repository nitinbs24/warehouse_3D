from unittest.mock import patch

from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tests.common import ChromeBrowser


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
        zone = self.env['stock.location'].create({
            'name': 'PR', 'usage': 'internal', 'location_id': warehouse.lot_stock_id.id})
        self.env['warehouse.rack.row'].create({
            'code': 'P05', 'kind': 'pallet', 'x': 9.7, 'y': 1.0, 'bays': 7, 'bay_width': 2.7,
            'depth': 1.1, 'levels': 5, 'level_height': 1.8, 'slots_per_level': 2,
            'warehouse_id': warehouse.id, 'location_id': zone.id,
        })
        self.env['warehouse.layout.area'].create([
            {'name': 'Receiving', 'kind': 'area', 'x': 0.5, 'y': 25.0, 'width': 19.5, 'depth': 13.5,
             'warehouse_id': warehouse.id},
            {'name': 'Inbound 1', 'kind': 'dock', 'x': 3.0, 'y': 38.4, 'width': 3.0, 'depth': 1.6,
             'warehouse_id': warehouse.id},
        ])
        self.start_tour('/odoo', 'warehouse_3d_view3d', login='admin')


@tagged('wh3d_screenshot', '-standard')
class TestView3dScreenshot(HttpCase):
    """Opt-in: ./run_tests.sh wh3d_screenshot — renders the handoff layout and saves a PNG for review."""

    def test_screenshot_template_layout(self):
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        Location = self.env['stock.location']
        pr = Location.create({'name': 'PR', 'usage': 'internal', 'location_id': warehouse.lot_stock_id.id})
        sh = Location.create({'name': 'SH', 'usage': 'internal', 'location_id': warehouse.lot_stock_id.id})
        pallet_x = [0.2, 4.3, 5.6, 9.7, 11.0, 15.1, 16.4, 20.5, 21.8, 25.9, 27.2, 31.3, 32.6, 36.7]
        shelf_x = [round(39.6 + 2.4 * k + d, 1) for k in range(8) for d in (0, 0.6)] + [59.0]
        rows = [{'code': f'P{i + 1:02d}', 'kind': 'pallet', 'x': x, 'y': 1.0, 'bays': 7, 'bay_width': 2.7,
                 'depth': 1.1, 'levels': 5, 'level_height': 1.8, 'slots_per_level': 2, 'location_id': pr.id}
                for i, x in enumerate(pallet_x)]
        rows += [{'code': f'S{i + 1:02d}', 'kind': 'shelf', 'x': x, 'y': 2.0, 'bays': 16, 'bay_width': 1.0,
                  'depth': 0.6, 'levels': 5, 'level_height': 0.4, 'slots_per_level': 1, 'location_id': sh.id}
                 for i, x in enumerate(shelf_x)]
        self.env['warehouse.rack.row'].create([dict(r, warehouse_id=warehouse.id) for r in rows])
        areas = [('Receiving', 0.5, 25, 19.5, 13.5), ('Charging', 21, 25, 8, 5.5), ('Office', 21, 31.5, 8, 8),
                 ('Packing', 30, 25, 9, 8), ('Shipping', 40, 25, 19.5, 13.5)]
        docks = [3, 8, 13, 44, 49, 54]
        self.env['warehouse.layout.area'].create(
            [{'name': n, 'kind': 'area', 'x': x, 'y': y, 'width': w, 'depth': d, 'warehouse_id': warehouse.id}
             for n, x, y, w, d in areas]
            + [{'name': f'Dock {i + 1}', 'kind': 'dock', 'x': x, 'y': 38.4, 'width': 3, 'depth': 1.6,
                'warehouse_id': warehouse.id} for i, x in enumerate(docks)])
        # Odoo closes the browser right after a tour; grab the picture just before that.
        original = ChromeBrowser._wait_code_ok

        def wait_then_screenshot(browser, *args, **kwargs):
            result = original(browser, *args, **kwargs)
            browser.take_screenshot('wh3d_view3d_').result(timeout=30)
            return result

        with patch.object(ChromeBrowser, '_wait_code_ok', wait_then_screenshot):
            self.start_tour('/odoo/action-warehouse_3d.action_wh3d_view3d', 'warehouse_3d_screenshot', login='admin')
