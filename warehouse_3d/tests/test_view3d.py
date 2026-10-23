from odoo.tests import HttpCase, TransactionCase, tagged


class TestView3dAssets(TransactionCase):

    def test_three_js_is_not_in_the_backend_bundle(self):
        # Three.js (~600 KB) loads only when the 3D view opens, not on every Odoo page.
        paths = [asset[0] for asset in self.env['ir.asset']._get_asset_paths('web.assets_backend', {})]
        self.assertTrue(any('warehouse_3d/static/src/view3d' in p for p in paths), "3D view code missing from bundle")
        self.assertFalse([p for p in paths if 'static/lib/three' in p])


@tagged('post_install', '-at_install')
class TestView3dTour(HttpCase):

    def test_view3d_opens_leaves_and_reopens(self):
        self.start_tour('/odoo', 'warehouse_3d_view3d', login='admin')
